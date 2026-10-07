"""Pattern generator: enumerate cant-sawing patterns, pre-screen them on straight tapered logs,
simulate the best on real logs and rank them. Also the diameter chart and class-boundary suggestions.

Three steps for one log class (or one diameter):

1. Enumerate. Every cant width; 0 to N sideboards a side; every stack of thicknesses across the cant
   whose wet height plus kerfs fits the largest log, and that does not leave room for another board
   on each side of the smallest log. Constraints (symmetry, thicker boards towards the centre,
   blades per saw, distinct thicknesses, products to include or exclude) prune as early as they can.
2. Pre-screen. Saw each candidate on straight, round, tapered logs at the class's small-end
   diameters, with a closed-form version of the engine's wane test. Cheap, and the same flitch
   positions repeat across candidates, so each is computed once.
3. Simulate the best few with the full engine on the class's logs and rank by the chosen objective.

Everything here is deterministic and uses no randomness.
"""
from __future__ import annotations

import dataclasses
import math
import statistics
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Iterator

from . import notation
from .model import Log, PatternResult, Products, ProductionLine, Settings, Size
from .sawing import check_pattern, layout, simulate_pattern


class Objective(str, Enum):
    VOLUME = "volume"       # dry volume recovery
    VALUE = "value"         # nett value recovery (R per m3 of log)
    TARGET = "target"       # dry volume of one target product


OBJECTIVE_LABELS = {Objective.VOLUME: "Dry volume recovery", Objective.VALUE: "Nett value recovery",
                    Objective.TARGET: "Volume of a target product"}


@dataclass(frozen=True)
class Constraints:
    symmetric: bool = True                 # same sideboards both sides; secondary reads the same both ways
    thicker_to_centre: bool = True         # boards never get thicker moving out from the centre
    max_sideboards_per_side: int = 2
    max_primary_blades: int | None = None  # saw lines on the primary saw (sideboards + 2)
    max_secondary_blades: int | None = None  # saw lines on the secondary saw (cant boards + 1)
    max_thicknesses: int | None = 3        # different thicknesses in one pattern
    cant_widths: tuple[float, ...] | None = None   # dry widths allowed as the cant; None = every width
    must_include: tuple[tuple[float, float], ...] = ()   # products (t, w) every pattern must yield
    exclude: tuple[tuple[float, float], ...] = ()        # products never to cut
    target: tuple[float, float] | None = None            # product for the TARGET objective and min share
    min_target_share: float = 0.0          # share (0-1) of the dry board volume that must be the target
    fill_face: bool = True                 # drop stacks that leave room for another board on each side
    max_candidates: int = 400_000          # stop enumerating beyond this and say so


@dataclass(frozen=True)
class Candidate:
    left: tuple[float, ...]       # sideboards as written: outermost first
    cant: float
    right: tuple[float, ...]      # sideboards as written: next to the cant first
    secondary: tuple[float, ...]  # bottom to top

    @property
    def primary_text(self) -> str:
        return notation.serialise_primary(self._pattern().primary)

    @property
    def secondary_text(self) -> str:
        return notation.serialise_stack(self._pattern().secondary)

    def _pattern(self) -> notation.Pattern:
        st = lambda ts: notation.Stack(tuple(notation.Item(t) for t in ts))
        return notation.Pattern(notation.Primary(st(self.left), self.cant, st(self.right)), st(self.secondary))

    @property
    def thicknesses(self) -> set[float]:
        return set(self.left) | set(self.right) | set(self.secondary)

    @property
    def primary_blades(self) -> int:
        return len(self.left) + len(self.right) + 2

    @property
    def secondary_blades(self) -> int:
        return len(self.secondary) + 1


@dataclass
class Ranked:
    candidate: Candidate
    prescreen: float
    result: PatternResult | None = None
    score: float = 0.0
    target_volume: float = 0.0
    target_share: float = 0.0

    @property
    def primary(self) -> str:
        return self.candidate.primary_text

    @property
    def secondary(self) -> str:
        return self.candidate.secondary_text


@dataclass
class GeneratorResult:
    ranked: list[Ranked]
    enumerated: int
    prescreened: int
    simulated: int
    diameters_mm: list[float]
    length_m: float
    logs: int
    truncated: bool = False
    notes: list[str] = field(default_factory=list)


class GeneratorError(ValueError):
    pass


# ------------------------------------------------------------------ products the generator may use

def restricted_products(products: Products, c: Constraints) -> Products:
    """The dataset's products with the excluded ones switched off."""
    if not c.exclude:
        return products
    ex = {(float(t), float(w)) for t, w in c.exclude}
    combos = [dataclasses.replace(x, valid=False) if (x.thickness, x.width) in ex else x for x in products.combinations]
    return dataclasses.replace(products, combinations=combos)


def usable_thicknesses(products: Products) -> list[Size]:
    return [t for t in products.thicknesses if products.valid_widths(t.dry)]


# ------------------------------------------------------------------ enumeration

def _runs(sizes: list[Size], kerf: float, budget: float, max_len: int, nonincreasing: bool,
          prefix: tuple = ()) -> Iterator[tuple[Size, ...]]:
    """Sequences of sizes (each costing wet + kerf) within the budget, optionally never increasing."""
    yield prefix
    if len(prefix) >= max_len:
        return
    for s in sizes:
        if nonincreasing and prefix and s.wet > prefix[-1].wet + 1e-9:
            continue
        cost = s.wet + kerf
        if cost <= budget + 1e-9:
            yield from _runs(sizes, kerf, budget - cost, max_len, nonincreasing, prefix + (s,))


def _height(stack: tuple[Size, ...], kerf: float) -> float:
    return sum(s.wet for s in stack) + kerf * max(0, len(stack) - 1)


def _stacks(sizes: list[Size], kerf: float, max_h: float, c: Constraints) -> Iterator[tuple[Size, ...]]:
    """Secondary stacks, bottom to top, no taller than max_h."""
    max_n = (c.max_secondary_blades - 1) if c.max_secondary_blades else 10 ** 6
    if c.symmetric:
        # half reads from the centre outward; the stack is mirror(half) [+ centre board] + half
        for half in _runs(sizes, kerf, max_h / 2.0, max_n // 2, c.thicker_to_centre):
            if half:
                st = tuple(reversed(half)) + half
                if len(st) <= max_n and _height(st, kerf) <= max_h + 1e-9:
                    yield st
            for mid in sizes:
                if c.thicker_to_centre and half and mid.wet < half[0].wet - 1e-9:
                    continue
                st = tuple(reversed(half)) + (mid,) + half
                if len(st) <= max_n and _height(st, kerf) <= max_h + 1e-9:
                    yield st
    else:
        # any sequence; with thicker_to_centre it must rise to one peak and fall again
        def build(prefix: tuple, falling: bool) -> Iterator[tuple]:
            if prefix:
                yield prefix
            if len(prefix) >= max_n:
                return
            for s in sizes:
                fall = falling
                if c.thicker_to_centre and prefix:
                    if s.wet < prefix[-1].wet - 1e-9:
                        fall = True
                    elif s.wet > prefix[-1].wet + 1e-9 and falling:
                        continue
                st = prefix + (s,)
                if _height(st, kerf) <= max_h + 1e-9:
                    yield from build(st, fall)
        yield from build((), False)


def enumerate_candidates(products: Products, line: ProductionLine, c: Constraints, face_max_mm: float,
                         face_min_mm: Callable[[float], float]) -> tuple[list[Candidate], bool]:
    """All candidates within the constraints. face_max_mm: the tallest stack any log could take.
    face_min_mm(cant_wet): height of the cant face on the smallest log (for fill_face).
    Returns (candidates, truncated)."""
    sizes = sorted(usable_thicknesses(products), key=lambda s: -s.wet)
    if not sizes:
        raise GeneratorError("no valid products: switch some products on (or exclude fewer)")
    sizes_up = list(reversed(sizes))
    thinnest = sizes_up[0]
    widths = [w for w in products.widths if c.cant_widths is None or any(abs(w.dry - x) < 1e-6 for x in c.cant_widths)]
    widths = [w for w in widths if w.wet < face_max_mm]
    k1, k2 = line.primary_kerf, line.secondary_kerf
    need = {float(t) for t, _ in c.must_include}
    max_side = c.max_sideboards_per_side
    stacks = list(_stacks(sizes, k2, face_max_mm, c))
    out: list[Candidate] = []
    truncated = False
    for w in widths:
        room = face_max_mm / 2.0 - w.wet / 2.0          # how far sideboards could reach
        sides = [s for s in _runs(sizes, k1, room, max(0, max_side), c.thicker_to_centre)]
        lo_face = face_min_mm(w.wet)
        ok_stacks = [st for st in stacks
                     if not (c.fill_face and _height(st, k2) + 2 * (thinnest.wet + k2) <= lo_face)]
        for right in sides:
            lefts = [tuple(reversed(right))] if c.symmetric else [tuple(reversed(x)) for x in sides]
            for left in lefts:
                if c.max_primary_blades and len(left) + len(right) + 2 > c.max_primary_blades:
                    continue
                side_t = {s.dry for s in left} | {s.dry for s in right}
                for st in ok_stacks:
                    ts = side_t | {s.dry for s in st}
                    if c.max_thicknesses and len(ts) > c.max_thicknesses:
                        continue
                    if need and not need <= ts:
                        continue
                    out.append(Candidate(tuple(s.dry for s in left), w.dry, tuple(s.dry for s in right),
                                         tuple(s.dry for s in st)))
                    if len(out) >= c.max_candidates:
                        return out, True
    return out, truncated


# ------------------------------------------------------------------ pre-screen on straight tapered logs

class _Cone:
    """Closed-form sawing of straight, round logs with a constant taper. Mirrors the engine's rules for
    the best board from a flitch (wane test A-07, widths, centre boards, resaw keeping the inner face)
    without discs: a board passes the wane test wherever the log is at least a certain radius, so its
    clear length runs from that point to the large end. That radius depends only on the flitch and the
    width, not on the log, so it is worked out once and reused for every candidate and diameter."""

    def __init__(self, length_mm: int, taper_mm_per_m: float, products: Products, line: ProductionLine):
        self.L = length_mm
        self.taper = max(taper_mm_per_m, 0.0)
        self.p = products
        self.line = line
        self.need: dict = {}       # (lo, hi, t, w) -> smallest radius at which the board passes
        self.memo: dict = {}
        self.thinner = {t.dry: sorted((x for x in usable_thicknesses(products) if x.wet < t.wet - 1e-6),
                                      key=lambda s: -s.dry) for t in products.thicknesses}
        self.lengths = {t.dry: {w.dry: products.allowed_lengths_mm(t.dry, w.dry) for w in products.widths}
                        for t in products.thicknesses}

    def _corner_ok(self, R: float, face: float, half_w: float, t: Size, w: Size) -> bool:
        o = abs(face)
        if half_w * half_w + o * o <= R * R:
            return True
        if half_w >= R or o >= R:
            return False
        rule = self.p.wane_rule(t.dry, w.dry)
        ad = rule.thickness_pct / 100.0 * t.dry
        aw = rule.width_pct / 100.0 * w.dry / 2.0
        if ad <= 0 or aw <= 0:
            return False
        depth = o - math.sqrt(R * R - half_w * half_w)
        width = half_w - math.sqrt(R * R - o * o)
        return depth <= t.wet and depth / ad + width / aw <= 1.0 + 1e-9

    def _radius_needed(self, lo: float, hi: float, t: Size, w: Size) -> float:
        key = (round(lo, 3), round(hi, 3), t.dry, w.dry)
        if key not in self.need:
            faces = [hi] if lo >= 0 else [lo] if hi <= 0 else [lo, hi]
            half = w.wet / 2.0
            a, b = 0.0, max(math.hypot(half, f) for f in faces)      # at b the corners are in the wood
            ok = lambda R: all(self._corner_ok(R, f, half, t, w) for f in faces)
            for _ in range(40):
                m = (a + b) / 2.0
                a, b = (a, m) if ok(m) else (m, b)
            self.need[key] = b
        return self.need[key]

    def _clear_length(self, r_need: float, r0: float) -> float:
        if r_need <= r0:
            return self.L
        if self.taper <= 0:
            return 0.0
        z = (r_need - r0) * 2.0 / self.taper * 1000.0          # mm from the small end
        return max(0.0, self.L - z)

    def _best(self, lo: float, hi: float, t: Size, cant: Size | None, r0: float):
        """(dry volume m3, value R, thickness, width) of the best board on this flitch, by volume."""
        best = (0.0, 0.0, 0.0, 0.0)
        for w in self.p.valid_widths(t.dry):
            full = cant is not None and abs(w.wet - cant.wet) < 1e-6
            if cant is not None and w.wet > cant.wet + 1e-6:
                continue
            if (t.dry, w.dry) in self.p.centre_boards and not full:
                continue
            clear = self._clear_length(self._radius_needed(lo, hi, t, w), r0)
            ok = [x for x in self.lengths[t.dry][w.dry] if x <= clear + 1e-6]
            if not ok:
                continue
            vol = t.dry * w.dry * max(ok) / 1e9
            if vol > best[0] + 1e-12 or (abs(vol - best[0]) <= 1e-12 and w.dry > best[3]):
                best = (vol, vol * self.p.price(t.dry, w.dry, max(ok)), t.dry, w.dry)
        return best

    def board(self, kind: str, lo: float, hi: float, t: Size, cant: Size | None, r0: float):
        key = (kind, round(lo, 3), round(hi, 3), t.dry, cant.dry if cant else None, r0)
        if key in self.memo:
            return self.memo[key]
        b = self._best(lo, hi, t, cant, r0)
        resaw = self.line.secondary_resaw if kind == "cant" else self.line.primary_resaw
        if not b[0] and resaw and not (lo < 0 < hi):
            inner_lo = abs(lo) <= abs(hi)
            for t2 in self.thinner.get(t.dry, []):
                l2, h2 = (lo, lo + t2.wet) if inner_lo else (hi - t2.wet, hi)
                b2 = self._best(l2, h2, t2, cant, r0)
                if b2[0] > b[0]:
                    b = b2
        self.memo[key] = b
        return b

    def volume(self, r0: float) -> float:
        """Log volume as the engine's nominal formula would give it: pi/4 x mid-length diameter^2 x L."""
        d_mid = 2 * r0 + self.taper * self.L / 2000.0
        return math.pi / 4.0 * d_mid * d_mid * self.L / 1e9


def _prescreen_score(lay, cone: _Cone, r0: float, objective: Objective, target) -> tuple[float, float, float]:
    """(objective score, recovery, target share) on one tapered log of small-end radius r0."""
    vol = val = tgt = 0.0
    for fl in lay.flitches:
        if fl.kind == "cant":
            b = cone.board("cant", fl.lo, fl.hi, fl.thickness, lay.cant, r0)
        else:   # a round log is the same on both sides: saw every sideboard as if on the right
            lo, hi = (fl.lo, fl.hi) if fl.lo >= 0 else (-fl.hi, -fl.lo)
            b = cone.board("side", lo, hi, fl.thickness, None, r0)
        vol += b[0]
        val += b[1]
        if target and (b[2], b[3]) == target:
            tgt += b[0]
    v = cone.volume(r0)
    rec = vol / v
    share = tgt / vol if vol else 0.0
    score = {Objective.VOLUME: rec, Objective.VALUE: val / v, Objective.TARGET: tgt / v + 1e-3 * rec}[objective]
    return score, rec, share


def prescreen(cands: list[Candidate], products: Products, line: ProductionLine, diameters_mm: list[float],
              length_mm: int, taper_mm_per_m: float, objective: Objective, c: Constraints,
              progress: Callable[[int, int], None] | None = None,
              cancelled: Callable[[], bool] | None = None) -> list[tuple[float, Candidate]]:
    cone = _Cone(length_mm, taper_mm_per_m, products, line)
    target = (float(c.target[0]), float(c.target[1])) if c.target else None
    out = []
    for i, cand in enumerate(cands):
        if cancelled and i % 2000 == 0 and cancelled():
            break
        if progress and i % 2000 == 0:
            progress(i, len(cands))
        lay = layout(cand._pattern(), products, line)
        scores = [_prescreen_score(lay, cone, d / 2.0, objective, target) for d in diameters_mm]
        score = sum(s[0] for s in scores) / len(scores)
        if c.min_target_share > 0 and target:
            share = sum(s[2] for s in scores) / len(scores)
            if share < 0.8 * c.min_target_share:       # loose: the full simulation decides
                continue
        if score > 0:
            out.append((score, cand))
    out.sort(key=lambda x: (-x[0], x[1].primary_blades + x[1].secondary_blades))
    return out


# ------------------------------------------------------------------ full simulation and ranking

def _target_volume(res: PatternResult, target) -> float:
    if not target:
        return 0.0
    return res.product_mix().get((float(target[0]), float(target[1])), {}).get("dry_volume", 0.0)


def rank_score(res: PatternResult, objective: Objective, target) -> float:
    if objective == Objective.VALUE:
        return res.nett_value_recovery
    if objective == Objective.TARGET:
        v = res.log_volume
        return (_target_volume(res, target) / v if v else 0.0) + 1e-3 * res.dry_recovery
    return res.dry_recovery


def _sample(logs: list[Log], n: int) -> list[Log]:
    if len(logs) <= n:
        return logs
    srt = sorted(logs, key=lambda g: (g.sed_cm, g.no))
    return [srt[round(i * (len(srt) - 1) / (n - 1))] for i in range(n)]


def class_geometry(logs: list[Log]) -> tuple[list[float], float, float, float, Callable[[float], float]]:
    """Pre-screen small-end diameters (mm), representative length (m) and taper (mm/m), tallest stack
    (mm), and the cant-face height at the small end of the smallest log for a given wet cant width."""
    seds = sorted(g.sed_cm for g in logs)
    diameters = sorted({seds[0] * 10, statistics.median(seds) * 10, seds[-1] * 10})
    length = statistics.median(g.length_m for g in logs)
    taper = statistics.median(g.taper_mm_per_m for g in logs)
    big = max((g.sed_cm * 10 + g.taper_mm_per_m * g.length_m) * math.sqrt(max(g.ovality, 1.0)) for g in logs)
    r_min = seds[0] * 10 / 2.0

    def face_min(cant_wet: float) -> float:
        h = cant_wet / 2.0
        return 2.0 * math.sqrt(r_min * r_min - h * h) if h < r_min else 0.0

    return diameters, length, taper, big, face_min


@dataclass(frozen=True)
class SimJob:
    """One simulation, picklable so the caller may run many in parallel processes."""
    logs: tuple[Log, ...]
    primary: str
    secondary: str
    products: Products
    line: ProductionLine
    settings: Settings
    log_price: float


def run_job(job: SimJob) -> PatternResult:
    return simulate_pattern(list(job.logs), job.primary, job.secondary, job.products, job.line, job.settings,
                            job.log_price)


# A blade that changes nothing should not win a tie: each saw line costs this much score
# (0.01 recovery points, or R0.01 per m3 for the value objective). ASSUMPTIONS A-48.
BLADE_PENALTY = {Objective.VOLUME: 1e-4, Objective.TARGET: 1e-4, Objective.VALUE: 0.01}


def _rank(cand: Candidate, ps: float, res: PatternResult, objective: Objective, target) -> Ranked:
    score = rank_score(res, objective, target) - BLADE_PENALTY[objective] * (cand.primary_blades + cand.secondary_blades)
    r = Ranked(cand, ps, res, score, _target_volume(res, target))
    dry = sum(x.dry_board_volume for x in res.logs)
    r.target_share = r.target_volume / dry if dry else 0.0
    return r


def generate(logs: list[Log], products: Products, line: ProductionLine, settings: Settings, log_price: float,
             objective: Objective = Objective.VOLUME, constraints: Constraints = Constraints(),
             simulate: int = 80, top: int = 10, sample_logs: int = 12,
             progress: Callable[[str, int, int], None] | None = None,
             cancelled: Callable[[], bool] | None = None,
             map_fn: Callable = map) -> GeneratorResult:
    """Best patterns for these logs.

    Pre-screen every candidate, simulate the best `simulate` of them on a stratified sample of
    `sample_logs` logs, then simulate the best `top` on every log and rank them. The pre-screen only
    discards clear losers: near the top its order is rough, while a 12-log sample ranks almost
    exactly like the whole class (docs/ASSUMPTIONS.md A-46). progress(stage, done, total) is called
    as work proceeds; map_fn lets the caller run the simulations in parallel (it must keep order)."""
    c = constraints
    if not logs:
        raise GeneratorError("no logs to saw: choose a class with logs, or a diameter")
    if objective == Objective.TARGET and not c.target:
        raise GeneratorError("choose the target product")
    if c.min_target_share > 0 and not c.target:
        raise GeneratorError("a minimum share needs a target product")
    probe = usable_thicknesses(products)
    if probe and products.widths:
        problems = check_pattern(f"/{products.widths[0].dry:g}/", f"{probe[0].dry:g}", products, line)
        if problems:
            raise GeneratorError(problems[0])
    prods = restricted_products(products, c)
    diameters, length_m, taper, face_max, face_min = class_geometry(logs)
    report = progress or (lambda *_: None)
    stop = cancelled or (lambda: False)
    report("enumerating", 0, 1)
    cands, truncated = enumerate_candidates(prods, line, c, face_max, face_min)
    notes = []
    if truncated:
        notes.append(f"Stopped enumerating at {len(cands):,} candidates; narrow the options to search them all.")
    screened = prescreen(cands, prods, line, diameters, round(length_m * 1000), taper, objective, c,
                         lambda i, n: report("pre-screening", i, n), cancelled)
    target = (float(c.target[0]), float(c.target[1])) if c.target else None

    def simulate_all(pairs, on_logs, stage):
        out = []
        batch = 8
        for i in range(0, len(pairs), batch):
            if stop():
                break
            report(stage, i, len(pairs))
            chunk = pairs[i:i + batch]
            jobs = [SimJob(tuple(on_logs), cd.primary_text, cd.secondary_text, prods, line, settings, log_price)
                    for _, cd in chunk]
            for (ps, cd), res in zip(chunk, map_fn(run_job, jobs)):
                out.append(_rank(cd, ps, res, objective, target))
        return out

    def keep(r: Ranked) -> bool:
        mix = r.result.product_mix()
        if any((float(t), float(w)) not in mix for t, w in c.must_include):
            return False
        return not (c.min_target_share > 0 and r.target_share < c.min_target_share - 1e-9)

    order = lambda r: -r.score
    shortlist = screened[:max(simulate, top)]
    sample = _sample(logs, sample_logs)
    if len(sample) < len(logs) and len(shortlist) > top:
        first = sorted(simulate_all(shortlist, sample, f"sawing a {len(sample)}-log sample"), key=order)
        finalists = [(r.prescreen, r.candidate) for r in first if keep(r)][:top]
        notes.append(f"{len(shortlist)} candidates sawn on a sample of {len(sample)} logs; "
                     f"the best {len(finalists)} then sawn on all {len(logs)} logs.")
    else:
        finalists = shortlist
    ranked = sorted((r for r in simulate_all(finalists, logs, "sawing every log") if keep(r)), key=order)[:top]
    report("done", 1, 1)
    return GeneratorResult(ranked, len(cands), len(screened), len(shortlist), diameters, length_m, len(logs),
                           truncated, notes)


# ------------------------------------------------------------------ diameter chart

def representative_logs(sed_cm: float, logs: list[Log], length_m: float | None = None) -> list[Log]:
    """Three ideal logs spanning one 1 cm step (sed, sed + 0.5, sed + 0.9 cm), with the median taper,
    sweep (mm/m), ovality and length of the dataset's logs."""
    if logs:
        taper = statistics.median(g.taper_mm_per_m for g in logs)
        sweep = statistics.median(g.sweep_mm_per_m for g in logs)
        ov = statistics.median(g.ovality for g in logs)
        length = length_m or statistics.median(g.length_m for g in logs)
    else:
        taper, sweep, ov, length = 10.0, 0.0, 1.0, length_m or 3.0
    return [Log(i + 1, round(sed_cm + d, 1), length, taper, round(sweep * length, 1), ov)
            for i, d in enumerate((0.0, 0.5, 0.9))]


@dataclass
class Step:
    sed_cm: float
    ranked: list[Ranked]

    @property
    def best(self) -> Ranked | None:
        return self.ranked[0] if self.ranked else None


@dataclass
class Group:
    from_cm: float
    to_cm: float            # inclusive top of the last step (e.g. 21.9)
    primary: str
    secondary: str
    steps: list[float]
    score: float = 0.0      # mean score of this pattern over the group's steps
    best: float = 0.0       # mean of each step's own best score (the most the group could get)


def pattern_key(r: Ranked) -> tuple[str, str]:
    return (r.primary, r.secondary)


def group_steps(steps: list[Step], tolerance: float = 0.0) -> list[Group]:
    """Suggest classes: run along the steps keeping the same pattern while, at each next step, it
    scores within `tolerance` of that step's best (same units as the score: 0.005 = half a point of
    recovery). A pattern that is not in a step's ranked list ends the group."""
    groups: list[Group] = []
    i = 0
    steps = [s for s in steps if s.best]
    while i < len(steps):
        # choose the pattern that carries furthest from this step, among the ones within tolerance here
        here = steps[i]
        best_run, best_r = 0, here.best
        for r in here.ranked:
            if here.best.score - r.score > tolerance + 1e-12:
                continue
            j = i + 1
            while j < len(steps):
                hit = next((x for x in steps[j].ranked if pattern_key(x) == pattern_key(r)), None)
                if hit is None or steps[j].best.score - hit.score > tolerance + 1e-12:
                    break
                j += 1
            if j - i > best_run or (j - i == best_run and r.score > best_r.score):
                best_run, best_r = j - i, r
        run = steps[i:i + best_run]
        groups.append(_group(run, best_r.primary, best_r.secondary))
        i += best_run
    return groups


def _group(run: list[Step], primary: str, secondary: str) -> Group:
    scores = [next(x.score for x in st.ranked if (x.primary, x.secondary) == (primary, secondary)) for st in run]
    return Group(run[0].sed_cm, round(run[-1].sed_cm + 0.9, 1), primary, secondary, [st.sed_cm for st in run],
                 sum(scores) / len(scores), sum(st.best.score for st in run) / len(run))


def best_classes(steps: list[Step], n_classes: int) -> list[Group]:
    """Split the steps into at most n_classes runs of neighbouring diameters, one pattern per run,
    so that the total score over all steps is as high as possible (exact, by dynamic programming).
    A pattern can only be chosen for a run if it was scored at every step of it."""
    steps = [st for st in steps if st.best]
    n = len(steps)
    if n == 0 or n_classes < 1:
        return []
    keys = sorted({pattern_key(r) for st in steps for r in st.ranked})
    score = [{pattern_key(r): r.score for r in st.ranked} for st in steps]
    # seg[i][j]: best (total, key) for steps i..j inclusive
    seg = [[(-math.inf, None)] * n for _ in range(n)]
    for k in keys:
        for i in range(n):
            total = 0.0
            for j in range(i, n):
                v = score[j].get(k)
                if v is None:
                    break
                total += v
                if total > seg[i][j][0]:
                    seg[i][j] = (total, k)
    K = min(n_classes, n)
    dp = [[-math.inf] * (n + 1) for _ in range(K + 1)]   # dp[c][j]: best total for the first j steps in c runs
    cut = [[0] * (n + 1) for _ in range(K + 1)]
    dp[0][0] = 0.0
    for c in range(1, K + 1):
        for j in range(1, n + 1):
            for i in range(c - 1, j):
                v = dp[c - 1][i] + seg[i][j - 1][0]
                if v > dp[c][j] + 1e-12:
                    dp[c][j], cut[c][j] = v, i
    c = max(range(1, K + 1), key=lambda c: (dp[c][n], -c))
    out, j = [], n
    while c > 0:
        i = cut[c][j]
        primary, secondary = seg[i][j - 1][1]
        out.append(_group(steps[i:j], primary, secondary))
        j, c = i, c - 1
    return list(reversed(out))


def diameter_chart(from_cm: int, to_cm: int, logs: list[Log], products: Products, line: ProductionLine,
                   settings: Settings, log_price: float | Callable[[float], float],
                   objective: Objective = Objective.VOLUME,
                   constraints: Constraints = Constraints(), simulate: int = 24, top: int = 10,
                   length_m: float | None = None,
                   progress: Callable[[str, int, int], None] | None = None,
                   cancelled: Callable[[], bool] | None = None, map_fn: Callable = map,
                   cross: int = 3) -> list[Step]:
    """Run the generator at every 1 cm step of small-end diameter from from_cm to to_cm inclusive.

    Then cross-check: the best `cross` patterns of every step are sawn at every other step too, so
    that each step's list scores every pattern that could carry a class across it. Without this a
    good pattern is often missing from its neighbour's top ten (crowded out by near-identical
    variants) and the suggested classes break up at every centimetre.

    log_price may be a function of the small-end diameter (cm), e.g. the price of the class it falls in."""
    price = log_price if callable(log_price) else (lambda _d: log_price)
    stop = cancelled or (lambda: False)
    steps, reps = [], []
    seds = list(range(int(from_cm), int(to_cm) + 1))
    for k, sed in enumerate(seds):
        if stop():
            break
        if progress:
            progress(f"searching at {sed} cm", k, len(seds))
        rep = representative_logs(float(sed), logs, length_m)
        reps.append(rep)
        try:
            res = generate(rep, products, line, settings, price(float(sed)), objective, constraints, simulate,
                           top, map_fn=map_fn)
            steps.append(Step(float(sed), res.ranked))
        except GeneratorError:
            steps.append(Step(float(sed), []))
    if cross and not stop():
        _cross_check(steps, reps, products, line, settings, price, objective, constraints, cross, progress, stop,
                     map_fn)
    return steps


def _cross_check(steps, reps, products, line, settings, price, objective, c, cross, progress, stop, map_fn):
    prods = restricted_products(products, c)
    target = (float(c.target[0]), float(c.target[1])) if c.target else None
    pool: dict[tuple[str, str], Candidate] = {}
    for st in steps:
        for r in st.ranked[:cross]:
            pool.setdefault(pattern_key(r), r.candidate)
    jobs, where = [], []
    for i, (st, rep) in enumerate(zip(steps, reps)):
        have = {pattern_key(r) for r in st.ranked}
        for key, cand in pool.items():
            if key not in have:
                jobs.append(SimJob(tuple(rep), cand.primary_text, cand.secondary_text, prods, line, settings,
                                   price(st.sed_cm)))
                where.append((i, cand))
    batch = 16
    for b in range(0, len(jobs), batch):
        if stop():
            return
        if progress:
            progress("cross-checking the best patterns at every diameter", b, len(jobs))
        for (i, cand), res in zip(where[b:b + batch], map_fn(run_job, jobs[b:b + batch])):
            steps[i].ranked.append(_rank(cand, 0.0, res, objective, target))
    for st in steps:
        st.ranked.sort(key=lambda r: -r.score)
