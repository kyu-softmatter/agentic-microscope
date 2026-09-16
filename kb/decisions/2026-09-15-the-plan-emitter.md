---
id: 2026-09-15-the-plan-emitter
question: "What does the designer write down, and what did writing it find?"
date: 2026-09-15
status: current
corrected_by: [2026-09-15-l1-3-read-a-notch-as-an-overlap]
---

# 2026-09-15 · The plan emitter, and the four holes it found

The designer's stage-1 runner has produced verdicts since 2026-09-14 and
nothing serialised them. `designer/emit.py` and `designer/cli.py` close that:
`python -m designer.cli emit` writes both halves of a plan and then validates
the `.md` it just wrote with `knowledge.plans.check_plan`.

**The emitter was the easy half.** Four defects upstream of it were found by
trying to write a plan and reading what came out, and all four have the same
shape: **a silence that reads as agreement.** They are the content of this
entry; the serialiser is not.

## R1 · An order is not a handoff — L3.2

`designer/run.py`'s `INTRA_TIER` said, in as many words, *"L3.2 is judged
against lens 2's `fps_usable_max`"*, and ordered lens 2 before lens 3 for it.
Nothing passed the number. So on every brief with a requested frame rate L3.2
emitted `fps_provenance.requested` — `warn`, `MAX_MARGIN`, grading nothing —
which reads from outside as a bias nobody could bound rather than a wire never
run. [CLAUDE.md §2 E5](../../CLAUDE.md) is the rule that check exists to
enforce, and it was enforcing it against `None`.

Carried as `build_compute(brief, detection=...)`: a **Setup**, not a `metrics`
lookup by string key, for the reason the 2026-09-14 entry gives.

On the test geometry — 40× WI, 512 px ROI, Sensitivity, 10 ms exposure, 100 fps
requested — the camera reaches 100 fps and L2.4's duty limit allows 30, so the
request is unrealizable by 3.3× and now **says so with margin 0.30**.

**One definition of the window.** `fps_at_duty_limit` was already derived twice,
in L2.4 and in L2.5, and lens 3's ceiling is a third reader.
`DetectionSetup.frame_rate_window()` returns the triple — hardware ceiling,
duty ceiling, the usable rate between them — plus which end binds, and all
three read it. **Both ends must exist for `fps_usable_max` to:** one bound
reported as the window is a single bound reading as a cleared pair (§3).

## R2 · Lens 2 had never reached Phase 1

`build_detection` passed no `PhotonBudget` and `config/briefs/_template.yaml`
had nowhere to carry one, so lens 2 BLOCKED with `missing.photon.signal` on
**every brief the designer ever ran** — and its Phase 0 is all-or-nothing, so
L2.1, L2.4, L2.5 and L2.6 went down with it on inputs that were all present.

Same shape as the objective-registry hole found the day before, one lens wider.

The two rates stay R2 and uncomputable (docs/04 §3, §4): this lens *takes*
k_det and does not re-derive the chain lens 1 owns, so a brief that is silent
still BLOCKs, correctly. What changed is that a brief carrying them is now
believed. The active brief gains the two R2 gaps — it could not have declared
them before, because nothing consumed them.

### And a crash the photon hole was hiding

`check_sampling` divides by `wavelength_em_nm`; `available_facts` never listed
it and the `sampling` `Check` did not require it. So a setup with no emission
wavelength **cleared Phase 0 and raised `TypeError`** out of L2.1 — invisible
for as long as the only caller was a CLI whose `--wavelength-em-nm` was
required. Now a named `missing.wavelength`.

## R3 · Half the light path was never judged

`optics.gate.evaluate` judges **one** channel against its siblings, and
`run.py` called it on `channels[0]`. For the only two-colour brief in the
repository that left the second arm's entire light path unexamined — and an
unexamined path is reported as nothing at all, which reads as a pass.

Worse in one specific way: crosstalk is *why* `evaluate` takes `others`, so
judging only channel 0 does not even get crosstalk right in one direction. It
asks whether channel 0 leaks into the rest and never whether the rest leak into
channel 0.

`LensRun.per_channel` keys a verdict by channel name; `verdict` stays channel
0's so **no ordering is invented** over the rest. The tier-1 hard-failure scan
reads every channel: a `hard` failure in the second arm stops the run exactly
as the first arm's does, and it had no way to be seen.

Both channels of `active-microrheology` FAIL L1.3 `spectral.overlap` at m=0.00.
Only one of those two failures was visible before today.

⚠ **And neither failure was real** -- L1.3 was reading the support hull of a
penta-band emission filter and calling a notch an overlap
([`2026-09-15-l1-3-read-a-notch-as-an-overlap.md`](2026-09-15-l1-3-read-a-notch-as-an-overlap.md),
same day). The sentence above still stands as written: the per-channel change
is what made the red arm's verdict visible at all, and so is how BOTH were
found to be wrong rather than one.

## R4 · Two states that were printed as one

A lens the tier-1 stop cut off printed its seat's reason for being **convened**
— "standing lens (01 §4)" — as its reason for **not running**. That reads as a
lens that had nothing to say rather than one the run never reached. It is a
fourth state, `not_reached`, beside `absent` · `undecided` ·
`not_constructible`.

The verdict table and the `unevaluated` list below it also disagreed, because
the table read the seat and the list read `unevaluated` — one run described two
ways on one page. Both now read `unevaluated`.

## What the emitter itself decides

**`verdicts` is enumerated from `margins`, not `metrics`.** `margins` is
`{result.code: margin}` in all nine gates; `metrics` is that in eight and a
flat dict of metric *names* in `optics`. Reading `metrics` gave lens 1 nine
rows called `resolution_nm` and `depth_of_field_nm`, none of which is a check,
and lost every real one. A uniform field beats a nearly-uniform one.

**Two keys beyond the template's sketch**, each because a reader could not
otherwise tell one silence from another:

| Key | Why it is not part of another list |
|---|---|
| `lenses` | the lens-level answer. A BLOCKED lens has **no** rows under `verdicts` — nothing graded — so without this a refusing lens and a clean one look alike |
| `unevaluated_judgment` | 4 · 5 · 6 · 8's subagent halves, which stage 1 can never convene. Separate from `unevaluated` because the causes differ: the roster decided one, and stage 1 not existing decided the other |

**Addresses come from `committee.collect_all()`**, not from a table here. A
hand-written code → address map is the drift `committee/` was built to stop,
and it would go stale on the next gate change exactly as the bias registries
did twice.

**A gap may name the code it answers.** `Gap.answers` is optional and exists
because the alternative was worse: matching gap to code by substring called
`target_relative_error` a field the brief had not predicted — it had, under
exactly that name, and the emitted code is `missing.target_error`. That count
is reported as a measure of the *brief's* quality, so a false surprise in it is
a false accusation. The substring fallback stays for the gaps that make no
claim; it is wrong in both directions and only one of those directions matters.

**Lens 9 does not decide `piezo`.** A commanded velocity on this bench can be
the stage *or* the steered trap — the active brief's is the trap — so convening
lens 9 says a motion is commanded and not which device commands it. The brief
states `meta.subsystems` or the plan does not claim it.

**`emit` refuses to overwrite either half**, on the same grounds as
`config/micromanager/set_pixel_size.py`: a plan is written *before* a run and
may already have been read by a person or acted on by a skill.

**`--out` has no default and `kb/plans/` is not one.** Writing there also means
running `knowledge.cli write` and reviewing the entry, which is a decision and
not a side effect of a CLI invocation (CLAUDE.md §6).

## What is still not written

`plan.md`'s **Preconditions, Sequence and Stop conditions are emitted empty**,
each under a line saying why. Every row in them is confirmed by something
*observed* and this runner observes nothing (SAFETY §0, E9); a stop condition
names the state an abort leaves the instrument in, which is a fact about
devices it never touches. **A section empty because nobody wrote it looks
exactly like one with nothing in it**, so the file says which it is.

`plan-check` passes on a Sequence table with a header and no rows, and that is
the correct reading of a stage-1 plan rather than a gap in the check.

## Falsifying condition

A fifth defect of this shape found in the same place would mean
`tests/test_designer_emit.py` covers the serialiser and not the pipeline — the
tests here assert holes are *named*, and a hole nobody thought to look for is
not among them. The measure to watch is the emitted
`unresolved[].predicted_by_brief`: it counts what the gates asked for that the
brief did not know to ask, and it is 2 of 37 on `active-microrheology` today.
Dropping to 0 would mean either the brief caught up or the harvest stopped
reporting.
