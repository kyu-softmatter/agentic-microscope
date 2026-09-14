---
id: 2026-09-13-the-planning-layer
question: "A research goal arrives as an open question. What turns it into a checked experiment plan, and who is allowed to fill in what it did not say?"
date: 2026-09-13
status: current
---

# 2026-09-13 · The planning layer: a refiner in front of the committee

**Asked for by KH.** The committee judges a proposal; nothing yet turns a
research goal into one. *"1차 목표는 decision maker (experiment designer와 질문
리파인을 하는 층을 구성할거야)."* Two new layers in front of the nine lenses,
and two output files behind them.

```
사람의 질문 (자유 형식)
      ↓
Query Refiner ──→ brief.yaml ──→ Experiment Designer ──→ plan.md + plan.yaml
      ↑                                                        ↓
  Librarian MCP (별도 구축 중)                          Hardware Orchestrator
```

This entry fixes the contracts between them. It does not design the lenses,
which are unchanged.

## 1. The refiner harvests; it does not declare

**Every lens already carries its own question list.** `_missing_inputs()`
exists in `validity/gate.py`, `velocity/gate.py`, `stability/gate.py` and the
rest, and each `missing.*` finding already carries a human explanation and an
`action` naming what would resolve it — CLAUDE.md §3's *"a refusal names what
would resolve it"* is enforced in code, not in prose.

So the refiner **runs the gates on a skeleton setup and collects the
`missing.*` findings**. It owns no checklist of its own.

The alternative — a hand-written list of what to ask — was rejected for the
reason `committee/` was built two days earlier: a table maintained beside the
code drifts from it, and `python -m committee.cli reconcile` is currently
reporting 7 orphan registrations, **five of which are lenses 5 and 8's codes
left behind when those lenses became reporting sections**. A refiner with its
own list would acquire the same drift, and unlike the bias registries nothing
would be watching it.

**Derived, not declared** — the same rule, its second application.

## 2. A fourth rank, and why it is not one of the three that exist

The refiner needs to sort a missing fact by **who can resolve it**. That is not
a question any existing ordering answers, and this repository already warns
twice that conflating its orderings is the error to avoid (CLAUDE.md §1, §2).
For the record, the ones that exist and what each governs:

| Existing | Governs |
|---|---|
| README item 9 | procedure — how the frame-rate triple is picked |
| CLAUDE.md §1 hierarchy | axes — which yields when they cannot coexist |
| CLAUDE.md §2 precedence | verdicts — gate kind outranks lens |
| `evidence` (`measured`/`assumed`) | whether a verdict may `advance` |

The new one is the **resolver rank**, and it sorts inputs rather than verdicts:

| | Who resolves it | Refiner's action | Examples |
|---|---|---|---|
| **R0** | the KB already has it | Librarian MCP fills it. **The human is not asked** | objective NA, pixel size 0.06453, disk bandwidth |
| **R1** | only the human knows | asked — once, as a list | goal, sample, duration, target precision, `intended_quantity` |
| **R2** | measurable, not yet measured | `BLOCKED`, and the item joins the **calibration queue** | `power_at_sample_mw`, L9.1's time base |
| **R3** | nobody knows | recorded as ungated, explicitly, and the run proceeds | per-dye constants, vibration, 1064 nm local heating |

**R1 and R2 are the split that matters.** The first is resolved by
conversation and the second never is. Today both leave a lens as `missing.*`
with no way to tell them apart, so **the rank is the one genuinely new piece of
information** — a constant tagged once per `missing.` code, not a second
declaration of the code itself.

### R1 with no answer: propose a default, brand it `assumed`

Decided by KH, 2026-09-13, over stopping at `BLOCKED`. When the human does not
know or defers, the refiner **proposes the KB's standing choice and records it
in `brief.yaml` as `evidence: assumed` with the entry it came from**.

This is not a breach of CLAUDE.md rule 2. The number comes from
`kb/expertise/microrheology-standard-conditions.md`, not from the model, and
the existing `advances` axis does the rest: a plan built on an assumed input
**computes and reports but cannot advance**. The operator gets a plan to react
to instead of an interrogation, and the cost is visible in the one field that
already exists to carry it.

R2 keeps `BLOCKED`. A default cannot stand in for a measurement nobody has
taken.

## 3. Three artifacts, not two

KH asked for two output files. The contract needs three, because the boundary
between the two layers is only testable if the thing crossing it is a file —
otherwise the refiner cannot be re-run without the designer, or the reverse.

| File | Reader | Home |
|---|---|---|
| `brief.yaml` | the designer | beside the plan |
| `plan.md` | the operator | `kb/plans/YYYY-MM-DD-<slug>.md` |
| `plan.yaml` | the orchestrator, and any re-check | `kb/plans/YYYY-MM-DD-<slug>.yaml` |

### `plan.md` is the existing plan format, not a new one

`kb/plans/_template.md` is already the prose form of exactly this, and
`python -m knowledge.cli plan-check` already validates it: six required
sections (`Request`, `Proposed setting + rationale`, `Committee verdict`,
`Preconditions`, `Sequence`, `Stop conditions`), an unknown subsystem refused,
a `Committee verdict` silent on what was **not** evaluated refused, and a
`Confirmed by` cell resting on a return code refused — SAFETY §0 held at the
plan instead of at the instrument.

The designer writes that shape and inherits the validator. Deciding a second
prose format would mean writing a second validator or going unchecked.

### `plan.yaml` must swallow the channel schema, not sit beside it

`config/channels/*.yaml` is already what `python -m optics.cli check` consumes.
`plan.yaml` carries that schema verbatim under `channels:` so the plan can be
re-checked directly, rather than restating the same facts in a second shape —
CLAUDE.md §7, one definition one file.

```yaml
brief:    {ref: brief.yaml, sha256: ...}
channels: [...]                      # config/channels schema, unchanged
acquisition: {fps: ..., fps_source: measured|requested|undecided, duration_s: ...}
verdicts:
  - {lens: 2, addr: L2.4, kind: bias, status: ..., m: 0.82, evidence: assumed}
unevaluated: [{lens: 8, why: "under 30 min"}]
unresolved:  [{code: missing.power_at_sample_mw, rank: R2, action: "..."}]
```

`unevaluated` and `unresolved` are **required keys even when empty**. An absent
key reads as a clear one, and `unevaluated ≠ cleared` (CLAUDE.md §3) is the
whole reason `plan-check` already refuses a silent "Not evaluated" section.

## 4. Call order is the committee's, unchanged

The designer does not invent an order. CLAUDE.md §2 already fixes it, and the
refiner sits entirely in front of it:

```
refiner (R0 fill · R1 ask · R2/R3 record)
   ↓  brief.yaml
1 · 2 · 3  (+7 trap, +9 motion)   code, parallel     → any hard m<1 stops here
   ↓
4 · 5  (+8 over ~30 min)          subagents, parallel
   ↓
6                                 subagent, alone, last
   ↓
plan.md + plan.yaml
```

## Why

Two reasons, and they are different.

**The refiner exists because a research goal is under-specified by
construction, and the alternative to asking is guessing.** An operator's
question does not carry `intended_quantity`, and `validity/gate.py` already
says in so many words why that one omission cannot be papered over: a wrong
pixel size ruins a diffusion coefficient and is irrelevant to a stoichiometry.
Without a refiner the model fills those gaps silently, which is precisely the
failure rule 2 exists to prevent.

**The two output files exist because the plan has two readers with opposite
needs.** The operator needs to know what was conceded and why, in sentences;
the orchestrator needs the parameters without the sentences. One file serving
both gets skimmed by the first reader and parsed with a regex by the second.

## Falsifying condition

This design is wrong if **the `missing.*` findings turn out not to span what a
refiner must ask.** The claim is that the union of the nine lenses'
`_missing_inputs()` is the complete question list. If a real research goal
produces a necessary question that no gate emits, then the refiner does need
knowledge of its own and §1 is wrong — and the honest repair is to add the
check to the lens that should have asked, not a list to the refiner.

A second, narrower falsifier: if operators routinely answer "알아서 해줘" to
R1, `brief.yaml` fills with `assumed` and **no plan ever advances**. The
default-proposal rule would then be producing plans that are pleasant to read
and unable to authorize anything, and R1 would have to move toward `BLOCKED`
after all.

## Not decided here

- **The version2 decomposition axis.** This session diagnosed four places the
  nine-lens subsystem split has come apart and put three re-cuts on the table —
  gate-kind-first, stage-first, quantity-graph. **None was chosen**, and the
  planning layer above is deliberately neutral to all three. The diagnosis is
  this session's reading of the repository's own records, not an operator
  statement, and it is not a source.
- **Whether `calibrate` is a stage or a precondition.** R2's queue is the same
  list as docs/07 Phase 0. If it becomes a first-class stage, Phase 0 stops
  being prose.
- **Whether any of the ten retired gate numbers return.** An execute-time stage
  would make G29/G30 candidates. KH's 2026-09-10 judgment that a
  during-the-run measurement is not a design element **stands**; reviving them
  would extend it, not reverse it, and would need new numbers.

## Diagram corrections (2026-09-13)

The architecture diagram KH is working from predates the last two weeks:

| Diagram | Current |
|---|---|
| "30 Deterministic Gates" | **48 checks**, addressed `L<lens>.<n>`; 22 `hard` · 6 `bias` · 3 `soft` can fail, 17 `info` report |
| Photo stability · Validity · Environments drawn as judging | lenses **5 and 8 are reporting sections**; lens **6 computes nothing** (`LIMITS` empty) |
| eight lens boxes | **nine** — `velocity` (lens 9) is missing |
| all lenses in one parallel block | **lens 6 runs alone and last** (CLAUDE.md §2 E2) |

---

## Correction, same day: the harvest is necessary and not sufficient

§1's claim — that the union of the lenses' `missing.*` findings is the question
list — was tested against the code the hour it was written, and it is **too
weak as stated**. Recorded here rather than in a new entry, because a design
and the measurement that bounds it belong together.

**Only 18 of the 48 checks answer `BLOCKED` when their input is absent**, and
`BLOCKED` is what emits a harvestable `missing.*`. The `If missing` column of
[04 §7](../../docs/04-decision-engine.md) has six distinct behaviours:

| `If missing` | n | Harvestable | |
|---|---:|---|---|
| `BLOCKED` | 18 | yes | the refiner's whole visible surface |
| `INFO` | 13 | no | mostly harmless — an `info` check reports either way |
| **`skipped (INFO)`** | **5** | **no** | ⚠ the check does not run, and nothing says so |
| `computable` | 5 | n/a | needs no input |
| `measurement required` | 3 | no | **this is R2, already named** |
| `ask` | 2 | no | **this is R1, already named** |
| `FAIL` | 1 | no | L9.1 |

Two findings, in opposite directions.

**In the design's favour: R1 and R2 were not invented here.** `ask` and
`measurement required` are already distinct values in 04 §7's table, in 5 rows
of 48. The resolver rank formalizes a distinction this repository was already
making by hand — it just was not machine-readable and was not applied to the
other 43.

**Against it: three facts the operator simply knows produce total silence.**
Measured 2026-09-13 on `sample.gate.evaluate`, with an objective and an
`imaging_depth_um` supplied and nothing else:

```
status: PASS | evidence: assumed | advances: False
  [info] geometry.ri_mismatch     Index-matched: mismatch 0.0000 ...
  [info] geometry.depth_window    Focal plane may sit anywhere up to 380.0 um ...
  [info] evidence.assumed         ... coverslip thickness (assumed)

  L4.3 chamber height  (hard) : silent
  L4.4 particle radius (bias) : silent
  L4.6 concentration   (info) : silent
```

`chamber_height_um`, `particle_radius_um` and `concentration_per_ml` are all
fields of `SampleSetup`; none of them was asked for and none of their checks
ran. The verdict is **`PASS`**, and its `advances: False` is owed to the
coverslip, which is unrelated. The depth window reports the full 380 µm
working-distance budget as available, which reads as permissive when the real
state is that no chamber is on record.

This is CLAUDE.md §3's own rule — **`unevaluated` ≠ `cleared`** — broken inside
a gate rather than by a reader.

### What the repair is, and what it is not

The entry's falsifier already named the correct repair and it holds: **add the
question to the lens that should have asked it, not a list to the refiner.**
Concretely, `skipped (INFO)` has to stop being a behaviour. A check whose input
is absent must say so, with a resolver rank attached, and a `hard` check must
never let a proposal reach `PASS` without running.

So the refiner's contract in §1 stands, and gains a precondition:

> The refiner harvests `missing.*`. **That is only complete once every check
> declares what it needs and what happens when it is absent** — one
> `if_missing` value per check, drawn from the resolver rank, replacing the six
> ad-hoc behaviours 04 §7 records today.

That declaration is a property of each check, so it is subject to the same rule
`committee/` established: it must be **parsed from the code, not declared
beside it**, or it acquires the drift this layer exists to prevent.

### Status

`sample`'s three silent checks are a defect, not a design gap, and they are
**open**. Whether the other lenses share the shape is unmeasured — only
`sample` was tested, because it holds 3 of the 5 `skipped (INFO)` rows. L1.5
and L1.7 are the remaining two and are both `info` kind, so the same silence
there costs less.

---

## Addition, same day: the plan states the whole machine, not only the judged part

**KH, 2026-09-13:** the plan should carry *"하드웨어의 모든 파라미터 중 실험에
영향을 주는 주요 파라미터와 큰 영향을 주지 않는 세부 파라미터를 모두"* — every
parameter the hardware can be set to, partitioned by whether it matters.

This changes `plan.yaml`'s contract. It stops being the committee's output and
becomes **the machine's complete state**, of which the committee's output is a
subset.

### The partition is derived, not editorial

Which parameters are "major" is not a judgement call:

| | Definition | What the section is |
|---|---|---|
| **major** | consumed by at least one check | the axes the gates defend — everything a plan carries today |
| **detail** | settable, and **no check reads it** | ⚠ the complete list of **unevaluated axes** |
| **off-ledger** | settable, and MM does not record it | Principle 3 — trap power, piezo, LUN-F per line, temperature stage |

The middle row is the one that does not exist anywhere today. `unevaluated` is
currently sayable per lens (§2 E4) and not per parameter, so **`unevaluated ≠
cleared` has never been countable.** Deriving the partition from what the
checks consume makes it countable, and makes it move on its own whenever a
check is added or removed — the `committee/` rule again.

### Two halves, and only one of them is a script

| Half | Source | State |
|---|---|---|
| MM-registered | `hardware/microscope.py:419` `Microscope.settable_properties()` — `getDevicePropertyNames` filtered by `not isPropertyReadOnly`, over every device | **Written, never run to produce a dossier.** Needs the MM device-adapter install (the same dependency as the 56 CI-skipped tests). The seven `.cfg` files are **not** this list: they carry 29 `Property,` lines of *startup state*, not the settable surface |
| off-ledger | `hardware/` modules, `reference/npcd-command-set.md`, and **KH enumerating the bench** | Not reachable by code |

### Why the second half cannot be a script, on this instrument's own evidence

`kb/systems/current.md > devices_not_in_mm_config` carries the
temperature-controlled stage, and that entry argues this case better than any
principle could:

> *"It was not missed by a bad scan — **nothing enumerable would have found
> it**, because it is not in any `.cfg`, has no MM adapter loaded, and no
> script has ever addressed it."*

It reached the repository on 2026-09-06 because KH listed hardware out loud.
Before that there were **zero** mentions of it in any file — while the
2026-09-04 wall-diffusion result carried "sample temperature at the coverslip
(3–8 %, one-sided, UNMEASURED)" as the first line of its error budget. A device
that *controls* the dominating quantity sat on the bench for the entire period
in which the budget was written around not having one.

So the exhaustive parameter list is not a completeness nicety. **It is the
artifact that would have caught that a year earlier**, and it is also proof
that enumeration alone cannot produce it.

### Status

Not started. The MM half is one script run away and needs the instrument; the
off-ledger half needs a session with KH at the bench. Neither is blocked on
anything in this entry.

---

## Revision, same day: the plan carries decisions; the interpreter carries the rest

**KH, 2026-09-13:** *"플랜.md는 숫자와 컨텍스트를 담고 뒤따르는 플랜
인터프리터가 나머지 파라미터를 모두 정하게 하는게 좋겠다."*

**The Addition above is superseded on its central claim** — `plan.yaml` is
*not* the machine's complete state — and is kept rather than edited out,
because the reasoning that produced it is what the correction is against. Its
derived three-way partition (major / detail / off-ledger) **survives intact**;
only the question of *which artifact carries the detail tier* changes.

### The reason is Principle 2, not only separation of concerns

An exhaustive device-property dump inside `plan.yaml` makes the plan **tier 2**
— instrument-bound — and [01 §3 Principle 2](../../docs/01-architecture.md)
says only tier 3 transfers. A plan enumerating every MM property is a plan that
cannot be reprojected onto another system, which is the capability
[03](../../docs/03-cross-system-transfer.md) exists for. The earlier framing
would have traded that away to gain completeness in the wrong file.

### The condition: the interpreter may not originate either

Rule 2 does not stop at the committee. This design moves parameter choices to
the last stage before the hardware, which is the stage with no reviewer, so the
rule has to be carried down with them:

| Parameter | Interpreter's action | Basis |
|---|---|---|
| **major** — consumed by a check | apply what the plan says | `plan.yaml` |
| **detail** — no check reads it | **leave it alone**, and record what it was | `Microscope.snapshot()` |
| detail that *must* change, and the plan is silent | **refuse** | rule 2 |

"Leave it alone" is the only default that originates nothing. It needs no
table of defaults, and `hardware/microscope.py` already carries the pieces —
`Setting`, `snapshot()`, `state()`, `is_noop()`.

### The exhaustive list moves stage; it does not disappear

| File | Stage | Content | Tier |
|---|---|---|---|
| `plan.yaml` | planning | what was decided, why, what was conceded | 3 — transfers |
| `as_set.yaml` | execution | the machine's complete state, every parameter | 2 — this instrument |

This is **better evidence than the planning-time list would have been.** One is
an intention, the other is what was actually true. The temperature stage is the
case in point: the damage is not that nobody planned its setpoint, it is that
**nobody recorded whether it was on**, which is why the 2026-09-04 grid's 3–8 %
is now irrecoverable rather than merely unmeasured
([`kb/systems/current.md`](../systems/current.md) `> devices_not_in_mm_config`,
[`docs/mhs-integration.md` §1.5](../../docs/mhs-integration.md)).

It is also the first concrete instance of the **stage axis** this session put
on the table and did not choose: `plan` and `execute` become different
artifacts because they answer at different times. That is evidence for axis A,
not a decision to adopt it.

### A note on the diagram

`Plan Interpreter (Plan → MHS)` is drawn as an LLM box. Under the rule above it
is **deterministic code**: apply the plan, leave the rest, record everything.
An LLM choosing unjudged parameters would break rule 2 at the one stage nobody
reviews. The interpreter reads `plan.yaml`, not `plan.md`, so it needs no
language model to do its job.

---

## Scope, same day: the plan comes first, the hardware seam comes later

**KH, 2026-09-13:** *"MHS는 현재는 고려단계이지만 플랜을 잘 만들어두면 추후에
하드웨어와 연결하면 된다고 생각해."*

Recorded because it fixes what this layer is answerable for. The planning
layer is the deliverable; **no part of it is designed against MHS's schema**,
and the interpreter's contract is `plan.yaml → driver` with MHS one possible
target beside the three bespoke translators that exist (pymmcore-plus, the
28-command TCP surface, the vendor DLL).
[`docs/mhs-integration.md`](../../docs/mhs-integration.md) already takes this
position — *"a note, not a plan"* — and nothing here changes it.

The Revision above is what makes the deferral safe: `plan.yaml` is tier 3, so
it survives whichever abstraction the hardware seam turns out to use. **Every
device property admitted into it would spend that property.**

### What deferring does not buy

The seam does not fail on format. It fails on confirmation, and this
repository already holds the evidence: **a return code of `0` from the
tweezers means the GUI accepted the command, not that anything happened** —
six wrong states and success share one byte (SAFETY §0) — and `No MCP tool has
reached a device`, so the entire hardware layer is written and unexercised.

The guard is built and is the designer's to honour: `plan-check`'s
`Confirmed by` column refuses a sequence step that rests on a return code. It
is the one thing carried from the planning layer into the execution one, and
treating it as a formality is how the deferral gets paid for later.
