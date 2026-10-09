"""Edger, cross-cut and wane test, on shapes simple enough to check by hand."""
import math

import numpy as np
import pytest

from conftest import make_products
from engine.edging import best_board, face_interval, depth_ladder, longest_run
from engine.model import EdgingObjective, Rules, Size, WaneRule

Z = np.arange(0, 3001, 50)                      # a 3.0 m flitch, discs every 5 cm
T25 = Size(25, 27)
VOL, LEN = EdgingObjective.VOLUME, EdgingObjective.LENGTH


def box(width_by_disc):
    """A flitch with square edges: clear wood from -w/2 to +w/2 at every depth."""
    w = np.asarray(width_by_disc, dtype=float)
    def chord(v):
        return np.where(w > 0, -w / 2, np.inf), np.where(w > 0, w / 2, -np.inf)
    return chord


def run(chord, products=None, objective=VOL, rules=None, widths=None, z=Z):
    products = products or make_products()
    widths = widths if widths is not None else products.valid_widths(25)
    return best_board(chord, z, 0.0, 27.0, T25, widths, products, objective, rules or Rules())


# ---------------------------------------------------------------- longest run

def test_longest_run_needs_a_common_position():
    lo = np.array([0.0, 0.0, 5.0, 5.0, 0.0])
    hi = np.array([4.0, 4.0, 9.0, 9.0, 4.0])
    z = np.arange(5) * 50
    first, last, c_lo, c_hi = longest_run(lo, hi, z)
    assert (first, last) == (0, 1) and (c_lo, c_hi) == (0.0, 4.0)       # discs 0-1 and 2-3 cannot share a board


def test_longest_run_skips_impossible_discs():
    lo = np.array([np.inf, 0.0, 0.0, 0.0, np.inf, 0.0])
    hi = np.array([-np.inf, 1.0, 1.0, 1.0, -np.inf, 1.0])
    assert longest_run(lo, hi, np.arange(6) * 50)[:2] == (1, 3)


def test_longest_run_none_when_nothing_fits():
    assert longest_run(np.array([np.inf] * 3), np.array([-np.inf] * 3), np.arange(3) * 50) is None


# ---------------------------------------------------------------- width, length, objective

def test_widest_board_that_fits_is_chosen():
    c = run(box(np.full(61, 130.0)))
    assert (c.width.dry, c.length_mm) == (114, 3000)              # 120 wet fits in 130, 160 does not


def test_board_needs_its_wet_width():
    assert run(box(np.full(61, 119.9))).width.dry == 102           # 114 dry needs 120 wet
    assert run(box(np.full(61, 80.9))) is None                     # even 76 dry needs 81 wet


def test_board_is_centred_in_its_allowed_range_by_default():
    c = run(box(np.full(61, 130.0)))
    assert c.u0 == pytest.approx(-60.0)
    assert run(box(np.full(61, 130.0)), rules=Rules(placement="high")).u0 == pytest.approx(-55.0)
    assert run(box(np.full(61, 130.0)), rules=Rules(placement="low")).u0 == pytest.approx(-65.0)


def test_length_is_floored_to_the_increment():
    w = np.zeros(61)
    w[5:53] = 100.0                                               # clear from 0.25 m to 2.60 m: 2.35 m
    c = run(box(w))
    assert c.length_mm == 2100 and (Z[c.first], Z[c.last]) == (250, 2600)


def test_span_exactly_on_an_increment_is_kept_whole():
    w = np.zeros(61)
    w[6:55] = 100.0                                               # 0.30 m to 2.70 m: exactly 2.4 m
    assert run(box(w)).length_mm == 2400


def test_shorter_than_the_minimum_length_gives_no_board():
    w = np.zeros(61)
    w[10:28] = 100.0                                              # 0.85 m clear, minimum is 0.9 m
    assert run(box(w)) is None
    w[10:29] = 100.0                                              # 0.90 m
    assert run(box(w)).length_mm == 900


def test_volume_objective_trades_width_against_length():
    w = np.full(61, 90.0)
    w[0:49] = 170.0                                               # 160 wet fits for the first 2.4 m only
    c = run(box(w))
    assert (c.width.dry, c.length_mm) == (152, 2400)              # 152 x 2.4 beats 76 x 3.0


def test_length_objective_takes_the_longest_board():
    w = np.full(61, 90.0)
    w[0:49] = 170.0
    c = run(box(w), objective=LEN)
    assert (c.width.dry, c.length_mm) == (76, 3000)


def test_value_objective_follows_price():
    w = np.full(61, 90.0)
    w[0:49] = 170.0
    cheap_wide = make_products(prices={(25, 152): 1000.0, (25, 114): 1000.0, (25, 102): 1000.0, (25, 76): 4000.0})
    c = run(box(w), products=cheap_wide, objective=EdgingObjective.VALUE)
    assert (c.width.dry, c.length_mm) == (76, 3000)               # 76 x 3.0 at R4000 beats anything wider at R1000


def test_equal_volume_goes_to_the_wider_board():
    w = np.full(61, 90.0)
    w[0:25] = 170.0                                               # 160 wet fits for 1.2 m: 152 x 1.2 = 76 x 2.4
    w[49:] = 0.0                                                  # and 81 wet fits for 2.4 m
    c = run(box(w))
    assert (c.width.dry, c.length_mm) == (152, 1200)
    c = run(box(w), rules=Rules(prefer_wider_on_tie=False))
    assert (c.width.dry, c.length_mm) == (76, 2400)


def test_invalid_combinations_are_never_cut():
    products = make_products(invalid={(25, 114)})
    assert run(box(np.full(61, 130.0)), products=products).width.dry == 102


def test_no_allowed_length_no_board():
    assert run(box(np.full(61, 130.0)), widths=[]) is None


# ---------------------------------------------------------------- wane

def round_flitch(radius, face=90.0):
    """Sideboard flitch of a cylinder: thickness axis v runs from the plane x = face - 27 to x = face."""
    def chord(v):
        x = face - 27.0 + v
        half = np.sqrt(np.clip(radius ** 2 - x ** 2, 0, None)) * np.ones(len(Z))
        return (-half, half) if radius > abs(x) else (np.full(len(Z), np.inf), np.full(len(Z), -np.inf))
    return chord


WANE = WaneRule(10.0, 30.0, 100.0, 0)


def test_no_wane_rule_means_square_edges():
    # R = 98: the outer face is 77.6 wide, short of the 81 a 76 mm board needs.
    assert run(round_flitch(98.0)) is None
    # R = 100: the outer face is 87.2 wide.
    assert run(round_flitch(100.0)).width.dry == 76


def test_wane_within_the_combined_allowance_is_accepted():
    # R = 98, 76 mm board centred: wane runs 0.76 mm down the edge (allowed 2.5) and 1.72 mm in along
    # the face (allowed 11.4): 0.30 + 0.15 = 0.46 of the allowance.
    a = 90 - math.sqrt(98 ** 2 - 40.5 ** 2)
    b = 40.5 - math.sqrt(98 ** 2 - 90 ** 2)
    assert a / 2.5 + b / 11.4 == pytest.approx(0.455, abs=0.005)
    c = run(round_flitch(98.0), products=make_products(WANE))
    assert (c.width.dry, c.length_mm) == (76, 3000)


def test_wane_beyond_the_combined_allowance_is_refused():
    # R = 97: 1.86 mm down the edge and 4.32 mm along the face: 0.74 + 0.38 = 1.12 of the allowance,
    # although each on its own is inside its limit.
    a = 90 - math.sqrt(97 ** 2 - 40.5 ** 2)
    b = 40.5 - math.sqrt(97 ** 2 - 90 ** 2)
    assert a < 2.5 and b < 11.4 and a / 2.5 + b / 11.4 > 1.0
    assert run(round_flitch(97.0), products=make_products(WANE)) is None


def test_wane_limit_is_solved_to_within_a_tenth_of_a_millimetre():
    # Find the radius at which the allowance is exactly used up, then check both sides of it.
    def used(r):
        return (90 - math.sqrt(r * r - 40.5 ** 2)) / 2.5 + (40.5 - math.sqrt(r * r - 90 ** 2)) / 11.4
    lo, hi = 97.0, 98.0
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if used(mid) > 1 else (lo, mid)
    products = make_products(WANE)
    assert run(round_flitch(hi + 0.05), products=products) is not None
    assert run(round_flitch(hi - 0.05), products=products) is None


def test_zero_length_wane_means_no_wane_at_all():
    products = make_products(WaneRule(10.0, 30.0, 0.0, 0))
    assert run(round_flitch(98.0), products=products) is None


def test_wane_percentages_use_dry_sizes_by_default():
    ladder = depth_ladder(round_flitch(98.0), 27.0, -1.0, 2.5, 8)
    lo, hi = face_interval(ladder, 81.0, 11.4)
    assert (lo <= hi).all()
    strict = make_products(WaneRule(2.0, 30.0, 100.0, 0))          # 0.5 mm allowed depth: 0.76 needed
    assert run(round_flitch(98.0), products=strict) is None


def test_length_wane_limits_how_much_of_the_board_may_be_waney():
    # First 1.5 m of the flitch is R = 98 (waney for a 76 mm board), the rest R = 100 (clean).
    def chord(v):
        x = 63.0 + v
        r = np.where(Z < 1500, 98.0, 100.0)
        half = np.sqrt(np.clip(r ** 2 - x ** 2, 0, None))
        return -half, half
    free = run(chord, products=make_products(WaneRule(10, 30, 100, 0)))
    assert free.length_mm == 3000 and free.wane_discs == 0
    half_ok = run(chord, products=make_products(WaneRule(10, 30, 50, 0)))
    assert half_ok.length_mm == 3000 and half_ok.wane_discs == 30        # 30 of 61 discs are waney
    quarter = run(chord, products=make_products(WaneRule(10, 30, 25, 0)))
    assert quarter.length_mm < 3000 and Z[quarter.last] == 3000          # trimmed from the waney end
    span = quarter.last - quarter.first + 1
    assert quarter.wane_discs <= 0.25 * span
