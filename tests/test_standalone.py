"""A mill sets up its own dataset from nothing (no Simsaw file) and gets the best pattern per class."""
import json
import pathlib

import pytest
from fastapi.testclient import TestClient

from app import models as m
from app import store
from app.main import create_app

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("CP_REQUIRE_LOGIN", raising=False)
    app = create_app(f"sqlite:///{tmp_path / 'own.db'}", run_in_thread=False, parallel=False)
    c = TestClient(app)
    c.db = app.state.db
    return c


def grid(c, ds, name, rows):
    r = c.post(f"/api/d/{ds}/grid/{name}", json={"rows": rows})
    assert r.status_code == 200, r.text


CLASS = {"min_length_m": 1.8, "max_length_m": 6.6, "length_incr_m": 0.3, "min_taper": 0, "max_taper": 25,
         "min_sweep": 0, "max_sweep": 40, "min_ovality": 0.5, "max_ovality": 1.5, "min_defect_core": 0,
         "max_defect_core": 100, "log_price": 650, "grades": []}


def test_start_page_leads_with_a_new_dataset_and_keeps_simsaw_optional(client):
    page = client.get("/").text
    assert page.index("New dataset") < page.index("Simsaw") and "<details" in page and "Empty" in page


def test_an_empty_dataset_set_up_by_hand_gets_the_best_pattern_for_every_class(client):
    r = client.post("/datasets/new", data={"name": "Our mill", "start": "empty"}, follow_redirects=False)
    ds = int(r.headers["location"].rsplit("/", 1)[1])
    with client.db.session() as s:
        assert s.query(m.LogClass).filter_by(dataset_id=ds).count() == 0
        assert s.query(m.ProductionLine).filter_by(dataset_id=ds).count() == 0
        assert s.query(m.Thickness).filter_by(dataset_id=ds).count() == 0
    home = client.get(f"/d/{ds}").text
    assert "Log classes" in home and "none yet" in home

    grid(client, ds, "thicknesses", [{"dry": 25, "wet": 27}, {"dry": 38, "wet": 41}])
    grid(client, ds, "widths", [{"dry": 76, "wet": 81}, {"dry": 114, "wet": 120}, {"dry": 152, "wet": 160}])
    grid(client, ds, "log_classes", [{**CLASS, "no": 1, "min_diameter_cm": 22, "max_diameter_cm": 25.9},
                                     {**CLASS, "no": 2, "min_diameter_cm": 26, "max_diameter_cm": 29.9}])
    r = client.post(f"/d/{ds}/machines/new", data={"name": "Twin saw"}, follow_redirects=False)
    with client.db.session() as s:
        line = s.query(m.ProductionLine).filter_by(dataset_id=ds).one().id

    assert "Every log class" in client.get(f"/d/{ds}/generator").text           # the first tab
    r = client.post(f"/d/{ds}/generator", data={"kind": "classes", "line_id": line, "objective": "volume",
                                                "simulate": "12", "max_sideboards": "1", "symmetric": "on",
                                                "thicker_to_centre": "on"}, follow_redirects=False)
    jid = int(r.headers["location"].rsplit("/", 1)[1])
    with client.db.session() as s:
        job = s.get(m.GeneratorJob, jid)
        assert job.status == "done", job.message
        rows = json.loads(job.result)["classes"]
    assert [row["no"] for row in rows] == [1, 2] and all(row["ideal"] for row in rows)    # no logs typed in
    assert all(row["ranked"] and 0.3 < row["ranked"][0]["dry_recovery"] < 0.8 for row in rows)
    page = client.get(f"/d/{ds}/generator/{jid}").text
    assert "Dry recovery" in page and "ideal logs" in page and "Save the best pattern of every class" in page

    client.post(f"/d/{ds}/generator/{jid}/save-all", data={"replace": "on"})
    client.post(f"/d/{ds}/generator/{jid}/save-all", data={"replace": "on"})        # twice: still one each
    with client.db.session() as s:
        pats = s.query(m.SawPattern).filter_by(dataset_id=ds).all()
        assert len(pats) == 2 and {p.source for p in pats} == {"generated"}
    assert "2 of 2 classes have a pattern" in client.get(f"/d/{ds}").text


def test_classes_with_logs_are_searched_on_their_own_logs(client):
    with client.db.session() as s:
        ds = store.import_simsaw(s, FIXTURES / "ngomi_1", "Mill", include_runs=False).id
        s.commit()
        line = s.query(m.ProductionLine).filter_by(dataset_id=ds).first().id
        n_classes = s.query(m.LogClass).filter_by(dataset_id=ds).count()
    r = client.post(f"/d/{ds}/generator", data={"kind": "classes", "line_id": line, "objective": "volume",
                                                "simulate": "12", "symmetric": "on", "thicker_to_centre": "on"},
                    follow_redirects=False)
    jid = int(r.headers["location"].rsplit("/", 1)[1])
    with client.db.session() as s:
        job = s.get(m.GeneratorJob, jid)
        assert job.status == "done", job.message
        rows = json.loads(job.result)["classes"]
    assert len(rows) == n_classes and not any(row["ideal"] for row in rows if row["logs"] > 3)
    client.post(f"/d/{ds}/generator/{jid}/save-all", data={})                       # add, keep the old patterns
    with client.db.session() as s:
        assert s.query(m.SawPattern).filter_by(dataset_id=ds, source="generated").count() == sum(bool(r["ranked"]) for r in rows)


def test_all_classes_needs_classes(client):
    r = client.post("/datasets/new", data={"name": "Bare", "start": "empty"}, follow_redirects=False)
    ds = int(r.headers["location"].rsplit("/", 1)[1])
    client.post(f"/d/{ds}/machines/new", data={"name": "L"})
    with client.db.session() as s:
        line = s.query(m.ProductionLine).filter_by(dataset_id=ds).one().id
    r = client.post(f"/d/{ds}/generator", data={"kind": "classes", "line_id": line}, follow_redirects=False)
    assert "log+classes" in r.headers["location"]
