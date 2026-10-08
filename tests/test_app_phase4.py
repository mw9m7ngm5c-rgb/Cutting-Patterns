"""Phase 4 through the app: settings, scenario comparison, live and chipper-profiler patterns, grades."""
import json
import pathlib

import pytest
from fastapi.testclient import TestClient

from app import models as m
from app import reports, snapshot, store
from app.main import create_app

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def client(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'p4.db'}", run_in_thread=False, parallel=False)
    with app.state.db.session() as s:
        ds = store.import_simsaw(s, FIXTURES / "ngomi_1", "Ngomi")
        s.commit()
        line = s.query(m.ProductionLine).filter_by(dataset_id=ds.id).one().id
    c = TestClient(app)
    c.ds, c.line, c.db = ds.id, line, app.state.db
    return c


SETTINGS_FORM = {"nominal_diameter": "0", "nominal_length_incr_m": "0.3", "nominal_taper_mm_per_m": "10",
                 "disc_separation_cm": "5", "points_per_disc": "64", "seed": "1", "use_nominal_diameter": "on",
                 "use_nominal_length": "on", "use_nominal_taper": "on"}


def test_settings_switch_real_log_variation_and_arris(client):
    client.post(f"/d/{client.ds}/settings", data={**SETTINGS_FORM, "real_logs": "on", "diameter_variation": "3",
                                                  "taper_variation": "2", "sweep_variation": "5", "ovality_variation": "4"})
    with client.db.session() as s:
        e = store.engine_dataset(s, client.ds)
    assert e.settings.variation is not None and e.settings.variation.sweep_mm == 5
    assert e.settings.arris_small_end is False                 # box left unticked
    client.post(f"/d/{client.ds}/settings", data={**SETTINGS_FORM, "arris_small_end": "on"})
    with client.db.session() as s:
        e = store.engine_dataset(s, client.ds)
    assert e.settings.variation is None and e.settings.arris_small_end is True
    assert client.get(f"/d/{client.ds}/settings").status_code == 200


def test_scenario_compare_two_machine_settings(client):
    r = client.post(f"/d/{client.ds}/machines/{client.line}/duplicate", follow_redirects=False)
    copy_id = int(r.headers["location"].split("line=")[1].split("&")[0])
    client.post(f"/d/{client.ds}/machines/{copy_id}", data={"tab": "secondary", "secondary_kerf": "5",
                                                            "secondary_outside_kerf": "", "secondary_outside_blades": "0",
                                                            "cant_guiding": "0", "max_sweep": "999",
                                                            "cant_misalignment_mm": "0", "secondary_offset_mm": "0"})
    with client.db.session() as s:
        assert s.query(m.SawPattern).filter_by(line_id=copy_id).count() == 0     # settings only, no patterns
    r = client.post(f"/d/{client.ds}/runs/compare", data={"patterns_line_id": client.line, "machine_a": client.line,
                                                          "machine_b": copy_id}, follow_redirects=False)
    loc = r.headers["location"]
    page = client.get(loc).text
    assert "Machine settings that differ" in page and "Secondary kerf (mm)" in page
    with client.db.session() as s:
        ra, rb = s.query(m.Run).filter(m.Run.name.like("%patterns on%")).order_by(m.Run.id).all()
        pa, pb = reports.run_patterns(s, ra.id), reports.run_patterns(s, rb.id)
    assert [p.rp.primary for p in pa] == [p.rp.primary for p in pb]
    assert all(b.dry_recovery < a.dry_recovery for a, b in zip(pa, pb))           # wider kerf, less timber
    assert "54.1 %" in page


def test_compare_any_two_runs_including_simsaws(client):
    client.post(f"/d/{client.ds}/runs", data={"name": "Ours"})
    with client.db.session() as s:
        ids = [r.id for r in s.query(m.Run).order_by(m.Run.id)]
    page = client.get(f"/d/{client.ds}/compare", params={"a": ids[0], "b": ids[1]}).text
    assert page.count("<tr") >= 5 and "None: the difference comes from the inputs" in page
    assert client.get(f"/d/{client.ds}/compare").status_code == 200


def test_saw_on_another_line(client):
    with client.db.session() as s:
        ln = s.get(m.ProductionLine, client.line)
        other = m.ProductionLine(dataset_id=client.ds, no=2, name="Wide kerf", primary_kerf=6, secondary_kerf=6,
                                 edger_blades=2)
        s.add(other)
        s.commit()
        oid = other.id
    client.post(f"/d/{client.ds}/runs", data={"name": "On wide kerf", "saw_on": oid})
    with client.db.session() as s:
        run = s.query(m.Run).filter_by(name="On wide kerf").one()
        snap = snapshot.loads(run.snapshot)
        assert {p.line_name for p in snap.patterns} == {"Wide kerf"}
        assert reports.run_patterns(s, run.id)[0].dry_recovery < 0.54


def test_live_and_profiler_patterns_on_the_pattern_screen(client):
    d = client.get(f"/api/d/{client.ds}/diagram", params={"line_id": client.line, "log_no": 8,
                                                          "primary": "2*19 2*38 2*19", "secondary": ""}).json()
    assert d["problems"] == [] and d["cant"] is None and all(b["board_type"] == 3 for b in d["boards"])
    bad = client.get(f"/api/d/{client.ds}/diagram", params={"line_id": client.line, "log_no": 8,
                                                            "primary": "25x76/114/25x76", "secondary": "3*38"}).json()
    assert "chipper-profiler" in bad["problems"][0]
    with client.db.session() as s:
        s.get(m.ProductionLine, client.line).saw_type = 2
        s.commit()
    ok = client.get(f"/api/d/{client.ds}/diagram", params={"line_id": client.line, "log_no": 8,
                                                           "primary": "25x76/114/25x76", "secondary": "3*38"}).json()
    assert ok["problems"] == [] and any(b["width"] == 76 and not b["edged"] for b in ok["boards"])
    with client.db.session() as s:
        cls = s.query(m.LogClass).filter_by(dataset_id=client.ds, no=1).one().id
    card = client.get(f"/d/{client.ds}/card", params={"line_id": client.line, "class_id": cls,
                                                      "primary": "2*19 2*38 2*19", "secondary": ""})
    assert card.status_code == 200 and "Live sawing" in card.text


def test_curve_sawing_shows_where_the_cuts_sit(client):
    with client.db.session() as s:
        s.get(m.ProductionLine, client.line).cant_guiding = 1
        s.commit()
    d = client.get(f"/api/d/{client.ds}/diagram", params={"line_id": client.line, "log_no": 1,
                                                          "primary": "25/114/25", "secondary": "2*19 3*38 3*19"}).json()
    assert d["problems"] == [] and d["secondary_shift"]["middle"] < -10          # log 1 has 31.9 mm of sweep


def test_grades_end_to_end(client):
    url = f"/api/d/{client.ds}/grid/board_grades"
    rows = client.get(url).json()["rows"]
    rows[0]["name"] = "Clear"
    client.post(url, json={"rows": rows + [{"no": 2, "name": "Core"}]})
    go = client.get(f"/api/d/{client.ds}/grid/grade_outputs").json()["rows"]
    for r in go:
        clear = r["board_grade_id"] == rows[0]["id"]
        r.update(p_zero=100 if clear else 0, p_fifty=50, p_ninety_nine=0 if clear else 100, p_hundred=0 if clear else 100)
    assert client.post(f"/api/d/{client.ds}/grid/grade_outputs", json={"rows": go}).status_code == 200
    combos = client.get(f"/api/d/{client.ds}/grid/combinations").json()["rows"]
    for c in combos:
        if c["board_grade_id"] != rows[0]["id"]:
            c["price"], c["price_placeholder"] = 1500, False
    client.post(f"/api/d/{client.ds}/grid/combinations", json={"rows": combos})
    with client.db.session() as s:
        for g in s.query(m.Log).filter_by(dataset_id=client.ds):
            g.defect_core_cm = 8.0
        s.commit()
    client.post(f"/d/{client.ds}/runs", data={"name": "Graded"})
    with client.db.session() as s:
        run = s.query(m.Run).filter_by(name="Graded").one()
        grades = {b.grade for b in s.query(m.RunBoardResult).join(m.RunPattern).filter(m.RunPattern.run_id == run.id)}
        assert grades == {"Clear", "Core"}
        rows_out = reports.board_report(s, run, None, "none")
        assert {r["grade"] for r in rows_out} == {"Clear", "Core"}
    page = client.get(f"/d/{client.ds}/reports", params={"run": run.id, "view": "boards"}).text
    assert "<th class=\"text\">Grade</th>" in page
    assert client.get(f"/d/{client.ds}/reports/{run.id}/excel").status_code == 200


def test_snapshots_from_before_phase_4_still_load(client):
    with client.db.session() as s:
        run = s.query(m.Run).first()
        d = json.loads(run.snapshot)
    d["products"].pop("grade_outputs", None)
    for k in ("arris_small_end", "variation"):
        d["settings"].pop(k, None)
    old = snapshot.from_dict(d)
    assert old.products.grade_outputs == {} and old.settings.variation is None
