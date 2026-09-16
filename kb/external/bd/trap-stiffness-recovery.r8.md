---
# Lands at  am:kb/external/bd/trap-stiffness-recovery.r8.md
# NOT in kb/calibrations/ — nothing here was measured on any instrument.
id: trap-stiffness-recovery.r8
question: "How much per-rung scatter can the height-ladder fit tolerate, and does the route that measures gamma stay under it?"
date: 2026-09-15
origin: bd
source_ref: "bd:bridge/threads/trap-stiffness-recovery/r8/ask_experiment.json"
source_hash: "sha256:3c85ed0bd802d8b2"
evidence_class: simulated
evidence_classes:
  sigma_gamma_max: simulated
  sigma_h0_forward: simulated
  per_rung_scatter_decomposition: simulated
  epsilon_ceiling: computed
  ou_reduction_crosscheck: simulated
may_be_gate_threshold: false
derived_from:
  - ref: "am:bridge/threads/trap-stiffness-recovery/r7/ask_simulation.json"
    hash: "sha256:e45e8b5f6cdc9562"
    note: "the ask this answers -- so this entry is not independent evidence about the question it settles"
  - ref: "bd:verify/verify_ladder_tolerance.py"
    hash: "sha256:cd6bc109253678ad"
    rev: "07d1048"
    note: "branch microscope-link-survey, not on BD's main"
  - ref: "bd:verify/verify_drag_ladder.py"
    hash: "sha256:fdd1dae3588398a9"
    rev: "07d1048"
  - ref: "bd:verify/verify_drag_hoomd_crosscheck.py"
    hash: "sha256:d6cf41dd55213fc4"
    rev: "07d1048"
  - ref: "bd:verify/_out/drag_ladder.json"
    hash: "sha256:76048f61948b7626"
    rev: "07d1048"
thread: trap-stiffness-recovery/r8
imported: 2026-09-15
supersedes: null
superseded_by: null
corrected_by: null
confirmed_by: null
---

# The ladder fit tolerates 4.48 % per rung, and the route that measures gamma delivers 7.2–9.5 % (imported from BD)

**`evidence_class: simulated`.** Every number below is the output of a
calculation. A plan may cite this entry to justify a setting; **no gate may
clear against it** (`may_be_gate_threshold: false`).

This answers r7, which this repository sent, so **it is not independent evidence
about the question it settles**.

⚠ **Read the findings before the headline.** Taken at face value the first line
says a claim of ours was confirmed, and the round is the opposite of good news.

## The two numbers, and why they point in different directions

| | value | what it is |
|---|---|---|
| `sigma_gamma_max` | **4.48 %** | The tolerance. Above this per-rung scatter the six-rung fit stops returning `h0` to ±0.2 µm. A property **of the fit** — obtained by direct propagation, `gamma_i` drawn as `gamma_true(h_i)(1 + sigma*xi)`, 4000 ladders per sigma |
| measured per-rung scatter | **7.2–9.5 %** | What the route that measures `gamma` actually delivers, simulated at this plan's settings. **1.8× the tolerance** |
| forward fit at that scatter | **0.433–0.450 µm** on `h0` | Stable across injected `h0` of 0.5, 1.0 and 2.0 µm |

So *our* claim — that the tolerance is at or above the 3 % the budget assumes —
is **confirmed with room**, and at 3 % the fit returns `h0` to **0.131 µm**,
which means r1's ±0.195 µm was *conservative given its own assumption*. **The
model was never the problem. The input was.**

## r1's own falsifier has fired

r1 pre-registered it, in round one: *"if its scatter exceeds ~0.4 µm once finite
`T_obs`, motion blur and localisation noise are included, then the ladder does
not produce a trapping height and the run should be redesigned around a direct
z datum instead."*

0.433–0.450 µm, with exactly those three included. **This is the first round
that could evaluate the criterion**, and it fails it.

⚠ **It fires on a simulated input, and that distinction is load-bearing.** BD
says so itself: the 1.8×-over-tolerance finding rests on a *simulated* per-rung
error, while `sigma_gamma_max = 4.48 %` does not — the tolerance is a property of
the fit, and it is the number **P7 on real data gets compared against**. So the
criterion has fired on the best evidence available and not on a measurement of
this instrument.

## Where the per-rung error actually is

**Decomposed, and it is not where this plan's budget put it:**

| component | contribution |
|---|---|
| equipartition `alpha = kT/var(x)` | **7.3–9.5 %** |
| the drag slope `x_eq(v)` | **1.3–1.6 %** |

**The slope is not the problem and lengthening the drive segments buys little.**
The variance estimate is, and it is bounded by `T_obs/tau_k`, which this plan
sets to **201–323**.

## A uniform bias lands on gamma_0, not on h0

`h0` is set by the **shape** of `gamma(h)`, so a multiplicative bias common to
every rung cancels out of it. Measured: the camera moves `gamma_0` by
**−4.65 %** and `h0` by nothing resolvable (1.106 with the camera on against
1.136 off, at `h0_true = 1.0`, both ±0.03).

So `epsilon` threatens **`gamma_bulk`, not the trapping height** — the ceiling
stays at ≤ 7.6 nm and now has a second, independent reason: the camera
contributes −4.8 to −6.9 % of bias on `gamma` per rung, entirely through `alpha`
inheriting the 8.66 % variance inflation. `gamma_bulk` therefore comes out about
5 % wrong unless `epsilon` is measured and corrected.

## The overdamped reduction was checked, not assumed

HOOMD Brownian at `k* = 21221`, `dt/tau_k = 0.002`, `T_obs/tau_k = 322.9`,
`N = 1000`: the slope `d<x>/dv` against the analytic `-1/k*` is **+0.032 %**,
`<x>` within −0.36 to +0.14 %, `var` within −1.31 to +0.03 %. A different *kind*
of evidence from the analytic layer, which is why it was run.

## What it licenses, and what it does not

**Licensed.** Treating `sigma_gamma_per_rung <= 4.48 %` as the design target the
measurement has to meet. Redesigning the run around a direct z datum, which is
r1's own pre-registered response. Spending effort on the **variance estimate**
rather than on the drive segments. Reading `epsilon` as a `gamma_bulk` problem.

**Not licensed.** Declaring the ladder dead on this evidence alone — the 7.2–9.5 %
is simulated and P7 is what measures it here. Any gate threshold: this is
`simulated` and carries `may_be_gate_threshold: false`, so 4.48 % is a target
and not a check. And `h0` as a physical number: no simulation on this side will
ever measure a wall factor it was not given, in this round or any later one.

## Still open

- **`gaps[1]`, `needs_data_transfer`, owner human** — P7, the per-rung scatter
  on real data. It is what turns this round's warning into a verdict.
- **`gaps[2]`, `not_yet_built`, owner bd** — whether these are the right six
  heights. 4.48 % is for *this* ladder, and a different six would plausibly move
  it **upward**: the near rungs carry the most Faxén signal and currently get the
  least statistics (`T_obs/tau_k` = 201 at h = 3.0 against 323 at h = 10).
  Cheap — seconds, not a run — and worth doing once P7 says what is achievable.
- **`gaps[3]`, `needs_human_action`, owner human** — which Lorentzian estimator
  each side uses. Still unnamed on both sides after eight rounds.
