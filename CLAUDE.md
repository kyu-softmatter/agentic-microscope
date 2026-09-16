# CLAUDE.md — working rules for this repository

An agent that turns a research goal into a microscope configuration checked
against what this instrument can physically do, and **refuses when the evidence
for a setting does not exist**. Full orientation: [README.md](README.md) ·
design: [`docs/01`–`docs/09`](docs/) · hazards: [SAFETY.md](SAFETY.md).

Two rules that outrank everything below:

1. **Read [SAFETY.md](SAFETY.md) before anything moves.** Class-4 1064 nm trap
   laser, four confocal lines, 0.13 mm working distance on the `100x-Oil`.
   **A return code of `0` from the tweezers means "the GUI accepted the
   command", not "the thing happened"** — six wrong states and success are the
   same byte (SAFETY §0). Never treat it as confirmation.
2. **Never originate a physical number.** Code computes, the KB records, the
   model judges what has no closed form. A missing input produces `BLOCKED`,
   which is a **valid result**, not a failure
   → [01 §3 Principle 1](docs/01-architecture.md).

---

## 1. The imaging priority hierarchy

**Operator's ranking (KH, 2026-09-07).** When a proposal cannot satisfy every
axis at once, this is the order in which they are defended. Rank 1 is protected
hardest; rank 4 is the free variable that moves first.

| Rank | Axis | What it is, concretely on this bench | Owned by | Settings |
|:---:|---|---|---|---|
| **1** | **Spatial resolution** | Pixel size at the sample and the NA that feeds it. Standing choice: `100x-Oil` at **1×1 binning, 0.06453 µm/px** — measured 2026-09-03, and 0.73 % from the 2025-04 table's 0.065 (§3) | lens 4 (objective, immersion) · lens 2 (binning, ROI) | objective, intermediate mag, binning |
| **2** | **Image quality** | SNR and localisation precision — whether a particle can be found and centred, not whether the picture is pretty | lens 2 (photon budget, SNR) · lens 1 (throughput) | exposure, gain, readout mode, filters |
| **3** | **Time resolution** | Achieved frame period. Standing choice: **20.0 ms exposure ⇒ ~50 fps** (this camera takes the exposure as the period) | lens 2 (frame interval) · lens 3 (frame-rate arithmetic) | exposure, interval, ROI, data rate |
| **4** | **Light source intensity** | Source level at the sample. Standing choice: Aura **GREEN ~80/1000** | lens 5 **reports** (level, duty, dose); nothing gates it — see H2 | level %, illumination duty |

Standing values and the reasoning behind them:
[`kb/expertise/microrheology-standard-conditions.md`](kb/expertise/microrheology-standard-conditions.md).

### How to apply it

- **H1 · Concede from the bottom up.** To fix a shortfall, move intensity first,
  then frame rate, then accept lower SNR, and only last touch magnification, NA
  or binning. Report every concession by name; do not spend a rank silently.
- **H2 · Intensity is instrumental, not a goal.** It is the lever, bounded above
  by bleaching and light-driving and below by "the analysis cannot work" — the
  *working LUT* of README item 9. It is **not** licence to add light: the bound
  is a measured window.
  ⚠ **The fence is gone as of 2026-09-10.** This rule used to end "and lens 5's
  gates are the fence"; lens 5 is a reporting section now and has no gates, so
  nothing enforces H2 but the reader. The only remaining ceiling on light level
  is lens 2's L2.2 saturation, which is about the camera and not about the sample
  → [`2026-09-10-lens-5-becomes-a-reporting-section.md`](kb/decisions/2026-09-10-lens-5-becomes-a-reporting-section.md).
- **H3 · The hierarchy is a tie-break among `soft` and `bias` trade-offs. It
  never overrides a `hard` gate** → [05 §2](docs/05-consensus-gate.md). Rank 1
  does not buy an oil objective past L4.5's RI-mismatch depth (~10 µm), and no
  rank raises the disk's write bandwidth (L3.1).
- **H4 · Do not "correct" a higher rank on lower-ranked grounds.** 1×1 is not
  the SNR-optimal choice and **must not be changed to 2×2 on SNR grounds** — a
  Mortensen-style variance argument favours 65 nm pixels for single-particle
  localisation once background scales per pixel area. Same for the objective:
  the ~17.6 % Faxén drag inflation at the ~8 µm working depth was accepted with
  that bound stated. **Report the bias; do not silently correct it, and do not
  re-litigate the objective.**
- **H5 · If the intensity window comes back empty, escalate upward — visibly.**
  No light level working is the real result. Something above has to move (frame
  rate, dye, objective, binning), and that revision is stated, not made quietly.
- **H6 · When the hierarchy cannot resolve it, hand the conflict to the human**
  in the form of [05 §6 deadlock handling](docs/05-consensus-gate.md) — each
  lens, its number, its basis, and the options with what each one concedes.

The cross-lens constraints in [01 §4](docs/01-architecture.md) are where this
ranking earns its keep, because each of them is a conflict with no single owner:

| Constraint | Lenses | Ranks in tension | Resolution under this hierarchy |
|---|---|---|---|
| Pixel size — Nyquist vs σ_PSF ≈ pixel | 2 ↔ 6 | 1 vs 2 | **Opposite directions.** Rank 1 holds: keep the finer pixel, report the SNR cost |
| Light level vs light-driving | 1 ↔ 5 | 2 vs 4 | Raise intensity for SNR *inside* the working window; if it does not fit, H5 |
| Motion blur in the MSD | 2 ↔ 6 | 2 vs 3 | Shorten exposure and pay for it in light (rank 4) before lengthening the frame period |
| ROI vs statistics | 3 ↔ 6 | 1 vs 3 | A smaller ROI is the standing choice (2–3× the particle); the cost lands on lens 6's power, not on binning |
| Requested vs achieved frame rate | 2 ↔ 3 | 3 | A requested rate is not evidence (L3.2). Rank 3 is judged on the *achieved* period |

### Relation to README to-do item 9

Two different orders, both live. Conflating them is the error to avoid:

| | Order | Governs |
|---|---|---|
| **README item 9** | frame rate → exposure *and* interval → intensity from a setup scan | **Procedure.** How the triple is *picked* from scratch. Frame rate is fixed first because it bounds everything downstream |
| **This hierarchy** | spatial resolution → image quality → time resolution → intensity | **Conflict.** Which axis *yields* when they cannot coexist |

So frame rate is chosen first and is still only the third thing defended. Item
9's step 1 "does not get to be revised silently", and H5 is the same rule seen
from the other end.

### What the hierarchy does not cover

- **Objective choice at load time is a safety decision, not an imaging one.**
  Load with a low-magnification objective in place — millimetres of working
  distance, so the front element cannot be reached — regardless of what rank 1
  wants for the measurement → README item 10, SAFETY §2.
- It ranks axes, not *quantities*. Statistical power (ungated since 2026-09-11), field count and
  duration are lens 6 and lens 8 questions and are not on this ladder.

### Status of this rule

The KB entry is
[`kb/expertise/imaging-priority-hierarchy.md`](kb/expertise/imaging-priority-hierarchy.md)
— **cite that, not this file.** What is here is the working form: per-lens
ownership and the cross-lens resolutions.

Read its *Stated vs reconstructed* table before leaning on it. The ranking and
the meaning of rank 4 are KH's, dated 2026-09-07; the `Why` is **reconstructed**
from four prior records rather than given in his words, the five falsifiers are
this repository's proposals, and the scope is assumed narrow (single-particle
tracking and microrheology) rather than assumed general. The `TODO(human)` in
that entry is what closes those three gaps.

---

## 2. The committee: run order, precedence, and the exceptions

Three orderings are now live here, and conflating any two of them is the error
to avoid. §1 already separates the first two; this is the third.

| | Order | Governs |
|---|---|---|
| **README item 9** | frame rate → exposure *and* interval → intensity | **Procedure.** How the triple is picked from scratch |
| **§1 hierarchy** | spatial resolution → image quality → time resolution → intensity | **Axes.** Which axis yields when they cannot coexist |
| **§2, here** | kind of gate first, then lens | **Lenses.** Who runs when, and whose verdict wins |

The roster — who owns what, and the nine cross-lens constraints — is
[01 §4](docs/01-architecture.md). Do not restate it. The pipeline this sits
inside is [05 §6](docs/05-consensus-gate.md).

### Run order

```
brief.yaml                      hand-written today     goal · constraints · sources
      ↓
1 · 2 · 3  (+7 if trapping)     code, in parallel      deterministic, fast
           (+9 if anything moves)
      ↓        any hard gate m < 1 → stop here, return a revision
4 · 5      (+8 if >30 min)      subagents, parallel    fed the computed results
      ↓
6                               subagent, alone        reviews all of the above
      ↓
synthesis → verdict             →  plan.md + plan.yaml
```

**The computational lenses run first** so that no subagent deliberates over a
physically impossible proposal, and **their numbers are the input** to the
judgment lenses — a judgment lens never generates the number it is judging.

⚠ [05 §6](docs/05-consensus-gate.md)'s diagram puts 4·5·6·8 in one parallel
block. **This supersedes that**: lens 6 reviews the other lenses' verdicts, so
it cannot run beside them.

### The experiment designer — the same order, run by code

**Planned 2026-09-13; both stages run as of 2026-09-15.**

```bash
python -m designer.cli run     config/briefs/active-microrheology.yaml
python -m designer.cli packets config/briefs/x.yaml --out <dir>
python -m designer.cli emit    config/briefs/x.yaml --id <slug> --date <date> \
    --question "..." --out <dir> [--judgment <verdict.yaml> ...]
```

`run` prints the nine verdicts and writes nothing. `emit` writes both halves of
the plan and then **validates the `.md` it just wrote** with the same check
`knowledge.cli plan-check` runs. `--out` has no default and `kb/plans/` is not
one: writing there also means running `knowledge.cli write` and reviewing the
entry, which is a decision and not a side effect (§6).

**Stage 1 is the nine `gate.py` modules**, and it runs end to end with no
subagent convened. `committee/` still only inspects the wiring between lenses,
and `hardware/orchestrator.py` is still for devices
→ [`2026-09-13-the-planning-layer.md`](kb/decisions/2026-09-13-the-planning-layer.md).

**Stage 2 is two commands and a conversation in between, because code cannot
convene a subagent** and `designer/judgment.py` does not pretend to. The four
agents in `.claude/agents/` have Read/Grep/Glob; **you** convene them. What is
in code is the part that can be checked either side of that
→ [`2026-09-15-stage-2-the-judgment-seam.md`](kb/decisions/2026-09-15-stage-2-the-judgment-seam.md).

| Half | What it does |
|---|---|
| `packets` | writes what each judgment lens is handed: its own gate's `Verdict` **to interpret, not recompute**, who carried it which number, the lens 01 §4 pairs it with, and **two** rulable lists. `must_rule_on` is obligatory — silence on one is refused; `may_rule_on` is the checks that ran and emitted nothing, offered because a margin with no finding reads as headroom. Every entry on both is **derived** — the gate's own findings, its skipped and its silent checks, and for lens 6 `validity.setup`'s three ledger states — never declared here |
| `emit --judgment` | reads the verdicts back and **refuses nine ways**. One refusal writes nothing: a refused judgment is not a missing one, and writing the plan without it would record a review that did not happen |

The refusals worth knowing without opening the file: a ruling with no `basis` ·
a subject the packet never asked about (the lens generated a finding) · silence
on a subject that is neither ruled nor in `unevaluated` · **`accept` on a
`hard` finding at m < 1**, which is §2 precedence level 4 in code · and lens 6
returning before 4 · 5 · 8, which is E2.

**Lens 6 is refused a packet until the others return.** It reviews their
verdicts, so a packet built early hands it the gate results and silently drops
the judgment half of exactly what it is convened over.

**A judgment half has four states and they are not one fact**: `judged` ·
`convened` (packet written, nothing came back) · `awaiting` (gate ran, packet
withheld under E2) · `absent` (no gate verdict to interpret, with the gate's
own reason). Collapsing `awaiting` into `absent` said lens 6's gate had
produced no verdict when it had returned FAIL.

`plan.md`'s Preconditions, Sequence and Stop conditions are **still unwritten
by either stage** and are emitted empty **with a line saying why**: a section
empty because nobody wrote it looks exactly like one with nothing in it.

**Input — `brief.yaml`.** The goal, the constraints, and every fact with the
entry it came from. **Hand-written until the query refiner exists**, and the
refiner is deliberately second: the designer is what fixes this schema, so
building the refiner first would make it guess at its own output.

**Output — two files, because the plan has two readers with opposite needs.**

| File | Reader | Shape |
|---|---|---|
| `plan.md` | the operator | the `kb/plans/_template.md` shape, so `knowledge.cli plan-check` already validates it — including the `Confirmed by` column that refuses a step resting on a return code (E9) |
| `plan.yaml` | the plan interpreter, and any re-check | tier 3. `config/channels` schema verbatim under `channels:`, and **no device property that no check reads** — admitting one makes the plan tier 2 and ends its portability (01 §3 Principle 2) |

`unevaluated` and `unresolved` are **required keys in `plan.yaml` even when
empty.** An absent key reads as a cleared one, which is §3 exactly.

**Three templates now fix these shapes**, and each says in its own header what
it refuses to carry: [`config/briefs/_template.yaml`](config/briefs/_template.yaml)
· [`kb/plans/_template.md`](kb/plans/_template.md) ·
[`kb/plans/_template.yaml`](kb/plans/_template.yaml). Every field in the brief
template is one a builder in `designer/build.py` actually reads, annotated with
the check that consumes it.

**The settings no check reads live in `plan.md`, not `plan.yaml`** (KH,
2026-09-14). The operator's parameter inventory lists about thirty of them —
CSU, both filter turrets, condenser, LAPP branch, dia lamp, PFS, z-drive,
camera fan/trigger/shutter/clear-cycle, confocal disk speed and aperture, the
Tweez trap and pattern block, the piezo's units, channel map and initial
position. They are set by a person and confirmed by something *observed*, in
`plan.md`'s Preconditions table, because a value in `plan.yaml` would be applied
by an interpreter that has no reviewer and cannot observe (E9). Two of them —
**confocal disk speed and aperture size — are in no KB entry at all**, so the
disk's exposure quantization cannot be computed today.

**The system's own scales are a brief field as of 2026-09-14.** Eight settings
in that inventory are bounded from below by the characteristic length and time
of the thing being measured, and nothing in this repository carried either — so
the harvest-based refiner could never have asked for them, which is the
falsifier [the planning-layer entry](kb/decisions/2026-09-13-the-planning-layer.md)
set for itself. `facts.system.characteristic_length_um` and
`characteristic_time_s` now feed **L2.6**, which reports pixels-per-feature and
frames-per-characteristic-time and **grades neither**: both thresholds are the
experimenter's and this repository holds no value for either.

**Stage 1 is the code half only.** All nine lenses have a `gate.py`, so the
order runs end to end with no subagent convened. The subagents — the
qualitative half of 4 · 5 · 6 · 8 — and `plan.md`'s prose are stage 2. So a
stage-1 verdict has every judgment row `unevaluated`, which is **a hole and not
a pass** (E4), and the file has to say so rather than omit them.

**The handoffs are the work, not the nine calls.** Lens 2's `fps_usable_max` is
what L3.2, L7.4 and L9.3 are judged against, and a *requested* rate is not
evidence (E5). 01 §4 lists nine cross-lens constraints and **two of them have no
code**: particle count 4 → 6 died with G11 on 2026-09-11, and ROI-versus-
statistics 3 ↔ 6 never had any. Wiring the designer is what will establish how
many of the nine are real.

⚠ **And a broken handoff looks exactly like a missing gate from the outside.**
The 2026-09-14 audit found three, all of them upstream of any check being
wrong: `build.py` hand-built the objective instead of looking it up, so lens 4
BLOCKED on `missing.working_distance` for **every brief ever run** and six
checks never executed; nothing carried the field of view from lens 2 to lens 4,
so L4.6's count reported "not evaluated", which reads as a pass; and the
30-minute convening threshold had two definitions that disagreed at exactly 30.
**Repair the wiring before adding a gate** →
[`2026-09-14-gate-audit-against-the-parameter-inventory.md`](kb/decisions/2026-09-14-gate-audit-against-the-parameter-inventory.md).

**A near-miss on a threshold WE chose is a concession, not a stop** (KH,
2026-09-16): *"안전에 위배되는게 아니면 2배정도 까지는 괜찮기도 할듯"*, because
the point of the experiment is that the value is unknown. A per-lens
`TOLERANCE` dict beside `LIMITS`, keyed by **emitted** code, says how far below
1.0 a `hard` failure still lets the run continue — three entries today, all
`0.5`. **A conceded gate cannot advance** and needs no rule for it: `grade()`
is HARD or worse for every margin a band admits.

⚠ **Four kinds of `hard` check deliberately have no band**, and the
distinction is the decision: physics or a boolean (`na_feasibility` is exact;
L9.1 asks whether a time base was *ever* measured) · already factored
(`disk_bandwidth_fraction` is 0.7 of a **measured** bandwidth, `full_well` 0.7
of full well — doubling those drops frames and clips pixels, which is no answer
rather than a worse one) · **safety** (L4.2 is the objective and the coverslip)
· and the brief's own (L9.2/L9.3 derive from `target_relative_error`, so 10 %
instead of 5 % is written in the brief, not granted behind it). The band is
also **not** what unblocks the active brief — that stops on a boolean and ~15
R1 answers → [`2026-09-16-a-band-on-the-thresholds-we-chose.md`](kb/decisions/2026-09-16-a-band-on-the-thresholds-we-chose.md).

**A new gate's threshold comes from the brief, not from `LIMITS`** (KH,
2026-09-14). The operator's multiples — ROI at 1.5× the system, concentration
at 3–5×, trap power at 1.2× — are per-experiment and are asked for, the way
lens 9 asks for `target_relative_error` and then has no `LIMITS` dict at all.
A constant in a `LIMITS` entry is a claim about every future experiment.

**After `plan.yaml`.** The plan interpreter applies what the plan decided,
**leaves every parameter no check reads at its current value**, and records the
whole machine state as `as_set.yaml`. It originates nothing and is code, not a
model — rule 2 does not stop at the committee, and the last stage before the
hardware is the one with no reviewer.

### Precedence — the kind of gate outranks the lens

A lens does not win an argument by being lens 1. **The gate's kind decides
first**, and only within one kind does anything else apply
([05 §2](docs/05-consensus-gate.md)):

| | What it is | Who may overrule it |
|---:|---|---|
| **0** | [SAFETY.md](SAFETY.md) | nobody. Not a lens, not negotiable |
| **1** | any `hard` gate at `m < 1` | nobody — **except inside its check's `TOLERANCE` band**, where it is a named concession and the run continues (KH, 2026-09-16). Three checks have one, all at 2×; it still cannot advance. §3 |
| **2** | any `bias` gate | proceed *only* where a correction formula exists; stop where none does |
| **3** | `soft` gates in conflict | **§1's rank order decides which yields** |
| **4** | lens 6's review | it may refuse to advance what 1–3 cleared; it may not clear what they stopped |

So §1's hierarchy is a tie-break **at level 3 and nowhere else** — H3, seen from
the lens side. Rank 1 does not buy an oil objective past L4.5, and no rank raises
the disk's write bandwidth (L3.1). And underneath all of it, **`unevaluated` ≠
`cleared`** (§3): a lens that did not run has not agreed.

### Exceptions

- **E1 · Lens 5's standing `BLOCKED` is over** (§3, 2026-09-09). It computes,
  so **a failure from G21/G22 is a genuine one** and nothing here excuses it.
  Both gates that made this exception necessary were removed the same day — G10
  (photobleaching) and G20 (saturation), each keyed to a per-dye constant that
  is empty for every dye. The entry is kept as a marker: if a lens ever blocks
  by design again, it needs its own line here rather than the benefit of this
  one.
- **E2 · Lens 6 runs alone and last.** See the ⚠ above.
- **E3 · Lens 7 silent on heating ≠ heating cleared.** Trap heating is ungated
  by decision ([05 §5](docs/05-consensus-gate.md), [06 D6](docs/06-pitfalls.md)).
- **E4 · A conditional lens that was not convened leaves a hole, not a pass.**
  Lens 8 under ~30 min, lens 7 with no trap and lens 9 with nothing moving are
  absent; their row in lens 6's bias ledger is `unevaluated`.
  ⚠ **Lens 8's row is now `unevaluated` even when it runs** (2026-09-10). It
  became a reporting section — every check INFO, `status: REPORT`,
  `advances: None` — so it emits no `bias` code for L6.2 to collect, and its
  drift and evaporation notes sit in `assumed_inputs`, which lens 6's
  single-quantity path does not read. The drift bias reaches a human reader and
  no gate. **Open, and lens 6's to close**
  → [`2026-09-10-lens-8-becomes-a-reporting-section.md`](kb/decisions/2026-09-10-lens-8-becomes-a-reporting-section.md).
- **E5 · Lenses 2 and 3 are convened together whenever frame rate is in play.**
  Lens 3 does not own the rate, and its arithmetic is only as good as the rate
  handed to it. A *requested* rate is not evidence — L3.2.
- **E6 · Lenses 1 and 5 are convened together, and 1 and 4 likewise.** Light for
  SNR against the dose budget, and immersion against depth, run in opposite
  directions (01 §4).
- **E7 · Objective choice at load time is not an imaging decision.** It sits
  outside this ladder and outside §1 — load at 4×, whatever rank 1 wants
  (SAFETY §2, README item 10).
- **E8 · Do not correct a higher rank on lower-ranked grounds** — H4. Report the
  bias instead.
- **E9 · A return code is not a confirmation** (SAFETY §0). Nothing advances on
  "the GUI accepted the command".

## 3. Evidence rules the code enforces

- **`measured` vs `assumed`, with a separate `advances` axis that only
  `measured` can satisfy.** A literature value lets a gate *compute* and never
  lets a verdict advance → [`kb/literature/`](kb/literature/).
- **A refusal names what would resolve it** — the missing input and where it
  lives. A `BLOCKED` with no fix instruction is a bug.
- **[`data/pixel_size.yaml`](data/pixel_size.yaml) is measured, all six rows**
  — settled 2026-09-09 after this repository had argued itself into the
  opposite. The 2025-04 spreadsheet is a measurement (KH), and eleven of its
  twelve cells landing exactly on `6.5 / (M_obj × M_int)` means those
  objectives sit at their nominal magnification, not that somebody typed the
  quotient. The one that departs, 20× by 0.39 %, is a real **20.078×**
  objective — and the table proves that itself: the tube lens and the 6.5 µm
  sensor are shared by all six rows, so an error in either would move all six,
  and 20×'s own two cells give 20.0785 by both paths, which rules out the
  intermediate magnifier. Nothing upstream is left; it is the lens.
  - **The earlier reading is kept in that file's header, marked wrong.** It
    reasoned from the digits to how the spreadsheet was produced — an inference
    about provenance made without the instrument. `kb/systems/current.md:1284`
    already records the precedent: **an operator statement about their own
    instrument outranks a shape inferred from a drawing.**
  - **100× does not come from the spreadsheet.** Two length standards were
    driven 10 µm at it on 2026-09-03 — closed-loop piezo 0.06460 µm/px, AOD
    trap 0.06445, agreeing to 0.24 % — so **0.06453** is recorded, agreeing
    with the spreadsheet's 0.065 to 0.73 %. Two independent measurements of the
    same cell.
  - **L6.3 can now say `pixel_size_measured` at any objective**, where before
    today the honest answer was nowhere. Every pixel-size-dependent quantity
    can `advance` at every magnification — so **a demotion is now the edit that
    needs justifying**, and `tests/test_pixel_size.py::test_every_row_is_measured`
    is what notices one.
  - The seven `.cfg` files match the table;
    `config/micromanager/set_pixel_size.py` **refuses to overwrite** a
    differing preset, so that resync is a decision and never a script run.
  - ⚠ `D:\codes` still hardcodes `px_to_um = 0.065` in every MATLAB file,
    0.73 % from the recorded 100×. Not this repository's to edit; lens 6 owns
    settings-versus-analysis mismatches → [`analysis/matlab/`](analysis/matlab/README.md).
- **`unevaluated` ≠ `cleared`.** Collapsing them is how a plausible number
  becomes a wrong one. A margin of 10.00 against a threshold nobody supplied
  still does not advance.
- **Lens 6 (`validity/`) reviews the other lenses' verdicts, so call it last.**
- **Two of the nine lenses judge nothing.** Lens 5 and lens 8 both became
  reporting sections on 2026-09-10 — every check INFO, `LIMITS` empty,
  `status: REPORT`, `feasibility: "N/A"`, `advances: None`. The reasons do not
  transfer and should not be merged: lens 5's gates needed per-dye constants
  that are empty for every proprietary bead colourant here (a missing input),
  while lens 8's inputs arrive **during** the run (drift, PFS state, an
  evaporation rate) or belong to another lens (free settling → lens 4's L4.6) —
  a timing and ownership problem. **A lens whose numbers merely happen to be
  absent is `BLOCKED`, which is different and recoverable.**
  `tests/test_advances_rule.py` holds both to the opposite of the advances rule.
- **Lens 5 computes as of 2026-09-09**, for the first time. Power and
  illuminated area both exist
  ([`kb/calibrations/illumination-power.yaml`](kb/calibrations/illumination-power.yaml)),
  so there is irradiance — all three engines put about the camera field on the
  sample, 603,654 µm² at 20×, giving 1.1–7.7 W/cm² depending on line. **G21 and
  G22 run**; G10 and G20 were both removed the same day
  ([04 §6](docs/04-decision-engine.md),
  [`kb/decisions/2026-09-09-g20-saturation-removed.md`](kb/decisions/2026-09-09-g20-saturation-removed.md)).
  ⚠ The 603,654 µm² is the *square* field, which is the Spectra's and the
  LUN-F-XL's; **the Aura is a circle circumscribing it, 948,218 µm²**, so an
  Aura irradiance from the square number is 1.56× too high
  ([`illumination-power.yaml`](kb/calibrations/illumination-power.yaml)) — the
  4.85 W/cm² row, not 7.62. `photo/gate.py`'s own refusal text still quotes the
  square for all three engines. Two more limits, and only one of them is
  still about evidence: the areas are **20× only**, because that is the
  magnification the fields were established at — not because of the pixel size,
  which is `measured` at every objective — and they are `computed`, since
  "about the camera field" was not quantified for any of the three engines.

## 4. Hardware, when it is in the loop

- Nothing moves without an explicit flag: `--unlock` (piezo), `--allow-motion`,
  `--allow-laser`, `--arm`, `--allow-immersion-change`. The MCP server ships
  with `AGENTIC_MICROSCOPE_ALLOW_MOTION=0` and `..._ALLOW_LASER=0`
  ([`.mcp.json`](.mcp.json)) and refuses the two moving tools by default.
- **No MCP tool has reached a device.** Do not write as though one has.
- `hardware/lunf_power.py` is complete as transport and **refuses to transmit** —
  the LUN-F-XL DAC word format is undocumented and a guessed byte goes into a
  laser driver. Leave that refusal in place.
- Known false leads, each of which cost a session: `Breakpoints > Enable Bits`
  is `0000`, so `TRAP_PATT_RELEASE_BP` returns `0` while doing nothing; the
  Tweez GUI has **no** trap-count ceiling (160 created and deleted cleanly in
  one pass); `10012` on a Kinetix is **usually a wedge, not ownership
  contention** — one standalone snap on that body clears it.

## 5. Commands

```bash
python mcp_server/bootstrap.py --dry-run
```

Prints the path of an interpreter that has the dependencies, or exits non-zero
naming what to install. **Use it instead of searching the filesystem** — on this
PC that is `~/venvs/auto_microscope` (Python 3.12.10, outside the repo so it
survives a clean checkout).

```bash
pytest -q -rs
```

1478 passed, 11 skipped on macOS, of 1,489 (re-measured 2026-09-15; was
1374/11 of 1,385 on 2026-09-14, and the 91 added since are the plan emitter's,
stage 2's seam, L1.3/L1.5, the four defects that convening the real agents
found, Phase 0b in all nine gates, the
third subject source, and the tolerance band -- the emitter is where the previous four broken handoffs were found, one
of them a number the run order already claimed to carry. Windows printed 1195/10 on 2026-09-09 — one Windows-only test — and has
**not** been re-measured since). Two kinds of
skip: three whole modules behind `pytest.importorskip("pymmcore_plus")`
holding 56 tests (counted 2026-09-09, not re-counted today — the dependency is
absent here, so they skip at import and cannot be collected) that need a
Micro-Manager device-adapter install, and seven `requires_cv2` tests in
`tests/test_objective_offsets.py` that call OpenCV
(`requirements-analysis.txt`, not in CI). `-rs` keeps all ten named, so the
count cannot quietly shrink. **The instrument is not required to run any test.**

```bash
PYTEST_CI_EMULATE=ci pytest -q -rs
```

**Run this before pushing anything that touches a test.** This venv has all four
requirement stacks; the runner has two, so a test reaching an uninstalled one
passes here and errors there — it did, for three commits after `062db16`.
`ci` hides `cv2` and `pymmcore_plus`; `base` also hides `mcp`
→ [`tests/ci_emulate.py`](tests/ci_emulate.py),
[`kb/decisions/2026-09-07-ci-environment-and-timing-bounds.md`](kb/decisions/2026-09-07-ci-environment-and-timing-bounds.md).

Two rules that follow from it: **if a test calls into a deferred `import cv2`,
mark it `requires_cv2`** — every cv2 import here sits inside a function body, so
the module loads and only the call fails. And **a timing test may assert what
the mechanism guarantees, not how well the OS scheduled it**: `sleep_until`'s
overshoot bound is 20 ms on an owned machine and 250 ms where `CI` is set,
because a shared runner's scheduler is not a property of this code.

```bash
python -m optics.cli check config/channels/proposed-2color.yaml
```

Every lens has the same shape — `optics` · `detection` · `compute` · `sample` ·
`photo` · `validity` · `stability` · `trapping` · `velocity`, each with `checks.py` ·
`gate.py` · `setup.py` · `cli.py`. All **52 checks** are collected in
[04](docs/04-decision-engine.md), addressed `L<lens>.<n>` since 2026-09-11 —
the lens number from [01 §4](docs/01-architecture.md), then the check's
position in it. **22 `hard` · 6 `bias` · 6 `soft` can fail; 18 `info` only
report**, and the kind is printed beside the address, because an address is a
location and not a claim that something can fail. That is what let the eleven
previously unnumbered checks be documented at all — two of them `hard`, so a
proposal could be stopped by something that appeared in no table.

**Ten old numbers are retired, not translated** — `G10`, `G11`, `G18`, `G20`,
`G21`, `G22`, `G26`, `G28`, `G29`, `G30` — G10 and G20 on
2026-09-09, the other six on 2026-09-10: G18 because the coverslip condition is
checked elsewhere, G21/G22 when **lens 5 stopped being a judging lens** and
became a reporting section, and G28/G29/G30 when PFS lock and both drift rates
moved to the **hardware execution stage**. Those last three share a shape, and
it is worth knowing before proposing a gate: **a planning gate must judge from
what is known before the run starts.** G28 was reading `PFS in Range` as the
servo state and that property reports the coverslip; G29 and G30 were reading
the right quantity at the wrong time — *"실험 중 측정해야한다면 디자인 요소로는
적합하지 않은듯"* (KH, 2026-09-10). **G11 and G26 followed on 2026-09-11**,
which left lens 6 computing nothing at all: G11's `1/√(N_p·N_f)` counts
*independent* samples and one trapped bead at 520 fps has 6.3 correlated frames
per relaxation time (3.5× optimistic), and G26 gated on a `despeckle` boolean
nobody verifies while `detection/recommend.py` already refuses on it where it
does damage. None of the ten numbers is reused.

```bash
python -m committee.cli reconcile
```

**Run this after adding or removing a gate.** `committee/` is not a lens — it
judges the *wiring between* them, and two failure modes there are silent: a
lens emitting a bias code no registry names (accepted, but it pins the
verdict's `evidence` to `assumed` forever) and a registry naming a code nobody
emits (a declaration matches nothing and the declarer is not told). The layer
**parses** every `CheckResult` in every `checks.py` with `ast` rather than
trusting a declaration, and `python -m committee.cli parser` reports any
construction site it could not read — a silent parse miss would make it
confidently claim a code is unreachable.

⚠ **It currently reports 7 and 8, and that is expected**: the drift is tracked,
not clean, and is KH's to close through this layer rather than by hand-editing
the tables → [`2026-09-11-the-emission-collection-layer.md`](kb/decisions/2026-09-11-the-emission-collection-layer.md).
`emissions` lists every code with its kind and severity; `invisible` lists the
34 sites that compute a result at severity `"ok"`, which every `gate.py` drops
from `findings`.

```bash
python -m knowledge.cli write
```

Rebuilds [`kb/INDEX.md`](kb/INDEX.md) from the `id` · `question` · `date`
frontmatter each entry carries. **Start there, not with a grep** — `kb/` is 48
files and ~710 KB, and `kb/systems/current.md` alone is 1,634 lines. The index
also carries `superseded_by` / `corrected_by`, which is the part that matters:
three entries — all three from 2026-08-26 — were corrected by a first-light
session the next day, and reading one of them without that link is the failure
mode this exists to stop.

It is **pointers only, never a citation** — open the entry and cite that
([09 §7](docs/09-knowledge-capture.md)). Run it after adding anything to `kb/`;
`tests/test_kb_index.py` fails if you don't, and also on a file with no
frontmatter or a supersession link that resolves to nothing.

```bash
python -m knowledge.cli plan-check
```

Refuses a `kb/plans/` entry whose shape a hardware skill would misread — a
missing section, an unknown subsystem, a committee verdict silent on what was
**not** evaluated, or a sequence step confirming on a return code. That last one
is [SAFETY §0](SAFETY.md) held at the plan instead of at the instrument.

## 6. Writing anything down

Do not duplicate what the repo already records. Pick the right home:

| Goes to | For |
|---|---|
| `data/*.yaml`, `kb/calibrations/` | a measured constant |
| `kb/decisions/YYYY-MM-DD-<slug>.md` | a design choice or a scope decision, dated |
| `kb/plans/YYYY-MM-DD-<slug>.md` | one hardware run, **before** it happens. Copy `_template.md`; `plan-check` refuses a shape a skill would misread. Graduates into `kb/decisions/` once run → [05 §6](docs/05-consensus-gate.md) |
| `kb/plans/YYYY-MM-DD-<slug>.yaml` | the same run, for a reader that is not a person — the experiment designer's machine half (§2). Same slug as the `.md`, deliberately: one run, one name, two readers. **Written by `designer.cli emit` since 2026-09-15**; `emit` refuses to overwrite either half, so a re-emission is a decision |
| `kb/expertise/<id>.md` | durable expert judgment. `Why` and `Falsifying condition` are **mandatory** ([09 §2](docs/09-knowledge-capture.md)) |
| `kb/sessions/YYYY-MM-DD.md` | the day's narrative. **A failed session gets a *longer* entry, not a shorter one.** Numbers, not adjectives |

And the rules from [09 §7](docs/09-knowledge-capture.md): show it and get
confirmation before storing · never store without a `Why` · always ask for the
falsifier · never mix a computed result and an expert judgment into one entry ·
**the agent's own inference is not a source** · capture a correction first,
because a correction is dense knowledge · always link when citing the KB, and
give no advice without a source.

## 7. Code conventions

- **Not a package.** No `[build-system]`; `pyproject.toml` exists to put the
  repository root on `sys.path` so bare `pytest` and `python -m pytest` agree.
  Everything runs as `python -m <lens>.cli`.
- Requirements are split on purpose: `requirements.txt` (numpy + pyyaml, 1,132
  tests) · `requirements-mcp.txt` (30 tests, pure Python, in CI) ·
  `requirements-micromanager.txt` (56, vendor device-adapter download, not in
  CI) · `requirements-analysis.txt` (7, OpenCV, not in CI).
- **One definition, one file.** `tests/test_sort_one_copy.py` fails if a shared
  name is defined in both `sort_core.py` and a CLI — a standalone copy already
  drifted once, in its docstrings, which is the state in which the next drift
  goes unnoticed.
- Prose here states what is *not* true alongside what is. Keep that when editing
  README, SAFETY or `docs/`: no claim without its date, its evidence tier, and
  its limit.

## 8. Public-repository constraint

Vendor manuals, proprietary DLLs, and commercial correspondence are in **no
commit here** — removed from the whole history on 2026-08-28, not just from the
tip. Do not reintroduce them, and do not paste quotes, pricing or named contacts
into tracked files. The technical conclusions drawn from them are stated inline
wherever they are used → [NOTICE.md](NOTICE.md).
