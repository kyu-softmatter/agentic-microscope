---
id: sample-mount-geometry
question: "How are this lab's samples mounted, and what does that geometry decide
  for lens 4"
source: user_statement
expert: KH
date: 2026-08-20
confidence: high
evidence: standing_practice
scope: "Default mounting for this lab's samples. Individual experiments may
  differ — ask when one does"
applies_to_systems: [current, current-laser, current-spectra, current-aura]
review_after: 2027-08-20
supersedes: null
---

## Verdict
**No spacer, no gasket.** The samples are mounted with the coverslip directly
against the sample. There is no chamber part setting a height.

`SampleSetup.unspaced_mount = True` is the flag for this, and it is the normal
case here, not the exception.

## Three consequences, in order of how easy they are to get wrong

### 1. The optical path is unchanged — do not "correct" the working distance

A spacer would not have been in the light path anyway; it forms the chamber walls
while the light goes through the one piece of glass facing the objective. Its
absence changes nothing about the working-distance budget. G16's only glass term
is the coverslip, and `coverslip_actual_um` carries it.

This is recorded because the opposite conclusion is intuitive and was reached
once during review: "a spacer sits between objective and sample, so it must eat
working distance." It does not, in either orientation of stand.
([`kb/decisions/2026-08-19-lens-4-scope.md`](../decisions/2026-08-19-lens-4-scope.md))

### 2. The sample thickness is uncontrolled, so G16b has nothing to check against

With a spacer, a missing `chamber_height_um` just means nobody looked the part
up. Without one, **there is no designed thickness to look up** — the gap is set
by drop volume, wetting, and the coverslip's own weight. It varies between
preparations, and a squashed drop is a **wedge**, so it varies across the field
too: the same commanded z is a different position in the sample at different
x, y.

G16b therefore does not skip quietly when `unspaced_mount` is set; it emits an
`info` finding saying no designed height exists, and asks for an estimate if the
focal depth is more than a few µm. It stays out of the feasibility grade — the
mount is not a defect — but it stays visible.

### 3. Particles sit near a wall — bounded, and normally absorbed by the trap

A thin unspaced sample keeps particles within a few µm of the coverslip, where
the drag is not the bulk Stokes drag. **G16c bounds it** rather than modelling
it: the truncated parallel-to-wall Faxén term `9a/(16h)` over-states the drag, so
`D` is low by *at most* that fraction. It reproduces
[`docs/06`](../../docs/06-pitfalls.md) D8's table exactly.

| a = 2 µm bead | h = 5 µm | 10 µm | 20 µm | 50 µm |
|---|---|---|---|---|
| drag penalty (≤) | +29.0% | +12.7% | +6.0% | +2.3% |
| `D` suppression (≤) | 22.5% | 11.2% | 5.6% | 2.2% |

Direction: `γ` up → `D = kT/γ` down → **measured `D` low, inferred viscosity and
moduli stiff.**

**The trap normally absorbs it, and this lab mainly traps** (KH 2026-08-20). D8's
answer to Faxén is in-situ power-spectrum calibration at the working height,
which returns κ and the wall-corrected γ together. So for the ordinary case G16c
reports the bound as INFO and the only standing obligation is: **redo the
calibration whenever the working height changes.**

The exception is **untrapped** measurement — free-diffusion, MSD-based
microrheology. There is no calibration step, so nothing absorbs the wall term and
the bound is the whole answer. Then G16c goes `bias`, and lens 6 rules on whether
the bound is acceptable. The lever is depth: the bound falls as `1/h`.

No Faxén *correction* is applied in either case
([`kb/decisions/2026-08-19-lens-7-scope.md`](../decisions/2026-08-19-lens-7-scope.md)
§2). Bounding and correcting are different acts — see
[`docs/01`](../../docs/01-architecture.md) §3 Principle 1b, of which this is the
worked example.

## What this does not settle
- **How thin is thin.** No typical drop thickness is on record. An estimate per
  preparation would make G16b runnable. G16c does not need it — it takes the
  imaging depth as `h` directly.
- **Whether the untrapped case ever arises here.** Mainly trapped, so mainly
  moot. Worth asking per experiment rather than assumed either way.

## Falsification conditions
1. A preparation uses a spacer, gasket, or coverslip-bottomed dish with a
   defined depth — then `unspaced_mount` is False for that experiment and
   `chamber_height_um` is a real part spec
2. A measured typical drop thickness is recorded, which converts consequence 2
   from "no height exists" to "the height is X ± Y"
3. Untrapped measurement becomes routine, at which point consequence 3 stops
   being a reported bound and starts being a live bias for lens 6 to rule on

## Related
[[coverslip-thickness-in-use]] · [[oil-objective-trapping-in-water]] ·
docs/06-pitfalls.md D8 · kb/decisions/2026-08-19-lens-4-scope.md ·
kb/decisions/2026-08-19-lens-7-scope.md ·
docs/01-architecture.md §3 Principle 1b ·
sample/setup.py `unspaced_mount` · sample/checks.py G16b · G16c
