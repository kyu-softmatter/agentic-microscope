---
id: oil-objective-trapping-in-water
question: "Can the oil-immersion objectives trap particles in an aqueous sample,
  and does their higher design NA buy a stronger trap"
source: user_observation
expert: KH
date: 2026-08-18
confidence: high
evidence: measured        # observed at the instrument; the NA arithmetic is exact
scope: "Optical tweezers (1064 nm) on aqueous samples. Applies to any objective
  whose design NA exceeds the sample medium's index — see
  [[sample-medium-refractive-index]] and [[immersion-media-in-use]]"
applies_to_systems: [current, current-laser]
review_after: 2027-08-18
supersedes: null
---

## Verdict

**Yes, they trap — and no, the extra NA buys nothing.** KH observed 2026-08-18
that polystyrene particles trap in water using immersion oil with the 60x and
100x objectives. That observation is correct and it corrected this project: lens
7 had been refusing those objectives outright.

The trap works because rays up to `NA = n_sample` still arrive. The extra NA
does **not** arrive: rays steeper than `NA = n_sample` are totally internally
reflected at the coverslip/sample interface, since Snell's

```
n_glass * sin(theta_glass) = NA_ray = n_sample * sin(theta_sample)
```

has no solution once `NA_ray > n_sample`. These are the same rays, at the same
interface, that TIRF illumination is built on.

| Objective | Design NA | Effective NA in water | κ per mW, 4 µm PS bead |
|---|---|---|---|
| 40x WI | 1.25 | 1.25 (matched, nothing lost) | 0.433 pN/µm |
| 60x Oil | 1.42 | **1.333** | 0.421 pN/µm |
| 100x Oil | 1.45 | **1.333** | 0.421 pN/µm |

Two consequences worth keeping:

- **60x Oil and 100x Oil are indistinguishable for trapping.** They clip to the
  same effective NA, so neither has any trap-strength advantage over the other.
- **All three agree within ~3%.** For a bead far larger than the focus
  (4 µm bead vs a ~260 nm waist) the stiffness is set by the bead's own
  geometry, not by the focus size. High NA matters for sub-micron particles,
  not here. **So the objective choice is an imaging decision, not a trapping
  one** — pick on effective pixel size and field of view.

## What it costs, and why a clipped verdict still cannot advance

Clipping is the correct computation, not an approximation — the discarded rays
are genuinely absent. But three limits ride along, and
`trapping.checks.check_effective_na` reports all three rather than letting them
pass silently:

1. **The computed stiffness is an upper bound.** Fresnel transmission falls to
   zero *at* the critical angle, so the outermost surviving rays carry vanishing
   power. The model weights them fully.
2. **Spherical aberration is not modelled at all.** The same index step that
   clips the NA aberrates the focus, depth-dependently, and the ray-optics model
   in `trapping/goa.py` has no term for it. The real focus is worse than the
   computed one. This is why the clipping is recorded in `assumed_inputs`: a
   TIR-clipped configuration reports `advances: False` until someone bounds the
   aberration, while an index-matched objective advances.
3. **It pins the working depth, and that costs quantitative accuracy.** G17
   limits depth to `1.85/|Δn| ≈ 10 µm` for oil on water. At that height a 4 µm
   bead carries a **+12.7% Faxén wall-drag bias** (+29% at 5 µm), and
   `trapping.dynamics.corner_frequency_hz` applies no wall correction. For an
   experiment that infers force from a commanded velocity, that bias lands
   directly on the measured quantity.

## How to use an oil objective quantitatively anyway

Calibrate the trap **in situ at the actual working height.** A power-spectrum
corner frequency gives `κ` and the wall-corrected drag `γ` together, since
`f_c = κ/(2πγ)` — so the Faxén bias is absorbed by measurement instead of
corrected by formula. G14 requires that calibration regardless, so it is not
extra work. It must be redone whenever the working height changes.

If the wanted quantity is an absolute force or drag and the depth is free to
choose, the 40x WI at 1.5x intermediate magnification is the better trade: it is
index-matched, sampling-identical to 60x Oil at 1.0x (both 108.3 nm/px, both
347 µm wide at 3200 px), and it can work 50–100 µm deep where the Faxén bias
falls to 1–2%.
