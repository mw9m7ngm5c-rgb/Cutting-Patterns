"""Edger, cross-cut and wane test: the best board that can be cut from one flitch.

A flitch is the piece of wood between two parallel saw planes. Its thickness direction is called v
and its width direction u; for a cant board v is y and u is x, for a sideboard v is x and u is y.
The caller supplies ``chord(v)``: for a plane at height v, where the wood starts and ends along u at
every disc (already clipped to the cant faces for cant boards).

Wane test (ASSUMPTIONS A-07, fitted to the Test1 run). At each corner of the board's cross-section
the bark may cut the corner off. Measure how far the cut runs down the edge (wane depth) and how far
it runs in along the face (wane width). The corner passes when

    wane depth / allowed depth  +  wane width / allowed width  <=  1

with allowed depth  = thickness_pct of the dry thickness, and
     allowed width  = half of width_pct of the dry width (the percentage is shared by the two edges).

For one disc that limits where each edge may sit, so the allowed positions of the board form one
interval per disc; a board exists over a run of discs when those intervals overlap.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from .model import EdgingObjective, Products, Rules, Size

_EPS = 1e-6
Chord = Callable[[float], tuple[np.ndarray, np.ndarray]]


@dataclass(frozen=True)
class Choice:
    thickness: Size
    width: Size
    v_lo: float
    v_hi: float
    u0: float             # position of the board's first edge along u
    first: int            # first disc of the clear span
    last: int             # last disc of the clear span
    length_mm: int
    score: tuple
    wane_discs: int = 0


@dataclass
class Ladder:
    """Chords of the flitch at 0, 1/K ... 1 of the allowed wane depth in from one face.
    lo[k], hi[k] are where the wood starts and ends along u at step k, per disc (k = 0 is the face)."""
    lo: np.ndarray        # (K + 1, n_discs)
    hi: np.ndarray
    share: np.ndarray     # (K + 1, 1) depth share used at each step
    out_lo: np.ndarray    # how far the wood reaches beyond the face's own end at each step
    out_hi: np.ndarray


def depth_ladder(chord: Chord, face: float, inward: float, depth: float, steps: int) -> Ladder:
    """inward is +1 or -1: the direction from the face into the board."""
    if depth <= _EPS or steps < 1:
        chords = [chord(face)]
    else:
        chords = [chord(face + inward * depth * k / steps) for k in range(steps + 1)]
    lo = np.stack([c[0] for c in chords])
    hi = np.stack([c[1] for c in chords])
    k = len(chords) - 1
    share = (np.arange(k + 1) / k if k else np.zeros(1))[:, None]
    with np.errstate(invalid="ignore"):
        out_lo, out_hi = lo[0] - lo, hi - hi[0]
    return Ladder(lo, hi, share, out_lo, out_hi)


def _edge_limit(ends: np.ndarray, out: np.ndarray, share: np.ndarray, allowed_width: float) -> np.ndarray:
    """Furthest position an edge may take on one side of a face, per disc.

    If the edge sits where the wood ends at ladder step k, the wane depth is share[k] of the allowed
    depth and the wane width is out[k]. Walk down the ladder to where the two shares add up to 1 and
    interpolate. NaN where the face itself has no wood.
    """
    steps = ends.shape[0] - 1
    with np.errstate(invalid="ignore"):
        used = share + out / allowed_width
    used = np.where(np.isfinite(used), used, np.inf)
    idx = np.clip((used <= 1.0 + _EPS).sum(axis=0) - 1, 0, steps - 1)
    cols = np.arange(ends.shape[1])
    m0, m1 = used[idx, cols], used[idx + 1, cols]
    e0, e1 = ends[idx, cols], ends[idx + 1, cols]
    with np.errstate(invalid="ignore", divide="ignore"):
        frac = np.clip((1.0 - m0) / (m1 - m0), 0.0, 1.0)
        frac = np.where(np.isfinite(frac), frac, 0.0)
        pos = e0 + frac * (e1 - e0)
    return np.where(np.isfinite(e0) & np.isfinite(pos), pos, np.nan)


def face_interval(ladder: Ladder, board_width: float, allowed_width: float) -> tuple[np.ndarray, np.ndarray]:
    """Allowed positions [lo, hi] of the board's first edge at every disc, as far as one face goes.
    An impossible disc comes back as lo = +inf, hi = -inf."""
    if ladder.lo.shape[0] == 1 or allowed_width <= _EPS:
        return ladder.lo[0], ladder.hi[0] - board_width      # no wane: the board must lie on the face's wood
    lo_edge = _edge_limit(ladder.lo, ladder.out_lo, ladder.share, allowed_width)
    hi_edge = _edge_limit(ladder.hi, ladder.out_hi, ladder.share, allowed_width)
    lo = np.where(np.isnan(lo_edge), np.inf, lo_edge)
    hi = np.where(np.isnan(hi_edge), -np.inf, hi_edge) - board_width
    return lo, hi


def longest_run(lo: np.ndarray, hi: np.ndarray, z_mm: np.ndarray) -> tuple[int, int, float, float] | None:
    """Longest stretch of discs whose intervals [lo, hi] share a common point.

    Returns (first, last, common_lo, common_hi), or None when no disc has a non-empty interval.
    Ties go to the stretch nearest the small end.
    """
    n = len(lo)
    idx = np.arange(n)
    upper = idx[None, :] >= idx[:, None]
    run_lo = np.maximum.accumulate(np.where(upper, lo[None, :], -np.inf), axis=1)
    run_hi = np.minimum.accumulate(np.where(upper, hi[None, :], np.inf), axis=1)
    ok = upper & (run_lo <= run_hi + _EPS)
    count = ok.sum(axis=1)
    if not count.any():
        return None
    last = idx + count - 1
    span = np.where(count > 0, z_mm[np.clip(last, 0, n - 1)] - z_mm, -1)
    first = int(np.argmax(span))
    j = int(last[first])
    return first, j, float(run_lo[first, j]), float(run_hi[first, j])


def _score(objective: EdgingObjective, thickness: Size, width: Size, length_mm: int, price: float,
           prefer_wider: bool) -> tuple:
    volume = thickness.dry * width.dry * length_mm
    tie = width.dry if prefer_wider else -width.dry
    if objective == EdgingObjective.LENGTH:
        return (length_mm, volume, tie)
    if objective == EdgingObjective.VALUE:
        return (volume * price, volume, tie)
    return (volume, tie)


def width_interval(chord: Chord, z_mm: np.ndarray, v_lo: float, v_hi: float, thickness: Size, width: Size,
                   products: Products, rules: Rules, ladders: dict) -> tuple[np.ndarray, np.ndarray, float]:
    """Where the first edge of a board of this width may lie at every disc, as far as the wane rule for
    the product allows: (lo, hi, allowed wane depth). An impossible disc has lo = +inf, hi = -inf.
    ``width`` gives the wane rule (by its dry size) and the board's real width (its wet size)."""
    rule = products.wane_rule(thickness.dry, width.dry)
    t_ref = thickness.wet if rules.wane_on_wet_sizes else thickness.dry
    w_ref = width.wet if rules.wane_on_wet_sizes else width.dry
    depth = rule.thickness_pct / 100.0 * t_ref
    allow = rule.width_pct / 100.0 * w_ref * rules.width_wane_edge_share
    if rule.length_wane <= 0 or depth <= _EPS or allow <= _EPS:
        depth = allow = 0.0                    # no wane at all
    depth = min(depth, (v_hi - v_lo) / 2.0)
    key = (round(depth, 6), round(v_lo, 6), round(v_hi, 6))
    if key not in ladders:
        ladders[key] = (depth_ladder(chord, v_lo, +1.0, depth, rules.wane_ladder),
                        depth_ladder(chord, v_hi, -1.0, depth, rules.wane_ladder))
    lo_face, hi_face = ladders[key]
    lo1, hi1 = face_interval(lo_face, width.wet, allow)
    lo2, hi2 = face_interval(hi_face, width.wet, allow)
    return np.maximum(lo1, lo2), np.minimum(hi1, hi2), depth


def best_board(chord: Chord, z_mm: np.ndarray, v_lo: float, v_hi: float, thickness: Size,
               widths: list[Size], products: Products, objective: EdgingObjective, rules: Rules,
               fixed_u0: float | None = None, cache: dict | None = None) -> Choice | None:
    """Best board of the given thickness with faces at v_lo and v_hi, over the candidate widths.

    For each width: find the longest clear span, cross-cut it down to the longest allowed length, and
    score it by the edging objective. Returns None when no width gives a board of the minimum length.
    fixed_u0 pins the board's first edge (a chipper-profiler cuts the width, not the edger).
    cache: share the depth ladders between calls on the same chord (the caller guarantees that).
    """
    best: Choice | None = None
    ladders: dict = cache if cache is not None else {}
    full_span = int(z_mm[-1] - z_mm[0])
    # the longest board any candidate could give from this log
    cap = max((x for w_ in widths for x in products.allowed_lengths_mm(thickness.dry, w_.dry) if x <= full_span),
              default=0)
    for width in sorted(widths, key=lambda s: -s.wet):
        lengths = products.allowed_lengths_mm(thickness.dry, width.dry)
        if not lengths:
            continue
        rule = products.wane_rule(thickness.dry, width.dry)
        lo_all, hi_all, depth = width_interval(chord, z_mm, v_lo, v_hi, thickness, width, products, rules, ladders)
        w = width.wet
        lo_face, hi_face = ladders[(round(depth, 6), round(v_lo, 6), round(v_hi, 6))]
        if fixed_u0 is not None:
            ok = (lo_all <= fixed_u0 + _EPS) & (fixed_u0 <= hi_all + _EPS)
            lo_all, hi_all = np.where(ok, fixed_u0, np.inf), np.where(ok, fixed_u0, -np.inf)
        run = longest_run(lo_all, hi_all, z_mm)
        if run is None:
            continue
        first, last, c_lo, c_hi = run
        c_hi = max(c_hi, c_lo)
        u0 = c_hi if rules.placement == "high" else c_lo if rules.placement == "low" else (c_lo + c_hi) / 2.0
        wane_discs = 0
        if depth > 0 and 0 < rule.length_wane < 100 and rule.length_wane_type == 0:
            first, last, wane_discs = _limit_wane_length((lo_face.lo[0], lo_face.hi[0]), (hi_face.lo[0], hi_face.hi[0]),
                                                         w, u0, first, last, rule.length_wane / 100.0)
            if last < first:
                continue
        span = int(z_mm[last] - z_mm[first])
        fit = [length for length in lengths if length <= span]
        if not fit:
            continue
        length = fit[-1]
        price = products.price(thickness.dry, width.dry, length)
        score = _score(objective, thickness, width, length, price, rules.prefer_wider_on_tie)
        if best is None or score > best.score:
            best = Choice(thickness, width, v_lo, v_hi, u0, first, last, length, score, wane_discs)
        if objective != EdgingObjective.VALUE and length >= cap:
            break          # widths run from wide to narrow: nothing narrower can beat a full-length board
    return best


def _limit_wane_length(face_a, face_b, w: float, u0: float, first: int, last: int, share: float):
    """Shorten the run from its waney ends until wane shows on at most ``share`` of its discs.
    Greedy, and so an approximation for length-wane values strictly between 0 and 100."""
    clean_lo = np.maximum(face_a[0], face_b[0])
    clean_hi = np.minimum(face_a[1], face_b[1]) - w
    waney = ~((clean_lo <= u0 + _EPS) & (u0 <= clean_hi + _EPS))
    while last >= first:
        n = last - first + 1
        bad = int(waney[first:last + 1].sum())
        if bad <= share * n + _EPS:
            return first, last, bad
        a = 0
        while first + a <= last and waney[first + a]:
            a += 1
        b = 0
        while last - b >= first and waney[last - b]:
            b += 1
        if a == 0 and b == 0:          # wane only in the middle: give up a disc at the small end
            first += 1
        elif b == 0 or (a > 0 and a <= b):
            first += 1                 # the shorter waney end goes first
        else:
            last -= 1
    return first, last, 0


def _runs(ok: np.ndarray, z_mm: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """For each row of ok (rows x discs): the longest stretch of True discs as (first, last, span mm).
    Ties go to the stretch nearest the small end; a row with no True disc has span -1."""
    rows = ok.shape[0]
    first = np.zeros(rows, dtype=int)
    last = np.zeros(rows, dtype=int)
    best = np.full(rows, -1.0)
    edges = np.diff(np.pad(ok.astype(np.int8), ((0, 0), (1, 1))), axis=1)
    s_row, s_col = np.nonzero(edges == 1)           # a stretch starts here ...
    _, e_col = np.nonzero(edges == -1)              # ... and ends just before here (same order)
    if not len(s_row):
        return first, last, best
    z = z_mm.astype(float)
    span = z[e_col - 1] - z[s_col]
    order = np.lexsort((s_col, -span, s_row))       # per row: longest first, then nearest the small end
    r = s_row[order]
    top = order[np.r_[True, r[1:] != r[:-1]]]
    first[s_row[top]] = s_col[top]
    last[s_row[top]] = e_col[top] - 1
    best[s_row[top]] = span[top]
    return first, last, best


def fixed_edger(chord: Chord, z_mm: np.ndarray, v_lo: float, v_hi: float, thickness: Size,
                pieces: list[tuple[float, Size | None]], products: Products, objective: EdgingObjective,
                rules: Rules, cache: dict | None = None) -> list[Choice]:
    """An edger whose blades are fixed at set distances apart (ASSUMPTIONS A-61).

    pieces: one per gap between neighbouring blades, as (offset of the gap's first edge from the
    first gap's first edge, product it makes), the product's wet size being the gap; None for a gap
    that makes no product of this thickness. All blades cut together; the flitch is moved across the
    blades to wherever the boards it gives are best by the edging objective. Every gap whose piece
    passes the wane rule over a valid length becomes a board; the rest is offcut.
    Returns the boards (an empty list when none can be made)."""
    ladders = cache if cache is not None else {}
    usable = [(i, off, w) for i, (off, w) in enumerate(pieces) if w is not None
              and products.allowed_lengths_mm(thickness.dry, w.dry)]
    if not usable:
        return []
    spans = []
    for i, off, w in usable:
        lo, hi, _ = width_interval(chord, z_mm, v_lo, v_hi, thickness, w, products, rules, ladders)
        spans.append((i, off, w, lo - off, hi - off))     # allowed positions of the first gap's edge
    ends = np.concatenate([np.concatenate([lo[np.isfinite(lo)], hi[np.isfinite(hi)]]) for _, _, _, lo, hi in spans])
    if not len(ends):
        return []
    # the boards only change where some gap's allowance starts or stops, so those positions (and the
    # points halfway between them) cover every case
    u = np.unique(np.round(ends, 1))
    u = np.unique(np.concatenate([u, (u[1:] + u[:-1]) / 2.0])) if len(u) > 1 else u
    total = np.zeros(len(u))
    tie = np.zeros(len(u))
    found = []
    for i, off, w, lo, hi in spans:
        ok = (lo[None, :] <= u[:, None] + _EPS) & (u[:, None] <= hi[None, :] + _EPS)
        first, last, span = _runs(ok, z_mm)
        lengths = np.asarray(sorted(products.allowed_lengths_mm(thickness.dry, w.dry)), dtype=float)
        idx = np.searchsorted(lengths, span + 1e-6, side="right") - 1      # longest allowed length that fits
        fit = np.where(idx >= 0, lengths[np.maximum(idx, 0)], 0.0)
        vol = thickness.dry * w.dry * fit
        if objective == EdgingObjective.VALUE:
            price = {x: products.price(thickness.dry, w.dry, int(x)) for x in np.unique(fit) if x > 0}
            gain = np.array([vol[k] * price.get(fit[k], 0.0) for k in range(len(u))])
        elif objective == EdgingObjective.LENGTH:
            gain = fit.astype(float)
        else:
            gain = vol.astype(float)
        total += gain
        tie += vol
        found.append((i, off, w, first, last, fit))
    score = total + 1e-9 * tie
    if score.max() <= 0:
        return []
    # of equally good positions take the middle of the widest unbroken stretch of them, so the flitch
    # sits centred on the blades as far as the boards allow
    top = score >= score.max() - 1e-9
    runs, start = [], None
    for j, on in enumerate(top):
        if on and start is None:
            start = j
        if (not on or j == len(top) - 1) and start is not None:
            stop = j if on else j - 1
            runs.append((u[stop] - u[start], start, stop))
            start = None
    _, a, b = max(runs)
    mid = (u[a] + u[b]) / 2.0
    k = a + int(np.argmin(np.abs(u[a:b + 1] - mid)))
    out = []
    for i, off, w, first, last, fit in found:
        if fit[k] > 0:
            length = int(fit[k])
            price = products.price(thickness.dry, w.dry, length)
            out.append(Choice(thickness, w, v_lo, v_hi, float(u[k] + off), int(first[k]), int(last[k]), length,
                              _score(objective, thickness, w, length, price, rules.prefer_wider_on_tie)))
    return out
