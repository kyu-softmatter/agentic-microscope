---
id: 2026-09-15-drag-calibration-stiffness-vs-size
question: "How does the trap stiffness of this instrument depend on particle size, and how large is the near-wall drag correction, measured by Stokes drag at one laser power"
date: 2026-09-15
status: planned
subsystems: [microscope, tweezers, piezo]
---

# 2026-09-15 · Stokes-drag calibration of alpha(a), across particle sizes

## Request

Operator (KH), 2026-09-15, in conversation:

> "다양한 크기의 입자로 드래그캘리브레이션을 해서 입자의 크기별 트랩 스티프니스를
> 측정하고자 해. 실험방법을 디자인해줘"

*(Quoted verbatim as the operator stated it. "I want to do a drag calibration
with particles of various sizes, to measure the trap stiffness per particle
size. Design the experimental method.")*

Extended in the same session, after the first draft of this plan:

> "응 이번 캘리브레이션에서 wall effect 도 정량적으로 측정해보면 좋겠다"

*("Yes — and in this calibration I would like the wall effect measured
quantitatively as well.")*

So: **alpha as a function of bead radius**, obtained by Stokes-drag calibration,
at one fixed laser power — and the **near-wall drag correction measured rather
than assumed**, on the same beads in the same run. Nothing about the medium, the
size list, the power or the temperature was specified; what each of those is
resolved to below is marked as a proposal or as BLOCKED, never as a fact.

**Why it is worth a run.** The stiffness model in `trapping/goa.py` predicts
**exactly `alpha ∝ 1/a` and nothing else**: `trapping.cli force-curve --dial 1`
at the 100x Oil (NA 1.45 -> effective 1.325, n_bead 1.5715, n_medium 1.3245)
returns 5.7875 / 4.3388 / 3.5054 / 2.8917 pN/µm at a = 1.5 / 2.0 / 2.475 /
3.0 µm, whose product with `a` is 8.68 pN to three figures at every radius. This
run therefore tests the model's only size prediction, and a departure from `1/a`
is the result rather than an error.

## Proposed setting + rationale

Every number below came from a gate, from `data/`, or from `kb/`. The sample
properties that are the operator's to supply are listed as BLOCKED in
Preconditions instead of being filled in here.

| Axis | Value | Source |
|---|---|---|
| Objective | `100x-Oil`, position 6 | [microrheology-standard-conditions](../expertise/microrheology-standard-conditions.md) |
| Binning / pixel size | 1x1, **0.06453 µm/px** | `data/pixel_size.yaml`, measured |
| Camera / mode | `Kinetix_red`, 16-bit `DynamicRange` | standing conditions; `data/detectors.yaml` |
| ROI | **256 (W) x 512 (H) px** | [2026-09-10 drag-calibration envelope](../decisions/2026-09-10-drag-calibration-operating-envelope.md) — width sets data rate (<=271 px), height sets frame rate |
| Exposure ⇒ period | **0.45 ms ⇒ 520 fps** | same envelope; its chosen operating point, off the boundary on purpose |
| Illumination | Aura **CYAN 36 per-mille**, set by counts | same envelope; SAFETY §6 (per-mille, not percent) |
| Circular buffer | **3200 frames** | same envelope, lens 3 margin 1.23 |
| Traps | **one** | splitting the beam halves the power per trap ([2026-09-03](../decisions/2026-09-03-three-subsystems-first-light.md) §6), and power is the one axis that must be common to every size |
| Drive | **piezo triangle wave, static trap** | the piezo reads back and the trap does not (SAFETY §0) |
| Drive amplitude | **±10 µm** about piezo mid-travel | SAFETY §3 |
| Target displacement | **x_eq = 0.15 a**, per size | proposal — keeps the bead inside the linear region of the trap |
| Velocities | **4 per size**, {0.25, 0.5, 0.75, 1.0} x the table's v | proposal — the slope of x_eq(v) is the measurand, not any single point |
| Segmentation | **3 segments x 5 s per velocity**, moving sample region between segments | proposal, CLAUDE.md D8 |
| Laser dial | **one value, held across every size, written down by hand** | not readable or settable in software (SAFETY §1) |

### The frame rate is not the standing 50 fps, and that is a concession

`trapping.cli check --detector-fps 50` fails the hard sampling gate at every
radius — at a = 2.475 µm it needs 1194 fps against the model's alpha at dial
10 % (margin 0.04). The gate is `f_s >= 10 f_c`, and `f_c = alpha/(2*pi*gamma)`
scales as `1/a^2`, so the small end of the series is the demanding one. Per-size
requirement, with `gamma = 6*pi*eta*a` Faxen-corrected at h = 8 µm, eta =
1.0016e-3 Pa.s (`trapping.dynamics.water_viscosity_pa_s(20)`), and the model's
`alpha = 8.68/a`:

| diameter | Mie x | alpha_model pN/µm | Faxen on gamma | x_eq = 0.15a | v µm/s | f_c Hz | **needs fps** |
|---|---|---|---|---|---|---|---|
| 0.5 µm | 2.0 | 34.7 | +1.8 % | 0.6 px | 271 | 1150 | 11 502 |
| 1.0 | 3.9 | 17.4 | +3.6 % | 1.2 px | 133 | 282 | 2 824 |
| 2.0 | 7.8 | 8.68 | +7.6 % | 2.3 px | 64 | 68 | 680 |
| 3.0 | 11.7 | 5.79 | +11.8 % | 3.5 px | 41 | 29 | 291 |
| 4.0 | 15.6 | 4.34 | +16.4 % | 4.6 px | 30 | 16 | 157 |
| 4.95 | 19.4 | 3.51 | +21.1 % | 5.8 px | 23 | 9.9 | 99 |
| 6.0 | 23.5 | 2.89 | +26.7 % | 7.0 px | 18 | 6.4 | 64 |

**520 fps covers every size at or above 3.0 µm with >=1.8x margin**, so one
acquisition setting serves the whole gradeable series — which also keeps the
photon budget common across sizes, and the envelope's own lens 2/3 verdicts
apply unchanged. Giving up the standing 50 fps is a **rank 3 concession**, named
here rather than spent silently (CLAUDE.md H1). It is paid for in rank 4: the
exposure ceiling at 520 fps is 0.576 ms at <=30 % duty, hence CYAN 36 per-mille.

### The size range this run may claim, and where it stops

- **Lower bound, hard: diameter ~2.6 µm.** Below it the Mie size parameter
  leaves the ray-optics regime and `trapping.gate` returns **BLOCKED**
  (`missing.regime`: "a GOA force number here would be fiction") — verified at
  a = 0.25 / 0.5 / 1.0 µm. A smaller bead can still be *measured*; it cannot be
  *graded*, and `unevaluated` is not `cleared`.
- **Registered sizes today are two:** `abvigen-blue-4um-nh2` (4.0 µm) and
  `bangs-dragongreen-5um-cooh` (4.95 µm measured lot mean) / `abvigen-red-5um-cooh`
  (5.0 µm), per `data/particles.yaml`. That is a **1.24x span**, against the
  ~8 % systematic in §Error budget — not enough to resolve `1/a`. **The size
  list is the one blocking input** (Preconditions P0).

### The wall effect: why one drag measurement cannot give it, and what does

**A drag calibration alone cannot separate the wall from the trap.** The
measured quantity is `x_eq/v = gamma_corr(h)/alpha(h)`, and both factors depend
on h: gamma through Faxen, alpha through the spherical aberration of an oil
objective focused into water, which `trapping.gate` reports as unmodelled and
which makes its own stiffness an upper bound. A height series of drag alone
returns their ratio and attributes all of it to whichever factor the reader
already believed in.

**Three observables on the same trapped bead break the degeneracy**, and the
acquisition above already produces all three:

| observable | what it measures | independent of |
|---|---|---|
| slope of `x_eq(v)` | `gamma_corr/alpha` | — |
| `var(x)` of the residuals, `alpha = kT/var(x)` | **alpha alone** | gamma |
| Lorentzian corner `f_c = alpha/(2*pi*gamma)` | `alpha/gamma_corr` | — |

The first and third are the **same information** (`f_c = 1/(2*pi*slope)`), so
they are a consistency check rather than a third constraint. The pair that
matters is **drag x equipartition -> gamma_corr(h)**, with `f_c` as the audit.
Both equipartition biases are bounded at this operating point:

- **localisation noise inflates `var(x)`** and so *under*-states alpha. The
  thermal amplitude is `sqrt(kT/alpha) = 34 nm` at alpha = 3.5 pN/µm, so an
  epsilon of 10 nm is already 9 % of the variance. It must be **measured, not
  assumed**: a bead **stuck to the coverslip**, imaged at the same exposure,
  light level and mode, gives epsilon directly. That stuck bead is wanted anyway
  as the z datum (P8) and as the drift witness (P10).
- **motion blur deflates it**, by `2*D*t_exp/3`. At 0.45 ms and h = 3-10 µm that
  is **1.2-1.9 % of the variance** — computed per height in the table below,
  and small because the envelope's exposure is short.

### The height ladder, and what it returns

Six heights on one bead, `a` = 2.475 µm. `s = 9a/(16h)` from
`sample.aberration.wall_drag_suppression`, which **refuses h <= a** rather than
returning a number there, and whose truncation after `9a/(16h)` over-states the
drag:

| h | s | gamma/gamma_0 | Faxen | v µm/s | f_c Hz | needs fps | blur on var(x) |
|---|---|---|---|---|---|---|---|
| 3.0 µm | 0.464 | 1.866 | +86.6 % | 14.9 | 6.4 | 64 | 1.21 % |
| 3.5 | 0.398 | 1.660 | +66.0 % | 16.8 | 7.2 | 72 | 1.36 % |
| 4.5 | 0.309 | 1.448 | +44.8 % | 19.2 | 8.2 | 82 | 1.56 % |
| 6.0 | 0.232 | 1.302 | +30.2 % | 21.4 | 9.2 | 92 | 1.73 % |
| 8.0 | 0.174 | 1.211 | +21.1 % | 23.0 | 9.9 | 99 | 1.86 % |
| 10.0 | 0.139 | 1.162 | +16.2 % | 24.0 | 10.3 | 103 | 1.94 % |

- **Lever arm: 1.43x in gamma** between h = 3.5 and 10 µm, against a ~3 %
  per-point statistical error. The effect is 14 sigma from flat; this is
  measurable, not marginal.
- **The far end is capped at ~10 µm** by lens 4's RI-mismatch screening limit
  `1.85/|dn|` for an oil objective in water. The near end is capped by
  `h > a` — the expansion's own domain — plus the bead's physical radius.
  **h = 3.0 µm on a 2.475 µm-radius bead leaves 0.5 µm of clearance and is the
  last row for that reason**; the run starts at 3.5 and only goes lower if the
  bead is behaving.
- **520 fps clears every row with >=5x margin.** The height ladder costs nothing
  in frame rate — the far-wall rows are the *easy* ones, because Faxen lowers
  `f_c`.

**The absolute height comes out of the fit, not out of the stage.** The piezo
reads back its own displacement, but the offset between the focal plane and the
trap centre is a constant nobody has measured, so `h = dz_piezo + h0` with `h0`
unknown. Fitting `gamma(dz) = gamma_0/(1 - 9a/(16(dz + h0)))` over the six
heights recovers both. Simulated over 400 realisations at 3 % per point
(`numpy`, seed 3): **`h0` to ±0.195 µm and `gamma_bulk` to 2.1 %**, both
unbiased. So this run's by-product is **the absolute trapping height**, which
[SAFETY §9](../../SAFETY.md) lists as an open safety question and calls the
quantity that dominates alpha.

**What this ladder does not measure.** The **perpendicular** Faxen coefficient.
The drive is in x, so this is the parallel-to-wall correction only, and the
axial drag near a wall is a different and larger series. Nothing here licenses
an axial claim.

### Error budget, and the one term that decides the run

`alpha = gamma_corr * v / x_eq`, so the relative errors add as those of gamma,
v and x_eq. What matters is the **ratio between sizes**, where the common terms
cancel:

| term | on one size | on the size ratio |
|---|---|---|
| eta (2.4 %/K, [2026-09-03](../decisions/2026-09-03-three-subsystems-first-light.md) §9) | 1.2 % at ±0.5 K | cancels |
| pixel size 0.06453 (measured, two standards agreeing to 0.24 %) | 0.3 % | cancels |
| piezo velocity | <0.5 %, closed loop | cancels |
| bead radius a | lot CV — `lot: null` on two of the three products, read it off the tube | **does not cancel** |
| **Faxen wall drag** | **+16 % to +87 % over the ladder** | **measured here, not assumed — see the ladder above** |
| height offset h0 | ±0.195 µm from the fit -> ~1 % on gamma at h = 8 µm | partially cancels (common h0) |
| localisation noise epsilon on `var(x)` | ~9 % of variance at epsilon = 10 nm, **measured on a stuck bead** | cancels only if epsilon is size-independent, which it is not |
| statistics (thermal) | ~15 independent samples per plateau -> 8 nm on 371 nm = 2 %; <1 % over 12 segments | — |

`s = 9a/(16h)`, so at a fixed h = 8 µm the correction would run from +3.6 % at
1 µm to +21.1 % at 4.95 µm: a **17 % false size dependence across the series**,
with the same shape as the `1/a` being sought. **Collecting more frames is
therefore wasted effort; the height is the whole precision of this run**
(CLAUDE.md D4). Measuring it instead of correcting for it is what the ladder
above buys, and it is why Sequence A comes first (D10).

**The grid tests the model's actual claim.** `9a/(16h)` asserts the correction is
a function of `a/h` alone. Running the ladder at more than one size overlaps
`a/h` from two directions, so sizes x heights is not a product of two sweeps but
**one curve measured twice** — and a disagreement between the two is the
truncation error of the first-order series, which `sample/aberration.py` already
declares as its own limit.

**The wall-drag ledger entry changes, and the operator's addition is what
changes it.**
[2026-09-11](../decisions/2026-09-11-wall-drag-reaches-the-bias-ledger.md) admits
`geometry.wall_drag.trapped` to CORRECTIONS only where gamma comes *out* of a
fit, and warns that the claim is false where gamma goes *in* as `6*pi*eta*a`.
The first draft of this plan was the false case and said so. **With the height
ladder, gamma comes out of the fit** — `gamma_bulk` and `h0` are the two fitted
parameters — so the declaration is now true, for this run, on this bias, and for
exactly the stated reason. ⚠ It is true only for the **parallel** correction and
only inside the ladder's 3-10 µm span; extrapolating either way re-opens it.

### What Brownian dynamics answered, and the three decisions it hands back

This plan was sent to the simulation agent as a question, not as numbers, and its
answer landed at
[`kb/external/bd/trap-stiffness-recovery.r2`](../external/bd/trap-stiffness-recovery.r2.md)
— `evidence_class: simulated`, `may_be_gate_threshold: false`. **Nothing below is
a gate threshold here.** Each item is a design motivation and, where the two
repositories disagree about a convention, a decision this plan leaves to the
operator rather than settling by itself.

It **refused the headline question**: BD has no wall and one height, so it makes
no claim about `h0`, about the Faxén separation, or about per-bead error bars.
The `±0.195 µm` in §Error budget therefore remains **this repository's own toy
estimate, uncorroborated** — the round did not verify it, and BD returned it
unverified rather than endorsing it.

**D-1 · The sampling convention differs by exactly 2π, and that is a decision.**

| convention | requirement at a = 4.95 µm | 520 fps against it |
|---|---|---|
| this instrument, **G14** (`trapping/checks.py` `check_sampling`, `f_s >= 10 f_c`) | **99 Hz** | passes by **5.3×** |
| BD's, `10/tau_k` (i.e. `10 f_c * 2*pi`) | **620 Hz** | **16 % short** (8.39 samples per `tau_k`) |

`f_c = 1/(2*pi*tau_k)`, so the two rules are the same rule with and without the
`2*pi` — neither is wrong and they are not interchangeable. G14 asks the corner
frequency to be resolved; the BD convention asks the *relaxation* to be sampled
ten times. **Which one governs this run is the operator's call**, and
`REQUIRED_SAMPLING_RATIO = 10.0` is not edited here: a constant in that table is
a claim about every future experiment. If the BD convention is chosen, 620 fps
needs the ROI height cut further, and lenses 2 and 3 are re-run together (E5).

**D-2 · The localisation budget is already spent at the assumed epsilon, and it
is a bias.** BD puts a **hard** ceiling at `epsilon <= 7.6 nm`, from
`(epsilon/l_k)^2 <= 0.05` at `l_k = 33.98 nm`. The assumed 10 nm here is above
that and is worth ~8 % on `alpha` — and because it is a **bias, not a variance**,
it does not average down over rungs or segments, which is the direction §Error
budget's "cancels only if epsilon is size-independent" was already pointing.
**Proposal, for the operator: promote P8's epsilon from a correction to a hard
precondition** — the run does not start until the stuck bead's centroid variance
is measured and is at or under the ceiling the analysis needs. Not done
unilaterally: a hard gate keyed to an imported number would be exactly the
`may_be_gate_threshold` violation the entry forbids. What is recorded here is the
proposal and its basis.

**D-3 · 5 s per rung is short of the point where the simulated precision was
demonstrated.** `T_obs/tau_k` is **310** at 5 s against the **2000** at which BD
measured `f_c` to +1.17 % — **6.4× short** — while clearing BD's own soft floor
of 100. BD's soft requirement is `T_obs >= 32.3 s` per rung. The cost of buying
it is the reason this is a decision and not an edit: 5 s → 32.3 s is paid at
**every rung of every size**, six rungs and (P0) at least three sizes, so it is
~8 min of held bead per size before drive segments, against a drift witness
(P10) that has to hold for all of it. Cheaper alternatives to weigh first:
accept the shorter `T_obs` and inflate the stated error on the equipartition
`alpha`, or take `f_c` from the drive-on blocks of step 9b instead of only 9c.

**D-4 · The simulated error bar is not comparable to a single bead.** BD's
1.17 % is an **ensemble of 1000 replicas**; one bead at the same `T_obs/tau_k`
scatters about **32×** more. Any comparison between this run's per-rung scatter
and that figure is invalid as stated — the entry says so about its own result.
Recorded here so the number is not read as a target this run has already met.

**What did transfer.** The regimes are different systems and that is the point:
`k*` 60 358 there against 21 221 here, `l_k/d` 0.004070 against 0.006865 — BD's
case is stiffer with a smaller fluctuation relative to the bead, i.e. the
*harder* measurement, so `f_c` recoverability transfers in the favourable
direction. `tau_p/tau_k` is 8.14e-4 there and 7.30e-5 here, both far under 1e-2:
**overdamped is genuinely shared**, not assumed to be.

## Committee verdict

Computational lenses first, judgment lenses fed their numbers (CLAUDE.md §3).

| Lens | Verdict | Deciding gate | m | Evidence |
|---|---|---|---|---|
| 1 optics | not convened | — | — | — |
| 2 detection | PASS (inherited) | frame_rate | 1.00 | assumed — DynamicRange row time is a datasheet value |
| 3 compute | PASS_WITH_CHANGES (inherited) | data_rate 136 MB/s | 1.06 | assumed — no achieved rate measured |
| 4 sample | not convened | — | — | — |
| 5 photo | not convened | — | — | — |
| 6 validity | not convened | — | — | — |
| 7 trapping | FAIL at 50 fps, PASS at 520 fps for d >= 2.6 µm | `sampling.aliased` (G14c) | 0.04 at 50 fps | assumed — dial -> mW placeholder, temperature 293.15 K default |
| 8 mechanical | **must be convened** — see below | z drift against the ladder | — | — |

**Not evaluated.** Every entry above marked "not convened" is `unevaluated`, not
cleared (CLAUDE.md §3), and each is a hole in this plan:

- **Lens 1 (optics) and lens 5 (photo)** were not convened. They must be, and
  **together with each other and with lens 2** — light for SNR and the dose
  budget run in opposite directions (E5, E6).
- **Lens 4 (sample)** was not convened, and it owns the two numbers this run
  turns on: the working depth against the RI-mismatch limit (~10 µm for an oil
  objective) and the Faxen wall-drag bias. Convene it with lens 1 (E6).
- **Lens 6 (validity)** was not convened, and it must run **alone and last**
  (E2). It owns the settings-versus-analysis mismatch in §Analysis.
- **Lens 8 (mechanical) must now be convened, and the wall measurement is why.**
  It was an absence in the first draft on duration grounds (~60 s per size, far
  under ~30 min). **The height ladder removes that argument**: z drift is no
  longer a long-run nuisance, it moves the measurand. 0.5 µm of drift at h = 8 µm
  is 2.7 % on gamma, which is the per-point error budget in its entirety.
  Convene it, and hand it the ladder — not the duration. Sedimentation is
  separately real: polystyrene is 1.05 g/cm3 and sinks
  (`data/particles.yaml > materials`).
- **Lens 7's silence on trap heating is not heating cleared** (E3). Over 1 W of
  1064 nm reaches the sample plane at dial 80 % through the 20x (SAFETY §1).
- Lenses 2 and 3 are **inherited** from the 2026-09-10 envelope, computed for
  the 4.95 µm bead. They are re-run per size, not assumed, once P0 fixes the
  list.

## Preconditions

Checked before anything moves. Each refuses the run on its own.

- [ ] **P0 · The list of particle sizes actually on the shelf**, with vendor,
      catalogue number and lot. Two sizes spanning 1.24x cannot resolve `1/a`;
      a >=3x span is the minimum and >=5x is what the run wants. — *checked by:*
      operator, and a new entry per product in `data/particles.yaml`
- [ ] **P1 · Trap height h above the coverslip, set and recorded**, identical for
      every size. Dominant systematic, and currently listed as an open safety
      question (SAFETY §9). — *checked by:* Sequence A
- [ ] **P2 · Laser dial %, written down**, and held across every size. The
      2026-09-03 alpha = 3.65-4.5 pN/µm is unusable against the model because
      the dial was never recorded and is unrecoverable
      ([2026-09-10](../decisions/2026-09-10-lens-7-measured-stiffness-and-numbering.md) §1).
      — *checked by:* a written note, per run; nothing in software reads it
- [ ] **P3 · Sample temperature, measured**, not the 293.15 K default. 2.4 %/K on
      eta. — *checked by:* thermometer at the sample
- [ ] **P4 · One frame-photometry frame per size**, despeckle OFF, per the
      9-step recipe in `kb/calibrations/frame-photometry.yaml`. Only the three
      5 µm entries exist today; without it G6/G7 cannot be satisfied for a new
      size. — *checked by:* `python -m detection.cli from-frame`
- [ ] **P5 · Tweezers calibration verified at the 100x**, if the nosepiece has
      moved since the last verification. Both Tweez calibrations are
      objective-dependent and neither is readable over TCP. — *checked by:*
      commanding ±10.000 µm and measuring it in camera data
- [ ] **P6 · The sample is dilute enough that one particle is isolated in the
      ROI.** Six near-identical blobs in one field produced six plausible and
      wrong fits on 2026-09-03. — *checked by:* a live frame before the run
      closes the viewer
- [ ] **P8 · A bead stuck to the coverslip, in or beside the ROI**, imaged at the
      identical exposure, light level and mode. It serves three purposes and the
      run needs all three: the **z datum** for `dz_piezo`, the **localisation
      noise epsilon** that `var(x)` must be corrected by, and the **drift
      witness** of P10. The 2026-09-03 session already used a chamber-stuck
      particle as a piezo ruler. — *checked by:* its centroid variance at zero
      drive, which is epsilon^2
      ⚠ **Proposed for promotion to a hard stop** — see D-2 above: at the assumed
      10 nm the localisation budget is already spent, and it is a bias that no
      amount of averaging removes. Still written as a correction here because the
      ceiling that motivates it (7.6 nm) is an **imported simulated** number and
      may not be a gate threshold. Operator's decision.
- [ ] **P9 · PFS state decided and recorded, and it is OFF during the ladder.**
      PFS servoing fights the piezo z, and `PFSOffset` is **the one remaining
      unmeasured sign convention on a collision device** (SAFETY §2) — it is
      still `0` = unknown in the configs on purpose. Do not write it.
      — *checked by:* the property read, logged before the ladder starts
- [ ] **P10 · A drift witness running for the whole ladder.** `config/session/focus_monitor.py`
      against the stuck bead of P8. Without it a monotonic z drift is
      indistinguishable from the Faxen curve the run exists to measure.
      — *checked by:* the witness trace, per height
- [ ] **P7 · The x_eq(v) slope fit exists before acquiring.** `alpha = gamma*v/x_eq`
      is implemented nowhere, and `creepx` detrends the mean displacement away by
      design — see §Analysis. — *checked by:* running the fit on the 2026-09-03
      drag data first

## Sequence

[SAFETY §8](../../SAFETY.md) is the standing setup order and is not repeated
here. Objective choice at load time is a safety decision outside the imaging
hierarchy (E7): **load at 4x or 10x.**

| # | Subsystem | Action | Flag required | Confirmed by |
|---:|---|---|---|---|
| 1 | piezo | centre all three axes at mid-travel, ramped (100 steps over ~1 s), **before any bead is trapped** | `--unlock` | position readback from the controller, which has one; a bare 300 µm step rings the loop |
| 2 | microscope | open both turret shutters; `CSUW1-Bright` = Bright Field, `CSUW1-Port` = red_only, `LaserLine` = AllOff | `--allow-motion` for the nosepiece only | a non-black live frame |
| 3 | microscope | Tweez GUI takes a camera, GUI calibration + trap placement, then **release**; then Micro-Manager loads its configuration | — | the GUI shows the calibrated field; MM then opens the body without a 10012 |
| 4 | tweezers | verify calibration: command ±10.000 µm and measure it | `--allow-laser`, armed at the GUI | the bead's excursion in camera data, in µm (9.9672 / 10.0852 on 2026-09-03) |
| 5 | tweezers | trap one bead; record **which named trap** holds it | `--allow-laser` | the bead visibly held, by eye in the GUI |
| 6 | piezo | **Sequence A — set h.** Find the coverslip surface, then retract the sample by the chosen h in ramped steps; wait out the ~0.9 µm creep | `--unlock` | z readback plus the bead's focus; h recorded in the run log |
| 7 | microscope | frame-photometry frame for this size, despeckle OFF | — | peak ADU mid-range and under the 95 % ceiling; `from-frame` refuses a clipped peak |
| 8 | microscope | **close the live view** | — | the viewer process is gone; leaving it up degrades timing ~20x (2.93 -> 51.4 ms) |
| 9 | microscope | record the stuck bead of P8 at **zero drive**, 5 s, same settings: this is epsilon and the z datum | — | its centroid variance, which is epsilon^2 — a number, not an assumption |
| 9a | piezo + microscope | **Sequence B, per height.** Set `dz_piezo` for this rung (ladder order **far -> near**: 10, 8, 6, 4.5, 3.5, 3.0 µm), ramped, then wait out the ~0.9 µm creep | `--unlock` | z readback plus the stuck bead's focus; the drift witness of P10 still running |
| 9b | piezo + microscope | per velocity at this height: triangle wave ±10 µm at v, 3 segments x 5 s, camera on one clock; discard 3.5/(2*pi*f_c) after each reversal (56 ms at 4.95 µm) | `--unlock`, `--arm` | per-frame timestamps in the acquisition, and the bead sitting off-trap-centre by the predicted x_eq |
| 9c | — | at the same height, with the drive **stopped**, 5 s of the held bead: this is `var(x)` for the equipartition alpha | — | the residual variance, and a Lorentzian `f_c` from the same block agreeing with `1/(2*pi*slope)` |
| 10 | piezo | close every waveform with a final sample at the centre | `--unlock` | centre position read back; without this the axis parks ~1.5 µm low and it compounds run to run |
| 11 | microscope | run report: achieved rate from the span over n-1 `ElapsedTime-ms` intervals, dropped frames by `ImageNumber` gaps on both detectors, `contaminated` | — | the numbers in the report; a requested rate is not evidence (G12b) |
| 12 | — | repeat 9a-9c for the next rung of the ladder | `--unlock` | the rung's own `dz_piezo` readback |
| 13 | — | repeat 5-12 for the next size, **same dial**, same ladder | — | the dial re-read from the written log and unchanged |

**A return code is not a confirmation** (SAFETY §0): on the tweezers six wrong
states and success are the same byte, and the confirmation column above is
observation in every row.

## Stop conditions

- **Achieved frame rate materially below 520 fps.** Then every row of the
  envelope table is a ceiling and not a rate, and the sampling floor is what is
  at risk. Stop, keep the data, re-derive the rate from timestamps.
  *State left:* trap armed, bead held, piezo at centre, light down.
- **The bead escapes the trap**, or x_eq exceeds ~0.3a (non-linear). Stop that
  velocity, do not raise the power to compensate: the power is the common axis
  of the whole series. *State left:* piezo returned to centre, trap left armed,
  light down.
- **h cannot be established** (P1 fails). Stop before Sequence B. A size series
  without a common, known h measures the wall, not the trap.
  *State left:* sample retracted, trap armed, piezo at centre.
- **The bead touches or sticks to the coverslip** on the near rungs — it stops
  following the drive, or its variance collapses. Stop the ladder at the last
  clean rung; do not push h lower to recover it. A stuck probe is a lost bead and
  a contaminated field. *State left:* piezo ramped back to the far rung, trap
  armed, light down.
- **The drift witness (P10) shows z moving by more than ~0.3 µm within a rung.**
  The Faxen curve and a monotonic drift have the same shape, so this invalidates
  the rung rather than degrading it. Stop, re-datum against the stuck bead,
  repeat that rung. *State left:* unchanged, drive stopped at centre.
- **PFS reads `In Range` when a nosepiece rotation is wanted.** Refuse. `Out of
  Range` authorises nothing either — it can veto, never permit.
  *State left:* untouched.
- **Any abort:** the laser may stay armed and both turret shutters stay open —
  the trap is the expensive thing to re-establish (operator instruction,
  2026-09-03). Never send `TRAP_OFF`/`LASER_OFF` or close `Turret2Shutter` to
  tidy up. Do not force-kill a script holding light unless a trap depends on the
  shutters staying open, in which case force-kill is the safer path because it
  skips the cleanup.

## Analysis

- **`alpha = gamma*v/x_eq` is implemented nowhere.**
  [microrheology-standard-conditions](../expertise/microrheology-standard-conditions.md)
  names it as the third of the three stiffness routes and records that the
  `creepx` pipeline **detrends the mean displacement away by design** — so the
  existing analysis discards exactly this run's signal. Three pieces to write
  before acquiring (D9): plateau extraction, the `x_eq(v)` slope fit, and an
  equipartition `alpha = kT/var(x)` on the residuals of the same data as an
  independent cross-check.
- **`D:\codes` hardcodes `px_to_um = 0.065`** in every MATLAB file, 0.73 % from
  the recorded 0.06453, and `alpha ∝ 1/pixel_size` propagates it. Not this
  repository's file to edit; lens 6 owns settings-versus-analysis mismatches.
- **The wall fit is a second thing to write:** `gamma(dz) = gamma_0/(1 - 9a/(16(dz+h0)))`
  by least squares over the rungs, with `gamma` at each rung formed as
  `slope x alpha_equipartition` and `alpha` corrected for epsilon (P8) and for
  the `2*D*t_exp/3` blur term. Report `gamma_0`, `h0`, and the residuals against
  the first-order series — the residuals are where the truncation shows up.
- **Identifying the trapped bead:** brightness does not do it. The trapped bead
  is the only object that does not translate with the stage — and this run
  translates the stage, so the discriminator is free here.
