---
id: 2026-09-15-stage-2-the-judgment-seam
question: "Code cannot convene a subagent. What can it check either side of one?"
date: 2026-09-15
status: current
corrected_by: [2026-09-15-l1-3-read-a-notch-as-an-overlap]
---

# 2026-09-15 · Stage 2, and the thing it refuses to pretend

**Asked for by KH** the same day the emitter landed: *"stage 2 만들자."*

Stage 1 is the nine `gate.py` modules and it runs end to end. Stage 2 is the
qualitative half of lenses 4 · 5 · 6 · 8 — four subagents in `.claude/agents/`
— and every plan stage 1 writes carries their rows as `unevaluated`, a hole and
not a pass (E4).

## The constraint that shaped this

**Code cannot convene a subagent.** The four agents have `Read`, `Grep`, `Glob`
and nothing else; the main agent convenes them. A `designer` module that called
itself the orchestrator would be a function that quietly does nothing, and the
first plan it wrote would carry four judgment rows nobody produced.

So stage 2 is **two commands and a conversation in between**, and the seam is
shaped so that nothing has to pretend otherwise:

```
python -m designer.cli packets <brief> --out <dir>      # what each lens is handed
        ↓   the main agent convenes the four agents      # not automatable from here
python -m designer.cli emit <brief> ... --judgment ...  # what may come back
```

Both halves are in one module, `designer/judgment.py`. They are one contract:
a schema written out in one file and read back in another drifts the first time
either moves.

**And both halves are files**, which is the planning-layer entry's §3 argument
applied a third time: a boundary only a function call crosses cannot be re-run
from either side.

## What a lens is handed

Four things, and the omissions matter as much as the contents.

| In the packet | Why |
|---|---|
| the lens's own gate `Verdict` | **to interpret, not recompute.** Every one of the four agent files already says the gate is authoritative over it; one of them previously carried a working-distance formula that contradicted the code |
| `carried` — the handoffs into this lens | a judgment lens never generates the number it is judging (§2), so the provenance of every number it will cite arrives with it |
| `must_rule_on` | below |
| `assumed_inputs` | D7: read the `assumed:` line of every verdict, it is the verdict's real content. Listed apart from the rulings because an assumed input is not a finding and cannot be ruled on — it is what the rulings rest on |
| `unevaluated_in_scope` | E4 inside the packet, so the reviewer is not left to infer a pass from silence |

**`must_rule_on` is derived, never declared.** Two sources, both of which
already existed:

- **every finding the lens's own gate emitted** — all of them, not the
  failures. An agent handed only the failures would be reading a filtered
  gate, and the filter would be this module's opinion about what matters.
- **for lens 6, `validity.setup`'s own ledger**: `uncorrected_bias_findings` ·
  `falsely_corrected_bias_findings` · `unverified_corrections`. The middle one
  is why this is not merely "the uncorrected biases" — a bias declared
  corrected for which no correction exists **would have read clean**.

Each bias subject carries the correction that exists, or why none does, from
`CORRECTIONS` / `UNCORRECTABLE`. Without that the reviewer cannot apply §2
precedence level 2 at all: *proceed only where a correction formula exists,
stop where none does*.

The reason for deriving rather than listing is
[the planning-layer entry](2026-09-13-the-planning-layer.md) §1's reason for
the refiner: a checklist maintained beside the code drifts from it, and
`committee reconcile` still reports 7 and 8 because two such tables did exactly
that. A question this module invented would be a tenth place for the same rot.

## What may come back — nine refusals

Each one is a way a judgment verdict can look like a review and not be one.

| Rule | Refused because |
|---|---|
| missing `unevaluated` key | required even when empty; an absent key reads as a cleared one (§3). Refused at **parse** time, since a `Judgment` holding an invented empty list has already lost the distinction |
| `no-basis` | a judgment with no `Why` is not storable (§6) and not reviewable |
| `invented-subject` | a subject this lens introduced is a finding it generated, and a judgment lens never generates the number it is judging (§2) |
| `silence` | a subject neither ruled on nor named in `unevaluated`. Omitting it reads as a pass (§3) |
| `cleared-a-stop` | `accept` on a `hard` finding at m < 1. **§2 precedence level 4 in code**: this lens may refuse to advance what 1–3 cleared; it may not clear what they stopped |
| `out-of-order` | lens 6 returning before 4 · 5 · 8 — E2 |
| `wrong-lens` | the verdict answers a different packet |
| `unknown-status` | not one of the gates' own four words, so the two verdicts could not be read side by side |
| `unknown-ruling` | not `accept` / `refuse` / `unevaluated` |

**`unevaluated` is a ruling, and it is the important one.** A reviewer who
cannot rule on something must be able to say so, or the only way to return a
verdict is to pretend. `unevaluated` ≠ `cleared` holds inside a judgment
verdict exactly as it holds between lenses.

**One refusal writes nothing.** A refused judgment is not a missing one:
writing the plan with the other verdicts would record a review that did not
happen.

## Lens 6 is refused a packet until the others return

E2, enforced on the writing side as well as the reading side. It reviews the
other lenses' verdicts, so a packet built before those exist hands it the gate
results and **silently drops the judgment half of exactly what it is convened
over** — which is the failure E2 exists to name, arriving through the door
marked convenience.

## Four states, because a hole has four causes

| State | What happened |
|---|---|
| `judged` | the verdict came back and survived the nine |
| `convened` | a packet was written and nothing came back |
| `awaiting` | the gate ran and the packet was **withheld** — lens 6 under E2 |
| `absent` | the gate produced no verdict, so there is nothing to convene over. The row carries the gate's own reason |

Collapsing `awaiting` into `absent` was the first version, and it was wrong in
the worst available direction: lens 6's gate had returned FAIL and the row said
its gate produced no verdict.

## What this could not be exercised on

⚠ **CORRECTED THE SAME DAY.** What follows was true when written and is not
now: L1.3 was reading the support hull of a penta-band emission filter and
calling a notch an overlap
([`2026-09-15-l1-3-read-a-notch-as-an-overlap.md`](2026-09-15-l1-3-read-a-notch-as-an-overlap.md)).
`config/briefs/active-microrheology.yaml` **does** reach stage 2: lens 1
returns `PASS_WITH_CHANGES` and `designer.cli packets` writes real packets from
it. The `no packets` path below is still correct behaviour and is still tested
— it just no longer describes this brief.

~~**The only real brief in the repository never reaches stage 2.**~~
`config/briefs/active-microrheology.yaml` stopped in tier 1 — both channels
FAILing L1.3 `spectral.overlap` at m=0.00, and §2 precedence level 1 stops the
run and returns a revision. `designer.cli packets` on a brief that stops there
prints *"no packets"* and the reasons, and **exits 0**: a run with nothing for
stage 2 is an answer, not an error.

So the seam is exercised on a synthetic fixture in
`tests/test_designer_judgment.py`. That is stated rather than hidden: D1 forbids
inventing an **experiment**, and a fixture that drives a code path is not one —
but it is also not evidence that a real proposal survives the seam, and nothing
here should be read as though it were.

## Falsifying condition

Two.

**The nine refusals are wrong if a returned verdict passes all of them and is
still not a review.** The most likely shape: a ruling whose `basis` is present,
sourced and irrelevant — the checks test for the *presence* of a Why and
cannot read it. If that happens the repair is a human reviewer on the rulings,
not a tenth mechanical rule.

**The derivation is wrong if a judgment lens needs to rule on something no gate
emitted and no ledger lists.** `sample-optics` names three such items in its
own file — sample concentration judgement, multiple scattering, ATPS per-phase
reasoning — and today they arrive only as the agent file's prose, so a reviewer
who never opens it will not rule on them and `check_judgment` will not notice.
The honest repair is the one §1 of the planning-layer entry already prescribes:
**add the check to the lens that should have asked**, not a list to this module.
