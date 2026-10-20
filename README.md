# Sawing pattern simulator and generator

Thorpe Timbers (Ngome). Tells the mill which cutting pattern to run for each log diameter class, and what recovery and product mix to expect.

Stand-alone: runs in any browser (Windows, Mac, tablet) from a cloud server or an office computer, and needs no other
software. You enter your own log classes and logs, board sizes and prices, and saw lines; the generator then finds
the best pattern and recovery for every log class in one go (Generator → Every log class). Importing an old Simsaw 6
file is possible but optional.

Status: **all four phases complete**: simulation engine and command line, web app, pattern generator, and advanced sawing (curve sawing, misalignment and offsets, arris alignment, three-blade edger, grades, real-log variation, live sawing, chipper-profiler lines, scenario comparison).

## Run it

macOS / Linux:

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m app                       # opens http://127.0.0.1:8000
```

Windows: the same with `.venv\Scripts\pip` and `.venv\Scripts\python`.

Start a dataset on the Datasets page, empty or from example values, and follow the steps on its first page.
An old Simsaw file can be imported there too (optional), or from the command line:
`.venv/bin/python -m app import "file.mdb" --name "Name"`.

The database is `data/cutting_patterns.db`; `--db other.db` or the `CP_DB` variable uses another file.

To run it for the whole office on a Mac (in the background, started at login, backed up every evening),
follow [docs/DEPLOY_MACOS.md](docs/DEPLOY_MACOS.md): in short `./deploy/macos/install.sh` then
`./deploy/macos/start-at-login.sh --shared`.

To run it on a cloud server, so you and colleagues can use it from any browser with a user name and
password, follow [docs/DEPLOY_CLOUD.md](docs/DEPLOY_CLOUD.md) (Render, using `render.yaml` and the `Dockerfile`).

Back up the database at any time (safe while the app runs): `.venv/bin/python -m app backup`.

Tests and the engine command line:

```
.venv/bin/python -m pytest                         # 256 tests
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
- `deploy/macos/`: install, start-at-login, update, backup and stop scripts for a Mac.
- `Dockerfile`, `render.yaml`: the cloud set-up.
- `reference/`: read-only Simsaw source material. Not committed.
