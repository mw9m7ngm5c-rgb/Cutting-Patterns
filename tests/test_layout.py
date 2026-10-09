import pytest

from engine import notation
from engine.model import CantGuiding, ProductionLine
from engine.sawing import layout


def lay(primary, secondary, products, line):
    return layout(notation.parse(primary, secondary), products, line)


def test_worked_example_from_the_ngomi_run(products, line):
    # 25/114/25 with 2*19 3*38 3*19, 3 mm kerfs: positions confirmed against Simsaw's stored boards.
    L = lay("25/114/25", "2*19 3*38 3*19", products, line)
    assert (L.cant_lo, L.cant_hi) == (-60.0, 60.0)                       # 114 dry is 120 wet
    side = {f.kind: (f.lo, f.hi) for f in L.flitches if f.kind != "cant"}
    assert side["right"] == (63.0, 90.0) and side["left"] == (-90.0, -63.0)   # kerf 3, then 27 wet
    cant = [(f.lo, f.hi) for f in L.flitches if f.kind == "cant"]
    assert cant[0] == (-124.5, -103.5) and cant[-1] == (103.5, 124.5)
    assert cant[2:5] == [(-76.5, -35.5), (-32.5, 8.5), (11.5, 52.5)]     # the three 38s


def test_stack_is_centred_and_boards_are_one_kerf_apart(products, line):
    L = lay("25/152/25", "19 25 38 50 38 25 19", products, line)
    cant = [f for f in L.flitches if f.kind == "cant"]
    assert cant[0].lo == pytest.approx(-cant[-1].hi)
    for a, b in zip(cant, cant[1:]):
        assert b.lo - a.hi == pytest.approx(3.0)
    assert [f.hi - f.lo for f in cant] == [21, 27, 41, 54, 41, 27, 21]


def test_sideboards_step_outward_and_number_from_the_cant(products, line):
    L = lay("25 38/114/38 25", "3*38", products, line)
    right = sorted((f for f in L.flitches if f.kind == "right"), key=lambda f: f.index)
    left = sorted((f for f in L.flitches if f.kind == "left"), key=lambda f: f.index)
    assert [(f.thickness.dry, f.lo, f.hi) for f in right] == [(38, 63.0, 104.0), (25, 107.0, 134.0)]
    assert [(f.thickness.dry, f.lo, f.hi) for f in left] == [(38, -104.0, -63.0), (25, -134.0, -107.0)]


def test_asymmetric_sideboards(products, line):
    L = lay("19/114/25 25", "3*38", products, line)
    assert sum(f.kind == "left" for f in L.flitches) == 1 and sum(f.kind == "right" for f in L.flitches) == 2


def test_every_board_has_a_kerf_on_both_sides(products, line):
    L = lay("25/114/25", "3*38", products, line)
    assert sorted(L.primary_kerfs) == [(-93.0, -90.0), (-63.0, -60.0), (60.0, 63.0), (90.0, 93.0)]
    assert len(L.secondary_kerfs) == 4                                     # two between, two outside
    assert L.secondary_kerfs[0] == (-67.5, -64.5) and L.secondary_kerfs[-1] == (64.5, 67.5)


def test_kerf_size_moves_every_saw_line(products):
    L = lay("25/114/25", "3*38", products, ProductionLine(primary_kerf=5.0, secondary_kerf=4.0))
    right = next(f for f in L.flitches if f.kind == "right")
    assert (right.lo, right.hi) == (65.0, 92.0)
    cant = [f for f in L.flitches if f.kind == "cant"]
    assert cant[1].lo - cant[0].hi == pytest.approx(4.0)
    assert cant[0].lo == pytest.approx(-(3 * 41 + 2 * 4) / 2)


def test_outside_blades_can_have_their_own_kerf(products):
    line = ProductionLine(primary_kerf=7.0, primary_outside_kerf=4.0, primary_outside_blades=1,
                          secondary_kerf=5.0, secondary_outside_kerf=3.0, secondary_outside_blades=1)
    L = lay("25/114/25", "4*38", products, line)
    # primary: the blade next to the cant is an inside blade (7), the slab cut is the outside blade (4)
    assert (60.0, 67.0) in L.primary_kerfs and (94.0, 98.0) in L.primary_kerfs
    widths = [round(b - a, 6) for a, b in L.secondary_kerfs]
    assert widths == [3.0, 5.0, 5.0, 5.0, 3.0]


def test_riving_knives_mark_the_boards_between_them(products, line):
    L = lay("25/152/25", "25 <3*38> 25", products, line)
    assert [f.knives for f in L.flitches if f.kind == "cant"] == [False, True, True, True, False]


def test_unknown_size_is_reported(products, line):
    with pytest.raises(KeyError, match="thickness 32"):
        lay("25/114/25", "3*32", products, line)
    with pytest.raises(KeyError, match="width 200"):
        lay("25/200/25", "3*38", products, line)


def test_live_sawing_lays_the_whole_stack_across_the_log(products, line):
    lo = lay("2*25 38 2*25", "", products, line)
    assert lo.live and lo.cant is None and not lo.secondary_kerfs
    assert [f.kind for f in lo.flitches] == ["live"] * 5
    # 2 x 27 + 41 + 2 x 27 wet and four 3 mm kerfs = 161 mm, centred
    assert lo.flitches[0].lo == pytest.approx(-80.5) and lo.flitches[-1].hi == pytest.approx(80.5)
    assert len(lo.primary_kerfs) == 6


def test_fixed_widths_and_arris_marker_reach_the_layout(products, line):
    lo = lay("25x76/114/25x76", "25 3*38,25", products, line)
    sides = [f for f in lo.flitches if not f.on_cant]
    assert all(f.fixed_width is not None and f.fixed_width.dry == 76 for f in sides)
    assert lo.arris_after == 3
