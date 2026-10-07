"""Pattern generator: enumeration, constraints, pre-screen geometry, ranking, class suggestions."""
import math
from types import SimpleNamespace

import pytest

from engine import generator as G
from engine.model import Log, ProductionLine, Settings, WaneRule
from engine.sawing import simulate_pattern

from conftest import FIXTURES, make_products


def enum(products, line, c=G.Constraints(), face_max=300.0, face_min=lambda w: 0.0):
    cands, truncated = G.enumerate_candidates(products, line, c, face_max, face_min)
    assert not truncated
    return cands


def test_symmetric_and_thicker_to_centre_by_default(products, line):
    cands = enum(products, line)
    assert cands
    for cd in cands:
        assert cd.left == tuple(reversed(cd.right))
        assert cd.secondary == tuple(reversed(cd.secondary))
        n = len(cd.secondary)
        half = cd.secondary[n // 2:]                       # centre outward
        assert all(a >= b for a, b in zip(half, half[1:]))
        assert all(a >= b for a, b in zip(cd.right, cd.right[1:]))


def test_asymmetric_option_finds_simsaws_class_1_pattern(products, line):
    c = G.Constraints(symmetric=False, max_thicknesses=3, cant_widths=(114.0,), max_sideboards_per_side=1)
    keys = {(cd.primary_text, cd.secondary_text) for cd in enum(products, line, c, face_max=270.0)}
    assert ("25/114/25", "2*19 3*38 3*19") in keys
    assert ("25/114/25", "2*19 3*38 3*19") not in {(cd.primary_text, cd.secondary_text) for cd in enum(products, line)}


def test_stacks_fit_the_largest_log_and_fill_the_smallest(products, line):
    k = line.secondary_kerf
    wet = {19: 21, 25: 27, 38: 41, 50: 54}
    face_min = lambda cant_wet: 150.0
    for cd in enum(products, line, face_max=250.0, face_min=face_min):
        h = sum(wet[t] for t in cd.secondary) + k * (len(cd.secondary) - 1)
        assert h <= 250.0
        assert h + 2 * (21 + k) > 150.0                  # no room left for another 19 on each side


def test_limits_on_blades_thicknesses_and_cant_widths(products, line):
    c = G.Constraints(max_primary_blades=4, max_secondary_blades=5, max_thicknesses=2, cant_widths=(114.0,),
                      max_sideboards_per_side=3)
    cands = enum(products, line, c)
    assert cands
    assert all(cd.primary_blades <= 4 and cd.secondary_blades <= 5 for cd in cands)
    assert all(len(cd.thicknesses) <= 2 and cd.cant == 114 for cd in cands)


def test_must_include_and_exclude(products, line):
    c = G.Constraints(must_include=((50.0, 152.0),), exclude=((19.0, 76.0), (19.0, 102.0), (19.0, 114.0), (19.0, 152.0)))
    prods = G.restricted_products(products, c)
    assert not prods.valid_widths(19)
    cands = enum(prods, line, c)
    assert cands and all(50 in cd.thicknesses and 19 not in cd.thicknesses for cd in cands)


def test_cone_finds_the_radius_where_a_board_first_passes(products, line):
    cone = G._Cone(3000, 0.0, products, line)            # no wane allowed (products fixture has none)
    t, w = products.thickness(38), products.width(114)
    # a 41 x 120 wet board from y = 10 to 51: both outer corners must be in the wood
    r = cone._radius_needed(10, 51, t, w)
    assert r == pytest.approx(math.hypot(60, 51), abs=1e-6)
    # straddling the centre: the farther face decides
    assert cone._radius_needed(-30, 11, t, w) == pytest.approx(math.hypot(60, 30), abs=1e-6)


def test_cone_wane_allowance_lowers_the_radius_needed(line):
    plain = make_products()
    waney = make_products(WaneRule(10, 30, 100, 0))
    t, w = plain.thickness(38), plain.width(114)
    r0 = G._Cone(3000, 0, plain, line)._radius_needed(10, 51, t, w)
    r1 = G._Cone(3000, 0, waney, line)._radius_needed(10, 51, t, w)
    assert r1 < r0


def test_cone_board_length_grows_from_the_large_end(products, line):
    cone = G._Cone(3000, 10.0, products, line)           # 10 mm/m: radius grows 5 mm per metre
    t, w = products.thickness(38), products.width(114)
    need = cone._radius_needed(10, 51, t, w)
    # a log 6 mm short of that radius at its small end reaches it 1.2 m along: 1.8 m of clear board
    assert cone._clear_length(need, need - 6.0) == pytest.approx(1800)
    assert cone._clear_length(need, need + 1.0) == 3000
    # the flitch takes whichever width gives the most volume (a narrower board may run longer)
    vol, _, tt, ww = cone._best(10, 51, t, None, need - 6.0)
    assert tt == 38 and vol >= 0.038 * 0.114 * 1.8 - 1e-12


@pytest.fixture(scope="module")
def ngomi():
    from importers import simsaw
    return simsaw.load_inputs(FIXTURES / "ngomi_1")


def test_generator_matches_or_beats_the_dataset_pattern_for_class_2(ngomi):
    ds = ngomi
    logs = ds.logs_in_class(2)
    own = simulate_pattern(logs, "25/152/25", "19 25 38 50 38 25 19", ds.products, ds.lines[0], ds.settings)
    res = G.generate(logs, ds.products, ds.lines[0], ds.settings, 120.0, simulate=30, top=5)
    assert res.enumerated > 1000 and len(res.ranked) == 5
    best = res.ranked[0]
    assert best.result.dry_recovery >= own.dry_recovery - 1e-9
    assert len(best.result.logs) == len(logs)              # finalists are sawn on every log
    scores = [r.score for r in res.ranked]
    assert scores == sorted(scores, reverse=True)
    again = G.generate(logs, ds.products, ds.lines[0], ds.settings, 120.0, simulate=30, top=5)
    assert [(r.primary, r.secondary) for r in again.ranked] == [(r.primary, r.secondary) for r in res.ranked]


def test_target_objective_and_minimum_share(ngomi):
    ds = ngomi
    logs = ds.logs_in_class(2)[:10]
    c = G.Constraints(target=(50.0, 152.0), min_target_share=0.3)
    res = G.generate(logs, ds.products, ds.lines[0], ds.settings, 120.0, G.Objective.TARGET, c, simulate=20, top=3)
    assert res.ranked
    for r in res.ranked:
        assert r.target_share >= 0.3
        assert r.target_volume == pytest.approx(r.result.product_mix()[(50.0, 152.0)]["dry_volume"])


def test_errors_are_plain(ngomi):
    ds = ngomi
    with pytest.raises(G.GeneratorError, match="no logs"):
        G.generate([], ds.products, ds.lines[0], ds.settings, 0)
    with pytest.raises(G.GeneratorError, match="target product"):
        G.generate(ds.logs[:3], ds.products, ds.lines[0], ds.settings, 0, G.Objective.TARGET)
    with pytest.raises(G.GeneratorError, match="curve sawing"):
        G.generate(ds.logs[:3], ds.products, ProductionLine(cant_guiding=1), ds.settings, 0)


def test_representative_logs_span_the_step(ngomi):
    reps = G.representative_logs(24.0, ngomi.logs)
    assert [g.sed_cm for g in reps] == [24.0, 24.5, 24.9]
    assert len({(g.length_m, g.taper_mm_per_m, g.ovality) for g in reps}) == 1


def _step(sed, scored):
    ranked = [SimpleNamespace(primary=p, secondary="s", score=v) for p, v in scored]
    return G.Step(sed, ranked)


def test_grouping_steps_into_classes():
    steps = [_step(18, [("A", 0.540), ("B", 0.538)]), _step(19, [("A", 0.550), ("B", 0.546)]),
             _step(20, [("B", 0.560), ("A", 0.557)]), _step(21, [("B", 0.570), ("C", 0.569)]),
             _step(22, [("C", 0.580)])]
    exact = G.group_steps(steps, 0.0)
    assert [(g.from_cm, g.to_cm, g.primary) for g in exact] == [(18, 19.9, "A"), (20, 21.9, "B"), (22, 22.9, "C")]
    loose = G.group_steps(steps, 0.005)
    assert [(g.from_cm, g.to_cm, g.primary) for g in loose] == [(18, 21.9, "B"), (22, 22.9, "C")]


def test_best_classes_is_the_exact_optimum_for_n_classes():
    # A is best at 18-19, B at 20-21; C is decent everywhere
    steps = [_step(18, [("A", 0.60), ("B", 0.50), ("C", 0.57)]), _step(19, [("A", 0.60), ("B", 0.50), ("C", 0.57)]),
             _step(20, [("B", 0.60), ("A", 0.50), ("C", 0.57)]), _step(21, [("B", 0.60), ("A", 0.50), ("C", 0.57)])]
    one = G.best_classes(steps, 1)
    assert [(g.from_cm, g.to_cm, g.primary) for g in one] == [(18, 21.9, "C")]
    assert one[0].score == pytest.approx(0.57) and one[0].best == pytest.approx(0.60)
    two = G.best_classes(steps, 2)
    assert [(g.from_cm, g.to_cm, g.primary) for g in two] == [(18, 19.9, "A"), (20, 21.9, "B")]
    assert len(G.best_classes(steps, 9)) == 2           # never more classes than help


def test_diameter_chart_cross_checks_every_step(ngomi):
    ds = ngomi
    steps = G.diameter_chart(22, 23, ds.logs, ds.products, ds.lines[0], ds.settings, lambda d: 120.0,
                             simulate=6, top=3, cross=2)
    assert [st.sed_cm for st in steps] == [22.0, 23.0]
    keys = [{G.pattern_key(r) for r in st.ranked} for st in steps]
    for st in steps:                                      # every step's best two are scored at the other step
        for r in st.ranked[:2]:
            assert all(G.pattern_key(r) in k for k in keys)
    assert all(a.score >= b.score for st in steps for a, b in zip(st.ranked, st.ranked[1:]))


def test_an_idle_blade_never_wins_a_tie(products, line, settings):
    logs = [Log(1, 12.0, 3.0, 10.0)]                     # 15 cm at the large end: narrower than a 152 cant
    plain = G.Candidate((), 152.0, (), (38.0, 38.0))
    extra = G.Candidate((19.0,), 152.0, (19.0,), (38.0, 38.0))   # sideboards beyond the log cut nothing
    res = [simulate_pattern(logs, c.primary_text, c.secondary_text, products, line, settings) for c in (plain, extra)]
    assert res[0].dry_recovery == pytest.approx(res[1].dry_recovery)
    a, b = (G._rank(c, 0, r, G.Objective.VOLUME, None) for c, r in zip((plain, extra), res))
    assert a.score > b.score
