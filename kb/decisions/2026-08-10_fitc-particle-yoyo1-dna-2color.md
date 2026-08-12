# 2026-08-10 · FITC particle + YOYO-1 DNA simultaneous 2-color design

## Request
Image FITC-coated particles and YOYO-1-labeled DNA simultaneously (as channels
distinguishable within one frame) on the current system (current-laser scope,
CSU-W1 spinning disk + LUN-F-XL laser).

## Proposed settings + basis (gate output summary)
- First calculation, `optics.cli recommend config/scopes/current-laser.yaml --dyes FITC,YOYO1`:
  both dyes come out with exactly the same optimal combination, 488nm /
  EM1-525/36 / Kinetix_blue → physically the same channel, crosstalk effectively
  100%. Simultaneous 2-color is impossible with this combination
  (→ [[current-laser-green-band-single-slot]]).
- Even forcing the assignment with `--panel --lines 488,405`, FITC's 405nm
  candidate brightness is 0.0000 — there is no excitation at all. Not a real
  solution.
- Alternative search: swap the particle label for a 647-class red.
  `optics.cli recommend --dyes YOYO1,ATTO647N --panel --lines 488,640`:
  YOYO1 (488/EM1-525/36/Kinetix_blue) + ATTO647N-class (640/EM1-705/72/Kinetix_red),
  crosstalk margin computed at 10.0 — physically separated.
  (Equivalent alternative: keeping FITC and swapping the DNA stain for SYTO61
  (628/645nm) gives the same margin — which label to change is a matter of reagent
  availability.)
- Channel definition file: config/channels/particle647-yoyo1-2color.yaml
  (dye: ATTO647N is an example — replace with the actual particle conjugate name)
- Both channels are grade `HARD` (margin 0.87, not PASS) — evidence is assumed
  (parametric spectra), which pushes the blocking requirement up to 7 OD, and
  without measurement only a 6.1 OD approximation comes out. Can proceed, but
  reproducibility is low.
- Final `optics.cli check` run result is **BLOCKED** — Kinetix is registered in
  data/detectors.yaml, but `read_noise_e` is null because the camera mode
  (Speed 2.0e-/Sensitivity 1.2e-/DynamicRange 1.6e-) is unsettled, and
  `full_well_e`/`dark_e_per_s` have no values in the datasheet itself. SNR and
  saturation cannot be computed until it is settled which mode is used.

## Settings actually used (and why, if different)
TBD — not yet run. Fill this in on execution (whether the particle label was
actually swapped, which 647-class dye was used, Kinetix mode, etc.).

## Result
TBD.

## What was learned → which files were changed
- Dye pairs in the green band (495-530nm) always compute to the same channel on
  this scope → generalized into a rule and written up as the new
  kb/expertise/current-laser-green-band-single-slot.md.
- config/channels/particle647-yoyo1-2color.yaml newly written (particle=647-class,
  DNA=YOYO1).
- Confirmed that the unsettled Kinetix camera mode blocks `check` on every channel
  → added to docs/02-knowledge-base.md §10 open questions.

## Related
[[current-laser-green-band-single-slot]] · config/scopes/current-laser.yaml ·
config/channels/particle647-yoyo1-2color.yaml
