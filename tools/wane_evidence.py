"""Test combined wane measures per corner against Simsaw's accepted / refused discs."""
import collections, sys
import numpy as np
sys.path.insert(0, ".")
from engine.log import build_sections
from importers.simsaw import load_run
run = load_run("tests/fixtures/ngomi_1"); ds = run.dataset
logs = {g.no: g for g in ds.logs}
wetT = {t.dry: t.wet for t in ds.products.thicknesses}; wetW = {w.dry: w.wet for w in ds.products.widths}
def measures(a, b, T, W, Td, Wd):
    return {
        "a/(.1T)": a / (.1 * T),
        "a/(.1T)+b/(.3W)": a / (.1 * T) + b / (.3 * W),
        "a/(.1Td)+b/(.3Wd)": a / (.1 * Td) + b / (.3 * Wd),
        "sqrt((a/.1T)^2+(b/.3W)^2)": np.sqrt((a / (.1 * T)) ** 2 + (b / (.3 * W)) ** 2),
        "area a*b/2 /(.1T*.3W/2)": a * b / (.1 * T * .3 * W),
        "a (mm)": a, "b (mm)": b,
    }
acc = collections.defaultdict(lambda: collections.defaultdict(list)); rej = collections.defaultdict(lambda: collections.defaultdict(list))
for bd in run.board_results:
    if bd.resawn: continue
    g = logs[bd.log_no]; sec = build_sections(g, ds.settings); z = sec.z_mm / 1000.0
    cant = bd.board_type == 2
    T, W = wetT[bd.thickness], wetW[bd.width]
    if cant:
        if abs((bd.right - bd.left) - (120 if bd.pattern_uid == 1 else 160)) < .01: continue
        e0, e1, f0, f1 = bd.left, bd.right, bd.bottom, bd.top; edge = sec.chord_y; face = sec.chord_x
    else:
        e0, e1, f0, f1 = bd.bottom, bd.top, bd.left, bd.right; edge = sec.chord_x; face = sec.chord_y
    worst = None
    for e, sgn in ((e0, -1), (e1, +1)):
        lo, hi = edge(e)
        for f, fs in ((f0, -1), (f1, +1)):
            a = np.maximum(lo - f0, 0) if fs < 0 else np.maximum(f1 - hi, 0)
            a = np.where(np.isfinite(a), a, T)
            flo, fhi = face(f)
            b = np.maximum(flo - e0, 0) if sgn < 0 else np.maximum(e1 - fhi, 0)
            b = np.where(np.isfinite(b), b, W)
            m = measures(a, b, T, W, bd.thickness, bd.width)
            worst = m if worst is None else {k: np.maximum(worst[k], m[k]) for k in m}
    inside = (z >= bd.front_m + 0.075) & (z <= bd.back_m - 0.075)
    key = (bd.thickness, "cant" if cant else "side")
    outs = []
    if bd.front_m > 0.15: outs.append(np.argmin(np.abs(z - (bd.front_m - 0.1))))
    if bd.back_m < g.length_m - 0.15: outs.append(np.argmin(np.abs(z - (bd.back_m + 0.1))))
    for k, v in worst.items():
        if inside.any(): acc[k][key].append(v[inside].max())
        for o in outs: rej[k][key].append(v[o])
for k in acc:
    print(k)
    for key in sorted(acc[k]):
        a = np.array(acc[k][key]); r = np.array(rej[k][key])
        print(f"   {key[0]:g} {key[1]:5s} accepted p97 {np.percentile(a,97):.3f} max {a.max():.3f} | refused min {r.min():.3f} p5 {np.percentile(r,5):.3f} p20 {np.percentile(r,20):.3f}  (n {len(a)}/{len(r)})")
