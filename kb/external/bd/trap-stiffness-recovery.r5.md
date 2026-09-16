---
# Lands at  am:kb/external/bd/trap-stiffness-recovery.r5.md
# NOT in kb/calibrations/ — nothing here was measured on any instrument.
# `question` and `date` are this repository's index metadata; the schema accepts
# them, so this file and the landed copy are byte-identical.
id: trap-stiffness-recovery.r5
question: "How much does one bead's fitted f_c scatter at this instrument's envelope, and is 3 % per rung reachable at all?"
date: 2026-09-15
origin: bd
source_ref: "bd:bridge/threads/trap-stiffness-recovery/r5/ask_experiment.json"
source_hash: "sha256:4ac1cf0d7d2f2a3e"
evidence_class: simulated
evidence_classes:
  sigma_f_c_single: simulated
  T_obs_requirement: simulated
  f_s_requirement: round_trip
  epsilon_ceiling: computed
may_be_gate_threshold: false
derived_from:
  - ref: "am:bridge/threads/trap-stiffness-recovery/r3/ask_simulation.json"
    hash: "sha256:2f408e684ca4333a"
    rev: "f2e5f94"
    note: "the ask this answers -- so this entry is not independent evidence about the question it settles"
  - ref: "bd:bridge/threads/trap-stiffness-recovery/r4/ask_experiment.json"
    hash: "sha256:1099538c29c594bc"
    note: "the correction this builds on"
  - ref: "bd:verify/verify_fc_estimator_bias.py"
    hash: "sha256:e8f5942515006b5f"
    rev: "a986c4d"
  - ref: "bd:verify/detector_model.py"
    hash: "sha256:8fee871ff56bc2d5"
    rev: "a986c4d"
thread: trap-stiffness-recovery/r5
imported: 2026-09-15
supersedes: null
superseded_by: null
corrected_by: null
confirmed_by: null
---

# One bead's f_c scatters 29 % at the planned 5 s, and 3 % is not reachable by waiting (imported from BD)

**`evidence_class: simulated`.** Every number below is the output of a
calculation. A plan may cite this entry to justify a setting; **no gate may
clear against it** (`may_be_gate_threshold: false`).

This answers r3, which this repository sent. **It is therefore not independent
evidence about r3's hypothesis** — it is the other side computing what we asked
it to compute, and the `derived_from` line above says so.

## The answer

`sigma_f_c_single = 29.1 ± 0.9 %` at this instrument's envelope — `f_s = 520 Hz`,
`t_exp = 0.45 ms`, `T_obs = 5 s`, `epsilon = 10 nm`, with exposure integration
and Gaussian localisation noise applied before fitting — over **n = 512
independent single-bead realisations** (4 batches × 128). The ±0.91 is the
standard error on a standard deviation, `sd/sqrt(2(n-1))`.

r3 asked for one percentage point of resolution because the decision was binary
at ~3 %. **The answer is 29.1, so the decision is not close.**

**r3's hypothesis splits cleanly, and only half of it survives.** Its mechanism
clause — that observation length binds and the sampling convention does not — is
**confirmed**. Its number — `≤ 3 %` — is **out by about 10×**.

## Why waiting does not fix it

Scatter goes as `1/sqrt(T_obs)`: 29.1 % at 5 s (`T_obs/tau_k = 309.7`), 9.2 %
at 32.3 s (2000.9). Reaching 3 % by observation length alone needs roughly
`(9.2/3)^2 × 32.3 s ≈ 300 s per rung` — which this plan's own D-3 cost argument
already rules out at six rungs and three sizes.

**So the question changes.** It is no longer "is 520 fps enough" but **"where
does per-rung precision come from"**. BD names two candidates and can simulate
neither without a wall runner: **more beads per rung**, or **`gamma` from the
drag slope rather than from `f_c`**. The second is this plan's primary route
already — `alpha = gamma*v/x_eq` — with the equipartition/PSD block as a
cross-check, so the honest reading is that **the cross-check cannot carry 3 %,
and the precision of the primary route has never been measured by either side.**

## r2's requirements, as they now stand

| quantity | requirement | hard | note |
|---|---|:-:|---|
| `T_obs` per rung | **≥ 32.3 s** | no | Same number, basis restated a second time and now **measured**: 29.1 ± 0.9 % at 5 s against 9.2 ± 0.3 % at 32.3 s. Neither is under 3 % |
| `f_s` | **≥ 99 Hz** | no | **Lowered from r2's 620 Hz** — the `tau_k/10` convention does not bind here. At 520 Hz the camera costs 2 % relative on the scatter against the 220 % that observation length costs. ⚠ **This is our own G14c number coming home**, marked `round_trip`: BD agreeing with it is not independent corroboration of G14, and it must not be read as one |
| `epsilon` | **≤ 7.6 nm** | **yes** | Unchanged and unaffected. Analytic, from `(epsilon/l_k)^2` at `l_k = 33.98 nm`. Still hard because it is a bias on the equipartition `alpha` and does not average down over rungs **or over beads** — which is exactly what distinguishes it from the scatter this document is about |

## What it licenses, and what it does not

**Licensed.** Abandoning the 620 Hz question entirely. Weighing `T_obs` against
a measured scatter. Redesigning where per-rung precision comes from — more beads
per rung, or leaning on the drag slope — and saying in the plan which one.

**Not licensed.** Reading BD's adoption of 99 Hz as evidence for G14. Any claim
about `h0` or the Faxén separation: after five rounds, still no wall runner and
still one height, so r1's headline question is **open**. And any statement of
`f_c`'s recoverability, which r4 withdrew and nothing has replaced — central
values are still not comparable between the two sides at the ~1 % level until
both name their Lorentzian fit.

## The finding whose owner is neither side

**The camera is not the problem, and that is the opposite of what both sides
expected.** Both modelled it because it acts on the equipartition `alpha` — and
it does — but on the *scatter of `f_c`* it is worth 2 % relative while `T_obs`
is worth 3.2×. Two different quantities were being conflated, on both sides, for
four rounds. r5 files this one with `resolution_owner: human`.
