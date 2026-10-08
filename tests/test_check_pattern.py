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
    ("25 38 25", "", None),
    ("25 38 25", "38", "takes no secondary"),
    ("25/114/25", "25 3*38,25", None),
    ("25/114/25", "25 3*38,", "between two boards"),
    ("25x76/114/25x76", "3*38", "chipper-profiler"),
    ("25x77/114/25x77", "3*38", "width 77 mm"),
    ("25/114/25", "3*38 <", "riving knives need both"),
])
def test_check_pattern(products, line, primary, secondary, expect):
    problems = check_pattern(primary, secondary, products, line)
    if expect is None:
        assert problems == []
    else:
        assert problems and expect in " ".join(problems)


def test_machine_settings_no_longer_stop_a_pattern(products):
    line = ProductionLine(cant_misalignment_mm=2, cant_guiding=1, log_rotation_deg=10, secondary_offset_mm=4)
    assert check_pattern("25/114/25", "3*38", products, line) == []
    profiler = ProductionLine(saw_type=2)
    assert check_pattern("25x76/114/25x76", "25x76 3*38 25x76", products, profiler) == []
