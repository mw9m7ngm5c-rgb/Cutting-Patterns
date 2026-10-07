# Sawing pattern simulator and generator

Thorpe Timbers (Ngome). Tells the mill which cutting pattern to run for each log diameter class, and what recovery and product mix to expect.

Status: **Phase 3 of 4 complete** (simulation engine, command line, web app, pattern generator). Phase 4 adds curve sawing, misalignment, the three-blade edger, grades, live sawing and chipper-profiler lines.

## Run it

macOS / Linux:

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m app                       # opens http://127.0.0.1:8000
```

Windows: the same with `.venv\Scripts\pip` and `.venv\Scripts\python`.

Import a Simsaw dataset from the Datasets page, or from the command line:

```
.venv/bin/python -m app import "reference/ngomi 1.mdb" --name "Ngomi"
```

The database is `data/cutting_patterns.db`; `--db other.db` or the `CP_DB` variable uses another file.

Tests and the engine command line:

```
.venv/bin/python -m pytest                         # 209 tests
.venv/bin/python cli.py validate --dataset tests/fixtures/ngomi_1 --run Test1
.venv/bin/python cli.py simulate --dataset tests/fixtures/ngomi_1 --pattern "25/114/25" "2*19 3*38 3*19" --class 1 --mix --volumes
```

## Layout

- `engine/`: the simulation. Standalone: no web, no database, no file access.
- `app/`: the web app (FastAPI, SQLite, server-rendered pages, vanilla JS, SVG diagrams). Calls the engine.
- `importers/`: reads Simsaw 6 `.mdb` datasets and runs.
- `cli.py`: `simulate` and `validate`.
- `tests/`: unit tests, acceptance tests against a real Simsaw run (`tests/fixtures/ngomi_1`), app tests.
- `docs/SPEC.md`: rules, data model, screens, validation, results per phase.
- `docs/ASSUMPTIONS.md`: every rule that was inferred rather than read, with its evidence.
- `tools/`: scripts behind the evidence in ASSUMPTIONS.
- `reference/`: read-only Simsaw source material. Not committed.
