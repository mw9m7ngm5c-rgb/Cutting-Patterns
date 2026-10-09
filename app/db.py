"""Database connection and migrations. One SQLite file holds every dataset."""
from __future__ import annotations

import datetime as dt
import os
import pathlib
import sqlite3

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "cutting_patterns.db"


def db_url(path: str | os.PathLike | None = None) -> str:
    path = pathlib.Path(path or os.environ.get("CP_DB") or DEFAULT_DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}"


def make_engine(url: str) -> Engine:
    eng = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _pragmas(conn, _):
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")      # batch runs write while pages read
        cur.close()

    return eng


def migrate(url: str) -> None:
    """Bring the database schema up to date (Alembic)."""
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(pathlib.Path(__file__).parent / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")


class Database:
    def __init__(self, url: str):
        self.url = url
        self.engine = make_engine(url)
        self.Session = sessionmaker(self.engine, expire_on_commit=False)

    def session(self) -> Session:
        return self.Session()


def backup_database(db_file: pathlib.Path, to_dir: pathlib.Path, keep: int) -> pathlib.Path:
    """Copy the database with SQLite's own backup, which is safe while the app is running, then
    delete all but the newest `keep` copies in that folder."""
    if not db_file.exists():
        raise FileNotFoundError(f"No database at {db_file}")
    to_dir.mkdir(parents=True, exist_ok=True)
    target = to_dir / f"{db_file.stem}-{dt.datetime.now():%Y-%m-%d-%H%M%S}.db"
    src = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    copies = sorted(to_dir.glob(f"{db_file.stem}-*.db"))
    for old in copies[:-keep] if keep > 0 else []:
        old.unlink()
    return target


def restore_database(backup_file: pathlib.Path, db_file: pathlib.Path) -> pathlib.Path:
    """Replace the database with a backup copy, using SQLite's backup so the running app sees the
    restored data. The current database is backed up first (into backups/ beside it); that copy's
    path is returned."""
    backup_file = pathlib.Path(backup_file)
    if not backup_file.exists():
        raise FileNotFoundError(f"No backup at {backup_file}")
    src = sqlite3.connect(f"file:{backup_file}?mode=ro", uri=True)
    try:
        src.execute("select count(*) from sqlite_master").fetchone()
    except sqlite3.DatabaseError:
        src.close()
        raise ValueError(f"{backup_file} is not a database backup") from None
    before = backup_database(db_file, db_file.parent / "backups", 0) if db_file.exists() else None
    dst = sqlite3.connect(db_file)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    return before
