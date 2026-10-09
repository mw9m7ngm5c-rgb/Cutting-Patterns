"""Between the database and the engine: build engine objects from a dataset, create new datasets,
import Simsaw .mdb files, duplicate datasets, keep the product tables complete."""
from __future__ import annotations

import datetime as dt
import pathlib

from sqlalchemy import delete, inspect, select
from sqlalchemy.orm import Session

from engine import model as em
from importers import simsaw

from . import models as m
from . import snapshot

# ------------------------------------------------------------------ labels used across the app

SAW_TYPES = {0: "Cant / live sawing", 1: "Cant / live sawing, grouped", 2: "Chipper-profiler", 3: "Chipper-profiler, grouped"}
CANT_GUIDING = {0: "None (straight cuts)", 1: "Half taper (follow the centreline)", 2: "Full taper (follow the top face)"}
EDGING_OBJECTIVES = {0: "Maximum volume", 1: "Maximum length", 2: "Maximum value"}
NOMINAL_DIAMETER = {0: "Odd number (18.0-19.9 → 19)", 1: "Even number (19.0-20.9 → 20)", 2: "Whole number (18.5-19.4 → 19)"}
DISTRIBUTIONS = {0: "Uniform", 2: "Normal, 95 % within limits", 1: "Normal, 65 % within limits"}
LENGTH_WANE_TYPES = {0: "% of board length"}
PRIMARY_MACHINES = ["", "Frame saw", "Band saw", "Circular saw", "Chipper canter"]
SECONDARY_MACHINES = ["", "Frame saw", "Circular gang rip", "Band saw"]


# ------------------------------------------------------------------ database -> engine

def _grade_names(s: Session, model, ds_id: int) -> dict[int, str]:
    return {g.id: g.name for g in s.scalars(select(model).where(model.dataset_id == ds_id).order_by(model.no))}


def engine_products(s: Session, ds_id: int) -> em.Products:
    th = {t.id: t for t in s.scalars(select(m.Thickness).where(m.Thickness.dataset_id == ds_id))}
    wd = {w.id: w for w in s.scalars(select(m.Width).where(m.Width.dataset_id == ds_id))}
    lc = {c.id: c for c in s.scalars(select(m.LengthClass).where(m.LengthClass.dataset_id == ds_id))}
    bg = _grade_names(s, m.BoardGrade, ds_id)
    combos = [em.Combination(th[c.thickness_id].dry, wd[c.width_id].dry, lc[c.length_class_id].name,
                             bg.get(c.board_grade_id, "All board grades"), bool(c.valid), float(c.price))
              for c in s.scalars(select(m.Combination).where(m.Combination.dataset_id == ds_id))]
    wane = {(th[r.thickness_id].dry, wd[r.width_id].dry):
            em.WaneRule(r.thickness_pct, r.width_pct, r.length_wane, r.length_wane_type)
            for r in s.scalars(select(m.WaneRule).where(m.WaneRule.dataset_id == ds_id))}
    centre = {(th[r.thickness_id].dry, wd[r.width_id].dry)
              for r in s.scalars(select(m.CentreBoard).where(m.CentreBoard.dataset_id == ds_id))}
    lg = _grade_names(s, m.LogGrade, ds_id)
    outputs = {(th[r.thickness_id].dry, wd[r.width_id].dry, lg[r.log_grade_id], bg[r.board_grade_id]):
               (r.p_zero, r.p_fifty, r.p_ninety_nine, r.p_hundred)
               for r in s.scalars(select(m.GradeOutput).where(m.GradeOutput.dataset_id == ds_id))
               if r.log_grade_id in lg and r.board_grade_id in bg}
    return em.Products(
        sorted((em.Size(t.dry, t.wet) for t in th.values()), key=lambda z: z.dry),
        sorted((em.Size(w.dry, w.wet) for w in wd.values()), key=lambda z: z.dry),
        [em.LengthClass(c.name, c.min_m, c.max_m, c.incr_m) for c in sorted(lc.values(), key=lambda c: c.min_m)],
        combos, list(bg.values()) or ["All board grades"], wane, centre, outputs)


def engine_line(ln: m.ProductionLine) -> em.ProductionLine:
    return em.ProductionLine(
        name=ln.name, saw_type=em.SawType(ln.saw_type),
        primary_machine=ln.primary_machine or "", secondary_machine=ln.secondary_machine or "",
        primary_kerf=ln.primary_kerf, primary_outside_kerf=ln.primary_outside_kerf,
        primary_outside_blades=ln.primary_outside_blades,
        secondary_kerf=ln.secondary_kerf, secondary_outside_kerf=ln.secondary_outside_kerf,
        secondary_outside_blades=ln.secondary_outside_blades,
        primary_resaw=ln.primary_resaw, primary_resaw_kerf=ln.primary_resaw_kerf,
        secondary_resaw=ln.secondary_resaw, secondary_resaw_kerf=ln.secondary_resaw_kerf,
        cant_guiding=em.CantGuiding(ln.cant_guiding), max_sweep=ln.max_sweep,
        log_rotation_deg=ln.log_rotation_deg, log_misalignment_mm=ln.log_misalignment_mm,
        primary_offset_mm=ln.primary_offset_mm, cant_misalignment_mm=ln.cant_misalignment_mm,
        secondary_offset_mm=ln.secondary_offset_mm, edging_objective=em.EdgingObjective(ln.edging_objective),
        edger_blades=ln.edger_blades, edger_kerf=ln.edger_kerf, second_board_width=ln.second_board_width,
        max_boards_per_flitch=ln.max_boards_per_flitch, edger_spacing=parse_spacing(ln.edger_spacing or ""))


def parse_spacing(text: str) -> tuple[float, ...]:
    """'160 107' or '160; 107' -> (160.0, 107.0). Raises ValueError on anything that is not a positive number."""
    parts = [x for x in text.replace(";", " ").replace(",", " ").split() if x]
    out = tuple(float(x) for x in parts)
    if any(v <= 0 for v in out):
        raise ValueError("blade distances must be above 0")
    return out


def engine_class(c: m.LogClass) -> em.LogClass:
    return em.LogClass(c.no, c.min_diameter_cm, c.max_diameter_cm, c.min_length_m, c.max_length_m, c.length_incr_m,
                       c.min_taper, c.max_taper, c.min_sweep, c.max_sweep, c.min_ovality, c.max_ovality,
                       c.min_defect_core, c.max_defect_core, c.log_price, tuple(g.name for g in c.grades))


def engine_settings(st: m.DatasetSettings) -> em.Settings:
    return em.Settings(st.use_nominal_diameter, em.NominalDiameter(st.nominal_diameter), st.use_nominal_length,
                       st.nominal_length_incr_m, st.use_nominal_taper, st.nominal_taper_mm_per_m,
                       st.disc_separation_cm, st.points_per_disc, st.discretised, st.seed,
                       st.chip_price, st.sawdust_price, st.pct_fines, bool(st.arris_small_end),
                       em.Variation(st.diameter_variation, st.taper_variation, st.sweep_variation,
                                    st.ovality_variation) if st.real_logs else None)


def engine_dataset(s: Session, ds_id: int) -> simsaw.Dataset:
    ds = s.get(m.Dataset, ds_id)
    lg = _grade_names(s, m.LogGrade, ds_id)
    classes = list(s.scalars(select(m.LogClass).where(m.LogClass.dataset_id == ds_id).order_by(m.LogClass.no)))
    lines = list(s.scalars(select(m.ProductionLine).where(m.ProductionLine.dataset_id == ds_id).order_by(m.ProductionLine.no)))
    logs = [em.Log(g.log_no, g.sed_cm, g.length_m, g.taper, g.sweep_mm, g.ovality, g.defect_core_cm,
                   lg.get(g.log_grade_id, "All log grades"))
            for g in s.scalars(select(m.Log).where(m.Log.dataset_id == ds_id).order_by(m.Log.log_no))]
    cls_no = {c.id: c.no for c in classes}
    line_name = {ln.id: ln.name for ln in lines}
    patterns = [simsaw.PatternDef(p.id, line_name.get(p.line_id, ""), cls_no.get(p.log_class_id, 0), p.pattern_no,
                                  p.primary, p.secondary)
                for p in s.scalars(select(m.SawPattern).where(m.SawPattern.dataset_id == ds_id))]
    patterns.sort(key=lambda p: (p.line_name, p.log_class_no, p.pattern_no))
    return simsaw.Dataset(engine_products(s, ds_id), [engine_class(c) for c in classes], logs,
                          [engine_line(ln) for ln in lines], patterns, engine_settings(settings_for(s, ds_id)),
                          ds.name if ds else "")


def settings_for(s: Session, ds_id: int) -> m.DatasetSettings:
    st = s.get(m.DatasetSettings, ds_id)
    if st is None:
        st = m.DatasetSettings(dataset_id=ds_id)
        s.add(st)
        s.flush()
    return st


def class_of(log: em.Log, classes: list[em.LogClass]) -> int | None:
    """Number of the first class the log falls in, or None."""
    for c in classes:
        if c.contains(log):
            return c.no
    return None


# ------------------------------------------------------------------ keeping product tables complete

def _default_wane(thickness_dry: float) -> tuple[float, float, float]:
    """Owner's default (7 Oct 2026): no wane on structural thicknesses (38 mm and up);
    10 % of thickness and 30 % of width over the whole length on thinner boards."""
    return (0.0, 0.0, 0.0) if thickness_dry >= 38 else (10.0, 30.0, 100.0)


def sync_products(s: Session, ds_id: int) -> None:
    """Make sure every thickness x width (x length class x grade) has a combination, a wane rule and
    grade outputs. New combinations are switched on at R0 and marked as placeholder prices."""
    th = list(s.scalars(select(m.Thickness).where(m.Thickness.dataset_id == ds_id)))
    wd = list(s.scalars(select(m.Width).where(m.Width.dataset_id == ds_id)))
    lcs = list(s.scalars(select(m.LengthClass).where(m.LengthClass.dataset_id == ds_id)))
    bgs = list(s.scalars(select(m.BoardGrade).where(m.BoardGrade.dataset_id == ds_id)))
    lgs = list(s.scalars(select(m.LogGrade).where(m.LogGrade.dataset_id == ds_id)))
    if not bgs:
        bgs = [m.BoardGrade(dataset_id=ds_id, no=1, name="All board grades")]
        s.add_all(bgs)
    if not lgs:
        lgs = [m.LogGrade(dataset_id=ds_id, no=1, name="All log grades")]
        s.add_all(lgs)
    s.flush()
    have_c = {(c.thickness_id, c.width_id, c.length_class_id, c.board_grade_id)
              for c in s.scalars(select(m.Combination).where(m.Combination.dataset_id == ds_id))}
    have_w = {(r.thickness_id, r.width_id) for r in s.scalars(select(m.WaneRule).where(m.WaneRule.dataset_id == ds_id))}
    have_g = {(r.thickness_id, r.width_id, r.log_grade_id, r.board_grade_id)
              for r in s.scalars(select(m.GradeOutput).where(m.GradeOutput.dataset_id == ds_id))}
    for t in th:
        for w in wd:
            for lc in lcs:
                for bg in bgs:
                    if (t.id, w.id, lc.id, bg.id) not in have_c:
                        s.add(m.Combination(dataset_id=ds_id, thickness_id=t.id, width_id=w.id, length_class_id=lc.id,
                                            board_grade_id=bg.id, valid=True, price=0.0, price_placeholder=True))
            if (t.id, w.id) not in have_w:
                tp, wp, lw = _default_wane(t.dry)
                s.add(m.WaneRule(dataset_id=ds_id, thickness_id=t.id, width_id=w.id, thickness_pct=tp,
                                 width_pct=wp, length_wane=lw, length_wane_type=0))
            for lg in lgs:
                for bg in bgs:
                    if (t.id, w.id, lg.id, bg.id) not in have_g:
                        s.add(m.GradeOutput(dataset_id=ds_id, thickness_id=t.id, width_id=w.id,
                                            log_grade_id=lg.id, board_grade_id=bg.id))
    s.flush()


# ------------------------------------------------------------------ new dataset

# Defaults taken from the Ngomi dataset (ngomi_1.mdb). Prices, log prices and kerfs are
# placeholders, flagged as such in the database and on screen, until the mill supplies its own.
NGOMI_THICKNESSES = [(19, 21), (25, 27), (38, 41), (50, 54)]
NGOMI_WIDTHS = [(76, 81), (102, 107), (114, 120), (152, 160)]
NGOMI_INVALID = {(25, 114), (50, 102), (50, 114)}
NGOMI_CLASSES = [(18.0, 21.9), (22.0, 25.9), (26.0, 29.9), (30.0, 35.9), (36.0, 41.9)]
PLACEHOLDER_PRICE = 4000.0
PLACEHOLDER_LOG_PRICE = 120.0


def create_empty_dataset(s: Session, name: str) -> m.Dataset:
    """A dataset with nothing but the fixed parts every dataset needs (one log grade, one board grade,
    one length range, default settings): the mill types in its own sizes, classes, logs and machines."""
    ds = m.Dataset(name=name, source="New (empty)", notes="")
    s.add(ds)
    s.flush()
    _fixed_parts(s, ds.id)
    s.add(m.DatasetSettings(dataset_id=ds.id))
    s.add(m.LogGenerator(dataset_id=ds.id))
    s.flush()
    return ds


def _fixed_parts(s: Session, i: int) -> None:
    s.add(m.LogGrade(dataset_id=i, no=1, name="All log grades"))
    s.add(m.BoardGrade(dataset_id=i, no=1, name="All board grades"))
    s.add(m.LengthClass(dataset_id=i, name="All", min_m=0.9, max_m=6.6, incr_m=0.3))


def create_default_dataset(s: Session, name: str) -> m.Dataset:
    ds = m.Dataset(name=name, source="New (example values)",
                   notes="Started from example sizes, log classes, a production line and settings. "
                         "Board prices, log prices and kerfs are placeholders until replaced.")
    s.add(ds)
    s.flush()
    i = ds.id
    _fixed_parts(s, i)
    s.add_all([m.Thickness(dataset_id=i, dry=d, wet=w) for d, w in NGOMI_THICKNESSES])
    s.add_all([m.Width(dataset_id=i, dry=d, wet=w) for d, w in NGOMI_WIDTHS])
    s.flush()
    sync_products(s, i)
    th = {t.id: t.dry for t in s.scalars(select(m.Thickness).where(m.Thickness.dataset_id == i))}
    wd = {w.id: w.dry for w in s.scalars(select(m.Width).where(m.Width.dataset_id == i))}
    for c in s.scalars(select(m.Combination).where(m.Combination.dataset_id == i)):
        c.valid = (th[c.thickness_id], wd[c.width_id]) not in NGOMI_INVALID
        c.price, c.price_placeholder = PLACEHOLDER_PRICE, True
    for n, (lo, hi) in enumerate(NGOMI_CLASSES, 1):
        s.add(m.LogClass(dataset_id=i, no=n, min_diameter_cm=lo, max_diameter_cm=hi, min_length_m=1.8, max_length_m=6.6,
                         length_incr_m=0.3, min_taper=0, max_taper=25, min_sweep=0, max_sweep=40, min_ovality=0.5,
                         max_ovality=1.5, min_defect_core=0, max_defect_core=100,
                         log_price=PLACEHOLDER_LOG_PRICE, log_price_placeholder=True))
    s.add(m.ProductionLine(dataset_id=i, no=1, name="Line 1", primary_kerf=3.0, secondary_kerf=3.0,
                           primary_resaw=True, primary_resaw_kerf=5.0, secondary_resaw=True, secondary_resaw_kerf=5.0,
                           edger_blades=3, edger_kerf=5.0, second_board_width="Best", kerfs_placeholder=True))
    s.add(m.DatasetSettings(dataset_id=i))
    s.add(m.LogGenerator(dataset_id=i))
    s.flush()
    return ds


# ------------------------------------------------------------------ Simsaw import

def _excel_date(serial) -> dt.datetime:
    try:
        return (dt.datetime(1899, 12, 30) + dt.timedelta(days=float(serial))).replace(microsecond=0)
    except (TypeError, ValueError):
        return dt.datetime.now().replace(microsecond=0)


def import_simsaw(s: Session, path, name: str | None = None, include_runs: bool = True) -> m.Dataset:
    """Import a Simsaw 6 dataset (.mdb file or a directory of exported JSON tables)."""
    src = simsaw.Source(path)
    inp = simsaw.load_inputs(src)
    ds = m.Dataset(name=name or pathlib.Path(path).stem, source=pathlib.Path(path).name,
                   notes="Imported from Simsaw 6.")
    s.add(ds)
    s.flush()
    i = ds.id
    r = simsaw._r

    # grades
    lg_by_uid, lg_by_name = {}, {}
    for row in sorted(src.table("log_grades"), key=lambda x: x.get("grade_no") or 0) or [{"grade_uid": None, "grade_no": 1, "grade": "All log grades"}]:
        g = m.LogGrade(dataset_id=i, no=int(row.get("grade_no") or 1), name=row["grade"] or "All log grades")
        s.add(g)
        s.flush()
        lg_by_uid[row["grade_uid"]], lg_by_name[g.name] = g, g
    bg_by_uid, bg_by_name = {}, {}
    for row in sorted(src.table("board_grades"), key=lambda x: x.get("grade_no") or 0) or [{"grade_uid": None, "grade_no": 1, "grade": "All board grades"}]:
        g = m.BoardGrade(dataset_id=i, no=int(row.get("grade_no") or 1), name=row["grade"] or "All board grades")
        s.add(g)
        s.flush()
        bg_by_uid[row["grade_uid"]], bg_by_name[g.name] = g, g

    # products
    p = inp.products
    th = {t.dry: m.Thickness(dataset_id=i, dry=t.dry, wet=t.wet) for t in p.thicknesses}
    wd = {w.dry: m.Width(dataset_id=i, dry=w.dry, wet=w.wet) for w in p.widths}
    lc = {c.name: m.LengthClass(dataset_id=i, name=c.name, min_m=c.min_m, max_m=c.max_m, incr_m=c.incr_m)
          for c in p.length_classes}
    s.add_all([*th.values(), *wd.values(), *lc.values()])
    s.flush()
    for c in p.combinations:
        g = bg_by_name.get(c.grade) or next(iter(bg_by_name.values()))
        s.add(m.Combination(dataset_id=i, thickness_id=th[c.thickness].id, width_id=wd[c.width].id,
                            length_class_id=lc[c.length_class].id, board_grade_id=g.id, valid=c.valid, price=c.price))
    for (t, w), rule in p.wane.items():
        s.add(m.WaneRule(dataset_id=i, thickness_id=th[t].id, width_id=wd[w].id, thickness_pct=rule.thickness_pct,
                         width_pct=rule.width_pct, length_wane=rule.length_wane, length_wane_type=rule.length_wane_type))
    for t, w in p.centre_boards:
        s.add(m.CentreBoard(dataset_id=i, thickness_id=th[t].id, width_id=wd[w].id))
    raw_th = {row["thickness_uid"]: r(row["dry_thickness"]) for row in src.table("thicknesses")}
    raw_wd = {row["width_uid"]: r(row["dry_width"]) for row in src.table("widths")}
    for row in src.table("grade_outputs"):
        t, w = raw_th.get(row["thickness_uid"]), raw_wd.get(row["width_uid"])
        if t in th and w in wd and row["log_grade_uid"] in lg_by_uid and row["board_grade_uid"] in bg_by_uid:
            s.add(m.GradeOutput(dataset_id=i, thickness_id=th[t].id, width_id=wd[w].id,
                                log_grade_id=lg_by_uid[row["log_grade_uid"]].id,
                                board_grade_id=bg_by_uid[row["board_grade_uid"]].id,
                                p_zero=row["zero_percent"], p_fifty=row["fifty_percent"],
                                p_ninety_nine=row["nine_nine_percent"], p_hundred=row["one_hundred_percent"]))

    # classes and their grades
    cls = {}
    for c in inp.log_classes:
        row = m.LogClass(dataset_id=i, no=c.no, min_diameter_cm=c.min_diameter_cm, max_diameter_cm=c.max_diameter_cm,
                         min_length_m=c.min_length_m, max_length_m=c.max_length_m, length_incr_m=c.length_incr_m,
                         min_taper=c.min_taper, max_taper=c.max_taper, min_sweep=c.min_sweep, max_sweep=c.max_sweep,
                         min_ovality=c.min_ovality, max_ovality=c.max_ovality, min_defect_core=c.min_defect_core,
                         max_defect_core=c.max_defect_core, log_price=c.log_price)
        s.add(row)
        cls[c.no] = row
    s.flush()
    class_no_by_uid = {row["log_class_uid"]: int(str(row["log_class_no"]).strip()) for row in src.table("log_classes")}
    for row in src.table("log_class_grades"):
        c = cls.get(class_no_by_uid.get(row["log_class_uid"]))
        g = lg_by_uid.get(row["grade_uid"])
        if c is not None and g is not None:
            s.add(m.LogClassGrade(log_class_id=c.id, log_grade_id=g.id))

    # logs
    s.add_all([m.Log(dataset_id=i, log_no=g.no, sed_cm=g.sed_cm, length_m=g.length_m, taper=g.taper_mm_per_m,
                     sweep_mm=g.sweep_mm, ovality=g.ovality, defect_core_cm=g.defect_core_cm,
                     log_grade_id=(lg_by_name.get(g.grade) or next(iter(lg_by_name.values()))).id)
               for g in inp.logs])

    # generator
    gen = (src.table("generators") or [None])[0]
    if gen:
        s.add(m.LogGenerator(
            dataset_id=i, no_of_logs=int(gen["no_of_logs"]), fixed_seed=bool(gen["reset_seed"]), seed=int(gen["seed"]),
            min_diameter=r(gen["min_diameter"]), max_diameter=r(gen["max_diameter"]), diameter_distr=int(gen["diameter_distr"]),
            min_length=r(gen["min_length"]), max_length=r(gen["max_length"]), length_incr=r(gen["length_incr"]),
            length_distr=int(gen["length_distr"]), min_taper=r(gen["min_taper"]), max_taper=r(gen["max_taper"]),
            taper_distr=int(gen["taper_distr"]), min_sweep=r(gen["min_sweep"]), max_sweep=r(gen["max_sweep"]),
            sweep_distr=int(gen["sweep_distr"]), min_ovality=r(gen["min_ovality"]), max_ovality=r(gen["max_ovality"]),
            ovality_distr=int(gen["ovality_distr"]), min_defect_core=r(gen["min_defect_core"]),
            max_defect_core=r(gen["max_defect_core"]), defect_core_distr=int(gen["defect_core_distr"]),
            log_grade_id=lg_by_uid[gen["log_grade_uid"]].id if gen.get("log_grade_uid") in lg_by_uid else None))
    else:
        s.add(m.LogGenerator(dataset_id=i))

    # lines and patterns
    lines = {}
    for n, ln in enumerate(inp.lines, 1):
        row = m.ProductionLine(dataset_id=i, no=n, **_line_fields(ln))
        s.add(row)
        lines[ln.name] = row
    s.flush()
    for pd in inp.patterns:
        if pd.line_name in lines and pd.log_class_no in cls:
            s.add(m.SawPattern(dataset_id=i, line_id=lines[pd.line_name].id, log_class_id=cls[pd.log_class_no].id,
                               pattern_no=pd.pattern_no, primary=pd.primary, secondary=pd.secondary, source="imported"))

    st = inp.settings
    s.add(m.DatasetSettings(dataset_id=i, use_nominal_diameter=st.use_nominal_diameter,
                            nominal_diameter=int(st.nominal_diameter), use_nominal_length=st.use_nominal_length,
                            nominal_length_incr_m=st.nominal_length_incr_m, use_nominal_taper=st.use_nominal_taper,
                            nominal_taper_mm_per_m=st.nominal_taper_mm_per_m, disc_separation_cm=st.disc_separation_cm,
                            points_per_disc=st.points_per_disc, discretised=st.discretised, seed=st.seed,
                            chip_price=st.chip_price, sawdust_price=st.sawdust_price, pct_fines=st.pct_fines,
                            arris_small_end=st.arris_small_end,
                            # Simsaw keeps real-log variation with the log generator (units: A-55)
                            real_logs=bool(gen and gen.get("real_logs")),
                            diameter_variation=float(gen.get("diameter_variation") or 0) if gen else 0.0,
                            taper_variation=float(gen.get("taper_variation") or 0) if gen else 0.0,
                            sweep_variation=float(gen.get("sweep_variation") or 0) if gen else 0.0,
                            ovality_variation=float(gen.get("ovality_variation") or 0) if gen else 0.0))
    s.flush()
    sync_products(s, i)

    if include_runs:
        dates = {row["run_name"]: row.get("run_date") for row in src.table("runs")}
        for run_name in simsaw.run_names(src):
            _import_run(s, i, simsaw.load_run(src, run_name), _excel_date(dates.get(run_name)))
    s.flush()
    return ds


def _line_fields(ln: em.ProductionLine) -> dict:
    return dict(
        name=ln.name, saw_type=int(ln.saw_type), primary_machine=ln.primary_machine,
        secondary_machine=ln.secondary_machine, primary_kerf=ln.primary_kerf,
        primary_outside_kerf=ln.primary_outside_kerf, primary_outside_blades=ln.primary_outside_blades,
        secondary_kerf=ln.secondary_kerf, secondary_outside_kerf=ln.secondary_outside_kerf,
        secondary_outside_blades=ln.secondary_outside_blades, primary_resaw=ln.primary_resaw,
        primary_resaw_kerf=ln.primary_resaw_kerf, secondary_resaw=ln.secondary_resaw,
        secondary_resaw_kerf=ln.secondary_resaw_kerf, cant_guiding=int(ln.cant_guiding), max_sweep=ln.max_sweep,
        log_rotation_deg=ln.log_rotation_deg, log_misalignment_mm=ln.log_misalignment_mm,
        primary_offset_mm=ln.primary_offset_mm, cant_misalignment_mm=ln.cant_misalignment_mm,
        secondary_offset_mm=ln.secondary_offset_mm, edging_objective=int(ln.edging_objective),
        edger_blades=ln.edger_blades, edger_kerf=ln.edger_kerf, second_board_width=ln.second_board_width,
        max_boards_per_flitch=ln.max_boards_per_flitch,
        edger_spacing=" ".join(f"{v:g}" for v in ln.edger_spacing))


def diameter_range(c: em.LogClass | None) -> str:
    return f"{c.min_diameter_cm:.1f} - {c.max_diameter_cm:.1f}" if c else ""


def _import_run(s: Session, ds_id: int, run: simsaw.Run, when: dt.datetime) -> m.Run:
    """A Simsaw batch run with Simsaw's own stored results, kept for comparison."""
    snap = run.dataset
    row = m.Run(dataset_id=ds_id, name=f"{run.name} (Simsaw)", created_at=when, source="simsaw", status="done",
                snapshot=snapshot.dumps(snap), message="Results calculated by Simsaw 6, imported unchanged.")
    s.add(row)
    s.flush()
    logs = {g.no: g for g in snap.logs}
    st = snap.settings
    total = 0
    for seq, pd in enumerate(snap.patterns):
        cl = next((c for c in snap.log_classes if c.no == pd.log_class_no), None)
        rp = m.RunPattern(run_id=row.id, seq=seq, line_name=pd.line_name, class_no=pd.log_class_no,
                          pattern_no=pd.pattern_no, primary=pd.primary, secondary=pd.secondary,
                          diameter_range=diameter_range(cl), log_price=cl.log_price if cl else 0.0,
                          chip_price=st.chip_price, sawdust_price=st.sawdust_price, pct_fines=st.pct_fines)
        s.add(rp)
        s.flush()
        for lr in (x for x in run.log_results if x.pattern_uid == pd.uid):
            g = logs.get(lr.log_no)
            s.add(m.RunLogResult(run_pattern_id=rp.id, log_no=lr.log_no, sed_cm=g.sed_cm if g else 0.0,
                                 length_m=g.length_m if g else 0.0, log_volume=lr.log_volume,
                                 dry_volume=lr.dry_board_volume, wet_volume=lr.wet_board_volume, value=lr.board_value,
                                 sawdust_volume=lr.sawdust_volume, chip_volume=lr.chip_volume, boards=lr.boards))
            total += 1
        for b in (x for x in run.board_results if x.pattern_uid == pd.uid):
            s.add(m.RunBoardResult(run_pattern_id=rp.id, log_no=b.log_no, board_type=b.board_type, board_no=b.board_no,
                                   thickness=b.thickness, width=b.width, length_m=b.length_m, left=b.left,
                                   right=b.right, bottom=b.bottom, top=b.top, front_m=b.front_m, back_m=b.back_m,
                                   resawn=b.resawn, resaw_position=b.resaw_position, dry_volume=b.dry_volume,
                                   wet_volume=b.wet_volume, value=b.value))
    row.progress = row.total = total
    return row


# ------------------------------------------------------------------ duplicate ("save as")

# Copy order: every table after the tables its foreign keys point to.
_COPY_ORDER = [m.LogGrade, m.BoardGrade, m.Thickness, m.Width, m.LengthClass, m.LogClass, m.LogClassGrade, m.Log,
               m.LogGenerator, m.Combination, m.WaneRule, m.CentreBoard, m.GradeOutput, m.ProductionLine,
               m.SawPattern, m.DatasetSettings, m.Run, m.RunPattern, m.RunLogResult, m.RunBoardResult,
               m.GeneratorJob]


def duplicate_dataset(s: Session, ds_id: int, name: str) -> m.Dataset:
    src = s.get(m.Dataset, ds_id)
    new = m.Dataset(name=name, notes=src.notes, source=f"Copy of {src.name}")
    s.add(new)
    s.flush()
    idmap: dict[str, dict[int, int]] = {"dataset": {ds_id: new.id}}
    for model in _COPY_ORDER:
        table = model.__table__
        fks = {col.name: next(iter(col.foreign_keys)).column.table.name for col in table.columns if col.foreign_keys}
        if "dataset_id" in table.columns:
            rows = s.scalars(select(model).where(model.dataset_id == ds_id)).all()
        else:   # child tables: rows whose parent was copied
            parent_col, parent_table = next((c, t) for c, t in fks.items())
            rows = s.scalars(select(model).where(getattr(model, parent_col).in_(list(idmap.get(parent_table, {}))))).all()
        pk = [c.name for c in table.primary_key.columns]
        mapping = idmap.setdefault(table.name, {})
        for row in rows:
            data = {c.key: getattr(row, c.key) for c in inspect(model).column_attrs}
            for col, target in fks.items():
                if data.get(col) is not None:
                    data[col] = idmap.get(target, {}).get(data[col], data[col])
            old_id = data.get("id")
            if pk == ["id"]:
                data.pop("id")
            obj = model(**data)
            s.add(obj)
            if pk == ["id"]:
                s.flush()
                mapping[old_id] = obj.id
    s.flush()
    return new


def delete_dataset(s: Session, ds_id: int) -> None:
    s.execute(delete(m.Dataset).where(m.Dataset.id == ds_id))
