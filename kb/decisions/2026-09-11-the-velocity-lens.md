---
id: 2026-09-11-the-velocity-lens
question: "What guards the commanded velocity that a Stokes-drag calibration multiplies straight into the measured stiffness?"
date: 2026-09-11
status: current
corrects: []
---

# 2026-09-11 · Lens 9, the system's velocity

**Asked for by KH**, and the framing was deliberately wider than the
subsystem that exposed the gap: *"스테이지 속도라기보다는 시스템의 속도랄까?"* —
the system's velocity rather than the stage's. So the lens covers the piezo
stage's ramps and the AOD trap's sweeps together.

```
python -m velocity.cli window --radius-um 2.5 --viscosity 1e-3 \
    --kappa 3.87 --sigma-nm 10 --target-error 0.05
```

`velocity/`, conditional like lenses 7 and 8, convened whenever something
commands a motion. **L9.1–L9.3 are `hard`, L9.4–L9.5 report.**

## Why it earned a lens

`κ = γv/x_eq`. The velocity goes in **commanded**, so an error in the
commanded-versus-actual scale is an unbounded multiplicative error on the
measured stiffness — and like a wrong pixel size (`docs/06` A1) it leaves a
perfectly reasonable number behind. Nothing was guarding it: `kb/`, `data/`,
`config/`, `hardware/` and `calibration/` hold no velocity calibration of any
kind (verified 2026-09-11).

## The finding, and it is sharper than "no velocity scale exists"

A velocity is a distance over a time, and **the two halves are in completely
different states.**

| half | state |
|---|---|
| distance | **corroborated to 0.24 %** — two independent length standards driven 10 µm on 2026-09-03, read off the camera: closed-loop piezo 0.06460 µm/px, AOD trap 0.06445 (`data/pixel_size.yaml`, 100x row) |
| time | **never checked** |

So L9.1 does not say "there is no scale". It says which half is settled, by how
much, and that the other half is the open one. ⚠ **A closed-loop controller
reporting position is not an answer** — the loop holds its own scale, and
whether that scale is seconds is the question. The action says to time a known
traverse against **the camera's own frame timestamps**, not against the
controller's clock, for exactly that reason.

**The lens therefore FAILS on every real configuration today.** That is the
finding, not a placeholder. Reporting FAIL is more honest than the silence that
preceded it.

## No invented thresholds: `LIMITS` is empty by construction

This was the design constraint that shaped the lens, from `CLAUDE.md` rule 2 —
never originate a physical number. Every bound derives:

| bound | derivation |
|---|---|
| offset **floor** | `δκ/κ = δx/x_eq` at fixed `v` and `γ`, so `x_eq ≥ σ/target`. 10 nm σ and a 5 % target give **200 nm**, and nobody picked a multiple |
| offset **ceiling** | `|x_eq| < ` bead radius — where `trapping.goa.trap_force` refuses, because past it "the focus would fall outside the bead, which this model does not cover" |
| step **duration** | the approach is exponential, residual after `n τ` is `e⁻ⁿ`, so `n = ln(1/target)`. 5 % needs **3.0 τ**, 2 % needs 3.9. **No "about five time constants" appears anywhere in this lens** |

Note what that makes of `target_relative_error`: it left lens 6 when G11 was
removed earlier the same day, because `1/√(N_p·N_f)` did not describe a
single-bead measurement. It is a real input again here, where it sets a
velocity rather than a sample size.

## The headline output

For the drag calibration this instrument is being set up for — 5 µm
polystyrene, water, κ = 3.87 pN/µm measured 2026-09-03, σ = 10 nm, 5 % target:

```
gamma               0.04712 pN s/um
tau = gamma/kappa   12.18 ms
offset per um/s     12.18 nm

offset floor          200 nm   = sigma / target
offset ceiling       2500 nm   = bead radius, where trap_force refuses

VELOCITY WINDOW     16.4 - 205 um/s
step duration       >= 36.5 ms  (3.00 tau, 19 frames at 520 fps)
```

⚠ **The upper end is a hard bound, not a recommendation.** Linearity departs
from the GOA force curve long before the focus leaves the bead — 1.5 % at 20 %
of the radius, 6.5 % at 40 % — and L9.2 reports the offset as a fraction of the
radius so that is visible. At the proposed 20 µm/s the bead sits 243 nm off
centre, 9.7 % of its radius, and κ comes out at 4.11 % against the 5 % target.

## What it deliberately does not own

- **The time axis.** Lens 2 owns the frame rate, lens 3's L3.2 owns whether
  that rate is achieved or requested. L9.5 names them and reports the
  inheritance — L9.3 converts its requirement into frames, so a
  requested-but-not-achieved rate biases the frame count in the direction that
  looks safe. Re-deriving it here would double-charge lens 3.
- **Near-wall drag.** `γ` is the unbounded Stokes value. Lens 4's L4.4 bounds
  the inflation and, by the 2026-08-19 scope decision, does not correct it —
  so a velocity chosen from this window inherits the bias, the
  `assumed_inputs` entry says so, and it is cleared at lens 4 and lens 6
  rather than here.
- **How to reach the velocity on the hardware.**
  `hardware/tweezers_drive.py` already plans AOD slowdown routes. This lens
  judges whether the target is the right target.

## Two things it got right from the start because the review had found them

- **`_ok` writes severity `"info"`, not `"ok"`.** Every `gate.py` drops `"ok"`
  from `findings`, and that turned into five separate invisible-computation
  defects across the other lenses in one review. A new lens does not get to
  repeat them, and `committee.invisible_computations()` confirms lens 9
  contributes none.
- **It is registered with the emission layer.** `committee.emissions.LENSES`
  gained `"velocity"` in the same change, and
  `test_the_layer_covers_every_lens_package` derives the lens set from the
  filesystem so a future lens cannot be added without registering it — a lens
  the layer does not know about is a lens whose emissions nobody reconciles.

## What changed

- `velocity/{__init__,kinematics,setup,checks,gate,cli}.py` — new
- `tests/test_velocity.py` (12) and `tests/test_velocity_gate.py` (22) — new
- `committee/emissions.py` — `velocity` registered, `_OK_SEVERITY` entry
- `tests/test_committee_emissions.py` — site count 104 → 112, plus a test that
  the layer covers every lens package and one that lens 9 has no invisible
  computations
- `tests/test_gate_registry.py` — `LENSES`, committee order, `EXPECTED_CHECKS`,
  `EXPECTED_LIMITS`, `EXPECTED_ADDRESSES`; 43 addresses → **48**
- `tests/test_advances_rule.py` — `velocity` is a judging lens
- `docs/01` (lens table, conditional count 2 → 3, tree), `docs/04` (five rows),
  `docs/05` (a Lens 9 section), `docs/03`, `docs/07`,
  `docs/mhs-integration.md`, `CLAUDE.md` (run order, E4, lens list, counts),
  `README.md` — 48 checks, 31 gates, 9 lenses, 7 judging

1329 passed, 11 skipped, identical under `PYTEST_CI_EMULATE=ci`.

## Open

- **No agent file.** The other conditional lenses have a qualitative half in
  `.claude/agents/`; this one does not, so the judgement that is not in the
  gate is currently nobody's.
- **`STANDING_LENSES` still cannot require a conditional lens**, so lens 9
  absent is indistinguishable from lens 9 not applying — the same hole as
  lenses 7 and 8, deferred to the pipeline rework.
- **The `fps_provenance.*` codes are still unregistered** in lens 6's
  correction tables, which L9.5 now names. That is one of the eight the
  emission layer reports.

## Falsifier

Somebody times a commanded traverse against the camera's timestamps and the
ratio comes back 1.000 within the measurement's own error. Then the time base
was never in doubt, L9.1 has been failing every configuration for nothing, and
the honest conclusion is that a *closed-loop controller's clock is trustworthy
by construction* — which would retire this gate and, more interestingly, weaken
the analogous argument for pixel size.

The narrower falsifier: if a measured ratio is supplied but only as a
declaration, L9.1 says the verdict "rests on the declaration and not on a
number" and stays at MAX_MARGIN without passing cleanly. If that intermediate
state turns out to be the one people actually use, it is doing no work and
should become a plain refusal instead.
