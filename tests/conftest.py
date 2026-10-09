import pathlib

import pytest

from engine.model import (Combination, LengthClass, Log, Products, ProductionLine, Settings, Size, WaneRule)
from importers import simsaw

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def ngomi_run():
    return simsaw.load_run(FIXTURES / "ngomi_1", "Test1")


@pytest.fixture(scope="session")
def ngomi_inputs():
    return simsaw.load_inputs(FIXTURES / "ngomi_1")


def make_products(wane: WaneRule | None = None, invalid=(), prices=None, centre=()) -> Products:
    """Ngomi sizes, every combination valid unless listed, one length class 0.9-6.6 m in 0.3 m steps."""
    th = [Size(19, 21), Size(25, 27), Size(38, 41), Size(50, 54)]
    wd = [Size(76, 81), Size(102, 107), Size(114, 120), Size(152, 160)]
    combos = [Combination(t.dry, w.dry, "All", "All board grades", (t.dry, w.dry) not in invalid,
                          (prices or {}).get((t.dry, w.dry), 4000.0)) for t in th for w in wd]
    rules = {(t.dry, w.dry): wane for t in th for w in wd} if wane else {}
    return Products(th, wd, [LengthClass("All", 0.9, 6.6, 0.3)], combos, wane=rules, centre_boards=set(centre))


@pytest.fixture
def products():
    return make_products()


@pytest.fixture
def line():
    return ProductionLine(primary_kerf=3.0, secondary_kerf=3.0, edger_kerf=5.0)


@pytest.fixture
def settings():
    return Settings(disc_separation_cm=5, points_per_disc=64)


def cylinder(diameter_cm: float, length_m: float = 3.0, **kw) -> Log:
    return Log(1, diameter_cm, length_m, **kw)
