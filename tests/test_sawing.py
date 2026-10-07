"""Whole-log sawing on cylinders and simple tapered logs: every number here can be checked by hand."""
import math

import pytest

from conftest import cylinder, make_products
from engine import notation
from engine.model import Log, ProductionLine, Rules, Settings, WaneRule
from engine.sawing import simulate_log, simulate_pattern

S = Settings(disc_separation_cm=5)
LINE = ProductionLine(primary_kerf=3.0, secondary_kerf=3.0, edger_kerf=5.0)


def saw(log, primary, secondary, products=None, line=LINE, settings=S, rules=None):
    return simulate_log(log, notation.parse(primary, secondary), products or make_products(), line, settings, rules)


def by_kind(result):
    kinds = {0: "left", 1: "right", 2: "cant"}
    return {(kinds[b.board_type], b.board_no): b for b in result.boards}


# ---------------------------------------------------------------- primary breakdown

def test_sideboard_is_edged_to_the_widest_width_its_outer_face_allows():
    # R = 100. Sideboard between x = 63 and 90; the face at x = 90 is 2*sqrt(100^2 - 90^2) = 87.2 wide.
    b = by_kind(saw(cylinder(20.0), "25/114/25", "38"))
    for side in ("left", "right"):
        board = b[(side, 0)]
        assert (board.thickness, board.width, board.length_m) == (25, 76, 3.0)
        assert board.edged and not board.resawn
        assert board.top - board.bottom == pytest.approx(81.0)            # wet width
        assert (board.bottom + board.top) / 2 == pytest.approx(0.0)       # centred on a straight log
    assert (b[("right", 0)].left, b[("right", 0)].right) == (63.0, 90.0)
    assert (b[("left", 0)].left, b[("left", 0)].right) == (-90.0, -63.0)


def test_sideboard_starts_where_taper_first_gives_enough_wood():
    # SED 19 cm, 10 mm/m taper: radius 95 + 5 z. A 76 mm board (81 wet) needs
    # R >= sqrt(90^2 + 40.5^2) = 98.69, reached at z = 0.738 m, so the first clear disc is 0.75 m.
    r = saw(Log(1, 19.0, 3.0, taper_mm_per_m=10.0), "25/114/25", "38")
    board = by_kind(r)[("right", 0)]
    assert board.front_m == pytest.approx(0.75) and board.back_m == pytest.approx(3.0)
    assert board.length_m == pytest.approx(2.1)                            # 2.25 m clear, cut to 0.3 m steps


def test_sweep_shifts_the_sideboard_down():
    # Horns up: the middle of the log hangs below the datum, so the board sits below centre.
    board = by_kind(saw(Log(1, 22.0, 3.0, sweep_mm=20.0), "25/114/25", "38"))[("right", 0)]
    assert (board.bottom + board.top) / 2 < -5.0


# ---------------------------------------------------------------- secondary breakdown

def test_centre_cant_boards_come_out_at_full_cant_width_without_edging():
    b = by_kind(saw(cylinder(20.0), "25/114/25", "3*38"))
    middle = b[("cant", 1)]
    assert (middle.thickness, middle.width, middle.length_m) == (38, 114, 3.0)
    assert (middle.left, middle.right) == (-60.0, 60.0) and not middle.edged
    assert (middle.bottom, middle.top) == (-20.5, 20.5)


def test_waney_cant_board_is_edged_narrower():
    # 152 cant (x = +-80) in a 20 cm log. Outer 38s lie between y = 23.5 and 64.5, where the log is
    # only 2*sqrt(100^2 - 64.5^2) = 152.8 wide: not the 160 a 152 board needs, so it is edged to 114.
    b = by_kind(saw(cylinder(20.0), "/152/", "3*38"))
    assert (b[("cant", 1)].width, b[("cant", 1)].edged) == (152, False)
    for i in (0, 2):
        assert (b[("cant", i)].width, b[("cant", i)].edged) == (114, True)
        assert b[("cant", i)].length_m == 3.0


def test_riving_knives_stop_cant_boards_from_being_edged():
    # Same log and pattern, but all three boards inside the knives: the outer two cannot make full
    # cant width anywhere along a cylinder, and cross-cutting does not help.
    r = saw(cylinder(20.0), "/152/", "<3*38>")
    assert [(b.board_no, b.width) for b in r.boards] == [(1, 152)]


def test_centre_boards_never_come_off_the_edger():
    products = make_products(centre={(38, 114)})
    b = by_kind(saw(cylinder(20.0), "/152/", "3*38", products))
    assert b[("cant", 0)].width == 102                                    # 114 is reserved for full-width boards
    b = by_kind(saw(cylinder(20.0), "/114/", "3*38", products))
    assert b[("cant", 1)].width == 114                                    # at full cant width it is allowed


def test_boards_outside_the_log_are_not_recovered():
    # Five 38s stack to 217 mm, taller than the 200 mm log.
    r = saw(cylinder(20.0), "/114/", "5*38")
    assert sorted(b.board_no for b in r.boards) == [1, 2, 3]


# ---------------------------------------------------------------- resaw

def test_resaw_takes_a_thinner_board_off_the_inner_face():
    # R = 95: a 25 mm sideboard (x = 63 to 90) has a 60.8 mm outer face, too narrow for any width.
    # Resawn to 19 (21 wet) its outer face moves in to x = 84, where the log is 88.7 wide.
    no_resaw = saw(cylinder(19.0), "25/114/25", "38")
    assert not [b for b in no_resaw.boards if b.board_type != 2]
    line = ProductionLine(primary_kerf=3.0, secondary_kerf=3.0, primary_resaw=True)
    b = by_kind(saw(cylinder(19.0), "25/114/25", "38", line=line))
    right, left = b[("right", 0)], b[("left", 0)]
    assert (right.thickness, right.width, right.resawn) == (19, 76, True)
    assert (right.left, right.right, right.resaw_position) == (63.0, 84.0, 84.0)
    assert (left.left, left.right, left.resaw_position) == (-84.0, -63.0, -84.0)


def test_resaw_only_when_the_full_thickness_gives_nothing():
    line = ProductionLine(primary_kerf=3.0, secondary_kerf=3.0, primary_resaw=True)
    b = by_kind(saw(cylinder(20.0), "25/114/25", "38", line=line))
    assert b[("right", 0)].thickness == 25 and not b[("right", 0)].resawn


def test_secondary_resaw_has_its_own_switch():
    # Outer 38s of a 5*38 stack lie between y = 67.5 and 108.5: outside a 20 cm log. Resawn to 19
    # the outer face is at 88.5, where the log is 93.1 wide.
    on = ProductionLine(primary_kerf=3.0, secondary_kerf=3.0, secondary_resaw=True)
    b = by_kind(saw(cylinder(20.0), "/114/", "5*38", line=on))
    top, bottom = b[("cant", 4)], b[("cant", 0)]
    assert (top.thickness, top.width, top.resawn, top.resaw_position) == (19, 76, True, 88.5)
    assert (top.bottom, top.top) == (67.5, 88.5)
    assert (bottom.bottom, bottom.top, bottom.resaw_position) == (-88.5, -67.5, -88.5)
    primary_only = ProductionLine(primary_kerf=3.0, secondary_kerf=3.0, primary_resaw=True)
    assert len(saw(cylinder(20.0), "/114/", "5*38", line=primary_only).boards) == 3


# ---------------------------------------------------------------- volumes and values

def test_board_volumes_and_value():
    products = make_products(prices={(38, 114): 3000.0})
    board = by_kind(saw(cylinder(20.0), "/114/", "38", products))[("cant", 0)]
    assert board.dry_volume == pytest.approx(0.038 * 0.114 * 3.0)
    assert board.wet_volume == pytest.approx(0.041 * 0.120 * 3.0)
    assert board.value == pytest.approx(0.038 * 0.114 * 3.0 * 3000.0)


def test_sawdust_is_the_wood_in_the_kerfs():
    # /114/ with one 38: two slab cuts (x = 60 to 63 each side) and two cuts above and below the
    # board (y = 20.5 to 23.5), the latter across the 120 mm cant. No edging.
    r = saw(cylinder(20.0), "/114/", "38")
    R = 100.0
    F = lambda x: x * math.sqrt(R * R - x * x) + R * R * math.asin(x / R)   # integral of the chord
    slab_cut = F(63.0) - F(60.0)
    expected = (2 * slab_cut + 2 * 120.0 * 3.0) * 3000.0 / 1e9
    assert r.sawdust_volume == pytest.approx(expected, rel=2e-3)


def test_edger_kerfs_add_sawdust():
    # /152/ with 3*38: the two outer boards are edged from the 160 mm cant down to 120 mm, so each gets
    # two 5 mm edger cuts through 41 mm of wood over 3 m: 4 x 5 x 41 x 3000 mm3.
    with_kerf = saw(cylinder(20.0), "/152/", "3*38")
    no_kerf = saw(cylinder(20.0), "/152/", "3*38", line=ProductionLine(primary_kerf=3.0, secondary_kerf=3.0, edger_kerf=0.0))
    assert with_kerf.sawdust_volume - no_kerf.sawdust_volume == pytest.approx(4 * 5 * 41 * 3000 / 1e9, rel=1e-6)


def test_resaw_kerf_adds_sawdust():
    # /114/ with 5*38 and a secondary resaw: each outer flitch is resawn at y = +-88.5. The 5 mm resaw
    # cut (centred on y = 91) passes through 2*sqrt(100^2 - 91^2) = 82.9 mm of wood, and the two
    # 19x76 boards each get two edger cuts through 21 mm.
    on = ProductionLine(primary_kerf=3.0, secondary_kerf=3.0, secondary_resaw=True, secondary_resaw_kerf=5.0)
    extra = saw(cylinder(20.0), "/114/", "5*38", line=on).sawdust_volume - saw(cylinder(20.0), "/114/", "5*38").sawdust_volume
    resaw = 2 * (2 * math.sqrt(100 ** 2 - 91 ** 2)) * 5 * 3000
    edger = 2 * 2 * 5 * 21 * 3000
    assert extra == pytest.approx((resaw + edger) / 1e9, rel=1e-6)


def test_mass_balance_closes_on_the_log_volume():
    for log in (cylinder(20.0), Log(2, 23.4, 2.7, taper_mm_per_m=9.0, sweep_mm=22.0, ovality=1.03)):
        r = saw(log, "25/114/25", "19 3*38 19", make_products(WaneRule(10, 30, 100, 0)))
        assert r.wet_board_volume + r.sawdust_volume + r.chip_volume == pytest.approx(r.log_volume, abs=1e-12)
        assert r.shrinkage_volume == pytest.approx(r.wet_board_volume - r.dry_board_volume)


def test_log_volume_follows_the_nominal_settings():
    actual = Settings(disc_separation_cm=5, use_nominal_diameter=False, use_nominal_length=False, use_nominal_taper=False)
    r = saw(cylinder(20.6), "/114/", "38", settings=actual)
    assert r.log_volume == pytest.approx(math.pi / 4 * 0.206 ** 2 * 3.0)
    r = saw(cylinder(20.6), "/114/", "38")                                   # nominal: 21 cm, 10 mm/m
    assert r.log_volume == pytest.approx(math.pi / 4 * (0.21 + 0.5 * 3.0 * 0.010) ** 2 * 3.0)


def test_pattern_result_recoveries():
    products = make_products()
    logs = [cylinder(20.0), Log(2, 20.0, 2.4)]
    res = simulate_pattern(logs, "25/114/25", "3*38", products, LINE, S, log_price=120.0)
    dry = sum(b.dry_volume for r in res.logs for b in r.boards)
    vol = sum(r.log_volume for r in res.logs)
    assert res.dry_recovery == pytest.approx(dry / vol)
    assert res.gross_value_recovery == pytest.approx(dry * 4000.0 / vol)
    assert res.nett_value_recovery == pytest.approx(dry * 4000.0 / vol - 120.0)
    assert res.board_count == sum(len(r.boards) for r in res.logs)
    assert res.average_length_m == pytest.approx(sum(b.length_m for r in res.logs for b in r.boards) / res.board_count)
    mix = res.product_mix()
    assert sum(d["count"] for d in mix.values()) == res.board_count


def test_residue_prices_add_to_nett_value():
    s = Settings(disc_separation_cm=5, chip_price=200.0, sawdust_price=50.0, pct_fines=10.0)
    res = simulate_pattern([cylinder(20.0)], "25/114/25", "3*38", make_products(), LINE, s, log_price=120.0)
    r = res.logs[0]
    residue = (r.chip_volume * 0.9 * 200.0 + r.sawdust_volume * 50.0) / r.log_volume
    assert res.nett_value_recovery == pytest.approx(res.gross_value_recovery + residue - 120.0)


def test_results_do_not_depend_on_how_discs_are_stored():
    log = Log(3, 23.4, 2.7, taper_mm_per_m=9.0, sweep_mm=22.0, ovality=1.03)
    products = make_products(WaneRule(10, 30, 100, 0))
    exact = saw(log, "25/152/25", "19 25 38 50 38 25 19", products)
    poly = saw(log, "25/152/25", "19 25 38 50 38 25 19", products,
               settings=Settings(disc_separation_cm=5, points_per_disc=720, discretised=True))
    assert [(b.board_type, b.board_no, b.label) for b in exact.boards] == [(b.board_type, b.board_no, b.label) for b in poly.boards]
    assert poly.sawdust_volume == pytest.approx(exact.sawdust_volume, rel=1e-3)


def test_simulation_is_deterministic():
    log = Log(3, 23.4, 2.7, taper_mm_per_m=9.0, sweep_mm=22.0, ovality=1.03)
    a = saw(log, "25/152/25", "19 25 38 50 38 25 19")
    b = saw(log, "25/152/25", "19 25 38 50 38 25 19")
    assert a.boards == b.boards and a.sawdust_volume == b.sawdust_volume
