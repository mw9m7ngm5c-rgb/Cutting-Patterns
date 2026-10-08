"""Data for the sawing-pattern screen: the end-view diagram of one log and the results of a class."""
from __future__ import annotations

from engine import notation
from engine.log import build_core_sections, build_sections
from engine.model import Log, PatternResult
from engine.sawing import check_pattern, layout, simulate_log, simulate_pattern
from importers.simsaw import Dataset

KIND = {0: "Left sideboard", 1: "Right sideboard", 2: "Cant board", 3: "Flitch"}


def _r(v: float, nd: int = 2) -> float:
    return round(float(v), nd)


def _outline(sec, index: int, points: int = 96) -> list[list[float]]:
    return [[_r(x), _r(y)] for x, y in sec.outline(index, points)]


def board_dict(b, dy: float = 0.0) -> dict:
    """dy: how far the secondary cuts sit above the datum at the small end; cant boards are drawn there."""
    dy = dy if b.board_type == 2 else 0.0
    return {"kind": KIND[b.board_type], "board_type": b.board_type, "board_no": b.board_no, "label": b.label,
            "piece": b.piece, "grade": b.grade, "core_share": b.core_share,
            "thickness": b.thickness, "width": b.width, "length_m": b.length_m, "left": _r(b.left), "right": _r(b.right),
            "bottom": _r(b.bottom + dy), "top": _r(b.top + dy), "front_m": _r(b.front_m), "back_m": _r(b.back_m),
            "resawn": b.resawn, "edged": b.edged, "dry_volume": b.dry_volume, "wet_volume": b.wet_volume, "value": b.value}


def log_dict(g: Log) -> dict:
    return {"no": g.no, "sed_cm": g.sed_cm, "length_m": g.length_m, "taper": g.taper_mm_per_m, "sweep_mm": g.sweep_mm,
            "sweep_mm_per_m": _r(g.sweep_mm_per_m), "ovality": g.ovality, "defect_core_cm": g.defect_core_cm, "grade": g.grade}


def diagram(ds: Dataset, line_name: str, log: Log, primary: str, secondary: str) -> dict:
    """End view of one log sawn with one pattern, in the saw frame (mm, y up)."""
    line = ds.line(line_name)
    out: dict = {"log": log_dict(log), "problems": check_pattern(primary, secondary, ds.products, line)}
    try:
        sec = build_sections(log, ds.settings, line)
    except NotImplementedError as e:
        out["problems"].append(str(e))
        return out
    out["small_end"] = _outline(sec, 0)
    out["large_end"] = _outline(sec, len(sec.z_mm) - 1)
    if log.defect_core_cm > 0:
        core = build_core_sections(log, ds.settings, line)
        out["core"] = _outline(core, 0)
    if out["problems"]:
        return out
    pattern = notation.parse(primary, secondary)
    lay = layout(pattern, ds.products, line)
    lr = simulate_log(log, pattern, ds.products, line, ds.settings, lay=lay)
    shift = lr.secondary_shift
    dy0 = float(shift[0]) if shift is not None and len(shift) else 0.0
    out.update({
        "cant": None if lay.live else {"lo": lay.cant_lo, "hi": lay.cant_hi, "wet": lay.cant.wet, "dry": lay.cant.dry},
        "primary_kerfs": [[_r(a), _r(b)] for a, b in lay.primary_kerfs],
        "secondary_kerfs": [[_r(a + dy0), _r(b + dy0)] for a, b in lay.secondary_kerfs],
        "half_cant": 0.0 if lay.live else (lay.cant_hi - lay.cant_lo) / 2.0,
        "secondary_shift": None if shift is None or not len(shift) or not any(abs(v) > 1e-6 for v in shift) else
            {"small_end": _r(shift[0], 1), "middle": _r(shift[len(shift) // 2], 1), "large_end": _r(shift[-1], 1)},
        "graded": ds.products.grades_in_use,
        "blades": blade_positions(lay),
        "boards": [board_dict(b, dy0) for b in lr.boards],
        "result": {"log_volume": lr.log_volume, "dry_volume": lr.dry_board_volume, "wet_volume": lr.wet_board_volume,
                   "value": lr.board_value, "sawdust": lr.sawdust_volume, "chips": lr.chip_volume,
                   "shrinkage": lr.shrinkage_volume, "boards": len(lr.boards),
                   "dry_recovery": lr.dry_board_volume / lr.log_volume if lr.log_volume else 0.0},
    })
    return out


def blade_positions(lay) -> dict:
    """Sawn faces as distances from the centreline (wet sizes, mm): what the saw doctor sets."""
    return {"primary": [_r(v, 1) for v in lay.primary_blades()], "secondary": [_r(v, 1) for v in lay.secondary_blades()]}


def pattern_result_dict(res: PatternResult) -> dict:
    mix_total = sum(d["dry_volume"] for d in res.product_mix().values()) or 1.0
    return {
        "logs": len(res.logs), "log_volume": res.log_volume, "dry_recovery": res.dry_recovery,
        "wet_recovery": res.wet_recovery, "gross_value": res.gross_value_recovery, "nett_value": res.nett_value_recovery,
        "boards": res.board_count, "boards_per_log": res.board_count / len(res.logs) if res.logs else 0.0,
        "average_length": res.average_length_m,
        "sawdust": sum(r.sawdust_volume for r in res.logs), "chips": sum(r.chip_volume for r in res.logs),
        "dry_volume": sum(r.dry_board_volume for r in res.logs), "wet_volume": sum(r.wet_board_volume for r in res.logs),
        "mix": [{"thickness": t, "width": w, "pieces": int(d["count"]), "dry_volume": d["dry_volume"],
                 "share": d["dry_volume"] / mix_total} for (t, w), d in res.product_mix().items()],
        "per_log": [{"no": r.log.no, "sed_cm": r.log.sed_cm, "length_m": r.log.length_m, "log_volume": r.log_volume,
                     "boards": len(r.boards), "dry_volume": r.dry_board_volume,
                     "dry_recovery": r.dry_board_volume / r.log_volume if r.log_volume else 0.0, "value": r.board_value}
                    for r in res.logs],
    }


def class_result(ds: Dataset, line_name: str, class_no: int, primary: str, secondary: str) -> dict:
    line = ds.line(line_name)
    problems = check_pattern(primary, secondary, ds.products, line)
    if problems:
        return {"problems": problems}
    logs = ds.logs_in_class(class_no)
    if not logs:
        return {"problems": ["no logs fall in this class"]}
    res = simulate_pattern(logs, primary, secondary, ds.products, line, ds.settings, ds.log_class(class_no).log_price)
    return {"problems": [], **pattern_result_dict(res)}


def median_log(logs: list[Log]) -> Log | None:
    """The log with the middle small-end diameter: the one drawn on cards and result thumbnails."""
    if not logs:
        return None
    srt = sorted(logs, key=lambda g: (g.sed_cm, g.no))
    return srt[(len(srt) - 1) // 2]


def setting_rows(lay, axis_label: str) -> list[dict]:
    """One row per blade, from one side to the other: where the blade cuts (distances from the
    centreline, wet sizes, mm) and the board or cant that follows it up to the next blade."""
    kerfs = sorted(lay.primary_kerfs if axis_label == "x" else lay.secondary_kerfs)
    pieces = [(f.lo, f.hi, "board", f.thickness) for f in lay.flitches if (f.kind != "cant") == (axis_label == "x")]
    if axis_label == "x" and not lay.live:
        pieces.append((lay.cant_lo, lay.cant_hi, "cant", lay.cant))
    rows = []
    for n, (a, b) in enumerate(kerfs, 1):
        nxt = next((p for p in sorted(pieces) if abs(p[0] - b) < 1e-6), None)
        rows.append({"blade": n, "from": round(a, 1), "to": round(b, 1), "kerf": round(b - a, 1),
                     "next": nxt[2] if nxt else None, "next_to": round(nxt[1], 1) if nxt else None,
                     "dry": nxt[3].dry if nxt else None, "wet": nxt[3].wet if nxt else None})
    return rows


def setting_card(ds: Dataset, line_name: str, class_no: int, primary: str, secondary: str) -> dict:
    """Everything the saw doctor needs for one pattern: diagram, blade positions, kerfs and what to expect."""
    line = ds.line(line_name)
    problems = check_pattern(primary, secondary, ds.products, line)
    logs = ds.logs_in_class(class_no)
    card = {"problems": problems, "line": line, "class": ds.log_class(class_no), "primary": primary,
            "secondary": secondary, "logs": len(logs)}
    if problems:
        return card
    lay = layout(notation.parse(primary, secondary), ds.products, line)
    card["primary_rows"] = setting_rows(lay, "x")
    card["secondary_rows"] = setting_rows(lay, "y")
    card["cant"] = lay.cant
    if logs:
        card["result"] = class_result(ds, line_name, class_no, primary, secondary)
        card["diagram"] = diagram(ds, line_name, median_log(logs), primary, secondary)
    return card
