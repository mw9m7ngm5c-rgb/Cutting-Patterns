"""Cant sawing: saw-line layout, primary and secondary breakdown, sawdust.

Phase 1 covers cant sawing with straight secondary cuts. Live sawing, chipper-profiler sideboards,
curve sawing, arris alignment, misalignment and offsets raise NotImplementedError until Phase 4.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import notation
from .edging import Choice, best_board
from .log import build_sections, log_volume_m3
from .model import (Board, CantGuiding, Log, LogResult, PatternResult, Products, ProductionLine,
                    Rules, Settings, Size)
from .sections import Sections


@dataclass(frozen=True)
class Flitch:
    kind: str            # "left", "right" (sideboards) or "cant"
    index: int           # board_no
    thickness: Size
    lo: float            # position of the two sawn faces along the thickness axis (x or y), lo < hi
    hi: float
    knives: bool = False  # inside the riving knives: cross-cut only, never edged

    @property
    def board_type(self) -> int:
        return {"left": 0, "right": 1, "cant": 2}[self.kind]


@dataclass
class Layout:
    """Where every saw line sits, in wet sizes, from the pattern text alone."""
    cant: Size
    cant_lo: float
    cant_hi: float
    flitches: list[Flitch] = field(default_factory=list)
    primary_kerfs: list[tuple[float, float]] = field(default_factory=list)     # x intervals
    secondary_kerfs: list[tuple[float, float]] = field(default_factory=list)   # y intervals

    def primary_blades(self) -> list[float]:
        """Sawn faces along x, left to right (both sides of every kerf)."""
        return sorted({v for k in self.primary_kerfs for v in k})

    def secondary_blades(self) -> list[float]:
        return sorted({v for k in self.secondary_kerfs for v in k})


def _kerf(i_from_outside: int, inside: float, outside: float | None, n_outside: int) -> float:
    if outside is not None and outside > 0 and i_from_outside < n_outside:
        return outside
    return inside


def layout(pattern: notation.Pattern, products: Products, line: ProductionLine) -> Layout:
    """Saw-line positions. The cant is centred on x = 0 and the secondary stack on y = 0; every
    board takes its wet thickness and neighbours are one kerf apart."""
    if pattern.is_live:
        raise NotImplementedError("live sawing (no cant in the primary pattern) arrives in Phase 4")
    if line.cant_guiding != CantGuiding.NONE:
        raise NotImplementedError("curve sawing (cant guiding) arrives in Phase 4")
    if line.cant_misalignment_mm or line.secondary_offset_mm:
        raise NotImplementedError("cant misalignment and secondary saw offset arrive in Phase 4")
    if pattern.secondary.arris_after is not None:
        raise NotImplementedError("arris alignment arrives in Phase 4")
    for item in (*pattern.primary.left.items, *pattern.primary.right.items, *pattern.secondary.items):
        if item.width is not None:
            raise NotImplementedError("chipper-profiler sideboards with fixed widths arrive in Phase 4")

    cant = products.width(pattern.primary.cant)
    lay = Layout(cant, -cant.wet / 2.0, cant.wet / 2.0)

    # primary: step outward from each cant face. Blade 0 from the outside is the slab cut.
    for kind, sign, stack in (("right", 1.0, pattern.primary.right.thicknesses),
                              ("left", -1.0, list(reversed(pattern.primary.left.thicknesses)))):
        blades = len(stack) + 1
        pos = cant.wet / 2.0
        for i, dry in enumerate(stack):
            k = _kerf(blades - 1 - i, line.primary_kerf, line.primary_outside_kerf, line.primary_outside_blades)
            t = products.thickness(dry)
            a, b = pos + k, pos + k + t.wet
            lay.primary_kerfs.append(tuple(sorted((sign * pos, sign * a))))
            lay.flitches.append(Flitch(kind, i, t, min(sign * a, sign * b), max(sign * a, sign * b)))
            pos = b
        k = _kerf(0, line.primary_kerf, line.primary_outside_kerf, line.primary_outside_blades)
        lay.primary_kerfs.append(tuple(sorted((sign * pos, sign * (pos + k)))))

    # secondary: the string reads from the bottom of the stack (-y) to the top (+y).
    sec = [products.thickness(t) for t in pattern.secondary.thicknesses]
    n = len(sec)
    if n:
        blades = n + 1                                   # two outer cuts plus one between each pair
        gaps = [_kerf(min(g, blades - 1 - g), line.secondary_kerf, line.secondary_outside_kerf,
                      line.secondary_outside_blades) for g in range(blades)]
        height = sum(t.wet for t in sec) + sum(gaps[1:-1])
        y = -height / 2.0
        lay.secondary_kerfs.append((y - gaps[0], y))
        for i, t in enumerate(sec):
            lay.flitches.append(Flitch("cant", i, t, y, y + t.wet, pattern.secondary.inside_knives(i)))
            y += t.wet
            lay.secondary_kerfs.append((y, y + gaps[i + 1]))
            y += gaps[i + 1]
    return lay


def _clipped(chord, lo_limit: float, hi_limit: float):
    def f(v):
        lo, hi = chord(v)
        lo = np.maximum(lo, lo_limit)
        hi = np.minimum(hi, hi_limit)
        empty = lo > hi
        return np.where(empty, np.inf, lo), np.where(empty, -np.inf, hi)
    return f


def _thinner(products: Products, thickness: Size) -> list[Size]:
    return sorted((t for t in products.thicknesses if t.wet < thickness.wet - 1e-6 and products.valid_widths(t.dry)),
                  key=lambda s: -s.dry)


def _cut_flitch(fl: Flitch, lay: Layout, sec: Sections, products: Products, line: ProductionLine,
                rules: Rules) -> tuple[Choice | None, bool]:
    """Edge, cross-cut and if need be resaw one flitch. Returns (choice, resawn)."""
    if fl.kind == "cant":
        chord = _clipped(sec.chord_x, lay.cant_lo, lay.cant_hi)
        limit = lay.cant.wet
        resaw = line.secondary_resaw
    else:
        chord = sec.chord_y
        limit = float("inf")
        resaw = line.primary_resaw

    def candidates(t: Size) -> list[Size]:
        out = []
        for w in products.valid_widths(t.dry):
            full = fl.kind == "cant" and abs(w.wet - lay.cant.wet) < 1e-6
            if w.wet > limit + 1e-6:
                continue
            if fl.knives and not full:
                continue                      # inside the riving knives: full cant width or nothing
            if (t.dry, w.dry) in products.centre_boards and not full:
                continue                      # centre boards never come off the edger
            out.append(w)
        return out

    choice = best_board(chord, sec.z_mm, fl.lo, fl.hi, fl.thickness, candidates(fl.thickness), products,
                        line.edging_objective, rules)
    if choice is not None or not resaw:
        return choice, False
    # Resaw: keep the sawn face nearer the centre of the log and take a thinner board off it.
    inner_is_lo = abs(fl.lo) <= abs(fl.hi)
    best: Choice | None = None
    for t in _thinner(products, fl.thickness):
        lo, hi = (fl.lo, fl.lo + t.wet) if inner_is_lo else (fl.hi - t.wet, fl.hi)
        c = best_board(chord, sec.z_mm, lo, hi, t, candidates(t), products, line.edging_objective, rules)
        if c is not None and (best is None or c.score > best.score):
            best = c
    return best, best is not None


def _board(fl: Flitch, c: Choice, resawn: bool, lay: Layout, sec: Sections, products: Products) -> Board:
    length_m = c.length_mm / 1000.0
    dry = c.thickness.dry * c.width.dry * c.length_mm / 1e9
    wet = c.thickness.wet * c.width.wet * c.length_mm / 1e9
    price = products.price(c.thickness.dry, c.width.dry, c.length_mm)
    u0, u1 = c.u0, c.u0 + c.width.wet
    if fl.kind == "cant":
        left, right, bottom, top = u0, u1, c.v_lo, c.v_hi
        edged = abs(c.width.wet - lay.cant.wet) > 1e-6
    else:
        left, right, bottom, top = c.v_lo, c.v_hi, u0, u1
        edged = True
    resaw_pos = 0.0
    if resawn:
        resaw_pos = c.v_hi if abs(c.v_lo - fl.lo) < 1e-9 else c.v_lo
    return Board(fl.board_type, fl.index, c.thickness.dry, c.width.dry, length_m, left, right, bottom, top,
                 float(sec.z_mm[c.first]) / 1000.0, float(sec.z_mm[c.last]) / 1000.0, resawn, resaw_pos,
                 edged, dry_volume=dry, wet_volume=wet, value=dry * price)


def _integrate(per_disc_area: np.ndarray, z_mm: np.ndarray) -> float:
    """mm2 per disc -> m3 along the log (trapezium rule)."""
    return float(np.sum((per_disc_area[1:] + per_disc_area[:-1]) * 0.5 * np.diff(z_mm.astype(float)))) / 1e9


def _overlap(lo: np.ndarray, hi: np.ndarray, a: float, b: float) -> np.ndarray:
    return np.clip(np.minimum(hi, b) - np.maximum(lo, a), 0.0, None)


def sawdust_volume(lay: Layout, sec: Sections, cuts: list[tuple[Flitch, Choice, bool]],
                   line: ProductionLine) -> float:
    """Wood removed by every kerf, measured on the log itself (ASSUMPTIONS A-22).

    Primary and secondary kerfs run the full length of the log. Edger kerfs run on both sides of each
    edged board along its clear span; a resaw kerf runs along the resawn flitch. A kerf only counts
    where it passes through wood.
    """
    z = sec.z_mm
    total = 0.0
    for a, b in lay.primary_kerfs:
        lo, hi = sec.chord_y((a + b) / 2.0)
        total += _integrate(np.clip(hi - lo, 0.0, None) * (b - a), z)
    for a, b in lay.secondary_kerfs:
        lo, hi = sec.chord_x((a + b) / 2.0)
        total += _integrate(_overlap(lo, hi, lay.cant_lo, lay.cant_hi) * (b - a), z)
    for fl, c, resawn in cuts:
        cant = fl.kind == "cant"
        across = sec.chord_y if cant else sec.chord_x      # wood extent along the thickness axis
        if resawn:
            k = line.secondary_resaw_kerf if cant else line.primary_resaw_kerf
            outward = abs(c.v_lo - fl.lo) < 1e-9             # board kept at the lo face, kerf above it
            ka, kb = (c.v_hi, min(c.v_hi + k, fl.hi)) if outward else (max(c.v_lo - k, fl.lo), c.v_lo)
            along = sec.chord_x if cant else sec.chord_y
            lo, hi = along((ka + kb) / 2.0)
            if cant:
                width = _overlap(lo, hi, lay.cant_lo, lay.cant_hi)
            else:
                width = np.clip(hi - lo, 0.0, None)
            total += _integrate(width * max(kb - ka, 0.0), z)
        edged = (not cant) or abs(c.width.wet - lay.cant.wet) > 1e-6
        if not edged:
            continue
        k = line.edger_kerf
        for ka, kb in ((c.u0 - k, c.u0), (c.u0 + c.width.wet, c.u0 + c.width.wet + k)):
            if cant:
                ka, kb = max(ka, lay.cant_lo), min(kb, lay.cant_hi)
            if kb <= ka:
                continue
            lo, hi = across((ka + kb) / 2.0)
            wood = _overlap(lo, hi, c.v_lo, c.v_hi)
            wood[:c.first] = 0.0                 # the edger cut is charged along the board's clear span
            wood[c.last + 1:] = 0.0
            total += _integrate(wood * (kb - ka), z)
    return total


def simulate_log(log: Log, pattern: notation.Pattern, products: Products, line: ProductionLine,
                 settings: Settings, rules: Rules | None = None, lay: Layout | None = None) -> LogResult:
    rules = rules or Rules()
    lay = lay or layout(pattern, products, line)
    sec = build_sections(log, settings, line)
    cuts: list[tuple[Flitch, Choice, bool]] = []
    boards: list[Board] = []
    for fl in lay.flitches:
        choice, resawn = _cut_flitch(fl, lay, sec, products, line, rules)
        if choice is None:
            continue
        cuts.append((fl, choice, resawn))
        boards.append(_board(fl, choice, resawn, lay, sec, products))
    boards.sort(key=lambda b: (b.board_type, b.board_no))
    volume = log_volume_m3(log, settings)
    dust = sawdust_volume(lay, sec, cuts, line)
    wet = sum(b.wet_volume for b in boards)
    return LogResult(log, boards, volume, dust, volume - wet - dust)


def simulate_pattern(logs: list[Log], primary: str, secondary: str, products: Products,
                     line: ProductionLine, settings: Settings, log_price: float = 0.0,
                     rules: Rules | None = None) -> PatternResult:
    pattern = notation.parse(primary, secondary)
    lay = layout(pattern, products, line)
    results = [simulate_log(log, pattern, products, line, settings, rules, lay) for log in logs]
    return PatternResult(primary, secondary, results, log_price, settings.chip_price,
                         settings.sawdust_price, settings.pct_fines)
