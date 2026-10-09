"""Start the app:  python -m app            (opens the browser at http://127.0.0.1:8000)

    python -m app --port 8001 --no-browser
    python -m app import "reference/ngomi 1.mdb" --name "Ngomi"     import a Simsaw dataset and exit
    python -m app --db path/to/file.db                              use another database file
    python -m app --host 0.0.0.0 --no-browser                       let other computers on the network in
    python -m app backup --to backups --keep 30                     copy the database safely, keep the newest 30
    python -m app restore backups/cutting_patterns-2026-01-31-180000.db  put a backup back (the current data is kept aside)
    python -m app migrate                                           create or update the database and exit
    python -m app adduser anna --admin                              add someone who may sign in (asks for a password)

Settings a server can give instead (used by the Docker image):
    PORT, CP_HOST            where to listen        CP_DB              database file
    CP_REQUIRE_LOGIN=1       always ask for a login CP_SECRET_KEY      key that signs the login cookie
    CP_ADMIN_USER / CP_ADMIN_PASSWORD   first administrator, created on start if missing
    CP_BEHIND_PROXY=1        trust the hosting proxy's https and client-address headers
"""
from __future__ import annotations

import argparse
import getpass
import os
import pathlib
import threading
import webbrowser


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app", description="Sawing pattern simulator")
    ap.add_argument("--db", help="SQLite database file (default data/cutting_patterns.db, or $CP_DB)")
    ap.add_argument("--host", default=os.environ.get("CP_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    ap.add_argument("--no-browser", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    imp = sub.add_parser("import", help="import a Simsaw .mdb file (or a directory of exported tables)")
    imp.add_argument("path")
    imp.add_argument("--name")
    bk = sub.add_parser("backup", help="copy the database safely, even while the app is running")
    bk.add_argument("--to", default=None, help="folder for the copies (default: backups/ next to data/)")
    bk.add_argument("--keep", type=int, default=30, help="how many copies to keep (default 30; 0 keeps all)")
    rs = sub.add_parser("restore", help="replace the database with a backup copy (the current one is backed up first)")
    rs.add_argument("file")
    sub.add_parser("migrate", help="create or update the database, then exit")
    au = sub.add_parser("adduser", help="add someone who may sign in")
    au.add_argument("username")
    au.add_argument("--admin", action="store_true", help="may add people and download backups")
    au.add_argument("--password", help="(asked for if left out)")
    a = ap.parse_args(argv)

    from .db import Database, backup_database, db_url, migrate, restore_database
    url = db_url(a.db)

    if a.cmd == "migrate":
        migrate(url)
        print(f"Database ready: {url[len('sqlite:///'):]}")
        return 0

    if a.cmd == "adduser":
        from . import auth
        migrate(url)
        password = a.password or getpass.getpass(f"Password for {a.username} (8+ characters): ")
        with Database(url).session() as s:
            try:
                auth.add_user(s, a.username, password, a.admin)
            except ValueError as e:
                raise SystemExit(str(e)) from None
            s.commit()
        print(f"{a.username} can now sign in{' as an administrator' if a.admin else ''}. "
              "The app now asks everyone to sign in.")
        return 0

    if a.cmd == "backup":
        db_file = pathlib.Path(url[len("sqlite:///"):])
        to = pathlib.Path(a.to) if a.to else db_file.parent.parent / "backups"
        try:
            print(f"Backed up to {backup_database(db_file, to, a.keep)}")
        except FileNotFoundError as e:
            raise SystemExit(str(e)) from None
        return 0

    if a.cmd == "restore":
        db_file = pathlib.Path(url[len("sqlite:///"):])
        try:
            before = restore_database(pathlib.Path(a.file), db_file)
        except (FileNotFoundError, ValueError) as e:
            raise SystemExit(str(e)) from None
        migrate(url)
        print(f"Restored {a.file}." + (f" The data it replaced is in {before}." if before else ""))
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
    behind_proxy = os.environ.get("CP_BEHIND_PROXY", "").strip().lower() in ("1", "true", "yes", "on")
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning",
                proxy_headers=behind_proxy, forwarded_allow_ips="*" if behind_proxy else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
