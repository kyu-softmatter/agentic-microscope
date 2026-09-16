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

| h | s | gamma/gamma_0 | Faxen | v µm/s | f_c Hz | needs fps | blur on var(x), `u/3` |
|---|---|---|---|---|---|---|---|
| 3.0 µm | 0.464 | 1.866 | +86.6 % | 14.9 | 6.4 | 64 | 0.60 % |
| 3.5 | 0.398 | 1.660 | +66.0 % | 16.8 | 7.2 | 72 | 0.68 % |
| 4.5 | 0.309 | 1.448 | +44.8 % | 19.2 | 8.2 | 82 | 0.78 % |
| 6.0 | 0.232 | 1.302 | +30.2 % | 21.4 | 9.2 | 92 | 0.87 % |
| 8.0 | 0.174 | 1.211 | +21.1 % | 23.0 | 9.9 | 99 | 0.93 % |
| 10.0 | 0.139 | 1.162 | +16.2 % | 24.0 | 10.3 | 103 | 0.97 % |

⚠ **The blur column was exactly twice too large until 2026-09-15, and the error
started here.** This plan and r1 of the bridge thread both quoted
`2*D*t_exp/3`, which is the **free-particle MSD** term. For a bead *in a trap*
the exposure-averaged variance is exact and different:
`var_blur/var = 2(u - 1 + e^-u)/u^2 -> 1 - u/3` with `u = t_exp/tau_k`. Checked
against exact-OU boxcar averaging at five values of `u` from 0.028 to 3, the
exact form holds within 3.3 sigma and `2u/3` is rejected at 16 to 358 sigma
→ [`trap-stiffness-recovery.r4`](../external/bd/trap-stiffness-recovery.r4.md)
§2. Every row above is now half what it was (0.60 → 0.97 %, was 1.21 → 1.94 %).
**No gate ever checked this number** — it was prose arithmetic in a plan, which
is why it survived two rounds.

- **Lever arm: 1.43x in gamma** between h = 3.5 and 10 µm, against a per-point
  statistical error of **~3 % that is this repository's own unverified estimate**
  — 400 numpy realisations, passed through r2 as `sigma_gamma_per_rung` and
  returned explicitly *not* corroborated (r2 `gaps[2]`). The 14-sigma-from-flat
  claim below rests entirely on it, so it is an assumption and not a result.
  ⚠ What *has* now been measured is the neighbouring estimator: one bead's
  **fitted `f_c` scatters 29.1 ± 0.9 %** at the planned 5 s per rung, falling to
  **9.2 ± 0.3 %** at 32.3 s (r4 `requirements[0]`). That is the PSD route, not
  the drag slope, and the two must not be conflated — but the per-rung `gamma`
  is formed as `slope x alpha_equipartition` (§Analysis), so it inherits
  whatever `kT/var(x)` does on the same 5 s block, and **nobody has measured
  that.** See D-3.
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
unbiased. So this run's by-product would be **the absolute trapping height**,
which [SAFETY §9](../../SAFETY.md) lists as an open safety question and calls
the quantity that dominates alpha.

⚠ **That by-product does not survive D-7, and the fit is not what failed.**
Independently propagated over 4000 ladders per sigma, the fit returns `h0` to
0.131 µm at 3 % per rung — so the ±0.195 µm above was *conservative for the
scatter it assumed*. The tolerance is **4.48 %**; the route that measures
`gamma` delivers **7.2–9.5 %**; at that scatter `h0` comes back to
**0.433–0.450 µm**, which trips the ~0.4 µm criterion r1 registered in round
one. **Read D-7 before planning around a fitted `h0`** — and note that the
numbers above are still the right *shape*: they were computed against an
assumption about the input, and the assumption is what was wrong.

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

### What Brownian dynamics answered, what it corrected, and what is still ours

> **If you read one item, read D-7.** The height ladder's fitted `h0` does not
> survive the scatter the measurement actually delivers, by the criterion this
> plan's own first ask registered in round one. The rest of the run — `alpha(a)`
> from the drag slope at fixed height — is not affected by it.

This plan was sent to the simulation agent as a question, not as numbers, over
three rounds. The answers landed at
[`r2`](../external/bd/trap-stiffness-recovery.r2.md) ·
[`r4`](../external/bd/trap-stiffness-recovery.r4.md) ·
[`r5`](../external/bd/trap-stiffness-recovery.r5.md) ·
[`r8`](../external/bd/trap-stiffness-recovery.r8.md) — all four
`evidence_class: simulated`, `may_be_gate_threshold: false`. **Nothing below is
a gate threshold here.** Each item is a design motivation and, where the two
repositories disagreed, either a decision left to the operator or — twice now —
a number one side had to withdraw.

**Read them in order r4, r5, then r2.** r2 is the oldest and two of its numbers
are wrong; it is kept because this plan cites it, and it carries a
`corrected_by` link at the top rather than an edited body.

It **refused the headline question**: BD has no wall and one height, so it makes
no claim about `h0`, about the Faxén separation, or about per-bead error bars.
The `±0.195 µm` in §Error budget therefore remains **this repository's own toy
estimate, uncorroborated** — the round did not verify it, and BD returned it
unverified rather than endorsing it.

⚠ **r2 has since been corrected, by r4, and one of the two wrong numbers was
ours.** Read [`trap-stiffness-recovery.r4`](../external/bd/trap-stiffness-recovery.r4.md)
before this section, not after: the r2 entry it supersedes is kept only because
this plan cites it. Both corrections were settled on **exact
Ornstein-Uhlenbeck data, whose `f_c` is known in closed form** — no simulation
run, so no integration error is mixed into the verdict.

- **`f_c` recoverable to +1.17 % is withdrawn and NOT replaced.** Exact OU fed
  through the archived run's own estimator returns +0.8 to +1.2 %: the
  simulation reproduced the *estimator*, and the estimator was read as physics.
  It is a bias — `T_obs x 26` does not remove it. **How well `f_c` can be
  recovered is not known** until the fit is fixed, and r4 offers no number in
  its place. Every sentence below that used to lean on 1.17 % now leans on a
  direct scatter measurement instead.
- **The `2*D*t_exp/3` blur term was ours, and it was twice too large** — see the
  ladder table. `u/3` is the trapped-bead coefficient.

**D-1 · The sampling convention differs by exactly 2π — and it is no longer a
decision, because the convention is not what binds.**

| convention | requirement at a = 4.95 µm | 520 fps against it |
|---|---|---|
| this instrument, **G14** (`trapping/checks.py` `check_sampling`, `f_s >= 10 f_c`) | **99 Hz** | passes by **5.3×** |
| BD's, `10/tau_k` (i.e. `10 f_c * 2*pi`) | **620 Hz** | **16 % short** (8.39 samples per `tau_k`) |

`f_c = 1/(2*pi*tau_k)`, so the two rules are the same rule with and without the
`2*pi`. Neither is wrong, and **r4 settled which one matters by measuring
instead of arguing**: turning the camera model on and off at 5 s per rung moves
one bead's `f_c` scatter from **28.5 % to 29.1 %** — about 2 % relative — while
`T_obs` moves it by a factor of **3.2**.

**r5 then closed it from the other side: BD withdrew its own 620 Hz in favour of
this instrument's 99 Hz**, because the `tau_k/10` convention does not bind at
this envelope
→ [`trap-stiffness-recovery.r5`](../external/bd/trap-stiffness-recovery.r5.md).
So there is **nothing left to decide here**: 520 fps stands, the ROI height is
not cut, and lenses 2 and 3 are not re-run for this reason.

⚠ **This is not corroboration of G14.** The 99 Hz is our own gate's number
coming home — the r5 entry marks it `round_trip` for exactly that reason — and a
number that returns is not a second measurement of itself. What the round
actually established is the *ranking* (observation length ≫ sampling rate), not
the threshold. `REQUIRED_SAMPLING_RATIO = 10.0` is therefore still not edited,
in either direction.

**D-2 · The localisation budget is already spent at the assumed epsilon, and it
is a bias.** BD puts a **hard** ceiling at `epsilon <= 7.6 nm`, from
`(epsilon/l_k)^2 <= 0.05` at `l_k = 33.98 nm`. **r4 leaves this one standing
unchanged**: it is analytic, and depends on neither of the withdrawn numbers.
The assumed 10 nm here is above that and is worth ~8 % on `alpha` — and because
it is a **bias, not a variance**, it does not average down over rungs or
segments, which is the direction §Error budget's "cancels only if epsilon is
size-independent" was already pointing. The blur fix moves the *net* camera
effect on `alpha` from ~8.0 % to **~7.7 %**: still epsilon-dominated, so the
ceiling does not move and this is the half of the camera budget that matters.

**r8 gives the ceiling a second, independent reason — and moves what it
threatens.** Measured there, the camera contributes **−4.8 to −6.9 % of bias on
`gamma` per rung** (camera off: −0.1 to +2.6 %), entirely through `alpha`
inheriting the 8.66 % variance inflation. But `h0` is set by the **shape** of
`gamma(h)`, so a bias common to every rung **cancels out of it**: with the
camera on, `h0` moves by nothing resolvable (1.106 against 1.136 at
`h0_true = 1.0`, both ±0.03), while `gamma_0` moves by **−4.65 %**. So
`epsilon` is a **`gamma_bulk` problem, not a trapping-height problem** — it puts
the absolute drag about 5 % out and leaves the ladder's geometry alone. That
sharpens P8 rather than softening it: `gamma_bulk` is what `alpha(a)` is
normalised by, which is this run's actual question.
**Proposal, for the operator: promote P8's epsilon from a correction to a hard
precondition** — the run does not start until the stuck bead's centroid variance
is measured and is at or under the ceiling the analysis needs. Not done
unilaterally: a hard gate keyed to an imported number would be exactly the
`may_be_gate_threshold` violation the entry forbids. What is recorded here is the
proposal and its basis.

**D-3 · 5 s per rung is thin, and the number that says so is now a measurement
rather than a comparison.** The original form of this item — "`T_obs/tau_k` is
310 against the 2000 at which BD measured `f_c` to +1.17 %, 6.4× short" — was
**arithmetic against a number that measured nothing**, and r4 voids it. The
requirement survives at the *same value* on a stronger basis: `T_obs >= 32.3 s`,
because the per-realisation scatter of one bead's fitted `f_c`, with exposure
and localisation noise applied, is

| `T_obs` per rung | `T_obs/tau_k` | one bead's `f_c` scatter |
|---|---|---|
| **5 s**, as planned | 310 | **29.1 ± 0.9 %** |
| **32.3 s** | 2001 | **9.2 ± 0.3 %** |

a factor of 3.2 for a factor of 6.5 in time. **Weigh the cost against that, not
against 1.17 %.** The cost is unchanged and is why this is a decision and not an
edit: 5 s → 32.3 s is paid at **every rung of every size**, six rungs and (P0)
at least three sizes — ~8 min of held bead per size before drive segments,
against a drift witness (P10) that has to hold for all of it, and drift is the
one nuisance that has the same shape as the measurand.

⚠ **And buying it does not reach 3 % anyway** (r5). Scatter goes as
`1/sqrt(T_obs)`, so 3 % from observation length alone needs about
`(9.2/3)^2 x 32.3 s ≈ 300 s per rung` — thirty minutes of held bead per size,
which the cost argument above rules out by a wide margin, and which would put
lens 8 back in play on duration grounds as well as on the ladder. **So the
decision is not "5 s or 32.3 s".** See D-5.

Two things to settle before paying it, in this order. **First, fix the
estimator** (§Analysis): the 29.1 % was measured through an unweighted fit over
the whole band, the same fit that produced the withdrawn +1.17 %, so part of
that scatter may be the fit rather than the window — and an analysis change
costs no instrument time. **Second, note what this figure is and is not**: it is
the PSD route on the 9c block. The per-rung `gamma` is `slope x
alpha_equipartition`, and `kT/var(x)` on the same block has never been measured
by either side. Cheaper alternatives still worth weighing: take `f_c` from the
drive-on blocks of 9b as well as 9c, or accept a shorter `T_obs` and inflate the
stated error — but not until the estimator question is closed, because right now
it is not known which of the two is being bought.

**D-4 · The simulated error bar is not comparable to a single bead — and the
ratio r2 gave for that was wrong too.** r2 said one bead scatters about **32×**
more, i.e. `sqrt(1000)`. r4 measured **21.1×** at `T_obs/tau_k = 2000` and
**15.5×** at 310: `f_c` is fitted to the `min(250, N)` subset rather than to all
1000 particles, and averaging spectra before a non-linear fit is not averaging
fits, so it was never a `sqrt(n)` law. **The ratio was the wrong thing to
carry** — the absolute figures are the ones in D-3, 9.2 % per bead at 2000 and
29.1 % at 310. Recorded so that no ensemble number is read as a target this run
has already met.

**D-5 · Where per-rung precision comes from is now the open design question,
and it replaces the one this plan was asking.** r5 answered the question this
repository sent in r3 — *how much does one bead's fitted `f_c` scatter at this
envelope, with the camera in the model?* — with **29.1 ± 0.9 %** over 512
single-bead realisations, against the `<= 3 %` that was hypothesised.

**The hypothesis split cleanly: the mechanism was right and the number was out
by about 10×.** Observation length binds and the sampling convention does not —
that part held. What did not hold is the premise underneath the whole error
budget, that ~3 % per rung is *available*. With D-3's 300 s ruled out, it is
not, from this route.

Two candidates remain, and **BD can simulate neither without a wall runner**, so
this one does not come back from the bridge:

- **More beads per rung.** Independent beads average as `1/sqrt(n)`, so ~10
  beads per rung would reach 9 % at 32.3 s, or ~95 at 5 s. That is a different
  run — P6 currently *enforces* one isolated bead per ROI precisely because six
  blobs in one field produced six plausible and wrong fits on 2026-09-03 — and
  it trades the isolation the run relies on for statistics.
- **`gamma` from the drag slope rather than from `f_c`.** This is already this
  plan's **primary** route (`alpha = gamma*v/x_eq`, §Analysis), with the
  equipartition/PSD block as the cross-check. r5's 29.1 % is about the
  *cross-check*, not about the primary route.
  ⚠ **Superseded in part by D-7**: r8 decomposed the primary route's per-rung
  error, and **it is not where this section guessed.** Of the 7.2–9.5 % total,
  the **equipartition `alpha = kT/var(x)` contributes 7.3–9.5 %** and the
  **drag slope only 1.3–1.6 %**. So the slope is not the weak half and
  lengthening the drive segments buys little; the **variance estimate** is the
  problem, and it is bounded by `T_obs/tau_k`, which this plan sets to 201–323.
  Leaning on the slope does not escape it, because §Analysis forms `gamma` per
  rung as `slope x alpha_equipartition` — the `alpha` is *inside* the primary
  route, not beside it. What is left to change is the variance estimate itself:
  more beads per rung, a longer 9c block, or an estimator that does better than
  `kT/var(x)` on a short record.

**So the honest next step is on this side, not the simulator's:** measure what
the drag slope actually returns per rung, on the 2026-09-03 data, before buying
any more observation time (P7 already requires that fit to exist before
acquiring — this makes it load-bearing rather than tidy). Nothing above changes
a gate, and none of these numbers may become one: they are `simulated` and the
entries carry `may_be_gate_threshold: false`.

**D-6 · `h0` is not waiting on a wall runner. No runner can answer it, and that
is a property of the question.** Five rounds have recorded the wall as a
*missing capability* on the simulation side — "still no runner". Checked here,
the limitation is stronger than that and does not expire:

At a **fixed** height the wall's entire effect is a scalar multiplier on
`gamma`. The dimensionless group that governs a trapped bead is
`k* = k_t d^2 / kT`, which carries `k_t`, `d` and `kT` and **no drag at all** —
21219 at our numbers, agreeing with the 21221 in r2's own regime table to
0.01 %. Since `gamma` enters only through `tau_k = gamma/k_t`, and `tau_k` is
the unit time, **all six rungs of the ladder are the same dimensionless run**.
Faxén lives entirely in the back-transform out of those units. A simulation
therefore cannot *learn* the wall: whatever wall factor it reports is the one
that was put in.

What a simulation **can** still do is the thing r1 asked for as a fallback and
never got: **test the fit procedure** on a synthetic `gamma(h)` ladder with
realistic per-rung noise. That is an estimator question, not a physics one, and
it is exactly what would replace the unverified ±0.195 µm in §Error budget. So
the outstanding request to the other side is a *fit test*, not a wall.

⚠ **And this repository wrote that fallback down in round 1, then spent four
rounds asking for the wall instead.** r1's `wall_drag` assumption says
verbatim: *"If BD cannot put a wall in, it can still test the FIT PROCEDURE on a
synthetic gamma(h) — say so rather than reporting a number from an infinite
medium."* The answer was in the first document this side sent. Nothing read it
back — the `assumptions[]` block was treated as a declaration to be filed rather
than a list to be re-read each round, and the cost was four rounds of asking for
something no runner could ever deliver. **Re-read your own assumptions block
before writing the next ask**; it is the only part of these documents that
carries what no number reveals, which is exactly why it is where an answer can
sit unnoticed.

⚠ **Derived here, from the definition of `k*` — and independently confirmed by
the other side.** When this paragraph was written the other side's identical
conclusion had only been relayed in conversation, which is not a source (09 §7),
so it was written as this repository's own arithmetic and said so. It has since
crossed properly: r8's `gaps[0]` is `kind: not_buildable_here`, `owner: nobody`
— *"No simulation on this side will ever measure a wall factor it was not
given"*
→ [`trap-stiffness-recovery.r8`](../external/bd/trap-stiffness-recovery.r8.md).
Two independent derivations of the same structural fact, which is stronger than
either. Cite this paragraph for the arithmetic and the import for their half.

**D-7 · The ladder fit tolerates 4.48 % per rung, the route that measures
`gamma` delivers 7.2–9.5 %, and r1's own falsifier has fired.**
→ [`trap-stiffness-recovery.r8`](../external/bd/trap-stiffness-recovery.r8.md).
Read this item before the two numbers, because taken alone the first one reads
as good news:

| | value | what it is |
|---|---|---|
| `sigma_gamma_max` | **4.48 %** | the tolerance — above it the six-rung fit stops returning `h0` to ±0.2 µm. A property **of the fit**, from 4000 ladders per sigma |
| the route's per-rung scatter | **7.2–9.5 %** | what measuring `gamma` at these settings delivers. **1.8× the tolerance** |
| forward fit at that scatter | **0.433–0.450 µm** on `h0` | stable across injected `h0` of 0.5, 1.0 and 2.0 µm |

So the claim r7 sent — that the tolerance is at or above the 3 % this budget
assumes — came back **confirmed with room**, and at 3 % the fit returns `h0` to
**0.131 µm**. §Error budget's ±0.195 µm was therefore *conservative given its
own assumption*: **the fit was never the problem, the input was.**

**r1 pre-registered the decision in round one**, and this is the first round that
could evaluate it: *"if its scatter exceeds ~0.4 µm once finite `T_obs`, motion
blur and localisation noise are included, then the ladder does not produce a
trapping height and the run should be redesigned around a direct z datum
instead."* 0.433–0.450 µm, with exactly those three included. **The criterion
fails.**

⚠ **It fails on a simulated input, and that distinction decides what happens
next.** r8 says so about its own result: the 1.8×-over-tolerance finding rests
on a *simulated* per-rung error, while the 4.48 % does not — the tolerance is a
property of the fit, and it is **the number P7's measurement on real data gets
compared against**. So this is the strongest evidence available and it is not a
measurement of this instrument. `may_be_gate_threshold: false` is not a
formality here: 4.48 % is a **design target**, not a check, and nothing in
`trapping/` has been changed to know about it.

**What follows, in order.**

1. **Start the redesign around a direct z datum now**, rather than after P7.
   It is r1's own pre-registered response, the evidence for needing it is as
   good as simulation gets, and the alternative is discovering it with the laser
   armed. What a direct z datum means on this bench is not settled and is the
   next design question — the stuck bead of P8 is already a z reference for
   `dz_piezo`, so the question is whether it can be made an *absolute* one.
2. **P7 still decides**, and it is still blocked on a data transfer (the
   2026-09-03 run is on the instrument PC). It is now worth more than before:
   it is the one number that converts this from a warning into a verdict.
3. **Do not declare the ladder dead in the KB.** Nothing here measured this
   instrument, and `unevaluated` is not `cleared` in either direction.

**And the six heights are not necessarily the right six** (r8 `gaps[2]`). The
4.48 % is for *this* ladder, and a different spacing would plausibly move it
**upward**: the near rungs carry the most Faxén signal and currently get the
least statistics — `T_obs/tau_k` is **201 at h = 3.0** against **323 at
h = 10**. Re-weighting the ladder is seconds of work on the other side and is
worth asking for once P7 says what scatter is actually achievable.

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
- [ ] **P7 · The x_eq(v) slope fit exists before acquiring**, *and returns its own
      per-rung scatter.* `alpha = gamma*v/x_eq` is implemented nowhere, and
      `creepx` detrends the mean displacement away by design — see §Analysis.
      ⚠ **This is now load-bearing rather than tidy** (D-5): the ~3 % per-rung
      error the whole error budget rests on is an unverified numpy figure, and
      the neighbouring route's measured scatter is 29.1 % at the planned 5 s. The
      fit on existing data is what says which regime this run is actually in, and
      it costs no instrument time. — *checked by:* `python -m calibration.cli
      drag-slope <tracked-positions> --settle-s 0.056`, and the
      `kb/calibrations/` entry it writes

      **The procedure, because this is the cheapest decisive step in the run.**

      1. **Find the tracked positions of the 2026-09-03 drag run, from *before*
         `creepx`.** That pipeline detrends the mean displacement away by design
         and the mean displacement is the measurand, so its output cannot be
         used however it is post-processed. This is the one step no code here
         can do. The files are kilobytes — two columns, one row per frame — so
         whether they are copied or read in place is a matter of convenience and
         not of design.
      2. **Prepare them**, because what is on disk is not what the fit reads.
         Per [`analysis/matlab/README.md`](../../analysis/matlab/README.md) the
         position files are **two columns `x y` in pixels, one row per frame**,
         with the speed in the filename and **no time column at all**:

         ```bash
         python -m calibration.cli drag-prepare <files...> \
             --frame-period-ms <achieved> \
             --frame-period-source "where that came from" --out prepared.csv
         ```

         ⚠ **The frame period is the number this step has to get right and
         nothing downstream can recover.** That README's own warning: it is
         hardcoded at `0.02` s in every MATLAB file and never read from
         metadata, while on this instrument the achieved period *equals the
         exposure*, so an acquisition at any other exposure silently puts every
         frequency axis and every diffusivity out by the ratio. Take it from the
         timestamp column, or from the run report's achieved rate over `n-1`
         `ElapsedTime-ms` intervals — **not from the setting** (G12b). The
         command requires a stated source, records it in the prepared file, and
         warns when the value is exactly 20.0 ms.

         It also **refuses a filename it cannot parse** rather than skipping it:
         those parsers skip a non-matching file "sometimes silently", and a
         skipped velocity is a missing point in a slope fit that the fit will
         not report.
      3. **Run the fit wherever the file is.** numpy only — no instrument, no
         Micro-Manager, no MATLAB, no edit to `D:\codes`. `requirements.txt` is
         three packages, so a clone runs it anywhere; **where it runs is
         incidental** and is recorded as provenance rather than required. In
         place or on a copy, whichever is easier. That shape is the operator's
         instruction (KH, 2026-09-16): expand P7 in the plan itself, and build
         it so **a plan can be produced on another computer too** — read the
         value from the file where it lives, then store it in `kb`. Refined the
         same day: producing a plan does not require being on site, so the fit
         is not tied to the instrument computer.
      4. **Commit the `kb/calibrations/` entry it writes**, after reading it. It
         carries the input's `source_hash`, the machine, `evidence_class:
         measured` and `verified: false`. Being measured *on this instrument* is
         what makes it admissible as a gate threshold, which no
         `kb/external/bd/` entry is.

      **What the number decides.** `sigma_gamma_rel` per rung against the
      **4.48 %** the ladder fit tolerates (D-7). Under it, the ladder stands;
      over it, r1's falsifier is confirmed on measured evidence rather than
      simulated and the run is redesigned around a direct z datum. The
      simulation side puts the route at 7.2–9.5 %, so the expected answer is
      *over* — which is exactly why it is worth measuring rather than assuming.

      ⚠ **Not blocked on a data transfer** — corrected 2026-09-16 under the
      instruction above. It is blocked on **a person doing one of two
      interchangeable things**: run the fit where the file is, or copy the file
      and run it here. The design does not care which, so "transfer" was the
      wrong name for the blocker. r7's `gaps[0].kind` still says
      `needs_data_transfer`; that document is sealed and cited, so the
      correction travels in the next round with a `corrects[]` entry rather than
      as an edit.

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
  the recorded 0.06453. Not this repository's file to edit; lens 6 owns
  settings-versus-analysis mismatches.
  **Worked out here rather than left as "it propagates", because it propagates
  into three quantities and the answer is different for each.** The mismatch is
  a *common multiplicative constant* on every length this run measures, so:

  | quantity | how `px_to_um` enters | error it contributes |
  |---|---|---|
  | **per-rung scatter on `gamma`** — what P7 measures, and what D-7's 4.48 % tolerance is compared against | `sigma(c·x)/mean(c·x) = sigma(x)/mean(x)` | **exactly zero.** A common factor cancels in a relative spread, identically |
  | absolute `alpha` from the drag slope, one size | `x_eq ∝ px`, so `alpha ∝ 1/px` | **−0.72 %** |
  | equipartition `alpha = kT/var(x)` | `var ∝ px²`, so `alpha ∝ 1/px²` | **−1.44 %** — twice the naive figure |
  | `alpha(a)` across sizes | common to every size | cancels, as §Error budget already says |

  Both survivors sit well under the ~8 % that `epsilon` contributes as a **bias**
  (D-2), so this is not what limits the run. ⚠ **The table is derived here, one
  line of arithmetic** — checkable above, and to be re-derived rather than
  trusted.

  **And the operator has ruled on the mismatch generally.** KH, 2026-09-15:

  > "이정도 오차는 오차라고 보지 않음"
  >
  > *("An error of this size I do not regard as an error.")*

  That is broader than the derivation and it is the operator's call about their
  own instrument, so it outranks a lens verdict (the precedent is
  `kb/systems/current.md:1284`). It does **not** retire the row that says
  `-1.44 %` on the equipartition `alpha`: a ruling that a number is tolerable is
  not a claim that it is zero, and the two survivors stay in the table so a
  later run at a tighter budget can find them.

  **So the pixel size is not a reason to move the data.** The reason is the next
  bullet and it stands alone: `alpha = gamma*v/x_eq` is implemented nowhere in
  `D:\codes`, and `creepx` detrends the mean displacement away by design — the
  existing analysis discards exactly this run's signal, whatever pixel size it
  uses. That plus "not this repository's to edit" is the whole case for P7 being
  a data transfer.
- **The wall fit is a second thing to write:** `gamma(dz) = gamma_0/(1 - 9a/(16(dz+h0)))`
  by least squares over the rungs, with `gamma` at each rung formed as
  `slope x alpha_equipartition` and `alpha` corrected for epsilon (P8) and for
  the blur term **`u/3`, not `2u/3`** (`u = t_exp/tau_k`) — see the ladder table.
  Correcting by `2u/3` over-corrects `alpha` by `u/3`, and **that is not a flat
  offset**: `u` varies monotonically along the ladder, so it writes a
  monotonic-in-`h` error into the very quantity being fitted. Its size is
  0.60 % at h = 3.0 to 0.97 % at h = 10 — a 0.37 percentage-point swing against
  a Faxen signal of +86.6 % to +16.2 %, so it is a correction to make and not a
  threat to `h0` (r4 §2, stated with its size so it is not over-read).
  Report `gamma_0`, `h0`, and the residuals against the first-order series — the
  residuals are where the truncation shows up.
- **Name the Lorentzian estimator, in writing, before acquiring.** Neither this
  repository nor BD had ever stated which fit it uses, and measured on exact OU
  that choice is worth **up to +7.9 %** on `f_c` — more than every declared
  physics difference in the bridge thread except the wall. An unweighted
  `curve_fit` over the whole one-sided PSD is dominated by points far above the
  corner, which carry no information about `f_c`; it is what produced r2's
  withdrawn +1.17 %. Weighted, or a band restricted to the corner. Until both
  sides name it, an agreement on `f_c` between them is uninterpretable at the
  ~1 % level → [`trap-stiffness-recovery.r4`](../external/bd/trap-stiffness-recovery.r4.md).
  This is an **analysis** change; no trajectory needs re-taking for it.
- **Identifying the trapped bead:** brightness does not do it. The trapped bead
  is the only object that does not translate with the stage — and this run
  translates the stage, so the discriminator is free here.
