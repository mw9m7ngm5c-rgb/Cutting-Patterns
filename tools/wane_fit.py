"""How well does each reading of the wane rule reproduce Simsaw's 730 boards?

    python tools/wane_fit.py

Rows: are the wane percentages taken of dry or wet sizes. Columns: the share of the width-wane
percentage that one edge may use. Cells: boards with the same product and length as Simsaw.
"""
import collections
import sys

sys.path.insert(0, ".")
from engine.model import Rules
from engine.sawing import simulate_pattern
from importers.simsaw import load_run

run = load_run("tests/fixtures/ngomi_1")
ds = run.dataset
ref = collections.defaultdict(dict)
for b in run.board_results:
    ref[(b.pattern_uid, b.log_no)][(b.board_type, b.board_no)] = b


def identical(rules: Rules) -> tuple[int, list[float]]:
    same, diffs = 0, []
    for pd in ds.patterns:
        res = simulate_pattern(run.logs_for(pd.uid), pd.primary, pd.secondary, ds.products, ds.lines[0], ds.settings, 0, rules)
        r = [x for x in run.log_results if x.pattern_uid == pd.uid]
        diffs.append(round(100 * (res.dry_recovery - sum(x.dry_board_volume for x in r) / sum(x.log_volume for x in r)), 2))
        for lr in res.logs:
            theirs = ref[(pd.uid, lr.log.no)]
            for b in lr.boards:
                t = theirs.get((b.board_type, b.board_no))
                same += bool(t and (t.thickness, t.width) == (b.thickness, b.width) and abs(t.length_m - b.length_m) < 1e-6)
    return same, diffs


if __name__ == "__main__":
    shares = [0.25, 0.4, 0.5, 0.6, 0.75, 1.0, 3.0]
    print("identical boards out of 730 (and recovery difference in points for the three patterns)")
    print("sizes   " + "".join(f"{'share ' + str(s):>26}" for s in shares))
    for wet in (False, True):
        cells = []
        for s in shares:
            n, d = identical(Rules(wane_on_wet_sizes=wet, width_wane_edge_share=s))
            cells.append(f"{n:>4} {str(d):>21}")
        print(f"{'wet' if wet else 'dry':<8}" + "".join(cells))
    print("share 3.0 is close to 'thickness wane only': the width term hardly counts.")
