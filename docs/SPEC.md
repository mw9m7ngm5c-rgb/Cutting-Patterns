# Sawing pattern simulator and generator: specification

Status: Phase 4 (advanced sawing) complete; all four phases built. Results: Phase 1 section 13, Phase 2 section 14, Phase 3 section 15, Phase 4 section 16.
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
  loggen.py      log generator (seeded ranges and distributions)
  generator.py   pattern generator, diameter chart, class suggestions
app/         the web app; calls the engine, never the other way round
  models.py      SQLAlchemy tables (section 6)          db.py        connection, migrations on start
  store.py       database <-> engine, new / import / duplicate datasets
  tables.py      column definitions behind every editable table
  simview.py     pattern-screen diagram and class results
  runs.py        batch runs in a background thread      reports.py   reports and Excel export
  genjobs.py     generator searches as background jobs  svg.py       diagrams drawn on the server
  snapshot.py    a run's inputs as JSON                 main.py      routes; __main__.py start command
  templates/, static/ (grid.js, pattern.js, app.css), migrations/ (Alembic)
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

1. Apply log rotation about the z axis (from horns up; the discs become polygons), log misalignment (an x shift growing linearly along the log, the middle of the log on the saw line, A-53) and primary saw offset (constant x shift). All zero in the reference run.
2. Cant: x from −W/2 to +W/2, W the **wet** cant width.
3. Sideboards step outward on each side: kerf, then wet thickness, repeated. A final kerf separates the last sideboard from the slab.
4. Kerf is the inside-blade kerf except for the outermost n blades per side when two kerf sizes are set.
5. Live sawing (no cant in the primary string): the whole stack is centred on x = 0, every piece is a flitch (board type 3) and goes to the edger. No secondary pattern.
6. Chipper-profiler lines: a sideboard or cant board written `TxW` is profiled to width W on the log's centreline and never edged; only its length is chosen. Fixed widths need a chipper-profiler line.

### 4.4 Secondary breakdown

1. The cant is turned on its side. In log coordinates the cuts are horizontal planes (constant y).
2. Stack height = Σ wet thicknesses + kerf × (boards − 1), centred on y = 0.
3. Everything that moves or bends the secondary cuts is one shift of the cant frame per disc (`secondary_shift`), so edging and the wane test work the same on curved boards. Board positions are reported in this cant frame.
   - Secondary saw offset: constant shift up.
   - Cant misalignment: shift growing linearly along the log, the middle on the saw line (A-53).
   - Cant guiding (curve sawing): half taper follows the curve of the log's centreline; full taper follows the top face of the cant (centreline plus the growth in radius, centred at mid-length), so the taper falls on one side. Either follows at most `max_sweep` (mm/m) × length of the sweep; the rest is sawn straight (A-54).
   - Arris alignment (comma in the string): the stack moves so the blade at the comma sits on the arris, the height where the cant's sawn faces run out of wood; top arris if the blade is in the upper half of the stack, else the bottom one. Judged on the small end only or along the whole log (setting) (A-57).

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
4. Cross-cut option: if "max boards per flitch" is 2 or more, edge further boards from the length the first board left, longest first, until the limit or no board fits (A-59).
5. Three-blade edger: the first board is pushed to one end of its room and a second board, of the fixed second width or any valid width ("Best"), is placed exactly one edger kerf beside it. The pair is kept only if it beats the single board; full-width cant boards and boards inside the riving knives are never split (A-58).
6. Resaw: when no valid board can be made at the flitch's thickness, try each thinner valid thickness. The resawn board keeps the inner sawn face; the resaw cut sits one wet thickness out from it, and the resaw kerf is charged to sawdust. Confirmed positions in the run: a 25 mm flitch at y 74 to 101 became a 19 mm board with the resaw cut at y = 95.

Wane test (fitted to the reference run, ASSUMPTIONS A-07). At each corner of the board's cross-section, at every disc along the board:

    wane depth down the edge / allowed depth  +  wane width along the face / allowed width  <=  1

where allowed depth = `thickness_wane %` of the dry thickness and allowed width = half of `width_wane %` of the dry width. Wane may be present on at most `length_wane` of the board length. Because both terms grow as an edge moves outward, each disc allows one interval of board positions, and a board exists over a run of discs when those intervals overlap. The edger takes the longest such run for each candidate width.

### 4.7 Grades

If more than one board grade exists, each board's grade is drawn from the probability table for its thickness × width and log grade, using the share of the board's sawn cross-section inside the defect core, averaged along the board (four bands: 0 %, 1 to 50 %, 51 to 99 %, 100 %). The draw uses a generator seeded from the run's seed and the log number. The board is priced at its grade's combination (R0 if that grade is not a valid product) (A-60).

### 4.7b Real logs

With real-log variation on, every log is built as irregular polygons: smooth random irregular taper, out-of-roundness (2 to 5 lobes per round, drifting along the log), uneven ovality and crook, drawn from the seed and the log number so a log always has the same shape. The saw datum still runs through the end centres (A-55, A-56).

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
| `run`, `run_*` | A batch run copies every input it used into `run.snapshot` (one JSON document holding exactly the engine inputs: products, wane, classes, logs, lines, patterns, settings), then stores `run_pattern`, `run_log_result` and `run_board_result`. The run saws from its snapshot, not the live tables, and reports read only the run's own tables. Simsaw's separate `run_*` input tables are folded into the snapshot when a run is imported. |

Additions beyond Simsaw: `saw_pattern.source` (manual / imported / generated), `dataset.name` and notes, placeholder flags on product prices, log prices and line kerfs, labels for the primary and secondary machine, `run.source` (app or imported Simsaw results) and run status and progress. `generator_job` (Phase 3) holds each search: its form, a snapshot of the inputs, progress and the ranked results.

## 7. Generator

`engine/generator.py`, for a production line and a log class, or a single diameter (three ideal logs across the 1 cm step).

1. **Enumerate.** Every allowed cant width; 0 to N sideboards a side; every secondary stack of usable thicknesses (a thickness with at least one valid product) whose wet height plus kerfs fits the largest log in the class at its large end. With "fill the face" (always on) a stack is dropped if another of the thinnest boards would still fit on each side of it at the small end of the smallest log.
2. **Constrain while enumerating.** Symmetric only (default on: same sideboards both sides, secondary reads the same both ways); thicker boards towards the centre (default on); most sideboards a side (2); most blades on each saw; most different thicknesses (3); cant widths to try; products the pattern must yield (their thickness must appear); products never to cut (switched off for the search). The class searches for Ngomi build 2 000 to 13 000 candidates.
3. **Pre-screen** every candidate on straight, round, tapered logs at the smallest, median and largest small-end diameter of the class, with the median length and taper. Closed form: for each flitch and width the smallest log radius at which the board passes the wane test is found once; the clear length then runs from there to the large end. It follows the engine's rules for widths, centre boards, valid lengths and resaw. It discards clear losers; near the top its order is rough (ASSUMPTIONS A-46).
4. **Simulate** the best 120 (80 before Phase 4) with the full engine on a stratified sample of 12 logs of the class, then the best 10 on every log. A minimum share of the target product and "must yield" are checked on these real results.
5. **Rank** by dry volume recovery, nett value recovery or volume of a target product, less a token 0.01 points per saw blade so a blade that changes nothing never wins a tie. Show the top 10 with recovery, nett value, boards per log, average length, product mix, blades and a diagram of the class's middle log.
6. **Diameter chart.** The same search at each 1 cm step of a diameter range, on three ideal logs per step with the dataset's median taper, sweep, ovality and length. Then the best three patterns of every step are sawn at every other step, so each step scores every pattern that could carry a class across it.
7. **Suggest classes** from the chart, two ways: a set number of classes (exact: the split and patterns with the highest total score), or neighbouring steps grouped while one pattern stays within a tolerance of each step's best. Both show what each class gives up against the best pattern at every centimetre. "Use these as the log classes" replaces the classes and saves each class's pattern.
8. **Saw setting card.** One printable A4 page per pattern: diagram of the class's middle log, one row per blade on each saw (where it cuts, as wet distances from the centreline, and the board or cant that follows), kerfs, edger and resaw, and what to expect per log (boards, recovery, length, value, pieces per product) from sawing every log in the class.

Generated patterns are saved as ordinary `saw_pattern` rows (source "generated") and can be edited by hand. The engine takes a `map_fn` so the app can run simulations in parallel processes; the engine itself starts none.

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

### 13.3 What it refused (until Phase 4)

A dataset that asked for a Phase 4 feature stopped with a message naming it. Since Phase 4 all of them are built (section 16).

### 13.4 Command line

```
python cli.py validate --dataset "reference/ngomi 1.mdb" --run Test1
python cli.py simulate --dataset "reference/ngomi 1.mdb"
python cli.py simulate --dataset "reference/ngomi 1.mdb" --pattern "25/114/25" "2*19 3*38 3*19" --class 1 --mix --volumes
python cli.py simulate --dataset "reference/ngomi 1.mdb" --pattern "25/114/25" "2*19 3*38 3*19" --log 8 --boards
```

## 14. Phase 2 results

Web app on top of the Phase 1 engine. The engine gained a log generator (`engine/loggen.py`) and a plain-language pattern check (`check_pattern`); its sawing rules are unchanged. 188 tests pass (150 from Phase 1, 38 new).

### 14.1 Start it

```
python -m app                       opens http://127.0.0.1:8000 in the browser
python -m app import "reference/ngomi 1.mdb" --name "Ngomi"
```

The database is `data/cutting_patterns.db` (change with `--db` or `CP_DB`). Migrations run on every start.

### 14.2 Screens

| Screen | What works |
| --- | --- |
| Datasets | New (Ngomi defaults, placeholders flagged), open, rename and notes, save as (deep copy including runs), delete, import a Simsaw `.mdb` (inputs, generator, grade outputs, class grades and every batch run with Simsaw's own results). |
| Logs | Log classes table with accepted grades and live log count; logs table with class shown, add, delete, paste from Excel; log generator with three distributions per property, fixed or recorded seed, replace or add. |
| Products | Tabs for sizes and grades, products and prices, wane, centre boards, grade outputs, residue prices. Adding a size creates its products (on, R0, flagged placeholder), wane rule (owner default) and grade outputs. |
| Machines | Production lines; tabs for the line, primary, secondary, and edging/cross-cut/resaw. Phase 4 settings are shown and marked; the engine refuses non-zero values with a message. |
| Sawing patterns | Line and class pickers; pattern list with a ready / cannot-saw flag; notation typed directly with live checking; builder by clicking or dragging sizes onto the diagram (symmetric sideboards by default); SVG end view with small- and large-end outlines, kerfs and labelled boards; step through the class's logs; single-log results; whole-class run with product mix and per-log table. |
| Batch runs | Name, choose lines and classes, background run with live progress, cancel (partial results kept), delete. A pattern that cannot be sawn is reported in the run, not fatal. |
| Reports | One-liner, board report (one pattern or combined; lengths none / length classes / every length), summary volume balance. Print styles. Excel export with six sheets (one-liner, boards by pattern, boards combined, summary, per log, inputs). |
| Settings | Nominal diameter, length and taper options, disc separation, points per disc, ellipses or polygons, seed. |

Placeholder values (prices, log prices, kerfs) are flagged in the database, shown in italics in the tables and listed in a banner on every page until they are replaced.

### 14.3 Checks

- An imported Ngomi dataset hands the engine exactly the objects the `.mdb` loader does (logs, lines, settings, products, wane, classes, patterns), so app runs equal the Phase 1 CLI: 54.10 / 52.37 / 56.23 %, boards 248 / 217 / 265.
- The imported Simsaw run reproduces Simsaw's one-liner from its stored per-log and per-board results: 54.0 / 52.3 / 56.2 % dry, 61.6 / 59.8 / 64.0 % wet, nett R2 040.04 / R1 971.66 / R2 129.20.
- A run saws from its snapshot: changing prices after starting a run does not change its results (tested).
- The pattern-screen API reproduces the worked example (log 8 on `25/114/25`): cant −60 to 60, sideboard 63 to 90, the 38s at −76.5/−35.5, −32.5/8.5, 11.5/52.5, log volume 0.105927 m³.
- Every page renders; the grid validates before writing and writes nothing if any row is wrong; generated logs repeat with a fixed seed.
- Checked in a real browser (Chromium): builder clicks and drag-and-drop, paste of two Excel rows, save, batch run with progress, all three reports. No script errors.

Speed: the 106 logs of the Ngomi run take about 2.7 s as a batch run including database writes; a class of 36 logs on the pattern screen about 0.8 s.

### 14.4 Not tested here

- Importing an actual `.mdb` through the web page. `reference/` is not in this repository, so the tests import the JSON fixtures exported from `ngomi 1.mdb`. The upload goes through the same importer as the Phase 1 `.mdb` path (`access-parser`), which was run against the real file in Phase 1.
- The start command on macOS and Windows. It uses only portable pieces (uvicorn, SQLite, `webbrowser`), but it was run on Linux only.

## 15. Phase 3 results

The pattern generator, diameter chart, class suggestions and saw setting cards. 209 tests pass (21 new).

### 15.1 Against the patterns in the Ngomi dataset

Same logs, same machine, symmetric patterns with thicker boards towards the centre (the defaults):

| Class | Dataset's pattern (this engine) | Generator's best | Time (4 cores) |
| --- | --- | --- | --- |
| 1: 18–21.9 cm, 36 logs | `25/114/25` `2*19 3*38 3*19`: 54.10 % | `50/114/50` `2*19 3*38 2*19`: 54.14 % | 11 s |
| 2: 22–25.9 cm, 34 logs | `25/152/25` `19 25 38 50 38 25 19`: 56.23 % | `2*19/152/2*19` `2*19 25 2*50 25 2*19`: 56.86 % | 13 s |
| 3: 26–29.9 cm, 30 logs | none | `19 25/152/25 19` `2*19 25 3*50 25 2*19`: 59.29 % | 11 s |
| 4: 30–35.9 cm, 44 logs | none | `2*38/152/2*38` `2*19 38 3*50 38 2*19`: 58.87 % | 15 s |
| 5: 36–41.9 cm, 48 logs | none | `38 50/152/50 38` `2*19 38 4*50 38 2*19`: 55.17 % | 17 s |

The dataset's class 1 pattern is not symmetric, so the default search cannot produce it; with "symmetric only" off it is among the candidates. Through the app (three worker processes) a class search took about 20 s. A diameter chart of 18–41 cm (24 steps) took 95 s.

Five classes suggested from that chart: 18–20.9, 21–26.9, 27–28.9, 29–31.9 and 32–41.9 cm, giving up 0.1 to 1.3 recovery points per class against the best pattern at every centimetre.

The chart's bars zigzag between odd and even centimetres. That is the "odd number" nominal diameter setting (logs of 18.x and 19.x cm are both booked at 19 cm), not the patterns: within a step every pattern sees the same logs, so it changes neither the best pattern nor the suggested classes.

### 15.2 Screens

| Screen | What works |
| --- | --- |
| Generator: best patterns for a class | Line; a log class or one diameter; objective; target product and minimum share; sideboards, blades, thicknesses; cant widths; must yield / never cut; symmetric and thicker-to-centre switches; candidates to simulate. Runs in the background with progress and cancel. Top 10 with diagram, figures and product mix; save any of them as a pattern of any class, open it on the pattern screen, or print its setting card. |
| Generator: diameter chart | Range, objective and the same constraints. Bar chart of the best result per centimetre coloured by suggested class, the suggested classes (set number, or tolerance) with what each gives up, the best and runner-up pattern per centimetre, and "use these as the log classes". |
| Earlier searches | Every search is kept with its inputs and results; delete. Copied with the dataset on "save as". |
| Saw setting card | From the pattern screen, a generator result or `/d/{id}/card?pattern_id=`. Fits one A4 page (checked by printing to PDF for 2-blade-a-side and 6-blade patterns). |

### 15.3 Not done or not tested here

- Process pool on macOS and Windows: written for both (worker processes are started with "spawn", the default on those systems), run on Linux only.
- Ranking for nett value and for a target product is tested on small cases; the timings above are for dry volume recovery.
- The generator searches cant sawing only. Live sawing and chipper-profiler patterns arrive with Phase 4, as do curve sawing and real-log variation.

## 16. Phase 4 results

Curve sawing, rotation, misalignment and offsets, arris alignment, three-blade edger, cross-cutting into several boards, grades from the defect core, real-log variation, live sawing, chipper-profiler lines and scenario comparison. 231 tests pass (22 new; the Phase 1 tests that checked these features were refused now check that they work).

### 16.1 Against Simsaw

Unchanged: 54.10 / 52.37 / 56.23 % dry recovery against Simsaw's 54.00 / 52.29 / 56.23 %, identical board counts and board positions. Every new feature is a no-op at its default. The Ngomi line's three-blade edger ("Best") is now simulated and, like Simsaw in Test1, finds no second board in classes 1 and 2.

### 16.2 What changed for classes 3 to 5

In the larger classes, which Test1 does not cover, the three-blade edger does find second boards on wide sideboards: in class 4 (30–35.9 cm) 38 of the 248 edged flitches (on the generator's best pattern) give two boards. The generator's best results move accordingly (dry recovery, same logs, 4 cores):

| Class | Phase 3 best | Phase 4 best | Time |
| --- | --- | --- | --- |
| 1 | 54.14 % | 54.14 % `50/114/50` `2*19 3*38 2*19` | 9 s |
| 2 | 56.86 % | 56.86 % `2*19/152/2*19` `2*19 25 2*50 25 2*19` | 12 s |
| 3 | 59.29 % | 59.29 % `19 25/152/25 19` `2*19 25 3*50 25 2*19` | 13 s |
| 4 | 58.87 % | 61.05 % `2*38/152/2*38` `2*19 38 3*50 38 2*19` | 16 s |
| 5 | 55.17 % | 61.30 % `2*38/152/2*38` `2*19 38 4*50 38 2*19` | 18 s |

The generator's pre-screen now counts second boards too, and it simulates 120 candidates instead of 80 (A-46).

### 16.3 Examples

- Curve sawing on the Ngomi patterns (Line 1 against a copy with half-taper cant guiding, all three patterns): +1.55 recovery points overall (+0.9 to +2.2 per pattern) and +R62/m³ nett. On an extreme swept log (26 cm, 4.8 m, 120 mm sweep) half taper raises recovery from 23.5 % to 40.1 %.
- Three-blade edger on a 40 cm log with 50 mm sideboards: two 50 × 152 boards per sideboard instead of one, recovery 13.4 % → 24.1 % on that pattern.

### 16.4 Speed

A class of 44–48 logs on one pattern: 1.0–1.3 s for ideal logs, 1.5 s with curve sawing, 1.9 s with real-log variation or log rotation (polygons with 64 points per disc). The generator: 9–18 s per class on 4 cores.

### 16.5 Screens

| Screen | Change |
| --- | --- |
| Machines | Every setting is live. "Copy as a scenario" copies a line's settings without its patterns. |
| Settings | Arris judged on the small end or the whole log; real-log variation on or off with four sizes. |
| Sawing patterns | Live and chipper-profiler patterns; boards show grade, core share, second boards and profiled boards; a note says where the secondary cuts sit when they are shifted or curved. |
| Batch runs | Saw on another line's machine settings; "Compare two machine settings" runs the same patterns on two lines and opens the comparison. |
| Compare | Any two runs (including Simsaw's imported run) side by side per pattern, with the differences and the machine settings that differ. |
| Reports | Board report and Excel by grade when grades are in use; link to Compare. |
| Generator | Option to search on logs with real-log variation. |
| Saw setting card | Live sawing; notes for curve sawing, secondary offset and arris alignment. |

### 16.6 Not checked against Simsaw

No Simsaw run uses any Phase 4 feature, so each is tested against hand-worked cases only (`tests/test_phase4.py`). The rules that had to be chosen are A-53 to A-60. A Simsaw run of the course's Problem 3 scenarios would turn them into checked rules.
