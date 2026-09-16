---
id: 2026-09-16-a-band-on-the-thresholds-we-chose
question: "The operator says up to 2x past a threshold is acceptable where safety is not involved. Which thresholds does that apply to, and does it unblock anything?"
date: 2026-09-16
status: current
---

# 2026-09-16 · A band on the thresholds we chose

**Asked for by KH**, in two messages:

> 너무 과도한 기준을 가지고 있으면 실험 진행이 어려운데, 항목마다 다르겠지만 약
> 5% 오차까지는 안전사항에 위배되지 않으면 실험을 돌려보는것도 좋을것 같아.
> **애초의 실험의 목적은 모르니까 측정하는것이지 정확한 값을 확인하는게
> 아니니까**
>
> 안전에 위배되는게 아니면 2배정도 까지는 괜찮기도 할듯

*Over-strict standards make it hard to run experiments; it differs per item,
but up to ~5 % — and then, up to about 2× — is acceptable where safety is not
violated.* **The reason is the load-bearing part: the point of the experiment
is that the value is unknown, so it is being measured. It is not a
confirmation of a value already known.*

And the instruction has KH's own precedent behind it. CLAUDE.md H4 records the
**~17.6 % Faxén drag inflation accepted against a 10 % limit "with that bound
stated"** — 1.76×, already granted, on exactly this kind of threshold.

## What was implemented

A per-lens `TOLERANCE` dict beside `LIMITS`, keyed by **emitted** code:
how far below its threshold a `hard` failure is a **concession** rather than a
**stop**. Three entries, all `0.5` — two times past the threshold:

| | threshold | why it degrades rather than destroys |
|---|---|---|
| `compute` `buffer.too_small` | `buffer_seconds_min` 5.0 s | a chosen depth, not a device limit. Below it a transient disk stall starts dropping frames sooner — a shorter grace period |
| `optics` `excitation.blocked` | `excitation_ratio` 0.2 | a chosen floor on source/absorption overlap. Below it the excitation is dimmer and the answer noisier, and lens 2's photon budget already carries the cost |
| `trapping` `sampling.aliased` | `f_s ≥ 10 f_c` | a chosen factor of ten on the PSD fit. At five the corner frequency is still recoverable and less well determined |

Measured behaviour on L3.4:

| buffer m | status | feasibility | `advances` |
|---:|---|---|---|
| 0.8 · 0.6 | **`PASS_WITH_CHANGES`** | HARD | **False** |
| 0.4 | `FAIL` | MARGINAL | False |

**A conceded gate cannot advance, and that needed no extra rule.** `grade()`
returns HARD or worse for every margin a band admits and `meets_grade` is
`False` for all of them. A concession reports; it does not authorise. The
failure is still a `fail` finding carrying its margin — what changes is only
that the run continues and the concession is named, which is CLAUDE.md H1
verbatim.

## Why a dict and not a global constant

The 22 `hard` checks were mapped to their thresholds before anything was
edited, and **they are not the same kind of thing.** Four kinds are
deliberately excluded, and the exclusions are the content of this decision:

### Physics, or a boolean

`na_feasibility` — *"NA ≤ n_immersion. Exact, not an approximation."* ·
`frame_rate` — a camera cannot run faster than it runs · `pixel_calibration` —
measured or not · `nyquist_divisor` — sampling at 1× aliases, which is not a
larger error but **a different signal**.

**And `velocity.time_base`, which is the one actually stopping the
repository's own brief.** Its question is *"has a commanded µm/s ever been
shown to be the µm/s that happens?"* The margin is 0.00 because the answer is
**no**. Two times "never measured" is never measured.

### Already factored

`disk_bandwidth_fraction` is **0.7 of a measured bandwidth** — its own comment
says *"never plan to sustain more than 70 %"*. `full_well_fraction` is 0.7 of
full well. Doubling them plans for 1.4× the disk and puts the peak at 1.4×
full well: dropped frames, and a clipped pixel. **That is not a worse answer,
it is no answer** — which is worse than a strict gate for the purpose KH gave.
Same for `capacity` (the disk runs out mid-run), `realtime_cpu`,
`ram_capacity` (128 GB is already half of 255.65 GB, authorised by KH).

### Safety

`working_distance` is the objective and the coverslip — SAFETY §2, precedence
0. Never.

### The brief's own number

L9.2 and L9.3 derive from `target_relative_error`. **That is already the
operator's to set**: 10 % instead of 5 % is written into the brief, not
granted behind it. A band here would loosen the experiment's own stated
criterion without the experiment saying so.

`blocking_od` 5.0 is excluded on a fifth ground: it is a **dated operator
decision** of its own
([`2026-09-09-blocking-threshold-fixed-at-5-od.md`](2026-09-09-blocking-threshold-fixed-at-5-od.md)),
and a blanket rule may not re-open one.

## ⚠ It does not unblock the brief it was asked for

This has to be said plainly, because the instruction was motivated by runs not
proceeding. **Of the three bands, none touches
`config/briefs/active-microrheology.yaml`.**

That proposal stops on `velocity.time_base` — a boolean, above — and is
otherwise BLOCKED on **about fifteen R1 inputs** (exposure, task kind, ROI,
target fps, imaging depth, chamber height, concentration, duration, camera
mode, …) plus **one R2 measurement**. A tolerance band changes none of them.

**What is blocking that brief is not strictness.** It is fifteen questions
answerable in one conversation and one measurement somebody has to make. The
band is correct and it was worth building; it is not the lever for this
proposal.

## Why

**The margin already was the tolerance.** `m = achieved / required`, so a gate
at 0.6 was already reporting "40 % short" as a number. What KH wanted was not a
looser threshold but for a near-miss to become a *reported concession* instead
of a *stop* — which is what H1 already prescribes and what nothing enforced at
the `hard` level, because precedence level 1 is unconditional.

So the edit is to the **stop**, not to `LIMITS`. Nothing about what any check
computes has changed, and every threshold in `LIMITS` is the number it was.
That matters for CLAUDE.md §2's rule that *"a constant in a `LIMITS` entry is a
claim about every future experiment"*: `TOLERANCE` makes a claim about this
repository's own conservatism, not about the physics.

## Falsifying condition

**The dict was keyed wrong on the way in, and that is the exposure.**
`TOLERANCE` was first keyed on the **registered** check code (`buffer`) while
results carry the **emitted** one (`buffer.too_small`), so it matched nothing
and all three bands were silently inert. That is *"a registry naming a code
nobody emits"* — the second of the two failure modes `committee/` exists to
catch — arriving in a brand-new table within minutes of its creation.

It is now pinned three ways in `tests/test_committee_emissions.py`, against
the **parsed** emission sites rather than against a rule: every key is a code
its lens emits, every key is a code that can `fail`, and every band is within
`[0.5, 1.0)`. The relation cannot be recovered by string surgery in any case —
`buffer` → `buffer.too_small` adds a suffix and `na_feasibility` →
`geometry.na_feasibility` adds a prefix.

**The remaining exposure is the classification, not the mechanism.** Three
checks were judged "degrades rather than destroys" by reading their branches;
`sampling.aliased` is the one to watch, because its **name is wrong inside the
band**. Nyquist on the trap dynamics is `f_s ≥ 2 f_c`, i.e. m = 0.2, so the
code only literally aliases below 0.2 — a future widening on the strength of
the name would cross into real aliasing. The comment in `trapping/checks.py`
says so and `test_a_band_stays_within_its_own_bounds` holds the floor at 0.5.

**And a fourth kind of exclusion would mean the taxonomy is incomplete.**
Four were found by mapping 22 checks. If a fifth appears — a threshold that is
neither physics, nor pre-factored, nor safety, nor the brief's, and still
should not be doubled — then "chosen by this repository" is not the right
criterion and the dict needs a reason field rather than a number.
