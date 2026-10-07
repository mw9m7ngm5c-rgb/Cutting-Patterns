"""Export every user table of a Simsaw 6 .mdb to JSON fixtures.

Usage: python importers/export_fixtures.py "reference/ngomi 1.mdb" tests/fixtures/ngomi_1
Each table becomes <out>/<table>.json as a list of row dicts, plus _manifest.json.
Read-only on the source file.
"""
import datetime
import decimal
import json
import pathlib
import sys

from access_parser import AccessParser


def _clean(v):
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, bytes):
        return v.hex()
    return v


def export(mdb_path: str, out_dir: str) -> dict:
    db = AccessParser(mdb_path)
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"source": pathlib.Path(mdb_path).name, "tables": {}}
    for name in sorted(db.catalog):
        if name.startswith("MSys"):
            continue
        cols = db.parse_table(name)
        keys = list(cols.keys())
        n = len(cols[keys[0]]) if keys else 0
        rows = [{k: _clean(cols[k][i]) for k in keys} for i in range(n)]
        (out / f"{name}.json").write_text(json.dumps(rows, indent=1))
        manifest["tables"][name] = {"rows": n, "columns": keys}
    (out / "_manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


if __name__ == "__main__":
    m = export(sys.argv[1], sys.argv[2])
    for t, info in m["tables"].items():
        print(f"{t:28s} {info['rows']:5d}")
