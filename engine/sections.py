"""Log cross-sections ("discs") along the length, in the saw frame.

Saw frame: x horizontal across the primary saw (cant centred on 0), y vertical (up positive),
z along the log from the small end.

Sawing code never looks at how a disc is stored. It asks a ``Sections`` object two questions:

    chord_x(y)   where does the horizontal line at height y enter and leave the wood, at every disc?
    chord_y(x)   the same for the vertical line at x.

Two implementations answer them: exact ellipses for ideal logs (Simsaw's "Analytical" type) and
closed polygons for anything else (Simsaw's "Discretised" type, and real or perturbed logs).
An empty chord is returned as lo = +inf, hi = -inf.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


class Sections:
    z_mm: np.ndarray            # (n,) integer positions of the discs from the small end

    def chord_x(self, y: float) -> tuple[np.ndarray, np.ndarray]:
        raise NotImplementedError

    def chord_y(self, x: float) -> tuple[np.ndarray, np.ndarray]:
        raise NotImplementedError

    def areas(self) -> np.ndarray:
        raise NotImplementedError

    def outline(self, index: int, points: int = 64) -> np.ndarray:
        """(points, 2) polygon of one disc, for drawing."""
        raise NotImplementedError

    def geometric_volume_m3(self) -> float:
        a = self.areas()
        z = self.z_mm.astype(float)
        return float(np.sum((a[1:] + a[:-1]) * 0.5 * np.diff(z))) / 1e9


def _empty_like(mask: np.ndarray, lo: np.ndarray, hi: np.ndarray):
    lo = np.where(mask, lo, np.inf)
    hi = np.where(mask, hi, -np.inf)
    return lo, hi


@dataclass
class EllipseSections(Sections):
    z_mm: np.ndarray
    cx: np.ndarray      # centre x per disc
    cy: np.ndarray      # centre y per disc
    rh: np.ndarray      # horizontal radius per disc
    rv: np.ndarray      # vertical radius per disc

    def chord_x(self, y):
        u = (y - self.cy) / self.rv
        inside = np.abs(u) < 1.0
        half = self.rh * np.sqrt(np.clip(1.0 - u * u, 0.0, None))
        return _empty_like(inside, self.cx - half, self.cx + half)

    def chord_y(self, x):
        u = (x - self.cx) / self.rh
        inside = np.abs(u) < 1.0
        half = self.rv * np.sqrt(np.clip(1.0 - u * u, 0.0, None))
        return _empty_like(inside, self.cy - half, self.cy + half)

    def areas(self):
        return np.pi * self.rh * self.rv

    def outline(self, index, points=64):
        t = np.linspace(0.0, 2 * np.pi, points, endpoint=False)
        return np.column_stack([self.cx[index] + self.rh[index] * np.cos(t),
                                self.cy[index] + self.rv[index] * np.sin(t)])

    def to_polygons(self, points: int) -> "PolygonSections":
        pts = np.stack([self.outline(i, points) for i in range(len(self.z_mm))])
        return PolygonSections(self.z_mm.copy(), pts)


@dataclass
class PolygonSections(Sections):
    z_mm: np.ndarray
    points: np.ndarray      # (n_discs, n_points, 2), each disc a closed polygon (last point joins the first)

    def _chord(self, value: float, axis: int):
        """Extent along the other axis of the line (coordinate ``axis`` == value), per disc.
        For a non-convex disc this is the outermost entry and exit."""
        a = self.points[:, :, axis] - value
        b = np.roll(a, -1, axis=1)
        o1 = self.points[:, :, 1 - axis]
        o2 = np.roll(o1, -1, axis=1)
        cross = (a <= 0) != (b <= 0)
        denom = np.where(cross, a - b, 1.0)
        hit = o1 + (o2 - o1) * (a / denom)
        lo = np.where(cross, hit, np.inf).min(axis=1)
        hi = np.where(cross, hit, -np.inf).max(axis=1)
        return lo, hi

    def chord_x(self, y):
        return self._chord(y, 1)

    def chord_y(self, x):
        return self._chord(x, 0)

    def areas(self):
        x, y = self.points[:, :, 0], self.points[:, :, 1]
        return 0.5 * np.abs(np.sum(x * np.roll(y, -1, axis=1) - np.roll(x, -1, axis=1) * y, axis=1))

    def outline(self, index, points=64):
        return self.points[index]
