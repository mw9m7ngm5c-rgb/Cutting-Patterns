"""Which kerfs does Simsaw charge to sawdust? Regress its stored sawdust on our kerf components."""
import sys
import numpy as np
sys.path.insert(0, ".")
from engine import notation
from engine.log import build_sections
from engine.model import Rules
from engine.sawing import layout, _cut_flitch, _integrate, _overlap
from importers.simsaw import load_run
run = load_run("tests/fixtures/ngomi_1"); ds = run.dataset; line = ds.lines[0]
rows = []; ref = []
for pd in ds.patterns:
    pat = notation.parse(pd.primary, pd.secondary); lay = layout(pat, ds.products, line)
    refl = {r.log_no: r for r in run.log_results if r.pattern_uid == pd.uid}
    for g in run.logs_for(pd.uid):
        sec = build_sections(g, ds.settings); z = sec.z_mm
        comp = dict(p_in=0., p_out=0., s_in=0., s_out=0., e_flitch=0., e_span=0., e_len=0., e_full=0., resaw=0., xcut=0., es_flitch=0., ec_flitch=0., es_span=0., ec_span=0., es_full=0., ec_full=0., es_log=0., ec_log=0., n_side=0., n_cant=0., s_box=0., p_box=0.)
        outer_x = max(abs(v) for k in lay.primary_kerfs for v in k)
        for a, b in lay.primary_kerfs:
            lo, hi = sec.chord_y((a + b) / 2); v = _integrate(np.clip(hi - lo, 0, None) * (b - a), z)
            comp["p_out" if max(abs(a), abs(b)) >= outer_x - 1e-6 else "p_in"] += v
        ys = sorted(lay.secondary_kerfs)
        for i, (a, b) in enumerate(ys):
            lo, hi = sec.chord_x((a + b) / 2); v = _integrate(_overlap(lo, hi, lay.cant_lo, lay.cant_hi) * (b - a), z)
            comp["s_out" if i in (0, len(ys) - 1) else "s_in"] += v
        for fl in lay.flitches:
            c, resawn = _cut_flitch(fl, lay, sec, ds.products, line, Rules(placement="high"))
            if c is None: continue
            cant = fl.kind == "cant"
            if resawn:
                along = sec.chord_x if cant else sec.chord_y
                k = 5.0; outward = abs(c.v_lo - fl.lo) < 1e-9
                ka, kb = (c.v_hi, min(c.v_hi + k, fl.hi)) if outward else (max(c.v_lo - k, fl.lo), c.v_lo)
                lo, hi = along((ka + kb) / 2)
                w = _overlap(lo, hi, lay.cant_lo, lay.cant_hi) if cant else np.clip(hi - lo, 0, None)
                comp["resaw"] += _integrate(w * (kb - ka), z)
            if cant and abs(c.width.wet - lay.cant.wet) < 1e-6: continue
            across = sec.chord_y if cant else sec.chord_x
            mask = np.zeros(len(z)); mask[c.first:c.last + 1] = 1
            for ka, kb in ((c.u0 - 5, c.u0), (c.u0 + c.width.wet, c.u0 + c.width.wet + 5)):
                if cant: ka, kb = max(ka, lay.cant_lo), min(kb, lay.cant_hi)
                if kb <= ka: continue
                lo, hi = across((ka + kb) / 2)
                t = _overlap(lo, hi, c.v_lo, c.v_hi)
                comp["e_flitch"] += _integrate(t * (kb - ka), z)
                comp["e_span"] += _integrate(t * mask * (kb - ka), z)
                comp["e_len"] += (c.v_hi - c.v_lo) * (kb - ka) * c.length_mm / 1e9
                comp["e_full"] += (c.v_hi - c.v_lo) * 5.0 * c.length_mm / 1e9
                tag = "c" if cant else "s"
                comp[f"e{tag}_flitch"] += _integrate(t * (kb - ka), z)
                comp[f"e{tag}_span"] += _integrate(t * mask * (kb - ka), z)
                comp[f"e{tag}_full"] += (c.v_hi - c.v_lo) * 5.0 * c.length_mm / 1e9
                comp[f"e{tag}_log"] += (c.v_hi - c.v_lo) * 5.0 * float(z[-1]) / 1e9
        rows.append(comp); ref.append(refl[g.no].sawdust_volume)
ref = np.array(ref)
def fit(names):
    X = np.array([[r[n] for n in names] for r in rows]); coef, *_ = np.linalg.lstsq(X, ref, rcond=None)
    resid = X @ coef - ref
    print(f"{'+'.join(names):45s} coef {np.round(coef, 3)}  rel resid sd {resid.std() / ref.mean():.4f}")
def ratio(names):
    v = sum(np.array([r[n] for r in rows]) for n in names); q = v / ref
    print(f"{'+'.join(names):45s} ratio mean {q.mean():.4f} sd {q.std():.4f} min {q.min():.3f} max {q.max():.3f}")
base = ["p_in", "p_out", "s_in", "s_out", "resaw"]
for extra in (["es_flitch", "ec_flitch"], ["es_span", "ec_span"], ["es_full", "ec_full"], ["es_log", "ec_log"], ["es_log", "ec_full"], ["es_full", "ec_span"], ["es_span", "ec_full"]):
    fit(base + extra)
