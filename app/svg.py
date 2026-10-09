"""End-view diagram as SVG markup, drawn on the server (generator results and saw setting cards).
The pattern screen draws the same picture in the browser (static/pattern.js)."""
from __future__ import annotations

from markupsafe import Markup, escape


def _pts(points) -> str:
    return " ".join(f"{x:.1f},{-y:.1f}" for x, y in points)


def diagram(d: dict, labels: bool = True, kerf_labels: bool = False, css_class: str = "diagram") -> Markup:
    if not d.get("large_end"):
        return Markup("")
    pts = d["large_end"] + d["small_end"]
    min_x, max_x = min(p[0] for p in pts), max(p[0] for p in pts)
    min_y, max_y = min(p[1] for p in pts), max(p[1] for p in pts)
    pad = 0.06 * max(max_x - min_x, max_y - min_y) + 8
    min_x, max_x, min_y, max_y = min_x - pad, max_x + pad, min_y - pad, max_y + pad
    W, H = max_x - min_x, max_y - min_y
    sw = W / 400
    out = [f'<svg class="{css_class}" viewBox="{min_x:.1f} {-max_y:.1f} {W:.1f} {H:.1f}" xmlns="http://www.w3.org/2000/svg" '
           f'role="img" aria-label="End view of log {d["log"]["no"]}">',
           f'<polygon points="{_pts(d["large_end"])}" fill="#e9d3a8" stroke="#b88a4a" stroke-width="{sw:.2f}"/>',
           f'<polygon points="{_pts(d["small_end"])}" fill="none" stroke="#b88a4a" stroke-width="{sw:.2f}" '
           f'stroke-dasharray="{W / 100:.1f} {W / 160:.1f}"/>']
    if d.get("core"):
        out.append(f'<polygon points="{_pts(d["core"])}" fill="none" stroke="#9b2c2c" stroke-width="{sw:.2f}" '
                   f'stroke-dasharray="{W / 200:.1f}"/>')
    for b in d.get("boards", []):
        w, h = b["right"] - b["left"], b["top"] - b["bottom"]
        dash = f' stroke-dasharray="{W / 150:.1f} {W / 300:.1f}"' if b["resawn"] else ""
        out.append(f'<rect x="{b["left"]:.1f}" y="{-b["top"]:.1f}" width="{w:.1f}" height="{h:.1f}" fill="#f4c97a" '
                   f'stroke="#8b5e1a" stroke-width="{W / 600:.2f}"{dash}><title>{escape(b["label"])}</title></rect>')
        if labels:
            vertical = h > w * 1.15
            long, short = (h, w) if vertical else (w, h)
            fs = max(2.5, min(short * 0.5, long * 0.9 / (len(b["label"]) * 0.6), W / 32))
            cx, cy = b["left"] + w / 2, -(b["bottom"] + h / 2)
            rot = f' transform="rotate(-90 {cx:.1f} {cy:.1f})"' if vertical else ""
            out.append(f'<text x="{cx:.1f}" y="{cy:.1f}" font-size="{fs:.1f}" text-anchor="middle" '
                       f'dominant-baseline="central" fill="#3b2a0c"{rot}>{escape(b["label"])}</text>')
    for a, b in d.get("primary_kerfs", []):
        out.append(f'<rect x="{a:.1f}" y="{-max_y:.1f}" width="{b - a:.1f}" height="{H:.1f}" fill="#5c5c5c" opacity=".55"/>')
    cant = d.get("cant")
    if cant:
        for a, b in d.get("secondary_kerfs", []):
            out.append(f'<rect x="{cant["lo"]:.1f}" y="{-b:.1f}" width="{cant["hi"] - cant["lo"]:.1f}" height="{b - a:.1f}" '
                       f'fill="#5c5c5c" opacity=".55"/>')
    sx, sy = min_x + pad * 0.4, -min_y - pad * 0.35
    out.append(f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{sx + 50:.1f}" y2="{sy:.1f}" stroke="#333" stroke-width="{W / 300:.2f}"/>'
               f'<text x="{sx + 25:.1f}" y="{sy - W / 120:.1f}" font-size="{W / 45:.1f}" text-anchor="middle" fill="#333">50 mm</text>')
    out.append("</svg>")
    return Markup("".join(out))
