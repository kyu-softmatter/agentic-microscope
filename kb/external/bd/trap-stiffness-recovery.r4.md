---
# Lands at  am:kb/external/bd/trap-stiffness-recovery.r4.md
# NOT in kb/calibrations/ — that directory means "measured on this instrument",
# and none of this was measured on any instrument.
# `question` and `date` are index metadata for the importing repository
# (knowledge/index.py requires both of everything it indexes) and the schema
# accepts them as optional, so this file and the landed copy are byte-identical.
id: trap-stiffness-recovery.r4
question: "Which of r2's numbers survive, now that the +1.17 % is known to be the estimator and the blur coefficient was twice too large?"
date: 2026-09-15
origin: bd
source_ref: "bd:verify/_out/fc_estimator_bias.json"
source_hash: "sha256:b48c48c94ad2f0be"
evidence_class: simulated
evidence_classes:
  blur_coefficient: computed
  epsilon_ceiling: computed
  estimator_bias: simulated
  f_c_scatter_single_bead: simulated
  single_bead_ratio: simulated
may_be_gate_threshold: false
derived_from:
  - ref: "bd:verify/verify_fc_estimator_bias.py"
    hash: "sha256:e8f5942515006b5f"
    rev: "a986c4d"
    note: "branch microscope-link-survey, not yet on BD's main"
  - ref: "bd:verify/detector_model.py"
    hash: "sha256:8fee871ff56bc2d5"
    rev: "a986c4d"
  - ref: "bd:bridge/threads/trap-stiffness-recovery/r2/ask_experiment.json"
    hash: "sha256:683eae8f34a6bef9"
    note: "the document this corrects"
  - ref: "am:kb/plans/2026-09-15-drag-calibration-stiffness-vs-size.md"
    hash: "sha256:58cfc405231a2970"
    rev: "9f971a8"
    note: "the blur coefficient corrected here originated in this file, at this revision"
thread: trap-stiffness-recovery/r4
imported: 2026-09-15
supersedes: null
superseded_by: null
corrected_by: null
confirmed_by: null
---

# What survives of r2, after the estimator and the blur term were checked (imported from BD)

**`evidence_class: simulated`.** Every number below is the output of a
calculation. A plan may cite this entry to justify a setting; **no gate may
clear against it** (`may_be_gate_threshold: false`).

**This entry corrects the one it descends from.** It supersedes
[`trap-stiffness-recovery.r2`](trap-stiffness-recovery.r2.md) on two values and
leaves the rest of that entry standing — which is why r2 is kept and linked
rather than deleted: this plan cites it, and a deleted import dangles the
citation.

**Settled on exact Ornstein-Uhlenbeck data, whose `f_c` is known in closed
form** — not on a Brownian-dynamics run. An exact OU sampler is unbiased at any
step size, which is what let the estimator's bias be separated from integration
error; a BD re-run could not have separated them.

## The two withdrawals

**1 · `f_c` recoverable to +1.17 % is withdrawn, and NOT replaced.** Exact OU
through the archived run's own estimator configuration — Welch, `nperseg 4096`,
unweighted `curve_fit` of `S0/(1+(f/f_c)^2)` over the whole one-sided PSD, 250
traces averaged before fitting — returns **+0.8 to +1.2 %**, i.e. 0.1 sigma from
the reported +1.17 %. The simulation reproduced the estimator, and the estimator
was read as physics. It is a **bias, not a variance**: `T_obs x 26` does not
remove it (+0.57 % at `T_obs/tau_k = 310`, +0.98 % at 8000), and the sampling
dependence is non-monotonic (+7.9 % at 2 samples per `tau_k`, +0.8 % at 10,
+3.8 % at 50) because an unweighted least squares over the whole band is
dominated by points far above the corner, which carry no information about
`f_c`. **How well `f_c` can be recovered is not known until the estimator is
fixed.** No number is offered in its place.

**2 · The blur coefficient for a trapped bead is `u/3`, not `2u/3`.**
`2*D*t_exp/3` is the free-particle MSD term. In a harmonic trap the
exposure-averaged variance is exact:
`var_blur/var = 2(u - 1 + e^-u)/u^2 -> 1 - u/3`, with `u = t_exp/tau_k`. Checked
against exact-OU boxcar averaging at five values of `u` from 0.028 to 3: the
exact form holds within **3.3 sigma**, `2u/3` is rejected at **16 to 358
sigma**. **This error originated on the AM side** — r1's `camera_model` and the
plan's `blur on var(x)` column — so every entry of that column is exactly half
what was written: **0.60 % at h = 3.0 µm rising to 0.97 % at h = 10 µm**, not
1.21 % to 1.94 %.

⚠ Not a flat offset: `u = t_exp/tau_k(h)` varies monotonically along the ladder,
so correcting `alpha` by `2u/3` writes a monotonic-in-`h` error into the
quantity being fitted. The size is a 0.37 percentage-point swing across the
ladder against a Faxén signal of +86.6 % to +16.2 % — **a correction to make,
not a threat to `h0`**.

**And r2's own single-bead ratio was wrong too.** r2 `finding[3]` said `~32x`,
i.e. `sqrt(1000)`. Measured: **21.1x** at `T_obs/tau_k = 2000` and **15.5x** at
310 — `f_c` is fitted to the `min(250, N)` subset, and averaging spectra before
a non-linear fit is not averaging fits. The ratio was the wrong thing to carry;
the absolute numbers are below.

## What happens to r2's three requirements

| quantity | requirement | hard | what changed |
|---|---|:-:|---|
| `T_obs` per rung | **≥ 32.3 s** | no | **Same number, different basis.** "2000 is where the 1.17 % was measured" is void. It survives on a measurement r2 did not have: one bead's fitted `f_c` scatters **29.1 ± 0.9 %** at 5 s (`T_obs/tau_k = 310`) and **9.2 ± 0.3 %** at 32.3 s (2001) — a factor 3.2 for a factor 6.5 in time |
| `f_s` | **≥ 620 Hz** | no | **Unchanged**, and never came from the 1.17 %. One thing added: at this envelope the convention is **not what binds** — the camera model on/off moves the scatter 28.5 % → 29.1 %, about 2 % relative, while `T_obs` moves it 3.2× |
| `epsilon` | **≤ 7.6 nm** | **yes** | **Unchanged and still hard.** Analytic, from `(epsilon/l_k)^2` at `l_k = 33.98 nm`; independent of both withdrawn numbers. The blur fix moves the net camera effect on `alpha` from ~8.0 % to **~7.7 %**, still epsilon-dominated |

## What this licenses, and what it does not

**Licensed.** Halving the blur column and the blur term in the analysis recipe.
Weighing `T_obs` against the 29.1 % → 9.2 % scatter instead of against 1.17 %.
Dropping the idea that the ROI height must be cut to reach 620 Hz — the
convention is not the constraint. Treating P8's `epsilon` as the binding half of
the camera budget.

**Not licensed.** Any claim about `h0`, the Faxén separation or the ladder fit:
still no wall runner, still one height. Any statement of how well `f_c` is
recoverable — withdrawn, not replaced. And no gate threshold: these are
simulated numbers and `may_be_gate_threshold: false` is the whole reason this
entry sits in `kb/external/bd/` rather than anywhere a check reads.

## The open item neither side owns

**Neither repository had said which Lorentzian estimator it uses.** Measured
here, that choice is worth **up to +7.9 %** on `f_c` — more than every declared
physics difference in this thread except the wall. Until both sides name the fit
(weighted or not, over what band), an agreement on `f_c` between them is
uninterpretable at the ~1 % level. Carried by BD as
`assumptions[estimator].status: unknown`. On the AM side it lands in the plan's
Analysis section as a piece to write before acquiring, and it costs no
instrument time.
