---
id: 2026-09-14-gate-audit-against-the-parameter-inventory
question: "Which of the operator's parameters can the committee actually decide, and where should the gates that decide the rest get their thresholds?"
date: 2026-09-14
status: current
---

# 2026-09-14 · The gate audit: three broken handoffs before any new gate

**Asked for by KH**, after the parameter inventory became the brief and plan
schemas the same day: *"이제 brief의 질문을 바탕으로 위 파라미터를 정하기 위해
gates를 다시 재배치/추가/삭제/수정을 할거야."*

The audit ran all 49 checks against one test: **a parameter is decidable only
if some check asks for it and some check bounds it.** What came out was not a
list of missing gates. It was three places where a gate that already exists
never received its input — so adding gates would have been building on top of
a floor that was not there.

## What was broken

**Lens 4 could not run at all through the designer.** `designer/build.py`
hand-built an `Objective` from the brief's label, NA and immersion, which
threw away everything else `data/objectives.yaml` carries — above all
`wd_um`. So `sample.gate` refused at Phase 0 with `missing.working_distance`
on every brief ever written, and L4.2, L4.3, L4.4, L4.5, L4.6 and L4.7 never
executed. The working distance has been on file since 2026-08-10.

**The brief names the objective; the registry is the objective.** That is the
repair, and the reason it is stated as a rule rather than a patch: the same
mistake is available for the detector, the dye and every filter, all of which
have registries and all of which a brief could re-type by hand.

**The field of view crossed no boundary.** `sample/setup.py` says of
`field_width_um`: *"Owned by lenses 1/2 (objective + camera); lens 4 only
consumes it"* — and nothing carried it. L4.6's particle count ran only when a
human typed the field into `sample/cli.py`. Through the designer it reported
"Settled crowding not evaluated", **which looks exactly like a check that
passed**. Lens 2 now computes it (`DetectionSetup.field_of_view_um`) and
`designer/run.py` hands it down; the handoff is recorded in `CROSS_TIER`
beside the one that already existed.

**One constant had two definitions**, and they had already drifted — not in
value, which is how a duplicated constant is usually caught, but in the
comparison around it. `StabilitySetup.convenes` is `> 30`; `designer/roster.py`
was `>= 30`. A thirty-minute acquisition convened lens 8 in one file and not in
the other.

## Where a new gate's threshold comes from: the brief

**Decided by KH.** The inventory carries numbers the repository has no source
for — ROI at 1.5× the system, concentration at 3–5× the system size, trap
power at 1.2× the requirement. None of them becomes a constant in a `LIMITS`
dict and none becomes a `kb/expertise/` entry. **The operator supplies the
multiple per experiment, in the brief, and the gate grades against that.**

The precedent is L9.3, which says it of itself: *"No 'about five time
constants' appears anywhere in this lens, because the number the experiment
actually needs follows from the precision it asked for."* Lens 9 has no
`LIMITS` dict at all for this reason. The alternative — storing one multiple
and applying it to every experiment — is a claim about all future experiments
made from one table.

## Where the piezo's travel bound belongs: both places

**Decided by KH.** `hardware/piezo_waveform.py` already refuses a waveform
outside `StageTravel`, and the calibrated 0–600 µm range is in
`kb/systems/current.md`. The range also becomes an R0 brief fact with a
lens 9 gate. **Not a duplicated definition**: one is a planning check on a
number known before the run, the other is the last refusal before the DAC, and
a bound enforced at two stages is defence in depth rather than two sources of
truth. **Designed here, not built.**

## Deferred, with what each one needs

Three additions were specified and left unbuilt, so that the audit's repairs
could land on their own:

| | What | What it needs before it can be written |
|---|---|---|
| **L4.8** `count_sufficiency` | the concentration LOWER bound. `sample/checks.py` still says *"whether the count is enough is G11's call"* and G11 went on 2026-09-11, so nothing bounds dilution from below | nothing — `expected_count` and `target_particles_in_field` both exist |
| **L9.6** `step_count` | the number of velocity steps a target error needs. G11's removal entry says it outright: *"a Stokes-drag calibration's precision does not come from N_p × N_f at all: it comes from the number of velocity steps"* | KH's review of the thermal-averaging derivation, σ = √(kT/κ)·√(2τ/T)/√N |
| **L6.5** `independent_samples` | 총 이미지 수, with the correlation-time correction that made G11 3.5× optimistic on this instrument's own calibration | a decision on whether lens 6 computes again at all |

None of the ten retired G-numbers is reused by any of them.

**No check was removed.** The audit looked for a check that judges nothing or
duplicates another and found none; L7.6 and L9.5, which only name who owns
what, were added deliberately on 2026-09-11 and are doing that job.

## Why

**Because a broken handoff and a missing gate look identical from the outside,
and only one of them is fixed by adding a gate.** Lens 4 reported BLOCKED and
L4.6 reported "not evaluated" — both are honest outputs of the design working
as specified, and both meant that six checks with correct physics behind them
had never once run on a real brief. Writing L4.8 on top of that would have
added a seventh.

**And because the threshold question decides what kind of repository this is.**
A `LIMITS` entry is a claim that a number holds for every experiment this
instrument will ever do. A brief field is a claim that this experiment asked
for it. The inventory's multiples are the operator's working rules, not
constants of the instrument, and the difference is exactly the one
`evidence: measured` vs `assumed` exists to track.

## Falsifying condition

This is wrong if **the brief-supplied thresholds turn out to be the same
number every time.** If ten briefs all say 1.5× for the ROI margin, then it is
a property of the bench and not of the experiment, it belongs in
`kb/expertise/` with a falsifier of its own, and asking for it ten times was
ten wasted questions. The test is cheap and should be run at ten briefs.

A second, narrower one: if lens 4 running end-to-end turns out to change no
verdict that a human would have caught anyway — if every brief that now
reaches L4.4–L4.7 gets the same answer the operator already assumed — then the
lens was BLOCKED for months at no cost, and the priority of wiring over
gate-writing was misjudged.

## Not decided here

- **Whether lens 6 computes again.** L6.5 above is written as a report, but
  lens 6 has computed nothing since G11 and 2026-09-11 called that *"the
  honest description of what it was already mostly doing"*. Reversing it is a
  decision about the lens, not about statistics.
- **Whether the other registries have the same hole as `objectives.yaml`.**
  The detector is looked up (`find_detector`); the dye and the filters reach
  the committee only through the channel file, which does look them up. Not
  audited beyond that.
- **What happens to a brief with a wrong type.** A `concentration_per_ml`
  that YAML parsed as a string reaches `sample/setup.py` and raises a
  `TypeError` inside a check. Found while testing, not fixed: the brief reader
  validates provenance and not types.
