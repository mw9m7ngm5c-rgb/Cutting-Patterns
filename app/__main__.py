"""Start the app:  python -m app            (opens the browser at http://127.0.0.1:8000)

    python -m app --port 8001 --no-browser
    python -m app import "reference/ngomi 1.mdb" --name "Ngomi"     import a Simsaw dataset and exit
    python -m app --db path/to/file.db                              use another database file
    python -m app --host 0.0.0.0 --no-browser                       let other computers on the network in
    python -m app backup --to backups --keep 30                     copy the database safely, keep the newest 30
    python -m app migrate                                           create or update the database and exit
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import sqlite3
import threading
import webbrowser


def backup(db_file: pathlib.Path, to_dir: pathlib.Path, keep: int) -> pathlib.Path:
    """Copy the database with SQLite's own backup, which is safe while the app is running, then
    delete all but the newest `keep` copies in that folder."""
    if not db_file.exists():
        raise SystemExit(f"No database at {db_file}")
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app", description="Sawing pattern simulator")
    ap.add_argument("--db", help="SQLite database file (default data/cutting_patterns.db, or $CP_DB)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    imp = sub.add_parser("import", help="import a Simsaw .mdb file (or a directory of exported tables)")
    imp.add_argument("path")
    imp.add_argument("--name")
    bk = sub.add_parser("backup", help="copy the database safely, even while the app is running")
    bk.add_argument("--to", default=None, help="folder for the copies (default: backups/ next to data/)")
    bk.add_argument("--keep", type=int, default=30, help="how many copies to keep (default 30; 0 keeps all)")
    sub.add_parser("migrate", help="create or update the database, then exit")
    a = ap.parse_args(argv)

    from .db import Database, db_url, migrate
    url = db_url(a.db)

    if a.cmd == "migrate":
        migrate(url)
        print(f"Database ready: {url[len('sqlite:///'):]}")
        return 0

    if a.cmd == "backup":
        db_file = pathlib.Path(url[len("sqlite:///"):])
        to = pathlib.Path(a.to) if a.to else db_file.parent.parent / "backups"
        print(f"Backed up to {backup(db_file, to, a.keep)}")
        return 0

    if a.cmd == "import":
        from . import store
        migrate(url)
        db = Database(url)
        with db.session() as s:
            ds = store.import_simsaw(s, a.path, a.name)
            s.commit()
            print(f"Imported {a.path} as dataset {ds.id}: {ds.name}")
        return 0

    import uvicorn
    from .main import create_app
    app = create_app(url)
    if not a.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(f"http://{a.host}:{a.port}/")).start()
    shown = "127.0.0.1" if a.host in ("0.0.0.0", "::") else a.host
    print(f"Sawing patterns: http://{shown}:{a.port}/   (database {url[len('sqlite:///'):]}; Ctrl+C to stop)")
    if shown != a.host:
        print(f"Other computers on the network: http://<this computer's address>:{a.port}/")
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
