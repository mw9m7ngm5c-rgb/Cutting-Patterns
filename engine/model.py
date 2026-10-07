"""Plain data structures for inputs and results. No behaviour beyond lookups and unit conversion."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class SawType(IntEnum):
    CANT_LIVE = 0
    CANT_LIVE_GROUPED = 1
    CHIPPER_PROFILER = 2
    CHIPPER_PROFILER_GROUPED = 3


class CantGuiding(IntEnum):
    NONE = 0
    HALF_TAPER = 1  # code assumed, see ASSUMPTIONS A-30
    FULL_TAPER = 2  # code assumed, see ASSUMPTIONS A-30


class EdgingObjective(IntEnum):
    VOLUME = 0
    LENGTH = 1  # code assumed, see ASSUMPTIONS A-09
    VALUE = 2   # not a documented Simsaw option; ours


class NominalDiameter(IntEnum):
    ODD = 0
    EVEN = 1   # code assumed, see ASSUMPTIONS A-19
    WHOLE = 2  # code assumed, see ASSUMPTIONS A-19


@dataclass(frozen=True)
class Size:
    """A thickness or a width: dry (nominal) and wet (green target) size in mm."""
    dry: float
    wet: float


@dataclass(frozen=True)
class LengthClass:
    name: str
    min_m: float
    max_m: float
    incr_m: float

    def lengths_mm(self) -> list[int]:
        lo, hi, step = round(self.min_m * 1000), round(self.max_m * 1000), round(self.incr_m * 1000)
        if step <= 0:
            return [lo]
        return list(range(lo, hi + 1, step))


@dataclass(frozen=True)
class WaneRule:
    """Allowed wane for one thickness x width product.

    thickness_pct: share of the board thickness that wane may take at an edge.
    width_pct:     share of the board width that wane may take on a face.
    length_wane:   share of the board length on which any wane may appear (type 0 = percent).
    """
    thickness_pct: float = 0.0
    width_pct: float = 0.0
    length_wane: float = 100.0
    length_wane_type: int = 0


NO_WANE = WaneRule(0.0, 0.0, 0.0, 0)


@dataclass(frozen=True)
class Combination:
    thickness: float      # dry mm
    width: float          # dry mm
    length_class: str
    grade: str
    valid: bool
    price: float          # R per m3 of dry volume


@dataclass
class Products:
    thicknesses: list[Size]
    widths: list[Size]
    length_classes: list[LengthClass]
    combinations: list[Combination]
    board_grades: list[str] = field(default_factory=lambda: ["All board grades"])
    wane: dict[tuple[float, float], WaneRule] = field(default_factory=dict)
    centre_boards: set[tuple[float, float]] = field(default_factory=set)

    def thickness(self, dry: float) -> Size:
        for s in self.thicknesses:
            if abs(s.dry - dry) < 1e-6:
                return s
        raise KeyError(f"thickness {dry:g} mm is not defined in this dataset")

    def width(self, dry: float) -> Size:
        for s in self.widths:
            if abs(s.dry - dry) < 1e-6:
                return s
        raise KeyError(f"width {dry:g} mm is not defined in this dataset")

    def valid_widths(self, thickness_dry: float) -> list[Size]:
        """Widths that form at least one valid combination with this thickness, narrow to wide."""
        ok = {c.width for c in self.combinations if c.valid and abs(c.thickness - thickness_dry) < 1e-6}
        return sorted((w for w in self.widths if w.dry in ok), key=lambda s: s.dry)

    def is_valid(self, thickness_dry: float, width_dry: float) -> bool:
        return any(c.valid and abs(c.thickness - thickness_dry) < 1e-6 and abs(c.width - width_dry) < 1e-6
                   for c in self.combinations)

    def wane_rule(self, thickness_dry: float, width_dry: float) -> WaneRule:
        return self.wane.get((thickness_dry, width_dry), NO_WANE)

    def allowed_lengths_mm(self, thickness_dry: float, width_dry: float) -> list[int]:
        """Every board length (mm) that some valid combination of this product allows, ascending."""
        names = {c.length_class for c in self.combinations
                 if c.valid and abs(c.thickness - thickness_dry) < 1e-6 and abs(c.width - width_dry) < 1e-6}
        out: set[int] = set()
        for lc in self.length_classes:
            if lc.name in names:
                out.update(lc.lengths_mm())
        return sorted(out)

    def price(self, thickness_dry: float, width_dry: float, length_mm: int, grade: str | None = None) -> float:
        """Price (R/m3) of the valid combination that covers this board; 0 if none does."""
        for c in self.combinations:
            if not c.valid or abs(c.thickness - thickness_dry) > 1e-6 or abs(c.width - width_dry) > 1e-6:
                continue
            if grade is not None and c.grade != grade:
                continue
            for lc in self.length_classes:
                if lc.name == c.length_class and length_mm in lc.lengths_mm():
                    return c.price
        return 0.0


@dataclass(frozen=True)
class Log:
    """One log, in the units Simsaw stores: cm, m, mm/m, mm (total sweep), cm (defect core)."""
    no: int
    sed_cm: float
    length_m: float
    taper_mm_per_m: float = 0.0
    sweep_mm: float = 0.0
    ovality: float = 1.0
    defect_core_cm: float = 0.0
    grade: str = "All log grades"

    @property
    def sweep_mm_per_m(self) -> float:
        return self.sweep_mm / self.length_m if self.length_m else 0.0

    @property
    def defect_core_pct(self) -> float:
        return 100.0 * self.defect_core_cm / self.sed_cm if self.sed_cm else 0.0


@dataclass(frozen=True)
class LogClass:
    no: int
    min_diameter_cm: float
    max_diameter_cm: float
    min_length_m: float = 0.0
    max_length_m: float = 99.0
    length_incr_m: float = 0.3
    min_taper: float = 0.0
    max_taper: float = 999.0
    min_sweep: float = 0.0       # mm/m
    max_sweep: float = 999.0     # mm/m
    min_ovality: float = 0.0
    max_ovality: float = 9.0
    min_defect_core: float = 0.0   # % of SED
    max_defect_core: float = 100.0
    log_price: float = 0.0         # R/m3
    grades: tuple[str, ...] = ()

    def contains(self, log: Log) -> bool:
        e = 1e-4
        return (self.min_diameter_cm - e <= log.sed_cm <= self.max_diameter_cm + e
                and self.min_length_m - e <= log.length_m <= self.max_length_m + e
                and self.min_taper - e <= log.taper_mm_per_m <= self.max_taper + e
                and self.min_sweep - e <= log.sweep_mm_per_m <= self.max_sweep + e
                and self.min_ovality - e <= log.ovality <= self.max_ovality + e
                and self.min_defect_core - e <= log.defect_core_pct <= self.max_defect_core + e
                and (not self.grades or log.grade in self.grades))


@dataclass(frozen=True)
class ProductionLine:
    name: str = "Line 1"
    saw_type: SawType = SawType.CANT_LIVE
    primary_machine: str = ""      # label only (frame saw, band saw, ...); the numbers below drive the simulation
    secondary_machine: str = ""
    primary_kerf: float = 3.0
    primary_outside_kerf: float | None = None
    primary_outside_blades: int = 0
    secondary_kerf: float = 3.0
    secondary_outside_kerf: float | None = None
    secondary_outside_blades: int = 0
    primary_resaw: bool = False
    primary_resaw_kerf: float = 5.0
    secondary_resaw: bool = False
    secondary_resaw_kerf: float = 5.0
    cant_guiding: CantGuiding = CantGuiding.NONE
    max_sweep: float = 999.0
    log_rotation_deg: float = 0.0
    log_misalignment_mm: float = 0.0
    primary_offset_mm: float = 0.0
    cant_misalignment_mm: float = 0.0
    secondary_offset_mm: float = 0.0
    edging_objective: EdgingObjective = EdgingObjective.VOLUME
    edger_blades: int = 2
    edger_kerf: float = 5.0
    second_board_width: str = "Best"
    max_boards_per_flitch: int = 0


@dataclass(frozen=True)
class Settings:
    use_nominal_diameter: bool = True
    nominal_diameter: NominalDiameter = NominalDiameter.ODD
    use_nominal_length: bool = True
    nominal_length_incr_m: float = 0.3
    use_nominal_taper: bool = True
    nominal_taper_mm_per_m: float = 10.0
    disc_separation_cm: float = 10.0
    points_per_disc: int = 32
    discretised: bool = False     # False = analytical ellipses (Simsaw "Analytical"), True = polygons
    seed: int = 1
    chip_price: float = 0.0       # R/m3
    sawdust_price: float = 0.0    # R/m3
    pct_fines: float = 0.0


@dataclass(frozen=True)
class Rules:
    """Rules the Simsaw documents leave open. The defaults are the ones fitted to the Test1 run
    (docs/ASSUMPTIONS.md, section B). Exposed so tests and experiments can vary them; the app does not."""
    wane_on_wet_sizes: bool = False        # wane percentages are taken of the dry (nominal) sizes
    width_wane_edge_share: float = 0.5     # each edge may use this share of the width-wane percentage
    wane_ladder: int = 8                   # depth steps used to solve the combined wane limit
    prefer_wider_on_tie: bool = True       # equal objective: take the wider board
    placement: str = "centre"              # where in its allowed range an edged board sits: centre | high | low


# ---------------------------------------------------------------- results

@dataclass(frozen=True)
class Board:
    board_type: int          # 0 left sideboard, 1 right sideboard, 2 cant board
    board_no: int            # sideboards: outward from the cant; cant boards: along the secondary string
    thickness: float         # dry mm
    width: float             # dry mm
    length_m: float
    left: float              # mm, saw frame (x)
    right: float
    bottom: float            # mm, saw frame (y)
    top: float
    front_m: float           # m from the small end
    back_m: float
    resawn: bool = False
    resaw_position: float = 0.0
    edged: bool = False
    grade: str = "All board grades"
    dry_volume: float = 0.0  # m3
    wet_volume: float = 0.0
    value: float = 0.0       # R

    @property
    def label(self) -> str:
        return f"{self.thickness:g}x{self.width:g}x{self.length_m:.1f}m"


@dataclass
class LogResult:
    log: Log
    boards: list[Board]
    log_volume: float        # m3, nominal or actual according to Settings
    sawdust_volume: float
    chip_volume: float

    @property
    def dry_board_volume(self) -> float:
        return sum(b.dry_volume for b in self.boards)

    @property
    def wet_board_volume(self) -> float:
        return sum(b.wet_volume for b in self.boards)

    @property
    def board_value(self) -> float:
        return sum(b.value for b in self.boards)

    @property
    def shrinkage_volume(self) -> float:
        return self.wet_board_volume - self.dry_board_volume


@dataclass
class PatternResult:
    primary: str
    secondary: str
    logs: list[LogResult]
    log_price: float = 0.0
    chip_price: float = 0.0
    sawdust_price: float = 0.0
    pct_fines: float = 0.0

    @property
    def log_volume(self) -> float:
        return sum(r.log_volume for r in self.logs)

    @property
    def board_count(self) -> int:
        return sum(len(r.boards) for r in self.logs)

    @property
    def dry_recovery(self) -> float:
        v = self.log_volume
        return sum(r.dry_board_volume for r in self.logs) / v if v else 0.0

    @property
    def wet_recovery(self) -> float:
        v = self.log_volume
        return sum(r.wet_board_volume for r in self.logs) / v if v else 0.0

    @property
    def gross_value_recovery(self) -> float:
        """R of boards per m3 of log."""
        v = self.log_volume
        return sum(r.board_value for r in self.logs) / v if v else 0.0

    @property
    def residue_value_recovery(self) -> float:
        v = self.log_volume
        if not v:
            return 0.0
        chips = sum(r.chip_volume for r in self.logs) * (1 - self.pct_fines / 100.0) * self.chip_price
        dust = sum(r.sawdust_volume for r in self.logs) * self.sawdust_price
        return (chips + dust) / v

    @property
    def nett_value_recovery(self) -> float:
        return self.gross_value_recovery + self.residue_value_recovery - self.log_price

    @property
    def average_length_m(self) -> float:
        n = self.board_count
        return sum(b.length_m for r in self.logs for b in r.boards) / n if n else 0.0

    def product_mix(self) -> dict[tuple[float, float], dict[str, float]]:
        """Per thickness x width: piece count and dry volume."""
        out: dict[tuple[float, float], dict[str, float]] = {}
        for r in self.logs:
            for b in r.boards:
                d = out.setdefault((b.thickness, b.width), {"count": 0, "dry_volume": 0.0})
                d["count"] += 1
                d["dry_volume"] += b.dry_volume
        return dict(sorted(out.items()))
