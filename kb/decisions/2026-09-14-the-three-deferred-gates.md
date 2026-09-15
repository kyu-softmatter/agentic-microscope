---
id: 2026-09-14-the-three-deferred-gates
question: "What arithmetic do L4.8, L6.5 and L9.6 rest on, and what stops L6.5 from being G11 again?"
date: 2026-09-14
status: current
---

# 2026-09-14 · L4.8, L6.5, L9.6 — and why one of them is not G11

**Asked for by KH** the same day the audit deferred them:
*"L4.8, L9.6, L6.5 만들자."* The audit
([`2026-09-14-gate-audit-against-the-parameter-inventory.md`](2026-09-14-gate-audit-against-the-parameter-inventory.md))
named each one and what it needed first. This is what each turned out to rest
on. **52 checks now; 22 `hard` · 6 `bias` · 6 `soft` · 18 `info`.**

All three are `soft`, and that is one decision made three times: **too few
samples is variance, not bias.** The answer is noisy, not wrong, so it is
graded and it trades against the other axes at [05 §2](../../docs/05-consensus-gate.md)
precedence level 3 — where a `hard` gate could not be traded at all. L9.3
sitting next to L9.6 is `hard` for the opposite reason: a short step biases
kappa systematically, and no amount of repetition removes it.

None of them has a `LIMITS` entry. Every threshold is the caller's
`target_relative_error` or `target_particles_in_field`, which is CLAUDE.md §2's
rule from the audit: a constant in `LIMITS` is a claim about every future
experiment.

## L4.8 — the bound that was named and then orphaned

`sample/checks.py`'s L4.6 said, in its own docstring, *"whether the count is
**enough** is G11's call"*. G11 was removed on 2026-09-11 and the sentence
stayed, so the operator inventory's *"너무 희석하면 실험하기가 힘듦"* went
unchecked for three days without anything looking wrong.

L4.8 is the same arithmetic as L4.6 — the same `sigma = c·H` settled areal
density, the same total-sedimentation premise — pointed the other way. That is
deliberate: **two bounds on one number, not two models of it**, and
`tests/test_sample_gate.py::test_l4_8_and_l4_6_cannot_disagree_about_how_many_there_are`
is what keeps it that way.

The threshold `target_particles_in_field` defaults to 1.0, and that default
originates nothing: below one particle in the field there is no measurement.
An ensemble experiment raises it in the brief.

## L9.6 — the derivation, stated so it can be argued with

The audit deferred this one pending review of the derivation. Here it is.
`kappa = gamma·v/x_eq` is measured by stepping the stage and reading the mean
bead offset, so with `v` commanded and `gamma` lens 4's business, **the
relative error on kappa is the relative error on `x_eq`** — and `x_eq` is a
mean over one step of a bead that never stops moving.

In the trap that bead is an Ornstein–Uhlenbeck process: variance `kT/kappa` by
equipartition, correlation time `tau = gamma/kappa`. Averaging it over a step
of length `T`:

```
Var(x_bar) = (2 sigma^2 tau / T) · [1 - (tau/T)(1 - exp(-T/tau))],  sigma = sqrt(kT/kappa)
```

**The exact expression, not the `T >> tau` limit**, because the limit is wrong
in the regime this lens is about — L9.3 exists precisely to tell callers their
step may be a few tau long, and at `T = tau` the simple form overstates the
averaging benefit by 37 %. As `T -> 0` the exact form returns `sigma`:
averaging over no time buys nothing, which is the check that it is the right
formula.

Localization noise adds in quadrature as `sigma_loc/sqrt(frames in the step)`
when lens 2 has supplied both numbers. Which term dominates is reported as
`limited_by`, because it decides what to change: a thermal-limited measurement
wants longer steps or a stiffer trap, a localization-limited one wants photons.

One step then gives `eps_1 = sigma_total/x_eq` and N steps give
`eps_1/sqrt(N)`. **Steps are independent in the way frames inside a step are
not** — each is a fresh approach to a fresh offset — which is why `1/sqrt(N)`
is honest here and was not honest in G11.

On this instrument's own calibration (a = 2.475 µm, kappa = 3.87 pN/µm,
tau = 12.1 ms, 1 s steps, 5 % target):

| v | x_eq | sigma of the mean | per step | steps needed |
|---:|---:|---:|---:|---:|
| 30 µm/s | 362 nm | 5.0 nm | 1.4 % | **1** |
| 5 µm/s | 60 nm | 5.0 nm | 8.3 % | **3** |
| 1 µm/s | 12 nm | 5.0 nm | 41 % | **69** |

The noise does not move with velocity and the signal does, which is the whole
content of the check: a slow sweep is not a gentler measurement, it is a
sixty-nine-times longer one.

Left undecided, `n_steps` produces a report and no grade — the same treatment
L2.4 gives an undecided frame rate, and for the same reason: a gate that failed
there would be failing a decision nobody has made.

## L6.5 — G11's question, and the four ways it is not G11

This reverses *"the lens computes nothing at all"*, which
[`2026-09-11-g11-and-g26-removed.md`](2026-09-11-g11-and-g26-removed.md) called
*"the honest description of what it was already mostly doing"*. Reversing it
needs more than a new number, so here is the whole difference:

| | G11 | L6.5 |
|---|---|---|
| samples | `N_p × N_f` | `N_p × N_f / (2·f·tau)` |
| on the 2026-09-03 calibration | 31,200 → 0.566 % | 2,479 → 2.01 % |
| kind | certified a measurement | `soft` |
| with no correlation time | did not ask | **does not grade** |

**The fourth row is the repair.** G11 was not wrong about `N_p × N_f`; it was
wrong to call the product independent, and it could not have been right,
because nothing told it the correlation time. `correlation_time_s` is now a
field, and absent it L6.5 returns a visible INFO saying so rather than a
number — which is exactly the state G11 gated in.

The `2` is the statistical inefficiency of an exponentially correlated series:
for an autocovariance `exp(-t/tau)` the integrated autocorrelation time is
`tau`, so a run of length `T` holds `T/(2·tau)` independent samples. Below
half a frame per correlation time the correction **turns off** — sampling
slower than the process decorrelates means consecutive frames already are
independent, and applying the formula there would claim more samples than
there are frames.

**And it is not the drag calibration's precision.** That is L9.6's, for the
reason the removal entry gives: kappa is fitted across commanded velocities and
the frames within one step are averaged, not counted. L6.5 answers the ensemble
question — an MSD, a diffusion coefficient, a modulus — where frames are the
samples and the only question is how many are independent.

`tests/test_validity_gate.py::test_l6_5_reproduces_the_numbers_that_retired_g11`
pins all four numbers in the table above, so the two entries cannot drift apart.

## Why

**Because the audit found that two of the three bounds had been *named* and
then lost.** L4.6's docstring pointed at an owner that no longer existed, and
the G11 entry's own prose said what the correct version needed and then nobody
wrote it. A gap that is documented is easier to leave open than one that is
not: the documentation reads as coverage.

**And because `soft` is the kind that was missing.** Before today the lens set
had 3 `soft` checks against 22 `hard`, which meant almost every question the
committee could answer was answered as possible-or-impossible. Precision is not
that kind of question, and three of the operator inventory's own bounds —
concentration from below, steps, total frames — are precision questions. §2
precedence level 3 exists for exactly these and had very little to arbitrate.

## Falsifying condition

**L9.6 is wrong if the bead's position noise in a driven step is not
`sqrt(kT/kappa)` with correlation time `gamma/kappa`.** That is the
equilibrium result, and a step is a driven, non-equilibrium transient: during
the approach the variance is smaller than equilibrium, so **L9.6 is
conservative during the transient and exact after it**. If a measured
position-noise spectrum during a step disagrees with the OU form by more than
the 37 % the exact-vs-limit correction is worth, the formula is wrong and not
just imprecise. The measurement is cheap: record one long step and compare its
running-mean variance against `2 sigma^2 tau/T`.

**L6.5 is wrong if the correlation time that matters is not the one supplied.**
A trapped bead has one obvious tau; a free particle in a viscoelastic medium
has a spectrum of them, and taking the longest makes the count pessimistic
while taking the shortest makes it G11 again. If briefs for viscoelastic
samples routinely produce a correction factor that disagrees with a measured
autocorrelation, the single-tau model is the thing to drop.

**L4.8 is wrong if total sedimentation is the wrong premise for the lower
bound.** It is the right premise for L4.6's upper bound — the most crowded the
coverslip can get — but for "are there enough" it is the *optimistic* end:
nothing is lost to the walls or the pipette. So L4.8 says so in its failure
text, and a preparation that routinely lands well under the predicted count
means the bound needs a loss term rather than a caveat.

## Not decided here

- ~~**The wiring.**~~ **Done the same day.** `designer/build.py` carries
  L6.5's four numbers down -- the particle count from
  `SampleSetup.expected_count_in_field` (the same settled density L4.6 and
  L4.8 bound from either side, moved onto the setup so all three readers share
  one definition), the frame count from duration x lens 2's decided rate, and
  the correlation time from lens 9's `tau = gamma/kappa` where there is a trap
  and the brief's stated characteristic time otherwise. `n_steps` and
  `target_particles_in_field` are brief fields. Worked end to end on a real
  geometry: 6.9 particles x 6,000 frames is 41,533 naive samples, and 50
  frames per correlation time makes that **415** -- 4.9 % against a 5 %
  target, where counting every frame would have claimed 0.49 %.
- **Whether L6.5 should read upstream metrics directly.** It takes plain
  fields instead, so the designer wires it. Reaching into another lens's
  `metrics` dict by string key was the alternative and is more fragile.
- **The rest of lens 6.** It computes one thing again, not everything. L6.1–
  L6.4 still read verdicts and declarations.
