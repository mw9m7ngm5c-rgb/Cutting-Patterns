# Sawing pattern simulator and generator

Thorpe Timbers (Ngome). Status: Phase 0 (plan) complete, no application code yet.

- `docs/SPEC.md`: simulation rules, data model, screens, validation plan.
- `docs/ASSUMPTIONS.md`: every inferred rule and its evidence.
- `importers/export_fixtures.py`: exports a Simsaw `.mdb` to JSON (`pip install access-parser`).
- `tests/fixtures/ngomi_1/`: the Ngomi dataset and its Test1 batch run.
- `tools/`: Phase 0 checks against the fixtures (need `numpy`).
- `reference/`: read-only Simsaw source material, not committed.
