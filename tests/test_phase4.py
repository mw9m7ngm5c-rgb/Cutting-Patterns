"""Phase 4 rules: curve sawing, misalignment and offsets, arris alignment, live sawing, chipper-profiler
boards, the three-blade edger, cross-cutting into several boards, grades and real-log variation."""
import dataclasses
import math

import numpy as np
import pytest

from conftest import make_products
from engine.log import build_sections
from engine.model import Combination, Log, ProductionLine, Settings, Variation, WaneRule
from engine.sawing import layout, simulate_log, simulate_pattern
from engine import notation

WANE = WaneRule(10, 30, 100, 0)
P = make_products(WANE)
S = Settings(disc_separation_cm=5)


def saw(log, primary, secondary="", products=P, settings=S, **kw):
    return simulate_pattern([log], primary, secondary, products, ProductionLine(**kw), settings).logs[0]


def balanced(r):
    return r.wet_board_volume + r.sawdust_volume + r.chip_volume == pytest.approx(r.log_volume, abs=1e-9)


# ------------------------------------------------------------------ the secondary saw's frame

def test_secondary_offset_and_cant_misalignment_move_the_cuts():
    log = Log(1, 30.0, 3.0, 10.0)
    r = saw(log, "/114/", "3*38", secondary_offset_mm=12)
    assert np.allclose(r.secondary_shift, 12)
    r = saw(log, "/114/", "3*38", cant_misalignment_mm=20)
    assert r.secondary_shift[0] == pytest.approx(-10) and r.secondary_shift[-1] == pytest.approx(10)
    # an offset larger than the log leaves nothing on the cant
    far = saw(log, "/114/", "3*38", secondary_offset_mm=400)
    assert not [b for b in far.boards if b.board_type == 2] and balanced(far)


def test_curve_sawing_follows_the_sweep_up_to_the_largest_the_saw_can_follow():
    log = Log(1, 26.0, 4.8, 6.0, sweep_mm=120.0)
    straight = saw(log, "25/114/25", "2*25 3*38 2*25")
    half = saw(log, "25/114/25", "2*25 3*38 2*25", cant_guiding=1)
    sec = build_sections(log, S)
    _, cy = sec.centres()
    assert np.allclose(half.secondary_shift, cy)                  # the cuts follow the centreline
    assert half.dry_board_volume > 1.5 * straight.dry_board_volume
    # the saw can follow only 10 mm/m x 4.8 m = 48 mm of the 120 mm sweep
    limited = saw(log, "25/114/25", "2*25 3*38 2*25", cant_guiding=1, max_sweep=10)
    assert np.allclose(limited.secondary_shift, cy * 48 / 120)
    full = saw(log, "25/114/25", "2*25 3*38 2*25", cant_guiding=2)
    r = np.sqrt(sec.areas() / np.pi)
    mid = np.interp(2400, sec.z_mm, r)
    assert np.allclose(full.secondary_shift, cy + r - mid)        # parallel to the top face of the cant
    assert all(balanced(x) for x in (straight, half, limited, full))


def test_arris_alignment_puts_the_marked_blade_on_the_arris():
    log = Log(1, 30.0, 3.0, 0.0)                                   # a straight cylinder, r = 150
    lay = layout(notation.parse("/114/", "25 3*38,25"), P, ProductionLine())
    third_38 = [f for f in lay.flitches if f.on_cant][3]
    arris = math.sqrt(150 ** 2 - 60 ** 2)                          # where the cant face (x = 60) leaves the wood
    r = saw(log, "/114/", "25 3*38,25")
    assert r.secondary_shift[0] == pytest.approx(arris - third_38.hi, abs=0.01)
    top_38 = [b for b in r.boards if b.board_type == 2 and b.board_no == 3][0]
    assert (top_38.thickness, top_38.width, top_38.length_m) == (38, 114, 3.0)   # full width, full length
    low = saw(log, "/114/", "25,3*38 25")                          # a blade in the lower half: bottom arris
    first_38 = [f for f in lay.flitches if f.on_cant][1]
    assert low.secondary_shift[0] == pytest.approx(-arris - first_38.lo, abs=0.01)


def test_arris_on_the_small_end_or_along_the_whole_log():
    log = Log(1, 30.0, 3.0, 0.0, sweep_mm=30.0)                    # sweep lowers the middle of the log
    small = saw(log, "/114/", "25 3*38,25", settings=dataclasses.replace(S, arris_small_end=True))
    whole = saw(log, "/114/", "25 3*38,25", settings=dataclasses.replace(S, arris_small_end=False))
    assert whole.secondary_shift[0] < small.secondary_shift[0] - 20


# ------------------------------------------------------------------ live sawing and chipper-profiler

def test_live_sawing_edges_every_flitch():
    log = Log(1, 28.0, 3.0, 9.0)
    r = saw(log, "2*25 2*38 2*25")
    assert r.boards and all(b.board_type == 3 and b.edged for b in r.boards)
    assert sorted({b.thickness for b in r.boards}) == [25, 38]
    assert balanced(r)


def test_chipper_profiler_cuts_fixed_widths_on_the_centreline_without_the_edger():
    log = Log(1, 30.0, 3.0, 10.0)
    r = saw(log, "25x76/114/25x76", "25x76 3*38 25x76", saw_type=2)
    profiled = [b for b in r.boards if b.width == 76 and b.thickness == 25]
    assert len(profiled) == 4 and not any(b.edged for b in profiled)
    for b in profiled:
        across = (b.bottom, b.top) if b.board_type < 2 else (b.left, b.right)
        assert across == (pytest.approx(-40.5), pytest.approx(40.5))
    # the edger kerfs are gone, so less sawdust than edging the same flitches
    edged = saw(log, "25/114/25", "25 3*38 25")
    assert r.sawdust_volume < edged.sawdust_volume and balanced(r)


# ------------------------------------------------------------------ edger and cross-cut

def test_three_blade_edger_takes_a_second_board_one_kerf_from_the_first():
    log = Log(1, 40.0, 3.0, 8.0)
    two = saw(log, "50/76/50", "2*25", edger_blades=2)
    three = saw(log, "50/76/50", "2*25", edger_blades=3)
    left = sorted((b for b in three.boards if b.board_type == 0), key=lambda b: b.piece)
    assert [b.piece for b in left] == [0, 1]
    assert left[1].bottom == pytest.approx(left[0].top + 5.0)       # one 5 mm edger kerf between them
    assert three.dry_board_volume > 1.5 * two.dry_board_volume
    fixed = saw(log, "50/76/50", "2*25", edger_blades=3, second_board_width="76")
    assert sorted(b.width for b in fixed.boards if b.board_type == 0) == [76, 152]
    assert balanced(three) and balanced(fixed)


def test_three_blade_edger_changes_nothing_when_no_second_board_fits():
    log = Log(1, 21.4, 2.7, 9.5)
    a = saw(log, "25/114/25", "2*19 3*38 3*19", edger_blades=2)
    b = saw(log, "25/114/25", "2*19 3*38 3*19", edger_blades=3)
    assert a.boards == b.boards and a.sawdust_volume == pytest.approx(b.sawdust_volume)


def test_cross_cut_into_more_boards_uses_the_length_the_first_left():
    log = Log(1, 26.0, 4.8, 6.0, sweep_mm=120.0)
    one = saw(log, "25/114/25", "2*25 3*38 2*25")
    more = saw(log, "25/114/25", "2*25 3*38 2*25", max_boards_per_flitch=2)
    extra = [b for b in more.boards if b.piece == 1]
    assert extra and more.dry_board_volume > one.dry_board_volume
    for b in extra:
        main = next(m for m in more.boards if (m.board_type, m.board_no, m.piece) == (b.board_type, b.board_no, 0))
        # the two boards do not overlap along the log
        assert b.front_m + b.length_m <= main.front_m + 1e-6 or b.front_m >= main.front_m + main.length_m - 1e-6
    assert balanced(more)


# ------------------------------------------------------------------ grades

def graded_products():
    base = make_products(WANE)
    combos = [dataclasses.replace(c, grade=g, price=4000.0 if g == "Clear" else 1000.0)
              for c in base.combinations for g in ("Clear", "Core")]
    outputs = {(t.dry, w.dry, "All log grades", g): v
               for t in base.thicknesses for w in base.widths
               for g, v in (("Clear", (100, 50, 0, 0)), ("Core", (0, 50, 100, 100)))}
    return dataclasses.replace(base, combinations=combos, board_grades=["Clear", "Core"], grade_outputs=outputs)


def test_grades_follow_the_share_of_defect_core():
    gp = graded_products()
    clear = saw(Log(1, 30.0, 3.0, 10.0), "25/114/25", "25 3*38 25", products=gp)
    assert {b.grade for b in clear.boards} == {"Clear"}
    cored = saw(Log(1, 30.0, 3.0, 10.0, defect_core_cm=12.0), "25/114/25", "25 3*38 25", products=gp)
    middle = [b for b in cored.boards if b.board_type == 2 and b.board_no == 2][0]
    assert middle.core_share > 0.99 and middle.grade == "Core"
    outer = [b for b in cored.boards if b.core_share == 0]
    assert outer and all(b.grade == "Clear" for b in outer)
    # value uses the price of the board's grade
    assert middle.value == pytest.approx(middle.dry_volume * 1000.0)
    assert outer[0].value == pytest.approx(outer[0].dry_volume * 4000.0)


def test_grades_are_repeatable_and_follow_the_seed():
    gp = graded_products()
    log = Log(1, 34.0, 3.0, 10.0, defect_core_cm=9.0)
    a = saw(log, "25/114/25", "2*25 3*38 2*25", products=gp)
    b = saw(log, "25/114/25", "2*25 3*38 2*25", products=gp)
    assert [x.grade for x in a.boards] == [x.grade for x in b.boards]
    seeds = {tuple(x.grade for x in saw(log, "25/114/25", "2*25 3*38 2*25", products=gp,
                                        settings=dataclasses.replace(S, seed=s)).boards) for s in range(1, 12)}
    assert len(seeds) > 1                                          # the 1-50 % band is a coin toss


def test_one_board_grade_means_no_grading():
    r = saw(Log(1, 30.0, 3.0, 10.0, defect_core_cm=12.0), "25/114/25", "25 3*38 25")
    assert {b.grade for b in r.boards} == {"All board grades"} and all(b.core_share == 0 for b in r.boards)


# ------------------------------------------------------------------ real-log variation

def test_real_log_variation_is_repeatable_per_log_and_keeps_the_size():
    v = dataclasses.replace(S, variation=Variation(diameter_pct=4, taper_pct=3, sweep_mm=8, ovality_pct=5))
    log = Log(7, 30.0, 3.0, 10.0)
    a, b = build_sections(log, v), build_sections(log, v)
    assert np.array_equal(a.points, b.points)
    other = build_sections(dataclasses.replace(log, no=8), v)
    assert not np.array_equal(a.points, other.points)
    ideal = build_sections(log, S)
    assert a.geometric_volume_m3() == pytest.approx(ideal.geometric_volume_m3(), rel=0.08)
    cx, cy = a.centres()
    assert (cx[0], cy[0], cx[-1], cy[-1]) == pytest.approx((0, 0, 0, 0), abs=1e-9)   # datum through the end centres
    r = simulate_pattern([log], "25/114/25", "2*25 3*38 2*25", P, ProductionLine(), v).logs[0]
    assert r.boards and balanced(r)
    none = dataclasses.replace(S, variation=Variation())
    assert type(build_sections(log, none)).__name__ == "EllipseSections"


def test_rotation_misalignment_and_offset_all_saw_and_balance():
    log = Log(1, 30.0, 3.0, 10.0, sweep_mm=30.0)
    for kw in ({"log_rotation_deg": 90}, {"log_misalignment_mm": 15}, {"primary_offset_mm": 10}):
        r = saw(log, "25/114/25", "2*25 3*38 2*25", **kw)
        assert r.boards and balanced(r)
    base = saw(log, "25/114/25", "2*25 3*38 2*25")
    off = saw(log, "25/114/25", "2*25 3*38 2*25", primary_offset_mm=25)
    assert off.dry_board_volume < base.dry_board_volume


def test_turning_a_swept_log_changes_what_it_gives():
    log = Log(1, 30.0, 3.0, 10.0, sweep_mm=45.0)
    up = saw(log, "25/114/25", "2*25 3*38 2*25")
    side = saw(log, "25/114/25", "2*25 3*38 2*25", log_rotation_deg=90)
    assert up.dry_board_volume != pytest.approx(side.dry_board_volume)
