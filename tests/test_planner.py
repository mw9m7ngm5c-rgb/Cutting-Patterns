"""The planner: a saw line, the sizes cut and the log classes on one screen; one button gives the best
pattern per class, drawn, with a full report."""
import re

import pytest
from fastapi.testclient import TestClient

from app import models as m
from app import planner, store
from app.main import create_app

FORM = {"line_name": "Main", "saw_type": "0", "primary_kerf": "4", "secondary_kerf": "3.5", "edger_blades": "2",
        "edger_kerf": "5", "edger_spacing": "",
        "th_dry": ["25", "38", "50"], "th_wet": ["27", "41", "54"],
        "wd_dry": ["76", "114", "152"], "wd_wet": ["81", "120", "160"],
        "cut": ["25x76", "25x114", "25x152", "38x152", "50x152"],
        "cl_from": ["20", "26"], "cl_to": ["25.9", "31.9"], "cl_length": ["4.8", "4.2"], "cl_taper": ["8", "9"]}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("CP_REQUIRE_LOGIN", raising=False)
    app = create_app(f"sqlite:///{tmp_path / 'plan.db'}", run_in_thread=False, parallel=False)
    c = TestClient(app)
    c.db = app.state.db
    r = c.post("/datasets/new", data={"name": "Our mill"}, follow_redirects=False)
    assert r.headers["location"].endswith("/plan")              # a new project opens in the planner
    c.ds = int(r.headers["location"].split("/")[2])
    return c


def problems(page: str) -> list[str]:
    return re.findall(r"<li>(.*?)</li>", page)


def test_a_new_project_starts_blank_in_the_planner(client):
    page = client.get(f"/d/{client.ds}/plan").text
    assert "Your saw line" in page and "The sizes you cut" in page and "Your log classes" in page
    assert 'name="primary_kerf" value=""' in page                  # nothing invented for the machine
    assert "Placeholder values" not in page


def test_saving_writes_the_line_sizes_and_classes(client):
    r = client.post(f"/d/{client.ds}/plan", data={**FORM, "action": "save"}, follow_redirects=False)
    assert r.status_code == 303
    with client.db.session() as s:
        plan = planner.load(s, client.ds)
        assert plan.ready
        assert (plan.line.primary_kerf, plan.line.secondary_kerf, plan.line.edger_blades) == (4, 3.5, 2)
        assert plan.thicknesses == [(25, 27), (38, 41), (50, 54)]
        assert plan.cut == {(25, 76), (25, 114), (25, 152), (38, 152), (50, 152)}
        assert [(c.min_cm, c.max_cm, c.length_m, c.taper) for c in plan.classes] == [(20, 25.9, 4.8, 8), (26, 31.9, 4.2, 9)]
        assert store.settings_for(s, client.ds).use_nominal_taper is False      # each class's taper counts
    # a size dropped from the list goes, with its products; a class dropped goes too
    client.post(f"/d/{client.ds}/plan", data={**FORM, "th_dry": ["25", "50"], "th_wet": ["27", "54"],
                                              "cl_from": ["20"], "cl_to": ["25.9"], "cl_length": ["4.8"],
                                              "cl_taper": ["8"], "action": "save"})
    with client.db.session() as s:
        plan = planner.load(s, client.ds)
        assert [t for t, _ in plan.thicknesses] == [25, 50] and (38, 152) not in plan.cut and len(plan.classes) == 1


def test_mistakes_are_explained_and_the_typing_is_kept(client):
    bad = {**FORM, "primary_kerf": "", "th_wet": ["24", "41", "54"], "cl_from": ["20", "25"],
           "edger_spacing": "100 200", "action": "calculate"}
    page = client.post(f"/d/{client.ds}/plan", data=bad).text
    found = " ".join(problems(page))
    assert "Headrig kerf" in found and "green (sawn) size" in found and "overlap" in found and "2 blades have 1 gap" in found
    assert 'value="31.9"' in page and 'value="4.2"' in page                  # nothing typed is lost
    with client.db.session() as s:
        assert s.query(m.ProductionLine).filter_by(dataset_id=client.ds).count() == 0     # nothing saved


def test_one_button_gives_drawings_and_a_full_report(client):
    r = client.post(f"/d/{client.ds}/plan", data={**FORM, "action": "calculate"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("#results")
    with client.db.session() as s:
        job = s.query(m.GeneratorJob).filter_by(dataset_id=client.ds, kind="plan").one()
        assert job.status == "done", job.message
        samples = s.query(m.Log).filter_by(dataset_id=client.ds, sample=True).all()
        assert len(samples) == 26 and {g.length_m for g in samples} == {4.8, 4.2}     # every 0.5 cm in each class
        pats = s.query(m.SawPattern).filter_by(dataset_id=client.ds).all()
        assert len(pats) == 2                                                         # the best of each class kept
        run = s.query(m.Run).filter_by(dataset_id=client.ds).one()
        assert run.status == "done"
    page = client.get(f"/d/{client.ds}/plan").text
    assert page.count("<svg") == 2 and "Best pattern for each class" in page and "Full report" in page
    recoveries = [float(x) for x in re.findall(r'big-figure">([\d.]+) %', page)]
    assert len(recoveries) == 2 and all(40 < v < 75 for v in recoveries)
    report = client.get(f"/d/{client.ds}/plan/report").text
    assert report.count("<svg") == 2 and "Saw settings" in report and "Where the log goes" in report
    assert "All classes" in report and "25 × 152" in report
    assert client.get(f"/d/{client.ds}/reports/{run.id}/excel").status_code == 200

    # again: sample logs are remade, not added to; patterns replaced, not piled up
    client.post(f"/d/{client.ds}/plan", data={**FORM, "action": "calculate"})
    with client.db.session() as s:
        assert s.query(m.Log).filter_by(dataset_id=client.ds, sample=True).count() == 26
        assert s.query(m.SawPattern).filter_by(dataset_id=client.ds).count() == 2


def test_measured_logs_are_used_instead_of_samples(client):
    client.post(f"/d/{client.ds}/plan", data={**FORM, "action": "save"})
    with client.db.session() as s:
        s.add_all([m.Log(dataset_id=client.ds, log_no=n, sed_cm=sed, length_m=3.6, taper=7, sweep_mm=10, ovality=1.0)
                   for n, sed in enumerate([21.0, 22.5, 24.0], 1)])
        s.commit()
        assert planner.load(s, client.ds).classes[0].real_logs == 3
    client.post(f"/d/{client.ds}/plan", data={**FORM, "action": "calculate"})
    with client.db.session() as s:
        e = store.engine_dataset(s, client.ds)
        assert [g.no for g in e.logs_in_class(1)] == [1, 2, 3]                   # class 1: the measured logs only
        assert all(g.no > 3 for g in e.logs_in_class(2))                         # class 2: samples


def test_report_before_any_calculation_points_back(client):
    r = client.get(f"/d/{client.ds}/plan/report", follow_redirects=False)
    assert r.status_code == 303 and "/plan" in r.headers["location"]


def test_example_project_is_ready_to_work_out(client):
    r = client.post("/datasets/new", data={"name": "Try", "start": "example"}, follow_redirects=False)
    ds = int(r.headers["location"].split("/")[2])
    with client.db.session() as s:
        assert planner.load(s, ds).ready
