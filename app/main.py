"""Web app: FastAPI routes, server-rendered pages, small JSON API for the grids and the pattern screen."""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import shutil
import tempfile
from urllib.parse import urlencode

import numpy as np
from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from engine import generator as G
from engine import loggen
from engine.sawing import check_pattern

from . import models as m
from . import snapshot
from . import genjobs, reports, runs, simview, store, svg, tables
from .db import Database, db_url, migrate

HERE = pathlib.Path(__file__).parent


def go(path: str, **params) -> RedirectResponse:
    """Redirect after a form post, carrying a message or tab in the query string."""
    q = urlencode({k: v for k, v in params.items() if v is not None})
    return RedirectResponse(f"{path}?{q}" if q else path, 303)


def _money(v) -> str:
    return "R " + f"{v:,.2f}".replace(",", " ")


def _num(v, nd=2) -> str:
    return "" if v is None else f"{v:,.{nd}f}".replace(",", " ")


def _pct(v, nd=1) -> str:
    return "" if v is None else f"{100 * v:.{nd}f} %"


def create_app(url: str | None = None, run_in_thread: bool = True, parallel: bool = True) -> FastAPI:
    url = url or db_url()
    migrate(url)
    db = Database(url)
    runs.close_interrupted(db)
    genjobs.close_interrupted(db)
    app = FastAPI(title="Sawing patterns")
    app.state.db = db
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    tpl = Jinja2Templates(directory=HERE / "templates")
    tpl.env.filters.update(money=_money, num=_num, pct=_pct)
    tpl.env.globals.update(store=store, svg=svg, objectives=G.OBJECTIVE_LABELS)

    def page(request: Request, name: str, **ctx):
        return tpl.TemplateResponse(request, name, ctx)

    def dataset_or_404(s, ds_id: int) -> m.Dataset:
        ds = s.get(m.Dataset, ds_id)
        if ds is None:
            raise HTTPException(404, "No such dataset")
        return ds

    def placeholders(s, ds_id: int) -> list[str]:
        out = []
        n = s.scalar(select(func.count()).select_from(m.Combination).where(m.Combination.dataset_id == ds_id,
                                                                           m.Combination.price_placeholder))
        if n:
            out.append(f"{n} product price{'s' if n > 1 else ''}")
        n = s.scalar(select(func.count()).select_from(m.LogClass).where(m.LogClass.dataset_id == ds_id,
                                                                        m.LogClass.log_price_placeholder))
        if n:
            out.append(f"{n} log price{'s' if n > 1 else ''}")
        for ln in s.scalars(select(m.ProductionLine).where(m.ProductionLine.dataset_id == ds_id,
                                                          m.ProductionLine.kerfs_placeholder)):
            out.append(f"kerfs on {ln.name}")
        return out

    def ctx(s, ds_id: int, section: str) -> dict:
        ds = dataset_or_404(s, ds_id)
        return {"ds": ds, "section": section, "placeholders": placeholders(s, ds_id)}

    # -------------------------------------------------------------- datasets

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request, msg: str = ""):
        with db.session() as s:
            rows = []
            for ds in s.scalars(select(m.Dataset).order_by(m.Dataset.name)):
                count = lambda model: s.scalar(select(func.count()).select_from(model).where(model.dataset_id == ds.id))
                rows.append({"ds": ds, "logs": count(m.Log), "patterns": count(m.SawPattern), "runs": count(m.Run)})
            return page(request, "datasets.html", rows=rows, msg=msg, section="datasets")

    @app.post("/datasets/new")
    def new_dataset(name: str = Form(...)):
        with db.session() as s:
            ds = store.create_default_dataset(s, name.strip() or "New dataset")
            s.commit()
            return RedirectResponse(f"/d/{ds.id}", 303)

    @app.post("/datasets/import")
    def import_dataset(file: UploadFile = File(...), name: str = Form("")):
        suffix = pathlib.Path(file.filename or "").suffix.lower()
        if suffix not in {".mdb", ".accdb"}:
            return go("/", msg="Choose a Simsaw .mdb file to import.")
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / (pathlib.Path(file.filename).name or "dataset.mdb")
            with path.open("wb") as fh:
                shutil.copyfileobj(file.file, fh)
            with db.session() as s:
                try:
                    ds = store.import_simsaw(s, path, name.strip() or path.stem)
                    s.commit()
                except Exception as e:   # a damaged or unexpected file: say so, keep the app running
                    s.rollback()
                    return go("/", msg=f"Could not import {file.filename}: {e}")
        return RedirectResponse(f"/d/{ds.id}", 303)

    @app.post("/datasets/{ds_id}/duplicate")
    def duplicate(ds_id: int, name: str = Form(...)):
        with db.session() as s:
            dataset_or_404(s, ds_id)
            new = store.duplicate_dataset(s, ds_id, name.strip() or "Copy")
            s.commit()
            return RedirectResponse(f"/d/{new.id}", 303)

    @app.post("/datasets/{ds_id}/rename")
    def rename(ds_id: int, name: str = Form(...), notes: str = Form("")):
        with db.session() as s:
            ds = dataset_or_404(s, ds_id)
            ds.name, ds.notes = name.strip() or ds.name, notes
            s.commit()
        return RedirectResponse(f"/d/{ds_id}", 303)

    @app.post("/datasets/{ds_id}/delete")
    def delete(ds_id: int):
        with db.session() as s:
            store.delete_dataset(s, ds_id)
            s.commit()
        return RedirectResponse("/", 303)

    @app.get("/d/{ds_id}", response_class=HTMLResponse)
    def overview(request: Request, ds_id: int):
        with db.session() as s:
            c = ctx(s, ds_id, "overview")
            e = store.engine_dataset(s, ds_id)
            classes = []
            for lc in e.log_classes:
                pats = [p for p in e.patterns if p.log_class_no == lc.no]
                classes.append({"c": lc, "logs": len(e.logs_in_class(lc.no)), "patterns": len(pats)})
            unclassed = sum(1 for g in e.logs if store.class_of(g, e.log_classes) is None)
            return page(request, "overview.html", **c, e=e, classes=classes, unclassed=unclassed)

    # -------------------------------------------------------------- data entry pages

    @app.get("/d/{ds_id}/logs", response_class=HTMLResponse)
    def logs_page(request: Request, ds_id: int, msg: str = ""):
        with db.session() as s:
            c = ctx(s, ds_id, "logs")
            gen = s.scalar(select(m.LogGenerator).where(m.LogGenerator.dataset_id == ds_id))
            if gen is None:
                gen = m.LogGenerator(dataset_id=ds_id)
                s.add(gen)
                s.commit()
            grades = s.scalars(select(m.LogGrade).where(m.LogGrade.dataset_id == ds_id).order_by(m.LogGrade.no)).all()
            return page(request, "logs.html", **c, gen=gen, grades=grades, msg=msg)

    @app.post("/d/{ds_id}/logs/generate")
    async def generate_logs(request: Request, ds_id: int):
        form = await request.form()
        with db.session() as s:
            dataset_or_404(s, ds_id)
            gen = s.scalar(select(m.LogGenerator).where(m.LogGenerator.dataset_id == ds_id)) or m.LogGenerator(dataset_id=ds_id)
            s.add(gen)
            try:
                for f in ("no_of_logs", "seed", "diameter_distr", "length_distr", "taper_distr", "sweep_distr",
                          "ovality_distr", "defect_core_distr"):
                    if f in form:
                        setattr(gen, f, int(form[f]))
                for f in ("min_diameter", "max_diameter", "min_length", "max_length", "length_incr", "min_taper",
                          "max_taper", "min_sweep", "max_sweep", "min_ovality", "max_ovality", "min_defect_core",
                          "max_defect_core"):
                    setattr(gen, f, float(str(form[f]).replace(",", ".")))
            except (KeyError, ValueError):
                return go(f"/d/{ds_id}/logs", msg="Every generator field needs a number.")
            gen.fixed_seed = form.get("fixed_seed") == "on"
            gen.log_grade_id = int(form["log_grade_id"]) if form.get("log_grade_id") else None
            if not gen.fixed_seed:
                gen.seed = loggen.new_seed()
            if gen.no_of_logs < 1 or gen.no_of_logs > 20000:
                return go(f"/d/{ds_id}/logs", msg="Generate between 1 and 20 000 logs.")
            replace = form.get("mode", "replace") == "replace"
            if replace:
                for g in s.scalars(select(m.Log).where(m.Log.dataset_id == ds_id)):
                    s.delete(g)
                s.flush()
                first = 1
            else:
                first = (s.scalar(select(func.max(m.Log.log_no)).where(m.Log.dataset_id == ds_id)) or 0) + 1
            grade = s.get(m.LogGrade, gen.log_grade_id) if gen.log_grade_id else None
            D = loggen.Distribution
            spec = loggen.GeneratorSpec(
                gen.no_of_logs, loggen.Range(gen.min_diameter, gen.max_diameter, D(gen.diameter_distr)),
                loggen.Range(gen.min_length, gen.max_length, D(gen.length_distr)), gen.length_incr,
                loggen.Range(gen.min_taper, gen.max_taper, D(gen.taper_distr)),
                loggen.Range(gen.min_sweep, gen.max_sweep, D(gen.sweep_distr)),
                loggen.Range(gen.min_ovality, gen.max_ovality, D(gen.ovality_distr)),
                loggen.Range(gen.min_defect_core, gen.max_defect_core, D(gen.defect_core_distr)),
                grade.name if grade else "All log grades", first)
            logs = loggen.generate_logs(spec, np.random.default_rng(gen.seed))
            s.add_all([m.Log(dataset_id=ds_id, log_no=g.no, sed_cm=g.sed_cm, length_m=g.length_m,
                             taper=g.taper_mm_per_m, sweep_mm=g.sweep_mm, ovality=g.ovality,
                             defect_core_cm=g.defect_core_cm, log_grade_id=grade.id if grade else None) for g in logs])
            s.commit()
            msg = f"{len(logs)} logs generated with seed {gen.seed}" + ("" if replace else f", numbered from {first}") + "."
        return go(f"/d/{ds_id}/logs", msg=msg)

    PRODUCT_TABS = {"sizes": "Sizes and grades", "prices": "Products and prices", "wane": "Wane",
                    "centre": "Centre boards", "grades": "Grade outputs", "residues": "Residues"}

    @app.get("/d/{ds_id}/products", response_class=HTMLResponse)
    def products_page(request: Request, ds_id: int, tab: str = "sizes", msg: str = ""):
        with db.session() as s:
            c = ctx(s, ds_id, "products")
            st = store.settings_for(s, ds_id)
            s.commit()
            return page(request, "products.html", **c, tab=tab if tab in PRODUCT_TABS else "sizes", tabs=PRODUCT_TABS,
                        st=st, msg=msg)

    @app.post("/d/{ds_id}/residues")
    def save_residues(ds_id: int, chip_price: float = Form(0.0), sawdust_price: float = Form(0.0),
                      pct_fines: float = Form(0.0)):
        with db.session() as s:
            dataset_or_404(s, ds_id)
            st = store.settings_for(s, ds_id)
            st.chip_price, st.sawdust_price, st.pct_fines = chip_price, sawdust_price, min(max(pct_fines, 0.0), 100.0)
            s.commit()
        return go(f"/d/{ds_id}/products", tab="residues", msg="Residue prices saved.")

    LINE_FLOATS = ("primary_kerf", "secondary_kerf", "primary_resaw_kerf", "secondary_resaw_kerf", "max_sweep",
                   "log_rotation_deg", "log_misalignment_mm", "primary_offset_mm", "cant_misalignment_mm",
                   "secondary_offset_mm", "edger_kerf")
    LINE_OPTIONAL = ("primary_outside_kerf", "secondary_outside_kerf")
    LINE_INTS = ("saw_type", "primary_outside_blades", "secondary_outside_blades", "cant_guiding", "edging_objective",
                 "edger_blades", "max_boards_per_flitch", "no")
    LINE_BOOLS = ("primary_resaw", "secondary_resaw", "kerfs_placeholder")

    @app.get("/d/{ds_id}/machines", response_class=HTMLResponse)
    def machines_page(request: Request, ds_id: int, line: int | None = None, tab: str = "primary", msg: str = ""):
        with db.session() as s:
            c = ctx(s, ds_id, "machines")
            lines = s.scalars(select(m.ProductionLine).where(m.ProductionLine.dataset_id == ds_id)
                              .order_by(m.ProductionLine.no)).all()
            cur = next((ln for ln in lines if ln.id == line), lines[0] if lines else None)
            return page(request, "machines.html", **c, lines=lines, cur=cur, tab=tab, msg=msg)

    @app.post("/d/{ds_id}/machines/new")
    def new_line(ds_id: int, name: str = Form(...)):
        with db.session() as s:
            dataset_or_404(s, ds_id)
            n = (s.scalar(select(func.max(m.ProductionLine.no)).where(m.ProductionLine.dataset_id == ds_id)) or 0) + 1
            ln = m.ProductionLine(dataset_id=ds_id, no=n, name=name.strip() or f"Line {n}", kerfs_placeholder=True)
            s.add(ln)
            s.commit()
            return RedirectResponse(f"/d/{ds_id}/machines?line={ln.id}", 303)

    @app.post("/d/{ds_id}/machines/{line_id}")
    async def save_line(request: Request, ds_id: int, line_id: int):
        form = await request.form()
        tab = form.get("tab", "primary")
        with db.session() as s:
            ln = s.get(m.ProductionLine, line_id)
            if ln is None or ln.dataset_id != ds_id:
                raise HTTPException(404)
            kerfs = lambda: tuple(getattr(ln, f) for f in LINE_FLOATS + LINE_OPTIONAL if "kerf" in f)
            before = kerfs()
            try:
                for f in LINE_FLOATS:
                    if f in form:
                        setattr(ln, f, float(str(form[f]).replace(",", ".")))
                for f in LINE_OPTIONAL:
                    if f in form:
                        v = str(form[f]).strip()
                        setattr(ln, f, float(v.replace(",", ".")) if v else None)
                for f in LINE_INTS:
                    if f in form:
                        setattr(ln, f, int(form[f]))
            except ValueError:
                return go(f"/d/{ds_id}/machines", line=line_id, tab=tab, msg="Every field needs a number.")
            for f in LINE_BOOLS:
                if f + "_present" in form:
                    setattr(ln, f, form.get(f) == "on")
            for f in ("name", "primary_machine", "secondary_machine", "second_board_width"):
                if f in form:
                    setattr(ln, f, str(form[f]).strip())
            if kerfs() != before and "kerfs_placeholder_present" not in form:
                ln.kerfs_placeholder = False      # a kerf typed in by the user is no longer a placeholder
            s.commit()
        return go(f"/d/{ds_id}/machines", line=line_id, tab=tab, msg="Saved.")

    @app.post("/d/{ds_id}/machines/{line_id}/delete")
    def delete_line(ds_id: int, line_id: int):
        with db.session() as s:
            ln = s.get(m.ProductionLine, line_id)
            if ln is not None and ln.dataset_id == ds_id:
                s.delete(ln)
                s.commit()
        return RedirectResponse(f"/d/{ds_id}/machines", 303)

    SETTING_BOOLS = ("use_nominal_diameter", "use_nominal_length", "use_nominal_taper", "discretised")

    @app.get("/d/{ds_id}/settings", response_class=HTMLResponse)
    def settings_page(request: Request, ds_id: int, msg: str = ""):
        with db.session() as s:
            c = ctx(s, ds_id, "settings")
            st = store.settings_for(s, ds_id)
            s.commit()
            return page(request, "settings.html", **c, st=st, msg=msg)

    @app.post("/d/{ds_id}/settings")
    async def save_settings(request: Request, ds_id: int):
        form = await request.form()
        with db.session() as s:
            dataset_or_404(s, ds_id)
            st = store.settings_for(s, ds_id)
            try:
                st.nominal_diameter = int(form["nominal_diameter"])
                st.nominal_length_incr_m = float(form["nominal_length_incr_m"])
                st.nominal_taper_mm_per_m = float(form["nominal_taper_mm_per_m"])
                st.disc_separation_cm = float(form["disc_separation_cm"])
                st.points_per_disc = int(form["points_per_disc"])
                st.seed = int(form["seed"])
            except (KeyError, ValueError):
                return go(f"/d/{ds_id}/settings", msg="Every field needs a number.")
            if st.disc_separation_cm <= 0 or st.points_per_disc < 8:
                return go(f"/d/{ds_id}/settings", msg="Disc separation must be above 0 and points per disc at least 8.")
            for f in SETTING_BOOLS:
                setattr(st, f, form.get(f) == "on")
            s.commit()
        return go(f"/d/{ds_id}/settings", msg="Settings saved.")

    # -------------------------------------------------------------- grid API

    @app.get("/api/d/{ds_id}/grid/{name}")
    def grid_read(ds_id: int, name: str):
        if name not in tables.ENTITIES:
            raise HTTPException(404)
        with db.session() as s:
            dataset_or_404(s, ds_id)
            return tables.read(s, ds_id, name)

    @app.post("/api/d/{ds_id}/grid/{name}")
    def grid_write(ds_id: int, name: str, payload: dict = Body(...)):
        if name not in tables.ENTITIES:
            raise HTTPException(404)
        with db.session() as s:
            dataset_or_404(s, ds_id)
            try:
                return tables.write(s, ds_id, name, payload.get("rows", []))
            except tables.GridError as e:
                return JSONResponse({"errors": e.errors}, 400)

    # -------------------------------------------------------------- sawing patterns

    @app.get("/d/{ds_id}/patterns", response_class=HTMLResponse)
    def patterns_page(request: Request, ds_id: int):
        with db.session() as s:
            c = ctx(s, ds_id, "patterns")
            e = store.engine_dataset(s, ds_id)
            lines = s.scalars(select(m.ProductionLine).where(m.ProductionLine.dataset_id == ds_id).order_by(m.ProductionLine.no)).all()
            classes = s.scalars(select(m.LogClass).where(m.LogClass.dataset_id == ds_id).order_by(m.LogClass.no)).all()
            sizes = {"thicknesses": [t.dry for t in e.products.thicknesses],
                     "widths": [w.dry for w in e.products.widths]}
            return page(request, "patterns.html", **c, lines=lines, classes=classes, sizes=sizes)

    def _line_and_class(s, ds_id, line_id, class_id):
        ln, lc = s.get(m.ProductionLine, line_id), s.get(m.LogClass, class_id)
        if ln is None or lc is None or ln.dataset_id != ds_id or lc.dataset_id != ds_id:
            raise HTTPException(404, "Choose a production line and log class from this dataset")
        return ln, lc

    @app.get("/api/d/{ds_id}/patterns")
    def pattern_list(ds_id: int, line_id: int, class_id: int):
        with db.session() as s:
            ln, lc = _line_and_class(s, ds_id, line_id, class_id)
            e = store.engine_dataset(s, ds_id)
            pats = s.scalars(select(m.SawPattern).where(m.SawPattern.line_id == line_id, m.SawPattern.log_class_id == class_id)
                             .order_by(m.SawPattern.pattern_no)).all()
            return {"patterns": [{"id": p.id, "pattern_no": p.pattern_no, "primary": p.primary, "secondary": p.secondary,
                                  "source": p.source,
                                  "problems": check_pattern(p.primary, p.secondary, e.products, e.line(ln.name))}
                                 for p in pats],
                    "logs": [simview.log_dict(g) for g in e.logs_in_class(lc.no)]}

    @app.post("/api/d/{ds_id}/patterns")
    def pattern_save(ds_id: int, payload: dict = Body(...)):
        with db.session() as s:
            ln, lc = _line_and_class(s, ds_id, int(payload["line_id"]), int(payload["class_id"]))
            primary, secondary = str(payload.get("primary", "")).strip(), str(payload.get("secondary", "")).strip()
            if not primary:
                return JSONResponse({"errors": ["Type a primary pattern first."]}, 400)
            pid = payload.get("id")
            if pid:
                p = s.get(m.SawPattern, int(pid))
                if p is None or p.dataset_id != ds_id:
                    raise HTTPException(404)
            else:
                n = (s.scalar(select(func.max(m.SawPattern.pattern_no)).where(
                    m.SawPattern.line_id == ln.id, m.SawPattern.log_class_id == lc.id)) or 0) + 1
                p = m.SawPattern(dataset_id=ds_id, line_id=ln.id, log_class_id=lc.id, pattern_no=n,
                                 source=payload.get("source", "manual"))
                s.add(p)
            p.primary, p.secondary = primary, secondary
            s.commit()
            return {"id": p.id}

    @app.post("/api/d/{ds_id}/patterns/{pid}/delete")
    def pattern_delete(ds_id: int, pid: int):
        with db.session() as s:
            p = s.get(m.SawPattern, pid)
            if p is None or p.dataset_id != ds_id:
                raise HTTPException(404)
            s.delete(p)
            s.commit()
            return {"ok": True}

    @app.get("/api/d/{ds_id}/diagram")
    def diagram(ds_id: int, line_id: int, log_no: int, primary: str = "", secondary: str = ""):
        with db.session() as s:
            ln = s.get(m.ProductionLine, line_id)
            if ln is None or ln.dataset_id != ds_id:
                raise HTTPException(404)
            e = store.engine_dataset(s, ds_id)
        log = next((g for g in e.logs if g.no == log_no), None)
        if log is None:
            raise HTTPException(404, "No such log")
        return simview.diagram(e, ln.name, log, primary, secondary)

    @app.get("/api/d/{ds_id}/simulate_class")
    def simulate_class(ds_id: int, line_id: int, class_id: int, primary: str = "", secondary: str = ""):
        with db.session() as s:
            ln, lc = _line_and_class(s, ds_id, line_id, class_id)
            e = store.engine_dataset(s, ds_id)
        return simview.class_result(e, ln.name, lc.no, primary, secondary)

    # -------------------------------------------------------------- batch runs

    @app.get("/d/{ds_id}/runs", response_class=HTMLResponse)
    def runs_page(request: Request, ds_id: int, msg: str = ""):
        with db.session() as s:
            c = ctx(s, ds_id, "runs")
            rows = s.scalars(select(m.Run).where(m.Run.dataset_id == ds_id).order_by(m.Run.created_at.desc(), m.Run.id.desc())).all()
            lines = s.scalars(select(m.ProductionLine).where(m.ProductionLine.dataset_id == ds_id).order_by(m.ProductionLine.no)).all()
            classes = s.scalars(select(m.LogClass).where(m.LogClass.dataset_id == ds_id).order_by(m.LogClass.no)).all()
            n_patterns = s.scalar(select(func.count()).select_from(m.SawPattern).where(m.SawPattern.dataset_id == ds_id))
            default_name = f"Run {dt.datetime.now():%Y-%m-%d %H:%M}"
            return page(request, "runs.html", **c, runs=rows, lines=lines, classes=classes, msg=msg,
                        default_name=default_name, n_patterns=n_patterns)

    @app.post("/d/{ds_id}/runs")
    async def start_run(request: Request, ds_id: int):
        form = await request.form()
        with db.session() as s:
            dataset_or_404(s, ds_id)
            line_names = [ln.name for ln in s.scalars(select(m.ProductionLine).where(
                m.ProductionLine.id.in_([int(v) for v in form.getlist("line_id")])))]
            class_nos = [c.no for c in s.scalars(select(m.LogClass).where(
                m.LogClass.id.in_([int(v) for v in form.getlist("class_id")])))]
        name = str(form.get("name") or "").strip() or f"Run {dt.datetime.now():%Y-%m-%d %H:%M}"
        rid = runs.create_run(db, ds_id, name, line_names or None, class_nos or None)
        if run_in_thread:
            runs.start(db, rid)
        else:
            runs.execute(db, rid)
        return go(f"/d/{ds_id}/runs", msg=f"Run “{name}” started.")

    @app.get("/api/runs/{rid}")
    def run_status(rid: int):
        with db.session() as s:
            r = s.get(m.Run, rid)
            if r is None:
                raise HTTPException(404)
            return {"id": r.id, "status": r.status, "progress": r.progress, "total": r.total, "message": r.message}

    @app.post("/d/{ds_id}/runs/{rid}/cancel")
    def cancel_run(ds_id: int, rid: int):
        runs.cancel(rid)
        return RedirectResponse(f"/d/{ds_id}/runs", 303)

    @app.post("/d/{ds_id}/runs/{rid}/delete")
    def delete_run(ds_id: int, rid: int):
        with db.session() as s:
            r = s.get(m.Run, rid)
            if r is not None and r.dataset_id == ds_id and r.status != "running":
                s.delete(r)
                s.commit()
        return RedirectResponse(f"/d/{ds_id}/runs", 303)

    # -------------------------------------------------------------- reports

    @app.get("/d/{ds_id}/reports", response_class=HTMLResponse)
    def reports_page(request: Request, ds_id: int, run: int | None = None, view: str = "oneliner",
                     pattern: str = "", lengths: str = "none"):
        pattern = int(pattern) if pattern.isdigit() else None
        with db.session() as s:
            c = ctx(s, ds_id, "reports")
            all_runs = s.scalars(select(m.Run).where(m.Run.dataset_id == ds_id, m.Run.status.in_(["done", "cancelled"]))
                                 .order_by(m.Run.created_at.desc(), m.Run.id.desc())).all()
            cur = next((r for r in all_runs if r.id == run), all_runs[0] if all_runs else None)
            data = {}
            if cur is not None:
                pats = reports.run_patterns(s, cur.id)
                data["patterns"] = pats
                data["combined"] = reports.combined(pats) if len(pats) > 1 else None
                if view == "boards":
                    lengths = lengths if lengths in reports.LENGTH_MODES else "none"
                    if pattern:
                        data["board_rows"] = [(next((p for p in pats if p.rp.id == pattern), None),
                                               reports.board_report(s, cur, pattern, lengths))]
                    else:
                        data["board_rows"] = [(None, reports.board_report(s, cur, None, lengths))]
                elif view == "summary":
                    data["balances"] = [(p, reports.volume_balance(p)) for p in pats + ([data["combined"]] if data["combined"] else [])]
            return page(request, "reports.html", **c, runs=all_runs, cur=cur, view=view, pattern=pattern,
                        lengths=lengths, length_modes=reports.LENGTH_MODES, **data)

    @app.get("/d/{ds_id}/reports/{rid}/excel")
    def report_excel(ds_id: int, rid: int):
        with db.session() as s:
            r = s.get(m.Run, rid)
            if r is None or r.dataset_id != ds_id:
                raise HTTPException(404)
            body = reports.excel(s, r)
            fname = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{r.name}.xlsx")
        return Response(body, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{fname}"'})

    # -------------------------------------------------------------- pattern generator

    def _products_list(e) -> list[tuple[float, float]]:
        return sorted({(c.thickness, c.width) for c in e.products.combinations if c.valid})

    def _pair(v: str) -> list[float]:
        t, w = v.lower().split("x")
        return [float(t), float(w)]

    @app.get("/d/{ds_id}/generator", response_class=HTMLResponse)
    def generator_page(request: Request, ds_id: int, tab: str = "class", msg: str = ""):
        with db.session() as s:
            c = ctx(s, ds_id, "generator")
            e = store.engine_dataset(s, ds_id)
            lines = s.scalars(select(m.ProductionLine).where(m.ProductionLine.dataset_id == ds_id).order_by(m.ProductionLine.no)).all()
            classes = s.scalars(select(m.LogClass).where(m.LogClass.dataset_id == ds_id).order_by(m.LogClass.no)).all()
            jobs = s.scalars(select(m.GeneratorJob).where(m.GeneratorJob.dataset_id == ds_id)
                             .order_by(m.GeneratorJob.created_at.desc(), m.GeneratorJob.id.desc())).all()
            seds = [g.sed_cm for g in e.logs]
            span = (int(min(seds)), int(max(seds))) if seds else (18, 40)
            lengths = sorted(g.length_m for g in e.logs)
            return page(request, "generator.html", **c, tab=tab, lines=lines, classes=classes, jobs=jobs, msg=msg,
                        products=_products_list(e), widths=[w.dry for w in e.products.widths], span=span,
                        length=lengths[len(lengths) // 2] if lengths else 3.0,
                        counts={lc.no: len(e.logs_in_class(lc.no)) for lc in e.log_classes})

    @app.post("/d/{ds_id}/generator")
    async def generator_start(request: Request, ds_id: int):
        f = await request.form()
        kind = "chart" if f.get("kind") == "chart" else "class"
        try:
            with db.session() as s:
                dataset_or_404(s, ds_id)
                ln = s.get(m.ProductionLine, int(f["line_id"]))
                if ln is None or ln.dataset_id != ds_id:
                    raise ValueError("choose a production line")
                e = store.engine_dataset(s, ds_id)
            num = lambda k: (str(f.get(k) or "").strip().replace(",", ".") or None)
            p = {"line_id": ln.id, "line_name": ln.name, "objective": f.get("objective", "volume"),
                 "symmetric": f.get("symmetric") == "on", "thicker_to_centre": f.get("thicker_to_centre") == "on",
                 "max_sideboards": int(num("max_sideboards") or 2),
                 "max_primary_blades": int(num("max_primary_blades")) if num("max_primary_blades") else None,
                 "max_secondary_blades": int(num("max_secondary_blades")) if num("max_secondary_blades") else None,
                 "max_thicknesses": int(num("max_thicknesses")) if num("max_thicknesses") else None,
                 "cant_widths": [float(w) for w in f.getlist("cant_width")] or None,
                 "must_include": [_pair(v) for v in f.getlist("must_include")],
                 "exclude": [_pair(v) for v in f.getlist("exclude")],
                 "target": _pair(f["target"]) if f.get("target") else None,
                 "min_share": float(num("min_share") or 0) / 100.0,
                 "length_m": float(num("length_m")) if num("length_m") else None}
            if kind == "class":
                p["simulate"] = int(num("simulate") or 80)
                if f.get("mode") == "diameter":
                    p["mode"], p["diameter_cm"] = "diameter", float(num("diameter_cm"))
                    title = f"{p['diameter_cm']:g} cm on {ln.name}"
                else:
                    with db.session() as s2:
                        cl = s2.get(m.LogClass, int(f["class_id"]))
                    if cl is None or cl.dataset_id != ds_id:
                        raise ValueError("choose a log class")
                    p["mode"], p["class_no"], p["class_id"] = "class", cl.no, cl.id
                    title = f"Class {cl.no} ({cl.min_diameter_cm:g}-{cl.max_diameter_cm:g} cm) on {ln.name}"
            else:
                p["simulate"] = int(num("simulate") or 24)
                p["from_cm"], p["to_cm"] = int(float(num("from_cm"))), int(float(num("to_cm")))
                if p["to_cm"] < p["from_cm"] or p["to_cm"] - p["from_cm"] > 60:
                    raise ValueError("the diameter range must run upward and span at most 60 cm")
                title = f"Diameter chart {p['from_cm']}-{p['to_cm']} cm on {ln.name}"
        except (KeyError, ValueError, TypeError) as err:
            msg = str(err) if isinstance(err, ValueError) and "could not convert" not in str(err) else "Check the numbers in the form."
            return go(f"/d/{ds_id}/generator", tab=kind, msg=msg)
        title += f", {G.OBJECTIVE_LABELS[G.Objective(p['objective'])].lower()}"
        jid = genjobs.create(db, ds_id, e, kind, p, title)
        if run_in_thread:
            genjobs.start(db, jid, parallel)
        else:
            genjobs.execute(db, jid, parallel)
        return RedirectResponse(f"/d/{ds_id}/generator/{jid}", 303)

    def _job(s, ds_id: int, jid: int) -> m.GeneratorJob:
        job = s.get(m.GeneratorJob, jid)
        if job is None or job.dataset_id != ds_id:
            raise HTTPException(404, "No such search")
        return job

    @app.get("/d/{ds_id}/generator/{jid}", response_class=HTMLResponse)
    def generator_job_page(request: Request, ds_id: int, jid: int, group: str = "n", n: int | None = None,
                           tol: float | None = None, msg: str = ""):
        with db.session() as s:
            c = ctx(s, ds_id, "generator")
            job = _job(s, ds_id, jid)
            p = json.loads(job.params)
            result = json.loads(job.result) if job.result else None
            classes = s.scalars(select(m.LogClass).where(m.LogClass.dataset_id == ds_id).order_by(m.LogClass.no)).all()
            data = {"job": job, "p": p, "result": result, "classes": classes, "msg": msg}
            if result and job.kind == "class" and result["ranked"]:
                snap = snapshot.loads(job.snapshot)
                if p.get("mode") == "diameter":
                    show = G.representative_logs(p["diameter_cm"], snap.logs, p.get("length_m"))[1]
                else:
                    show = simview.median_log([g for g in snap.logs if g.no in set(result["meta"]["log_nos"])])
                data["shown_log"] = show
                data["diagrams"] = [simview.diagram(snap, p["line_name"], show, r["primary"], r["secondary"])
                                    if show else None for r in result["ranked"]]
                d = p.get("diameter_cm")
                data["default_class"] = p.get("class_id") or next(
                    (cl.id for cl in classes if d is not None and cl.min_diameter_cm <= d <= cl.max_diameter_cm), None)
            if result and job.kind == "chart":
                value = p.get("objective") == "value"
                data["group"] = "tol" if group == "tol" else "n"
                data["n"] = n or max(1, len(classes))
                data["tol"] = tol if tol is not None else (20.0 if value else 0.5)
                data["groups"] = genjobs.groups(result, data["group"],
                                                data["n"] if data["group"] == "n" else data["tol"], p.get("objective"))
                data["scale"] = 1.0 if value else 100.0
                data["chart"] = _chart(result, data["groups"], p.get("objective"))
            return page(request, "generator_job.html", **c, **data)

    def _chart(result: dict, groups: list, objective: str | None) -> dict:
        steps = [st for st in result["steps"] if st["ranked"]]
        value = objective == "value"
        ys = [st["ranked"][0]["nett_value"] if value else 100 * st["ranked"][0]["dry_recovery"] for st in steps]
        group_of = {}
        for gi, g in enumerate(groups):
            for sed in g.steps:
                group_of[sed] = gi
        return {"bars": [{"sed": st["sed"], "y": y, "group": group_of.get(st["sed"], 0),
                          "pattern": f'{st["ranked"][0]["primary"]}  {st["ranked"][0]["secondary"]}'}
                         for st, y in zip(steps, ys)],
                "ymax": max(ys) if ys else 1.0, "ymin": min(0.0, min(ys)) if ys else 0.0,
                "unit": "R/m³ log, nett" if value else "% dry recovery"}

    @app.get("/api/genjobs/{jid}")
    def generator_status(jid: int):
        with db.session() as s:
            job = s.get(m.GeneratorJob, jid)
            if job is None:
                raise HTTPException(404)
            return {"status": job.status, "stage": job.stage, "progress": job.progress, "total": job.total,
                    "message": job.message}

    @app.post("/d/{ds_id}/generator/{jid}/cancel")
    def generator_cancel(ds_id: int, jid: int):
        genjobs.cancel(jid)
        return RedirectResponse(f"/d/{ds_id}/generator/{jid}", 303)

    @app.post("/d/{ds_id}/generator/{jid}/delete")
    def generator_delete(ds_id: int, jid: int):
        with db.session() as s:
            job = _job(s, ds_id, jid)
            if job.status not in ("running", "queued"):
                s.delete(job)
                s.commit()
        return go(f"/d/{ds_id}/generator", tab="history")

    @app.post("/d/{ds_id}/generator/{jid}/save")
    def generator_save(ds_id: int, jid: int, primary: str = Form(...), secondary: str = Form(""),
                       class_id: int = Form(...)):
        with db.session() as s:
            job = _job(s, ds_id, jid)
            p = json.loads(job.params)
            cl = s.get(m.LogClass, class_id)
            ln = s.get(m.ProductionLine, p["line_id"])
            if cl is None or cl.dataset_id != ds_id or ln is None:
                return go(f"/d/{ds_id}/generator/{jid}", msg="That class or line no longer exists.")
            n = (s.scalar(select(func.max(m.SawPattern.pattern_no)).where(
                m.SawPattern.line_id == ln.id, m.SawPattern.log_class_id == cl.id)) or 0) + 1
            s.add(m.SawPattern(dataset_id=ds_id, line_id=ln.id, log_class_id=cl.id, pattern_no=n, primary=primary,
                               secondary=secondary, source="generated"))
            s.commit()
        return go(f"/d/{ds_id}/generator/{jid}", msg=f"Saved as pattern {n} of class {cl.no} on {ln.name}.")

    @app.post("/d/{ds_id}/generator/{jid}/apply")
    def generator_apply(ds_id: int, jid: int, group: str = Form("n"), value: float = Form(...)):
        """Replace the log classes with the suggested ones and save each class's pattern."""
        with db.session() as s:
            job = _job(s, ds_id, jid)
            p = json.loads(job.params)
            ln = s.get(m.ProductionLine, p["line_id"])
            if job.kind != "chart" or not job.result or ln is None:
                return go(f"/d/{ds_id}/generator/{jid}", msg="Nothing to apply.")
            groups = genjobs.groups(json.loads(job.result), group, value, p.get("objective"))
            old = s.scalars(select(m.LogClass).where(m.LogClass.dataset_id == ds_id).order_by(m.LogClass.no)).all()
            template = old[0] if old else None
            keep = ("min_length_m", "max_length_m", "length_incr_m", "min_taper", "max_taper", "min_sweep",
                    "max_sweep", "min_ovality", "max_ovality", "min_defect_core", "max_defect_core")
            prices = [(c.min_diameter_cm, c.max_diameter_cm, c.log_price, c.log_price_placeholder) for c in old]
            grades = list(template.grades) if template else []
            for c in old:
                s.delete(c)
            s.flush()
            for n, g in enumerate(groups, 1):
                mid = (g.from_cm + g.to_cm) / 2
                price = next(((pr, ph) for lo, hi, pr, ph in prices if lo <= mid <= hi), (0.0, True))
                cl = m.LogClass(dataset_id=ds_id, no=n, min_diameter_cm=g.from_cm, max_diameter_cm=g.to_cm,
                                log_price=price[0], log_price_placeholder=price[1],
                                **{k: getattr(template, k) for k in keep} if template else {})
                cl.grades = grades
                s.add(cl)
                s.flush()
                s.add(m.SawPattern(dataset_id=ds_id, line_id=ln.id, log_class_id=cl.id, pattern_no=1,
                                   primary=g.primary, secondary=g.secondary, source="generated"))
            s.commit()
        return go(f"/d/{ds_id}/logs", msg=f"{len(groups)} log classes set from the diameter chart, each with its best pattern.")

    @app.get("/d/{ds_id}/card", response_class=HTMLResponse)
    def setting_card(request: Request, ds_id: int, line_id: int | None = None, class_id: int | None = None,
                     primary: str = "", secondary: str = "", pattern_id: int | None = None):
        with db.session() as s:
            c = ctx(s, ds_id, "patterns")
            if pattern_id:
                sp = s.get(m.SawPattern, pattern_id)
                if sp is None or sp.dataset_id != ds_id:
                    raise HTTPException(404)
                line_id, class_id, primary, secondary = sp.line_id, sp.log_class_id, sp.primary, sp.secondary
            ln, lc = _line_and_class(s, ds_id, line_id, class_id)
            e = store.engine_dataset(s, ds_id)
        card = simview.setting_card(e, ln.name, lc.no, primary, secondary)
        return page(request, "card.html", **c, card=card, today=dt.date.today())

    return app
