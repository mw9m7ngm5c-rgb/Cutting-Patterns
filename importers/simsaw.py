"""Read a Simsaw 6 dataset into engine objects.

Source is either a .mdb file (read with access-parser) or a directory of JSON files written by
``export_fixtures.py``. Two views of a dataset:

    load_inputs(src)        the current inputs (logs, products, line, patterns, settings)
    load_run(src, name)     a batch run's own snapshot (run_* tables) plus Simsaw's stored results

A run snapshot has its own keys: thicknesses, widths and logs are renumbered, and only valid
combinations are copied. Run tables are therefore never joined to input tables by uid.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field

from engine.model import (CantGuiding, Combination, EdgingObjective, LengthClass, Log, LogClass,
                          NominalDiameter, Products, ProductionLine, SawType, Settings, Size, WaneRule)


def _r(v, nd=4):
    """Access stores single-precision floats; 21.399999618 means 21.4."""
    return round(float(v), nd) if v is not None else 0.0


class Source:
    def __init__(self, path: str | pathlib.Path):
        self.path = pathlib.Path(path)
        self._db = None
        if self.path.is_file():
            from access_parser import AccessParser
            self._db = AccessParser(str(self.path))
        elif not self.path.is_dir():
            raise FileNotFoundError(f"{self.path} is neither a .mdb file nor a fixtures directory")
        self._cache: dict[str, list[dict]] = {}

    def table(self, name: str) -> list[dict]:
        if name not in self._cache:
            if self._db is not None:
                if name not in self._db.catalog:
                    rows = []
                else:
                    cols = self._db.parse_table(name)
                    keys = list(cols)
                    n = len(cols[keys[0]]) if keys else 0
                    rows = [{k: cols[k][i] for k in keys} for i in range(n)]
            else:
                f = self.path / f"{name}.json"
                rows = json.loads(f.read_text()) if f.exists() else []
            self._cache[name] = rows
        return self._cache[name]


@dataclass
class PatternDef:
    uid: int
    line_name: str
    log_class_no: int
    pattern_no: int
    primary: str
    secondary: str


@dataclass
class Dataset:
    products: Products
    log_classes: list[LogClass]
    logs: list[Log]
    lines: list[ProductionLine]
    patterns: list[PatternDef]
    settings: Settings
    name: str = ""

    def logs_in_class(self, class_no: int) -> list[Log]:
        lc = next(c for c in self.log_classes if c.no == class_no)
        return [g for g in self.logs if lc.contains(g)]

    def log_class(self, class_no: int) -> LogClass:
        return next(c for c in self.log_classes if c.no == class_no)

    def line(self, name: str | None = None) -> ProductionLine:
        if name is None:
            return self.lines[0]
        return next(ln for ln in self.lines if ln.name == name)


@dataclass
class ReferenceBoard:
    pattern_uid: int
    log_no: int
    board_type: int
    board_no: int
    thickness: float
    width: float
    length_m: float
    left: float
    right: float
    bottom: float
    top: float
    front_m: float
    back_m: float
    resawn: bool
    resaw_position: float
    dry_volume: float
    wet_volume: float
    value: float


@dataclass
class ReferenceLog:
    pattern_uid: int
    log_no: int
    boards: int
    dry_board_volume: float
    wet_board_volume: float
    board_value: float
    sawdust_volume: float
    chip_volume: float
    log_volume: float


@dataclass
class Run:
    name: str
    dataset: Dataset                       # built from the run_* snapshot
    log_results: list[ReferenceLog] = field(default_factory=list)
    board_results: list[ReferenceBoard] = field(default_factory=list)
    oneliner: list[dict] = field(default_factory=list)

    def logs_for(self, pattern_uid: int) -> list[Log]:
        nos = {r.log_no for r in self.log_results if r.pattern_uid == pattern_uid}
        return [g for g in self.dataset.logs if g.no in nos]


def _settings(src: Source) -> Settings:
    ints = {r["variable_name"]: r["variable_value"] for r in src.table("misc_integers")}
    dbl = {r["variable_name"]: r["variable_value"] for r in src.table("misc_doubles")}
    return Settings(
        use_nominal_diameter=bool(ints.get("Use nominal diameter", 1)),
        nominal_diameter=NominalDiameter(int(ints.get("Nominal diameter", 0))),
        use_nominal_length=bool(ints.get("Use nominal length", 1)),
        nominal_length_incr_m=_r(dbl.get("Nominal length incr", 0.3)),
        use_nominal_taper=bool(ints.get("Use nominal taper", 1)),
        nominal_taper_mm_per_m=_r(dbl.get("Nominal taper", 10.0)),
        disc_separation_cm=float(ints.get("Disc separation", 10)),
        points_per_disc=int(ints.get("Points per disc", 32)),
        discretised=bool(ints.get("Discretised logs", 0)),
        seed=int(ints.get("Seed value", 0)) or 1,
        chip_price=_r(dbl.get("Chip price", 0.0)),
        sawdust_price=_r(dbl.get("Sawdust price", 0.0)),
        pct_fines=float(ints.get("Percentage fines", 0)),
        arris_small_end=bool(ints.get("Arris from top x-sec", 1)),
    )


def _products(src: Source, prefix: str) -> Products:
    th = {r["thickness_uid"]: Size(_r(r["dry_thickness"]), _r(r["wet_thickness"])) for r in src.table(prefix + "thicknesses")}
    wd = {r["width_uid"]: Size(_r(r["dry_width"]), _r(r["wet_width"])) for r in src.table(prefix + "widths")}
    ln = {r["length_uid"]: LengthClass(r.get("description") or "All", _r(r["min_length"]), _r(r["max_length"]), _r(r["length_incr"]))
          for r in src.table(prefix + "lengths")}
    gr = {r["grade_uid"]: r["grade"] for r in src.table(prefix + "board_grades")}
    combos = [Combination(th[r["thickness_uid"]].dry, wd[r["width_uid"]].dry, ln[r["length_uid"]].name,
                          gr.get(r["grade_uid"], "All board grades"), bool(r["valid_combination"]), _r(r["unit_price"], 2))
              for r in src.table(prefix + "combinations")
              if r["thickness_uid"] in th and r["width_uid"] in wd and r["length_uid"] in ln]
    wane = {(th[r["thickness_uid"]].dry, wd[r["width_uid"]].dry):
            WaneRule(_r(r["thickness_wane_perc"]), _r(r["width_wane_perc"]), _r(r["length_wane"]), int(r["length_wane_type"]))
            for r in src.table(prefix + "wane") if r["thickness_uid"] in th and r["width_uid"] in wd}
    centre = {(th[r["thickness_uid"]].dry, wd[r["width_uid"]].dry) for r in src.table("centre_boards")
              if not prefix and r["thickness_uid"] in th and r["width_uid"] in wd}
    lgr = {r["grade_uid"]: r["grade"] for r in src.table(prefix + "log_grades")}
    outputs = {(th[r["thickness_uid"]].dry, wd[r["width_uid"]].dry, lgr[r["log_grade_uid"]], gr[r["board_grade_uid"]]):
               (float(r["zero_percent"]), float(r["fifty_percent"]), float(r["nine_nine_percent"]),
                float(r["one_hundred_percent"]))
               for r in src.table(prefix + "grade_outputs")
               if r["thickness_uid"] in th and r["width_uid"] in wd and r["log_grade_uid"] in lgr
               and r["board_grade_uid"] in gr}
    return Products(sorted(th.values(), key=lambda s: s.dry), sorted(wd.values(), key=lambda s: s.dry),
                    list(ln.values()), combos, list(gr.values()) or ["All board grades"], wane, centre, outputs)


def _lines(src: Source, prefix: str) -> list[ProductionLine]:
    out = []
    for r in sorted(src.table(prefix + "production_line"), key=lambda r: r["prod_line_no"]):
        two_p, two_s = r["no_of_primary_kerfs"] == 2, r["no_of_second_kerfs"] == 2
        out.append(ProductionLine(
            name=r["name"], saw_type=SawType(int(r["saw_type_uid"])),
            primary_kerf=_r(r["inside_primary_kerf"]),
            primary_outside_kerf=_r(r["outside_primary_kerf"]) if two_p else None,
            primary_outside_blades=int(r["primary_outside_blades"]) if two_p else 0,
            secondary_kerf=_r(r["inside_second_kerf"]),
            secondary_outside_kerf=_r(r["outside_second_kerf"]) if two_s else None,
            secondary_outside_blades=int(r["second_outside_blades"]) if two_s else 0,
            primary_resaw=bool(r["primary_resaw"]), primary_resaw_kerf=_r(r["primary_resaw_kerf"]),
            secondary_resaw=bool(r["second_resaw"]), secondary_resaw_kerf=_r(r["second_resaw_kerf"]),
            cant_guiding=CantGuiding(int(r["cant_guiding"])), max_sweep=float(r["max_sweep"]),
            log_rotation_deg=float(r["log_rotation_min"]), log_misalignment_mm=float(r["log_alignment_min"]),
            primary_offset_mm=float(r["primary_offset_min"]), cant_misalignment_mm=float(r["cant_alignment_min"]),
            secondary_offset_mm=float(r["second_offset_min"]),
            edging_objective=EdgingObjective(int(r["edging_objective"])),
            edger_blades=int(r["no_of_edging_blades"]), edger_kerf=_r(r["edger_kerf"]),
            second_board_width=str(r["second_board_width"]), max_boards_per_flitch=int(r["max_boards_per_length"]),
        ))
    return out


def _classes(src: Source, prefix: str) -> dict[int, LogClass]:
    out = {}
    for r in src.table(prefix + "log_classes"):
        no = int(str(r["log_class_no"]).strip())
        out[r["log_class_uid"]] = LogClass(
            no, _r(r["min_diameter"]), _r(r["max_diameter"]), _r(r["min_length"]), _r(r["max_length"]),
            _r(r["length_incr"]), _r(r["min_taper"]), _r(r["max_taper"]), _r(r["min_sweep"]), _r(r["max_sweep"]),
            _r(r["min_ovality"]), _r(r["max_ovality"]), float(r["min_defect_core"]), float(r["max_defect_core"]),
            _r(r["log_price"], 2))
    return out


def _log(r: dict, grade: str = "All log grades") -> Log:
    return Log(int(r["log_no"]), _r(r["diameter"]), _r(r["length"]), _r(r["taper"]), _r(r["sweep"]),
               _r(r["ovality"]), _r(r["defect_core"]), grade)


def _patterns(src: Source, prefix: str, classes: dict[int, LogClass], lines: list[ProductionLine]) -> list[PatternDef]:
    groups = {g["group_uid"]: g["production_line_uid"] for g in src.table(prefix + "saw_pattern_groups")}
    line_by_uid = {r["prod_line_uid"]: r["name"] for r in src.table(prefix + "production_line")}
    out = []
    for r in src.table(prefix + "saw_patterns"):
        line_name = line_by_uid.get(groups.get(r["group_uid"]), lines[0].name if lines else "")
        cls = classes.get(r["log_class_uid"])
        out.append(PatternDef(r["saw_pattern_uid"], line_name, cls.no if cls else 0, int(r["pattern_no"]),
                              r["primary"] or "", r["secondary"] or ""))
    return sorted(out, key=lambda p: (p.line_name, p.log_class_no, p.pattern_no))


def load_inputs(path) -> Dataset:
    src = path if isinstance(path, Source) else Source(path)
    grades = {r["grade_uid"]: r["grade"] for r in src.table("log_grades")}
    classes = _classes(src, "")
    lines = _lines(src, "")
    logs = [_log(r, grades.get(r.get("grade_uid"), "All log grades"))
            for r in sorted(src.table("logs"), key=lambda r: r["log_no"])]
    return Dataset(_products(src, ""), sorted(classes.values(), key=lambda c: c.no), logs, lines,
                   _patterns(src, "", classes, lines), _settings(src), src.path.stem)


def run_names(path) -> list[str]:
    src = path if isinstance(path, Source) else Source(path)
    return [r["run_name"] for r in src.table("runs")]


def load_run(path, name: str | None = None) -> Run:
    src = path if isinstance(path, Source) else Source(path)
    runs = src.table("runs")
    if not runs:
        raise ValueError("this dataset holds no batch run")
    if name is not None and name not in [r["run_name"] for r in runs]:
        raise ValueError(f"no batch run called {name!r}")
    name = name or runs[-1]["run_name"]
    classes = _classes(src, "run_")
    lines = _lines(src, "run_")
    products = _products(src, "run_")
    run_logs = {r["log_uid"]: r for r in src.table("run_logs")}
    logs = [_log(r) for r in sorted(run_logs.values(), key=lambda r: r["log_no"])]
    ds = Dataset(products, sorted(classes.values(), key=lambda c: c.no), logs, lines,
                 _patterns(src, "run_", classes, lines), _settings(src), f"{src.path.stem}:{name}")
    th = {r["thickness_uid"]: _r(r["dry_thickness"]) for r in src.table("run_thicknesses")}
    wd = {r["width_uid"]: _r(r["dry_width"]) for r in src.table("run_widths")}
    run = Run(name, ds, oneliner=src.table("oneliner_data"))
    for r in src.table("run_log_results"):
        run.log_results.append(ReferenceLog(
            r["saw_pattern_uid"], int(run_logs[r["log_uid"]]["log_no"]), int(r["no_of_boards_recov"]),
            r["dry_board_volume"], r["wet_board_volume"], r["board_value"], r["sawdust_volume"],
            r["chip_volume"], r["log_volume"]))
    for b in src.table("run_board_results"):
        run.board_results.append(ReferenceBoard(
            b["saw_pattern_uid"], int(run_logs[b["log_uid"]]["log_no"]), int(b["board_type"]), int(b["board_no"]),
            th[b["thickness_uid"]], wd[b["width_uid"]], _r(b["board_length"]), _r(b["board_left"]),
            _r(b["board_right"]), _r(b["board_bottom"]), _r(b["board_top"]), _r(b["board_front"]),
            _r(b["board_back"]), bool(b["resawn"]), _r(b["resaw_position"]), b["dry_volume"],
            b["wet_volume"], b["board_value"]))
    return run
