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
1 · 2 · 3  (+7 if trapping)     code, in parallel      deterministic, fast
      ↓        any hard gate m < 1 → stop here, return a revision
4 · 5      (+8 if >30 min)      subagents, parallel    fed the computed results
      ↓
6                               subagent, alone        reviews all of the above
      ↓
synthesis → verdict
```

**The computational lenses run first** so that no subagent deliberates over a
physically impossible proposal, and **their numbers are the input** to the
judgment lenses — a judgment lens never generates the number it is judging.

⚠ [05 §6](docs/05-consensus-gate.md)'s diagram puts 4·5·6·8 in one parallel
block. **This supersedes that**: lens 6 reviews the other lenses' verdicts, so
it cannot run beside them.

### Precedence — the kind of gate outranks the lens

A lens does not win an argument by being lens 1. **The gate's kind decides
first**, and only within one kind does anything else apply
([05 §2](docs/05-consensus-gate.md)):

| | What it is | Who may overrule it |
|---:|---|---|
| **0** | [SAFETY.md](SAFETY.md) | nobody. Not a lens, not negotiable |
| **1** | any `hard` gate at `m < 1` | nobody. Stop and return a revision |
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
  Lens 8 under ~30 min and lens 7 with no trap are absent; their row in lens 6's
  bias ledger is `unevaluated`.
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
- **Two of the eight lenses judge nothing.** Lens 5 and lens 8 both became
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

1194 passed, 11 skipped on macOS, of 1,205 (measured 2026-09-09 after G20's
removal took 16 tests with it; Windows prints 1195/10 — one Windows-only test,
not re-measured there). Two kinds of skip: three whole
modules behind `pytest.importorskip("pymmcore_plus")` holding 56 tests that need
a Micro-Manager device-adapter install, and seven `requires_cv2` tests in
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
`photo` · `validity` · `stability` · `trapping`, each with `checks.py` ·
`gate.py` · `setup.py` · `cli.py`. All **43 checks** are collected in
[04](docs/04-decision-engine.md), addressed `L<lens>.<n>` since 2026-09-11 —
the lens number from [01 §4](docs/01-architecture.md), then the check's
position in it. **19 `hard` · 6 `bias` · 3 `soft` can fail; 15 `info` only
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
