import pytest

from engine.notation import (Item, PatternError, parse, parse_primary, parse_stack, serialise,
                             serialise_primary, serialise_stack)

# Every pattern that appears in the reference dataset, the template, the help pages and the course notes.
PRIMARIES = ["25/114/25", "19/152/19", "25/152/25", "25/76/25", "25 38/114/38 25", "2*25/114/2*25",
             "38/114/38", "25/200/25", "/114/", "3*25 2*38 3*25"]
SECONDARIES = ["2*19 3*38 3*19", "2*19 25 50 25 2*19", "19 25 38 50 38 25 19", "5*25", "25 3*38 25",
               "2*25 2*38 2*25", "9*25", "6*38", "25 5*38 25", "8*25", "2*25 4*38 2*25",
               "25 3*38,25", "25 <3*38> 25", "25<4*25>25", "25x76 3*38 25x76"]


@pytest.mark.parametrize("text", PRIMARIES)
def test_primary_round_trip(text):
    assert serialise_primary(parse_primary(text)) == text


@pytest.mark.parametrize("text", [s for s in SECONDARIES if s != "25<4*25>25"])
def test_secondary_round_trip(text):
    assert serialise_stack(parse_stack(text)) == text


def test_help_example_without_spaces_normalises():
    # The centre-board help page writes "25<4*25>25"; we read it and write it back with spaces.
    assert serialise_stack(parse_stack("25<4*25>25")) == "25 <4*25> 25"


def test_cant_pattern_structure():
    p = parse("25 38/114/38 25", "25 3*38 25")
    assert p.primary.cant == 114
    assert p.primary.left.thicknesses == [25, 38]     # outermost first
    assert p.primary.right.thicknesses == [38, 25]    # next to the cant first
    assert p.secondary.thicknesses == [25, 38, 38, 38, 25]
    assert not p.is_live
    assert serialise(p) == ("25 38/114/38 25", "25 3*38 25")


def test_multiplier_expands_and_collapses():
    assert parse_stack("3*38").thicknesses == [38, 38, 38]
    assert serialise_stack(parse_stack("38 38 38")) == "3*38"


def test_arris_blade():
    s = parse_stack("25 3*38,25")
    assert s.arris_after == 3 and s.thicknesses == [25, 38, 38, 38, 25]


def test_arris_between_equal_boards_does_not_merge():
    s = parse_stack("2*38,38")
    assert s.arris_after == 1
    assert serialise_stack(s) == "2*38,38"


def test_riving_knives():
    s = parse_stack("25 <3*38> 25")
    assert s.knives == (1, 3)
    assert [s.inside_knives(i) for i in range(5)] == [False, True, True, True, False]


def test_knives_between_equal_boards_do_not_merge():
    s = parse_stack("25 <2*25> 25")
    assert s.knives == (1, 2)
    assert serialise_stack(s) == "25 <2*25> 25"


def test_chipper_profiler_sideboard_width():
    s = parse_stack("25x76 3*38 25x76")
    assert s.items[0] == Item(25, 76) and s.items[1] == Item(38, None)


def test_live_sawing_has_no_cant():
    p = parse("3*25 2*38 3*25")
    assert p.is_live and p.primary.left.thicknesses == [25, 25, 25, 38, 38, 25, 25, 25]


@pytest.mark.parametrize("bad", ["25//25", "25/abc/25", "25 /114", "25 <3*38 25", "25 3*38> 25",
                                 ",25", "25 ,,38", "25 x 38", "0*25", "25/114/25,"])
def test_bad_patterns_are_rejected(bad):
    with pytest.raises(PatternError):
        if "/" in bad:
            parse_primary(bad)
        else:
            parse_stack(bad)
