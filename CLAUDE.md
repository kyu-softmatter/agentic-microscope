# CLAUDE.md — working rules for this repository

An agent that turns a research goal into a microscope configuration checked
against what this instrument can physically do, and **refuses when the evidence
for a setting does not exist**.

This file is the only document loaded automatically. It is therefore an
**index and a protocol, not a copy** — it carries the rules you must never have
to look up, the order in which to read everything else, and a lookup table for
every setting and condition. Values live in `data/` and `kb/`; this file points
at them. A number duplicated here is a number that can go stale, so there are
very few.

---

## 0. Boot sequence — do this before proposing anything

Read in this order. Do not skip ahead to a proposal.

| # | Read | Why this one, and how much |
|:-:|---|---|
| 1 | **[SAFETY.md](SAFETY.md)** | All 416 lines, every session, **before anything moves.** Ten sections: §0 the return-code property · §1/§1b lasers · §2 objective/coverslip collision · §3 piezo · §4 camera ownership · §5 shutters · §6 sample exposure · §7 data-integrity hazards · §8 running procedure · §9 open questions |
| 2 | **[README.md](README.md)** — "What works today" and "Current execution boundary" | What is actually reachable versus designed. The boundary section holds items 0a/0b/0c, the hardware seam. Skip the rest of its 2,213 lines until you need a to-do item by number |
| 3 | **[docs/01-architecture.md](docs/01-architecture.md)** | The eight lenses, who owns what, and §4's nine cross-lens constraints. §5 of this file is the working form; 01 §4 is the roster |
| 4 | **`python -m knowledge.cli write` then [kb/INDEX.md](kb/INDEX.md)** | The KB is ~50 files and the dossier alone is over 1,600 lines. **Start at the index, never with a grep.** It carries `superseded_by` / `corrected_by`, which is the part that matters — three entries from 2026-08-26 were corrected the next day, and reading one without its link is the failure this index exists to stop |

Then **§2b, the design protocol — before proposing any setting** — followed by
§2's lookup table and the relevant `docs/0*`. [SAFETY.md](SAFETY.md) and [docs/04](docs/04-decision-engine.md) are
the two you will return to most.

**On SAFETY.md's own status.** It is a **first draft / memo dated 2026-09-03,
not yet reviewed by the operator**, and it says so in its header: "treat it as a
record of what was learned, not as an approved procedure." It still sits at
precedence 0 below (§5) and still outranks every lens — everything in it is
either measured on this instrument or an operator instruction, and each item
says which. Both facts are true at once; state them both when you cite it.

---

## 1. The hard rules

Five rules, inlined because they must never depend on a second file read.

1. **A return code is not a confirmation.** On the optical tweezers a return of
   `0` means "the GUI accepted the command", not "the thing happened". The
   Tweez 300 has **no readback of any kind** — no position, force, trap list or
   calibration. Six wrong states and success are the same byte
   ([SAFETY §0](SAFETY.md)). Confirm by eye in the GUI or by measuring the
   result in camera data. Never advance on a return code.
2. **Never originate a physical number.** Code computes, the KB records, the
   model judges what has no closed form. A missing input produces `BLOCKED`,
   which is a **valid result**, not a failure
   → [01 §3 Principle 1](docs/01-architecture.md). A *setting* you propose is
   not a *fact* you may invent — §2b D2 is where that line is drawn, and
   feeding an invented setting into a gate is the way a verdict comes back
   looking measured when it is not.
3. **`unevaluated` ≠ `cleared`.** A lens that did not run has not agreed. A
   margin of 10.00 against a threshold nobody supplied does not advance.
4. **Nothing moves without its explicit flag**: `--unlock` (piezo),
   `--allow-motion`, `--allow-laser`, `--arm`, `--allow-immersion-change`.
5. **Load the sample with a low-magnification objective in place** — a 4× or
   10×, millimetres of working distance, so the front element cannot be
   reached. This holds regardless of what the imaging hierarchy wants
   → [README item 10](README.md), [SAFETY §2](SAFETY.md).

---

## 2. Lookup — the settings and conditions channel

**Find the value here; do not re-derive it and do not recall it.** Every row is
the canonical source. Where a row has a limit, the limit is stated.

### Instrument constants

| To know | Read | Tier, and its limit |
|---|---|---|
| pixel size at the sample, per objective × intermediate mag | [`data/pixel_size.yaml`](data/pixel_size.yaml) | **measured, all six rows** (§6). 100× is `0.06453` µm/px from two length standards, 2026-09-03 |
| NA, working distance, immersion, magnification | [`data/objectives.yaml`](data/objectives.yaml) | one 6-position turret shared by all three light paths |
| parfocal z offsets between objectives | [`kb/calibrations/objective-offsets.yaml`](kb/calibrations/objective-offsets.yaml) | measured |
| trap field half-extents, px → trap µm | [`data/trapping_range.yaml`](data/trapping_range.yaml) | mirrors the dossier's `trapping_range` |
| camera QE, read noise, gain | [`data/detectors.yaml`](data/detectors.yaml) | — |
| per-row readout time (for `ReadoutTimeNs`/ROI height) | [`kb/calibrations/camera-readout.yaml`](kb/calibrations/camera-readout.yaml) | measured |
| disk write bandwidth | [`kb/calibrations/disk-bandwidth.yaml`](kb/calibrations/disk-bandwidth.yaml) | measured; G12 gates data rate at 0.7× it |
| filters, dichroics, path elements | [`data/filters.yaml`](data/filters.yaml) | — |
| light-source registry | [`data/light_sources.yaml`](data/light_sources.yaml) | — |
| source power and irradiance at the sample | [`kb/calibrations/illumination-power.yaml`](kb/calibrations/illumination-power.yaml) | power **measured**; area **computed, 20× only**. See the warning below |
| the three light paths as configured | [`config/scopes/`](config/scopes/) | `current-laser` · `current-spectra` · `current-aura` |

### Sample and specimen

| To know | Read |
|---|---|
| fluorophore spectra and properties | [`data/fluorophores.yaml`](data/fluorophores.yaml) |
| the beads this lab actually disperses | [`data/particles.yaml`](data/particles.yaml) |
| one test frame → signal and background in e⁻/s | [`kb/calibrations/frame-photometry.yaml`](kb/calibrations/frame-photometry.yaml) — the measurement that unblocks G6 and G7 |
| coverslip thickness in use | [`kb/expertise/coverslip-thickness-in-use.md`](kb/expertise/coverslip-thickness-in-use.md) |
| immersion media in use | [`kb/expertise/immersion-media-in-use.md`](kb/expertise/immersion-media-in-use.md) |
| sample medium refractive index | [`kb/expertise/sample-medium-refractive-index.md`](kb/expertise/sample-medium-refractive-index.md) |
| sample mount geometry | [`kb/expertise/sample-mount-geometry.md`](kb/expertise/sample-mount-geometry.md) |
| oil objective trapping in water | [`kb/expertise/oil-objective-trapping-in-water.md`](kb/expertise/oil-objective-trapping-in-water.md) |
| the green-band single-slot constraint | [`kb/expertise/current-laser-green-band-single-slot.md`](kb/expertise/current-laser-green-band-single-slot.md) |

### Standing experimental choices

The one place values are inlined, because a proposal needs them without a
lookup. Reasoning and falsifiers:
[`kb/expertise/microrheology-standard-conditions.md`](kb/expertise/microrheology-standard-conditions.md).

| Axis | Standing choice |
|---|---|
| objective | `100x-Oil`, 1×1 binning, **0.06453 µm/px** |
| exposure | **20.0 ms ⇒ ~50 fps** — this camera takes the exposure as the frame period |
| illumination | Aura **GREEN ~80/1000** |
| ROI | 2–3× the particle |

⚠ **The irradiance trap.** `illuminated_area_um2` is keyed **per (source ×
objective), not per objective** — the three engines put different *shapes* on
the sample. The LUN-F-XL and Spectra get about the camera field; the **Aura is a
circle that circumscribes it, 1.57× the area**. Using the square for all three
overstates the Aura by that factor. Take each engine's own area from the file,
and note its `basis` field still calls the 20× pixel size `nominal` — that
predates the 2026-09-09 reversal in §6 and is stale; the pixel size is
`measured`. Areas exist at **20× only**, because that is the magnification the
fields were established at.

### Design and process documents

| For | Read |
|---|---|
| the eight lenses and the nine cross-lens constraints | [`docs/01-architecture.md`](docs/01-architecture.md) |
| how the KB is organised | [`docs/02-knowledge-base.md`](docs/02-knowledge-base.md) |
| moving a calibration between instruments | [`docs/03-cross-system-transfer.md`](docs/03-cross-system-transfer.md) |
| **every gate formula and threshold** | [`docs/04-decision-engine.md`](docs/04-decision-engine.md) |
| the committee pipeline and deadlock handling | [`docs/05-consensus-gate.md`](docs/05-consensus-gate.md) |
| known traps, D1–D*n* | [`docs/06-pitfalls.md`](docs/06-pitfalls.md) |
| what is built and what is next | [`docs/07-roadmap.md`](docs/07-roadmap.md) |
| the optical path, formally | [`docs/08-optical-path-spec.md`](docs/08-optical-path-spec.md) |
| how to write to the KB | [`docs/09-knowledge-capture.md`](docs/09-knowledge-capture.md) |

---

## 2b. Designing an experiment — the order of operations

A goal is not a setting. Work in this order, and **stop at the first step that
needs something you do not have.** Every rule here was paid for by a session;
none is theoretical.

**D1 · Take the experiment from the operator; never invent one.** Get the
physical question, the sample, and the constraints. Do not substitute a nearby
proposal because a config file for it happens to exist, and do not silently
change the experiment you were given. If the request is ambiguous, ask before
computing — a verdict on the wrong experiment costs more than the question did.

**D2 · Separate a physical fact from a design setting.**
*Facts* — viscosity, refractive index, temperature, concentration, relaxation
time, a dye's spectrum — come from the operator or from `kb/`. **Never
originate one** (hard rule 2); a missing fact is `BLOCKED`.
*Settings* — ROI, duration, segment count, velocity, amplitude, target
stiffness — are yours to **propose**, and every one must be labelled as a
proposal with the fact it was derived from. Feeding an invented setting into a
gate produces a verdict that looks measured and is not.

**D3 · Estimate the observable before choosing any setting.** Compute the
expected signal and compare it to the noise floor **at the standing
conditions**, before proposing anything. When the signal lands below the floor,
the standing conditions are wrong *for this sample*: escalate it as a revision
(H5). Do not patch it quietly, and do not discover it after the run.

**D4 · Optimise the precision of the answer, not the size of the signal.**
Name the figure of merit — the total error on the quantity being measured — and
minimise *that*. A change that enlarges the raw signal while costing more
independent samples is usually a loss, and the trade rarely runs in the
direction intuition suggests.

**D5 · Check that the instrument's bandwidth brackets the physics.** Every
measurement has a fast limit and a slow limit — frame period and run length,
trap corner and acquisition time, buffer depth and drift. Name both, and check
the timescale of interest falls between them. A configuration that cannot see
the phenomenon will still return clean numbers.

**D6 · Sweep an unknown input; do not pick a value for it.** Run the gate
across the plausible range and report **where the verdict changes**. "Unknown"
then becomes "this measurement decides it, and here is what it decides" — which
is actionable, where a guess is only a liability.

**D7 · A gate that passes on a placeholder has not passed.** Cross-check any
verdict resting on a default or an uncalibrated input against the measured
values in `kb/`, and say which direction the placeholder errs in. Read the
`assumed:` line of every verdict; it is the verdict's real content.

**D8 · Prefer several short acquisitions to one long one** when the statistics
are equivalent — they usually are, since total observation time is what sets
them. Segmentation buys robustness to drift, bleaching and mid-run failure, and
it yields a spread across repeats that a single run cannot produce. Control
what varies between segments (height, focus, sample region) or the spread
becomes a bias instead of an error bar.

**D9 · Confirm the analysis can consume the data before acquiring it.** A
pipeline that filters, detrends or rescales may remove exactly the signal the
run exists to produce. Check the analysis path against the intended observable
first → lens 6 owns settings-versus-analysis mismatches.

**D10 · When two requirements genuinely conflict, split the run in two** and
order them so the first measures an input the second needs. Report the conflict
by name (H1); do not average the two requirements into a setting that serves
neither.

**D11 · Re-examine every standing choice against this sample.** Standing values
carry the scope they were established in. A different medium, probe or depth
can move a limit in your favour as easily as against it — the objective and
depth in particular are worth re-deriving each time rather than inherited.

**D12 · Check the operator's own derivations, numerically.** Prior analysis is
a source and is treated as one, which includes verifying its arithmetic. Report
a discrepancy with the corrected number and what it changes downstream; a
correction is the densest knowledge there is → [09 §7](docs/09-knowledge-capture.md).

---

## 3. The committee: run order, precedence, exceptions

**Three orderings are live. Conflating any two is the error to avoid.**

| | Order | Governs |
|---|---|---|
| [README item 9](README.md) | frame rate → exposure *and* interval → intensity | **Procedure.** How the triple is picked from scratch |
| §4 below | spatial resolution → image quality → time resolution → intensity | **Axes.** Which axis yields when they cannot coexist |
| §3, here | kind of gate first, then lens | **Lenses.** Who runs when, and whose verdict wins |

So frame rate is chosen *first* and is still only the *third* thing defended.

### Run order

```
1 · 2 · 3  (+7 if trapping)     code, in parallel      deterministic, fast
      ↓        any hard gate m < 1 → stop here, return a revision
4 · 5      (+8 if >30 min)      subagents, parallel    fed the computed results
      ↓
6                               subagent, alone        reviews all of the above
      ↓
synthesis → verdict
```

**Run the computational lenses first** so no subagent deliberates over a
physically impossible proposal, and **hand their numbers to the judgment
lenses** — a judgment lens never generates the number it is judging. This
matches [05 §6](docs/05-consensus-gate.md) "Stage 3, corrected"; the roster is
[01 §4](docs/01-architecture.md) and is not restated here.

### Precedence — the kind of gate outranks the lens

A lens does not win an argument by being lens 1. **Decide on the gate's kind
first**, and apply anything else only within one kind
([05 §2](docs/05-consensus-gate.md)):

| | What it is | Who may overrule it |
|---:|---|---|
| **0** | [SAFETY.md](SAFETY.md) — an unreviewed draft, and still absolute (§0) | nobody. Not a lens, not negotiable |
| **1** | any `hard` gate at `m < 1` | nobody. Stop and return a revision |
| **2** | any `bias` gate | proceed *only* where a correction formula exists; stop where none does |
| **3** | `soft` gates in conflict | **§4's rank order decides which yields** |
| **4** | lens 6's review | it may refuse to advance what 1–3 cleared; it may not clear what they stopped |

§4's hierarchy is a tie-break **at level 3 and nowhere else**. Rank 1 does not
buy an oil objective past G17's RI-mismatch depth (~10 µm), and no rank raises
the disk's write bandwidth (G12a).

### Exceptions

- **E1 · Lens 5's standing `BLOCKED` is over** (2026-09-09). It computes, so
  **treat a failure from G20/G21/G22 as genuine.** G10, the gate this exception
  existed for, was removed the same day. Kept as a marker: a lens that blocks by
  design again needs its own line here, not the benefit of this one.
- **E2 · Convene lens 6 alone and last.** It reviews the other lenses' verdicts,
  so it cannot run beside them.
- **E3 · Lens 7 silent on heating ≠ heating cleared.** Trap heating is ungated
  by decision ([05 §5](docs/05-consensus-gate.md), [06 D6](docs/06-pitfalls.md)).
- **E4 · A conditional lens that was not convened leaves a hole, not a pass.**
  Lens 8 under ~30 min and lens 7 with no trap are absent; record their row in
  lens 6's bias ledger as `unevaluated`.
- **E5 · Convene lenses 2 and 3 together whenever frame rate is in play.** Lens
  3 does not own the rate, and its arithmetic is only as good as the rate handed
  to it. A *requested* rate is not evidence — G12b.
- **E6 · Convene lenses 1 and 5 together, and 1 and 4 likewise.** Light for SNR
  against the dose budget, and immersion against depth, run in opposite
  directions (01 §4).
- **E7 · Objective choice at load time is not an imaging decision.** It sits
  outside this ladder and outside §4 — load at 4× or 10×, whatever rank 1 wants
  (hard rule 5).
- **E8 · Do not correct a higher rank on lower-ranked grounds** — H4 below.
  Report the bias instead.
- **E9 · A return code is not a confirmation** — hard rule 1. Nothing advances
  on "the GUI accepted the command".

---

## 4. The imaging priority hierarchy

**Operator's ranking (KH, 2026-09-07).** When a proposal cannot satisfy every
axis at once, defend in this order. Rank 1 is protected hardest; rank 4 moves
first. Standing values are in §2.

| Rank | Axis | What it is on this bench | Owned by |
|:---:|---|---|---|
| **1** | **Spatial resolution** | Pixel size at the sample and the NA that feeds it | lens 4 (objective, immersion) · lens 2 (binning, ROI) |
| **2** | **Image quality** | SNR and localisation precision — whether a particle can be found and centred, not whether the picture is pretty | lens 2 (photon budget) · lens 1 (throughput) |
| **3** | **Time resolution** | *Achieved* frame period | lens 2 (frame interval) · lens 3 (arithmetic) |
| **4** | **Light source intensity** | Source level at the sample | lens 5 (level, duty, dose) · lens 1 |

### How to apply it

- **H1 · Concede from the bottom up.** Move intensity first, then frame rate,
  then accept lower SNR, and only last touch magnification, NA or binning.
  **Report every concession by name**; do not spend a rank silently.
- **H2 · Treat intensity as instrumental, not a goal.** It is the lever, bounded
  above by bleaching and light-driving and below by "the analysis cannot work" —
  the *working LUT* of README item 9. It is **not** licence to add light: the
  bound is a measured window and lens 5's gates are the fence.
- **H3 · Use the hierarchy only as a tie-break among `soft` and `bias` gates.
  It never overrides a `hard` gate** → §3 precedence, [05 §2](docs/05-consensus-gate.md).
- **H4 · Do not "correct" a higher rank on lower-ranked grounds.** 1×1 is not
  the SNR-optimal choice and **must not be changed to 2×2 on SNR grounds** — a
  Mortensen-style variance argument favours 65 nm pixels for single-particle
  localisation once background scales per pixel area. Same for the objective:
  the ~17.6 % Faxén drag inflation at the ~8 µm working depth was accepted with
  that bound stated. **Report the bias; do not silently correct it, and do not
  re-litigate the objective.**
- **H5 · If the intensity window comes back empty, escalate upward — visibly.**
  No light level working is the real result. Something above has to move (frame
  rate, dye, objective, binning); **state that revision, do not make it
  quietly.**
- **H6 · When the hierarchy cannot resolve it, hand the conflict to the human**
  as [05 §6 deadlock handling](docs/05-consensus-gate.md) — each lens, its
  number, its basis, and the options with what each one concedes.

### Where the ranking earns its keep

The cross-lens constraints in [01 §4](docs/01-architecture.md) each have no
single owner:

| Constraint | Lenses | Ranks in tension | Resolution |
|---|---|---|---|
| Pixel size — Nyquist vs σ_PSF ≈ pixel | 2 ↔ 6 | 1 vs 2 | **Opposite directions.** Rank 1 holds: keep the finer pixel, report the SNR cost |
| Light level vs light-driving | 1 ↔ 5 | 2 vs 4 | Raise intensity for SNR *inside* the working window; if it does not fit, H5 |
| Motion blur in the MSD | 2 ↔ 6 | 2 vs 3 | Shorten exposure and pay for it in light (rank 4) before lengthening the frame period |
| ROI vs statistics | 3 ↔ 6 | 1 vs 3 | The smaller ROI is the standing choice; the cost lands on lens 6's power, not on binning |
| Requested vs achieved frame rate | 2 ↔ 3 | 3 | A requested rate is not evidence (G12b). Judge rank 3 on the *achieved* period |

### What it does not cover

- **Objective choice at load time** — a safety decision, not an imaging one
  (hard rule 5, E7).
- It ranks axes, not *quantities*. Statistical power (G11), field count and
  duration are lens 6 and lens 8 questions and are not on this ladder.

### Status of this rule

Cite [`kb/expertise/imaging-priority-hierarchy.md`](kb/expertise/imaging-priority-hierarchy.md),
**not this file.** Read its *Stated vs reconstructed* table first: the ranking
and the meaning of rank 4 are KH's, dated 2026-09-07, but the `Why` is
**reconstructed** from four prior records rather than given in his words, the
five falsifiers are this repository's proposals, and the scope is assumed narrow
(single-particle tracking and microrheology) rather than assumed general. The
`TODO(human)` in that entry closes those three gaps.

---

## 5. Evidence rules the code enforces

- **`measured` vs `assumed`, with a separate `advances` axis that only
  `measured` can satisfy.** A literature value lets a gate *compute* and never
  lets a verdict advance → [`kb/literature/`](kb/literature/).
- **A refusal names what would resolve it** — the missing input and where it
  lives. A `BLOCKED` with no fix instruction is a bug.
- **`unevaluated` ≠ `cleared`** (hard rule 3). Collapsing them is how a
  plausible number becomes a wrong one.
- **Call lens 6 (`validity/`) last** — it reviews the other lenses' verdicts.
- **Lens 5 computes as of 2026-09-09**, for the first time. Power and
  illuminated area both exist, so there is irradiance, and **G20, G21 and G22
  run**. G10 was removed the same day ([04 §6](docs/04-decision-engine.md)).
  Take the numbers and their two limits from §2's lookup, not from memory.

---

## 6. Pixel size — the settled position, and why it was contested

**[`data/pixel_size.yaml`](data/pixel_size.yaml) is measured, all six rows** —
settled 2026-09-09 after this repository had argued itself into the opposite.

- The 2025-04 spreadsheet is a measurement (KH). Eleven of its twelve cells
  landing exactly on `6.5 / (M_obj × M_int)` means those objectives sit at their
  nominal magnification, **not** that somebody typed the quotient.
- The one that departs, 20× by 0.39 %, is a real **20.078×** objective — and the
  table proves it: the tube lens and the 6.5 µm sensor are shared by all six
  rows, so an error in either would move all six, and 20×'s own two cells give
  20.0785 by both paths, which rules out the intermediate magnifier. Nothing
  upstream is left; it is the lens.
- **The earlier reading is kept in that file's header, marked wrong.** It
  reasoned from the digits to how the spreadsheet was produced — an inference
  about provenance made without the instrument. The precedent is recorded in
  [`kb/systems/current.md`](kb/systems/current.md) under the trapping field:
  **an operator statement about their own instrument outranks a shape inferred
  from a drawing.**
- **100× does not come from the spreadsheet.** Two length standards were driven
  10 µm at it on 2026-09-03 — closed-loop piezo 0.06460 µm/px, AOD trap
  0.06445, agreeing to 0.24 % — so **0.06453** is recorded, agreeing with the
  spreadsheet's 0.065 to 0.73 %. Two independent measurements of the same cell.
- **G24 can say `pixel_size_measured` at any objective**, where before that day
  the honest answer was nowhere. Every pixel-size-dependent quantity can
  `advance` at every magnification — so **a demotion is now the edit that needs
  justifying**, and `tests/test_pixel_size.py::test_every_row_is_measured` is
  what notices one.
- The seven `.cfg` files match the table;
  `config/micromanager/set_pixel_size.py` **refuses to overwrite** a differing
  preset, so that resync is a decision and never a script run.
- ⚠ `D:\codes` still hardcodes `px_to_um = 0.065` in every MATLAB file, 0.73 %
  from the recorded 100×. Not this repository's to edit; lens 6 owns
  settings-versus-analysis mismatches
  → [`analysis/matlab/`](analysis/matlab/README.md).

---

## 7. Hardware, when it is in the loop

- **Nothing moves without its flag** (hard rule 4). The MCP server ships with
  `AGENTIC_MICROSCOPE_ALLOW_MOTION=0` and `..._ALLOW_LASER=0`
  ([`.mcp.json`](.mcp.json)) and refuses the two moving tools by default.
- **No MCP tool has reached a device.** Do not write as though one has.
- `hardware/lunf_power.py` is complete as transport and **refuses to transmit** —
  the LUN-F-XL DAC word format is undocumented and a guessed byte goes into a
  laser driver. **Leave that refusal in place; do not "fix" it by guessing.**
- **Known false leads, each of which cost a session.** `Breakpoints > Enable
  Bits` is `0000`, so `TRAP_PATT_RELEASE_BP` returns `0` while doing nothing ·
  the Tweez GUI has **no** trap-count ceiling (160 created and deleted cleanly
  in one pass) · `10012` on a Kinetix is **usually a wedge, not ownership
  contention** — one standalone snap on that body clears it.

---

## 8. Commands

```bash
python mcp_server/bootstrap.py --dry-run
```

Prints the path of an interpreter that has the dependencies, or exits non-zero
naming what to install. **Use it instead of searching the filesystem** — on the
instrument PC that is `~/venvs/auto_microscope` (Python 3.12.10, outside the
repo so it survives a clean checkout). It does not exist on other machines, and
the MCP server fails to connect where it is absent.

```bash
pytest -q -rs
```

1211 passed, 10 skipped on Windows, of 1,274 (measured 2026-09-09; macOS and
Linux print 1210/11 — one Windows-only test — **not re-measured there**). Two
kinds of skip: three whole modules behind `pytest.importorskip("pymmcore_plus")`
holding 56 tests that need a Micro-Manager device-adapter install, and seven
`requires_cv2` test items in `tests/test_objective_offsets.py` that call OpenCV
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

Two rules follow. **If a test calls into a deferred `import cv2`, mark it
`requires_cv2`** — every cv2 import here sits inside a function body, so the
module loads and only the call fails. And **a timing test may assert what the
mechanism guarantees, not how well the OS scheduled it**: `sleep_until`'s
overshoot bound is 20 ms on an owned machine and 250 ms where `CI` is set,
because a shared runner's scheduler is not a property of this code.

```bash
python -m optics.cli check config/channels/proposed-2color.yaml
```

The eight lenses are `optics` · `detection` · `compute` · `sample` · `photo` ·
`validity` · `stability` · `trapping`. Each has `checks.py` · `gate.py` ·
`cli.py`, and all but `optics` and `trapping` also have `setup.py`. Every gate
formula is in [04](docs/04-decision-engine.md): of 31 gate IDs, 28 are
implemented, `G2`–`G4` exist only as a threshold and a default verdict in that
document, and **`G10` is vacant** — removed 2026-09-09, and the number is not
reused.

```bash
python -m knowledge.cli write
```

Rebuilds [`kb/INDEX.md`](kb/INDEX.md) from the `id` · `question` · `date`
frontmatter each entry carries. **Run it after adding anything to `kb/`**;
`tests/test_kb_index.py` fails if you don't, and also on a file with no
frontmatter or a supersession link that resolves to nothing. The index is
**pointers only, never a citation** — open the entry and cite that
([09 §7](docs/09-knowledge-capture.md)).

```bash
python -m knowledge.cli plan-check
```

Refuses a `kb/plans/` entry whose shape a hardware skill would misread — a
missing section, an unknown subsystem, a committee verdict silent on what was
**not** evaluated, or a sequence step confirming on a return code. That last one
is hard rule 1 held at the plan instead of at the instrument.

---

## 9. Writing anything down

Do not duplicate what the repo already records. Pick the right home:

| Goes to | For |
|---|---|
| `data/*.yaml`, `kb/calibrations/` | a measured constant |
| `kb/decisions/YYYY-MM-DD-<slug>.md` | a design choice or a scope decision, dated |
| `kb/plans/YYYY-MM-DD-<slug>.md` | one hardware run, **before** it happens. Copy `_template.md`; `plan-check` refuses a shape a skill would misread. Graduates into `kb/decisions/` once run → [05 §6](docs/05-consensus-gate.md) |
| `kb/expertise/<id>.md` | durable expert judgment. `Why` and `Falsifying condition` are **mandatory** ([09 §2](docs/09-knowledge-capture.md)) |
| `kb/sessions/YYYY-MM-DD.md` | the day's narrative. **A failed session gets a *longer* entry, not a shorter one.** Numbers, not adjectives |

And from [09 §7](docs/09-knowledge-capture.md): show it and get confirmation
before storing · never store without a `Why` · always ask for the falsifier ·
never mix a computed result and an expert judgment into one entry · **the
agent's own inference is not a source** · capture a correction first, because a
correction is dense knowledge · always link when citing the KB, and give no
advice without a source.

---

## 10. Code conventions

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
- **State what is *not* true alongside what is.** Keep that when editing README,
  SAFETY or `docs/`: no claim without its date, its evidence tier, and its
  limit.
- **Cite a file, not a line number.** Line references into `kb/systems/current.md`
  drift on every edit above them; name the section or the YAML key instead.

---

## 11. Public-repository constraint

Vendor manuals, proprietary DLLs, and commercial correspondence are in **no
commit here** — removed from the whole history on 2026-08-28, not just from the
tip. Do not reintroduce them, and do not paste quotes, pricing or named contacts
into tracked files. The technical conclusions drawn from them are stated inline
wherever they are used → [NOTICE.md](NOTICE.md).
