---
id: 2026-09-09-frame-period-is-not-a-gate-input
question: "Should G8 fail a duty cycle computed from a frame period nobody has decided yet, and do G8 and G9 collapse into one gate once the period is factored out?"
date: 2026-09-09
status: current
---

# 2026-09-09 · The frame period is a decision neither G8 nor G9 owns

**Decided by KH** during the lens 2 review. G8 and G9 now consume an explicit
frame rate with a provenance, and **report instead of grading while the rate is
undecided**. They are *not* merged.

## Request

> "G8같이 최소값을 제안/요구하는 경우에는 리밋을 넘어가는 경우를 제외하고는
> 패스할 수 있고, 실제 프레임 레잇은 이후에 다른 서브에이전트의 결과와 함께
> 종합적으로 검토 후 결정할 수 있도록 하자."
> — *A gate like G8 that proposes or requires a minimum should be able to pass
> unless the limit is actually exceeded, and the real frame rate should be
> decided later, reviewed together with the other subagents' results.*

Followed by:

> "즉 G8과 G9가 합쳐지는 모습이 되려나"
> — *So does that mean G8 and G9 end up merging?*

## Why

**G8 was grading a decision nobody had made.** `duty = t_exp / t_frame`, and
`t_frame` came from `frame_period_s(exposure, readout, overhead)` — the
*fastest the camera can go*. That maximises duty, so the gate was silently
assuming the worst case and then failing on it. On the drag-calibration
proposal that put `motion_blur` at margin **exactly 1.00**, which set the
bottleneck and pinned the feasibility grade, all from an assumption rather than
from a setting anyone had chosen.

**And the other side of it was a hole.** G9 graded only when `target_fps` was
supplied and reported `INFO` otherwise, so *no* frame-rate judgement happened at
all in the common case — while lens 3's G12b was simultaneously warning that a
*requested* rate is not evidence. There was nowhere for a **measured** achieved
rate to enter lens 2.

**The right shape is a shared, named, provenanced input.** `Acquisition` now
carries `target_fps` (requested) and `achieved_fps` (observed), with
`decided_fps` and `fps_source` derived so they cannot disagree with the fields
they describe:

| `fps_source` | G9 | G8 |
|---|---|---|
| `undecided` | INFO, reports the realizable rate | **INFO, reports the duty at the camera's floor as an upper bound** |
| `requested` | grades realizability (`hard`) | grades duty at that period |
| `measured` | grades against the observed rate | grades duty at the observed period |

`measured` and `requested` are **the same two tokens as lens 3's
`compute.setup.FPS_SOURCES`**, at KH's instruction, because G12b is this same
requested-versus-achieved distinction seen from the data-rate side.
`test_detection_and_compute_share_the_fps_vocabulary` fails if the two drift
apart. `undecided` is lens 2's only addition — lens 3 always has a rate, since
it cannot compute a data rate without one.

## Why they do not merge

This was the second question and the answer is no, for a reason that is
structural rather than stylistic.

They share `t_frame` and **conflict** over it: lowering duty wants a longer
period, raising the achievable rate wants a shorter one. A shared input plus a
conflict is the definition of a cross-gate constraint, not of one gate.

More decisively, **[05 §2](../../docs/05-consensus-gate.md)'s precedence runs on
the gate's kind, and these two have different kinds.** G9 asks a hardware
question — is this rate reachable — and is `hard`: nobody may overrule it. G8
asks a measurement question — is the exposure a small enough fraction of the
period — and is `bias`: proceed where a correction formula exists, and one does
(Savin–Doyle). A merged gate would have to pick one kind, and both choices are
wrong: as `hard` it would stop a proposal over a correctable MSD bias, and as
`bias` it would wave through a physically unreachable frame rate as if a
correction could recover it.

## What it cost, stated plainly

- **G8 no longer contributes to the feasibility grade in the common case.**
  `INFO` is excluded from grading, so a configuration whose only weakness is
  duty now grades on the other gates. That is the intended trade — the bound is
  still printed in the findings, and it is the *worst case* — but it means a
  reader who skips the `info` lines will not see it. The finding text says
  "UPPER BOUND" and "Not graded" for that reason.
- **Somebody now has to state the rate for G8 to bite at all.** One existing
  test had to gain `achieved_fps=100.0` to keep asserting what it always meant.
  That is the cost of the change made visible: the gate stopped guessing.
- **`decided_fps` is floored at the camera's minimum period** (`max(1/decided,
  t_frame_min)`), because a decided rate faster than the hardware is not a
  period the camera can run. G9 is the gate that reports that contradiction; G8
  should not silently compute a duty from an impossible period.

## The route this opens

The rate is now settled in synthesis, which is where the inputs actually are:
lens 3's bandwidth arithmetic (G12a, and at readout limit the data rate depends
only on ROI **width**), lens 7's `G14` sampling requirement (`f_s ≥ 10 f_c`),
and lens 8's drift budget over the acquisition. On the drag-calibration proposal
those three want 109 MB/s, ≥124–153 fps and short segments respectively, and
553 fps satisfies all of them — a conclusion no single gate could have reached.

Then `achieved_fps` should come from the acquisition's own `ElapsedTime-ms`
series, **as the span across `n−1` intervals rather than the median interval**,
because that metadata is quantised to 1 ms on this build and the proposed period
is 1.808 ms.

## Falsifying condition

An acquisition where the duty cycle at the *achieved* rate exceeds 30 % and the
MSD is fitted anyway, because the bound printed while the rate was undecided was
read as a pass. That is the failure mode this decision accepts by moving G8 out
of the grade, and finding one is the reason to make `achieved_fps` a required
input at plan-check time rather than an optional one.

Equally: if the frame period turns out **not** to be a free variable on this
camera at all — CLAUDE.md §1 records that it takes the exposure as the period —
then `undecided` is a state that never occurs in practice for a real
acquisition, the three-way split is one state too many, and `t_frame_min` was
the honest answer all along.
