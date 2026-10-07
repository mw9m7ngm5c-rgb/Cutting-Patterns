# Assumptions register

Every rule the engine will use that I had to infer rather than read. Each entry says what the rule is, where it came from and how sure I am.

Status key:

- **Confirmed**: reproduces the Test1 run exactly, checked by script.
- **Read**: stated in the help file or course notes.
- **Inferred**: consistent with the data, but the data cannot distinguish it from alternatives. Will be settled in Phase 1 by fitting against the 730 reference boards.
- **Open**: the reference material cannot settle it. Needs an answer from you or a second dataset.

Rule for Phase 1: where the documents are silent, the simplest rule that reproduces the reference results wins, and this file is updated to say which rule that was.

## A. Geometry and frame

| ID | Rule | Status | Evidence |
| --- | --- | --- | --- |
| A-01 | x across the primary saw, y vertical (up positive), z from the small end. Secondary string reads from −y to +y. | Confirmed | Stack positions computed from the pattern text match all 570 cant boards with zero error. |
| A-02 | Board type 0 = left sideboard, 1 = right sideboard, 2 = cant board. Board number counts outward from the cant (sideboards) or along the secondary string (cant boards). | Confirmed | Same check; 160 sideboards match. |
| A-03 | Horizontal diameter = D/√ovality, vertical = D×√ovality. | Read | Help: ovality is vertical ÷ horizontal and nominal diameter is the root of their product. |
| A-04 | Horns up means both ends high and the middle low. The saw datum (y = 0) runs through the centres of the two end discs. | Inferred | Boards at the bottom of the stack are recovered far more often than boards at the top (position 1: 33 of 36 logs; position 6: 3 of 36). Sideboard centres average −0.47 × sweep. A hand check on log 8 puts the first clear point of the top board at z ≈ 1.55 m under this datum, against a stored 1.6. The alternative datum (through the mid-length centre) is not yet excluded. |
| A-05 | Simsaw ran this dataset in "Analytical" mode (exact ellipses). I use polygons as specified in the brief. With 64 points the chord error is at most about 0.13 mm at these diameters. | Inferred | `misc_integers`: Discretised logs = 0, Points per disc = 64. If the polygon error costs accuracy on test 3, the polygon builder will place points so that chords at the saw lines are exact. |
| A-06 | Disc positions run from z = 0 to z = L at the disc separation. Board start and end positions snap to discs. | Inferred | Stored front/back values are rounded to 0.1 m, but lengths behave as if the true positions are on a 0.05 m grid: a stored span of 2.4 m often gives a 2.1 m board, which fits a true span of 2.35 m. |

## B. Wane, edging, cross-cut, resaw

| ID | Rule | Status | Evidence |
| --- | --- | --- | --- |
| A-07 | Wane test at each disc: at each edge of the board, wane may take at most `thickness_wane %` of the thickness, and on the waney face at most `width_wane %` of the width. Tested on wet sizes. | Inferred | Not documented anywhere in the reference set. One hand calculation (log 8, top 19×76) lands within one disc of the stored result. Whether width wane is per edge or the two edges combined, and whether percentages apply to wet or dry sizes, will be fitted. |
| A-08 | `length_wane` with type 0 is a percentage of board length on which wane may appear. 100 means wane is allowed along the whole board. | Open | Every rule in the dataset is 100 / type 0, so the data says nothing about other values. Type 1 is presumably an absolute length. Simsaw cannot be run to check the wane tab, so type 0 is implemented as a percentage and other types are rejected on import with a clear message. |
| A-09 | `edging_objective` 0 = volume. | Inferred | Course screenshots show "Volume" selected in "Edging for maximum" with otherwise matching settings; the help names volume and board length as choices. Other codes unknown. |
| A-10 | Edger placement across a symmetric flitch: Simsaw does not centre the board. Edged cant boards sit 0 to 7 mm to the +x side, never to the −x side. | Open | Probably a search that starts at one side and keeps the first best position. It does not change volume or count, so it does not affect acceptance test 3. I will centre the board unless you want Simsaw's positions reproduced. |
| A-11 | A cant board that passes the wane test at full cant width for part of its length is taken at full width and cross-cut, or edged narrower and kept longer, whichever gives more volume. | Inferred | Run contains both outcomes (for example 19×114 at 1.5 m and 19×102 at 2.1 m in the same stack position on different logs). |
| A-12 | Board length = clear span floored to the length increment; minimum length from the length class; no trim allowance at either end. | Confirmed | Full-length boards equal the log length (2.4, 2.7, 3.0 m). Shortest board is 0.9 m, the class minimum. |
| A-13 | Resaw happens only when no valid board can be made at the flitch's own thickness. Thinner valid thicknesses are then tried. The board keeps the inner sawn face. | Inferred | Help text, plus 11 resawn boards in the run: all 25 mm flitches cut to 19×76, resaw line exactly one wet thickness (21 mm) from the inner face. |
| A-14 | `edging_face` is 1 when the waney side of a resawn board faces +x or +y, otherwise 0. | Inferred | Holds for all 11 resawn boards; always 0 for boards that were not resawn. Stored for import fidelity only. |
| A-15 | Second board width "Best" means the second edger board may be any valid width for that thickness. | Open | No flitch in the run yielded two boards, so nothing to check against. |
| A-16 | Max boards per flitch = 0 means the cross-cut-and-re-edge option is off. | Inferred | No flitch in the run yielded two boards. |
| A-17 | Without riving knives every cant board may be edged. | Read | Help, riving knives page. |

## C. Volumes

| ID | Rule | Status | Evidence |
| --- | --- | --- | --- |
| A-18 | Nominal log volume = π/4 × (D + 0.5·L·taper)² × L. The printed formula omits "× L". | Confirmed | All 106 log volumes to 8e-9 m³. |
| A-19 | Nominal diameter setting 0 = odd: 2·floor(SED/2) + 1. | Confirmed | Same check. Codes for even and whole number are assumed to be 1 and 2. |
| A-20 | Nominal length = length floored to the nominal length increment (0.3 m). | Confirmed | Same check, though every log in the run is already a multiple of 0.3 m. |
| A-21 | Mass balance uses the **nominal** log volume. Chips are the remainder. | Confirmed | Closes to 1e-8 m³ on all 106 results. Side effect: on a log much smaller than its nominal class, chips could come out negative. I will report it as is and flag such logs. |
| A-22 | Sawdust = wood actually removed by every kerf (primary including the outer slab cut, secondary, edger, resaw), on the real log geometry, not scaled to nominal volume. | Inferred | Regressing stored sawdust on my estimates of each kerf component gives coefficients near 1 for primary and secondary kerfs with a residual of 0.5 %. The edger term fits at about 0.6 of full thickness × length × 2 kerfs, which suggests kerfs are only charged where they pass through wood. Exact rule to be fitted in Phase 1. |
| A-23 | Board value = dry volume × price. Nett value recovery = gross − log price (+ residue values, zero here). | Confirmed | 2160.04 − 120 = 2040.04, and likewise for the other two patterns. |
| A-24 | Average length in the one-liner is the mean board length, not volume-weighted. | Confirmed | 2.27 / 2.24 / 2.26 m against stored 2.3 / 2.2 / 2.3. |

## D. Units and import

| ID | Rule | Status | Evidence |
| --- | --- | --- | --- |
| A-25 | Log sweep is stored in mm total; class limits and the generator use mm/m. Conversion: mm ÷ length. | Confirmed | Generator limit 15 mm/m; largest stored sweep ÷ length is 15.0. |
| A-26 | Log defect core is stored in cm; class limits use % of SED. | Read | Column headings in the Logs screen. All cores are 0 in this dataset. |
| A-27 | `run_*` tables are a self-contained snapshot with their own keys. Thickness and width keys are renumbered in size order; logs are renumbered and carry `log_no`; only valid combinations are copied. | Confirmed | Decoding run boards with run keys gives sensible products; decoding with input keys does not. |
| A-28 | Distribution codes: 0 uniform, 2 normal with 95 % within limits, 1 normal with 65 % within limits. | Inferred | Code 2 fields have 2.5 % (taper) and 3.5 % (ovality) of logs outside the limits. Code 1 is by elimination. Sweep is clipped to its limits. |
| A-29 | Saw type codes: 0 cant/live, 1 cant/live grouped, 2 chipper-profiler, 3 chipper-profiler grouped. | Confirmed | `saw_types` table. |
| A-30 | Cant guiding codes: 0 none, 1 half taper, 2 full taper. | Inferred | 0 matches "none" in the run. The order of the other two is a guess: the help text lists "none, full taper, or half taper" but describes half taper first. Needs a dataset that uses curve sawing; Simsaw cannot be run to check the dropdown. |
| A-31 | I cannot reproduce Simsaw's log generator output for a given seed. The 200 Ngomi logs are imported as data; new logs come from this app's own generator and seed. | Open by nature | The random number generator inside Simsaw is not documented. |

## E. Not covered by the reference material

These features are in the brief but have no reference results to validate against. They will be built from the help text and tested on hand-computable cases only.

- Curve sawing (half and full taper) and the maximum-sweep limit.
- Rotation, misalignment and offsets.
- Arris alignment.
- Riving knives.
- Grades from defect core.
- Three-blade edger second board and cross-cut into two boards.
- Live sawing and chipper-profiler lines.
- Real-log variation.

A second Simsaw dataset with a run that uses some of these (the course's Problem 3 scenarios would do) would turn most of section E into testable rules.
