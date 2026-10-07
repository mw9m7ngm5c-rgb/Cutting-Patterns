"""Evidence for ASSUMPTIONS A-46: how well the generator's pre-screen and a small log sample predict
the full simulation.

    python tools/prescreen_vs_full.py tests/fixtures/ngomi_1 [class ...]

For each class: the top 150 candidates by pre-screen (every second one) are sawn on every log and
on a 12-log sample. Prints the rank correlation of the pre-screen with the full result, where the
best pattern sat in the pre-screen order, and whether the sample picked the same best pattern.
"""
import sys

from engine import generator as G
from engine.sawing import simulate_pattern
from importers import simsaw


def ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0] * len(xs)
    for k, i in enumerate(order):
        r[i] = k
    return r


def spearman(a, b):
    ra, rb, n = ranks(a), ranks(b), len(a)
    return 1 - 6 * sum((x - y) ** 2 for x, y in zip(ra, rb)) / (n * (n * n - 1))


def main(path, classes):
    ds = simsaw.load_inputs(path)
    line = ds.lines[0]
    for cls in classes:
        logs = ds.logs_in_class(cls)
        c = G.Constraints()
        dia, length, taper, fmax, fmin = G.class_geometry(logs)
        cands, _ = G.enumerate_candidates(ds.products, line, c, fmax, fmin)
        screened = G.prescreen(cands, ds.products, line, dia, round(length * 1000), taper, G.Objective.VOLUME, c)
        pool = screened[:150:2]
        sample = G._sample(logs, 12)
        full = [simulate_pattern(logs, cd.primary_text, cd.secondary_text, ds.products, line, ds.settings).dry_recovery
                for _, cd in pool]
        part = [simulate_pattern(sample, cd.primary_text, cd.secondary_text, ds.products, line, ds.settings).dry_recovery
                for _, cd in pool]
        best = max(range(len(pool)), key=lambda i: full[i])
        print(f"class {cls}: {len(cands)} candidates; pre-screen vs full Spearman {spearman([s for s, _ in pool], full):.2f}; "
              f"best {100 * full[best]:.2f} % at pre-screen rank {best + 1} of {len(pool)}; "
              f"sample's best is full rank {sorted(range(len(pool)), key=lambda i: -full[i]).index(max(range(len(pool)), key=lambda i: part[i])) + 1}")


if __name__ == "__main__":
    main(sys.argv[1], [int(x) for x in sys.argv[2:]] or [1, 3, 5])
