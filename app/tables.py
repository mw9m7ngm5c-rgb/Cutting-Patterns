"""Editable tables: one definition per entity drives the shared grid component (static/grid.js).

GET returns {columns, rows}; POST receives the edited rows and replaces the table: rows with an id
are updated, rows without one are added, ids that are missing are deleted. Everything is validated
before anything is written.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from engine.sawing import check_pattern

from . import models as m
from . import store


@dataclass
class Col:
    name: str
    label: str
    type: str = "float"                # float int str bool choice tags
    unit: str = ""
    readonly: bool = False
    choices: list[tuple[Any, str]] | None = None
    placeholder_flag: str | None = None   # bool column cleared when this value is edited
    required: bool = True
    min: float | None = None
    help: str = ""

    def public(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if v is not None}
        if self.choices is not None:
            d["choices"] = [[v, label] for v, label in self.choices]
        return d


@dataclass
class Entity:
    title: str
    model: type
    columns: Callable[[Session, int], list[Col]]
    query: Callable[[Session, int], list]
    to_row: Callable[[Session, int, Any], dict] | None = None
    apply: Callable[[Session, int, Any, dict], None] | None = None
    can_add: bool = True
    can_delete: bool = True
    after_save: Callable[[Session, int], None] | None = None
    note: str = ""
    sort_key: Callable[[dict], Any] | None = None


class GridError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


# ------------------------------------------------------------------ helpers

def _rows(model, order):
    def q(s: Session, ds: int):
        return list(s.scalars(select(model).where(model.dataset_id == ds).order_by(*order(model))))
    return q


def _plain_row(cols: list[Col]):
    def to_row(s, ds, obj):
        return {"id": obj.id, **{c.name: getattr(obj, c.name) for c in cols if hasattr(obj, c.name)},
                **{c.placeholder_flag: getattr(obj, c.placeholder_flag) for c in cols if c.placeholder_flag}}
    return to_row


def _plain_apply(cols: list[Col]):
    def apply(s, ds, obj, row):
        for c in cols:
            if not c.readonly and c.name in row:
                setattr(obj, c.name, row[c.name])
            if c.placeholder_flag and c.placeholder_flag in row:
                setattr(obj, c.placeholder_flag, bool(row[c.placeholder_flag]))
    return apply


def _sizes(s: Session, ds: int):
    th = {t.id: t.dry for t in s.scalars(select(m.Thickness).where(m.Thickness.dataset_id == ds))}
    wd = {w.id: w.dry for w in s.scalars(select(m.Width).where(m.Width.dataset_id == ds))}
    return th, wd


def _grade_choices(model):
    def f(s: Session, ds: int):
        return [(g.id, g.name) for g in s.scalars(select(model).where(model.dataset_id == ds).order_by(model.no))]
    return f


def _size_label(v: float) -> str:
    return f"{v:g}"


# ------------------------------------------------------------------ definitions

def _simple(title, model, cols, order, after=None, note="", can_add=True, can_delete=True):
    return Entity(title, model, lambda s, ds: cols, _rows(model, order), _plain_row(cols), _plain_apply(cols),
                  can_add, can_delete, after, note)


SIZE_COLS = [Col("dry", "Dry size", unit="mm", min=1, help="Nominal (dry) size, used in pattern notation and volumes"),
             Col("wet", "Wet size", unit="mm", min=1, help="Green target size the saws are set to")]

ENTITIES: dict[str, Entity] = {
    "thicknesses": _simple("Thicknesses", m.Thickness, SIZE_COLS, lambda M: [M.dry], store.sync_products),
    "widths": _simple("Widths", m.Width, SIZE_COLS, lambda M: [M.dry], store.sync_products),
    "length_classes": _simple("Length classes", m.LengthClass, [
        Col("name", "Name", "str"), Col("min_m", "Shortest", unit="m", min=0.1), Col("max_m", "Longest", unit="m", min=0.1),
        Col("incr_m", "Step", unit="m", min=0.0)], lambda M: [M.min_m], store.sync_products),
    "log_grades": _simple("Log grades", m.LogGrade, [Col("no", "No", "int"), Col("name", "Log grade", "str")],
                          lambda M: [M.no], store.sync_products),
    "board_grades": _simple("Board grades", m.BoardGrade, [Col("no", "No", "int"), Col("name", "Board grade", "str")],
                            lambda M: [M.no], store.sync_products),
}


# log classes: grades are a tags column, plus a read-only log count
def _class_cols(s, ds):
    return [Col("no", "Class", "int"), Col("min_diameter_cm", "SED from", unit="cm"), Col("max_diameter_cm", "SED to", unit="cm"),
            Col("min_length_m", "Length from", unit="m"), Col("max_length_m", "Length to", unit="m"),
            Col("length_incr_m", "Length step", unit="m"),
            Col("min_taper", "Taper from", unit="mm/m"), Col("max_taper", "Taper to", unit="mm/m"),
            Col("min_sweep", "Sweep from", unit="mm/m"), Col("max_sweep", "Sweep to", unit="mm/m"),
            Col("min_ovality", "Ovality from"), Col("max_ovality", "Ovality to"),
            Col("min_defect_core", "Core from", unit="% SED"), Col("max_defect_core", "Core to", unit="% SED"),
            Col("log_price", "Log price", unit="R/m³", placeholder_flag="log_price_placeholder"),
            Col("grades", "Grades", "tags", required=False, choices=_grade_choices(m.LogGrade)(s, ds),
                help="Leave empty to accept every grade"),
            Col("log_count", "Logs", "int", readonly=True)]


def _class_row(s, ds, c):
    cols = _class_cols(s, ds)
    d = {"id": c.id, **{k.name: getattr(c, k.name) for k in cols if k.type != "tags" and k.name != "log_count"},
         "log_price_placeholder": c.log_price_placeholder, "grades": [g.id for g in c.grades]}
    return d


def _class_apply(s, ds, c, row):
    for k in _class_cols(s, ds):
        if k.readonly or k.type == "tags" or k.name not in row:
            continue
        setattr(c, k.name, row[k.name])
    if "log_price_placeholder" in row:
        c.log_price_placeholder = bool(row["log_price_placeholder"])
    ids = set(row.get("grades") or [])
    c.grades = [g for g in s.scalars(select(m.LogGrade).where(m.LogGrade.dataset_id == ds)) if g.id in ids]


ENTITIES["log_classes"] = Entity("Log classes", m.LogClass, _class_cols, _rows(m.LogClass, lambda M: [M.no]),
                                 _class_row, _class_apply,
                                 note="A log belongs to the first class whose limits it meets.")


def _log_cols(s, ds):
    return [Col("log_no", "Log", "int"), Col("sed_cm", "SED", unit="cm", min=1),
            Col("length_m", "Length", unit="m", min=0.1), Col("taper", "Taper", unit="mm/m", min=0),
            Col("sweep_mm", "Sweep", unit="mm total", min=0, help="Total deviation of the centreline, not mm/m"),
            Col("ovality", "Ovality", min=0.05), Col("defect_core_cm", "Defect core", unit="cm", min=0,
                                                     help="Core diameter in cm, not % of SED"),
            Col("log_grade_id", "Grade", "choice", choices=_grade_choices(m.LogGrade)(s, ds), required=False),
            Col("class_no", "Class", "int", readonly=True)]


def _log_row(s, ds, g):
    return {"id": g.id, "log_no": g.log_no, "sed_cm": g.sed_cm, "length_m": g.length_m, "taper": g.taper,
            "sweep_mm": g.sweep_mm, "ovality": g.ovality, "defect_core_cm": g.defect_core_cm,
            "log_grade_id": g.log_grade_id}


ENTITIES["logs"] = Entity("Logs", m.Log, _log_cols, _rows(m.Log, lambda M: [M.log_no]), _log_row,
                          lambda s, ds, o, r: _plain_apply(_log_cols(s, ds))(s, ds, o, r),
                          note="Paste straight from Excel: copy the cells, click the first cell to fill, press Ctrl+V (⌘V).")


# products keyed by size: these rows come from sync_products, so no adding or deleting
def _keyed(title, model, value_cols: list[Col], extra_keys=(), note=""):
    def cols(s, ds):
        keys = [Col("thickness", "Thickness", unit="mm", readonly=True), Col("width", "Width", unit="mm", readonly=True)]
        for name, label, choices in extra_keys:
            keys.append(Col(name, label, "choice", readonly=True, choices=choices(s, ds)))
        return keys + value_cols

    def query(s, ds):
        th, wd = _sizes(s, ds)
        rows = list(s.scalars(select(model).where(model.dataset_id == ds)))
        return sorted(rows, key=lambda r: (th.get(r.thickness_id, 0), wd.get(r.width_id, 0),
                                           *[getattr(r, k) for k, _, _ in extra_keys]))

    def to_row(s, ds, r):
        th, wd = _sizes(s, ds)
        d = {"id": r.id, "thickness": th.get(r.thickness_id), "width": wd.get(r.width_id)}
        for k, _, _ in extra_keys:
            d[k] = getattr(r, k)
        for c in value_cols:
            d[c.name] = getattr(r, c.name)
            if c.placeholder_flag:
                d[c.placeholder_flag] = getattr(r, c.placeholder_flag)
        return d

    return Entity(title, model, cols, query, to_row, _plain_apply(value_cols), False, False, None, note)


def _length_class_choices(s, ds):
    return [(c.id, c.name) for c in s.scalars(select(m.LengthClass).where(m.LengthClass.dataset_id == ds))]


ENTITIES["combinations"] = _keyed(
    "Products and prices", m.Combination,
    [Col("valid", "Product", "bool", help="Untick sizes the mill does not sell"),
     Col("price", "Price", unit="R/m³ dry", min=0, placeholder_flag="price_placeholder")],
    [("length_class_id", "Length class", _length_class_choices),
     ("board_grade_id", "Board grade", _grade_choices(m.BoardGrade))],
    note="One row per thickness × width × length class × board grade. Board value = dry volume × price.")

ENTITIES["wane"] = _keyed(
    "Wane rules", m.WaneRule,
    [Col("thickness_pct", "Thickness wane", unit="% of thickness", min=0),
     Col("width_pct", "Width wane", unit="% of width", min=0),
     Col("length_wane", "Length wane", unit="% of length", min=0),
     Col("length_wane_type", "Length wane type", "choice", choices=list(store.LENGTH_WANE_TYPES.items()))],
    note="How the three numbers combine is set out in docs/ASSUMPTIONS.md (A-07, A-08). "
         "0 / 0 means no wane allowed on that product.")

ENTITIES["grade_outputs"] = _keyed(
    "Grade outputs", m.GradeOutput,
    [Col("p_zero", "No core", unit="%", min=0), Col("p_fifty", "1-50 % core", unit="%", min=0),
     Col("p_ninety_nine", "51-99 % core", unit="%", min=0), Col("p_hundred", "All core", unit="%", min=0)],
    [("log_grade_id", "Log grade", _grade_choices(m.LogGrade)),
     ("board_grade_id", "Board grade", _grade_choices(m.BoardGrade))],
    note="Chance (%) of each board grade by how much of the board's cross-section is defect core. "
         "Used from Phase 4; with one board grade every board gets it.")


def _centre_cols(s, ds):
    th = [(t.id, _size_label(t.dry)) for t in s.scalars(select(m.Thickness).where(m.Thickness.dataset_id == ds).order_by(m.Thickness.dry))]
    wd = [(w.id, _size_label(w.dry)) for w in s.scalars(select(m.Width).where(m.Width.dataset_id == ds).order_by(m.Width.dry))]
    return [Col("thickness_id", "Thickness", "choice", unit="mm", choices=th),
            Col("width_id", "Width", "choice", unit="mm", choices=wd)]


ENTITIES["centre_boards"] = Entity(
    "Centre boards", m.CentreBoard, _centre_cols, _rows(m.CentreBoard, lambda M: [M.id]),
    lambda s, ds, r: {"id": r.id, "thickness_id": r.thickness_id, "width_id": r.width_id},
    lambda s, ds, o, r: _plain_apply(_centre_cols(s, ds))(s, ds, o, r),
    note="Sizes cut only as full-width boards from the cant, never at the edger.")


def _pattern_cols(s, ds):
    lines = [(ln.id, ln.name) for ln in s.scalars(select(m.ProductionLine).where(m.ProductionLine.dataset_id == ds).order_by(m.ProductionLine.no))]
    classes = [(c.id, f"{c.no}: {c.min_diameter_cm:g}-{c.max_diameter_cm:g} cm")
               for c in s.scalars(select(m.LogClass).where(m.LogClass.dataset_id == ds).order_by(m.LogClass.no))]
    return [Col("line_id", "Line", "choice", choices=lines), Col("log_class_id", "Log class", "choice", choices=classes),
            Col("pattern_no", "Pattern", "int"), Col("primary", "Primary", "str"), Col("secondary", "Secondary", "str", required=False),
            Col("source", "Source", "str", readonly=True), Col("check", "Check", "str", readonly=True)]


def _pattern_row(s, ds, p):
    return {"id": p.id, "line_id": p.line_id, "log_class_id": p.log_class_id, "pattern_no": p.pattern_no,
            "primary": p.primary, "secondary": p.secondary, "source": p.source}


ENTITIES["patterns"] = Entity("Sawing patterns", m.SawPattern, _pattern_cols,
                              _rows(m.SawPattern, lambda M: [M.line_id, M.log_class_id, M.pattern_no]), _pattern_row,
                              lambda s, ds, o, r: _plain_apply(_pattern_cols(s, ds))(s, ds, o, r))


# ------------------------------------------------------------------ computed columns

def _computed(s: Session, ds: int, name: str, rows: list[dict]) -> None:
    if name == "logs" or name == "log_classes":
        e = store.engine_dataset(s, ds)
        if name == "logs":
            by_no = {g.no: g for g in e.logs}
            for r in rows:
                g = by_no.get(r["log_no"])
                r["class_no"] = store.class_of(g, e.log_classes) if g else None
        else:
            counts: dict[int, int] = {}
            for g in e.logs:
                no = store.class_of(g, e.log_classes)
                if no is not None:
                    counts[no] = counts.get(no, 0) + 1
            for r in rows:
                r["log_count"] = counts.get(r["no"], 0)
    elif name == "patterns":
        e = store.engine_dataset(s, ds)
        lines = {ln.id: ln.name for ln in s.scalars(select(m.ProductionLine).where(m.ProductionLine.dataset_id == ds))}
        for r in rows:
            try:
                problems = check_pattern(r["primary"], r["secondary"] or "", e.products, e.line(lines[r["line_id"]]))
            except (KeyError, StopIteration):
                problems = ["production line not found"]
            r["check"] = "; ".join(problems) if problems else "OK"


# ------------------------------------------------------------------ read and write

def read(s: Session, ds: int, name: str) -> dict:
    ent = ENTITIES[name]
    cols = ent.columns(s, ds)
    rows = [ent.to_row(s, ds, o) for o in ent.query(s, ds)]
    _computed(s, ds, name, rows)
    return {"name": name, "title": ent.title, "note": ent.note, "can_add": ent.can_add, "can_delete": ent.can_delete,
            "columns": [c.public() for c in cols], "rows": rows}


def _coerce(c: Col, v, rowno: int) -> Any:
    label = f"row {rowno}, {c.label}"
    if v is None or (isinstance(v, str) and v.strip() == ""):
        if c.type == "bool":
            return False
        if c.type == "tags":
            return []
        if c.required and c.type != "choice":
            raise ValueError(f"{label}: a value is needed")
        if c.type == "str":
            return ""
        if c.required:
            raise ValueError(f"{label}: choose a value")
        return None
    try:
        if c.type == "float":
            out = float(str(v).replace(",", ".").replace(" ", ""))
        elif c.type == "int":
            f = float(str(v).replace(" ", ""))
            if f != int(f):
                raise ValueError
            out = int(f)
        elif c.type == "bool":
            out = v if isinstance(v, bool) else str(v).strip().lower() in {"1", "true", "yes", "y", "x", "on"}
        elif c.type == "choice":
            allowed = {str(k): k for k, _ in c.choices or []}
            by_label = {str(lbl).lower(): k for k, lbl in c.choices or []}
            if str(v) in allowed:
                out = allowed[str(v)]
            elif str(v).strip().lower() in by_label:
                out = by_label[str(v).strip().lower()]
            else:
                raise ValueError
        elif c.type == "tags":
            allowed = {k for k, _ in c.choices or []}
            out = [int(x) for x in v]
            if any(x not in allowed for x in out):
                raise ValueError
        else:
            out = str(v).strip()
    except (TypeError, ValueError):
        kind = {"float": "number", "int": "whole number", "choice": "choice", "tags": "choice"}.get(c.type, "value")
        raise ValueError(f"{label}: {v!r} is not a valid {kind}") from None
    if c.min is not None and isinstance(out, (int, float)) and not isinstance(out, bool) and out < c.min:
        raise ValueError(f"{label}: must be at least {c.min:g}")
    return out


def write(s: Session, ds: int, name: str, rows: list[dict]) -> dict:
    ent = ENTITIES[name]
    cols = ent.columns(s, ds)
    existing = {o.id: o for o in ent.query(s, ds)}
    errors: list[str] = []
    clean: list[dict] = []
    for i, row in enumerate(rows, 1):
        out = {"id": row.get("id")}
        for c in cols:
            if c.readonly:
                continue
            try:
                out[c.name] = _coerce(c, row.get(c.name), i)
            except ValueError as e:
                errors.append(str(e))
            if c.placeholder_flag:
                out[c.placeholder_flag] = bool(row.get(c.placeholder_flag, False))
        if out["id"] is not None and out["id"] not in existing:
            errors.append(f"row {i}: no longer exists; reload the page")
        if out["id"] is None and not ent.can_add:
            errors.append(f"row {i}: rows cannot be added to this table")
        clean.append(out)
    if name == "length_classes":
        for i, r in enumerate(clean, 1):
            if "min_m" in r and "max_m" in r and r["min_m"] > r["max_m"]:
                errors.append(f"row {i}: shortest is longer than longest")
    if errors:
        raise GridError(errors)
    keep = {r["id"] for r in clean if r["id"] is not None}
    gone = [o for oid, o in existing.items() if oid not in keep]
    if gone and not ent.can_delete:
        raise GridError(["rows cannot be deleted from this table"])
    try:
        for o in gone:
            s.delete(o)
        s.flush()
        with s.no_autoflush:       # apply() may query choices; a half-filled new row must not be written yet
            for r in clean:
                obj = existing.get(r["id"]) if r["id"] is not None else None
                if obj is None:
                    obj = ent.model(dataset_id=ds)
                    s.add(obj)
                ent.apply(s, ds, obj, r)
        s.flush()
        if ent.after_save:
            ent.after_save(s, ds)
        s.commit()
    except IntegrityError as e:
        s.rollback()
        if "UNIQUE" in str(e.orig):
            raise GridError(["two rows are the same (each size, name or product may appear only once)"]) from None
        raise GridError([f"could not save: {e.orig}"]) from None
    return read(s, ds, name)
