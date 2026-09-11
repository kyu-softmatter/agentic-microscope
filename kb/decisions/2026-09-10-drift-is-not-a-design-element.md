---
id: 2026-09-10-drift-is-not-a-design-element
question: "Can a planning gate judge a quantity that is only measurable while the experiment runs?"
date: 2026-09-10
status: current
corrects: []
---

# 2026-09-10 · Drift is not a design element — G29 and G30 leave lens 8

**Decided by KH.** Offered two options for G30 (make it refuse like G29, or
delete it), the answer rejected both framings:

> **"실험 중 측정해야한다면 디자인 요소로는 적합하지 않은듯"**
> *(if it has to be measured during the experiment, it is not suitable as a
> design element)*

That is a criterion, not a verdict on one gate, and it applies symmetrically.
**`G29` (axial drift) and `G30` (lateral drift) are vacant and not reused.**
They follow `G28` (PFS lock), which left the same day for a reason this
generalises: `kb/decisions/2026-09-10-g28-moves-to-the-hardware-stage.md`.

The rule to carry forward:

> **A planning gate judges a proposal from what is known before the run
> starts.** A gate whose input arrives during the acquisition is the wrong
> shape regardless of how good the physics inside it is.

## What the two gates were, and why neither shape worked

They were opposite failure modes on the same missing number, which is how the
problem surfaced at all:

| | G29 axial | G30 lateral |
|---|---|---|
| formula | `rate × duration ≤ 0.5 × DOF` | `rate × duration ≤ tolerance` |
| kind | `hard` | `bias` |
| rate in `requires`? | **yes** | **no** |
| so with no rate | **BLOCKED** — refused loudly | **margin 10.00, severity `ok`** — passed silently and `_ok` dropped it from `findings` entirely |

Neither is defensible. G30 was the `_ok` defect for the third time in this
review, and G29's refusal was worse than it looked: **Phase 0 is
all-or-nothing**, so one absent rate returned `BLOCKED` with empty `margins`
and empty `metrics`, taking G31 and G32 down with it even though *their* inputs
were present. The most common verdict this lens produced was a refusal caused
by a gate that should not have existed.

The first instinct — make G30 refuse too, so at least the silence goes — was
recommended and was wrong. It would have made the lens refuse *twice* as often
for a number that, by the criterion above, it should never have asked for.

## The rate was obtainable, and that is not the point

This was checked before deleting anything, because "no data exists" would have
been the wrong reason:

- **Axial.** `config/session/focus_monitor.py` already reads `ZDrive` and both
  cameras several times a second and records a focus score per camera against
  the Z it was measured at. A run logs its own drift.
- **Lateral.** `data/particles.yaml` records that 8 of 21 beads sat below
  110 nm of measured motion, p10 at 10.5 nm — **most of the population is
  immobilised on the coverslip.** The fiducial is already in the sample, in the
  same frames, at no extra acquisition cost.

So both rates are cheap. They are cheap **from the acquisition**, which is
precisely the wrong timing for a gate on a proposal. `compute.drops` is the
precedent for where that work belongs: it judges an acquisition that already
ran, from its own timestamps, and does not pretend to be a gate on a plan.

## What replaced them: publish the requirement, not the measurement

`stability.drift_budget` (INFO, unnumbered) inverts the question. Duration and
depth of field are **both planning inputs**, so the tolerance *is* a design
quantity even though the rate is not:

```
axial_rate_for_one_dof_nm_per_min  = depth_of_field_nm / duration_min
axial_rate_for_half_dof_nm_per_min = half of that
```

One division, and **no threshold** — one full DOF is a definition, and the half
is printed on the same line so the reader picks their own fraction. The
`axial_drift_dof_fraction = 0.5` constant went with G29; nothing replaced it.

On the 100x oil (DOF 0.375 µm) over 60 min that reads **6.3 nm/min for a full
DOF, 3.1 nm/min for half** — tighter than most intuitions about a good optical
table, which is the reason to print it. The lens now hands the hardware stage a
number to be judged against instead of asking the operator for one.

Severity is `info`, never `ok`, so no `gate.py` drops it from `findings`. That
is the rule established earlier in the same review: **ungraded and invisible
are different things, and a report that must be seen cannot use `_ok`.**

## The cost, accepted deliberately

The drift entry in `stability/gate.py::_assumed_inputs` is now
**unconditional**. There is no planning input that can retire it, so:

- lens 8 can never report `evidence: measured`, and
- a long acquisition never `advances` on lens 8's say-so alone.

This is the intended reading, not a bug to be fixed later. Drift is the
dominant bias on a long run and **planning it well does not discharge it** —
the run's own frames do. A lens that could report `measured` on drift from
planning inputs alone would be lying about the one thing it most needs to be
honest about.

A second consequence, worth knowing before reading a verdict: **no `hard`-kind
check remains in this lens.** Both HARD gates (G28, G29) are gone, so lens 8
cannot return `FAIL` on its own — G31 and G32 are `bias` and cap at
`PASS_WITH_CHANGES` while dragging `feasibility` down. `PASS_WITH_CHANGES ·
INFEASIBLE` from lens 8 is not a contradiction.

## What changed

- `stability/checks.py` — `check_axial_drift` and `check_lateral_drift`
  excised; two `Check` registry entries and `axial_drift_dof_fraction` removed;
  `check_drift_budget` added (INFO, no `requires`); module docstring records
  where all three gates went
- `stability/setup.py` — `axial_drift_rate_nm_per_min`,
  `lateral_drift_rate_nm_per_min` and `lateral_tolerance_um` removed. **The
  absent fields are the enforcement**: a caller asserting a rate now gets
  `TypeError`
- `stability/gate.py` — `missing.axial_drift_rate` removed from `_missing_inputs`
  (with it, the Phase-0 short-circuit that was taking down G31/G32); the
  `_assumed_inputs` drift entry made unconditional
- `stability/cli.py` — three flags removed; the docstring says why there are no
  drift flags, so the absence does not read as an oversight
- `stability/drift.py` — `total_drift_nm` **kept**, with a comment that no gate
  calls it any more and the analysis stage is its consumer. The formula is not
  wrong; its timing was
- `stability/__init__.py`, `docs/04`, `docs/05`, `CLAUDE.md`, `README.md` —
  G29/G30 marked vacant; gate count 26 → **24**, implemented 23 → **21**
- `.claude/agents/mechanical-env.md` — the G28/G29/G30 sections replaced by one
  that says what to report instead, and **not to ask for a drift rate**; the
  Phase 0 table, the division-of-labour table, the Phase 2 aggregation rules
  and the worked example all corrected. This file had never been updated for
  G28 either, so it was describing five gates when the code had two
- `.claude/agents/measurement-validity.md` — the G30 bias-ledger row struck
  through with what to read instead (the unconditional evidence downgrade), and
  a G31 row added, which had been missing
- `validity/setup.py` — the two `stability.lateral_drift` registry entries kept
  but marked **dormant**: nothing emits the code at planning time, and the
  remedy named there is still the right one for the stage that will
- `tests/test_stability_gate.py` — three drift tests replaced by five: both
  gates absent, all three fields rejected, the budget's arithmetic and its
  scaling with duration, and that it is visible rather than graded
- `tests/test_gate_registry.py` — snapshot, `LIMITS`, `VACANT_GATES` (now eight
  numbers) and the unnumbered-check set updated

1239 passed, 11 skipped.

## Falsifier

Somebody shows a drift figure that is **a property of the instrument rather
than of a run** — a table specification, a thermally-characterised enclosure, a
measured rate with a stated reproducibility across sessions. Then the rate is
known before the run starts, the criterion above does not bite, and a gate on
it is the right shape after all. Note what that would take: not one
measurement, but a demonstration that the number transfers between sessions.
`drift.py` already records the reason to doubt it — thermal drift is worst in
the first hour after the enclosure is disturbed, so a rate depends on enclosure
history, not just on the instrument.

The weaker falsifier: if the hardware stage never implements the drift
judgement, this decision has not moved the check, it has deleted it. The
budget report is what makes that visible — it states a requirement on every
long run, so an unanswered requirement is a loose end someone can see.
