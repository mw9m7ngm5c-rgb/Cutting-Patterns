"""Log generator: draws ideal logs from a range and a distribution per property.

All randomness comes from the ``numpy.random.Generator`` the caller passes in, so a fixed seed
always gives the same logs. Simsaw's own generator is not documented, so its logs cannot be
reproduced seed for seed (ASSUMPTIONS A-33); this one only follows the same ranges and
distributions.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

import numpy as np

from .model import Log


class Distribution(IntEnum):
    UNIFORM = 0
    NORMAL_65 = 1   # normal, 65 % of draws inside the limits (ASSUMPTIONS A-30)
    NORMAL_95 = 2   # normal, 95 % of draws inside the limits


# z-scores that put 65 % and 95 % of a normal distribution between the limits
_Z = {Distribution.NORMAL_65: 0.934589, Distribution.NORMAL_95: 1.959964}


@dataclass(frozen=True)
class Range:
    min: float
    max: float
    distribution: Distribution = Distribution.UNIFORM


@dataclass(frozen=True)
class GeneratorSpec:
    """Ranges in class-limit units: diameter cm, length m, taper mm/m, sweep mm/m, defect core % of SED."""
    count: int
    diameter_cm: Range
    length_m: Range
    length_incr_m: float = 0.3
    taper_mm_per_m: Range = Range(0.0, 0.0)
    sweep_mm_per_m: Range = Range(0.0, 0.0)
    ovality: Range = Range(1.0, 1.0)
    defect_core_pct: Range = Range(0.0, 0.0)
    grade: str = "All log grades"
    first_no: int = 1


def draw(r: Range, n: int, rng: np.random.Generator) -> np.ndarray:
    if r.max <= r.min:
        return np.full(n, float(r.min))
    if r.distribution == Distribution.UNIFORM:
        return rng.uniform(r.min, r.max, n)
    mid, half = (r.min + r.max) / 2.0, (r.max - r.min) / 2.0
    return rng.normal(mid, half / _Z[Distribution(r.distribution)], n)


def _lengths(spec: GeneratorSpec, n: int, rng: np.random.Generator) -> np.ndarray:
    """Lengths fall on the increment grid between the limits."""
    lo, hi, step = (round(v * 1000) for v in (spec.length_m.min, spec.length_m.max, spec.length_incr_m))
    if step <= 0 or hi <= lo:
        return np.full(n, lo / 1000.0)
    steps = (hi - lo) // step
    if spec.length_m.distribution == Distribution.UNIFORM:
        k = rng.integers(0, steps + 1, n)
    else:
        k = np.clip(np.rint((draw(spec.length_m, n, rng) * 1000 - lo) / step), 0, steps).astype(int)
    return (lo + k * step) / 1000.0


def generate_logs(spec: GeneratorSpec, rng: np.random.Generator) -> list[Log]:
    """Normal draws are not clipped to the limits, as in Simsaw (a few logs fall outside); they are
    only kept physically possible: positive diameter and ovality, no negative taper, sweep or core."""
    n = spec.count
    if n <= 0:
        return []
    d = np.maximum(np.round(draw(spec.diameter_cm, n, rng), 1), 1.0)
    length = _lengths(spec, n, rng)
    taper = np.maximum(np.round(draw(spec.taper_mm_per_m, n, rng), 1), 0.0)
    sweep = np.maximum(draw(spec.sweep_mm_per_m, n, rng), 0.0)
    ov = np.maximum(np.round(draw(spec.ovality, n, rng), 2), 0.05)
    core = np.clip(draw(spec.defect_core_pct, n, rng), 0.0, 100.0)
    return [Log(spec.first_no + i, float(d[i]), round(float(length[i]), 4), float(taper[i]),
                round(float(sweep[i] * length[i]), 1),           # stored as total mm, like Simsaw
                float(ov[i]), round(float(core[i] * d[i] / 100.0), 1), spec.grade)
            for i in range(n)]


def new_seed(rng: np.random.Generator | None = None) -> int:
    """A fresh seed to record with an unseeded run, so it can be repeated."""
    rng = rng or np.random.default_rng()
    return int(rng.integers(1, 2 ** 31 - 1))

