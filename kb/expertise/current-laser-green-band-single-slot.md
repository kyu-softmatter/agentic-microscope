---
id: current-laser-green-band-single-slot
question: "On the current-laser scope (LUN-F-XL + CSU-W1), can two dyes excited at
  488nm and emitting in the 500-530nm band be seen simultaneously as distinguishable
  channels"
source: calculation
expert: KH
date: 2026-08-10
confidence: high
scope: "config/scopes/current-laser.yaml — LUN-F-XL 4 lines (405/488/561/640) +
  EM1 filter wheel + dual-camera splitter at 561nm (DM A561LP)"
applies_to_systems: [current-laser]
review_after: 2027-08-10
supersedes: null
---

## Verdict
Impossible. Computed with `optics.cli recommend`, FITC and YOYO-1 (the
dsDNA-binding form, both with em_peak in the 500-530nm band) come out with exactly
the same optimal (line, filter, camera) combination: 488nm / EM1-525/36 /
Kinetix_blue — physically the same channel, so crosstalk is effectively 100%. Do
not judge by eyeballing em_peak nm and concluding "10nm apart, should be fine";
always recompute with recommend.

## Why
- There are only four excitation lines, 405/488/561/640, so dyes in this band
  effectively only use the 488 line (excitation efficiency is near zero at
  405/561/640 — FITC's 405nm candidate brightness actually computes to 0.0000)
- The EM1 filter wheel has only one band covering 500-530nm, EM1-525/36
  (the 88000v2-EM 4-band has worse blocking OD and ranks lower — not an
  alternative)
- The dual-camera splitter (DM A561LP) splits at 561nm, so 500-530nm emission
  always goes to just one side, the reflected side (Kinetix_blue) — the splitter
  cannot separate them either

## Applicability
- Limited to the config/scopes/current-laser.yaml scope (other scope/light-source
  combinations need recomputing)
- Expected to apply to every dye pair whose em_peak falls roughly within
  495-530nm (confirmed with FITC/YOYO-1; e.g. an AlexaFluor488 + EGFP combination
  is likely to clash for the same reason — recompute individually, this entry does
  not automatically guarantee it)
- Does not apply to dyes on a different line (e.g. 405-only dyes) or to sequential
  (time-division) acquisition — this verdict concerns "simultaneous" observation
  only

## Falsification conditions
This verdict is based on parametric (peak_nm + FWHM) approximate spectra
(evidence: assumed — no measured FITC/YOYO-1 curves are linked in
data/fluorophores.yaml, see data/spectra/README.md). Any one of the following
observations puts it up for review:

1. Measured absorption/emission curves for FITC and YOYO-1 (dsDNA-binding form)
   are added to data/spectra/ and linked via `curves:` in fluorophores.yaml, and on
   recomputation the optimal (line, filter, camera) combination differs from the
   current one
2. A filter that divides the 500-530nm band is newly added to the EM1 (or EM2)
   filter wheel (e.g. a narrow band like 510/20)
3. The dual-camera splitter is swapped for one that splits at a wavelength inside
   this band (495-530nm, e.g. 510nm) instead of 561nm

## Related
[[fitc-yoyo1-channel-conflict]] (agent memory) ·
kb/decisions/2026-08-10_fitc-particle-yoyo1-dna-2color.md ·
config/channels/particle647-yoyo1-2color.yaml
