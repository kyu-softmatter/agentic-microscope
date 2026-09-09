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
| **1** | **Spatial resolution** | Pixel size at the sample and the NA that feeds it. Standing choice: `100x-Oil` at **1×1 binning, 0.065 µm/px** | lens 4 (objective, immersion) · lens 2 (binning, ROI) | objective, intermediate mag, binning |
| **2** | **Image quality** | SNR and localisation precision — whether a particle can be found and centred, not whether the picture is pretty | lens 2 (photon budget, SNR) · lens 1 (throughput) | exposure, gain, readout mode, filters |
| **3** | **Time resolution** | Achieved frame period. Standing choice: **20.0 ms exposure ⇒ ~50 fps** (this camera takes the exposure as the period) | lens 2 (frame interval) · lens 3 (frame-rate arithmetic) | exposure, interval, ROI, data rate |
| **4** | **Light source intensity** | Source level at the sample. Standing choice: Aura **GREEN ~80/1000** | lens 5 (light level, duty, dose) · lens 1 | level %, illumination duty |

Standing values and the reasoning behind them:
[`kb/expertise/microrheology-standard-conditions.md`](kb/expertise/microrheology-standard-conditions.md).

### How to apply it

- **H1 · Concede from the bottom up.** To fix a shortfall, move intensity first,
  then frame rate, then accept lower SNR, and only last touch magnification, NA
  or binning. Report every concession by name; do not spend a rank silently.
- **H2 · Intensity is instrumental, not a goal.** It is the lever, bounded above
  by bleaching and light-driving and below by "the analysis cannot work" — the
  *working LUT* of README item 9. It is **not** licence to add light: the bound
  is a measured window and lens 5's gates are the fence.
- **H3 · The hierarchy is a tie-break among `soft` and `bias` trade-offs. It
  never overrides a `hard` gate** → [05 §2](docs/05-consensus-gate.md). Rank 1
  does not buy an oil objective past G17's RI-mismatch depth (~10 µm), and no
  rank raises the disk's write bandwidth (G12a).
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
| Requested vs achieved frame rate | 2 ↔ 3 | 3 | A requested rate is not evidence (G12b). Rank 3 is judged on the *achieved* period |

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
- It ranks axes, not *quantities*. Statistical power (G11), field count and
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

## 2. Evidence rules the code enforces

- **`measured` vs `assumed`, with a separate `advances` axis that only
  `measured` can satisfy.** A literature value lets a gate *compute* and never
  lets a verdict advance → [`kb/literature/`](kb/literature/).
- **A refusal names what would resolve it** — the missing input and where it
  lives. A `BLOCKED` with no fix instruction is a bug.
- **`unevaluated` ≠ `cleared`.** Collapsing them is how a plausible number
  becomes a wrong one. A margin of 10.00 against a threshold nobody supplied
  still does not advance.
- **Lens 6 (`validity/`) reviews the other lenses' verdicts, so call it last.**
- Two blockers are load-bearing and still open: `power_at_sample_mw` is `{}` for
  every line of every source, and `bleach_photons` is empty for every dye — so
  **lens 5 returns `BLOCKED` on this instrument by design.** Every dose number
  is relative until a power meter sits at the sample plane.

## 3. Hardware, when it is in the loop

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

## 4. Commands

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

1186 passed, 10 skipped on Windows, of 1,249 (measured 2026-09-09; macOS and
Linux print 1185/11 — the 2026-09-07 figure plus the 24 added since, not
re-measured there — one Windows-only test). Two kinds of skip: three whole
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
`gate.py` · `setup.py` · `cli.py`. The formulas behind all 32 gates are
collected in [04](docs/04-decision-engine.md); 29 are implemented, and `G2`–`G4`
exist only as a threshold and a default verdict in that document.

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

## 5. Writing anything down

Do not duplicate what the repo already records. Pick the right home:

| Goes to | For |
|---|---|
| `data/*.yaml`, `kb/calibrations/` | a measured constant |
| `kb/decisions/YYYY-MM-DD-<slug>.md` | a design choice or a scope decision, dated |
| `kb/expertise/<id>.md` | durable expert judgment. `Why` and `Falsifying condition` are **mandatory** ([09 §2](docs/09-knowledge-capture.md)) |
| `kb/sessions/YYYY-MM-DD.md` | the day's narrative. **A failed session gets a *longer* entry, not a shorter one.** Numbers, not adjectives |

And the rules from [09 §7](docs/09-knowledge-capture.md): show it and get
confirmation before storing · never store without a `Why` · always ask for the
falsifier · never mix a computed result and an expert judgment into one entry ·
**the agent's own inference is not a source** · capture a correction first,
because a correction is dense knowledge · always link when citing the KB, and
give no advice without a source.

## 6. Code conventions

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

## 7. Public-repository constraint

Vendor manuals, proprietary DLLs, and commercial correspondence are in **no
commit here** — removed from the whole history on 2026-08-28, not just from the
tip. Do not reintroduce them, and do not paste quotes, pricing or named contacts
into tracked files. The technical conclusions drawn from them are stated inline
wherever they are used → [NOTICE.md](NOTICE.md).
