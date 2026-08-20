---
id: coverslip-thickness-in-use
question: "What coverslip thickness does this lab mount on, and does it match what
  the objectives are corrected for"
source: user_statement
expert: KH
date: 2026-08-20
confidence: high
evidence: nominal_product_thickness
scope: "All samples on the Ti2-E nosepiece. Concerns the coverslip only — the
  objective's design thickness is a property of the lens, see kb/systems/current.md
  > objectives"
applies_to_systems: [current, current-laser, current-spectra, current-aura]
review_after: 2027-08-20
supersedes: null
---

## Verdict
**170 µm.** The coverslips in use are the 170 µm ones. (The product line runs
140–180 µm; 170 is the one selected, and that is what matters.)

This **matches the design thickness of every objective on the nosepiece**:

| Objective | NA | Immersion | Catalogue cover glass | Collar |
|---|---|---|---|---|
| 4x | 0.20 | air | 0–0.17 mm (works without one) | – |
| 10x | 0.45 | air | 0.17 mm | – |
| 20x | 0.80 | air | 0.17 mm | – |
| 40x WI | 1.25 | water | 0.15–0.19 mm (= collar span) | **yes** |
| 60x Oil | 1.42 | oil | 0.17 mm | – |
| 100x Oil | 1.45 | oil | 0.17 mm | – |

So **G18 is not a bottleneck on this system.** Deviation is zero, margin is
10.0, ROUTINE. The 40x WI's 0.15–0.19 mm collar span brackets 170 µm
comfortably, so that objective has headroom on either side.

## What still costs something: evidence, not physics

`sample.gate` reports `evidence: assumed` when `coverslip_actual_um` is not
supplied, because **170 µm is a nominal product thickness, not a micrometer
reading of the coverslip on the stage.** `docs/06` records that the real spread
of a nominal coverslip is wider than its stated tolerance, and that remains the
reason the reading matters.

The consequence is narrow and worth stating precisely, because it is easy to
overstate in both directions:

- `status` is **PASS** — the geometry is sound. `evidence.assumed` is an *info*
  finding and does not downgrade the status.
- `advances` is **False**, purely on the evidence axis.
- **One micrometer reading is sufficient.** Unlike the sample-medium refractive
  index (settled by literature value, see [[sample-medium-refractive-index]]),
  this one cannot be settled by a nominal figure — but it is a thirty-second
  measurement and it is the only thing standing between an ordinary lens-4
  verdict and `advances: YES`.

## Why the physics cares at all

An objective is designed to form a diffraction-limited image through a specified
thickness of glass; the coverslip is part of the optical design, not an
accessory. A thickness error leaves the objective's internal spherical-aberration
compensation wrong by that difference, which broadens the PSF, drops the peak
intensity, and biases the axial response — silently, which is why G18 is a
**bias** gate rather than hard.

Sensitivity scales roughly as **NA⁴**, so it is ~2,800× stronger on the 100x Oil
(NA 1.45) than on the 4x (NA 0.20). That scaling is illustrative only: this
repository has no wave-optics aberration model and will not add one
([`kb/decisions/2026-08-19-lens-4-scope.md`](../decisions/2026-08-19-lens-4-scope.md)
§3), so G18 reports *that* the thickness deviates and never *how much* that
costs.

## Falsification conditions
1. A micrometer reading of the glass actually in use comes in more than 5 µm off
   170 — G18 would then warn, and `LAB_DEFAULT_COVERSLIP_UM` should change
2. The lab switches to a different thickness from the 140–180 µm product line,
   at which point the deviation is no longer zero and the objectives without a
   collar (all but the 40x WI) lose their design correction
3. An objective is added whose design thickness is not 170 µm, making "the
   design" no longer a single number across the nosepiece — the fallback is
   deliberately routed through the lab constant rather than the objective's
   design value so that this case reports a real deviation

## Related
[[sample-medium-refractive-index]] · [[immersion-media-in-use]] ·
kb/systems/current.md > objectives · data/objectives.yaml ·
kb/decisions/2026-08-19-lens-4-scope.md · docs/06-pitfalls.md ·
sample/setup.py `LAB_DEFAULT_COVERSLIP_UM`
