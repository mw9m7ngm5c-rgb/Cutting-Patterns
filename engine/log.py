"""Ideal-log geometry and log volume."""
from __future__ import annotations

import math

import numpy as np

from .model import Log, NominalDiameter, ProductionLine, Settings
from .sections import EllipseSections, PolygonSections, Sections


def disc_positions_mm(length_m: float, separation_cm: float) -> np.ndarray:
    """Discs from the small end at the given separation, always including the large end."""
    length = round(length_m * 1000)
    step = max(1, round(separation_cm * 10))
    z = list(range(0, length, step))
    z.append(length)
    return np.array(z, dtype=np.int64)


def centreline_y(z_mm: np.ndarray, length_mm: float, sweep_mm: float) -> np.ndarray:
    """Height of the log centre above the saw datum.

    Constant-radius arc, horns up: both end centres sit on the datum (y = 0) and the middle of the
    log hangs below it by the sweep. ASSUMPTIONS A-04.
    """
    if sweep_mm <= 0 or length_mm <= 0:
        return np.zeros(len(z_mm))
    half = length_mm / 2.0
    radius = (half * half + sweep_mm * sweep_mm) / (2.0 * sweep_mm)
    d = z_mm - half
    return -(np.sqrt(radius * radius - d * d) - (radius - sweep_mm))


def _smooth_noise(n: int, rng: np.random.Generator, terms: int = 3) -> np.ndarray:
    """A smooth random curve over n points along the log, mean about 0, standard deviation about 1:
    a few sine waves of one to `terms` cycles with random amplitude and phase."""
    t = np.linspace(0.0, 1.0, n)
    out = np.zeros(n)
    for j in range(1, terms + 1):
        out += rng.normal() / j * np.sin(2 * np.pi * j * t + rng.uniform(0, 2 * np.pi))
    norm = math.sqrt(sum(1.0 / (j * j) for j in range(1, terms + 1)) / 2.0)
    return out / norm


def log_rng(settings: Settings, log: Log, stream: int) -> np.random.Generator:
    """Every random draw for one log comes from the run's seed and the log's number, so a log always
    gets the same shape and grades whatever order it is sawn in (ASSUMPTIONS A-56)."""
    return np.random.default_rng([int(settings.seed), int(log.no), stream])


def _varied_sections(log: Log, settings: Settings, z: np.ndarray) -> PolygonSections:
    """A real-looking log: the ideal log with irregular taper, out-of-roundness, uneven ovality and
    crook, as polygons (ASSUMPTIONS A-55)."""
    v = settings.variation
    rng = log_rng(settings, log, 1)
    n = len(z)
    d = (log.sed_cm * 10.0 + log.taper_mm_per_m * (z / 1000.0)) * (1 + v.taper_pct / 100.0 * _smooth_noise(n, rng))
    ov = np.clip(log.ovality * (1 + v.ovality_pct / 100.0 * _smooth_noise(n, rng)), 0.3, 3.0)
    root = np.sqrt(ov)
    rh, rv = d / 2.0 / root, d / 2.0 * root
    cx = v.sweep_mm * _smooth_noise(n, rng)
    cy = centreline_y(z, float(z[-1]), log.sweep_mm) + v.sweep_mm * _smooth_noise(n, rng)
    # the saw datum runs through the centres of the end discs, as for an ideal log (A-04)
    for c in (cx, cy):
        c -= c[0] + (c[-1] - c[0]) * (z - z[0]) / max(z[-1] - z[0], 1)
    m = max(int(settings.points_per_disc), 16)
    theta = np.linspace(0.0, 2 * np.pi, m, endpoint=False)
    bump = np.zeros((n, m))
    for k in range(2, 6):            # lumps of 2 to 5 per round, drifting along the log
        amp = _smooth_noise(n, rng)[:, None] / k
        phase = rng.uniform(0, 2 * np.pi) + 0.5 * _smooth_noise(n, rng)[:, None]
        bump += amp * np.cos(k * theta[None, :] + phase)
    bump /= math.sqrt(sum(1.0 / (k * k) for k in range(2, 6)) / 2.0)
    scale = 1 + v.diameter_pct / 100.0 * bump
    pts = np.stack([cx[:, None] + rh[:, None] * scale * np.cos(theta)[None, :],
                    cy[:, None] + rv[:, None] * scale * np.sin(theta)[None, :]], axis=-1)
    return PolygonSections(z, pts, np.column_stack([cx, cy]))


def _place(sec: Sections, line: ProductionLine | None, z: np.ndarray, points: int) -> Sections:
    """Put the log on the primary saw: turn it about its axis, skew it and offset it sideways."""
    if line is None:
        return sec
    if line.log_rotation_deg:
        if isinstance(sec, EllipseSections):
            sec = sec.to_polygons(max(points, 16))
        sec = sec.rotated(line.log_rotation_deg)
    # misalignment: the log lies at an angle to the saw line, the middle of the log on it (A-53)
    dx = line.primary_offset_mm + line.log_misalignment_mm * (z / max(float(z[-1]), 1.0) - 0.5)
    if np.any(np.abs(dx) > 1e-9):
        sec = sec.shifted(dx)
    return sec


def build_sections(log: Log, settings: Settings, line: ProductionLine | None = None) -> Sections:
    """Cross-sections of the log as it lies on the primary saw.

    Ideal log: diameter grows linearly from the small end by the taper; ovality is vertical over
    horizontal diameter with the nominal diameter their geometric mean; sweep is a horns-up arc.
    With real-log variation in the settings the discs are irregular polygons instead. The line
    then turns, skews and offsets the log.
    """
    z = disc_positions_mm(log.length_m, settings.disc_separation_cm)
    if settings.variation is not None and settings.variation.active:
        sec: Sections = _varied_sections(log, settings, z)
    else:
        d = log.sed_cm * 10.0 + log.taper_mm_per_m * (z / 1000.0)
        root = math.sqrt(log.ovality) if log.ovality > 0 else 1.0
        cy = centreline_y(z, float(z[-1]), log.sweep_mm)
        sec = EllipseSections(z, np.zeros(len(z)), cy, d / 2.0 / root, d / 2.0 * root)
        if settings.discretised:
            sec = sec.to_polygons(settings.points_per_disc)
    return _place(sec, line, z, settings.points_per_disc)


def build_core_sections(log: Log, settings: Settings, line: ProductionLine | None = None) -> Sections:
    """Defect core: same centreline and ovality as the log, constant diameter (no taper), placed on
    the saw the same way as the log."""
    z = disc_positions_mm(log.length_m, settings.disc_separation_cm)
    root = math.sqrt(log.ovality) if log.ovality > 0 else 1.0
    r = np.full(len(z), log.defect_core_cm * 10.0 / 2.0)
    if settings.variation is not None and settings.variation.active:
        cx, cy = _varied_sections(log, settings, z).centres()
    else:
        cx, cy = np.zeros(len(z)), centreline_y(z, float(z[-1]), log.sweep_mm)
    return _place(EllipseSections(z, cx, cy, r / root, r * root), line, z, settings.points_per_disc)


def nominal_diameter_cm(sed_cm: float, mode: NominalDiameter) -> float:
    d = round(sed_cm, 4)
    if mode == NominalDiameter.ODD:        # 18.0-19.9 -> 19
        return 2.0 * math.floor(d / 2.0 + 1e-9) + 1.0
    if mode == NominalDiameter.EVEN:       # 19.0-20.9 -> 20
        return 2.0 * math.floor((d + 1.0) / 2.0 + 1e-9)
    return float(math.floor(d + 0.5 + 1e-9))  # 18.5-19.4 -> 19


def nominal_length_m(length_m: float, incr_m: float) -> float:
    if incr_m <= 0:
        return length_m
    return math.floor(round(length_m * 1000) / round(incr_m * 1000) + 1e-9) * incr_m


def log_volume_m3(log: Log, settings: Settings) -> float:
    """pi/4 x (D + 0.5 x L x taper)^2 x L, with D, L and taper each nominal or actual per Settings."""
    d = nominal_diameter_cm(log.sed_cm, settings.nominal_diameter) if settings.use_nominal_diameter else log.sed_cm
    length = nominal_length_m(log.length_m, settings.nominal_length_incr_m) if settings.use_nominal_length else log.length_m
    taper = settings.nominal_taper_mm_per_m if settings.use_nominal_taper else log.taper_mm_per_m
    mid = d / 100.0 + 0.5 * length * taper / 1000.0
    return math.pi / 4.0 * mid * mid * length
