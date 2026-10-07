"""Log generator: seeded, within physical bounds, distributions behave as specified."""
import numpy as np
import pytest

from engine.loggen import Distribution, GeneratorSpec, Range, draw, generate_logs

NGOMI = GeneratorSpec(200, Range(17.0, 41.9), Range(2.4, 3.0), 0.3, Range(8, 11, Distribution.NORMAL_95),
                      Range(0, 15, Distribution.NORMAL_95), Range(0.95, 1.05, Distribution.NORMAL_95))


def test_same_seed_same_logs_and_different_seed_different_logs():
    a = generate_logs(NGOMI, np.random.default_rng(1))
    b = generate_logs(NGOMI, np.random.default_rng(1))
    c = generate_logs(NGOMI, np.random.default_rng(2))
    assert a == b
    assert a != c


def test_lengths_fall_on_the_increment_and_within_limits():
    logs = generate_logs(NGOMI, np.random.default_rng(5))
    assert {g.length_m for g in logs} == {2.4, 2.7, 3.0}


def test_uniform_stays_inside_the_limits():
    logs = generate_logs(NGOMI, np.random.default_rng(3))
    assert all(17.0 <= g.sed_cm <= 41.9 for g in logs)
    assert [g.no for g in logs] == list(range(1, 201))


@pytest.mark.parametrize("dist, inside", [(Distribution.NORMAL_95, 0.95), (Distribution.NORMAL_65, 0.65)])
def test_normal_distributions_put_the_stated_share_inside_the_limits(dist, inside):
    x = draw(Range(10, 20, dist), 200_000, np.random.default_rng(7))
    share = np.mean((x >= 10) & (x <= 20))
    assert share == pytest.approx(inside, abs=0.005)
    assert np.mean(x) == pytest.approx(15, abs=0.02)


def test_sweep_is_stored_as_total_mm_and_core_as_cm():
    spec = GeneratorSpec(50, Range(30, 30), Range(3.0, 3.0), 0.3, sweep_mm_per_m=Range(10, 10),
                         defect_core_pct=Range(20, 20))
    for g in generate_logs(spec, np.random.default_rng(1)):
        assert g.sweep_mm == pytest.approx(30.0)          # 10 mm/m x 3 m
        assert g.defect_core_cm == pytest.approx(6.0)     # 20 % of 30 cm
        assert g.sweep_mm_per_m == pytest.approx(10.0)


def test_no_negative_sweep_taper_or_core():
    spec = GeneratorSpec(2000, Range(20, 30), Range(3.0, 3.0), 0.3, Range(0, 1, Distribution.NORMAL_65),
                         Range(0, 1, Distribution.NORMAL_65), Range(0.9, 1.1), Range(0, 1, Distribution.NORMAL_65))
    logs = generate_logs(spec, np.random.default_rng(11))
    assert min(g.taper_mm_per_m for g in logs) >= 0
    assert min(g.sweep_mm for g in logs) >= 0
    assert min(g.defect_core_cm for g in logs) >= 0
