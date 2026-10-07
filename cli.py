"""Command line for the sawing engine.

    python cli.py simulate --dataset "reference/ngomi 1.mdb" --pattern "25/114/25" "2*19 3*38 3*19" --class 1
    python cli.py simulate --dataset tests/fixtures/ngomi_1                 every pattern in the dataset
    python cli.py validate --dataset tests/fixtures/ngomi_1 --run Test1     compare with Simsaw's stored run

--dataset takes a Simsaw .mdb file or a directory of JSON fixtures.
"""
from __future__ import annotations

import argparse
import sys
import time

from engine.model import PatternResult
from engine.sawing import simulate_pattern
from importers import simsaw


def _oneliner_header() -> str:
    return (f"{'Class':>5} {'Primary':<18} {'Secondary':<26} {'Logs':>4} {'Dry %':>6} {'Wet %':>6} "
            f"{'Gross R/m3':>10} {'Nett R/m3':>10} {'Boards':>6} {'Avg len':>7}")


def _oneliner(class_no, res: PatternResult) -> str:
    return (f"{class_no:>5} {res.primary:<18} {res.secondary:<26} {len(res.logs):>4} {res.dry_recovery * 100:>6.1f} "
            f"{res.wet_recovery * 100:>6.1f} {res.gross_value_recovery:>10.2f} {res.nett_value_recovery:>10.2f} "
            f"{res.board_count:>6} {res.average_length_m:>7.1f}")


def _print_mix(res: PatternResult) -> None:
    total = sum(d["dry_volume"] for d in res.product_mix().values()) or 1.0
    print("\n  Product mix")
    print(f"  {'Size':<10} {'Pieces':>6} {'Dry m3':>9} {'Share':>6}")
    for (t, w), d in res.product_mix().items():
        print(f"  {t:g}x{w:<7g} {int(d['count']):>6} {d['dry_volume']:>9.4f} {100 * d['dry_volume'] / total:>5.1f}%")


def _print_volumes(res: PatternResult) -> None:
    logs = res.log_volume
    dry = sum(r.dry_board_volume for r in res.logs)
    wet = sum(r.wet_board_volume for r in res.logs)
    chips = sum(r.chip_volume for r in res.logs)
    dust = sum(r.sawdust_volume for r in res.logs)
    print("\n  Volumes (m3)")
    for name, v in (("Logs", logs), ("Sawn boards (dry)", dry), ("Shrinkage", wet - dry), ("Chips", chips),
                    ("Sawdust", dust), ("Total", dry + (wet - dry) + chips + dust)):
        print(f"  {name:<18} {v:>9.4f} {100 * v / logs if logs else 0:>6.1f}%")


def _print_boards(res: PatternResult) -> None:
    kind = {0: "left side", 1: "right side", 2: "cant"}
    for lr in res.logs:
        g = lr.log
        print(f"\n  Log {g.no}: SED {g.sed_cm:g} cm, {g.length_m:g} m, taper {g.taper_mm_per_m:g} mm/m, sweep {g.sweep_mm:g} mm, "
              f"ovality {g.ovality:g}   volume {lr.log_volume:.6f} m3")
        for b in lr.boards:
            print(f"    {kind[b.board_type]:<10} {b.board_no}  {b.label:<16} x {b.left:7.1f} to {b.right:7.1f}   "
                  f"y {b.bottom:7.1f} to {b.top:7.1f}   z {b.front_m:.2f} to {b.back_m:.2f} m{'   resawn' if b.resawn else ''}")


def cmd_simulate(a) -> int:
    ds = simsaw.load_run(a.dataset, a.run).dataset if a.run else simsaw.load_inputs(a.dataset)
    line = ds.line(a.line)
    if a.pattern:
        if a.log is None and a.log_class is None:
            print("with --pattern, say which logs to saw: --class N or --log NO", file=sys.stderr)
            return 2
        jobs = [(a.log_class, a.pattern[0], a.pattern[1] if len(a.pattern) > 1 else "")]
    else:
        jobs = [(p.log_class_no, p.primary, p.secondary) for p in ds.patterns
                if p.line_name == line.name and (a.log_class is None or p.log_class_no == a.log_class)]
    if not jobs:
        print("no sawing patterns to simulate", file=sys.stderr)
        return 1
    print(f"Dataset {ds.name}, production line {line.name}")
    print(_oneliner_header())
    results = []
    for class_no, primary, secondary in jobs:
        if a.log is not None:
            logs = [g for g in ds.logs if g.no == a.log]
            price = next((c.log_price for c in ds.log_classes if logs and c.contains(logs[0])), 0.0)
            label = "-"
        else:
            logs = ds.logs_in_class(class_no)
            price, label = ds.log_class(class_no).log_price, class_no
        if not logs:
            print(f"{label:>5} {primary:<18} {secondary:<26}  no logs")
            continue
        res = simulate_pattern(logs, primary, secondary, ds.products, line, ds.settings, price)
        results.append(res)
        print(_oneliner(label, res))
    for res in results:
        if a.mix or a.boards or a.volumes:
            print(f"\n{res.primary}   {res.secondary}")
        if a.volumes:
            _print_volumes(res)
        if a.mix:
            _print_mix(res)
        if a.boards:
            _print_boards(res)
    return 0


def cmd_validate(a) -> int:
    run = simsaw.load_run(a.dataset, a.run)
    ds = run.dataset
    line = ds.lines[0]
    print(f"Run {run.name}: engine against Simsaw's stored results")
    print(f"{'Primary':<12} {'Secondary':<24} {'Logs':>4} {'Dry % ours':>10} {'Simsaw':>7} {'diff':>6} "
          f"{'Boards ours':>11} {'Simsaw':>7} {'identical':>10} {'sec':>5}")
    ok = True
    for pd in ds.patterns:
        logs = run.logs_for(pd.uid)
        t0 = time.perf_counter()
        res = simulate_pattern(logs, pd.primary, pd.secondary, ds.products, line, ds.settings,
                               ds.log_class(pd.log_class_no).log_price)
        dt = time.perf_counter() - t0
        ref = [r for r in run.log_results if r.pattern_uid == pd.uid]
        ref_dry = 100 * sum(r.dry_board_volume for r in ref) / sum(r.log_volume for r in ref)
        ref_n = sum(r.boards for r in ref)
        theirs = {(b.log_no, b.board_type, b.board_no): b for b in run.board_results if b.pattern_uid == pd.uid}
        same = sum(1 for lr in res.logs for b in lr.boards
                   if (t := theirs.get((lr.log.no, b.board_type, b.board_no))) is not None
                   and (t.thickness, t.width) == (b.thickness, b.width) and abs(t.length_m - b.length_m) < 1e-6)
        diff = res.dry_recovery * 100 - ref_dry
        ok &= abs(diff) <= 1.0 and abs(res.board_count - ref_n) <= 0.05 * ref_n
        print(f"{pd.primary:<12} {pd.secondary:<24} {len(logs):>4} {res.dry_recovery * 100:>10.2f} {ref_dry:>7.2f} "
              f"{diff:>+6.2f} {res.board_count:>11} {ref_n:>7} {same:>6}/{ref_n:<3} {dt:>5.2f}")
    print("within tolerance (1.0 point of recovery, 5 % of board count)" if ok else "OUTSIDE tolerance")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="cli.py", description="Sawing pattern simulator")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("simulate", help="saw logs with one pattern, or with every pattern in the dataset")
    s.add_argument("--dataset", required=True, help="Simsaw .mdb file or fixtures directory")
    s.add_argument("--run", help="use the inputs snapshotted with this batch run instead of the current inputs")
    s.add_argument("--pattern", nargs="+", metavar=("PRIMARY", "SECONDARY"), help='e.g. "25/114/25" "2*19 3*38 3*19"')
    s.add_argument("--class", dest="log_class", type=int, help="log class number")
    s.add_argument("--log", type=int, help="saw a single log (log number)")
    s.add_argument("--line", help="production line name (default: the first)")
    s.add_argument("--boards", action="store_true", help="list every board")
    s.add_argument("--mix", action="store_true", help="show the product mix")
    s.add_argument("--volumes", action="store_true", help="show the volume balance")
    s.set_defaults(func=cmd_simulate)
    v = sub.add_parser("validate", help="compare the engine with a stored Simsaw batch run")
    v.add_argument("--dataset", required=True)
    v.add_argument("--run")
    v.set_defaults(func=cmd_validate)
    a = ap.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
