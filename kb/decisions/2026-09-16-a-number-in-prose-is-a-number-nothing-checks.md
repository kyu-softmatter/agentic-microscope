---
id: 2026-09-16-a-number-in-prose-is-a-number-nothing-checks
question: "Hard rule 2 says a plan originates no physical number. What actually enforced that, and what does now?"
date: 2026-09-16
status: current
---

# 2026-09-16 · A number in prose is a number nothing checks

**Nothing enforced hard rule 2 before this.** `plan-check` validated a plan's
sections, its subsystems and its confirmation column — the *shape* a hardware
skill reads — and said nothing about the numbers. Three failures in two days,
all the same shape, paid for the fix.

## Request

None. This came out of an inter-repository exchange finding an error in a number
this repository had sent, and then a second and a third of the same kind while
the first was being corrected.

## The three, because the pattern is the point

| | what was wrong | what should have caught it |
|---|---|---|
| **The blur coefficient** | `2*D*t_exp/3` is the **free-particle MSD** term. A trapped bead's is `u/3`. Every entry of one table column was twice too large, for two rounds, and reached the other agent as this instrument's arithmetic | a structured block the prose cites |
| **Three dead citations** | Three `kb/decisions/` links pointed at entries that exist only on `version2` — including the source of the ROI, the exposure and the 520 fps | anything that reads a link |
| **Six unreachable tiers** (other side) | `tier` values in the first ask were not derivable from the evidence that produced them, and propagated by copy into three later rounds | the same: a declared field nothing re-derives |

**None of them was a wrong calculation.** Each was a number sitting in text,
where the only thing between it and a reader is somebody re-reading it. The blur
term survived two rounds of adversarial review by two agents *because it looked
like prose.*

## Why

**A plan is prose because the operator reads it**, and that is not negotiable —
the Sequence table's `Confirmed by` column exists because a person at the
instrument needs sentences, not a schema. So the plan cannot stop being prose;
what it can gain is a second half that a check can read.

Hence `kb/plans/<slug>.json` beside `kb/plans/<slug>.md`, same slug — one run,
one name, two readers — with **the structured block authoritative and the prose
citing it**. Each entry carries `symbol · value · unit · source · evidence ·
role`, using the bridge protocol's own evidence vocabulary so an exported ask
needs no translation.

**`plan-check` now refuses**, where a sidecar exists:

- a number in the settings table with no structured entry;
- a `role: threshold` sourced from `kb/external/` — hard rule 3 held where
  provenance still exists, since a gate receives a bare float;
- an `assumed` `fact` whose source does not name what would resolve it.

And **independently of any sidecar**, it refuses a citation that resolves to
nothing, and any citation of `kb/INDEX.md`. The index always exists, so that is
the one bad citation a resolution check cannot catch, and it leaves a reader one
indirection short of the entry that would have changed the answer.

## What it does not cover, and this is the important paragraph

**The scope is the `Value` column of *Proposed setting + rationale*. The plan's
derived tables are not covered — so the blur coefficient that motivated all of
this would still get through today.**

That is deliberate and temporary. Catching that class needs the declaration to
be **per column and to carry the formula** (`u/3, u = t_exp/tau_k`), which is
also the artefact that would have made the wrong coefficient reviewable: nobody
reviewing `1.21 %` in a cell can see which formula produced it, and everybody
reviewing `2u/3` beside `u/3` can. `tests/test_plan_sidecar.py` pins the current
limit with a test, so it cannot quietly become untrue.

**And it is not retroactive.** Backfilling a sidecar from prose would put
numbers into a structured block with nobody re-deriving them — the same act that
produced the blur coefficient. A plan without a sidecar is checked exactly as
before.

## The other half: a precondition that reads closeable

The same session found P7 — "run the slope fit on the 2026-09-03 data" — written
as a checklist item, so it read as a minute's work, while the data was on
another machine and the existing pipeline (`creepx`) detrends the mean
displacement away by design.

**Operator instruction (KH, 2026-09-16):** expand P7 in the plan itself, and
build it so **a plan can be produced on another computer too** — read the value
from the file where it lives, then store it in `kb`. Refined the same day:
producing a plan does not require being on site, so the fit is not tied to the
instrument computer.

So `python -m calibration.cli drag-slope <tracked-positions> --settle-s 0.056`:
numpy only, no instrument, no Micro-Manager, no MATLAB, no edit to `D:\codes`.
It writes a `kb/calibrations/` entry carrying the input's `source_hash`, the
machine as *provenance rather than requirement*, `evidence_class: measured` and
`verified: false`. **Being measured on this instrument is what makes it
admissible as a gate threshold**, which no `kb/external/` entry is — that is the
whole asymmetry of the previous decision, seen from the other side.

## Falsifying condition

**This is wrong if the sidecar becomes an inventory nobody reads.** The failure
mode is specific and recognisable: entries whose `source` says "proposal" with
no entry named, added to silence the check. If that appears, the rule is
generating compliance rather than provenance, and the fix is to narrow what must
be declared rather than to keep the field.

It is also wrong if a number that matters goes wrong *again* inside the covered
scope. One escape there and the column-and-formula extension stops being the
next step and becomes overdue.

## Open

- **Per-column declarations with formulas** — what would actually catch the blur
  class. Named above.
- **The `ask_simulation.json` writer** is still hand-written. The sidecar is its
  input and now exists, and the shape has run twice by hand, which was the
  stated condition for automating it.
- **The tracked positions of 2026-09-03** are still unidentified — the one step
  in P7 that no code here can take.
