# Sawing pattern simulator and generator: specification

Status: Phase 1 (engine and command line) complete; awaiting sign-off before Phase 2. Phase 1 results are in section 13.
Companion document: `ASSUMPTIONS.md` (every rule here that was inferred rather than read is listed there with its evidence).

## 1. Purpose

A local web app for Thorpe Timbers (Ngome) that answers one question per log diameter class: **which cutting pattern should the mill run, and what recovery and product mix will it give?**

Two halves:

1. **Simulator.** Given logs, products, machine settings and a pattern, compute the boards recovered. Functionally equivalent to Simsaw 6 for the features listed in section 4.
2. **Generator.** Given a log class (or one diameter) and the valid product list, enumerate feasible cant-sawing patterns, simulate them and rank them. Simsaw has no equivalent.

Built from documented behaviour and the data files only. `simsaw.exe` and `SIMSAW.HLP` were not opened.

## 2. What the reference material contains

| File | What I found |
| --- | --- |
| `Simsaw help files.pdf` | 48 scanned pages (not 46). Read in full. Covers data files, log classes, logs, log generator, products, centre boards, grade outputs, residues, machine settings (primary, secondary, edging/X-cut/resaw), pattern notation, arris alignment, riving knives, single and batch simulation, reports, and the three Settings tabs. No page describes the wane tab, the summary report, chipper-profiler pattern building or grouped patterns in any detail. |
| `Simsaw_6_short_course_2026.doc` | 22 pages. Five problems plus two step-by-step appendices. Screenshots give default dry/wet sizes, typical machine settings, a Settings screen (disc separation 5 cm, 64 points per disc, type Analytical, interpolation Cubic splines, "Cant arris alignment uses small end only"), and the pattern screen with boards labelled. Lists twelve what-if scenarios (Problem 3) that become Phase 4 scenario tests. |
| `ngomi 1.mdb` | 39 user tables. Inputs plus batch run "Test1". Exported to `tests/fixtures/ngomi_1/` (one JSON file per table). |
| `simsaw.ini`, `simsawforms.ini` | Report options and window positions only. |
| `template.mdb`, `temp.jpg` | **Not in the folder.** See section 11. |

File names in the folder use spaces (`ngomi 1.mdb`, `Simsaw help files.pdf`), not underscores.

### 2.1 Facts confirmed from the Test1 run

All checked by script against the fixtures (`tools/check_sawlines.py`, `tools/explore_sawdust.py`).

- Nominal log volume formula reproduces all 106 `run_log_results.log_volume` values to 8e-9 m³.
- Mass balance (wet boards + sawdust + chips = log volume) closes to 1e-8 m³ on every log.
- Dry volume, wet volume and value formulas reproduce all 730 boards to 2e-9 m³.
- Saw-line positions derived from the pattern text alone reproduce the stored position of **all 730 boards with zero error**, and all 326 full-width cant boards sit exactly on the cant faces.
- Recomputed one-liner figures match the stored report: 54.00 / 52.29 / 56.23 % dry, 248 / 217 / 265 boards, 2.27 / 2.24 / 2.26 m average length, nett value = gross value − log price.

### 2.2 Things in the data that differ from the brief

- **13 of the 16 thickness × width combinations are valid, not all 16.** 25×114, 50×102 and 50×114 are switched off. This is why 25 mm sideboards in the run come out at 76, 102 or 152 and never 114.
- The class definitions hold 36 and 34 logs in the two classes that have patterns, so the run covers **70 logs**, and 8 of the 200 logs (17.0 to 17.9 cm) fall in no class.
- The edger is set to 3 blades with second board width **"Best"**, not a fixed width. No flitch in the run produced two boards, so the second-board logic never fired.
- "Max boards per flitch" is 0 and no flitch was cross-cut into two boards.
- The `run_*` snapshot tables **renumber their keys**: thicknesses and widths are re-keyed 1 to 4 in size order, logs are re-keyed 1 to 70 and matched to input logs by `log_no`, and only valid combinations are copied. The importer treats a run as self-contained and never joins `run_*` to input tables by uid.

## 3. Architecture

```
engine/      standalone package: no web, no database, no file I/O beyond explicit loaders
  model.py       dataclasses for every input and result
  model.py       dataclasses for every input and result, recovery and value sums
  notation.py    pattern parser and serialiser
  sections.py    cross-sections behind one interface: exact ellipses and polygons (numpy)
  log.py         ideal-log builder (discs along the length), log volume
  sawing.py      saw-line layout, primary and secondary breakdown, resaw, sawdust
  edging.py      edger, cross-cut, wane test
  generator.py   enumeration, pre-screen, ranking  (Phase 3)
app/         FastAPI routes, Jinja2 templates, static (vanilla JS, inline SVG), SQLAlchemy models, Alembic
importers/   Simsaw .mdb import (access-parser)
cli.py       simulate / generate commands; calls the engine only
tests/       unit tests + fixtures
docs/        SPEC.md, ASSUMPTIONS.md
reference/   read-only, not committed
```

Rules:

- `engine/` imports nothing from `app/` or `importers/`, and nothing from FastAPI or SQLAlchemy. A test enforces this by scanning imports.
- The engine works in **millimetres** for cross-section and **metres** for length. Unit conversion (cm diameters, mm total sweep, cm defect core, mm/m and % class limits) happens once, in `model.py` constructors and in the importer.
- One `numpy.random.Generator`, created from the run seed, is passed explicitly wherever randomness is needed. No module-level random state. (Phase 1 uses no randomness; grades in Phase 4 are the first user.)
- Python 3.11+, FastAPI, SQLite, `numpy`, `openpyxl`, `pytest`. One start command (`python -m app`), which runs migrations and opens the browser.

## 4. Simulation rules

### 4.1 Coordinate frame

Confirmed against the stored board coordinates.

- **x** horizontal, across the primary saw. The cant is centred on x = 0.
- **y** vertical, positive up. The secondary stack is centred on y = 0. The secondary string reads from negative y to positive y.
- **z** along the log from the small end (0) to the large end (length).
- Stored results use this same frame for every board, whichever saw cut it. A board record is a box: left/right (x), bottom/top (y), front/back (z).
- Board type 0 is a left sideboard, 1 a right sideboard, 2 a cant board. Board number counts outward from the cant for sideboards and along the secondary string for cant boards.

### 4.2 Log geometry

- Discs at a fixed separation along z (setting; 5 cm in this dataset, 10 cm Simsaw default).
- Each ideal disc is an ellipse. Nominal diameter D(z) = SED + taper × z. Horizontal diameter D/√ovality, vertical diameter D×√ovality.
- Sweep is a constant-radius arc in the y–z plane, horns up: both ends high, the middle low by the sweep amount. The saw datum (y = 0) runs through the centres of the two end discs.
- Defect core: same centreline and ovality, constant diameter (no taper).
- All sawing code asks the discs two questions through one interface: where does a horizontal line at height y enter and leave the wood, and the same for a vertical line at x. Two implementations answer: exact ellipses (Simsaw's "Analytical" type, which the Ngomi dataset uses) and closed polygons with a settable number of points (Simsaw's "Discretised" type, and the route for measured or perturbed discs). No sawing code knows which it has. See ASSUMPTIONS A-05 for why both exist.

### 4.3 Primary breakdown

1. Apply log rotation about the z axis, log misalignment (x shift growing linearly from small end to large end) and primary saw offset (constant x shift). All zero in the reference run; Phase 4 for non-zero values.
2. Cant: x from −W/2 to +W/2, W the **wet** cant width.
3. Sideboards step outward on each side: kerf, then wet thickness, repeated. A final kerf separates the last sideboard from the slab.
4. Kerf is the inside-blade kerf except for the outermost n blades per side when two kerf sizes are set.
5. Live sawing (no cant in the primary string): every piece is a flitch and goes to the edger. Phase 4.

### 4.4 Secondary breakdown

1. The cant is turned on its side. In log coordinates the cuts are horizontal planes (constant y).
2. Stack height = Σ wet thicknesses + kerf × (boards − 1), centred on y = 0 after applying secondary saw offset and cant misalignment.
3. Cant guiding: none (straight cuts, as in the reference run), half taper (cuts follow the centreline arc) or full taper (cuts follow the inside curve), each limited by maximum sweep: sweep beyond the limit is left over and sawn straight. Phase 4.
4. Arris alignment (comma in the string): the stack is shifted so that the marked blade gives the first full-length bark-free board on that side. A setting chooses whether this is judged on the small-end section only. Phase 4.

### 4.5 Which boards are edged

- A cant board whose full cant width passes the wane test for its thickness × cant-width product over a valid length is taken at full width with no edging.
- Otherwise, if it lies inside the riving knives it is cross-cut only (shortened until it passes).
- Otherwise it is a flitch and goes to the edger, as do all sideboards.
- With no riving knives in the pattern, every board may be edged.

### 4.6 Edger, cross-cut and resaw

For a flitch of fixed wet thickness:

1. Candidate products: valid combinations with that thickness, excluding centre-board-only sizes, and for cant flitches not wider than the cant.
2. For each candidate width, find the placement across the flitch and the z-range over which the board passes the wane test. Length = z-range floored to the length increment, and must reach the minimum length.
3. Pick by edging objective (volume in the reference run; length is the other documented choice).
4. Cross-cut option: if "max boards per flitch" allows, split the flitch along z and edge each part separately when that raises the objective.
5. Three-blade edger: after the first board is chosen, try a second board from the remaining offcut at the fixed second width (or the best valid width when set to "Best").
6. Resaw: when no valid board can be made at the flitch's thickness, try each thinner valid thickness. The resawn board keeps the inner sawn face; the resaw cut sits one wet thickness out from it, and the resaw kerf is charged to sawdust. Confirmed positions in the run: a 25 mm flitch at y 74 to 101 became a 19 mm board with the resaw cut at y = 95.

Wane test (fitted to the reference run, ASSUMPTIONS A-07). At each corner of the board's cross-section, at every disc along the board:

    wane depth down the edge / allowed depth  +  wane width along the face / allowed width  <=  1

where allowed depth = `thickness_wane %` of the dry thickness and allowed width = half of `width_wane %` of the dry width. Wane may be present on at most `length_wane` of the board length. Because both terms grow as an edge moves outward, each disc allows one interval of board positions, and a board exists over a run of discs when those intervals overlap. The edger takes the longest such run for each candidate width.

### 4.7 Grades

If more than one board grade exists, each board's grade is drawn from the probability table for its thickness × width and log grade, using the share of the board cross-section that lies inside the defect core (four bands: 0 %, 1 to 50 %, 51 to 99 %, 100 %). The draw uses the run's seeded generator. The reference run has one grade, so this is Phase 4.

### 4.8 Volumes and values

- Board dry volume = dry thickness × dry width × length. Wet volume uses wet sizes. Value = dry volume × product price.
- Nominal log volume = π/4 × (D + 0.5 × L × taper)² × L, with D, L and taper each either nominal or actual according to three settings.
  - Nominal diameter, odd option: 2 × floor(SED / 2) + 1 (cm). Even and whole-number options follow the same pattern.
  - Nominal length: floored to the nominal length increment.
  - Nominal taper: one setting (10 mm/m here).
- Sawdust = volume of wood actually removed by every saw kerf (primary, secondary, edger, resaw), measured on the log geometry.
- Chips = log volume − wet board volume − sawdust. Because log volume is nominal while sawdust is geometric, chips absorb the difference.
- Shrinkage = wet board volume − dry board volume.
- Recovery (dry) = Σ dry board volume ÷ Σ log volume. Gross value recovery = Σ board value ÷ Σ log volume. Nett value recovery = gross − log price + residue value per m³ of log (chips less fines at chip price, sawdust at sawdust price).

## 5. Pattern notation

Grammar (sizes are dry mm):

```
primary    := side? "/" cant "/" side?      cant sawing
            | side                           live sawing
secondary  := side
side       := item (" " | "," | "<" | ">")* ...
item       := [count "*"] thickness ["x" width]
```

- `n*t` is n adjacent boards of thickness t. The serialiser collapses runs of equal adjacent items back to `n*t`.
- `,` marks the arris blade between two items. `<` and `>` mark the riving knives.
- `25x76` is a chipper-profiler sideboard with a fixed width.
- The parser keeps the exact token sequence so that parse → serialise returns the input string for every pattern in the datasets and course notes (`25/114/25`, `2*25/114/2*25`, `2*19 3*38 3*19`, `25 3*38,25`, `25 <3*38> 25`, `25x76 3*38 25x76`, `3*25 2*38 3*25`).
- Validation: every thickness and cant width must exist in the dataset; a pattern that refers to a size that has since been removed is shown as invalid, not silently dropped.

## 6. Data model

SQLite tables mirror the Simsaw schema so that datasets import without loss. A `dataset` row replaces the one-file-per-dataset model; every table below carries `dataset_id`.

| Entity | Key fields |
| --- | --- |
| `log_grade`, `board_grade` | Separate tables. Board grades carry the knot-ratio limit columns present in Simsaw. |
| `log_class` | min/max diameter (cm), length (m) + increment, taper (mm/m), sweep (mm/m), ovality, defect core (%), log price (R/m³), allowed log grades, parent class (for grouped patterns, stored but unused). |
| `log` | SED (cm), length (m), taper (mm/m), sweep (**mm total**), ovality, defect core (**cm**), grade. Class membership is derived, comparing sweep ÷ length and core ÷ SED against class limits. |
| `log_generator` | ranges, distribution code per property, count, seed, real-log variation fields. |
| `thickness`, `width` | dry and wet size (mm). |
| `length_class` | min, max, increment (m), description. |
| `combination` | thickness × width × length class × board grade, `valid`, price (R/m³). |
| `wane_rule` | per thickness × width: thickness wane %, width wane %, length wane, length wane type. |
| `centre_board` | thickness × width. |
| `grade_output` | per thickness × width × log grade × board grade: four probabilities. |
| `production_line` | every field of Simsaw's `production_line`, including min/max/increment triplets for rotation, alignment and offsets. |
| `saw_pattern` | line, log class, pattern number, primary, secondary, source (manual / generated). |
| `setting` | nominal options, disc separation, points per disc, seed, residue prices, % fines. |
| `run`, `run_*` | A batch run copies every input it used into `run_*` tables, then stores `run_log_result` and `run_board_result`. Reports read only `run_*`. |

Additions beyond Simsaw: `saw_pattern.source`, generator job tables (constraints, candidates, scores), and `dataset.name`.

## 7. Generator

For a production line and a log class, or a single diameter.

1. **Enumerate.** For each valid cant width: for 0..N sideboards per side from the valid thicknesses; for each secondary stack of valid thicknesses whose wet height plus kerfs fits the available cant face at the class's diameters. Symmetric-only (default) roughly square-roots the search space.
2. **Constrain.** Maximum blades per saw, maximum distinct thicknesses, must-include and exclude products, minimum share of a target product, centre boards only at full cant width.
3. **Pre-screen.** Score each candidate on a straight, untapered cylinder at three diameters in the class (minimum, middle, maximum) using a closed-form chord calculation. Keep the best few hundred.
4. **Simulate.** Run the full engine on the class's logs for the survivors.
5. **Rank.** By dry volume recovery, nett value recovery or volume of a target product. Show the top 10 with recovery, value, boards per log, product mix and diagram.
6. **Diameter chart.** Repeat at each 1 cm step across the diameter range, show the best pattern per step, and suggest class boundaries where the best pattern changes.
7. **Saw setting card.** One printable page per pattern: diagram, blade positions as cumulative wet distances from the centreline, kerfs, expected boards per log, expected recovery.

Generated patterns are saved as ordinary `saw_pattern` rows and can be edited by hand.

## 8. Screens

Original layout and wording; Simsaw's workflow order.

1. **Datasets.** New, open, duplicate, import from `.mdb`.
2. **Log definitions.** Class table; logs table with add, paste from Excel, delete; log generator with three distributions and a fixed-seed option.
3. **Product definitions.** Tabs: dimensions and prices, wane rules, centre boards, grade outputs, residues.
4. **Machine settings.** Lines table; tabs for primary, secondary, edging/cross-cut/resaw.
5. **Sawing patterns.** Line and class pickers; pattern list; SVG diagram (small-end and large-end outlines, saw lines, recovered boards labelled `38x114x2.4m`); build by dragging sizes onto the diagram or typing notation; step through logs; run one log or the class; results beside the diagram.
6. **Pattern generator.** Section 7.
7. **Batch simulation.** Named runs, progress, cancel.
8. **Reports.** One-liner, board report (by pattern or combined; lengths none / classified / detailed), summary. Print styles and Excel export.

UI terms: small-end diameter, wet and dry sizes, cant, sideboard, kerf, wane. Currency in Rand.

## 9. Validation plan

Fixtures: `tests/fixtures/ngomi_1/*.json`, exported by `importers/export_fixtures.py`.

| # | Test | Tolerance | Status after Phase 1 |
| --- | --- | --- | --- |
| 1 | Nominal log volume vs `run_log_results.log_volume` | 1e-5 m³ | Pass: all 106 to 8e-9 |
| 2 | Saw lines and full-width cant boards vs stored coordinates | 0.1 mm | Pass: all 730 boards on our saw lines; 325 of Simsaw's 326 full-width boards reproduced |
| 3 | Per-pattern dry recovery and board count | 1.0 pp, 5 % | Pass: within 0.10 pp, board counts exact |
| 4 | Per-log mass balance | 1e-6 m³ | Pass |
| 5 | Notation round-trip | exact | Pass: every pattern in both datasets, the help pages and the course notes |

If test 3 fails I stop and show a per-log, per-board comparison for the five worst logs.

Further engine tests, one per rule in section 4, on hand-computable cases: a cylinder with a known chord, a tapered log with a known first clear length, a flitch that must be resawn, a board that is exactly on a length increment.

## 10. Phases

As in the brief: 0 plan (this document), 1 engine and CLI with the acceptance tests, 2 app, 3 generator, 4 advanced. I stop at the end of each and wait.

## 11. Missing inputs

- `template.mdb`: received and exported to `tests/fixtures/template/`. It holds Simsaw's defaults: thicknesses 25/38/50/76, widths 76/114/152/228, one line with 5 mm kerfs and a two-blade edger, one pattern `25/76/25` + `5*25`, R800/m³, and no wane rows.
- `temp.jpg`: still missing. The course notes contain a similar screenshot (page 21), which is enough to design the diagram.

## 12. Decisions from the owner (7 October 2026)

| Topic | Decision |
| --- | --- |
| Primary and secondary machines | Not fixed. Each production line has a selectable machine type for the primary saw (frame saw, band saw, circular saw, chipper canter) and the secondary saw (frame saw, circular gang rip, band saw). The type is a label plus a set of default kerfs; the simulation itself is driven by the kerf, guiding and saw-type fields. |
| Kerfs | Selectable per line. Default 3 mm primary and secondary (Ngomi values), marked as placeholder until measured. |
| Curve sawing | Owner not sure what the secondary saw can do. Default "none" (straight), selectable per line. Half and full taper arrive in Phase 4. |
| Edger blades and resaw | Selectable per line, Ngomi values as defaults (3 blades, 5 mm edger kerf, resaws on both saws at 5 mm). |
| Products and prices | Owner enters prices in the app. Datasets start with the 13 valid Ngomi sizes at the R4 000/m³ placeholder, clearly marked. |
| Log intake | Owner will supply diameter range, lengths and log price. Until then the Ngomi classes and R120/m³ placeholder. |
| Default wane | No wane on structural thicknesses (38 and 50 mm). 10 % thickness and 30 % width on 19 and 25 mm. Editable per product. The acceptance tests keep using the wane rules stored in the Test1 run. |
| Default generator objective | Dry volume recovery. Switchable on each run. |
| Code home | GitHub repository, one commit per phase. |
| `template.mdb` | Added by the owner and imported. |
| Simsaw screenshots | Not available (Simsaw cannot be run). ASSUMPTIONS A-08, A-09, A-15 and A-30 stay fitted or assumed. |

## 13. Phase 1 results

Engine and command line only; no web app yet. 150 tests pass.

### 13.1 Against Simsaw's Test1 run

| Pattern | Logs | Dry recovery, ours | Simsaw | Boards, ours | Simsaw | Identical boards |
| --- | --- | --- | --- | --- | --- | --- |
| `25/114/25` + `2*19 3*38 3*19` | 36 | 54.10 % | 54.00 % | 248 | 248 | 242 |
| `19/152/19` + `2*19 25 50 25 2*19` | 36 | 52.37 % | 52.29 % | 217 | 217 | 212 |
| `25/152/25` + `19 25 38 50 38 25 19` | 34 | 56.23 % | 56.23 % | 265 | 265 | 265 |

"Identical" means same position in the pattern, same thickness and width, same length. The 11 boards that differ are each one disc (5 cm) either side of a 0.3 m length step. All 11 of Simsaw's resawn boards are reproduced. Sawdust totals are 5 to 7 % above Simsaw's (ASSUMPTIONS A-23); chips absorb the difference, recovery is unaffected.

Speed: 50 logs on one pattern in about 0.4 s (target 2 s).

### 13.2 What the engine does

- Pattern notation: parse, validate, serialise.
- Ideal logs: taper, ovality, horns-up sweep, defect core outline; exact or polygon discs.
- Cant sawing with straight secondary cuts, one or two kerf sizes per saw.
- Edging to the best valid width by volume, length or value; cross-cut to length steps; minimum length; wane rules per product; invalid combinations; centre boards; riving knives.
- Resaw on the primary and secondary lines.
- Volumes, values, mass balance, recoveries, product mix.
- Simsaw import from `.mdb` or JSON fixtures: current inputs or a batch run's snapshot with Simsaw's results.

### 13.3 What it refuses for now

A dataset that asks for any Phase 4 feature (curve sawing, arris alignment, rotation, misalignment, offsets, live sawing, chipper-profiler sideboards) stops with a message naming the feature. It is never silently ignored.

### 13.4 Command line

```
python cli.py validate --dataset "reference/ngomi 1.mdb" --run Test1
python cli.py simulate --dataset "reference/ngomi 1.mdb"
python cli.py simulate --dataset "reference/ngomi 1.mdb" --pattern "25/114/25" "2*19 3*38 3*19" --class 1 --mix --volumes
python cli.py simulate --dataset "reference/ngomi 1.mdb" --pattern "25/114/25" "2*19 3*38 3*19" --log 8 --boards
```
