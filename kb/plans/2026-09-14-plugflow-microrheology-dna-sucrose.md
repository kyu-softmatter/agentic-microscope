---
id: 2026-09-14-plugflow-microrheology-dna-sucrose
question: "How does the mobility of a trapped 5 um probe in 3c* lambda-DNA / 55% sucrose change with Weissenberg number under plug flow"
date: 2026-09-14
status: planned
subsystems: [microscope, tweezers, piezo]
---

# 2026-09-14 · Plug-flow mobility vs Wi, lambda-DNA / 55 % sucrose

## Request

Operator (KH), 2026-09-13:

> "now lets say i want to do the same experiment with plug flow to capture the
> chnge in mobility of the particle under plug flow, what flow should i use and
> how to use the piezo? what speed to run at? i orobably need high enough Wi to
> probe non linearity"

**Runs second.** It is parameterised on `lambda`, the DNA relaxation time,
which the passive run
([2026-09-14-passive-microrheology-dna-sucrose](2026-09-14-passive-microrheology-dna-sucrose.md))
measures. **Do not run this first** — every velocity below is derived from
`lambda` and guessing it wastes the session.

## Proposed setting + rationale

**Plug flow requires the trap.** A freely suspended bead in uniform flow
translates with the fluid: no relative velocity, no local strain rate, nothing
nonlinear to probe. Strain is generated only by *holding* the bead while the
fluid moves, so **the trap's maximum force sets the maximum reachable Wi.**

The operator's own framework (slide "How do we choose a fluid?", 2026-09-13),
whose algebra was checked and holds:

    Wi = lambda * U / D          (D = DIAMETER)
    F_drag = 3 * pi * eta * D * U
    F_trap = alpha * <x>,  linear regime taken as <x> < D/5
    =>  eta/lambda = alpha / (15 * pi * D * Wi)

With the operator's `eta = 0.3 Pa.s` and `D = 5 µm`,
`gamma = 3*pi*eta*D = 14.14 pN.s/µm`, and `<x> <= D/5 = 1 µm`:

| lambda | Wi | U | F_drag | **alpha required** | rms fluct |
|---|---|---|---|---|---|
| 5 s | 1 | 1.00 µm/s | 14.1 pN | 14.1 pN/µm | 16.9 nm |
| **10 s** | **1** | **0.50 µm/s** | **7.1 pN** | **7.07 pN/µm** | **23.9 nm** |
| 10 s | 3 | 1.50 µm/s | 21.2 pN | 21.2 pN/µm | 13.8 nm |
| 20 s | 1 | 0.25 µm/s | 3.5 pN | 3.54 pN/µm | 33.8 nm |

**Read the required alpha off the measured `lambda`** once the passive run
reports it. `alpha_req = 15 * pi * eta * Wi * D / lambda`, linear in D — a
smaller probe needs a softer trap, but 5 µm was chosen for heterogeneity
averaging and is not re-litigated here.

**This trap is ~5-15x stiffer than the passive run's.** At alpha ~= 7 pN/µm the
thermal fluctuations are ~24 nm = 0.37 px, at the localisation floor:
**no passive rheology can be extracted from this run.** Two runs, two powers,
two calibrations — that is why these are separate plans.

### Piezo trajectory

Total travel is **720 µm** (operator, 2026-09-13). Trajectories are
range-checked against the travel the controller reports and **refused, never
clipped** (SAFETY §3), so an overrun aborts rather than silently truncating.

- Centre **360 µm**; usable **±300 µm**; 60 µm guard at each end.
- **Triangle wave**, constant-speed legs, alternating direction. The reversals
  are not waste: the **startup transient at each direction change is the
  nonlinear signature** being looked for.
- **Fix the leg duration and vary the amplitude** — at fixed amplitude the slow
  legs cannot traverse and the fast legs overrun:

| Wi (at lambda = 10 s) | U | leg amplitude | leg time |
|---|---|---|---|
| 0.3 | 0.15 µm/s | 36 µm | 4 min |
| 1 | 0.50 µm/s | 120 µm | 4 min |
| 3 | 1.50 µm/s | 300 µm (capped) | 3.3 min |

- **Soft-start every leg over ~1 s.** Stepping straight to 1.5 µm/s applies
  21 pN instantly, above the trap ceiling, and drops the bead at every reversal.
  This is the velocity-domain form of SAFETY §3's "ramp large moves, don't step
  them".

## Committee verdict

Not yet convened — this plan is written before the passive run supplies
`lambda`. **It must not be executed on the verdict below**; re-run the
committee with the measured `lambda` and `alpha` first.

| Lens | Verdict | Deciding gate | m | Evidence |
|---|---|---|---|---|
| 1 optics | not run | — | — | unchanged optically from the passive plan |
| 2 detection | **BLOCKED** | `missing.photon.signal` | — | same test frame unblocks both |
| 3 compute | PASS_WITH_CHANGES | `data_rate` | 10.00 | same ROI and rate as the passive run |
| 4 sample | PASS (at n=1.43) | `geometry.ri_mismatch` | 1.05 | assumed index |
| 5 photo | not run | — | — | convene with lens 1 per E6 |
| 6 validity | not run | — | — | see the analysis warning below |
| 7 trapping | not run | — | — | **must be re-run at the flow alpha**, not the passive one |
| 8 mechanical | not run | — | — | convene if total time exceeds ~30 min |

**Not evaluated.**

- **Trap heating, again ungated** (E3), and this run uses a **stiffer trap and
  therefore more power** than the passive one. The bias is larger here, and
  still nothing computes it.
- **Lens 6 has an unresolved objection, recorded now so it is not discovered
  afterwards.** From
  [microrheology-standard-conditions](../expertise/microrheology-standard-conditions.md):
  the Stokes-drag route `kappa = gamma*v/x_eq` is **"not implemented
  anywhere. The `creepx` pipeline detrends that mean away to isolate
  fluctuations, so the drag information is discarded by design."** The mean
  displacement under flow **is the entire signal of this run**, and the
  existing analysis will subtract it. `D:\codes` is not this repository's to
  edit (CLAUDE.md §6). **Resolve the analysis path before acquiring**, or the
  data cannot answer the question.

## Preconditions

- [ ] **`lambda` measured** by the passive run — *checked by:* a fitted
      relaxation time in that run's outcome section. Every velocity depends on
      it.
- [ ] **Everything in the passive plan's preconditions** — *checked by:* that
      plan. Index, temperature, photometry and trap calibration all carry over.
- [ ] **Analysis path that keeps the mean displacement** — *checked by:* a
      script that reports `x_eq` under known stage velocity without detrending.
- [ ] **Piezo travel confirmed as 720 µm** — *checked by:* the travel the
      controller reports, not this file.
- [ ] **NanoBench 6000 session closed** — *checked by:* COM4 opens. The port is
      exclusive (SAFETY §3).
- [ ] **Piezo centred at 360 µm BEFORE a bead is trapped** — *checked by:*
      position readback. Centring after trapping translates the sample by
      hundreds of µm and tears the bead out (SAFETY §3).

## Sequence

[SAFETY §8](../../SAFETY.md) is the standing setup order. Specific to this run:

| # | Subsystem | Action | Flag required | Confirmed by |
|---:|---|---|---|---|
| 1 | piezo | Unlock; **centre all axes at 360 µm**, ramped not stepped | `--unlock --allow-motion` | position readback at 360 µm |
| 2 | microscope | Focus to 20 µm above the coverslip | `--allow-motion` | `ZDrive` readback |
| 3 | tweezers | Trap a bead; raise dial to the `alpha_req` for the measured `lambda` | `--allow-laser` | measured `alpha = kT/var(x)` from 60 s of frames |
| 4 | — | Record the dial % **by hand** | — | written in the session log; nothing reads it back |
| 5 | microscope | Close the live view | — | viewer gone — it degrades timing ~20x |
| 6 | piezo | Triangle leg at the lowest U, **soft-started over ~1 s** | `--unlock --allow-motion` | bead still trapped; `x_eq` reaches a plateau |
| 7 | microscope + piezo | Acquire on one clock through the velocity ladder | `--unlock --allow-motion` | per-frame timestamps aligned to stage position |
| 8 | piezo | **Close the waveform with a final sample at the centre** | `--unlock --allow-motion` | position readback at 360 µm, not 1.5 µm low |
| 9 | microscope | Check drops, achieved rate, and bead retention | — | `ImageNumber` continuous; bead present in last frame |

**A return code is not a confirmation** (SAFETY §0). The piezo has position
readback and the camera has frames; the tweezers have neither. Confirm the trap
only by observing the bead.

## Stop conditions

- **Bead lost at a reversal** → the soft-start ramp is too fast or `alpha` is
  too low for that U. Stop, drop to the previous U, do not continue the ladder.
- **`x_eq` exceeds D/5 = 1 µm** → the linear-regime assumption behind the whole
  velocity ladder has failed. Stop; that Wi is not reachable at this `alpha`.
- **Trajectory refused by the range check** → an amplitude exceeds the 720 µm
  travel. Do not retry with a clipped trajectory; re-derive the leg amplitude.
- **Any abort** leaves: piezo **returned to 360 µm centre** (never parked
  mid-travel), laser disarmed at the GUI, light down via the `finally` path.
  A force-kill skips cleanup and leaves excitation on — use the stop-file.
