# Assumptions register

Every rule the engine uses that I had to infer rather than read. Each entry says what the rule is, where it came from and how sure I am. Updated at the end of Phase 4 (section I is new; section F is now built).

Status key:

- **Confirmed**: reproduces the Test1 run exactly, checked by a test.
- **Read**: stated in the help file or course notes.
- **Fitted**: not documented; chosen because it reproduces the Test1 run best. The evidence is given. A different dataset could move it.
- **Open**: the reference material cannot settle it.
- **Ours**: a choice made for this app where Simsaw's behaviour is unknown or not worth copying.

Where Phase 1 landed against the run: 719 of 730 boards have the same product and length as Simsaw, board counts are exact for all three patterns, and dry recovery is within 0.10 points (54.10 / 52.37 / 56.23 against 54.00 / 52.29 / 56.23). The 11 boards that differ are all one disc (5 cm) either side of a length step.

## A. Geometry and frame

| ID | Rule | Status | Evidence |
| --- | --- | --- | --- |
| A-01 | x across the primary saw, y vertical (up positive), z from the small end. The secondary string reads from −y to +y. | Confirmed | Stack positions computed from the pattern text match all 570 stored cant boards with zero error (`test_2_saw_line_positions_match_every_stored_board`). |
| A-02 | Board type 0 = left sideboard, 1 = right sideboard, 2 = cant board. Board number counts outward from the cant (sideboards) or along the secondary string (cant boards). | Confirmed | Same test; 160 sideboards match. Numbering of a second sideboard on one side is assumed (the run has one per side). |
| A-03 | Horizontal diameter = D/√ovality, vertical = D×√ovality. | Read | Help: ovality is vertical ÷ horizontal and nominal diameter is the root of their product. |
| A-04 | Horns up means both ends high and the middle low. The saw datum (y = 0) runs through the centres of the two end discs. | Fitted | With this datum the engine reproduces 98.5 % of boards, including which end of the log every short top or bottom board comes from, and typical sideboard positions to within a few tenths of a millimetre. |
| A-05 | Discs are held behind one interface with two implementations: exact ellipses (Simsaw's "Analytical" type, used when the dataset says so, as Ngomi does) and closed polygons (Simsaw's "Discretised" type, and the route for real or perturbed logs). Sawing code cannot tell them apart. | Ours | The brief asked for polygons only. Simsaw ran this dataset analytically, and matching it to a disc needs chords better than a 64-point polygon gives (0.13 mm low). A test shows both give the same boards (`test_results_do_not_depend_on_how_discs_are_stored`). |
| A-06 | Discs run from z = 0 at the disc separation and always include the large end. A board's clear span starts and ends on discs. | Fitted | Stored front/back values are rounded to 0.1 m; lengths only make sense on a 0.05 m grid (a stored 2.4 m span often gives a 2.1 m board). |

## B. Wane, edging, cross-cut, resaw

| ID | Rule | Status | Evidence |
| --- | --- | --- | --- |
| A-07 | **Wane test.** At each corner of the board's cross-section, at every disc: (wane depth down the edge ÷ allowed depth) + (wane width in along the face ÷ allowed width) ≤ 1. Allowed depth = thickness wane % of the **dry** thickness. Allowed width = **half** the width wane % of the **dry** width (the percentage is shared between the two edges). | Fitted | Not documented anywhere. Measured directly from where Simsaw put each board (`tools/wane_evidence.py`): it never accepts wane deeper than about 75 % of the thickness allowance, which rules out "depth ≤ 10 % and width ≤ 30 % separately" (that reading gives 582 identical boards and +1.3 points of recovery). The combined form gives 719 of 730; the table from `tools/wane_fit.py` shows the peak at dry sizes and a half share. Other thresholds, thicknesses of allowance or products with different percentages are untested because every rule in the dataset is 10 / 30 / 100. |
| A-08 | `length_wane` type 0 is the share of the board length on which wane may appear. 100 means anywhere. 0 means no wane at all. Values in between are applied by trimming the board from its waney end (an approximation). Other types are not implemented. | Open | Every rule in the dataset is 100 / type 0. Simsaw cannot be run to read the wane tab. |
| A-09 | `edging_objective` 0 = volume. Length (longest board first) is implemented as code 1. A value objective (price × volume) is ours, code 2. | Fitted | Volume reproduces the run. The other codes are assumed. |
| A-10 | **Placement.** Simsaw pushes an edged board to the +x / +y end of its allowed range. This app centres it by default. | Ours | With `Rules(placement="high")` our edged-board positions differ from Simsaw's by a median of 0.2 mm (sideboards) and 0.5 mm (cant boards). The largest differences, up to 4.6 mm, are boards that could be cut wane-free: there Simsaw seems to stop at the last wane-free position, which the engine does not copy. Centring gives the same boards and volumes and looks right on the saw card. |
| A-11 | A cant board is taken at full cant width or edged narrower, whichever scores higher on the edging objective; equal scores go to the wider board. | Fitted | Wider-on-tie gives 719 identical boards, narrower-on-tie 714. |
| A-12 | Board length = clear span floored to the length increment; minimum length from the length class; no trim allowance at either end. | Confirmed | Full-length boards equal the log length; shortest board is 0.9 m, the class minimum. |
| A-13 | Resaw only when no valid board can be made at the flitch's own thickness. Every thinner valid thickness is then tried and the best by the edging objective kept. The board keeps the inner sawn face. | Confirmed for the run | All 11 resawn boards in the run are reproduced: same log, position, product and resaw line (`test_3_resawn_boards_match_simsaw`). "Best of the thinner thicknesses" is assumed; the run only ever had one thinner option. |
| A-14 | Simsaw's `edging_face` flag is 1 when the waney side of a resawn board faces +x or +y. | Fitted | Holds for all 11. Not used by the engine. |
| A-15 | Second board width "Best" means the second edger board may be any valid width; a number means that dry width only. | Open | No flitch in the run yielded two boards; our engine finds none there either (classes 1 and 2), but does in classes 3 to 5. See A-58. |
| A-16 | Max boards per flitch 0 or 1 means the cross-cut-and-re-edge option is off. | Fitted | No flitch in the run yielded two boards. See A-59. |
| A-17 | Without riving knives every cant board may be edged. Inside the knives a board is full cant width or nothing, shortened by cross-cutting. | Read | Help, riving knives page. Tested on a cylinder only. |
| A-18 | Centre-board products are never cut at the edger; they are allowed only at full cant width. | Read | Help, centre boards page. Tested on a cylinder only. |

## C. Volumes

| ID | Rule | Status | Evidence |
| --- | --- | --- | --- |
| A-19 | Nominal log volume = π/4 × (D + 0.5·L·taper)² × L. The printed formula omits "× L". | Confirmed | All 106 stored log volumes to 8e-9 m³. |
| A-20 | Nominal diameter setting 0 = odd: 2·floor(SED/2) + 1. Even and whole number are codes 1 and 2. | Confirmed (odd); assumed (codes 1, 2) | Same test. |
| A-21 | Nominal length = length floored to the nominal length increment. | Confirmed | Same test, though every log in the run is already a multiple of 0.3 m. |
| A-22 | Mass balance uses the **nominal** log volume. Chips are the remainder. | Confirmed | Closes to 1e-8 m³ on all 106 stored results. A log well below its nominal class could show negative chips; the engine reports it as is. |
| A-23 | **Sawdust** = wood removed by every kerf, measured on the log: primary and secondary kerfs (including the slab cut and the cuts outside the outermost cant boards) along the whole log; two edger kerfs per edged board along its clear span; the resaw kerf along the resawn flitch. | Fitted, approximate | Total sawdust comes out 5 to 7 % above Simsaw's (about 0.7 % of log volume moves from chips to sawdust). A regression (`tools/sawdust_evidence.py`) puts primary and secondary kerfs at 0.9 to 1.0 of ours and suggests Simsaw charges edged cant boards roughly one kerf, not two. I have not adopted that without knowing why. Recovery is not affected. |
| A-24 | Board value = dry volume × price. Nett value recovery = gross − log price + residue value (chips less fines, and sawdust, at their prices). | Confirmed (first two); read (residues) | 2160.04 − 120 = 2040.04. Residue prices are zero in the run. |
| A-25 | Average length in the one-liner is the plain mean of board lengths. | Confirmed | 2.3 / 2.2 / 2.3 m as stored. |

## D. Units and import

| ID | Rule | Status | Evidence |
| --- | --- | --- | --- |
| A-26 | Log sweep is stored in mm total; class limits and the generator use mm/m. | Confirmed | Generator limit 15 mm/m; largest stored sweep ÷ length is 15.0. Class membership computed this way gives Simsaw's 36 / 34 / 30 / 44 / 48 logs per class. |
| A-27 | Log defect core is stored in cm; class limits use % of SED. | Read | Column headings in the Logs screen. All cores are 0 here. |
| A-28 | `run_*` tables are a self-contained snapshot with their own keys: thickness and width keys renumbered in size order, logs renumbered and carrying `log_no`, only valid combinations copied. | Confirmed | Decoded this way, every stored board volume equals dry thickness × dry width × length. |
| A-29 | Access stores single-precision numbers (21.4 arrives as 21.399999618). The importer rounds to four decimals. | Confirmed | Needed for the nominal diameter class and length steps to come out right. |
| A-30 | Distribution codes: 0 uniform, 2 normal with 95 % within limits, 1 normal with 65 % within limits. | Fitted | Code 2 fields have 2.5 % (taper) and 3.5 % (ovality) of logs outside the limits. Code 1 is by elimination. |
| A-31 | Saw type codes: 0 cant/live, 1 cant/live grouped, 2 chipper-profiler, 3 chipper-profiler grouped. | Confirmed | `saw_types` table. |
| A-32 | Cant guiding codes: 0 none, 1 half taper, 2 full taper. | Open | 0 matches the run. The order of the other two is a guess; what each does is A-54. |
| A-33 | Simsaw's log generator cannot be reproduced seed for seed. The 200 Ngomi logs are imported as data. | Open by nature | Its random number generator is not documented. |
| A-34 | The template dataset has no wane rows. A product with no wane rule is cut with no wane allowed. | Ours | New datasets in the app start from the owner's defaults instead (A-40). |

## E. Built in Phase 1 but checked on simple shapes only

No reference results exist for these, so they are tested on cylinders and plain tapered logs where the answer can be worked out by hand:

- Riving knives, centre boards, two kerf sizes, length objective, value objective, length wane below 100 %.

## F. Built in Phase 4

Everything this section listed at the end of Phase 1 is now simulated: curve sawing and the maximum-sweep limit; log rotation, log and cant misalignment, primary and secondary saw offsets; arris alignment; grades from the defect core; the three-blade edger and cross-cutting a flitch into several boards; live sawing and chipper-profiler boards; real-log variation. No Simsaw run uses any of them, so the rules below (section I) are checked against hand-worked cases only. A second Simsaw dataset with a run that uses them (the course's Problem 3 scenarios would do) would turn them into checked rules.

## G. Phase 2: app and log generator

| ID | Rule | Status | Evidence |
| --- | --- | --- | --- |
| A-35 | Log generator: a normal distribution is centred between the limits with a standard deviation that puts 95 % (or 65 %) of draws inside them (half-range ÷ 1.960, or ÷ 0.935). Draws are **not** clipped to the limits, only kept physically possible (diameter and ovality above zero; taper, sweep and core not negative). | Fitted | Simsaw's Ngomi logs fall outside their normal limits about as often as this predicts (A-30). A test confirms 95.0 % and 65.0 % inside on 200 000 draws. |
| A-36 | Generated lengths fall on the length step between the limits: uniform picks a step at random; normal draws are rounded to the nearest step and clipped to the range. Diameter is rounded to 0.1 cm, taper to 0.1 mm/m, ovality to 0.01. Sweep is drawn in mm/m and stored as total mm (× length); defect core is drawn in % of SED and stored in cm. | Ours | Simsaw's generated Ngomi logs use 0.1 cm and 0.01 steps and lengths on the 0.3 m grid. The unit conversions follow A-26 and A-27. |
| A-37 | With "use this seed" off, the app draws a fresh seed and records it in the generator settings, so the batch can be repeated. | Ours | Keeps every draw on one seeded generator, as the brief requires. |
| A-38 | A log class with no grades ticked accepts every log grade. | Ours | Simsaw's table always lists at least one grade; an empty list should not silently exclude every log. |
| A-39 | A size added in the app gets a product for every length class and board grade, switched on, priced R0 and flagged as a placeholder. | Ours | No price may be invented (brief section 11). R0 is obviously wrong in the reports, and the placeholder banner names it until it is replaced. |
| A-40 | Default wane for a new size or dataset: no wane on thicknesses of 38 mm and up (0 % / 0 % / 0 %); 10 % thickness, 30 % width over 100 % of the length on thinner boards. | Read (owner, 7 Oct 2026) | Owner decision, SPEC section 12. Imported datasets keep their own wane rules. |
| A-41 | A run's snapshot is one JSON document holding exactly what the engine is given, instead of Simsaw's set of `run_*` tables. | Ours | Equivalent for reports and re-runs, much simpler; tested to round-trip every input exactly. |
| A-42 | Board report "length classes" groups boards by the dataset's named length classes; a board fitting more than one goes to the first, by shortest minimum. | Assumed | Simsaw's report options (simsaw.ini) list none / classified / detailed lengths without saying how "classified" groups. The Ngomi dataset has one length class, so the choice cannot be checked. |
| A-43 | Combined one-liner and summary figures are volume-weighted: totals of volumes and values over the total log volume; the combined nett value weights each pattern's nett value by its log volume. | Ours | Gives the same answer as sawing all the logs as one batch. |
| A-44 | Editing a placeholder (price, log price or any kerf on a line) clears its flag; the line's flag can also be set or cleared by hand. | Ours | |

## H. Phase 3: pattern generator

| ID | Rule | Status | Evidence |
| --- | --- | --- | --- |
| A-45 | "Thicker boards towards the centre" (default on): moving out from the centre of the cant, and out from the cant across the sideboards, a board is never thicker than the one inside it. | Ours | Every pattern in the Ngomi dataset and the course notes follows it, and it keeps the search to thousands of candidates instead of millions. It can be switched off. |
| A-46 | The pre-screen only discards clear losers. On the top 60–150 candidates of three classes its order agrees weakly with the full simulation (Spearman 0.2–0.4); the best pattern sat between rank 9 and 51. A 12–16-log stratified sample ranks almost exactly like the whole class (its best was the class's best in all three). So 120 candidates (80 until Phase 4) are sawn on a 12-log sample and the best 10 on every log. In Phase 4 the three-blade edger moved class 3's best pattern to pre-screen rank 87, outside the first 80. | Fitted | `tools/prescreen_vs_full.py`. A sweep allowance in the pre-screen made the agreement no better and was dropped. |
| A-47 | A stack is dropped when another of the thinnest boards (plus a kerf) would fit on each side of it within the cant face at the small end of the smallest log. | Ours | Such a stack leaves a full-length board in the log. Taller stacks are allowed up to the large end of the largest log, because the outer boards still give shorter lengths. |
| A-48 | Each saw blade costs 0.01 recovery points (R0.01/m³ for the value objective) in the ranking, so of two patterns that saw the same boards the one with fewer blades wins. | Ours | Without it, patterns with sideboards that cut nothing on the smaller logs of a class could top the list. |
| A-49 | Diameter chart steps use three ideal logs (SED, SED + 0.5 and SED + 0.9 cm) with the dataset's median taper, sweep in mm/m, ovality and length; each step's log price is the price of the class its SED falls in. | Ours | One log per step was too noisy: board lengths step in 0.3 m. |
| A-50 | Class suggestions use the cross-checked scores: the best three patterns of each step are sawn at every step. A pattern outside that pool can only carry a class over the steps where it was already in the top 10. | Ours | Without the cross-check the suggested classes broke up at nearly every centimetre. |
| A-51 | "Use these as the log classes" keeps the other limits (length, taper, sweep, ovality, core, accepted grades) of the current first class, and each new class takes the log price of the current class containing its middle diameter. | Ours | Diameter is the only thing the chart decides. |
| A-52 | "Never cut" switches those products off for the search only. A saved pattern is sawn with the dataset's own product list, so it may yield an excluded size there. | Ours | Said on the generator form. |

## I. Phase 4: advanced sawing

| ID | Rule | Status | Evidence |
| --- | --- | --- | --- |
| A-53 | Log misalignment and cant misalignment skew the log (or cant) end to end with its middle on the saw line: the shift runs from −m/2 at the small end to +m/2 at the large end. Saw offsets are constant shifts. Log rotation turns the log about the saw's axis (through the end-disc centres) from horns up, anticlockwise as drawn. | Ours | The help pages name the settings without the geometry. Centring the skew keeps a misaligned log's mean position on the saw line. |
| A-54 | Half taper: the secondary cuts follow the curve of the log's centreline. Full taper: they follow the top face of the cant (centreline plus the growth in radius, zero at mid-length), so the taper falls on one side. Either follows at most max sweep (mm/m) × length of the sweep; beyond that the bend is scaled down and the rest sawn straight. | Assumed | From the names and the Phase 0 reading of the help file ("cuts follow the centreline arc" / "the inside curve"). With horns up the top face is the concave one. |
| A-55 | Real-log variation, in our own units: out-of-roundness as % of radius (2–5 lobes per round, drifting along the log), irregular taper as % of diameter, crook as mm of centreline wander, uneven ovality as % of ovality, each a smooth random curve along the log with that standard deviation. Simsaw's generator stores four variation numbers whose units are not documented; they are imported as these. Typical ranges on the Settings page are a starting point, not Ngome measurements. | Ours | Ngomi's variation fields are all 0. Measured logs (Simsaw's log_discs / log_points tables) are not imported: the dataset has none to test with. |
| A-56 | Every random draw for a log (its real-log shape, its board grades) comes from a generator seeded with the run's seed and the log number, so results do not depend on the order logs are sawn in, nor on parallel workers. | Ours | Keeps the brief's "one seeded generator" deterministic per log. |
| A-57 | Arris alignment puts the blade at the comma on the arris: the height where the cant's sawn faces (x = ±cant/2) leave the wood, the lower of the two faces at the top (the higher at the bottom). A blade in the upper half of the stack goes to the top arris, otherwise the bottom one. With "small end only" the arris is taken at the small-end disc, else the tightest along the log. | Assumed | Help page: "the marked blade gives the first full-length bark-free board". Simsaw's own setting is imported (`Arris from top x-sec`). |
| A-58 | Three-blade edger: the first board is pushed to the low or high end of its room and a second board placed exactly one edger kerf beside it (two outside saws and one between). The pair is kept only when it beats the single board on the edging objective. A kerf shared by the two boards is charged to sawdust once. | Ours | Without pinning the second board the edger would need four saws. Ngomi's 3-blade "Best" setting gives no second boards in classes 1 and 2, as in Simsaw's run, but does in classes 3 to 5 (SPEC 16.2). |
| A-59 | Cross-cutting into several boards: after the first board (and any second board), further boards are edged from the length the first left, longest first, up to "max boards per flitch". A board may start on the disc where the previous one was cut off. No cross-cut kerf is charged. | Ours | |
| A-60 | Grade from the defect core: the share of the board's wet cross-section inside the core is sampled on a 6 × 6 grid at up to 12 discs along the board; bands are 0, up to 50 %, up to (not including) 100 %, and 100 %. The board is priced at its drawn grade's combination, R0 if that grade is not a valid product. | Ours | Help page names the four bands. Pricing an invalid grade at R0 keeps the board in the volume figures and shows the loss in value. |

## J. Edger blades and spacing (after Phase 4)

| ID | Rule | Status | Evidence |
| --- | --- | --- | --- |
| A-61 | Fixed-spacing edger: the line gives the wet distance between each pair of neighbouring blades. All blades cut together and the flitch is slid across them to the position that gives the most by the edging objective (of equally good positions, the middle). Each gap makes a board of the widest valid product whose wet width fits it (the board is the gap's full width, the product its dry size); a gap whose piece fails the wane rule, or holds no product of that thickness, is offcut. A cant board that can be taken at full cant width still is, when that gives more. Edger kerfs are charged only beside the boards made. | Ours (owner, 9 Oct 2026: "fixed spacings") | Movable blades (no spacing given) behave as before, so the Simsaw comparison is unchanged. |
| A-62 | Movable blades with more than three blades: the first board is pushed to one end and further boards are added one kerf apart, each the best that fits next, up to one board fewer than there are blades. | Ours | Generalises A-58. A greedy row; the best combination of widths is not searched exhaustively. |
| A-63 | The generator's quick pre-check scores a fixed-blade edger by the best run of neighbouring gaps that fits the flitch together, using the first gap's wane rule. | Ours | Approximation; the shortlist is then sawn with the full engine. |
