"""Generator screens: searches run as jobs, results render, patterns save, classes apply, cards print."""
import json
import pathlib

import pytest
from fastapi.testclient import TestClient

from app import models as m
from app import store
from app.main import create_app

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def client(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'gen.db'}", run_in_thread=False, parallel=False)
    with app.state.db.session() as s:
        ds = store.import_simsaw(s, FIXTURES / "ngomi_1", "Ngomi")
        s.commit()
        line = s.query(m.ProductionLine).filter_by(dataset_id=ds.id).one().id
        classes = {c.no: c.id for c in s.query(m.LogClass).filter_by(dataset_id=ds.id)}
    c = TestClient(app)
    c.ds, c.line, c.classes, c.db = ds.id, line, classes, app.state.db
    return c


BASE = {"objective": "volume", "symmetric": "on", "thicker_to_centre": "on", "max_sideboards": "2",
        "max_thicknesses": "3", "min_share": "0"}


def start(client, **form):
    r = client.post(f"/d/{client.ds}/generator", data={**BASE, "line_id": client.line, **form}, follow_redirects=False)
    assert r.status_code == 303, r.text
    loc = r.headers["location"]
    return int(loc.rsplit("/", 1)[1]) if "/generator/" in loc else loc


def job(client, jid):
    with client.db.session() as s:
        return s.get(m.GeneratorJob, jid)


def test_class_search_ranks_saves_and_prints(client):
    jid = start(client, kind="class", mode="class", class_id=client.classes[2], simulate="15")
    j = job(client, jid)
    assert j.status == "done", j.message
    res = json.loads(j.result)
    assert len(res["ranked"]) == 10 and res["meta"]["logs"] == 34
    rec = [r["dry_recovery"] for r in res["ranked"]]
    assert rec[0] >= 0.5623 - 1e-9                       # at least Simsaw's own class 2 pattern
    page = client.get(f"/d/{client.ds}/generator/{jid}").text
    assert page.count('class="panel result-card"') == 10 and "<svg" in page
    best = res["ranked"][0]
    client.post(f"/d/{client.ds}/generator/{jid}/save",
                data={"primary": best["primary"], "secondary": best["secondary"], "class_id": client.classes[2]})
    with client.db.session() as s:
        saved = s.query(m.SawPattern).filter_by(dataset_id=client.ds, source="generated").one()
        assert (saved.primary, saved.secondary, saved.pattern_no) == (best["primary"], best["secondary"], 2)
    card = client.get(f"/d/{client.ds}/card", params={"pattern_id": saved.id})
    assert card.status_code == 200 and "Saw setting card" in card.text and "Blade" in card.text
    assert "34 logs of the class" in card.text


def test_single_diameter_search_and_constraints(client):
    jid = start(client, kind="class", mode="diameter", diameter_cm="24", simulate="10",
                must_include="50x152", exclude=["19x76", "19x102", "19x114", "19x152"])
    res = json.loads(job(client, jid).result)
    assert res["ranked"] and res["meta"]["logs"] == 3
    for r in res["ranked"]:
        sizes = {(x["thickness"], x["width"]) for x in r["mix"]}
        assert (50, 152) in sizes and not any(t == 19 for t, _ in sizes)
        assert "19" not in (r["primary"] + " " + r["secondary"]).split("/")[0].split()
    assert client.get(f"/d/{client.ds}/generator/{jid}").status_code == 200


def test_chart_suggests_classes_both_ways_and_applies_them(client):
    jid = start(client, kind="chart", from_cm="22", to_cm="25", simulate="6")
    j = job(client, jid)
    assert j.status == "done", j.message
    steps = json.loads(j.result)["steps"]
    assert [st["sed"] for st in steps] == [22, 23, 24, 25]
    page = client.get(f"/d/{client.ds}/generator/{jid}", params={"group": "n", "n": 2}).text
    assert "Suggested log classes" in page and page.count("<code>") >= 4
    assert client.get(f"/d/{client.ds}/generator/{jid}", params={"group": "tol", "tol": 0.5}).status_code == 200
    client.post(f"/d/{client.ds}/generator/{jid}/apply", data={"group": "n", "value": "2"})
    with client.db.session() as s:
        cls = s.query(m.LogClass).filter_by(dataset_id=client.ds).order_by(m.LogClass.no).all()
        assert len(cls) == 2 and cls[0].min_diameter_cm == 22 and cls[-1].max_diameter_cm == 25.9
        assert all(c.log_price == 120 and c.max_sweep == 40 for c in cls)
        pats = s.query(m.SawPattern).filter_by(dataset_id=client.ds).all()
        assert len(pats) == 2 and all(p.source == "generated" for p in pats)


def test_bad_form_is_explained_not_fatal(client):
    loc = start(client, kind="chart", from_cm="30", to_cm="20")
    assert isinstance(loc, str) and "msg=" in loc
    loc = start(client, kind="class", mode="diameter", diameter_cm="abc")
    assert isinstance(loc, str) and "msg=" in loc
    jid = start(client, kind="class", mode="class", class_id=client.classes[2], objective="target")
    j = job(client, jid)
    assert j.status == "failed" and "target product" in j.message
    assert "target product" in client.get(f"/d/{client.ds}/generator/{jid}").text


def test_generator_pages_and_copies(client):
    for tab in ("class", "chart", "history"):
        assert client.get(f"/d/{client.ds}/generator", params={"tab": tab}).status_code == 200
    jid = start(client, kind="class", mode="diameter", diameter_cm="20", simulate="5")
    with client.db.session() as s:
        copy = store.duplicate_dataset(s, client.ds, "Copy")
        s.commit()
        assert s.query(m.GeneratorJob).filter_by(dataset_id=copy.id).count() == 1
    client.post(f"/d/{client.ds}/generator/{jid}/delete")
    assert job(client, jid) is None
