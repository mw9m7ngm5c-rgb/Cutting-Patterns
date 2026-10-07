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


def build_sections(log: Log, settings: Settings, line: ProductionLine | None = None) -> Sections:
    """Cross-sections of an ideal log in the saw frame.

    Diameter grows linearly from the small end by the taper. Ovality is vertical / horizontal
    diameter with the nominal diameter their geometric mean.
    """
    if line is not None and (line.log_rotation_deg or line.log_misalignment_mm or line.primary_offset_mm):
        raise NotImplementedError("log rotation, misalignment and primary saw offset arrive in Phase 4")
    z = disc_positions_mm(log.length_m, settings.disc_separation_cm)
    d = log.sed_cm * 10.0 + log.taper_mm_per_m * (z / 1000.0)
    root = math.sqrt(log.ovality) if log.ovality > 0 else 1.0
    rh = d / 2.0 / root
    rv = d / 2.0 * root
    cy = centreline_y(z, float(z[-1]), log.sweep_mm)
    sec = EllipseSections(z, np.zeros(len(z)), cy, rh, rv)
    if settings.discretised:
        return sec.to_polygons(settings.points_per_disc)
    return sec


def build_core_sections(log: Log, settings: Settings) -> Sections:
    """Defect core: same centreline and ovality as the log, constant diameter (no taper)."""
    z = disc_positions_mm(log.length_m, settings.disc_separation_cm)
    root = math.sqrt(log.ovality) if log.ovality > 0 else 1.0
    r = np.full(len(z), log.defect_core_cm * 10.0 / 2.0)
    cy = centreline_y(z, float(z[-1]), log.sweep_mm)
    return EllipseSections(z, np.zeros(len(z)), cy, r / root, r * root)


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
