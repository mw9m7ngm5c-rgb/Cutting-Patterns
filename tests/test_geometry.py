import math

import numpy as np
import pytest

from engine.log import (build_core_sections, build_sections, centreline_y, disc_positions_mm, log_volume_m3,
                        nominal_diameter_cm, nominal_length_m)
from engine.model import Log, NominalDiameter, ProductionLine, Settings

S5 = Settings(disc_separation_cm=5)


def test_discs_every_separation_including_both_ends():
    z = disc_positions_mm(2.7, 5)
    assert z[0] == 0 and z[-1] == 2700 and len(z) == 55 and set(np.diff(z)) == {50}


def test_discs_always_include_the_large_end():
    z = disc_positions_mm(2.72, 10)
    assert list(z[-3:]) == [2600, 2700, 2720]


def test_diameter_grows_linearly_by_the_taper():
    sec = build_sections(Log(1, 20.0, 3.0, taper_mm_per_m=10.0), S5)
    assert sec.rh[0] == pytest.approx(100.0) and sec.rh[-1] == pytest.approx(115.0)
    assert sec.rh[30] == pytest.approx(107.5)          # 1.5 m: 200 + 15 mm diameter


def test_ovality_is_vertical_over_horizontal_with_geometric_mean_diameter():
    sec = build_sections(Log(1, 20.0, 3.0, ovality=1.21), S5)
    assert sec.rv[0] / sec.rh[0] == pytest.approx(1.21)
    assert math.sqrt(2 * sec.rv[0] * 2 * sec.rh[0]) == pytest.approx(200.0)


def test_sweep_is_horns_up_with_both_ends_on_the_datum():
    z = disc_positions_mm(3.0, 5)
    y = centreline_y(z, 3000.0, 30.0)
    assert y[0] == pytest.approx(0.0, abs=1e-6) and y[-1] == pytest.approx(0.0, abs=1e-6)
    assert y[len(z) // 2] == pytest.approx(-30.0)       # the middle hangs below by the sweep
    assert (y <= 1e-9).all()


def test_sweep_is_a_constant_radius_arc():
    z = disc_positions_mm(3.0, 5).astype(float)
    y = centreline_y(z, 3000.0, 30.0)
    radius = (1500.0 ** 2 + 30.0 ** 2) / 60.0
    centre_y = radius - 30.0
    assert np.allclose(np.hypot(z - 1500.0, y - centre_y), radius)


def test_straight_log_has_a_straight_centreline():
    assert not centreline_y(disc_positions_mm(3.0, 5), 3000.0, 0.0).any()


def test_defect_core_follows_sweep_and_ovality_but_not_taper():
    log = Log(1, 20.0, 3.0, taper_mm_per_m=10.0, sweep_mm=20.0, ovality=1.1, defect_core_cm=8.0)
    core, sec = build_core_sections(log, S5), build_sections(log, S5)
    assert np.allclose(core.cy, sec.cy)
    assert np.allclose(core.rv / core.rh, 1.1)
    assert np.allclose(np.sqrt(core.rv * core.rh), 40.0)          # constant: no taper


def test_chords_of_a_circle():
    sec = build_sections(Log(1, 20.0, 1.0), S5)
    lo, hi = sec.chord_x(60.0)
    assert hi[0] == pytest.approx(80.0) and lo[0] == pytest.approx(-80.0)      # 60-80-100 triangle
    lo, hi = sec.chord_y(-80.0)
    assert hi[0] == pytest.approx(60.0) and lo[0] == pytest.approx(-60.0)


def test_a_line_that_misses_the_log_gives_an_empty_chord():
    sec = build_sections(Log(1, 20.0, 1.0), S5)
    lo, hi = sec.chord_x(101.0)
    assert (lo > hi).all()


def test_polygon_discs_agree_with_ellipses():
    log = Log(1, 22.0, 2.4, taper_mm_per_m=9.0, sweep_mm=18.0, ovality=1.04)
    exact = build_sections(log, S5)
    poly = build_sections(log, Settings(disc_separation_cm=5, points_per_disc=720, discretised=True))
    for y in (-90.0, -30.0, 0.0, 55.0, 80.0):
        (a, b), (c, d) = exact.chord_x(y), poly.chord_x(y)
        assert np.allclose(a, c, atol=0.05) and np.allclose(b, d, atol=0.05)
    for x in (-100.0, 20.0, 75.0):
        (a, b), (c, d) = exact.chord_y(x), poly.chord_y(x)
        assert np.allclose(a, c, atol=0.05) and np.allclose(b, d, atol=0.05)
    assert np.allclose(exact.areas(), poly.areas(), rtol=1e-4)


def test_geometric_volume_of_a_cylinder():
    sec = build_sections(Log(1, 20.0, 3.0), S5)
    assert sec.geometric_volume_m3() == pytest.approx(math.pi * 0.1 ** 2 * 3.0)


@pytest.mark.parametrize("sed,odd,even,whole", [(18.0, 19, 18, 18), (19.9, 19, 20, 20), (20.0, 21, 20, 20),
                                                (21.4, 21, 22, 21), (21.9, 21, 22, 22), (24.0, 25, 24, 24),
                                                (25.9, 25, 26, 26), (18.5, 19, 18, 19), (19.4, 19, 20, 19)])
def test_nominal_diameter_classes(sed, odd, even, whole):
    assert nominal_diameter_cm(sed, NominalDiameter.ODD) == odd
    assert nominal_diameter_cm(sed, NominalDiameter.EVEN) == even
    assert nominal_diameter_cm(sed, NominalDiameter.WHOLE) == whole


def test_nominal_length_rounds_down_to_the_increment():
    assert nominal_length_m(2.7, 0.3) == pytest.approx(2.7)
    assert nominal_length_m(2.95, 0.3) == pytest.approx(2.7)
    assert nominal_length_m(3.0, 0.3) == pytest.approx(3.0)


def test_nominal_log_volume_worked_example():
    # Log 8 of the Ngomi run: 21.4 cm -> 21 cm class, 2.7 m, nominal taper 10 mm/m.
    log = Log(8, 21.4, 2.7, taper_mm_per_m=9.5)
    v = log_volume_m3(log, Settings(nominal_taper_mm_per_m=10.0))
    assert v == pytest.approx(math.pi / 4 * (0.21 + 0.5 * 2.7 * 0.010) ** 2 * 2.7)
    assert v == pytest.approx(0.105927, abs=1e-6)


def test_each_nominal_option_can_be_switched_off():
    log = Log(1, 21.4, 2.75, taper_mm_per_m=8.0)
    actual = Settings(use_nominal_diameter=False, use_nominal_length=False, use_nominal_taper=False)
    assert log_volume_m3(log, actual) == pytest.approx(math.pi / 4 * (0.214 + 0.5 * 2.75 * 0.008) ** 2 * 2.75)
    only_d = Settings(use_nominal_diameter=True, use_nominal_length=False, use_nominal_taper=False)
    assert log_volume_m3(log, only_d) == pytest.approx(math.pi / 4 * (0.21 + 0.5 * 2.75 * 0.008) ** 2 * 2.75)


def test_rotation_turns_the_sweep_and_offsets_move_the_log():
    log = Log(1, 30.0, 3.0, 10.0, sweep_mm=40.0)
    plain = build_sections(log, S5)
    turned = build_sections(log, S5, ProductionLine(log_rotation_deg=90))
    _, cy = plain.centres()
    cx_t, cy_t = turned.centres()
    assert np.allclose(cy_t, 0, atol=1e-6) and np.allclose(np.abs(cx_t), np.abs(cy), atol=1e-6)
    assert turned.areas() == pytest.approx(plain.to_polygons(S5.points_per_disc).areas(), rel=1e-9)
    moved = build_sections(log, S5, ProductionLine(primary_offset_mm=12, log_misalignment_mm=20))
    cx_m, _ = moved.centres()
    assert cx_m[0] == pytest.approx(12 - 10) and cx_m[-1] == pytest.approx(12 + 10)