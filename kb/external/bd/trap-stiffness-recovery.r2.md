---
# Lands at  am:kb/external/bd/trap-stiffness-recovery.r2.md
# NOT in kb/calibrations/ — that directory means "measured on this instrument",
# and a simulated f_c placed there would be a lie the path itself tells.
id: trap-stiffness-recovery.r2
# `question` and `date` are NOT in the bridge's kb_external_entry schema, which
# is `additionalProperties: false`. They are here because knowledge/index.py
# requires both of every indexed entry, and an imported number that never
# appears in kb/INDEX.md is one CLAUDE.md §0 tells the reader to start from and
# would never find. The body below is a mechanical copy; these two lines are
# this repository's index metadata, not content. Closing the gap properly means
# adding both keys to the bridge schema -- proposed, not edited (ownership rule).
question: "What does Brownian dynamics require of an acquisition that is to recover f_c, and what does that license for the drag-calibration plan?"
date: 2026-09-15
origin: bd
source_ref: "bd:runs/trap-2d-5um__a5ef4f45d589"
source_hash: "sha256:09913b52a633d7f9"
evidence_class: simulated
may_be_gate_threshold: false
derived_from:
  - ref: "am:kb/plans/2026-09-15-drag-calibration-stiffness-vs-size.md"
    hash: "sha256:58cfc405231a2970"
thread: trap-stiffness-recovery/r2
imported: 2026-09-15
supersedes: null
superseded_by: null
corrected_by: null
confirmed_by: null
---

# Acquisition requirements for recovering f_c, from Brownian dynamics (imported from BD)

**`evidence_class: simulated`.** Every number below is the output of a
calculation, not of an instrument. A plan may cite this entry to justify a
setting; **no gate may clear against it** (`may_be_gate_threshold: false`) —
a margin computed against a simulated threshold reads as measured, which is the
disease hard rule 3 already names.

**Note the `derived_from` line.** This entry descends from *our own* plan. It is
therefore not independent evidence about that plan, and requirement 4 below is
our own number coming home — kept because it is disclosed, soft, and useful.

## Requirements

| quantity | requirement | hard | basis |
|---|---|:-:|---|
| `T_obs` per rung | **≥ 32.3 s** | no | `T_obs/tau_k = 2000`, where BD measured `f_c` to +1.17 %. Our 5 s is 310 — 6.4× short of the validated point, though it clears BD's soft floor of 100. |
| `f_s` | **≥ 620 Hz** | no | `tau_k/10`. Our envelope caps at 520 Hz (8.39 samples/`tau_k`). **Convention, not limit** — see finding 1. |
| `epsilon` | **≤ 7.6 nm** | **yes** | `(epsilon/l_k)² ≤ 0.05` at `l_k = 33.98 nm`. Our assumed 10 nm is ~8 % on `alpha`, and it is a bias, not a variance. |
| `sigma_gamma` per rung | ≤ 3.0 % | no | **our own 400-realisation figure, returned unverified.** Do not read as corroborated. |

## What this does and does not license

**Licensed:** lengthening `T_obs` at step 9c, raising `f_s` by shrinking the ROI
height, and treating precondition P8 (`epsilon` on a stuck bead) as a hard gate
rather than a correction. Each of those is a *design* change motivated by an
imported number — allowed.

**Not licensed:** any claim about `h0`, about the Faxén separation, or about
per-bead error bars. BD has no wall, no detector, and its 1.17 % is an
ensemble-of-1000 number: a single bead at the same `T_obs/tau_k` would scatter
about 32× more.

## The regime is not ours, and that is the point

`k*` 60 358 vs our 21 221; `l_k/d` 0.004070 vs our 0.006865. Different systems.
What transfers is the *recoverability* of `f_c`, and it transfers in the
favourable direction: BD's case is stiffer and its fluctuation smaller relative
to the bead, so it is the harder measurement.

`tau_p/tau_k` = 8.14e-4 there and 7.30e-5 here, both far under the 1e-2 limit —
overdamped is genuinely shared.

## Open, for r3

BD lists four gaps. Two are cheap and would close most of this: **add a
sampling layer** (integrate over `t_exp`, then add Gaussian `epsilon`), and
**re-run at `n_replicas = 1`** to get a per-realisation scatter instead of an
ensemble one. The expensive one is a wall runner, which `RUNNERS` does not have.
