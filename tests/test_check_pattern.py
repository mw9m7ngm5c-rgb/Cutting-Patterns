"""Plain-language reasons a pattern cannot be sawn."""
import pytest

from engine.model import ProductionLine
from engine.sawing import check_pattern


@pytest.mark.parametrize("primary, secondary, expect", [
    ("25/114/25", "2*19 3*38 3*19", None),
    ("25/115/25", "2*19", "cant width 115 mm"),
    ("22/114/25", "3*38", "thickness 22 mm"),
    ("25/114/25", "", "needs a secondary pattern"),
    ("25//25", "38", "is not a number"),
    ("25 38 25", "", "live sawing"),
    ("25/114/25", "25 3*38,25", "arris alignment"),
    ("25x76/114/25x76", "3*38", "chipper-profiler"),
    ("25/114/25", "3*38 <", "riving knives need both"),
])
def test_check_pattern(products, line, primary, secondary, expect):
    problems = check_pattern(primary, secondary, products, line)
    if expect is None:
        assert problems == []
    else:
        assert problems and expect in " ".join(problems)


def test_phase_4_machine_settings_are_reported(products):
    problems = check_pattern("25/114/25", "3*38", products, ProductionLine(cant_misalignment_mm=2))
    assert "misalignment" in problems[0]
