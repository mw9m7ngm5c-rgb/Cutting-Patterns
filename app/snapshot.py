"""A batch run's inputs as JSON, and back.

The snapshot holds exactly what the engine was given (products, classes, logs, lines, patterns,
settings), so a run can be reloaded and re-sawn after the dataset has changed.
"""
from __future__ import annotations

import dataclasses
import json

from engine.model import (CantGuiding, Combination, EdgingObjective, LengthClass, Log, LogClass,
                          NominalDiameter, Products, ProductionLine, SawType, Settings, Size, Variation, WaneRule)
from importers.simsaw import Dataset, PatternDef

VERSION = 1


def to_dict(ds: Dataset) -> dict:
    p = ds.products
    return {
        "version": VERSION,
        "name": ds.name,
        "products": {
            "thicknesses": [dataclasses.asdict(s) for s in p.thicknesses],
            "widths": [dataclasses.asdict(s) for s in p.widths],
            "length_classes": [dataclasses.asdict(c) for c in p.length_classes],
            "combinations": [dataclasses.asdict(c) for c in p.combinations],
            "board_grades": list(p.board_grades),
            "wane": [{"thickness": t, "width": w, **dataclasses.asdict(r)} for (t, w), r in sorted(p.wane.items())],
            "centre_boards": [list(k) for k in sorted(p.centre_boards)],
            "grade_outputs": [[t, w, lg, bg, *v] for (t, w, lg, bg), v in sorted(p.grade_outputs.items())],
        },
        "log_classes": [{**dataclasses.asdict(c), "grades": list(c.grades)} for c in ds.log_classes],
        "logs": [dataclasses.asdict(g) for g in ds.logs],
        "lines": [{k: (int(v) if isinstance(v, (SawType, CantGuiding, EdgingObjective)) else v)
                   for k, v in dataclasses.asdict(ln).items()} for ln in ds.lines],
        "patterns": [dataclasses.asdict(pd) for pd in ds.patterns],
        "settings": {k: (int(v) if isinstance(v, NominalDiameter) else v)
                     for k, v in dataclasses.asdict(ds.settings).items()},   # variation becomes a dict or None
    }


def from_dict(d: dict) -> Dataset:
    p = d["products"]
    products = Products(
        [Size(**s) for s in p["thicknesses"]],
        [Size(**s) for s in p["widths"]],
        [LengthClass(**c) for c in p["length_classes"]],
        [Combination(**c) for c in p["combinations"]],
        list(p["board_grades"]),
        {(r["thickness"], r["width"]): WaneRule(r["thickness_pct"], r["width_pct"], r["length_wane"], r["length_wane_type"])
         for r in p["wane"]},
        {(t, w) for t, w in p["centre_boards"]},
        {(r[0], r[1], r[2], r[3]): tuple(r[4:8]) for r in p.get("grade_outputs", [])},
    )
    classes = [LogClass(**{**c, "grades": tuple(c["grades"])}) for c in d["log_classes"]]
    logs = [Log(**g) for g in d["logs"]]
    lines = []
    for ln in d["lines"]:
        ln = dict(ln)
        ln["saw_type"] = SawType(ln["saw_type"])
        ln["cant_guiding"] = CantGuiding(ln["cant_guiding"])
        ln["edging_objective"] = EdgingObjective(ln["edging_objective"])
        lines.append(ProductionLine(**ln))
    settings = dict(d["settings"])
    settings["nominal_diameter"] = NominalDiameter(settings["nominal_diameter"])
    if settings.get("variation"):
        settings["variation"] = Variation(**settings["variation"])
    return Dataset(products, classes, logs, lines, [PatternDef(**pd) for pd in d["patterns"]],
                   Settings(**settings), d.get("name", ""))


def dumps(ds: Dataset) -> str:
    return json.dumps(to_dict(ds), separators=(",", ":"))


def loads(text: str) -> Dataset:
    return from_dict(json.loads(text))
