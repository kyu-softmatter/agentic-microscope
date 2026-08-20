# experimentalist

An agent that designs experiments and proposes microscope settings.

It builds a knowledge base from past microscope metadata and hardware specs;
given the goal of a new experiment, it proposes **settings that are executable on
the current instrument**, with the reasoning attached. A proposal is confirmed
only once it passes review by every subsystem lens of the committee — optics,
detection, compute resources, sample geometry, photo-perturbation, and
measurement validity, plus optical tweezers and mechanical/environmental when
those apply.

---

## Current status

**Design complete; all eight committee lenses are implemented.** Nine design
documents, 32 hard gates (G1–G32) across ~15,600 lines of Python (modules, excluding tests), 618 tests
passing. The six standing lenses — optics, detection, compute resources, sample
geometry, photo-perturbation, measurement validity — and both conditional lenses
— optical tweezers, mechanical/environmental — each compute their verdict and
report it through their committee gate. Lenses 4 · 5 · 6 additionally carry the
qualitative half of their judgment as LLM subagents in
[`.claude/agents/`](.claude/agents/), layered on top of their code, because part
of what they weigh has no closed form. Three things are deliberately left
ungated and named as such: vibration and stage repeatability (no measurement
channel exists), local heating at 1064 nm ([06 D6](docs/06-pitfalls.md)), and
near-wall Faxén drag ([06 D8](docs/06-pitfalls.md)), which is absorbed by
in-situ trap calibration rather than corrected by formula.

What is blocking progress is mostly **facts, not code** — the gates run, but
return `BLOCKED` for want of measured inputs. Illumination power at the sample is
the top blocker: `power_at_sample_mw` is empty for every registered light source,
and it cannot be substituted by code (a power meter is required). The remaining
hardware measurements have runnable scripts in
[`calibration/`](calibration/), and results already collected are in
[`kb/calibrations/`](kb/calibrations/). → [Phase 0](docs/07-roadmap.md)

Read [the pitfalls](docs/06-pitfalls.md) before starting any implementation.

---

## Document map

| Document | Contents |
|---|---|
| [01 Architecture](docs/01-architecture.md) | Overall design, layers, 5 design principles, committee composition, folder structure |
| [02 Knowledge base](docs/02-knowledge-base.md) | 3-tier normalization, **three-way device wiring cross-check**, off-ledger settings, SQLite schema |
| [03 Cross-system transfer](docs/03-cross-system-transfer.md) | Current instrument ≠ past instrument. What transfers and what does not |
| [04 Decision engine](docs/04-decision-engine.md) | Decision order, photon budget / SNR / sampling / timing formulas, the 32 hard gates |
| [05 Committee](docs/05-consensus-gate.md) | hard/bias/soft distinction, **difficulty grades**, **improvement proposals (sensitivity analysis)**, deadlock handling |
| [06 Pitfalls](docs/06-pitfalls.md) | What actually goes wrong in this data and this science — grounded in measured evidence |
| [07 Roadmap](docs/07-roadmap.md) | Phase 0 (secure the evidence) → 5 (automate manipulation). Three things that pay off immediately |
| [08 Optics lens design](docs/08-optical-path-spec.md) | Reviewer computation structure (check registry), hardware YAML description format |
| [09 Expertise capture](docs/09-knowledge-capture.md) | **From conversation into the KB.** The real purpose of this project |
| [Observed systems](reference/observed-systems.md) | ⚠ **Old setup** inventory. Full scan of 2,343 metadata records |
| [Nikon quote (2024-09-29)](reference/quotes/2024-09-29_nikon-quote-REDACTED_ti2e-csuw1_takatori.md) | Original Ti2E+CSU-W1 quote. Many part numbers cross-checked against the current system |
| [Teledyne Kinetix 22 correspondence (2026-08-20)](reference/quotes/2026-08-20_teledyne-kinetix22-inquiry_price-and-demo-loan.md) | Indicative unit price, lead time, demo-loan terms, vendor contact. **Commercial facts only** — its flat spec table conflates three mutually exclusive readout modes, so specs still come from `data/detectors.yaml > Kinetix22` |

**Code**

| Module | Lens | Status |
|---|---|---|
| [`optics/`](optics/) | 1 · optics | Implemented |
| [`detection/`](detection/) | 2 · detection (G5–G9) | Implemented |
| [`compute/`](compute/) | 3 · compute resources (G12a–c, G13a–d) | Implemented, hardened 2026-08-19 ([`kb/decisions/2026-08-19-lens-3-hardening.md`](kb/decisions/2026-08-19-lens-3-hardening.md)): data rate now sums **one stream per camera** and reads the container width off the readout mode; G12b refuses a requested frame rate as evidence ([06 C4](docs/06-pitfalls.md)); G13d gates the RAM-capture path at a 32 GB authorized ceiling. [`compute/drops.py`](compute/drops.py) adds the post-hoc half — `python -m compute.cli scan <archive> --contaminated-only` needs no hardware and runs on the existing archive today. Verified 2026-08-20 against the real `D:\data` archive: both MM schema generations parse, and it also flags **truncated** runs, where MM stopped early while its Summary kept advertising the planned frame count |
| [`sample/`](sample/) | 4 · sample geometry & optics (G15–G19) | Implemented. Scope fixed 2026-08-19 ([`kb/decisions/2026-08-19-lens-4-scope.md`](kb/decisions/2026-08-19-lens-4-scope.md)): sample-medium index settled at 1.333, coverslip settled at 170 µm — matching every objective's design ([`kb/expertise/coverslip-thickness-in-use.md`](kb/expertise/coverslip-thickness-in-use.md)) — and wave-optics aberration + wavelength/temperature RI **ungated by decision**. So **a micrometer reading of the coverslip is the only routine assumption left, and it is sufficient**: `100x-Oil` at 9 µm depth then reaches `PASS · TIGHT · advances YES`, and `40x-WI` with its collar recorded reaches `PASS · ROUTINE · advances YES`. Past ~10 µm depth an oil objective is held by G17's RI mismatch instead. ATPS BLOCKs by design and is asked at experiment time, not pre-populated |
| [`photo/`](photo/) | 5 · photo-perturbation (G10, G20–G22) | Implemented. **BLOCKED on the real instrument** until `power_at_sample_mw` is measured and dyes get `bleach_photons` — that refusal is the intended behaviour |
| [`validity/`](validity/) | 6 · measurement validity (G11, G23–G27) | Implemented. Reviews the other lenses' verdicts, so **call it last**. Judges each `intended_quantities` entry separately — a biased MSD and a sound intensity profile can come out of one session — and checks a declared correction against a registry rather than believing it. G27 is currently the only thing that notices the committee never convened |
| [`stability/`](stability/) | 8 · mechanical & environmental (G28–G32) | Implemented, conditional on acquisitions over 30 min. G28 (PFS lock) and G31 (sedimentation) work today; G29 BLOCKED until a drift rate is measured; vibration and stage repeatability ungated |
| [`trapping/`](trapping/) | 7 · optical tweezers (G14) | Physics library + committee gate wired. Objectives whose design NA exceeds the sample index are TIR-clipped and computed rather than refused (2026-08-18) — see [`kb/expertise/oil-objective-trapping-in-water.md`](kb/expertise/oil-objective-trapping-in-water.md). Scope fixed 2026-08-19: the dial-% → mW calibration is **deferred** (so verdicts stay `evidence: assumed`), water-only media, and local heating + near-wall Faxén drag are **ungated by decision**, not gaps ([06 D6 · D8](docs/06-pitfalls.md), [`kb/decisions/2026-08-19-lens-7-scope.md`](kb/decisions/2026-08-19-lens-7-scope.md)) |
| [`.claude/agents/`](.claude/agents/) | 3 · 4 · 5 · 6 · 8 | Prompt-only, by design: layered over the code above rather than standing in for it. For lenses 4 · 5 · 6 · 8 that is the qualitative half — the part with no closed form. Lens 3 is different: it is fully deterministic, so [`compute-resources.md`](.claude/agents/compute-resources.md) only gathers inputs, runs the code, and carries the 2↔3 and 3↔6 cross-lens wires |

The formulas behind every gate are collected in
[04](docs/04-decision-engine.md).

```bash
.venv\Scripts\python -m optics.cli check config/channels/proposed-2color.yaml
```

[`calibration/`](calibration/) — Phase 0 hardware measurement scripts (disk
bandwidth, camera row time, EM1/EM2 camera identification). Ready to run on
reconnecting to the microscope PC. Illumination power is the one exception: it
needs a power meter and cannot be replaced by code.

```bash
.venv\Scripts\python -m calibration.cli disk-bandwidth D:\data\_bench --size-gb 4
```

---

## The problem this project solves

Three things set it apart from a generic "microscope settings recommendation
chatbot."

**1. Past settings cannot be copied verbatim.**
The 2,343 records in `D:\data` came from one particular Nikon + Photometrics
combination, and the system in use now is different. So device values like
`Exposure=80ms, Level=5` are not transferable. What is transferable are the
**physical quantities** that setting produced — photon flux at the sample,
effective pixel size, excitation/emission bands, photon budget. Converting to
physical quantities and reprojecting onto the current instrument is the axis of
this system.
→ [03](docs/03-cross-system-transfer.md)

**2. Illumination can be an experimental variable, not a measurement tool.**
In systems like light-driven active colloids, FRAP, or photo-induced
aggregation, the excitation light **drives** the sample. "Raise the light for
SNR" is correct in purely optical terms and can ruin the experiment in colloidal
terms. The lenses are separated to catch that conflict.
→ [05](docs/05-consensus-gate.md)

**3. The optimal setting depends on the analysis goal.**
For the same sample, the optimal pixel size and exposure time run in **opposite
directions** depending on whether you are observing morphology or tracking
particles. Applying Nyquist mechanically gives the wrong answer for
microrheology.
→ [06 §1](docs/06-pitfalls.md)

---

## Sources used

| Source | Location | Status |
|---|---|---|
| Micro-Manager acquisition metadata, 2,343 records | `D:\data\**\*_metadata.txt` | Obtained (30 GB) |
| ND2 / LIF (separate Nikon and Leica systems) | `D:\data\**\*.nd2`, `*.lif` | Obtained, parser not implemented |
| Experiment protocols | `D:\experiment method` | Obtained, not yet integrated |
| Analysis code | `D:\codes` | Obtained, not yet integrated |
| **Current system MM `.cfg`** | `kb/systems/current.md` | Obtained (`DMD_dualcam.cfg`, 2026-07-03) — most serials not yet obtained |
| Measured pixel size calibration | `kb/systems/current.md` | Obtained (Kinetix, 4x–100x × 1x/1.5x, 2025-04) |
| Camera row time, disk bandwidth | `kb/calibrations/` | Obtained (2026-08-12) |
| **Illumination power at sample** | `data/light_sources.yaml` | **Not obtained — top blocker** |
| **Hardware spec documents** | Location unspecified | **Not obtained** |

The working PC and the microscope PC are separate, so a live connection is out of
scope. For now this produces offline recommendations only.
→ [07](docs/07-roadmap.md)
