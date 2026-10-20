"""The planner: one screen for the three things a mill knows (its saw line, the sizes it cuts and its
log classes), turned into the dataset tables the rest of the app works from.

Classes without real logs get sample logs: one every half centimetre across the class's diameter
range, at the class's typical length and taper, straight and round. They are marked as samples and
remade on every calculation, so real logs typed or pasted on the Logs page always take precedence.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from engine import model as em

from . import models as m
from . import store

SAW_TYPES = {0: "Headrig then gang saw (cant sawing)", 2: "Chipper-canter or profiler, then gang saw"}
SAMPLE_STEP_CM = 0.5


@dataclass
class ClassRow:
    no: int
    min_cm: float | str = ""
    max_cm: float | str = ""
    length_m: float | str = ""
    taper: float | str = ""
    real_logs: int = 0


@dataclass
class Plan:
    line: m.ProductionLine | None
    thicknesses: list[tuple[float, float]]
    widths: list[tuple[float, float]]
    cut: set[tuple[float, float]]
    classes: list[ClassRow]
    problems: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return not self.problems


def _num(v) -> float | None:
    try:
        return float(str(v).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def _key(t: float, w: float) -> str:
    return f"{t:g}x{w:g}"


def load(s: Session, ds_id: int) -> Plan:
    line = s.scalar(select(m.ProductionLine).where(m.ProductionLine.dataset_id == ds_id).order_by(m.ProductionLine.no))
    th = s.scalars(select(m.Thickness).where(m.Thickness.dataset_id == ds_id).order_by(m.Thickness.dry)).all()
    wd = s.scalars(select(m.Width).where(m.Width.dataset_id == ds_id).order_by(m.Width.dry)).all()
    tdry, wdry = {t.id: t.dry for t in th}, {w.id: w.dry for w in wd}
    cut = {(tdry[c.thickness_id], wdry[c.width_id])
           for c in s.scalars(select(m.Combination).where(m.Combination.dataset_id == ds_id, m.Combination.valid))}
    e = store.engine_dataset(s, ds_id)
    real = [g for g in e.logs if g.no not in sample_log_nos(s, ds_id)]
    classes = []
    for c in s.scalars(select(m.LogClass).where(m.LogClass.dataset_id == ds_id).order_by(m.LogClass.no)):
        n = sum(1 for g in real if store.class_of(g, e.log_classes) == c.no)
        classes.append(ClassRow(c.no, c.min_diameter_cm, c.max_diameter_cm,
                                c.plan_length_m if c.plan_length_m is not None else "",
                                c.plan_taper if c.plan_taper is not None else "", n))
    plan = Plan(line, [(t.dry, t.wet) for t in th], [(w.dry, w.wet) for w in wd], cut, classes)
    plan.problems = check(plan)
    return plan


def check(plan: Plan) -> list[str]:
    out = []
    if plan.line is None:
        out.append("Enter your saw line.")
    if not plan.cut:
        out.append("Tick at least one size you cut.")
    if not plan.classes:
        out.append("Enter at least one log class.")
    for c in plan.classes:
        if not c.real_logs and (c.length_m == "" or c.taper == ""):
            out.append(f"Class {c.no}: enter the typical log length and taper.")
    return out


def sample_log_nos(s: Session, ds_id: int) -> set[int]:
    return set(s.scalars(select(m.Log.log_no).where(m.Log.dataset_id == ds_id, m.Log.sample)))


# ------------------------------------------------------------------ saving the form

def _rows(form, *names) -> list[tuple]:
    cols = [form.getlist(n) for n in names]
    return [tuple(r) for r in zip(*cols)]


def save(s: Session, ds_id: int, form) -> list[str]:
    """Write the planner form to the dataset. Returns problems; nothing is written if there are any."""
    errors: list[str] = []

    # saw line
    kerfs = {k: _num(form.get(k)) for k in ("primary_kerf", "secondary_kerf", "edger_kerf")}
    labels = {"primary_kerf": "Headrig kerf", "secondary_kerf": "Gang saw kerf", "edger_kerf": "Edger kerf"}
    for k, v in kerfs.items():
        if v is None or not 0 < v < 30:
            errors.append(f"{labels[k]}: enter the saw kerf in mm (for example 4).")
    blades = _num(form.get("edger_blades"))
    if blades is None or blades < 2 or blades != int(blades):
        errors.append("Edger blades: a whole number, 2 or more.")
    spacing_text = (form.get("edger_spacing") or "").strip()
    spacing = ""
    if spacing_text:
        try:
            gaps = store.parse_spacing(spacing_text)
            if blades and len(gaps) != int(blades) - 1:
                errors.append(f"Edger spacing: {int(blades)} blades have {int(blades) - 1} gaps; enter one distance per gap, "
                              "or leave it empty if the blades move.")
            spacing = " ".join(f"{v:g}" for v in gaps)
        except ValueError:
            errors.append("Edger spacing: distances in mm, numbers above 0, separated by spaces.")
    saw_type = int(form.get("saw_type") or 0)
    saw_type = saw_type if saw_type in SAW_TYPES else 0

    # sizes
    def sizes(prefix: str, label: str) -> list[tuple[float, float]]:
        out, seen = [], set()
        for dry, wet in _rows(form, f"{prefix}_dry", f"{prefix}_wet"):
            if not str(dry).strip() and not str(wet).strip():
                continue
            d, w = _num(dry), _num(wet)
            if d is None or d <= 0:
                errors.append(f"{label}: '{dry}' is not a size in mm.")
                continue
            if w is None or w < d:
                errors.append(f"{label} {d:g}: the green (sawn) size must be at least the finished size.")
                continue
            if d in seen:
                errors.append(f"{label} {d:g} is listed twice.")
                continue
            seen.add(d)
            out.append((d, w))
        return sorted(out)

    th, wd = sizes("th", "Thickness"), sizes("wd", "Width")
    if not th:
        errors.append("Enter at least one board thickness.")
    if not wd:
        errors.append("Enter at least one board width.")
    cut = set()
    for v in form.getlist("cut"):
        t, _, w = v.partition("x")
        if _num(t) is not None and _num(w) is not None:
            cut.add((_num(t), _num(w)))
    cut &= {(t, w) for t, _ in th for w, _ in wd}

    # log classes
    classes = []
    for lo, hi, ln, tp in _rows(form, "cl_from", "cl_to", "cl_length", "cl_taper"):
        if not any(str(x).strip() for x in (lo, hi, ln, tp)):
            continue
        n = len(classes) + 1
        a, b, length, taper = _num(lo), _num(hi), _num(ln), _num(tp)
        if a is None or b is None or not 0 < a < b:
            errors.append(f"Class {n}: the diameter must run from a smaller to a larger number of cm.")
            continue
        if ln.strip() and (length is None or not 0.5 <= length <= 20):
            errors.append(f"Class {n}: log length in metres (for example 4.8).")
            continue
        if tp.strip() and (taper is None or not 0 <= taper <= 60):
            errors.append(f"Class {n}: taper in mm per metre (for example 8).")
            continue
        classes.append((a, b, length, taper))
    for (a1, b1, *_), (a2, b2, *_) in zip(classes, classes[1:]):
        if a2 <= b1:
            errors.append(f"Log classes overlap at {a2:g} cm: each class must start above the one before it.")
    if errors:
        return errors

    # -- write
    line = s.scalar(select(m.ProductionLine).where(m.ProductionLine.dataset_id == ds_id).order_by(m.ProductionLine.no))
    if line is None:
        line = m.ProductionLine(dataset_id=ds_id, no=1, name="Saw line")
        s.add(line)
    line.name = (form.get("line_name") or "").strip() or line.name or "Saw line"
    line.saw_type = saw_type
    line.primary_kerf, line.secondary_kerf, line.edger_kerf = (kerfs["primary_kerf"], kerfs["secondary_kerf"],
                                                               kerfs["edger_kerf"])
    line.edger_blades, line.edger_spacing = int(blades), spacing
    line.kerfs_placeholder = False

    for model, rows in ((m.Thickness, th), (m.Width, wd)):
        have = {x.dry: x for x in s.scalars(select(model).where(model.dataset_id == ds_id))}
        want = dict(rows)
        for dry, x in have.items():
            if dry not in want:
                s.delete(x)
            else:
                x.wet = want[dry]
        for dry, wet in rows:
            if dry not in have:
                s.add(model(dataset_id=ds_id, dry=dry, wet=wet))
    s.flush()
    if not s.scalar(select(func.count()).select_from(m.LengthClass).where(m.LengthClass.dataset_id == ds_id)):
        s.add(m.LengthClass(dataset_id=ds_id, name="All", min_m=0.9, max_m=6.6, incr_m=0.3))
        s.flush()
    store.sync_products(s, ds_id)
    tdry = {t.id: t.dry for t in s.scalars(select(m.Thickness).where(m.Thickness.dataset_id == ds_id))}
    wdry = {w.id: w.dry for w in s.scalars(select(m.Width).where(m.Width.dataset_id == ds_id))}
    for c in s.scalars(select(m.Combination).where(m.Combination.dataset_id == ds_id)):
        c.valid = (tdry[c.thickness_id], wdry[c.width_id]) in cut

    old = s.scalars(select(m.LogClass).where(m.LogClass.dataset_id == ds_id).order_by(m.LogClass.no)).all()
    for c in old[len(classes):]:
        s.delete(c)
    for i, (a, b, length, taper) in enumerate(classes):
        c = old[i] if i < len(old) else m.LogClass(dataset_id=ds_id, no=i + 1)
        if i >= len(old):
            s.add(c)
        c.no, c.min_diameter_cm, c.max_diameter_cm = i + 1, a, b
        c.plan_length_m, c.plan_taper = length, taper
        # the class's own limits must let its sample logs in
        if length is not None:
            c.min_length_m = min(c.min_length_m if c.min_length_m is not None else 0.0, length)
            c.max_length_m = max(c.max_length_m if c.max_length_m is not None else 99.0, length)
        if taper is not None:
            c.min_taper = min(c.min_taper if c.min_taper is not None else 0.0, taper)
            c.max_taper = max(c.max_taper if c.max_taper is not None else 999.0, taper)
    # each class's own taper counts (not one nominal taper for every log)
    store.settings_for(s, ds_id).use_nominal_taper = False
    s.flush()
    return []


def make_sample_logs(s: Session, ds_id: int) -> int:
    """Replace the sample logs: for each class with no real logs, one log every half centimetre of
    small-end diameter across the class, at its typical length and taper. Returns how many were made."""
    s.execute(delete(m.Log).where(m.Log.dataset_id == ds_id, m.Log.sample))
    s.flush()
    e = store.engine_dataset(s, ds_id)
    next_no = (s.scalar(select(func.max(m.Log.log_no)).where(m.Log.dataset_id == ds_id)) or 0) + 1
    made = 0
    for c in s.scalars(select(m.LogClass).where(m.LogClass.dataset_id == ds_id).order_by(m.LogClass.no)):
        if e.logs_in_class(c.no) or c.plan_length_m is None or c.plan_taper is None:
            continue
        seds, d = [], c.min_diameter_cm
        while d < c.max_diameter_cm - 1e-6:
            seds.append(round(d, 1))
            d += SAMPLE_STEP_CM
        seds.append(round(c.max_diameter_cm, 1))
        for sed in seds:
            s.add(m.Log(dataset_id=ds_id, log_no=next_no, sed_cm=sed, length_m=c.plan_length_m, taper=c.plan_taper,
                        sweep_mm=0.0, ovality=1.0, defect_core_cm=0.0, sample=True))
            next_no += 1
            made += 1
    s.flush()
    return made


def sample_class_log(logs: list[em.Log]) -> em.Log | None:
    """The log a class's diagram is drawn on: the middle one by diameter."""
    if not logs:
        return None
    return sorted(logs, key=lambda g: (g.sed_cm, g.no))[len(logs) // 2]


def from_form(form, problems: list[str], line: m.ProductionLine | None) -> Plan:
    """The form as typed, to show it again with its problems (nothing saved)."""
    sizes = lambda prefix: [(d, w) for d, w in _rows(form, f"{prefix}_dry", f"{prefix}_wet") if str(d).strip() or str(w).strip()]
    cut = set()
    for v in form.getlist("cut"):
        t, _, w = v.partition("x")
        cut.add((_num(t), _num(w)))
    classes = [ClassRow(i + 1, *r) for i, r in enumerate(
        r for r in _rows(form, "cl_from", "cl_to", "cl_length", "cl_taper") if any(str(x).strip() for x in r))]
    shown = m.ProductionLine(name=form.get("line_name") or "", saw_type=int(form.get("saw_type") or 0),
                             primary_kerf=form.get("primary_kerf"), secondary_kerf=form.get("secondary_kerf"),
                             edger_kerf=form.get("edger_kerf"), edger_blades=form.get("edger_blades"),
                             edger_spacing=form.get("edger_spacing") or "")
    return Plan(shown, sizes("th"), sizes("wd"), cut, classes, problems)


# ------------------------------------------------------------------ results

def results(s: Session, job: m.GeneratorJob) -> dict | None:
    """Everything the planner shows for a finished plan job: per class the best pattern drawn on the
    class's middle log, the batch-run numbers, the board list and the saw settings; and the totals."""
    import json

    from . import reports, simview, snapshot
    if job.status != "done" or not job.result:
        return None
    res = json.loads(job.result)
    p = json.loads(job.params)
    snap = snapshot.loads(job.snapshot)
    run = s.get(m.Run, res.get("run_id")) if res.get("run_id") else None
    summaries = {ps.rp.class_no: ps for ps in reports.run_patterns(s, run.id)} if run else {}
    out = []
    for row in res["classes"]:
        c = {"no": row["no"], "min_cm": row["min_cm"], "max_cm": row["max_cm"], "logs": row["logs"],
             "problem": row["problem"], "best": row["ranked"][0] if row["ranked"] else None,
             "others": row["ranked"][1:]}
        if c["best"]:
            logs = snap.logs_in_class(row["no"])
            log = sample_class_log(logs)
            c["log"] = log
            c["diagram"] = simview.diagram(snap, p["line_name"], log, c["best"]["primary"], c["best"]["secondary"]) if log else None
            ps = summaries.get(row["no"])
            c["summary"] = ps
            if ps is not None:
                c["balance"] = reports.volume_balance(ps)
                c["mix"] = board_mix(s, ps.rp.id, ps.logs)
            cl = snap.log_class(row["no"])
            c["length_m"] = sorted(g.length_m for g in logs)[len(logs) // 2] if logs else None
            c["sample"] = row["no"] in p.get("sample_classes", [])
            c["log_price"] = cl.log_price
        out.append(c)
    done = [ps for ps in summaries.values()]
    return {"classes": out, "run": run, "total": reports.combined(done) if done else None, "params": p,
            "line": snap.line(p["line_name"]), "products": snap.products, "seconds": res["meta"]["seconds"],
            "valued": any(x.price > 0 for x in snap.products.combinations if x.valid)}


def board_mix(s: Session, run_pattern_id: int, logs: int) -> list[dict]:
    rows = s.execute(select(m.RunBoardResult.thickness, m.RunBoardResult.width, func.count(),
                            func.sum(m.RunBoardResult.dry_volume), func.avg(m.RunBoardResult.length_m))
                     .where(m.RunBoardResult.run_pattern_id == run_pattern_id)
                     .group_by(m.RunBoardResult.thickness, m.RunBoardResult.width)
                     .order_by(m.RunBoardResult.thickness.desc(), m.RunBoardResult.width.desc())).all()
    total = sum(r[3] or 0 for r in rows) or 1.0
    return [{"thickness": t, "width": w, "pieces": n, "per_log": n / logs if logs else 0.0, "dry_volume": v or 0.0,
             "share": (v or 0.0) / total, "length": ln or 0.0} for t, w, n, v, ln in rows]
