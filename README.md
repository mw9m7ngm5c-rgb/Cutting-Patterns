# Sawing pattern simulator and generator

Thorpe Timbers (Ngome). Tells the mill which cutting pattern to run for each log diameter class, and what recovery and product mix to expect.

Status: **Phase 1 of 4 complete** (simulation engine and command line). The web app is Phase 2, the pattern generator Phase 3.

## Run it

```
python -m venv .venv
.venv/bin/pip install -r requirements.txt          # Windows: .venv\Scripts\pip
.venv/bin/python -m pytest                         # 150 tests
.venv/bin/python cli.py validate --dataset tests/fixtures/ngomi_1 --run Test1
.venv/bin/python cli.py simulate --dataset tests/fixtures/ngomi_1 --pattern "25/114/25" "2*19 3*38 3*19" --class 1 --mix --volumes
```

`--dataset` also takes a Simsaw `.mdb` file directly.

## Layout

- `engine/`: the simulation. Standalone: no web, no database, no file access.
- `importers/`: reads Simsaw 6 `.mdb` datasets and runs.
- `cli.py`: `simulate` and `validate`.
- `tests/`: unit tests on hand-checkable shapes, and acceptance tests against a real Simsaw run (`tests/fixtures/ngomi_1`).
- `docs/SPEC.md`: rules, data model, screens, validation, results so far.
- `docs/ASSUMPTIONS.md`: every rule that was inferred rather than read, with its evidence.
- `tools/`: scripts behind the evidence in ASSUMPTIONS.
- `reference/`: read-only Simsaw source material. Not committed.
