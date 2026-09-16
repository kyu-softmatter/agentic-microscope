---
id: 2026-09-15-an-empty-ledger-is-not-a-clean-one
question: "A check passes and emits nothing. Where does that go, and when is the silence a claim about the proposal rather than about the committee?"
date: 2026-09-15
status: current
---

# 2026-09-15 · An empty ledger is not a clean one

Every gate drops `severity == "ok"` from `findings`. So a check that runs and
passes exists only in `margins` and `metrics` — which no CLI prints, and which
a reader takes for headroom.

**Lens 6 reported it about its own gate**, convened on a real proposal:

> `bias_findings: 0`, `applicable: 0`, `uncorrected_codes: []` — because the
> four lenses that emit bias-kind findings BLOCKED before Phase 1 and produced
> none. **Anyone reading `margins` without `metrics` on this verdict reads the
> opposite of the truth.**

On that run **lens 4 had already identified an uncorrectable near-wall drag on
the intended quantity**, in prose, while the ledger built to catch exactly that
reported m = 10.0.

The gap turned out to live in two places, and they needed different repairs.

## 1 · The gate: say which silence this is

`check_bias_ledger`'s `if not all_bias:` branch returned `_ok` with *"No
upstream lens reported a bias finding, so there is nothing biasing the intended
quantity that the committee knows about."* The wording is careful — *that the
committee knows about* — and it vanished anyway, because `_ok` does.

**The distinction was already available**: `setup.blocked_lenses()` and
`setup.missing_standing_lenses()` both exist. Two reasons a lens reports no
bias, and both now populate a `ledger_empty_because` key:

| | |
|---|---|
| it **BLOCKED** | no verdict to report a bias from |
| it is a **standing lens that never reported** | quieter, and the one `blocked_lenses` alone would miss |

Non-empty, and the branch emits at `severity: "info"` instead of `ok`:

> No upstream lens reported a bias finding — but compute, photo, sample,
> detection produced no verdict to report one from, so this ledger is **EMPTY
> rather than clean**. The margin is MAX because **nothing was weighed**, not
> because nothing was found.

Empty, and `_ok` stays — *"and every standing lens returned a verdict"* added
to the message so the clean case states its own premise.

**The precedent is in the adjacent branch of the same function.** The
`not applicable` branch was changed from `_ok` to `severity: "info"` on
2026-09-11, with the comment *"This branch made a DECISION … As `_ok` both
vanished."* Identical reasoning, applied next door and not here.

## 2 · The seam: a second list, and silence on it is not refused

`designer/judgment.py` had two subject sources — findings, and checks that did
not run. A check that ran and emitted nothing was in neither.

`Packet.may_rule_on` is the third, derived from `margins` minus the emitted
codes, so it needs no gate change and cannot drift.

**It is optional, and the split is the whole point.** Lens 6 wanted the
*ability* to rule on its two; lens 4 had already complained about being handed
eight subjects that wanted eight identical answers. So:

- every code in `must_rule_on` appears in `rulings` or in `unevaluated`, or the
  verdict is refused for `silence`;
- a code from `may_rule_on` may be ruled on and may be left alone;
- **a ruling on an optional subject is checked exactly like an obligatory
  one** — `basis` required, `cleared-a-stop` applied. Offered is not unchecked.

## What the two repairs did to each other

Doing the gate first made the seam's job smaller, and that is the better
outcome rather than wasted work: **lens 6's own two checks are now obligatory
subjects**, because the gate says something about them. `may_rule_on` is empty
for lens 6 and carries lens 4's four quiet passes
(`geometry.na_feasibility` · `depth_in_chamber` · `wall_drag` ·
`count_in_field`).

So the list exists for the general case and the specific complaint that
motivated it was answered upstream of the list. Had the seam been built first,
lens 6's ledger would have become *rulable* while still *reading as headroom*
to everyone who did not rule on it.

## Why Phase 0b made this urgent

[Phase 0b](2026-09-15-phase-0-was-all-or-nothing.md) makes more checks run, so
more of them pass quietly, so a BLOCKED verdict now carries margins it did not
carry before. It widened exactly this gap. `may_rule_on` is drawn from those
margins — the fix and the thing it fixes have the same cause, one commit apart.

## Falsifying condition

**`may_rule_on` fails if reviewers ignore it, and nothing would tell us.**
Silence on an optional subject is not refused, by design, so a list nobody
reads is indistinguishable from a list with nothing worth saying. The
measurable signal is the ratio of optional rulings to optional subjects over
several convenings; if it stays at zero while `must_rule_on` is answered in
full, the offer is decoration and the honest repair is to promote specific
checks rather than to keep a list nobody uses.

**And the gate's fix rests on `STANDING_LENSES` being the right roster.**
`missing_standing_lenses` is what catches the quiet case, and lens 8 is not in
that roster — `validity/cli.py` rejects `stability` as an upstream name and its
own comment calls that arbitrary. So a run where lens 8 was the only lens that
would have reported a bias still produces a ledger that reads clean, and
`ledger_empty_because` will not name it.
