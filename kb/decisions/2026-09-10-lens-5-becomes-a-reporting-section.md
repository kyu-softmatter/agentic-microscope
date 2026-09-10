---
id: 2026-09-10-lens-5-becomes-a-reporting-section
question: "Should lens 5 keep gating light-driving and dose, when the sample information those gates need is often absent and mitigations they cannot see are often present?"
date: 2026-09-10
status: current
corrects: [2026-08-19-lens-5-hardening, 2026-09-09-g20-saturation-removed]
---

# 2026-09-10 · Lens 5 stops being a lens

**Decided by KH.** `photo/` is now a **reporting section**: every check `INFO`,
`G21` and `G22` vacant alongside `G10` and `G20`, and out of
`validity.setup.STANDING_LENSES`. It cannot block a proposal and it cannot
bless one.

## Request

> "다른 요소들도 참 중요하긴 한데, 시료에 radical scavanger를 넣기도 하고,
> 시료에 대한 정보가 없는 경우들도 있음. 시료에 대한 정보가 있을 때에만
> 정보로서 제안해주는게 좋을듯."
> — *The other factors do matter, but we sometimes put radical scavenger in the
> sample, and there are cases where we have no information about the sample. It
> would be better to offer it as information only when there IS information
> about the sample.*

Offered three options — condition G21 on sample information, keep it gating only
when photoresponsiveness is confirmed, or demote the lens — and the answer was
**C**.

## Why

**Two things the illumination numbers cannot see.**

*Mitigations that change the answer without changing the irradiance.* A radical
scavenger in the buffer moves the threshold this lens compares against, and the
lens has no way to know it is there. G21 saw W/cm² and never saw chemistry.

*Absent sample information, which is the normal state.* `photoresponsive` was
tri-state precisely so that silence would not read as "no" — but the `None`
branch **warned and entered `assumed_inputs`, so it withheld `advances`**. That
made "we do not know what this sample is" block a verdict, on a question that is
frequently unanswerable at planning time.

**And the lens had already been hollowed out.** G10 went on 2026-09-09 and G20
the same day, both keyed to per-dye constants empty for every dye. What was left
was one graded gate whose commonest branch returned `MAX_MARGIN` with a warning.
The argument that retired G10 — *"a gate that has one answer is not a gate; it
is a reminder, and the reminder had been read"* — had come to apply to the lens
as a whole.

## What changed

- **Every check is `INFO`.** `photo.gate.evaluate` now **asserts** nothing is
  gradeable, so adding a graded check to a reporting section fails loudly rather
  than quietly reintroducing a veto.
- **`status` is `REPORT`** (or `BLOCKED`). `PASS`/`PASS_WITH_CHANGES`/`FAIL` are
  gone: there is nothing here that can pass or fail. `BLOCKED` survives, because
  a report still cannot be written without irradiance and an exposure plan.
- **`feasibility` is `N/A`, not `UNKNOWN`.** `UNKNOWN` is what an ungraded
  *judgement* looks like, and this is not an ungraded judgement.
- **`advances` is `None`, not `False`.** `False` would read as a refusal.
  `to_dict` carries `reporting_only: True` beside it.
- **Out of `STANDING_LENSES`**, so G27 no longer demands a verdict it cannot
  produce. Its absence is **not** an E4 hole — it is not a lens.
- **`G21` and `G22` are vacant.** In this repository a gate number means *this
  can fail and stop or bias the result*, which is the rule
  `tests/test_gate_registry.py` pins; nothing here can.
- **The CLI prints no margins block.** Every entry would be `MAX_MARGIN` with a
  full bar — "lots of headroom" from a section that measured no limit.

## The bug this exposed, which is the best part of it

`_ok()` set severity `"ok"`, and `photo/gate.py` drops those from `findings`. So
`check_total_dose` — whose docstring says *"What it always does is report the
number"* — **discarded that number every time**, because the no-ceiling branch
is the only branch that ever runs (no dye or bead here has a dose ceiling). The
dose was computed into `metrics` and never said.

`_ok` now sets severity `"info"`. On the drag-calibration configuration the
report gained a line it should always have had:

```
[info] perturbation.total_dose
       Total dose 51.25 J/cm^2 over 22120 frames. Duty cycle 23.4%.
       No dose ceiling supplied, so this is reported, not gated.
```

Same correction as `sample/checks.py`'s G16c the same day. **Ungraded and
invisible are different things, and `_ok` conflates them.**

## What this costs

**1. Rank 4 of the operator's own hierarchy has no fence.** `CLAUDE.md` H2 says
light level is *"bounded above by bleaching and light-driving"* and that
**"lens 5's gates are the fence."** There are no gates. Nothing now stops a
proposal that raises the light indefinitely except lens 2's G6 saturation, which
is about the camera and not about the sample. H2's mechanism is gone; its
instruction remains, enforced by whoever reads the report.

**2. Nothing from this section reaches lens 6's bias ledger.** G23 collects
`kind == "bias"`, and there is none. `validity/setup.py` still registers
`perturbation.light_driving` and `perturbation.photobleaching` in `CORRECTIONS`
and `BIAS_SCOPE`, deliberately left as vocabulary — **five registered codes now
have no emitter** (G10's, G17's, G18's, G20's and G21's).

**3. A confirmed photoresponsive sample over its measured threshold no longer
fails anything.** It is reported, in as many words, and acting on it is the
reader's. `docs/06 D2`'s accident — imaging a light-driven sample without
realising — is now caught by reading rather than by refusing.

## Falsifying condition

A run where the illumination drives the sample, the report says so, and nobody
acts on it. That is precisely the exposure this decision accepts, and it is the
reason the light-driving text stayed long and specific instead of becoming a
number.

Narrower and more likely: if a proposal ever raises the light level past what
the sample tolerates and no other lens objects, then H2 needed a mechanism and
not just an instruction — and the answer is a gate somewhere, though not
necessarily here.
