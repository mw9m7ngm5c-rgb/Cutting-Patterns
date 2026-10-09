"""Log cross-sections ("discs") along the length, in the saw frame.

Saw frame: x horizontal across the primary saw (cant centred on 0), y vertical (up positive),
z along the log from the small end.

Sawing code never looks at how a disc is stored. It asks a ``Sections`` object two questions:

    chord_x(y)   where does the horizontal line at height y enter and leave the wood, at every disc?
    chord_y(x)   the same for the vertical line at x.

y and x may be one number or one value per disc (a cut that is curved or skewed along the log).

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

    def centres(self) -> tuple[np.ndarray, np.ndarray]:
        """(cx, cy) of every disc: the log's centreline."""
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

    def centres(self):
        return self.cx, self.cy

    def outline(self, index, points=64):
        t = np.linspace(0.0, 2 * np.pi, points, endpoint=False)
        return np.column_stack([self.cx[index] + self.rh[index] * np.cos(t),
                                self.cy[index] + self.rv[index] * np.sin(t)])

    def shifted(self, dx: np.ndarray | float) -> "EllipseSections":
        """The same discs moved sideways by dx (one value or one per disc)."""
        return EllipseSections(self.z_mm, self.cx + dx, self.cy, self.rh, self.rv)

    def inside(self, index: int, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Which of the points (x, y) lie inside disc ``index``."""
        u = (x - self.cx[index]) / self.rh[index]
        v = (y - self.cy[index]) / self.rv[index]
        return u * u + v * v <= 1.0

    def to_polygons(self, points: int) -> "PolygonSections":
        pts = np.stack([self.outline(i, points) for i in range(len(self.z_mm))])
        return PolygonSections(self.z_mm.copy(), pts, np.column_stack([self.cx, self.cy]))


class Shifted(Sections):
    """A view of sections in a frame that moves up by ``dy`` (one value per disc): the cant as the
    secondary saw sees it when the cuts are curved, skewed or offset. chord_x(v) is the wood along
    the cut at height v in this frame; chord_y(x) gives heights in this frame."""

    def __init__(self, base: Sections, dy: np.ndarray):
        self.base = base
        self.z_mm = base.z_mm
        self.dy = np.asarray(dy, dtype=float)

    def chord_x(self, y):
        return self.base.chord_x(np.asarray(y, dtype=float) + self.dy)

    def chord_y(self, x):
        lo, hi = self.base.chord_y(x)
        return lo - self.dy, hi - self.dy

    def areas(self):
        return self.base.areas()

    def centres(self):
        cx, cy = self.base.centres()
        return cx, cy - self.dy

    def outline(self, index, points=64):
        o = self.base.outline(index, points).copy()
        o[:, 1] -= self.dy[index]
        return o

    def inside(self, index, x, y):
        return self.base.inside(index, x, np.asarray(y, dtype=float) + self.dy[index])


@dataclass
class PolygonSections(Sections):
    z_mm: np.ndarray
    points: np.ndarray      # (n_discs, n_points, 2), each disc a closed polygon (last point joins the first)
    centre: np.ndarray | None = None   # (n_discs, 2) the pith, when known; else the mean of the points

    def __post_init__(self):
        self._next = np.roll(self.points, -1, axis=1)      # each point's neighbour, for the chords

    def _chord(self, value, axis: int):
        """Extent along the other axis of the line (coordinate ``axis`` == value), per disc.
        For a non-convex disc this is the outermost entry and exit."""
        value = np.asarray(value, dtype=float)
        v = value[:, None] if value.ndim == 1 else value
        a = self.points[:, :, axis] - v
        b = self._next[:, :, axis] - v
        o1 = self.points[:, :, 1 - axis]
        o2 = self._next[:, :, 1 - axis]
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

    def centres(self):
        if self.centre is not None:
            return self.centre[:, 0], self.centre[:, 1]
        return self.points[:, :, 0].mean(axis=1), self.points[:, :, 1].mean(axis=1)

    def shifted(self, dx) -> "PolygonSections":
        dx = np.broadcast_to(np.asarray(dx, dtype=float), self.z_mm.shape)
        pts = self.points.copy()
        pts[:, :, 0] += dx[:, None]
        centre = None if self.centre is None else self.centre + np.column_stack([dx, np.zeros_like(dx)])
        return PolygonSections(self.z_mm, pts, centre)

    def rotated(self, degrees: float) -> "PolygonSections":
        """Turned about the saw's z axis (x = y = 0) by the given angle, anticlockwise seen from the small end."""
        t = np.radians(degrees)
        c, s_ = np.cos(t), np.sin(t)
        rot = np.array([[c, s_], [-s_, c]])
        centre = None if self.centre is None else self.centre @ rot
        return PolygonSections(self.z_mm, self.points @ rot, centre)

    def inside(self, index: int, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Which of the points (x, y) lie inside disc ``index`` (even-odd rule)."""
        px, py = self.points[index, :, 0], self.points[index, :, 1]
        qx, qy = np.roll(px, -1), np.roll(py, -1)
        x, y = np.asarray(x, dtype=float)[..., None], np.asarray(y, dtype=float)[..., None]
        cross = (py <= y) != (qy <= y)
        with np.errstate(divide="ignore", invalid="ignore"):
            xs = px + (y - py) * (qx - px) / np.where(cross, qy - py, 1.0)
        return (np.sum(cross & (x < xs), axis=-1) % 2) == 1
