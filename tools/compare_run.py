"""Compare the engine with Simsaw's stored Test1 run, board by board.

    python tools/compare_run.py [fixtures-or-mdb] [--worst N]
"""
import collections
import dataclasses
import sys
import time

sys.path.insert(0, ".")
from engine.model import Rules
from engine.sawing import simulate_pattern
from importers.simsaw import load_run


def compare(run, rules=None, verbose=True, worst=0):
    ds = run.dataset
    line = ds.lines[0]
    out = []
    for pd in ds.patterns:
        logs = run.logs_for(pd.uid)
        t0 = time.perf_counter()
        res = simulate_pattern(logs, pd.primary, pd.secondary, ds.products, line, ds.settings,
                               ds.log_class(pd.log_class_no).log_price, rules)
        dt = time.perf_counter() - t0
        ref_logs = {r.log_no: r for r in run.log_results if r.pattern_uid == pd.uid}
        ref_boards = collections.defaultdict(dict)
        for b in run.board_results:
            if b.pattern_uid == pd.uid:
                ref_boards[b.log_no][(b.board_type, b.board_no)] = b
        ref_vol = sum(r.log_volume for r in ref_logs.values())
        ref_dry = sum(r.dry_board_volume for r in ref_logs.values()) / ref_vol
        ref_n = sum(r.boards for r in ref_logs.values())
        same = diff_prod = diff_len = extra = missing = 0
        per_log = []
        dust_ref = sum(r.sawdust_volume for r in ref_logs.values())
        dust = sum(r.sawdust_volume for r in res.logs)
        for lr in res.logs:
            mine = {(b.board_type, b.board_no): b for b in lr.boards}
            theirs = ref_boards[lr.log.no]
            for k in set(mine) | set(theirs):
                m, t = mine.get(k), theirs.get(k)
                if m is None: missing += 1
                elif t is None: extra += 1
                elif (m.thickness, m.width) != (t.thickness, t.width): diff_prod += 1
                elif abs(m.length_m - t.length_m) > 1e-6: diff_len += 1
                else: same += 1
            per_log.append((abs(lr.dry_board_volume - ref_logs[lr.log.no].dry_board_volume), lr, theirs))
        row = dict(pattern=f"{pd.primary} | {pd.secondary}", logs=len(logs), dry=res.dry_recovery * 100,
                   ref_dry=ref_dry * 100, boards=res.board_count, ref_boards=ref_n, same=same,
                   diff_prod=diff_prod, diff_len=diff_len, extra=extra, missing=missing,
                   dust_ratio=dust / dust_ref, seconds=dt)
        out.append(row)
        if verbose:
            print(f"{row['pattern']:42s} dry {row['dry']:.2f} (Simsaw {row['ref_dry']:.2f})  boards {row['boards']} ({ref_n})"
                  f"  same {same} prod {diff_prod} len {diff_len} extra {extra} missing {missing}"
                  f"  sawdust x{row['dust_ratio']:.3f}  {dt:.2f}s")
        if worst:
            per_log.sort(key=lambda t: -t[0])
            for d, lr, theirs in per_log[:worst]:
                g = lr.log
                print(f"  log {g.no}: d {g.sed_cm} L {g.length_m} taper {g.taper_mm_per_m} sweep {g.sweep_mm} oval {g.ovality}"
                      f"   dry volume diff {d * 1000:.2f} dm3")
                mine = {(b.board_type, b.board_no): b for b in lr.boards}
                for k in sorted(set(mine) | set(theirs)):
                    m, t = mine.get(k), theirs.get(k)
                    ms = f"{m.label:16s} u[{m.left:7.1f},{m.right:7.1f}] v[{m.bottom:7.1f},{m.top:7.1f}] z[{m.front_m:.2f},{m.back_m:.2f}]{' R' if m.resawn else ''}" if m else "-"
                    ts = f"{t.thickness:g}x{t.width:g}x{t.length_m:.1f}m  x[{t.left:7.1f},{t.right:7.1f}] y[{t.bottom:7.1f},{t.top:7.1f}] z[{t.front_m:.1f},{t.back_m:.1f}]{' R' if t.resawn else ''}" if t else "-"
                    flag = " " if (m and t and (m.thickness, m.width, round(m.length_m, 3)) == (t.thickness, t.width, round(t.length_m, 3))) else "*"
                    print(f"   {flag} type {k[0]} no {k[1]}:  ours {ms:75s} Simsaw {ts}")
    return out


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--worst" in argv:
        i = argv.index("--worst"); worst = int(argv[i + 1]); del argv[i:i + 2]
    else:
        worst = 0
    args = argv
    run = load_run(args[0] if args else "tests/fixtures/ngomi_1")
    compare(run, worst=worst)
