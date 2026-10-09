"""Sign-in: passwords, the session cookie, who may see what, and the cloud start-up settings."""
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from app import auth
from app import models as m
from app.main import create_app


@pytest.fixture
def make(tmp_path, monkeypatch):
    for k in ("CP_REQUIRE_LOGIN", "CP_SECRET_KEY", "CP_ADMIN_USER", "CP_ADMIN_PASSWORD"):
        monkeypatch.delenv(k, raising=False)

    def build(**env):
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        app = create_app(f"sqlite:///{tmp_path / 'auth.db'}", run_in_thread=False, parallel=False)
        c = TestClient(app, follow_redirects=False)
        c.db = app.state.db
        return c
    return build


def sign_in(c, user, pw):
    return c.post("/login", data={"username": user, "password": pw, "next": "/"})


def test_passwords_are_hashed_and_checked():
    h = auth.hash_password("correct horse")
    assert h.startswith("scrypt$") and "correct horse" not in h
    assert auth.check_password("correct horse", h)
    assert not auth.check_password("Correct horse", h)
    assert not auth.check_password("x", "rubbish")
    assert auth.hash_password("same") != auth.hash_password("same")            # salted
    assert auth.password_problem("short") and auth.password_problem("long enough") is None


def test_tokens_cannot_be_forged_or_outlive_their_expiry():
    key = b"k" * 32
    t = auth.make_token(7, key)
    assert auth.read_token(t, key) == 7
    uid, exp, sig = t.split(".")
    assert auth.read_token(f"8.{exp}.{sig}", key) is None                     # someone else's id
    assert auth.read_token(f"{uid}.{int(exp) + 9999}.{sig}", key) is None      # stretched expiry
    assert auth.read_token(t, b"other key") is None
    assert auth.read_token(auth.make_token(7, key, hours=-1), key) is None
    assert auth.read_token("garbage", key) is None and auth.read_token(None, key) is None


def test_without_accounts_the_app_stays_open(make):
    c = make()
    assert c.get("/").status_code == 200


def test_cloud_settings_require_login_and_create_the_first_admin(make):
    c = make(CP_REQUIRE_LOGIN="1", CP_ADMIN_USER="Anna", CP_ADMIN_PASSWORD="first-password", CP_SECRET_KEY="s3cret")
    r = c.get("/d/1/logs")
    assert r.status_code == 303 and r.headers["location"].startswith("/login?next=%2Fd%2F1%2Flogs")
    assert c.get("/api/runs/1").status_code == 401
    assert c.get("/healthz").json() == {"ok": True}
    assert c.get("/static/app.css").status_code == 200
    assert c.get("/login").status_code == 200
    t0 = time.time()
    bad = sign_in(c, "anna", "wrong-password")
    assert time.time() - t0 >= 0.9 and "do+not+match" in bad.headers["location"]
    ok = sign_in(c, "ANNA", "first-password")                                   # user names ignore case
    assert ok.status_code == 303 and auth.COOKIE in ok.cookies
    c.cookies.set(auth.COOKIE, ok.cookies[auth.COOKIE])
    home = c.get("/")
    assert home.status_code == 200 and "Anna" in home.text and "Sign out" in home.text
    out = c.post("/logout")
    c.cookies.clear()
    assert out.status_code == 303 and c.get("/").status_code == 303


def test_admins_add_people_and_others_cannot(make):
    c = make(CP_ADMIN_USER="anna", CP_ADMIN_PASSWORD="first-password")
    c.cookies.set(auth.COOKIE, sign_in(c, "anna", "first-password").cookies[auth.COOKIE])
    assert "do+not" not in c.post("/users", data={"username": "ben", "password": "ben-password"}).headers["location"]
    assert "at+least+8" in c.post("/users", data={"username": "cas", "password": "short"}).headers["location"]
    assert "already" in c.post("/users", data={"username": "Ben", "password": "another-pw"}).headers["location"]
    page = c.get("/account").text
    assert "ben" in page and "Download a backup" in page
    backup = c.get("/backup")
    assert backup.status_code == 200 and backup.content[:16] == b"SQLite format 3\x00"

    c.cookies.clear()
    c.cookies.set(auth.COOKIE, sign_in(c, "ben", "ben-password").cookies[auth.COOKIE])
    assert c.post("/users", data={"username": "eve", "password": "eve-password"}).status_code == 403
    assert c.get("/backup").status_code == 403
    assert "Download a backup" not in c.get("/account").text
    # everyone may change their own password, knowing the current one
    assert "not+right" in c.post("/account/password", data={"current": "nope", "new": "new-password"}).headers["location"]
    c.post("/account/password", data={"current": "ben-password", "new": "new-password"})
    c.cookies.clear()
    assert auth.COOKIE in sign_in(c, "ben", "new-password").cookies


def test_admin_resets_passwords_and_removes_people_but_not_themselves(make):
    c = make(CP_ADMIN_USER="anna", CP_ADMIN_PASSWORD="first-password")
    c.cookies.set(auth.COOKIE, sign_in(c, "anna", "first-password").cookies[auth.COOKIE])
    c.post("/users", data={"username": "ben", "password": "ben-password"})
    with c.db.session() as s:
        ben = s.query(m.User).filter_by(username="ben").one().id
        anna = s.query(m.User).filter_by(username="anna").one().id
    c.post(f"/users/{ben}/password", data={"password": "reset-password"})
    assert "cannot+remove" in c.post(f"/users/{anna}/delete").headers["location"]
    c.post(f"/users/{ben}/delete")
    with c.db.session() as s:
        assert [u.username for u in s.query(m.User)] == ["anna"]


def test_once_an_account_exists_login_is_required_even_without_the_setting(make):
    c = make()
    with c.db.session() as s:
        auth.add_user(s, "solo", "solo-password", is_admin=True)
        s.commit()
    assert c.get("/").status_code == 303


def test_next_cannot_send_people_to_another_site(make):
    c = make(CP_ADMIN_USER="anna", CP_ADMIN_PASSWORD="first-password")
    r = c.post("/login", data={"username": "anna", "password": "first-password", "next": "//evil.example/x"})
    assert r.headers["location"] == "/"
    r = c.post("/login", data={"username": "anna", "password": "first-password", "next": "https://evil.example"})
    assert r.headers["location"] == "/"


def test_a_form_sent_after_the_session_ended_goes_back_to_sign_in(make):
    c = make(CP_REQUIRE_LOGIN="1")
    r = c.post("/datasets/new", data={"name": "x"})
    assert r.status_code == 303 and r.headers["location"].startswith("/login")


def test_adduser_command(tmp_path, monkeypatch):
    from app.__main__ import main
    monkeypatch.delenv("CP_REQUIRE_LOGIN", raising=False)
    db = tmp_path / "cli.db"
    assert main(["--db", str(db), "adduser", "zola", "--admin", "--password", "zola-password"]) == 0
    with pytest.raises(SystemExit, match="at least 8"):
        main(["--db", str(db), "adduser", "yan", "--password", "short"])
    row = sqlite3.connect(db).execute("select username, is_admin, password_hash from app_user").fetchall()
    assert row[0][:2] == ("zola", 1) and row[0][2].startswith("scrypt$")


def test_restore_command_puts_a_backup_back_and_keeps_the_replaced_data(tmp_path, monkeypatch, capsys):
    from app.__main__ import main
    monkeypatch.delenv("CP_REQUIRE_LOGIN", raising=False)
    db = tmp_path / "data" / "live.db"
    main(["--db", str(db), "adduser", "first", "--password", "first-password"])
    main(["--db", str(db), "backup", "--to", str(tmp_path / "copies")])
    saved = next((tmp_path / "copies").glob("live-*.db"))
    main(["--db", str(db), "adduser", "second", "--password", "second-password"])
    assert main(["--db", str(db), "restore", str(saved)]) == 0
    names = lambda f: [r[0] for r in sqlite3.connect(f).execute("select username from app_user order by id")]
    assert names(db) == ["first"]
    kept = next((db.parent / "backups").glob("live-*.db"))
    assert names(kept) == ["first", "second"]
    (tmp_path / "junk.db").write_text("not a database at all" * 50)
    with pytest.raises(SystemExit, match="not a database"):
        main(["--db", str(db), "restore", str(tmp_path / "junk.db")])
    with pytest.raises(SystemExit, match="No backup"):
        main(["--db", str(db), "restore", str(tmp_path / "missing.db")])
