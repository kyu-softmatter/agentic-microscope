# experimentalist

An agent that designs experiments and proposes microscope settings.

It builds a knowledge base from past microscope metadata and hardware specs;
given the goal of a new experiment, it proposes **settings that are executable on
the current instrument**, with the reasoning attached. A proposal is confirmed
only once it passes review by every subsystem lens of the committee — optics,
detection, compute resources, sample geometry, photo-perturbation, and
measurement validity, plus optical tweezers and mechanical/environmental when
those apply.

> **Public repository.** Vendor manuals, proprietary DLLs, and commercial
> correspondence are in no commit here — removed from the whole history on
> 2026-08-28, not just from the tip. See [NOTICE](NOTICE.md) for what was
> removed, what that did and did not accomplish, and how to restore the hardware
> dependencies.

---

## Architecture

Every stage either **reads** evidence out of the knowledge base or **writes**
evidence back into it. `R` marks a read, `W` marks a write.

```text
      RESEARCHER GOAL    "track single bacteria in a crowded gel for 2 h"
              |
              v
  +-------------------------------------------------------------------+
  |  GOAL -> REQUIRED MEASUREMENT                                     |
  |  what has to be true of the data for the question to be           |
  |  answerable at all                                                |
  |                                                                   |
  |  R  kb/systems/current.md     which instrument this actually is   |
  +---------------------------------+---------------------------------+
                                    v
  +-------------------------------------------------------------------+
  |  COMMITTEE               8 lenses . 32 hard gates (G1-G32)        |
  |                                                                   |
  |    1 optics/     2 detection/    3 compute/     4 sample/         |
  |    5 photo/      6 validity/     7 trapping/    8 stability/      |
  |                                                                   |
  |  Lens 6 reviews the other lenses' verdicts, so it is called last.  |
  |  G27 is the only thing that notices the committee never convened.  |
  |  Lenses 3.4.5.6.8 carry an LLM subagent in .claude/agents/,        |
  |  layered over the code rather than standing in for it. It supplies |
  |  the half of a judgment that has no closed form, and originates    |
  |  no number.                                                       |
  |                                                                   |
  |  R  kb/systems/        device wiring, cross-checked three ways     |
  |  R  kb/calibrations/   what has actually been measured            |
  |  R  kb/expertise/      tacit priors, each with its own falsifier   |
  |  R  data/*.yaml        detectors, objectives, filters, light       |
  |                        sources, fluorophores, spectra             |
  +---------------------------------+---------------------------------+
                                    |
           +------------------------+------------------------+
           v  a hard gate fails                              v  advances
  +----------------------------+            +----------------------------+
  |  BLOCKED                   |            |  PROPOSAL                  |
  |  names the missing input   |            |  settings, plus feasibility|
  |  and what would supply it  |            |  evidence tier, confidence |
  |                            |            |  and per-check margins     |
  |  W  kb/decisions/          |            |                            |
  |     the verdict, and any   |            |  R  archive precedent from |
  |     effect left ungated    |            |     2,343 MM records, as   |
  |     BY DECISION            |            |     physical quantities    |
  +-------------+--------------+            +-------------+--------------+
                |                                         |
                v                                         |
      back to the researcher                              |
      -- no setting is proposed                           |
                                                          v
  +-------------------------------------------------------------------+
  |  hardware/                                      drivers, present  |
  |  microscope.py . optical_tweezers.py . piezo_stage.py .           |
  |  piezo_waveform.py . tweezers_drive.py . orchestrator.py          |
  |                                                                   |
  |  (!) Offline today. The working PC and the microscope PC are      |
  |      separate, so this repo produces recommendations, not motion. |
  |      Vendor DLLs are not published here -- see NOTICE.md.         |
  |                                                                   |
  |  lunf_power.py -- LUN-F-XL per-line power over an FTDI SPI link:  |
  |  [X] REFUSES TO TRANSMIT. Nikon does not document the DAC word    |
  |      format, and a guessed byte goes into a laser driver.         |
  +---------------------------------+---------------------------------+
                                    v
             ACQUISITION  ->  ANALYSIS  ->  RESULTS        [roadmap]
             phases 1-5, docs/07-roadmap.md
                                    |
                                    |  W  a measured value replaces an
                                    |     assumed one, and every gate that
                                    |     consumed it becomes decidable
                                    v
  +===================================================================+
  |  KNOWLEDGE BASE                                             kb/   |
  +===================================================================+
  |  kb/systems/       what this instrument physically is. Device     |
  |                    wiring cross-checked three independent ways;   |
  |                    current.md is the live configuration.          |
  |                                                                   |
  |  kb/calibrations/  numbers that were actually measured -- pixel   |
  |                    size per objective, camera row time, disk      |
  |                    bandwidth.                                     |
  |                                                                   |
  |  kb/expertise/     tacit lab judgment made machine-readable, e.g. |
  |                    which coverslip thickness is really in use, or |
  |                    trapping with an oil objective in water.       |
  |                                                                   |
  |  kb/decisions/     what was decided and why -- scope fixes, lens  |
  |                    hardening, and effects ungated BY DECISION     |
  |                    rather than by omission.                       |
  |                                                                   |
  |  Ingested: 2,343 heterogeneous Micro-Manager acquisitions across  |
  |  two schema generations. Every record carries its source, its     |
  |  trust level, its applicable scope, and the observation that      |
  |  would falsify it.                                                |
  +---------------------------------+---------------------------------+
                                    |
                                    +--> R  feeds the next proposal
```

### When the knowledge base changes

| Moment | Direction | What moves |
|---|---|---|
| A review is requested | **R** | system config, measured calibrations, expertise priors, the `data/*.yaml` registries |
| A hard gate fails | **W** | the verdict and the input that would resolve it, into `kb/decisions/` |
| A proposal is generated | **R** | precedent from the 2,343-record archive — as physical quantities, never as raw device values |
| A Phase 0 calibration is performed | **W** | a measured value replaces an assumed one, and every gate that consumed it becomes decidable |
| An effect is deliberately not gated | **W** | recorded as *ungated by decision* with the reasoning — vibration and stage repeatability, 1064 nm local heating ([06 D6](docs/06-pitfalls.md)), near-wall Faxén drag ([06 D8](docs/06-pitfalls.md)) |
| A judgment is made in conversation | **W** | captured out of chat into a durable expertise note → [09](docs/09-knowledge-capture.md), *the real purpose of this project* |

The falsifier field is the point: a stored prior is not permanent, and it carries
up front the observation that would retire it.

Lens-by-lens implementation status is in the **Code** table below.

---

## Current status

**Design complete; all eight committee lenses are implemented.** Nine design
documents, 32 hard gates (G1–G32), full test suite passing. The six standing
lenses — optics, detection, compute resources, sample geometry,
photo-perturbation, measurement validity — and both conditional lenses —
optical tweezers, mechanical/environmental — each compute their verdict and
report it through their committee gate. Lenses 4 · 5 · 6 · 8 additionally carry
the qualitative half of their judgment as LLM subagents in
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

## What a refusal looks like

A missing input blocks the answer instead of being interpolated. Here is the
photo-perturbation lens on this instrument — unedited apart from wrapping the
long lines:

```console
$ .venv\Scripts\python -m photo.cli check --channel config/channels/proposed-2color.yaml \
      --channel-name 488 --exposure-ms 80 --n-frames 7200 --frame-interval-ms 1000

========================================================================
488 (AlexaFluor488) @ 470 nm  irradiance unknown   ->  BLOCKED
feasibility: UNKNOWN   evidence: assumed   confidence: none   advances: NO
assumed:
  - sample photoresponsiveness (never asked, so light-driving is
    unconfirmed rather than cleared)
========================================================================

  findings
    [FAIL] missing.power_at_sample
           No measured mW at the sample plane (and/or no illuminated area),
           so irradiance is unknown and every dose quantity in this lens is
           undefined. The metadata's percent setting is not a physical
           quantity and does not transfer between instruments.
        -> Supply a measured mW for this evaluation, or accept that every
           dose number stays relative. The registry fix is sample-plane
           power per level in data/light_sources.yaml > power_at_sample_mw,
           which can only be measured, never computed -- but all laser
           power measurement is deferred by decision (user, 2026-08-19,
           docs/07 Phase 0), so this is not being proposed as the next
           task. Until it lands, BLOCKED here is the honest answer.
    [FAIL] missing.bleach_photons
           The dye has no `bleach_photons` on record, so the photobleaching
           budget (G10) has nothing to count against. docs/04 §6: the
           qualitative `photostability` grade is explicitly not a
           substitute.
        -> Add bleach_photons (mean photons emitted before bleaching) to
           the dye's entry in data/fluorophores.yaml, from the literature
           or a measured decay curve. It is empty for every dye in the
           registry today.
```

Two properties of that output matter more than the refusal itself.

**It names its own assumption first.** `sample photoresponsiveness (never asked,
so light-driving is unconfirmed rather than cleared)` — *unevaluated* and
*cleared* are carried as different states, because collapsing them is how a
plausible number becomes a wrong one.

**A refusal is not a dead end.** Each finding names the input that would resolve
it and where that input lives. Supplying both missing measurements on the command
line moves the same channel to `PASS_WITH_CHANGES` — and it still does not
advance:

```console
$ ... --power-mw 2.5 --area-um2 40000 --bleach-photons 1e5

488 (AlexaFluor488) @ 470 nm  6.2 W/cm^2   ->  PASS_WITH_CHANGES
feasibility: MARGINAL   evidence: assumed   confidence: low   advances: NO

  margins (achieved / required; 1.0 = exactly at the limit)
      0.20  perturbation.photobleaching          ##
     10.00  perturbation.saturation              ####################
     10.00  perturbation.light_driving           ####################
     10.00  perturbation.total_dose              ####################
     10.00  perturbation.trap_heating_unowned    ####################

  findings
    [WARN] perturbation.photobleaching
           About 100.0% of the label bleaches over 7200 frames, past the
           20% limit. Intensity decays through the movie, so anything
           derived from brightness drifts with it. This is a **lower
           bound** -- bleaching is often superlinear in intensity (triplet
           pathways).
    [WARN] perturbation.light_driving
           Nobody has said whether this sample responds to light, so
           6.2 W/cm^2 is unevaluated, not cleared. [...] The margin below
           is not a judgement -- there is nothing yet to judge.
```

The `light_driving` margin reads 10.00 and the verdict still refuses to advance,
because that margin is computed against a threshold nobody has supplied. A number
that looks safe is not the same as a question that has been answered.
→ [05](docs/05-consensus-gate.md), [06 D2](docs/06-pitfalls.md)

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
| Vendor correspondence *(not published — see [NOTICE](NOTICE.md))* | Purchase quotes and vendor email threads are the provenance behind several `data/*.yaml` entries. They carry pricing, lead times, and named contacts, so they are held privately; the technical conclusions drawn from them are stated inline wherever they are used |

**Code**

| Module | Lens | Status |
|---|---|---|
| [`optics/`](optics/) | 1 · optics | Implemented |
| [`detection/`](detection/) | 2 · detection (G5–G9) | Implemented |
| [`compute/`](compute/) | 3 · compute resources (G12a–c, G13a–d) | Implemented, hardened 2026-08-19 ([`kb/decisions/2026-08-19-lens-3-hardening.md`](kb/decisions/2026-08-19-lens-3-hardening.md)): data rate now sums **one stream per camera** and reads the container width off the readout mode; G12b refuses a requested frame rate as evidence ([06 C4](docs/06-pitfalls.md)); G13d gates the RAM-capture path at a 32 GB authorized ceiling. [`compute/drops.py`](compute/drops.py) adds the post-hoc half — `python -m compute.cli scan <archive> --contaminated-only` needs no hardware and runs on the existing archive today. Verified 2026-08-20 against the real `D:\data` archive: both MM schema generations parse, and it also flags **truncated** runs, where MM stopped early while its Summary kept advertising the planned frame count |
| [`sample/`](sample/) | 4 · sample geometry & optics (G15–G19) | Implemented. Scope fixed 2026-08-19 ([`kb/decisions/2026-08-19-lens-4-scope.md`](kb/decisions/2026-08-19-lens-4-scope.md)): sample-medium index settled at 1.333, coverslip settled at 170 µm — matching every objective's design ([`kb/expertise/coverslip-thickness-in-use.md`](kb/expertise/coverslip-thickness-in-use.md)) — and wave-optics aberration + wavelength/temperature RI **ungated by decision**. So **a micrometer reading of the coverslip is the only routine assumption left, and it is sufficient**: `100x-Oil` at 9 µm depth then reaches `PASS · TIGHT · advances YES`, and `40x-WI` with its collar recorded reaches `PASS · ROUTINE · advances YES`. Past ~10 µm depth an oil objective is held by G17's RI mismatch instead. ATPS BLOCKs by design and is asked at experiment time, not pre-populated |
| [`photo/`](photo/) | 5 · photo-perturbation (G10, G20–G22) | Implemented. **BLOCKED on the real instrument** until `power_at_sample_mw` is measured and dyes get `bleach_photons` — that refusal is the intended behaviour, and [the transcript above](#what-a-refusal-looks-like) is it |
| [`validity/`](validity/) | 6 · measurement validity (G11, G23–G27) | Implemented. Reviews the other lenses' verdicts, so **call it last**. Judges each `intended_quantities` entry separately — a biased MSD and a sound intensity profile can come out of one session — and checks a declared correction against a registry rather than believing it. G27 is currently the only thing that notices the committee never convened |
| [`stability/`](stability/) | 8 · mechanical & environmental (G28–G32) | Implemented, conditional on acquisitions over 30 min. G28 (PFS lock) and G31 (sedimentation) work today; G29 BLOCKED until a drift rate is measured; vibration and stage repeatability ungated |
| [`trapping/`](trapping/) | 7 · optical tweezers (G14) | Physics library + committee gate wired. Objectives whose design NA exceeds the sample index are TIR-clipped and computed rather than refused (2026-08-18) — see [`kb/expertise/oil-objective-trapping-in-water.md`](kb/expertise/oil-objective-trapping-in-water.md). Scope fixed 2026-08-19: the dial-% → mW calibration is **deferred** (so verdicts stay `evidence: assumed`), water-only media, and local heating + near-wall Faxén drag are **ungated by decision**, not gaps ([06 D6 · D8](docs/06-pitfalls.md), [`kb/decisions/2026-08-19-lens-7-scope.md`](kb/decisions/2026-08-19-lens-7-scope.md)) |
| [`hardware/`](hardware/) | drivers | Microscope, optical tweezers, piezo stage and waveform, trap patterns, and a shared-clock orchestrator. Offline today — the working PC and the microscope PC are separate, and the vendor DLLs these drivers bind to are not published here ([NOTICE](NOTICE.md)). [`hardware/lunf_power.py`](hardware/lunf_power.py) is complete as transport and **refuses to transmit**: the LUN-F-XL DAC word format is undocumented, and a guessed byte goes into a laser driver |
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
