"""Every page reachable by a link opens, on a project the planner has worked out and on an imported one.
Catches screens that cannot show a kind of record another screen made (a server error to the user)."""
import pathlib
import re
from urllib.parse import urldefrag

import pytest
from fastapi.testclient import TestClient

from app import models as m
from app import store
from app.main import create_app
from tests.test_planner import FORM

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("CP_REQUIRE_LOGIN", raising=False)
    app = create_app(f"sqlite:///{tmp_path / 'all.db'}", run_in_thread=False, parallel=False)
    c = TestClient(app, raise_server_exceptions=False, follow_redirects=False)
    c.db = app.state.db
    return c


def crawl(c, start: list[str], limit: int = 400) -> dict[str, int]:
    seen, todo, status = set(), list(start), {}
    while todo and len(seen) < limit:
        url = todo.pop()
        if url in seen:
            continue
        seen.add(url)
        r = c.get(url)
        status[url] = r.status_code
        if r.status_code in (301, 302, 303, 307):
            todo.append(urldefrag(r.headers["location"]).url)
            continue
        if "text/html" not in r.headers.get("content-type", ""):
            continue
        for href in re.findall(r'href="(/[^"]*)"', r.text):
            href = urldefrag(href.replace("&amp;", "&")).url
            if href.startswith(("/static/", "/logout", "/backup")) or "/excel" in href:
                continue
            todo.append(href)
    return status


def test_no_page_fails_after_the_planner_and_the_generator(client):
    client.post("/datasets/new", data={"name": "Mill"})
    client.post("/d/1/plan", data={**FORM, "action": "calculate"})
    with client.db.session() as s:
        line = s.query(m.ProductionLine).filter_by(dataset_id=1).one().id
        cls = s.query(m.LogClass).filter_by(dataset_id=1, no=1).one().id
    search = {"line_id": line, "objective": "volume", "simulate": "12", "max_sideboards": "1", "symmetric": "on",
              "thicker_to_centre": "on"}
    client.post("/d/1/generator", data={**search, "kind": "classes"})
    client.post("/d/1/generator", data={**search, "kind": "class", "mode": "class", "class_id": cls})
    client.post("/d/1/generator", data={**search, "kind": "chart", "from_cm": "20", "to_cm": "22"})
    client.post("/d/1/runs", data={"name": "By hand"})
    with client.db.session() as s:
        assert s.query(m.GeneratorJob).filter_by(dataset_id=1).count() == 4
    status = crawl(client, ["/", "/d/1/plan", "/d/1/generator?tab=history", "/d/1/runs"])
    failed = {u: c for u, c in status.items() if c >= 500}
    assert not failed, failed
    assert any("/generator/" in u for u in status) and len(status) > 30


def test_no_page_fails_on_an_imported_project(client):
    with client.db.session() as s:
        store.import_simsaw(s, FIXTURES / "ngomi_1", "Imported")
        s.commit()
    status = crawl(client, ["/", "/d/1/plan", "/d/1/runs"])
    failed = {u: c for u, c in status.items() if c >= 500}
    assert not failed, failed


def test_a_server_error_says_what_happened(client, monkeypatch):
    from app import planner
    monkeypatch.setattr(planner, "load", lambda *a: (_ for _ in ()).throw(RuntimeError("disc too thin")))
    client.post("/datasets/new", data={"name": "Mill"})
    r = client.get("/d/1/plan")
    assert r.status_code == 500 and "Something went wrong" in r.text and "RuntimeError: disc too thin" in r.text
