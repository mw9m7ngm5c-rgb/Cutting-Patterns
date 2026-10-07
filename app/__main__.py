"""Start the app:  python -m app            (opens the browser at http://127.0.0.1:8000)

    python -m app --port 8001 --no-browser
    python -m app import "reference/ngomi 1.mdb" --name "Ngomi"     import a Simsaw dataset and exit
    python -m app --db path/to/file.db                              use another database file
"""
from __future__ import annotations

import argparse
import threading
import webbrowser


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
    a = ap.parse_args(argv)

    from .db import Database, db_url, migrate
    url = db_url(a.db)

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
    print(f"Sawing patterns: http://{a.host}:{a.port}/   (database {url[len('sqlite:///'):]}; Ctrl+C to stop)")
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
