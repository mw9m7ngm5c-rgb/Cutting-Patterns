"""Batch simulation: snapshot the inputs, saw every pattern's logs, store per-log and per-board results.

A run always saws from its own snapshot, never from the live tables, so the stored results and
the stored inputs always agree.
"""
from __future__ import annotations

import dataclasses
import threading
import traceback

from sqlalchemy import select

from engine import notation
from engine.sawing import layout, simulate_log
from importers.simsaw import Dataset

from . import models as m
from . import snapshot, store
from .db import Database

_cancel: dict[int, threading.Event] = {}


def _jobs(ds: Dataset, line_names: list[str] | None, class_nos: list[int] | None):
    for pd in ds.patterns:
        if line_names and pd.line_name not in line_names:
            continue
        if class_nos and pd.log_class_no not in class_nos:
            continue
        if not any(c.no == pd.log_class_no for c in ds.log_classes):
            continue
        yield pd, ds.logs_in_class(pd.log_class_no)


def create_run(db: Database, ds_id: int, name: str, line_names: list[str] | None = None,
               class_nos: list[int] | None = None, saw_on: str | None = None) -> int:
    """A run of the dataset's patterns. saw_on names a production line whose machine settings saw
    every chosen pattern instead of the pattern's own line (a scenario: same patterns, other machine)."""
    with db.session() as s:
        ds = store.engine_dataset(s, ds_id)
        if line_names or class_nos:
            ds.patterns = [pd for pd, _ in _jobs(ds, line_names, class_nos)]
        if saw_on:
            ds.line(saw_on)                                   # must exist
            ds.patterns = [dataclasses.replace(pd, line_name=saw_on) for pd in ds.patterns]
        total = sum(len(logs) for _, logs in _jobs(ds, None, None))
        run = m.Run(dataset_id=ds_id, name=name, status="queued", total=total, snapshot=snapshot.dumps(ds))
        s.add(run)
        s.commit()
        return run.id


def execute(db: Database, run_id: int) -> None:
    """Saw the run. Safe to call in a thread; checks for cancel between logs."""
    cancel = _cancel.setdefault(run_id, threading.Event())
    with db.session() as s:
        run = s.get(m.Run, run_id)
        run.status = "running"
        s.commit()
        try:
            ds = snapshot.loads(run.snapshot)
            done = 0
            for seq, (pd, logs) in enumerate(_jobs(ds, None, None)):
                line = ds.line(pd.line_name)
                cl = ds.log_class(pd.log_class_no)
                st = ds.settings
                rp = m.RunPattern(run_id=run_id, seq=seq, line_name=pd.line_name, class_no=pd.log_class_no,
                                  pattern_no=pd.pattern_no, primary=pd.primary, secondary=pd.secondary,
                                  diameter_range=store.diameter_range(cl), log_price=cl.log_price,
                                  chip_price=st.chip_price, sawdust_price=st.sawdust_price, pct_fines=st.pct_fines)
                s.add(rp)
                s.flush()
                try:
                    pattern = notation.parse(pd.primary, pd.secondary)
                    lay = layout(pattern, ds.products, line)
                except (notation.PatternError, KeyError, NotImplementedError) as e:
                    rp.error = str(e).strip("'\"")
                    done += len(logs)
                    run.progress = done
                    s.commit()
                    continue
                for log in logs:
                    if cancel.is_set():
                        run.status, run.message = "cancelled", "Stopped before the end; the results so far are kept."
                        s.commit()
                        return
                    lr = simulate_log(log, pattern, ds.products, line, ds.settings, lay=lay)
                    s.add(m.RunLogResult(run_pattern_id=rp.id, log_no=log.no, sed_cm=log.sed_cm, length_m=log.length_m,
                                         log_volume=lr.log_volume, dry_volume=lr.dry_board_volume,
                                         wet_volume=lr.wet_board_volume, value=lr.board_value,
                                         sawdust_volume=lr.sawdust_volume, chip_volume=lr.chip_volume,
                                         boards=len(lr.boards)))
                    s.add_all([m.RunBoardResult(
                        run_pattern_id=rp.id, log_no=log.no, board_type=b.board_type, board_no=b.board_no,
                        thickness=b.thickness, width=b.width, length_m=b.length_m, left=b.left, right=b.right,
                        bottom=b.bottom, top=b.top, front_m=b.front_m, back_m=b.back_m, resawn=b.resawn,
                        resaw_position=b.resaw_position, edged=b.edged, piece=b.piece, core_share=b.core_share,
                        grade=b.grade, dry_volume=b.dry_volume,
                        wet_volume=b.wet_volume, value=b.value) for b in lr.boards])
                    done += 1
                    run.progress = done
                    s.commit()
            run.status = "done"
            errors = s.scalars(select(m.RunPattern).where(m.RunPattern.run_id == run_id, m.RunPattern.error != "")).all()
            run.message = (f"{len(errors)} pattern(s) could not be sawn; see the one-liner report." if errors else "")
            s.commit()
        except Exception as e:   # keep the app alive and say what went wrong
            s.rollback()
            run = s.get(m.Run, run_id)
            run.status, run.message = "failed", f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}"
            s.commit()
        finally:
            _cancel.pop(run_id, None)


def start(db: Database, *run_ids: int) -> threading.Thread:
    """Saw one or more runs, one after the other, in a background thread."""
    for rid in run_ids:
        _cancel[rid] = threading.Event()

    def work():
        for rid in run_ids:
            execute(db, rid)

    t = threading.Thread(target=work, daemon=True, name="run-" + "-".join(map(str, run_ids)))
    t.start()
    return t


def cancel(run_id: int) -> bool:
    ev = _cancel.get(run_id)
    if ev is None:
        return False
    ev.set()
    return True


def close_interrupted(db: Database) -> None:
    """Runs left running when the app last stopped can never finish: mark them, keep their results."""
    with db.session() as s:
        for run in s.scalars(select(m.Run).where(m.Run.status.in_(["running", "queued"]))):
            run.status = "cancelled"
            run.message = "Stopped because the app was closed during the run; the results so far are kept."
        s.commit()
