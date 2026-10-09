"""Acceptance tests from the brief (section 7): the engine against Simsaw's stored Test1 run.

The run holds 3 patterns, 70 logs, 106 log results and 730 boards.
"""
import collections
import time

import pytest

from engine import notation
from engine.log import log_volume_m3
from engine.sawing import layout, simulate_log, simulate_pattern

SIMSAW_ONELINER = {  # (primary, secondary): (dry %, wet %, boards, average length)
    ("25/114/25", "2*19 3*38 3*19"): (54.0, 61.6, 248, 2.3),
    ("19/152/19", "2*19 25 50 25 2*19"): (52.3, 59.8, 217, 2.2),
    ("25/152/25", "19 25 38 50 38 25 19"): (56.2, 64.0, 265, 2.3),
}


@pytest.fixture(scope="module")
def results(ngomi_run):
    ds = ngomi_run.dataset
    out = {}
    for pd in ds.patterns:
        out[pd.uid] = simulate_pattern(ngomi_run.logs_for(pd.uid), pd.primary, pd.secondary, ds.products,
                                       ds.lines[0], ds.settings, ds.log_class(pd.log_class_no).log_price)
    return out


def test_the_run_is_what_the_brief_describes(ngomi_run):
    ds = ngomi_run.dataset
    assert ngomi_run.name == "Test1"
    assert len(ds.patterns) == 3 and len(ngomi_run.log_results) == 106 and len(ngomi_run.board_results) == 730
    assert {(p.primary, p.secondary) for p in ds.patterns} == set(SIMSAW_ONELINER)
    line = ds.lines[0]
    assert (line.primary_kerf, line.secondary_kerf, line.edger_kerf, line.edger_blades) == (3.0, 3.0, 5.0, 3)
    assert line.primary_resaw and line.secondary_resaw and line.primary_resaw_kerf == 5.0
    assert [(t.dry, t.wet) for t in ds.products.thicknesses] == [(19, 21), (25, 27), (38, 41), (50, 54)]
    assert [(w.dry, w.wet) for w in ds.products.widths] == [(76, 81), (102, 107), (114, 120), (152, 160)]
    assert ds.settings.disc_separation_cm == 5


# ---- 1. nominal log volume ------------------------------------------------------------------

def test_1_nominal_log_volume_matches_every_stored_log_volume(ngomi_run):
    ds = ngomi_run.dataset
    logs = {g.no: g for g in ds.logs}
    worst = max(abs(log_volume_m3(logs[r.log_no], ds.settings) - r.log_volume) for r in ngomi_run.log_results)
    assert worst < 1e-5
    assert worst < 1e-7          # in fact it is exact to single-precision storage


# ---- 2. saw lines and full-width centre boards ----------------------------------------------

def test_2_saw_line_positions_match_every_stored_board(ngomi_run):
    ds = ngomi_run.dataset
    for pd in ds.patterns:
        lay = layout(notation.parse(pd.primary, pd.secondary), ds.products, ds.lines[0])
        fl = {(f.board_type, f.index): f for f in lay.flitches}
        for b in ngomi_run.board_results:
            if b.pattern_uid != pd.uid:
                continue
            f = fl[(b.board_type, b.board_no)]
            lo, hi = (b.bottom, b.top) if b.board_type == 2 else (b.left, b.right)
            assert lo == pytest.approx(f.lo, abs=0.1) and hi == pytest.approx(f.hi, abs=0.1)


def test_2_full_width_centre_boards_match(ngomi_run, results):
    """Every board Simsaw left at full cant width sits exactly on our cant faces and saw lines, and
    our engine cuts the same full-width board there (one marginal board in 326 excepted: Simsaw kept
    it at full width for 1.8 m, we get a clear span one disc short and edge it narrower)."""
    ds = ngomi_run.dataset
    stored = reproduced = 0
    for pd in ds.patterns:
        lay = layout(notation.parse(pd.primary, pd.secondary), ds.products, ds.lines[0])
        fl = {f.index: f for f in lay.flitches if f.kind == "cant"}
        ours = {(lr.log.no, b.board_type, b.board_no): b for lr in results[pd.uid].logs for b in lr.boards}
        for t in ngomi_run.board_results:
            if t.pattern_uid != pd.uid or t.board_type != 2 or abs((t.right - t.left) - lay.cant.wet) > 0.05:
                continue
            stored += 1
            assert t.left == pytest.approx(lay.cant_lo, abs=0.1) and t.right == pytest.approx(lay.cant_hi, abs=0.1)
            assert t.bottom == pytest.approx(fl[t.board_no].lo, abs=0.1) and t.top == pytest.approx(fl[t.board_no].hi, abs=0.1)
            m = ours.get((t.log_no, 2, t.board_no))
            if m is not None and (m.thickness, m.width) == (t.thickness, t.width):
                reproduced += 1
                assert (m.left, m.right, m.bottom, m.top) == pytest.approx((t.left, t.right, t.bottom, t.top), abs=0.1)
    assert stored == 326 and reproduced >= 325


def test_2_worked_example_log_8(ngomi_run):
    ds = ngomi_run.dataset
    log = next(g for g in ds.logs if g.no == 8)
    assert (log.sed_cm, log.length_m) == (21.4, 2.7)
    r = simulate_log(log, notation.parse("25/114/25", "2*19 3*38 3*19"), ds.products, ds.lines[0], ds.settings)
    assert r.log_volume == pytest.approx(0.105927, abs=1e-6)
    boards = {(b.board_type, b.board_no): b for b in r.boards}
    assert (boards[(1, 0)].left, boards[(1, 0)].right) == (63.0, 90.0)
    assert [(boards[(2, i)].bottom, boards[(2, i)].top) for i in (2, 3, 4)] == [(-76.5, -35.5), (-32.5, 8.5), (11.5, 52.5)]
    # Simsaw's eight boards for this log, by position
    assert {k: b.label for k, b in boards.items()} == {
        (0, 0): "25x102x2.7m", (1, 0): "25x102x2.7m", (2, 1): "19x102x2.1m", (2, 2): "38x114x2.7m",
        (2, 3): "38x114x2.7m", (2, 4): "38x114x2.7m", (2, 5): "19x114x2.7m", (2, 6): "19x76x0.9m"}


# ---- 3. recovery and board count -------------------------------------------------------------

def _reference(ngomi_run, uid):
    ref = [r for r in ngomi_run.log_results if r.pattern_uid == uid]
    vol = sum(r.log_volume for r in ref)
    return (100 * sum(r.dry_board_volume for r in ref) / vol, 100 * sum(r.wet_board_volume for r in ref) / vol,
            sum(r.boards for r in ref))


def test_3_dry_recovery_within_one_point_and_board_count_within_five_percent(ngomi_run, results):
    for pd in ngomi_run.dataset.patterns:
        res = results[pd.uid]
        dry, wet, n = _reference(ngomi_run, pd.uid)
        table_dry, table_wet, table_n, table_len = SIMSAW_ONELINER[(pd.primary, pd.secondary)]
        assert round(dry, 1) == table_dry and n == table_n            # the fixture agrees with the brief's table
        assert abs(res.dry_recovery * 100 - dry) <= 1.0
        assert abs(res.board_count - n) <= 0.05 * n
        assert abs(res.wet_recovery * 100 - wet) <= 1.0
        assert round(res.average_length_m, 1) == table_len


def test_3_tighter_guard_against_regressions(ngomi_run, results):
    """Where Phase 1 actually landed: within 0.15 points, exact board counts, 98 % identical boards."""
    same = total = 0
    for pd in ngomi_run.dataset.patterns:
        res = results[pd.uid]
        dry, wet, n = _reference(ngomi_run, pd.uid)
        assert abs(res.dry_recovery * 100 - dry) <= 0.15
        assert res.board_count == n
        theirs = {(b.log_no, b.board_type, b.board_no): b for b in ngomi_run.board_results if b.pattern_uid == pd.uid}
        total += len(theirs)
        for lr in res.logs:
            for b in lr.boards:
                t = theirs.get((lr.log.no, b.board_type, b.board_no))
                same += bool(t and (t.thickness, t.width) == (b.thickness, b.width) and abs(t.length_m - b.length_m) < 1e-6)
    assert total == 730 and same >= 715


def test_3_resawn_boards_match_simsaw(ngomi_run, results):
    ours = collections.Counter()
    theirs = collections.Counter()
    for pd in ngomi_run.dataset.patterns:
        for lr in results[pd.uid].logs:
            for b in lr.boards:
                if b.resawn:
                    ours[(pd.uid, lr.log.no, b.board_type, b.board_no, b.thickness, b.width, round(abs(b.resaw_position), 1))] += 1
    for t in ngomi_run.board_results:
        if t.resawn:
            theirs[(t.pattern_uid, t.log_no, t.board_type, t.board_no, t.thickness, t.width, round(abs(t.resaw_position), 1))] += 1
    assert len(theirs) == 11 and ours == theirs


def test_3_sawdust_is_close_to_simsaw(ngomi_run, results):
    for pd in ngomi_run.dataset.patterns:
        ref = sum(r.sawdust_volume for r in ngomi_run.log_results if r.pattern_uid == pd.uid)
        ours = sum(r.sawdust_volume for r in results[pd.uid].logs)
        assert ours == pytest.approx(ref, rel=0.10)


# ---- 4. mass balance -------------------------------------------------------------------------

def test_4_mass_balance_closes_on_every_log(results):
    for res in results.values():
        for r in res.logs:
            assert abs(r.wet_board_volume + r.sawdust_volume + r.chip_volume - r.log_volume) < 1e-6
            assert r.chip_volume > 0


# ---- 5. notation -----------------------------------------------------------------------------

def test_5_every_pattern_in_the_datasets_round_trips(ngomi_run, ngomi_inputs):
    from importers import simsaw
    from conftest import FIXTURES
    template = simsaw.load_inputs(FIXTURES / "template")
    patterns = ngomi_run.dataset.patterns + ngomi_inputs.patterns + template.patterns
    assert len(patterns) == 7
    for pd in patterns:
        assert notation.serialise(notation.parse(pd.primary, pd.secondary)) == (pd.primary, pd.secondary)


# ---- performance target ----------------------------------------------------------------------

def test_fifty_logs_on_one_pattern_in_under_two_seconds(ngomi_inputs):
    logs = ngomi_inputs.logs[:50]
    t0 = time.perf_counter()
    simulate_pattern(logs, "25/152/25", "19 25 38 50 38 25 19", ngomi_inputs.products, ngomi_inputs.lines[0],
                     ngomi_inputs.settings)
    assert time.perf_counter() - t0 < 2.0
