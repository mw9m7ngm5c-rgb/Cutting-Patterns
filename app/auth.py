"""Sign-in for the web app: user accounts, password hashing and a signed session cookie.

Login is required once any user account exists, or always when the server sets CP_REQUIRE_LOGIN=1
(the cloud set-up does). On a single office Mac with no accounts the app stays open, as before.

Passwords are hashed with scrypt (Python's standard library). The session cookie holds the user id
and an expiry, signed with HMAC-SHA256 using CP_SECRET_KEY (or a key generated once and kept in the
data folder), so it cannot be forged or extended.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import os
import pathlib
import secrets
import time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models as m

COOKIE = "cp_session"
SESSION_HOURS = 12
MIN_PASSWORD = 8
_N, _R, _P = 2 ** 14, 8, 1


# ------------------------------------------------------------------ passwords

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return "scrypt$%d$%d$%d$%s$%s" % (_N, _R, _P, base64.b64encode(salt).decode(), base64.b64encode(key).decode())


def check_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, key = stored.split("$")
        got = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                             dklen=len(base64.b64decode(key)))
        return hmac.compare_digest(got, base64.b64decode(key))
    except (ValueError, TypeError):
        return False


def password_problem(password: str) -> str | None:
    if len(password) < MIN_PASSWORD:
        return f"A password needs at least {MIN_PASSWORD} characters."
    return None


# ------------------------------------------------------------------ the signing key

def secret_key(db_file: pathlib.Path | None) -> bytes:
    """CP_SECRET_KEY if set; otherwise a random key made once and kept next to the database."""
    env = os.environ.get("CP_SECRET_KEY")
    if env:
        return env.encode()
    if db_file is None:
        return secrets.token_bytes(32)
    path = db_file.parent / "secret.key"
    if not path.exists():
        path.write_bytes(secrets.token_bytes(32))
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return path.read_bytes()


def make_token(user_id: int, key: bytes, hours: float = SESSION_HOURS) -> str:
    body = f"{user_id}.{int(time.time() + hours * 3600)}"
    sig = hmac.new(key, body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def read_token(token: str | None, key: bytes) -> int | None:
    """The user id in a valid, unexpired token; otherwise None."""
    if not token or token.count(".") != 2:
        return None
    uid, expires, sig = token.split(".")
    want = hmac.new(key, f"{uid}.{expires}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, want):
        return None
    try:
        if int(expires) < time.time():
            return None
        return int(uid)
    except ValueError:
        return None


# ------------------------------------------------------------------ accounts

def login_required(s: Session) -> bool:
    if os.environ.get("CP_REQUIRE_LOGIN", "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    return bool(s.scalar(select(func.count()).select_from(m.User)))


def add_user(s: Session, username: str, password: str, is_admin: bool = False) -> m.User:
    username = username.strip()
    if not username:
        raise ValueError("Type a user name.")
    problem = password_problem(password)
    if problem:
        raise ValueError(problem)
    if s.scalar(select(m.User).where(func.lower(m.User.username) == username.lower())):
        raise ValueError(f"There is already a user called {username}.")
    user = m.User(username=username, password_hash=hash_password(password), is_admin=is_admin)
    s.add(user)
    s.flush()
    return user


def authenticate(s: Session, username: str, password: str) -> m.User | None:
    user = s.scalar(select(m.User).where(func.lower(m.User.username) == username.strip().lower()))
    if user is None:
        check_password(password, hash_password("timing"))     # same work either way
        return None
    if not check_password(password, user.password_hash):
        return None
    user.last_login = dt.datetime.now().replace(microsecond=0)
    return user


def ensure_admin_from_env(s: Session) -> None:
    """On a fresh server: create the first administrator from CP_ADMIN_USER / CP_ADMIN_PASSWORD if no
    account by that name exists yet. Later changes to those variables do not alter existing accounts."""
    name, pw = os.environ.get("CP_ADMIN_USER", "").strip(), os.environ.get("CP_ADMIN_PASSWORD", "")
    if not name or not pw:
        return
    if s.scalar(select(m.User).where(func.lower(m.User.username) == name.lower())) is None:
        add_user(s, name, pw, is_admin=True)
        s.commit()
