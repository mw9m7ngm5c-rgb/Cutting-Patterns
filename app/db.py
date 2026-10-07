"""Database connection and migrations. One SQLite file holds every dataset."""
from __future__ import annotations

import os
import pathlib

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
