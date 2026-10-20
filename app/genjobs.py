"""Generator searches as background jobs: one class (or diameter), every log class at once, or a
diameter chart.

A job keeps the form it was started with and a snapshot of the engine inputs, like a batch run, so
its results stay meaningful after the dataset changes.
"""
from __future__ import annotations

import atexit
import dataclasses
import json
import multiprocessing
import os
import threading
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from types import SimpleNamespace

from engine import generator as G
from importers.simsaw import Dataset

from . import models as m
from . import simview, snapshot
from .db import Database

_cancel: dict[int, threading.Event] = {}
_pool: ProcessPoolExecutor | None = None
_pool_lock = threading.Lock()


def _map_fn(parallel: bool):
    """Simulations in parallel processes when the machine has more than one core."""
    global _pool
    if not parallel or (os.cpu_count() or 1) < 2:
        return map
    with _pool_lock:
        if _pool is None:
            # spawn, not fork: forked workers would inherit the web server's listening socket
            _pool = ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 1),
                                        mp_context=multiprocessing.get_context("spawn"))
            atexit.register(_pool.shutdown, wait=False, cancel_futures=True)
    return _pool.map


# ------------------------------------------------------------------ the form <-> engine options

def constraints(p: dict) -> G.Constraints:
    pair = lambda x: (float(x[0]), float(x[1]))
    return G.Constraints(
        symmetric=bool(p.get("symmetric", True)), thicker_to_centre=bool(p.get("thicker_to_centre", True)),
        max_sideboards_per_side=int(p.get("max_sideboards", 2)),
        max_primary_blades=int(p["max_primary_blades"]) if p.get("max_primary_blades") else None,
        max_secondary_blades=int(p["max_secondary_blades"]) if p.get("max_secondary_blades") else None,
        max_thicknesses=int(p["max_thicknesses"]) if p.get("max_thicknesses") else None,
        cant_widths=tuple(float(w) for w in p["cant_widths"]) if p.get("cant_widths") else None,
        must_include=tuple(pair(x) for x in p.get("must_include", [])),
        exclude=tuple(pair(x) for x in p.get("exclude", [])),
        target=pair(p["target"]) if p.get("target") else None,
        min_target_share=float(p.get("min_share", 0.0)))


def class_price(ds: Dataset, sed_cm: float) -> float:
    for c in ds.log_classes:
        if c.min_diameter_cm - 1e-6 <= sed_cm <= c.max_diameter_cm + 1e-6:
            return c.log_price
    return 0.0


def ranked_dict(r: G.Ranked) -> dict:
    d = simview.pattern_result_dict(r.result)
    d.pop("per_log", None)
    d.update(primary=r.primary, secondary=r.secondary, prescreen=r.prescreen, score=r.score,
             target_volume=r.target_volume, target_share=r.target_share,
             primary_blades=r.candidate.primary_blades, secondary_blades=r.candidate.secondary_blades)
    return d


def class_logs(ds: Dataset, cl, length_m: float | None = None) -> tuple[list, bool]:
    """The logs to search a class on: its own logs when it has any; otherwise ideal logs at every
    centimetre across its diameter range, shaped like the dataset's logs (or straight logs with 10 mm/m
    taper when there are none). The flag says whether ideal logs were used."""
    own = ds.logs_in_class(cl.no)
    if own:
        return own, False
    seds, d = [], cl.min_diameter_cm
    while d <= cl.max_diameter_cm + 1e-6:
        seds.append(round(d, 1))
        d += 1.0
    if seds[-1] < cl.max_diameter_cm - 0.05:
        seds.append(round(cl.max_diameter_cm, 1))
    logs = [dataclasses.replace(G.representative_logs(sed, ds.logs, length_m)[0], no=i + 1)
            for i, sed in enumerate(seds)]
    return logs, True


def _steps(result: dict) -> list[G.Step]:
    return [G.Step(st["sed"], [SimpleNamespace(**r) for r in st["ranked"]]) for st in result.get("steps", [])]


def groups(result: dict, mode: str, value: float, objective: str | None) -> list[G.Group]:
    """Suggested classes from a stored chart result: a fixed number of classes ("n"), or neighbouring
    diameters grouped while one pattern stays within a tolerance of each step's best ("tol"; recovery
    points, or rand per m3 for the value objective)."""
    if mode == "n":
        return G.best_classes(_steps(result), max(1, int(value)))
    tol = value if objective == "value" else value / 100.0
    return G.group_steps(_steps(result), tol)


# ------------------------------------------------------------------ jobs

def create(db: Database, ds_id: int, ds: Dataset, kind: str, params: dict, title: str) -> int:
    with db.session() as s:
        job = m.GeneratorJob(dataset_id=ds_id, kind=kind, title=title, params=json.dumps(params),
                             snapshot=snapshot.dumps(ds), status="queued")
        s.add(job)
        s.commit()
        return job.id


def execute(db: Database, job_id: int, parallel: bool = True) -> None:
    cancel = _cancel.setdefault(job_id, threading.Event())
    t0 = time.time()
    with db.session() as s:
        job = s.get(m.GeneratorJob, job_id)
        job.status = "running"
        s.commit()
        last = [0.0]

        def progress(stage: str, done: int, total: int) -> None:
            now = time.time()
            if now - last[0] < 0.4 and done:
                return
            last[0] = now
            job.stage, job.progress, job.total = stage, done, total
            s.commit()

        try:
            p = json.loads(job.params)
            ds = snapshot.loads(job.snapshot)
            line = ds.line(p["line_name"])
            if not p.get("real_logs", True):
                ds.settings = dataclasses.replace(ds.settings, variation=None)   # search on ideal logs
            c = constraints(p)
            obj = G.Objective(p.get("objective", "volume"))
            mapf = _map_fn(parallel)
            if job.kind == "class":
                if p.get("mode") == "diameter":
                    d = float(p["diameter_cm"])
                    logs = G.representative_logs(d, ds.logs, p.get("length_m") or None)
                    price = class_price(ds, d)
                else:
                    logs = ds.logs_in_class(int(p["class_no"]))
                    price = ds.log_class(int(p["class_no"])).log_price
                res = G.generate(logs, ds.products, line, ds.settings, price, obj, c,
                                 simulate=int(p.get("simulate", 120)), progress=progress,
                                 cancelled=cancel.is_set, map_fn=mapf)
                out = {"ranked": [ranked_dict(r) for r in res.ranked],
                       "meta": {"enumerated": res.enumerated, "prescreened": res.prescreened,
                                "simulated": res.simulated, "notes": res.notes, "logs": res.logs,
                                "diameters_mm": res.diameters_mm, "length_m": res.length_m,
                                "truncated": res.truncated, "seconds": round(time.time() - t0, 1),
                                "log_nos": [g.no for g in logs] if p.get("mode") != "diameter" else []}}
            elif job.kind == "classes":
                classes = sorted(ds.log_classes, key=lambda cl: cl.no)
                rows = []
                for i, cl in enumerate(classes):
                    if cancel.is_set():
                        break
                    label = f"Class {cl.no} ({i + 1} of {len(classes)})"
                    logs, ideal = class_logs(ds, cl, p.get("length_m") or None)
                    row = {"no": cl.no, "min_cm": cl.min_diameter_cm, "max_cm": cl.max_diameter_cm,
                           "logs": len(logs), "ideal": ideal, "ranked": [], "problem": ""}
                    try:
                        res = G.generate(logs, ds.products, line, ds.settings, cl.log_price, obj, c,
                                         simulate=int(p.get("simulate", 80)), top=3,
                                         progress=lambda st, d, n, label=label: progress(f"{label}: {st}", d, n),
                                         cancelled=cancel.is_set, map_fn=mapf)
                        row["ranked"] = [ranked_dict(r) for r in res.ranked[:3]]
                    except G.GeneratorError as e:
                        row["problem"] = str(e)
                    rows.append(row)
                if rows and all(r["problem"] for r in rows):
                    raise G.GeneratorError(rows[0]["problem"])
                out = {"classes": rows, "meta": {"seconds": round(time.time() - t0, 1)}}
            else:
                steps = G.diameter_chart(int(p["from_cm"]), int(p["to_cm"]), ds.logs, ds.products, line, ds.settings,
                                         lambda d: class_price(ds, d), obj, c, simulate=int(p.get("simulate", 24)),
                                         length_m=p.get("length_m") or None, progress=progress,
                                         cancelled=cancel.is_set, map_fn=mapf)
                out = {"steps": [{"sed": st.sed_cm,
                                  "ranked": [{"primary": r.primary, "secondary": r.secondary, "score": r.score,
                                              "dry_recovery": r.result.dry_recovery,
                                              "nett_value": r.result.nett_value_recovery,
                                              "boards_per_log": r.result.board_count / len(r.result.logs)}
                                             for r in st.ranked]} for st in steps],
                       "meta": {"seconds": round(time.time() - t0, 1)}}
            job.result = json.dumps(out)
            job.status = "cancelled" if cancel.is_set() else "done"
            job.message = "Stopped before the end; the results so far are shown." if cancel.is_set() else ""
            s.commit()
        except G.GeneratorError as e:
            s.rollback()
            job = s.get(m.GeneratorJob, job_id)
            job.status, job.message = "failed", str(e)
            s.commit()
        except Exception as e:   # keep the app alive and say what went wrong
            s.rollback()
            job = s.get(m.GeneratorJob, job_id)
            job.status, job.message = "failed", f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}"
            s.commit()
        finally:
            _cancel.pop(job_id, None)


def start(db: Database, job_id: int, parallel: bool = True) -> threading.Thread:
    _cancel[job_id] = threading.Event()
    t = threading.Thread(target=execute, args=(db, job_id, parallel), daemon=True, name=f"generator-{job_id}")
    t.start()
    return t


def cancel(job_id: int) -> bool:
    ev = _cancel.get(job_id)
    if ev is None:
        return False
    ev.set()
    return True


def close_interrupted(db: Database) -> None:
    from sqlalchemy import select
    with db.session() as s:
        for job in s.scalars(select(m.GeneratorJob).where(m.GeneratorJob.status.in_(["running", "queued"]))):
            job.status, job.message = "cancelled", "Stopped because the app was closed during the search."
        s.commit()
