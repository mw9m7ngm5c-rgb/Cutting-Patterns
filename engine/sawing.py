"""Sawing: saw-line layout, primary and secondary breakdown, edging, grades, sawdust.

Cant sawing, live sawing and chipper-profiler boards. The log is placed on the primary saw by
``log.build_sections`` (rotation, misalignment, primary offset, real-log variation). Everything
that moves or bends the secondary cuts (curve sawing, cant misalignment, secondary offset, arris
alignment) is one shift of the cant frame per disc (``secondary_shift``), so the edger and the wane
test work the same on straight and curved boards.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

import numpy as np

from . import notation
from .edging import Choice, best_board
from .log import build_core_sections, build_sections, log_rng, log_volume_m3
from .model import (Board, CantGuiding, Log, LogResult, PatternResult, Products, ProductionLine,
                    Rules, SawType, Settings, Size)
from .sections import Sections, Shifted


@dataclass(frozen=True)
class Flitch:
    kind: str            # "left", "right" (sideboards), "cant" (cant boards) or "live" (live sawing)
    index: int           # board_no
    thickness: Size
    lo: float            # position of the two sawn faces along the thickness axis (x or y), lo < hi
    hi: float
    knives: bool = False  # inside the riving knives: cross-cut only, never edged
    fixed_width: Size | None = None   # chipper-profiler: profiled to this width on the centreline, never edged

    @property
    def board_type(self) -> int:
        return {"left": 0, "right": 1, "cant": 2, "live": 3}[self.kind]

    @property
    def on_cant(self) -> bool:
        return self.kind == "cant"


@dataclass
class Layout:
    """Where every saw line sits, in wet sizes, from the pattern text alone."""
    cant: Size | None            # None for live sawing
    cant_lo: float
    cant_hi: float
    flitches: list[Flitch] = field(default_factory=list)
    primary_kerfs: list[tuple[float, float]] = field(default_factory=list)     # x intervals
    secondary_kerfs: list[tuple[float, float]] = field(default_factory=list)   # y intervals (cant frame)
    arris_after: int | None = None         # secondary board the arris blade follows

    @property
    def live(self) -> bool:
        return self.cant is None

    def primary_blades(self) -> list[float]:
        """Sawn faces along x, left to right (both sides of every kerf)."""
        return sorted({v for k in self.primary_kerfs for v in k})

    def secondary_blades(self) -> list[float]:
        return sorted({v for k in self.secondary_kerfs for v in k})


def _kerf(i_from_outside: int, inside: float, outside: float | None, n_outside: int) -> float:
    if outside is not None and outside > 0 and i_from_outside < n_outside:
        return outside
    return inside


def _stack(sizes: list[Size], fixed: list[Size | None], kind: str, kerf: float, outside: float | None,
           n_outside: int, knives=lambda i: False) -> tuple[list[Flitch], list[tuple[float, float]]]:
    """A centred stack of boards one kerf apart, with a cut outside each end."""
    n = len(sizes)
    blades = n + 1
    gaps = [_kerf(min(g, blades - 1 - g), kerf, outside, n_outside) for g in range(blades)]
    height = sum(t.wet for t in sizes) + sum(gaps[1:-1])
    pos = -height / 2.0
    kerfs = [(pos - gaps[0], pos)]
    flitches = []
    for i, t in enumerate(sizes):
        flitches.append(Flitch(kind, i, t, pos, pos + t.wet, knives(i), fixed[i]))
        pos += t.wet
        kerfs.append((pos, pos + gaps[i + 1]))
        pos += gaps[i + 1]
    return flitches, kerfs


def layout(pattern: notation.Pattern, products: Products, line: ProductionLine) -> Layout:
    """Saw-line positions. Cant sawing: the cant is centred on x = 0 and the secondary stack on y = 0.
    Live sawing: the whole stack of flitches is centred on x = 0. Every board takes its wet thickness
    and neighbours are one kerf apart."""
    fixed = lambda item: products.width(item.width) if item.width is not None else None
    if pattern.is_live:
        items = pattern.primary.left.items
        fl, kerfs = _stack([products.thickness(i.thickness) for i in items], [fixed(i) for i in items], "live",
                           line.primary_kerf, line.primary_outside_kerf, line.primary_outside_blades)
        return Layout(None, 0.0, 0.0, fl, kerfs, [])

    cant = products.width(pattern.primary.cant)
    lay = Layout(cant, -cant.wet / 2.0, cant.wet / 2.0, arris_after=pattern.secondary.arris_after)

    # primary: step outward from each cant face. Blade 0 from the outside is the slab cut.
    for kind, sign, items in (("right", 1.0, list(pattern.primary.right.items)),
                              ("left", -1.0, list(reversed(pattern.primary.left.items)))):
        blades = len(items) + 1
        pos = cant.wet / 2.0
        for i, item in enumerate(items):
            k = _kerf(blades - 1 - i, line.primary_kerf, line.primary_outside_kerf, line.primary_outside_blades)
            t = products.thickness(item.thickness)
            a, b = pos + k, pos + k + t.wet
            lay.primary_kerfs.append(tuple(sorted((sign * pos, sign * a))))
            lay.flitches.append(Flitch(kind, i, t, min(sign * a, sign * b), max(sign * a, sign * b),
                                       fixed_width=fixed(item)))
            pos = b
        k = _kerf(0, line.primary_kerf, line.primary_outside_kerf, line.primary_outside_blades)
        lay.primary_kerfs.append(tuple(sorted((sign * pos, sign * (pos + k)))))

    # secondary: the string reads from the bottom of the stack (-y) to the top (+y).
    items = pattern.secondary.items
    if items:
        fl, kerfs = _stack([products.thickness(i.thickness) for i in items], [fixed(i) for i in items], "cant",
                           line.secondary_kerf, line.secondary_outside_kerf, line.secondary_outside_blades,
                           pattern.secondary.inside_knives)
        lay.flitches += fl
        lay.secondary_kerfs = kerfs
    return lay


# ------------------------------------------------------------------ the secondary saw's frame

def secondary_shift(lay: Layout, sec: Sections, line: ProductionLine, settings: Settings) -> np.ndarray:
    """How far above the saw datum the secondary cuts sit at every disc (mm).

    - secondary saw offset: the whole stack moves up;
    - cant misalignment: the cant lies at an angle, its middle on the saw line (A-53);
    - cant guiding (curve sawing): half taper follows the curve of the log's centreline, full taper
      follows the top face of the cant, so the taper is all taken on one side; either only as far as
      the largest sweep the saw can follow, the rest is sawn straight (A-54);
    - arris alignment: the stack moves so the marked blade sits on the arris (A-57).
    """
    z = sec.z_mm.astype(float)
    n = len(z)
    if lay.live:
        return np.zeros(n)
    span = max(z[-1] - z[0], 1.0)
    t = (z - z[0]) / span
    dy = line.secondary_offset_mm + line.cant_misalignment_mm * (t - 0.5)
    if line.cant_guiding != CantGuiding.NONE:
        _, cy = sec.centres()
        straight = cy[0] + (cy[-1] - cy[0]) * t
        bend = cy - straight
        sweep = float(np.max(np.abs(bend)))
        can_follow = max(line.max_sweep, 0.0) * span / 1000.0
        share = 1.0 if sweep <= can_follow or sweep <= 1e-9 else can_follow / sweep
        follow = straight + share * bend
        if line.cant_guiding == CantGuiding.FULL_TAPER:
            r = np.sqrt(sec.areas() / np.pi)
            follow = follow + (r - np.interp(z[0] + span / 2.0, z, r))
        dy = dy + follow
    dy = np.asarray(dy, dtype=float) * np.ones(n)
    if lay.arris_after is not None:
        dy = dy + _arris_shift(lay, Shifted(sec, dy), settings)
    return dy


def _arris_shift(lay: Layout, cant: Shifted, settings: Settings) -> float:
    """Move the stack so the blade after board ``arris_after`` sits on the arris: the height at which
    the cant's sawn faces run out of wood. A blade in the upper half of the stack goes to the top
    arris, otherwise to the bottom one. Judged on the small end only, or along the whole log."""
    boards = [f for f in lay.flitches if f.on_cant]
    j = lay.arris_after
    if j is None or j >= len(boards) - 1:
        return 0.0
    edge = lay.cant.wet / 2.0 - 1e-6
    lo_l, hi_l = cant.chord_y(-edge)
    lo_r, hi_r = cant.chord_y(edge)
    pick = slice(0, 1) if settings.arris_small_end else slice(None)
    top = float(min(hi_l[pick].min(), hi_r[pick].min()))
    bottom = float(max(lo_l[pick].max(), lo_r[pick].max()))
    if not (np.isfinite(top) and np.isfinite(bottom)) or top <= bottom:
        return 0.0                      # the cant faces see no wood: nothing to align to
    if j >= (len(boards) - 1) / 2.0:
        return top - boards[j].hi
    return bottom - boards[j + 1].lo


# ------------------------------------------------------------------ cutting one flitch

def _clipped(chord, lo_limit: float, hi_limit: float):
    def f(v):
        lo, hi = chord(v)
        lo = np.maximum(lo, lo_limit)
        hi = np.minimum(hi, hi_limit)
        empty = lo > hi
        return np.where(empty, np.inf, lo), np.where(empty, -np.inf, hi)
    return f


def _masked(chord, keep: np.ndarray):
    """The chord with every disc outside ``keep`` emptied (for cutting the rest of a flitch)."""
    def f(v):
        lo, hi = chord(v)
        return np.where(keep, lo, np.inf), np.where(keep, hi, -np.inf)
    return f


def _thinner(products: Products, thickness: Size) -> list[Size]:
    return sorted((t for t in products.thicknesses if t.wet < thickness.wet - 1e-6 and products.valid_widths(t.dry)),
                  key=lambda s: -s.dry)


def _total(choices: list[Choice]) -> float:
    return sum(c.score[0] for c in choices)


@dataclass
class Cut:
    flitch: Flitch
    choice: Choice
    resawn: bool
    piece: int = 0


def _cut_flitch(fl: Flitch, lay: Layout, sec: Sections, cant: Sections, products: Products,
                line: ProductionLine, rules: Rules) -> list[Cut]:
    """Edge, cross-cut and if need be resaw one flitch; with a three-blade edger or cross-cutting
    into several boards, the extra boards too."""
    if fl.on_cant:
        chord = _clipped(cant.chord_x, lay.cant_lo, lay.cant_hi)
        limit = lay.cant.wet
        resaw = line.secondary_resaw
        u_lo, u_hi = lay.cant_lo, lay.cant_hi
    else:
        chord = sec.chord_y
        limit = float("inf")
        resaw = line.primary_resaw
        u_lo, u_hi = -np.inf, np.inf
    z = sec.z_mm

    if fl.fixed_width is not None:
        # chipper-profiler: the width is cut on the log's centreline, so only the length is chosen
        w = fl.fixed_width
        c = best_board(chord, z, fl.lo, fl.hi, fl.thickness, [w], products, line.edging_objective, rules,
                       fixed_u0=-w.wet / 2.0)
        return [Cut(fl, c, False)] if c is not None else []

    def candidates(t: Size) -> list[Size]:
        out = []
        for w in products.valid_widths(t.dry):
            full = fl.on_cant and abs(w.wet - lay.cant.wet) < 1e-6
            if w.wet > limit + 1e-6:
                continue
            if fl.knives and not full:
                continue                      # inside the riving knives: full cant width or nothing
            if (t.dry, w.dry) in products.centre_boards and not full:
                continue                      # centre boards never come off the edger
            out.append(w)
        return out

    def one(ch, rl=rules, cache=None) -> tuple[Choice | None, bool]:
        c = best_board(ch, z, fl.lo, fl.hi, fl.thickness, candidates(fl.thickness), products,
                       line.edging_objective, rl, cache=cache)
        if c is not None or not resaw:
            return c, False
        # Resaw: keep the sawn face nearer the centre of the log and take a thinner board off it.
        inner_is_lo = abs(fl.lo) <= abs(fl.hi)
        best: Choice | None = None
        for t in _thinner(products, fl.thickness):
            lo, hi = (fl.lo, fl.lo + t.wet) if inner_is_lo else (fl.hi - t.wet, fl.hi)
            c = best_board(ch, z, lo, hi, t, candidates(t), products, line.edging_objective, rl, cache=cache)
            if c is not None and (best is None or c.score > best.score):
                best = c
        return best, best is not None

    ladders: dict = {}                     # depth ladders on the unmasked chord, shared by every call below
    first, resawn = one(chord, cache=ladders)
    if first is None:
        return []
    cuts = [Cut(fl, first, resawn)]

    # three-blade edger: a second board from the offcut beside the first (A-58)
    full_width = fl.on_cant and abs(first.width.wet - lay.cant.wet) < 1e-6
    if line.edger_blades >= 3 and not fl.knives and not full_width:
        second = _second_board(fl, first, chord, z, u_lo, u_hi, products, line, rules, candidates, ladders)
        if second is not None:
            cuts = [Cut(fl, second[0], resawn), Cut(fl, second[1], resawn, 1)]

    # cross-cut: further boards from the length the first one left (A-59)
    if line.max_boards_per_flitch > 1:
        used = np.zeros(len(z), dtype=bool)
        for c in cuts:
            end = z[c.choice.first] + c.choice.length_mm
            used[c.choice.first:np.searchsorted(z, end, side="right")] = True
        piece = len(cuts)
        while piece < line.max_boards_per_flitch:
            free = ~used
            # a board may start or end on the disc where the cross-cut is made
            edges = np.flatnonzero(np.diff(used.astype(int)) != 0)
            free[edges] = True
            free[np.minimum(edges + 1, len(z) - 1)] = True
            c, rs = one(_masked(chord, free))
            if c is None:
                break
            cuts.append(Cut(fl, c, rs, piece))
            used[c.first:np.searchsorted(z, z[c.first] + c.length_mm, side="right")] = True
            piece += 1
    return cuts


def _second_board(fl, first: Choice, chord, z, u_lo, u_hi, products, line, rules, candidates, cache=None):
    """Best pair of boards side by side with the edger's middle blade between them, or None.

    A three-blade edger has two outside saws and one between the boards, so the second board lies
    exactly one kerf from the first. The first board is pushed to one end of the room it has (low or
    high) to leave the most for the second; the pair is kept only if it beats the single board."""
    k = line.edger_kerf
    t = first.thickness
    if line.second_board_width.strip().lower() in ("", "best"):
        widths2 = candidates(t)
    else:
        try:
            w2 = products.width(float(line.second_board_width))
            widths2 = [w2] if any(abs(w.dry - w2.dry) < 1e-6 for w in candidates(t)) else []
        except (KeyError, ValueError):
            widths2 = []
    if not widths2:
        return None
    # Quick test before searching: on the narrower of the flitch's two faces the wood, plus the most
    # wane the wane rule lets each outside edge carry, must hold both boards and the kerf somewhere.
    lo1, hi1 = chord(first.v_lo)
    lo2, hi2 = chord(first.v_hi)
    room = np.minimum(hi1 - lo1, hi2 - lo2)
    room = float(np.max(room[np.isfinite(room)])) if np.any(np.isfinite(room)) else 0.0
    wane = max((products.wane_rule(t.dry, w.dry).width_pct / 100.0 * w.dry * rules.width_wane_edge_share
                for w in [first.width, *widths2]), default=0.0)
    if first.width.wet + k + min(w.wet for w in widths2) > room + 2 * wane + 1e-6:
        return None
    best = None
    for placement in ("low", "high"):
        f = best_board(chord, z, first.v_lo, first.v_hi, t, [first.width], products, line.edging_objective,
                       dataclasses.replace(rules, placement=placement), cache=cache)
        if f is None:
            continue
        for w2 in widths2:
            u2 = f.u0 + f.width.wet + k if placement == "low" else f.u0 - k - w2.wet
            if u2 < u_lo - 1e-6 or u2 + w2.wet > u_hi + 1e-6:
                continue
            s = best_board(chord, z, first.v_lo, first.v_hi, t, [w2], products, line.edging_objective, rules,
                           fixed_u0=u2, cache=cache)
            if s is not None and (best is None or _total([f, s]) > _total(best)):
                best = [f, s]
    if best is None or _total(best) <= _total([first]):
        return None
    return best


# ------------------------------------------------------------------ boards and grades

def _core_share(fl: Flitch, c: Choice, core: Sections) -> float:
    """Share of the board's sawn cross-section inside the defect core, averaged along the board."""
    grid = (np.arange(6) + 0.5) / 6.0
    u = c.u0 + grid * c.width.wet
    v = c.v_lo + grid * (c.v_hi - c.v_lo)
    uu, vv = np.meshgrid(u, v)
    x, y = (uu, vv) if fl.on_cant else (vv, uu)
    discs = np.unique(np.linspace(c.first, c.last, num=min(12, c.last - c.first + 1)).round().astype(int))
    return float(np.mean([core.inside(i, x, y).mean() for i in discs]))


def _grade(products: Products, log: Log, t: float, w: float, share: float, rng: np.random.Generator) -> str:
    """Draw the board grade from the grade-output table for this size and log grade (A-60)."""
    band = 0 if share <= 1e-9 else 1 if share <= 0.5 else 2 if share < 1 - 1e-9 else 3
    p = np.array([products.grade_outputs.get((t, w, log.grade, g), (0, 0, 0, 0))[band]
                  for g in products.board_grades], dtype=float)
    if p.sum() <= 0:
        return products.board_grades[0]
    return products.board_grades[int(np.searchsorted(np.cumsum(p / p.sum()), rng.random(), side="right"))]


def _board(cut: Cut, lay: Layout, sec: Sections, products: Products, grade: str | None = None,
           core_share: float = 0.0) -> Board:
    fl, c, resawn = cut.flitch, cut.choice, cut.resawn
    length_m = c.length_mm / 1000.0
    dry = c.thickness.dry * c.width.dry * c.length_mm / 1e9
    wet = c.thickness.wet * c.width.wet * c.length_mm / 1e9
    price = products.price(c.thickness.dry, c.width.dry, c.length_mm, grade)
    u0, u1 = c.u0, c.u0 + c.width.wet
    if fl.on_cant:
        left, right, bottom, top = u0, u1, c.v_lo, c.v_hi
        edged = abs(c.width.wet - lay.cant.wet) > 1e-6 and fl.fixed_width is None
    else:
        left, right, bottom, top = c.v_lo, c.v_hi, u0, u1
        edged = fl.fixed_width is None
    resaw_pos = 0.0
    if resawn:
        resaw_pos = c.v_hi if abs(c.v_lo - fl.lo) < 1e-9 else c.v_lo
    out = Board(fl.board_type, fl.index, c.thickness.dry, c.width.dry, length_m, left, right, bottom, top,
                float(sec.z_mm[c.first]) / 1000.0, float(sec.z_mm[c.last]) / 1000.0, resawn, resaw_pos,
                edged, dry_volume=dry, wet_volume=wet, value=dry * price, piece=cut.piece, core_share=core_share)
    if grade is not None:
        out = dataclasses.replace(out, grade=grade)
    return out


# ------------------------------------------------------------------ sawdust

def _integrate(per_disc_area: np.ndarray, z_mm: np.ndarray) -> float:
    """mm2 per disc -> m3 along the log (trapezium rule)."""
    return float(np.sum((per_disc_area[1:] + per_disc_area[:-1]) * 0.5 * np.diff(z_mm.astype(float)))) / 1e9


def _overlap(lo: np.ndarray, hi: np.ndarray, a: float, b: float) -> np.ndarray:
    return np.clip(np.minimum(hi, b) - np.maximum(lo, a), 0.0, None)


def sawdust_volume(lay: Layout, sec: Sections, cuts: list[Cut], line: ProductionLine,
                   cant: Sections | None = None) -> float:
    """Wood removed by every kerf, measured on the log itself (ASSUMPTIONS A-23).

    Primary and secondary kerfs run the full length of the log. Edger kerfs run on both sides of each
    edged board along its clear span (a kerf shared by two boards side by side counts once); a resaw
    kerf runs along the resawn flitch. A kerf only counts where it passes through wood.
    """
    cant = cant if cant is not None else sec
    z = sec.z_mm
    total = 0.0
    for a, b in lay.primary_kerfs:
        lo, hi = sec.chord_y((a + b) / 2.0)
        total += _integrate(np.clip(hi - lo, 0.0, None) * (b - a), z)
    for a, b in lay.secondary_kerfs:
        lo, hi = cant.chord_x((a + b) / 2.0)
        total += _integrate(_overlap(lo, hi, lay.cant_lo, lay.cant_hi) * (b - a), z)
    edger: dict[tuple, tuple] = {}
    resaws: set[tuple] = set()
    for cut in cuts:
        fl, c, resawn = cut.flitch, cut.choice, cut.resawn
        on_cant = fl.on_cant
        geo = cant if on_cant else sec
        across = geo.chord_y if on_cant else geo.chord_x      # wood extent along the thickness axis
        if resawn and (fl.kind, fl.index) not in resaws:
            resaws.add((fl.kind, fl.index))
            k = line.secondary_resaw_kerf if on_cant else line.primary_resaw_kerf
            outward = abs(c.v_lo - fl.lo) < 1e-9             # board kept at the lo face, kerf above it
            ka, kb = (c.v_hi, min(c.v_hi + k, fl.hi)) if outward else (max(c.v_lo - k, fl.lo), c.v_lo)
            along = geo.chord_x if on_cant else geo.chord_y
            lo, hi = along((ka + kb) / 2.0)
            width = _overlap(lo, hi, lay.cant_lo, lay.cant_hi) if on_cant else np.clip(hi - lo, 0.0, None)
            total += _integrate(width * max(kb - ka, 0.0), z)
        edged = fl.fixed_width is None and ((not on_cant) or abs(c.width.wet - lay.cant.wet) > 1e-6)
        if not edged:
            continue
        k = line.edger_kerf
        for ka, kb in ((c.u0 - k, c.u0), (c.u0 + c.width.wet, c.u0 + c.width.wet + k)):
            if on_cant:
                ka, kb = max(ka, lay.cant_lo), min(kb, lay.cant_hi)
            if kb <= ka:
                continue
            key = (fl.kind, fl.index, round(c.v_lo, 3), round(min(ka, kb), 1))
            span = np.zeros(len(z), dtype=bool)
            span[c.first:c.last + 1] = True       # the edger cut is charged along the board's clear span
            if key in edger:
                span |= edger[key][3]
            edger[key] = (across, ka, kb, span, c.v_lo, c.v_hi)
    for across, ka, kb, span, v_lo, v_hi in edger.values():
        lo, hi = across((ka + kb) / 2.0)
        wood = np.where(span, _overlap(lo, hi, v_lo, v_hi), 0.0)
        total += _integrate(wood * (kb - ka), z)
    return total


# ------------------------------------------------------------------ one log, one pattern

def simulate_log(log: Log, pattern: notation.Pattern, products: Products, line: ProductionLine,
                 settings: Settings, rules: Rules | None = None, lay: Layout | None = None) -> LogResult:
    rules = rules or Rules()
    lay = lay or layout(pattern, products, line)
    sec = build_sections(log, settings, line)
    dy = secondary_shift(lay, sec, line, settings)
    cant = Shifted(sec, dy) if np.any(np.abs(dy) > 1e-9) else sec
    grading = products.grades_in_use
    rng = log_rng(settings, log, 2) if grading else None
    core = None
    if grading and log.defect_core_cm > 0:
        core = build_core_sections(log, settings, line)
    cuts: list[Cut] = []
    boards: list[Board] = []
    for fl in lay.flitches:
        for cut in _cut_flitch(fl, lay, sec, cant, products, line, rules):
            cuts.append(cut)
            grade, share = None, 0.0
            if grading:
                if core is not None:
                    share = _core_share(fl, cut.choice, Shifted(core, dy) if fl.on_cant else core)
                grade = _grade(products, log, cut.choice.thickness.dry, cut.choice.width.dry, share, rng)
            boards.append(_board(cut, lay, sec, products, grade, share))
    boards.sort(key=lambda b: (b.board_type, b.board_no, b.piece))
    volume = log_volume_m3(log, settings)
    dust = sawdust_volume(lay, sec, cuts, line, cant)
    wet = sum(b.wet_volume for b in boards)
    return LogResult(log, boards, volume, dust, volume - wet - dust, dy)


def simulate_pattern(logs: list[Log], primary: str, secondary: str, products: Products,
                     line: ProductionLine, settings: Settings, log_price: float = 0.0,
                     rules: Rules | None = None) -> PatternResult:
    pattern = notation.parse(primary, secondary)
    lay = layout(pattern, products, line)
    results = [simulate_log(log, pattern, products, line, settings, rules, lay) for log in logs]
    return PatternResult(primary, secondary, results, log_price, settings.chip_price,
                         settings.sawdust_price, settings.pct_fines)


def check_pattern(primary: str, secondary: str, products: Products, line: ProductionLine) -> list[str]:
    """Plain-language problems that stop this pattern being sawn on this line; empty when it can be."""
    try:
        pattern = notation.parse(primary, secondary)
    except notation.PatternError as e:
        return [str(e)]
    problems: list[str] = []
    items = (*pattern.primary.left.items, *pattern.primary.right.items, *pattern.secondary.items)
    if pattern.primary.cant is not None:
        try:
            products.width(pattern.primary.cant)
        except KeyError:
            problems.append(f"cant width {pattern.primary.cant:g} mm is not a width in this dataset")
        if not pattern.secondary.items:
            problems.append("a cant pattern needs a secondary pattern (the boards across the cant)")
    else:
        if not pattern.primary.left.items:
            problems.append("type a primary pattern")
        if pattern.secondary.items:
            problems.append("live sawing (no cant) takes no secondary pattern: every board comes off the primary saw")
    for item in items:
        try:
            products.thickness(item.thickness)
        except KeyError:
            msg = f"thickness {item.thickness:g} mm is not a thickness in this dataset"
            if msg not in problems:
                problems.append(msg)
        if item.width is not None:
            try:
                products.width(item.width)
            except KeyError:
                msg = f"width {item.width:g} mm is not a width in this dataset"
                if msg not in problems:
                    problems.append(msg)
    if any(i.width is not None for i in items) and line.saw_type not in (SawType.CHIPPER_PROFILER,
                                                                         SawType.CHIPPER_PROFILER_GROUPED):
        problems.append("boards with a fixed width (such as 25x76) need a chipper-profiler production line")
    arris = pattern.secondary.arris_after
    if arris is not None and arris >= len(pattern.secondary.items) - 1:
        problems.append("the arris comma must sit between two boards")
    if problems:
        return problems
    try:
        layout(pattern, products, line)
    except (KeyError, ValueError) as e:
        problems.append(str(e).strip("'\""))
    return problems
