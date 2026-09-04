# Agentic microscope

[![tests](https://github.com/kyu-softmatter/agentic-microscope/actions/workflows/tests.yml/badge.svg)](https://github.com/kyu-softmatter/agentic-microscope/actions/workflows/tests.yml)
[![licence: MIT](https://img.shields.io/badge/licence-MIT-blue.svg)](LICENSE)

An agent that turns a research goal into a microscope configuration that is
checked against what the instrument can physically do — and refuses when the
evidence for a setting does not exist.

It works from measured hardware limits, recorded calibrations, 2,343 prior
acquisitions and explicit scientific constraints. Eight review lenses and 32
deterministic gates decide whether a proposal may advance. The LLM contributes
the qualitative half of a judgment where there is no closed form; it does not
originate a physical value and cannot overrule a failed gate.

> ## ⚠ Read [`SAFETY.md`](SAFETY.md) before moving any hardware
>
> Not a formality. This instrument carries a **class-4 1064 nm trap laser**,
> four confocal laser lines, and objectives whose working distance is short
> enough (0.13 mm on the `100x-Oil`) that a nosepiece write is the worst
> irreversible risk on the bench. The property that generates most of the
> hazards: **on the optical tweezers a return code of `0` means "the GUI
> accepted the command", not "the thing happened"** — the Tweez 300 TCP
> interface has no readback of any kind, so six distinct wrong states and a
> success are the same byte
> ([SAFETY §0](SAFETY.md)). Never treat a `0` from the tweezers as
> confirmation; confirm by eye in the GUI, or by measuring the result in the
> camera data.
>
> **`SAFETY.md` is a first draft and is not yet reviewed by the operator.** It
> is the current best account of the hazards, not a cleared procedure.

**The hardware setup is 28 devices.** Not a subsystem count — the number
Micro-Manager actually loads from
[`config/micromanager/single_cam_red_noDMD.cfg`](config/micromanager/single_cam_red_noDMD.cfg),
the configuration the three-subsystem run uses: the Ti2-E body with its 14
sub-devices (nosepiece, both filter turrets and their shutters, PFS and
PFSOffset, ZDrive, XYStage, light path, condenser, `LappMainBranch1`, dia lamp,
intermediate magnification), one `Kinetix_red` over PVCAM, the seven `CSUW1-*`
spinning-disk devices, two Lumencor light engines (`LightEngine`, `Aura`), the
`NIDAQHub` with `LUNF-Blanking`, and a serial manager. The DMD-in variants load
29–30. The optical tweezers and the piezo stage are **not** among the 28 —
they are driven outside Micro-Manager, over TCP and a vendor DLL respectively,
which is exactly why a shared clock had to be built rather than assumed.

> **Development context.** An independent project, developed primarily during
> evenings and weekends alongside full-time postdoctoral research at Stanford,
> begun in early July 2026. It is built on **one** instrument — the microscope
> in Prof. Sho Takatori's lab, Stanford Chemical Engineering — and every
> calibration, expertise note and device record here is that instrument's,
> labelled as such. Not a supported product.
>
> **Companion projects — three axes of one system.**
> [`Brownian-Dynamics Agent`](https://github.com/kyu-softmatter/Brownian-Dynamics-Agent)
> applies the same provenance and validation rules to simulation. It asks what
> the physical system should do; this asks whether the instrument can measure
> the difference well enough to decide. A third,
> [`research-topic`](https://github.com/kyu-softmatter/research-topic),
> asks which question is worth asking at all, and is meant to hold the knowledge
> base and the definitions of rigor that both of the others enforce. **It is a
> sketch — nothing is built there yet**, and neither working repository depends
> on it. → [below](#toward-a-model-to-experiment-loop)

---

## What works today

Every lens computes and returns a verdict. What that verdict is allowed to
claim is a separate question, and mostly the answer is *not yet* — which is the
design, not a gap.

| | |
|---|---|
| **8 review lenses** | optics · detection · compute resources · sample geometry · photo-perturbation · measurement validity · optical tweezers · mechanical & environmental |
| **32 deterministic gates** | G1–G32, each classified `hard` / `bias` / `soft` by what its failure costs → [05 §2](docs/05-consensus-gate.md) |
| **Provenance on every input** | `measured` vs `assumed`, with a separate `advances` axis that only `measured` can satisfy. Literature values compute but never advance → [`kb/literature/`](kb/literature/) |
| **2,343 prior acquisitions** | normalized out of Micro-Manager metadata into transferable physical quantities, across two schema generations |
| **939 tests, 883 on CI** | offline; the instrument is not required to run any of them. The badge covers 883 — the other 56 need a Micro-Manager device-adapter install → [running the tests](#running-the-tests) |
| **A 28-device instrument** | what Micro-Manager loads from `single_cam_red_noDMD.cfg` — Ti2-E and its 14 sub-devices, one Kinetix, seven CSU-W1 devices, two Lumencor engines, NIDAQ hub + LUN-F blanking, serial manager. Tweezers and piezo sit outside those 28 → [above](#agentic-microscope) |
| **Hardware drivers** | microscope (pymmcore-plus), optical tweezers (TCP), piezo stage (vendor DLL), trap patterns, piezo waveforms, and a shared-clock orchestrator |
| **First light on real hardware** | piezo and optical tweezers each driven from this repository, **separately** — 2026-08-27. **All three subsystems together on one clock — 2026-09-03**, with per-frame timestamps; κ = 3.65–4.5 pN/µm from three independent routes |
| **A written hazard account** | [`SAFETY.md`](SAFETY.md) — laser classes, the objective/coverslip collision procedure, camera ownership order, and the failure modes that return `0`. **First draft, not yet operator-reviewed** |
| **An MCP surface over both bespoke paths** | tweezers and piezo as 9 MCP tools in four tiers, the two moving ones refused by default, verified end to end over stdio but **not yet against a device** → [below](#an-mcp-surface-over-the-two-bespoke-paths) |
| **Refusal paths that hold** | `hardware/lunf_power.py` is complete as transport and refuses to transmit, because the DAC word format is undocumented and a guessed byte goes into a laser driver |

What is **not** true today, stated here so nothing above implies it: **no MCP
tool has reached a device**; no experiment has been executed end to end by the
agent; there is no closed feedback loop; and nothing analyses a frame while the
run is still going. Those are the
[current execution boundary](#current-execution-boundary).

One correction the 2026-09-03 run forced, kept here rather than quietly
dropped: `Breakpoints > Enable Bits` is `0000`, so `TRAP_PATT_RELEASE_BP`
returns `0` while doing nothing. **Every release-round-trip latency figure
measured before that date is precision on a command with no effect.**

> The useful measure is not how much of this exists. It is how many places the
> system refuses to turn a missing number into a confident one.

---

## Why this is different

**The hard problem here is not device access. It is scientific validity.**

A camera will accept an exposure, a laser will stay inside its hardware limit,
and an acquisition will complete — and the measurement can still be biased, or
simply incapable of answering the question that motivated it. Those are two
different questions and this project keeps them apart:

- **Hardware feasibility** — *can the instrument do this?*
- **Measurement validity** — *would the resulting data support the claim?*

Three concrete cases where the two disagree:

- An exposure can be perfectly legal and still put a **motion-blur bias into the
  MSD** — Savin–Doyle's `−2D·t_exp/3` against `+2ε²`, which at short lags cancel
  into a plausible straight line with the wrong slope → [04 §5](docs/04-decision-engine.md).
- Illumination can be well inside every hardware limit and still **drive the
  sample**, which for light-responsive colloids changes the thing being measured
  → [05](docs/05-consensus-gate.md).
- A literature value can let a gate **compute** — and must never let a verdict
  advance, because it is not a measurement of this instrument
  → [`kb/literature/`](kb/literature/).

### What the code owns, and what the model owns

| Responsibility | Deterministic code | LLM |
|---|:---:|:---:|
| Physical calculations | **yes** | no |
| Hardware limits | **yes** | no |
| Evidence and provenance | **yes** | reads |
| Hard gates | **yes** | cannot override |
| Qualitative judgment with no closed form | no | **yes** |
| Originating a missing numerical value | no | **no** |

The deterministic half is deterministic *for a reason*: its job is to fix the
**scale** — off by 2× or by 2000× — which has a closed form that does not vary
between runs. The margin covers what that cannot: the phenomenon being measured
is one nobody here has measured yet, so the true value, and the formula's own
assumptions, are both entitled to depart from the number
→ [01 §1c](docs/01-architecture.md).

The agent packaging is Claude-specific; the contracts underneath it — the
specifications, the gates, the provenance rules, the physical calculations and
the hardware limits — are plain Python and YAML, and are intended to stay
model-independent.

---

## A refusal is a valid result

The shortest description of the whole system:

```text
 research goal
      |
      v
 proposal  ->  photo-perturbation lens
                    |
                    v
          sample-plane power was never measured
                    |
                    v
                 BLOCKED

   missing input     power_at_sample_mw
   what unblocks it  a power meter at the sample plane
   what it is not    a model failure
```

`BLOCKED` is the correct outcome when the physical evidence a proposal needs
does not exist. The transcript below is that refusal on the real instrument.

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

**Why a ratio, and why the physics is code.** The computation under a lens is
deterministic, and not a language model, because its job is to fix the **scale**
— off by 2× or by 2000× — and that question has a closed form that does not vary
between runs. The margin carries what the deterministic part cannot: an
experiment is pointed at a phenomenon nobody here has measured, so the true value
is entitled to depart from the one the formula produced, and the formula's
assumptions are entitled to be what departs. `m = achieved / required` is how
much room there is for that. Printing it beats collapsing it to `PASS`, which
throws away the only number that says whether a small surprise is survivable.
→ [01 §1c](docs/01-architecture.md), [05 §3](docs/05-consensus-gate.md)

---

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
  |  kb/literature/    published values a gate needs and nobody here  |
  |                    has measured. Always assumed, so they let a    |
  |                    gate compute instead of BLOCK but never let a  |
  |                    verdict advance -- each is a placeholder built |
  |                    to be replaced by a calibration.               |
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

---

## Current status

**Design complete; all eight committee lenses are implemented.** Nine design
documents, 32 hard gates (G1–G32), 939 tests passing. The badge above reports
883 of them — the other 56 need a Micro-Manager device-adapter install and run
in a separate workflow, which is stated at the top of each file in
[`.github/workflows/`](.github/workflows/) and again under [running the
tests](#running-the-tests). The six standing
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

**`BLOCKED` is the current default, not the permanent one.** One `UNKNOWN`
among the 32 gates blocks the verdict today, which is the only defensible
setting while there is no record to check a verdict against. As experiments
accumulate, strictness relaxes — but against the record rather than against
confidence, by promoting an input's evidence tier rather than lowering a
threshold, and never on a hard gate or a bias gate. What has to be accumulated
for that is **the outcome of refusals**, not the count of runs that went well.
→ [05 §7](docs/05-consensus-gate.md)

**Where this is going.** The longer-term goal is to join this agent to
[**Brownian-Dynamics Agent**](https://github.com/kyu-softmatter/Brownian-Dynamics-Agent)
— the same architecture pointed at the integrator instead of the instrument. One
decides what the system does, the other decides what the microscope can actually
record, and today they are consulted separately and can silently contradict.
Joined, a simulation would supply the τ_c · ℓ_c · target precision that
[04 §1](docs/04-decision-engine.md) currently takes from a human, and a
measurement would become the independent oracle a simulation has no grader for.
**Neither is finished, and coupling two moving targets would be a mistake** — so
it is future work, with a stated order of preconditions.
→ [Toward a model-to-experiment loop](#toward-a-model-to-experiment-loop)

**One instrument, and what another lab would have to replace.** Every
calibration, expertise note and device record here belongs to this microscope.
Being usable elsewhere is a considered direction, and the mechanism is already
central to the design — device settings do not transfer between microscopes,
physical quantities do. What is portable, and the failure mode that makes it
more than a configuration exercise, is in
[03 §8](docs/03-cross-system-transfer.md).

Read [the pitfalls](docs/06-pitfalls.md) before starting any implementation.

---

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

---

## Current execution boundary

**What is missing is a seam, not a subsystem.** Items 0a, 0b and 0c are not part
of the chain and jump the queue anyway — each is waiting only on being at the
instrument, and 0a's and 0b's hardware has now arrived. Then five: **1–3 are the
missing path from a committee verdict to a running instrument** — **item 1 is
done as of 2026-09-03** — 4 is the first real use of that path, and the only
test of whether any of the rest was right; **5 is the next step**, and is what a
run does with what it is seeing while it is still happening. Items 1–3
sit between stages 5d and 5e, and 5 is 5e itself
→ [07 Phase 5](docs/07-roadmap.md#phase-5--automating-microscope-operation).

> **Every item below that moves hardware — 0a, 0b, 0c, 1, 4, 5 — is gated on
> [`SAFETY.md`](SAFETY.md) first.** Read it before the laser is armed, before a
> nosepiece write, and before the piezo is unlocked. It is a first draft and
> not yet operator-reviewed.
A note on how this would look under Anthropic's Model Hardware Standard is in
[`docs/mhs-integration.md`](docs/mhs-integration.md), deliberately off the main
line.

- [ ] **0a · Measure the illumination power at the sample.** Outside the 1→5
  chain, and ahead of all of it the moment the hardware is in hand: **Saksham is
  borrowing a power meter.** That was the missing precondition — this is the one
  blocker in the whole repository that **code cannot substitute for**, and it was
  deferred on 2026-08-19 partly because no meter was available.

  It is ~30 minutes and the procedure is already written down in
  [`data/light_sources.yaml`](data/light_sources.yaml): sensor at the real
  sample position (not the back focal plane with the objective removed), mW for
  each line × objective × level 10/25/50/75/100%, divided by illuminated area
  for W/cm², plus the level at which linearity breaks. It lands in
  `power_at_sample_mw`, which is empty for **every** line of every registered
  source today.

  What it buys is out of proportion to the half hour. Every dose and SNR number
  stops being relative and becomes absolute, so exposure can be computed from
  scratch instead of copied from precedent; lens 5 stops returning `BLOCKED` on
  this instrument ([the transcript above](#a-refusal-is-a-valid-result) is that
  refusal); and the numbers become transferable to another microscope at all,
  which is what [03](docs/03-cross-system-transfer.md) exists for and what the
  other-labs direction rests on.

  Two limits to hold onto, so the measurement is not oversold. **It does not by
  itself unblock lens 5** — G10 also needs `bleach_photons`, which is empty for
  every dye in the registry, and the photobleaching budget needs both numbers to
  count anything. And it is **immediately meaningful for the widefield sources**
  (SpectraIII, AuraIII) but contingent for the confocal lines: until the LUN-F
  per-line power path exists, measuring those characterises the laser at
  whatever power NIS last left it at, not at a power this repository can command
  → [07 Phase 0](docs/07-roadmap.md).

- [ ] **0b · Reach the confocal laser without going through NIS-Elements.**
  **The USB-B cable has arrived**, which makes the move recorded on 2026-08-20
  as *untried* the next one to try: cable the LUN-F-XL chassis straight to the
  PC on the free port.

  The LUN-F-XL (405 · 488 · 561 · 640 nm, feeding `CSUW1-Hub`) is **the only
  laser on this instrument**, and today it is reachable only through
  NIS-Elements — which the 2026-08-11 decision took out of the control path
  entirely. What already works is **blanking**: on/off over NI PCIe-6323 digital
  lines `Dev1/port0/line2/4/6/8` through MM's stock NIDAQ adapter. What does not
  is **per-line power**: it is reachable over the FTDI FT4222H, Nikon does not
  document the DAC word format, and
  [`hardware/lunf_power.py`](hardware/lunf_power.py) refuses to transmit rather
  than send a guessed byte into a laser driver.

  **The first question is one bit wide: does the chassis enumerate as its own
  USB device at all?** If it does, the problem is solved by *bypassing* the
  contended path rather than by decoding it, and the laser stops being a device
  this repository can only watch. If it does not, the fallback is a USBPcap
  capture on the NIS↔controller link — rung 3 of the discovery ladder, which
  yields a hypothesis and not a fact
  ([scope](kb/decisions/2026-08-29-device-discovery-scope.md)).

  **Discovery stays read-only.** Enumerate, read descriptors, stop. No
  `LASER_ON`, and no guessed byte — writing to a class-4 laser driver is not a
  discovery step. Note also that the current topology may move the problem
  rather than solve it: the laser sits behind the Nikon/Yokogawa confocal
  controller, so if it is only reachable *through* that controller, the thing
  that needs a direct path is the controller.

  **This is what decides whether 0a's confocal half means anything.** Until a
  power path this repository can command exists, measuring the laser lines
  records whatever power NIS last left them at — so 0a's widefield half is
  unconditional and its confocal half waits here. And it is the same *kind* of
  problem as the camera-ownership conflict in item 1: not physics, not protocol,
  but **who is allowed to command a device, through which stack.**

- [ ] **0c · Confirm the MCP surface reaches the hardware.** Built 2026-08-31
  ([`mcp_server/`](mcp_server/), 9 tools, 30 tests) and verified end to end over
  stdio — handshake, tool list, a plan matching what
  [`config/tweezers/run_pattern.py`](config/tweezers/run_pattern.py) prints, a
  refused move. **No tool has reached a device.** The vendor DLL is not on the
  working PC and the Tweez GUI is not listening on it, so the `read` and `move`
  tiers have only been exercised along their refusal and unavailable paths. Until
  that changes, the claim is *the interface is correct*, not *the interface
  works*.

  Three checks, in this order, because the cheap ones are also the ones that
  cannot damage anything:

  1. **`piezo_read_state` against `sim:/NPC6330`**, the DLL's own simulator. Then
     against COM4. If the identity, channels and travel it returns do not match
     what [`config/piezo/verify_piezo_commands.py`](config/piezo/verify_piezo_commands.py)
     prints, the tool is not the thin wrapper it claims to be — which is the
     actual risk here, not a crash.
  2. **`piezo_move` on `sim:` with `AGENTIC_MICROSCOPE_ALLOW_MOTION=1`.** The one
     path with no test coverage, exercised on a device that cannot be hurt. It
     should move the simulated axis and read the position back.
  3. **`tweezers_probe` with the GUI live.** `reachable: true` with a status is
     the whole claim; `tweezers_run` stays refused.

  **The piezo goes first, and the asymmetry is the reason.** Its state is
  readable, so a commanded position can be checked against a measured one, and it
  has a simulator. The tweezers have neither — no trap readback over TCP and no
  simulator — so there the tool's output can be compared only against the GUI by
  eye. That is also why `tweezers_run` is gated on `allow_laser` as well as
  `allow_motion` → [the MCP section](#an-mcp-surface-over-the-two-bespoke-paths).

  **What this does not settle, and should not be read as settling.** It exercises
  one of the tweezers' three control surfaces; `Breakpoints > Enable Bits`,
  `Repeat > Enabled` and laser power stay GUI-only, so a plan the server accepts
  is still not a drive that runs unattended. And it says nothing about whether an
  agent *should* be driving the instrument — the committee decides that, above any
  transport → [`kb/decisions/2026-08-31-mcp-hardware-server-scope.md`](kb/decisions/2026-08-31-mcp-hardware-server-scope.md).

  One thing to fix while at it, and it is not cosmetic:
  [`hardware/optical_tweezers.py`](hardware/optical_tweezers.py) has **no safety
  switch of its own**, unlike the other two drivers — its constructor opens the
  socket and all 28 commands including `laser_on()` are directly callable. Today
  `mcp_server/switches.py` is the only brake in that path. The switch belongs in
  the driver, where the other two put theirs and where MHS puts device safety
  limits; it changes six call sites, which is why it was not done as a side
  effect of adding the server.

- [x] **1 · Run the three subsystems on one timeline.** ✅ **Done 2026-09-03.**
  A master script over three sub-scripts — optical tweezers · microscope
  (Micro-Manager) · piezo stage — with the shared variables **confirmed**
  rather than assumed.
  [`config/session/run_trap_stage_sine.py`](config/session/run_trap_stage_sine.py)
  put both zeros on the camera's clock and recorded per-frame timestamps
  through [`calibration/timestamped_capture.py`](calibration/timestamped_capture.py).

  **What is still open inside this item**, so the checkbox is not read as more
  than it is: the tweezers still have no timestamp of their own — all three
  routes below remain unbuilt, and the breakpoint route is now known to be
  worse than it looked, because `TRAP_PATT_RELEASE_BP` returns `0`
  unconditionally. The camera-ownership conflict is unresolved.

  **The first action is smaller than that**: re-run the two scripts that have
  already driven each subsystem alone. [`try_hardware.py`](try_hardware.py)
  (`tweezers` · `tweezers --send` · `piezo` · `piezo --move --unlock`) and
  [`gated_oscillations.py`](gated_oscillations.py), the three 2 s
  breakpoint-gated holds at +10 µm. They are the **first-light** path and
  deliberately not the production one —
  [`config/tweezers/run_pattern.py`](config/tweezers/run_pattern.py) refuses on
  precisely the blockers that first light exists to resolve, and you cannot
  record the trapezoid off the GUI until something has drawn a pattern in it.
  Three things decide whether that re-run means anything, none of them readable
  from Python: `Breakpoints > Enable Bits` must cover `0001` — it defaults to
  `0000`, which reduces every breakpoint to nothing while every return code
  still says 0 — `Repeat > Enabled` must be true, and the piezo's `--move`
  refuses without `--unlock`, whose access code is not in this repo. The repo
  path is hardcoded at the top of `gated_oscillations.py`.

  Partly standing already: [`hardware/orchestrator.py`](hardware/orchestrator.py) holds
  the one monotonic clock, the camera arbiter, the latency log and the shared
  store, and the four rosters are settled — the microscope is always on the
  roster, because its per-frame `ElapsedTime-ms` is the series every other
  subsystem is aligned onto
  ([`2026-08-27`](kb/decisions/2026-08-27-optional-subsystems-one-timeline.md)).
  Each subsystem has had first light **alone**: the piezo drove 60 cycles at
  1 Hz with 0/6000 overruns and reads back every sample; the tweezers ran a 1 Hz
  ±10 µm drive with a 2 s breakpoint hold. What is missing is **the three of
  them at once**, and one conflict is already measured and unresolved: while the
  Tweez GUI owns the camera there is trap-position readback and no imaging from
  pymmcore-plus, and while Micro-Manager owns it, the reverse. Active
  microrheology needs bead *and* trap position simultaneously, and **only one
  owner can see both**
  ([`2026-08-27` §8](kb/decisions/2026-08-27-tweezers-first-light-measured-limits.md)).

  **So the piece to build or find is a timestamp that comes from the tweezers
  itself, rather than from analysing the camera's images.** Three routes, none
  of them free:

  - **The probe's own `.Data` series** — `TimOrg, PrbOrgX, PrbOrgY, TrpOrgX,
    TrpOrgY`. A flat `TrpOrgX` would give arrival time, hold duration and
    achieved frequency at once, which is better than any boolean status. But it
    **does not escape the conflict**: samples accumulate only while the Tweez
    GUI is tracking, and reaching the node at all means reaching the
    undocumented embedded node tree, which nothing has read yet — 0 of 51 paths
    at GUI startup, because the tree is not up when the init script runs (§7).
  - **The hardware trigger**, which TCP has and the node API does not. Start the
    trap loop and the camera from one edge and the trap position at any frame is
    *computed* from a hardware-clocked pattern — 50 kHz at the lab's current
    operating point, `points × n_traps / period` — instead of read back.
    Open-loop, though: `TRAP_PATT_RELEASE_BP` answers 0 whether the trap was
    waiting at the breakpoint or the pattern had already finished, so nothing on
    this route confirms that a given pass actually happened.
  - **An out-of-band sensor** on the trap beam, landing on the same NIDAQ clock
    as the camera. Nothing like it exists here today, and it is the only one of
    the three that yields an **independent** time base rather than a computed
    one or one borrowed from the camera.

  None of them can be replaced by timing the drive from the host:
  [`hardware/orchestrator.py`](hardware/orchestrator.py) says it in its own
  docstring — **the host clock is not the experiment clock**, and mapping host
  stamps onto MM's series afterwards is a correlation, not a synchronisation.

- [ ] **2 · An LLM node that turns gate verdicts into that master script.**
  Today the committee ends at a proposal a human reads, and `hardware/` begins
  at a script a human writes; nothing joins them. This node takes the verdict,
  its margins and the settings that produced them, and emits the master +
  sub-script pair from item 1. Two properties it has to have, or it is worse
  than the gap it fills: **every emitted line traces to the check that justified
  it**, and **anything the verdict does not fix is `BLOCKED`, never defaulted** —
  a node that silently picks a plausible exposure has undone every refusal
  upstream of it.

- [ ] **3 · A sub-agent that reviews item 2's output against each instrument's
  measured limits.** Per-instrument, and grounded in what has actually been
  measured rather than what the manuals claim: the piezo's travel, settle and
  waveform behaviour; the tweezers' 28-command TCP surface, its GUI-only
  properties and its absent trap readback; camera timing and ROI; and the write
  switches that already default off (`allow_write`, `allow_motion`,
  `allow_laser`, and the `.cfg` refusal on `NIDAQAO-Dev1/ao2`). It must be able
  to **refuse a script before it runs** — a reviewer that has never blocked
  anything is not a reviewer, and here the thing being reviewed drives glass
  into glass and a laser into a sample.

- [ ] **4 · Four first measurements, with the priors deliberately withheld.**
  The point of the exercise is not the four numbers; it is what the agent does
  without precedent. **It gets no archive** — not the 2,343 past acquisitions,
  and this round not the recorded instrument description either. The only prior
  it is allowed is **the published literature**. Whatever it cannot look up it
  has to derive or measure, and a `BLOCKED` that names the missing input is a
  correct answer, not a failure.

  1. **Drag calibration in water** (tweezers + piezo). Stokes drag at a known
     stage velocity → κ. Needs laser power, the traverse speed and simple
     particle tracking. The hard part is **knowing where the trap is, on the
     camera's clock** — the three routes under item 1 are its precondition. And
     one practical thing decides whether the number is real: **both ends of the
     traverse have to be cut**, keeping only the constant-velocity segment.
     Acceleration at the turnarounds is bias, not signal.
  2. **Microrheology, passive and active** (tweezers + piezo). Needs the piezo
     position and the exact start and end times — and, the real problem, those
     times expressed on **the camera's clock**, not the host's. Amplitude and
     frequency have to be *recommended* rather than chosen, because the result
     is only a modulus while the drive stays in the **linear regime**. Partly
     specified already in
     [`config/channels/active-microrheology-probe-tracer.yaml`](config/channels/active-microrheology-probe-tracer.yaml)
     and [`config/tweezers/active-microrheology-drive.yaml`](config/tweezers/active-microrheology-drive.yaml);
     the motion-blur bias that decides it is [04 §5](docs/04-decision-engine.md).
  3. **FRAP** (DMD). Bleach circle size, the conversion matrix behind it, camera
     rate, total duration, objective choice, the dye's band, and a **two-level
     light schedule in time** — DMD-intense to bleach, Aura-mild to watch the
     recovery. Then the check that matters across all four: does the time index
     it estimates agree with the timestamps everyone else is sharing? Two named
     blockers stand in front of this one: the DMD's vendor package is pinned to
     MM interface v71 against the v75 core, making it **the one device that does
     not load through pymmcore-plus**, and lens 5 refuses without
     `power_at_sample_mw` and `bleach_photons` — which for FRAP is not a side
     check but the measurement itself.
  4. **Simple hydrodynamics** (dual-cam, still being specified). One large
     particle and small tracers, split across the two cameras. The test is
     whether the agent designs the **wavelength bands** itself (G1–G4:
     coupling · collection · blocking · crosstalk) and then finds the
     **characteristic time scale** from what it recorded — which is the same
     τ_c the [model-to-experiment section](#toward-a-model-to-experiment-loop)
     argues a simulation should supply. Here it has to come out of the data
     instead, which makes it the cleanest check of the two against each other.

- [ ] **5 · Real-time image analysis — ⭐ THE NEXT STEP (from 2026-09-03).**
  With item 1 done, this is what the queue advances to. Analyse during the
  acquisition rather than after it, and let what comes out change the run:
  trim, extend, adjust, or abort. This is stage 5e, the one stage of Phase 5
  not started.

  **Two halves, and the second is what makes the first trustworthy.**

  - **Particle trapping, live.** Detect on each frame whether a bead is held —
    and, one rung up, re-acquire one that has been lost. This is the smallest
    closed loop available and the first place feedback moves hardware instead
    of merely stopping it.
  - **Post-processing that confirms the physical experiment is actually
    working.** Run the analysis against the frames as they land and check the
    result is physics and not an artefact: does the MSD have the slope the
    drive implies, does κ from the live data agree with the 3.65–4.5 pN/µm
    already measured by three independent routes, is the bead responding to the
    trap at the commanded frequency at all. **This is the only thing that can
    catch a tweezers command that returned `0` and did nothing** — the
    `TRAP_PATT_RELEASE_BP` failure was found this way and no other way. On an
    instrument with no readback, measuring the result *is* the readback.

  **How much analysis is affordable is a verdict, not a preference.** Lens 3
  already states the condition — with real-time processing attached, CPU time
  per frame must stay under `1/f_total` (G13c), on top of the data rate holding
  under 0.7× disk bandwidth (G12a) and the buffer covering 5 seconds (G13a). So
  the live layer is built as a ladder and the gate decides how far up it can
  run: per-frame drop and saturation checks at the bottom — the same
  [`compute/drops.py`](compute/drops.py) logic that today only runs post hoc on
  the archive — then focus and drift, then single-particle tracking, then
  anything that fits a model. Each rung costs CPU per frame, and each rung's
  cost is a number G13c can be asked about **before** the run rather than
  discovered as dropped frames during it.

  **The first closed loop is the smallest one**, and it is where this starts:
  *the particle has fallen out of the trap* — and then, one rung up, *pick up a
  new one*. Detecting the loss costs almost nothing per frame, so lens 3 clears
  it on any machine, and it catches the failure that quietly ruins the most
  runs: a drag calibration or a microrheology sweep goes on producing
  data after the bead is gone, and that data still looks like data. It also
  exercises everything else exactly once. Saying "the bead left the trap"
  requires knowing where the trap was on that frame, which is item 1's timestamp
  problem. **Re-trapping is the first time feedback moves hardware rather than
  merely stopping it** — an `allow_motion`-class write issued mid-run, which is
  the first real test of item 3's reviewer and of the per-frame record the rules
  below demand.

  What each of the four examples would get: 4.1 notices the bead leaving the
  trap and marks the constant-velocity segment live instead of in post; 4.2
  checks the drive is still in the linear regime and adjusts amplitude before
  spending an hour outside it; 4.3 watches the recovery curve and stops when it
  has plateaued; 4.4 estimates τ_c early and sets the frame rate from it.

  **Two rules to write before the first loop closes, not after.** A run whose
  settings change mid-acquisition is a run whose provenance changes with them,
  so **every adjustment has to land in the record per-frame** or lens 6's bias
  ledger (G23) is judging a session that no longer exists. And **the stop
  criterion has to be fixed in advance**: a loop that halts when the curve looks
  right will produce curves that look right, which is the same self-confirming
  failure the [model-to-experiment section](#toward-a-model-to-experiment-loop)
  guards against on the simulation side. Seal the rule, then let the loop run
  against it.

---

## An MCP surface over the two bespoke paths

[`mcp_server/`](mcp_server/) exposes the tweezers and the piezo as MCP tools —
the two subsystems with no abstraction at all, a 28-command TCP surface and a
vendor DLL. Nine tools in four tiers, each declared in the tool's own MCP
annotations: **plan** (no device), **write** (a file), **read** (the device,
reads only), **move** (the laser, the stage). Nothing in the plan tier
recomputes anything — each tool calls the same entry point
[`config/tweezers/run_pattern.py`](config/tweezers/run_pattern.py) and
[`config/piezo/verify_piezo_commands.py`](config/piezo/verify_piezo_commands.py)
call, so a tool and a script that disagree is a bug, and the tests compare them
field by field.

The two moving tools are refused by default and the refusal is a value, not an
exception: `refused: true` naming the switch and how to set it, plus the exact
TCP lines or the exact target it would have commanded. An MCP tool that raises
reads to the calling model as a broken tool, and a model that believes a tool is
broken routes around it — which is the failure this whole repository is built
against. `advances: false` behaves the same way, and the tool descriptions say
in as many words that it is a valid result.

Two things it does not do. It does not expose the eight committee lenses, which
is the other half of the job and needs each lens's CLI to hand its parser over
as the tool schema. And it reaches one of the tweezers' three control surfaces:
`Breakpoints > Enable Bits`, `Repeat > Enabled` and laser power are GUI-only, so
a plan the server accepts is still not a drive that runs unattended.
→ [`kb/decisions/2026-08-31-mcp-hardware-server-scope.md`](kb/decisions/2026-08-31-mcp-hardware-server-scope.md)

---

## How this is meant to be maintained

**Prototype first, and it is not close.** Everything below is a convenience
layer over a system that cannot yet run an experiment end to end, and building
convenience on top of an unfinished foundation is how the convenience ends up
shaped wrong. Items 0–5 above come first. The plan is written down now so the
*shape* is fixed while it is still free to change.

### Then: one folder per instrument

The person looking after this microscope should find everything about one device
in one place, instead of reconstructing it from six. The intended shape:

```text
hardware/
  piezo/
    README.md       what this device is, how it is reached, what it refuses
                    and why — written by the agent and kept current by it
    MANIFEST.yaml   what belongs in vendor/: which file, which version, where
                    to obtain it, checksum, and the version the code was
                    tested against
    vendor/         .gitignore'd — manual, DLL, SDK samples. Never committed
    first-light.py  the smallest run that proves the device is alive.
                    Read-only by default
    limits.yaml     limits that were *measured*, not the catalogue's
```

Two rules decide whether this helps or just adds a second copy of everything.

**It indexes; it does not duplicate.** The source of truth stays where it is —
wiring in [`kb/systems/current.md`](kb/systems/current.md), measured numbers in
[`kb/calibrations/`](kb/calibrations/), registries in `data/*.yaml`, scope calls
in [`kb/decisions/`](kb/decisions/). The folder holds only what is genuinely
per-device and links the rest. The companion repository's two unmerged knowledge
schemas are the cautionary case: once there are two stores, a lesson filed in
one is invisible to a reader of the other, and nobody remembers to query both.

**The vendor material cannot be committed.** Manuals, DLLs and commercial
correspondence were removed from the entire history on 2026-08-28
([NOTICE](NOTICE.md)), so `vendor/` is the ignored slot and `MANIFEST.yaml` is
the committed half — enough to restore the folder without shipping anything that
is not ours. [`hardware/piezo/vendor/`](hardware/piezo/) already works this way:
`dll_adapter.py` is committed because it carries local modifications, the DLLs
are not. **One piece of that is missing today** — `.gitignore` has no rule for
`vendor/`. The scrub cleaned the history and left nothing standing in the way of
a re-commit. That rule belongs in place *before* the pattern is generalised to
eight devices, not after.

### `FIRST RUN`: what is here, and what is new

Its job is a **comparison**, not a scan. Enumerate what the machine can see — MM
`.cfg`, pymmcore-plus, USB, serial ports, whether each vendor DLL is present —
and diff that against the recorded dossier:

| Set | What it means |
|---|---|
| **expected and found** | the boring majority. Record firmware and serial wherever they are readable, since those are rung-1 facts and mostly still missing |
| **expected and missing** | something was unplugged, moved, or stopped loading. The most useful alarm in the whole tool, and the one nothing reports today |
| **found and unknown** | the interesting case, and the one below |

For an unknown device the agent's job is to get it onto **rung 1** of the
[discovery ladder](kb/decisions/2026-08-29-device-discovery-scope.md) and to
produce a **stub**, not an answer:

- **Read what the device says about itself first** — USB descriptors and
  `VID:PID`, the MM adapter name, a `--describe` or identity query. That is the
  only rung that settles anything about *this unit*.
- **Then look for manual and driver *candidates*, each carrying the evidence
  that matched it** — the `VID:PID`, the model string, the firmware version.
  Never a bare link. Retrieval is exactly where a model is confidently wrong,
  and a manual for the neighbouring firmware revision is worse than no manual,
  because it reads as authoritative.
- **Write the stub, and stop.** A new `hardware/<device>/` with the description
  and the open questions. **Nothing is written into `kb/systems/` until a human
  confirms it** — that file is the wiring dossier every lens reads, and a guess
  landing in it propagates into 32 gates.
- **Read-only.** Enumerate and read descriptors; issue no commands. Same rule as
  item 0b, and for the same reason.

Worth noticing: this is also the **onboarding path for a different lab**. An
instrument that shares no history with this one is precisely the case *expected:
nothing · found: everything*, which is what
[03 §8](docs/03-cross-system-transfer.md) describes from the other direction.

### What else would make it easier to keep

Five, in the order they would pay off.

1. **One command that says what state the instrument is in.** That answer is
   currently spread over [`calibration/`](calibration/), `compute.cli scan`, the
   MM config check and three decision notes. A single `doctor` should print what
   loads, what is missing, which gates are `BLOCKED`, and the one input that
   would unblock each. **Every lens already produces that last part** — nothing
   collects it.
2. **An expiry on every measured number.** `kb/calibrations/` records when a
   value was measured and never when it stops being trustworthy. The pixel-size
   calibration is from 2025-04 and is treated exactly like the disk bandwidth
   measured on 2026-08-12. A re-measure interval is a falsifier on a timer, and
   the doctor should say what has aged out.
3. **A fingerprint stamped on every acquisition.**
   [03 §7](docs/03-cross-system-transfer.md) already computes one when a new
   `.cfg` appears. If each acquisition records *which* fingerprint it ran under,
   data taken before and after a hardware change can be re-scoped instead of
   silently mixed.
4. **A checklist of what software cannot see.** The Splitter has no `Device,`
   line in any config, the polarizer and analyzer are manual, the coverslip is a
   micrometer reading, and three GUI-only tweezers properties gate an entire
   drive. These are the settings that invalidate a run without leaving a trace.
   A per-configuration manual-steps list, confirmed at run time, is the only
   place they can honestly live.
5. **A diff of what changed since the last run.** Nearly free once 1 and 3
   exist: store what the doctor printed, per run. *"It worked last week"* then
   becomes a diff rather than a memory.

---

## Toward a model-to-experiment loop

The other half of this project is
[**Brownian-Dynamics Agent**](https://github.com/kyu-softmatter/Brownian-Dynamics-Agent):
the same architecture pointed at the integrator instead of the instrument. It
reads a physical system out of a sketch, fixes it in SI with a provenance on
every number, derives a dimensionless specification, runs it in HOOMD-blue, and
files what it learned — including the failures — into a knowledge base the next
run queries first.

| | **agentic-microscope** (this repo) | **Brownian-Dynamics Agent** |
|---|---|---|
| Input | a research goal | a sketch of a physical system |
| Decides | what the instrument can actually record | what the system does, in silico |
| Refuses when | a gate's input was never measured | a number has no provenance |
| Produces | executable settings, an evidence tier, per-check margins | a dimensionless spec and a defended result |
| Its knowledge base | instrument config, calibrations, tacit expertise, decisions | system cards, findings, benchmarks, post-mortems |
| Its unit of doubt | `measured` vs `assumed`, and a falsifier on every prior | `tier` and `derived_from` on every number, and a sealed prediction |

The two architectures match because the second was built from the first's
lessons: hard gates that return `BLOCKED` naming the one missing input, a
deterministic core under a thin agent layer, and a knowledge base read before
every decision and written after every verdict. **Neither is finished, and
coupling two moving targets would be a mistake** — so this is future work, with
a stated order of preconditions.
→ [07 Phase 6](docs/07-roadmap.md#phase-6--joining-the-simulation-agent)

### A third axis, and the question neither repo asks

Both repositories take the scientific question from a human, and both hand their
evidence back to one.
[`research-topic`](https://github.com/kyu-softmatter/research-topic) (sketch
stage) is meant to sit in both of those places: it proposes the question, and it
keeps what came back — **including the failures, which is the part that gets
skipped.**

| Axis | Repository | Asks | Status |
|---|---|---|---|
| **Topic** | [`research-topic`](https://github.com/kyu-softmatter/research-topic) | which question is worth asking, and what the other two should read | sketch only. **Nothing built** |
| **Experiment** | **this repository** | what the instrument can actually record | running |
| **Simulation** | [`Brownian-Dynamics Agent`](https://github.com/kyu-softmatter/Brownian-Dynamics-Agent) | what the physical system should do | running |

Two things it is specifically meant to own, because neither of the working
repositories can:

**1 · A knowledge base both can read.** This repository has one, and it is
**bound to the instrument** — `kb/systems/current.md` is which machine this
microscope actually is, and a simulation cannot use that. The third repository is
where the domain-neutral half goes.

**2 · The definitions of rigor, in one place.** This repository enforces 32
gates; the simulation side enforces ten rigor axes. They were built independently
and converged on the same shape — division by axis rather than by person, a
deterministic gate, default-to-`BLOCKED`, a falsifier attached to every judgment,
and an LLM that originates no number. **That convergence is the argument for a
third place:** what two projects reached without consulting each other is not
domain-specific, and keeping one copy of it beats keeping two that drift.

The intended shape is a loop rather than a pipeline, and **that is why the risk is
worth stating out loud**: three components that feed each other will amplify
whatever bias they share. The third repository carries that objection as a
registered conflict, and its answer is that a topic may only enter the loop in a
form the other two can falsify.

**No dependency runs the other way.** Nothing here imports, reads or waits on the
third repository, and if it is never built, nothing here breaks.

### Why joining them is worth doing

**1 · The number this repo takes from a human is one the simulation computes.**
The decision order opens with *"physical quantity to measure + target precision
← the human gives this"*, and its step ①' wants the system's τ_c and ℓ_c,
*measured if measurable, otherwise a theoretical estimate +
`evidence: assumed`* → [04 §1](docs/04-decision-engine.md). Those are exactly
what a simulation produces, and they propagate through the committee: G8 needs
`D` or τ_c for the motion-blur ceiling, G5 needs ℓ_c and the task kind, G11
needs a target error, G14 needs κ. Fed from a spec instead of from a person,
four gates stop asking and start deriving — each number still carrying its own
provenance.

**2 · A measurement closes assumptions a simulation cannot close by itself.**
Its most damaging soft spot is `T = 300 K`, labelled tier 1 but actually
inherited from a sketch that never stated a temperature — worth −4 % to −14 % on
every timescale it computes, because water's viscosity is 2.06 %/K sensitive. A
thermometer reading ends that. The same holds for particle size distribution,
salt concentration and surface potential: tier-1 *choices* over there, routine
measurements over here. This repository is already built to accept an outside
number without either side losing track of what it is —
[`kb/literature/`](kb/literature/) exists precisely so a value nobody here
measured can let a gate **compute** while never setting `evidence: measured`.

**3 · Verifying a hypothesis needs both halves, and neither half can do it
alone.** Its central result is that a colloidal chain held together by DLVO
forces alone has no bending stiffness: bow of **0.1135 d** without adhesion
against **0.00639 d** with JKR, 22.3σ apart, at a bead diameter of
d = 1.47 µm. Read as an experiment, that is 167 nm against 9.4 nm of transverse
displacement. The *difference* is 157 nm and comfortably resolvable; deciding
whether the JKR branch is separable from zero sits at ~9 nm, at the 10 nm target
precision this repo's own worked examples use — so it is settled by photon count
and frame count ([04 §4](docs/04-decision-engine.md), G11), not by the physics.
**That is the question neither repository can answer alone**, and today it is
answered by consulting them separately and trusting that the two `d` mean the
same thing in the same units.

**4 · Proposing the next hypothesis, not only checking the current one.** The
same result, read the other way: bow separates DLVO from JKR at 22.3σ under a
soft trap and at only 1.4× under a stiff one. **Discriminating power is a
property of the protocol, not of the effect** — so a simulation sweep scored
against this repo's feasibility gates ranks candidate experiments by predicted
separation *per unit of instrument time*, and the ones worth running are those
whose predicted effect clears the achievable precision by a stated margin. That
pairing — predicted separation against achievable precision — is a number both
sides can compute and neither can compute alone. It is also what turns a
`BLOCKED` into a proposal rather than a dead end: *the effect is below your
localization precision; either deepen the DLVO well or change objective.*

**5 · The bias ledger tells the simulation which mismatches are the
instrument's.** The simulation side lists four layers of evidence and
deliberately left the fifth — comparison against experiment — unadopted, because
a mismatch there has too many candidate causes. Lens 6 removes most of them: G23
carries every bias that damages the specific quantity being measured, G24–G26
check that the calibrations behind it exist, and the terms are already written
down here — a measured MSD carries `−2D·t_exp/3` from blur and `+2ε²` from
static localization error, which at short lags **cancel into a plausible but
wrong straight line** → [04 §5](docs/04-decision-engine.md). Those belong on the
simulation's side of the comparison, added to the prediction rather than
subtracted from the data. An independent measured oracle is the most valuable
evidence there is in a domain with no grader — but only when it arrives with its
own bias ledger attached.

### What has to be true first

| Precondition | Where it stands |
|---|---|
| This instrument is **connected** | not yet — the working PC and the microscope PC are separate. Stages 5a–5d are built (2026-08-26) but exercised against a demo config only; 5e not started |
| Illumination power at the sample is **measured** | not yet — the top blocker, deferred by decision (2026-08-19). A power meter, not code |
| τ_c · ℓ_c have **somewhere to live** | `kb/samples/` does not exist yet; it arrives with [Phase 4](docs/07-roadmap.md) |
| Computed values have a **provenance kind of their own** | they do not. There are two tiers here, `measured` and `assumed`, and a simulated τ_c is neither a measurement of this sample nor a literature value. Giving it its own tier — with the simulation's own gate verdict as its falsifier — is the honest fix |
| The simulation side **seals its predictions before running** | not yet; it is that repo's own item 1. An unsealed prediction handed to an instrument produces an experiment designed around a post-hoc rationalization |
| A shared **quantity vocabulary** exists | it does not. Both sides already speak SI with a provenance and a tier, which is the hard half; a common serialization for *"particle diameter, measured, tier 1, ±3 %"* is the missing half |

**The order matters.** Sealing first, on their side. Then the vocabulary, because
that is the actual interface and nothing useful crosses until a number can cross
with its provenance intact. The wiring itself is small once those two exist.

**And one hazard to hold onto from the start:** a simulated number must never be
allowed to set `evidence: measured`. If it can, the loop closes on itself — the
simulation supplies the threshold, the gate clears against it, and the
experiment confirms the simulation that designed it. The rule that keeps
[`kb/literature/`](kb/literature/) honest is the same rule this interface needs.

---

### The loop, and how much of it exists

```text
                    SCIENTIFIC QUESTION
                             |
                  +----------+----------+
                  |                     |
                  v                     v
        Brownian-Dynamics Agent   Agentic Microscope
          what should happen?     what can be measured?
                  |                     |
                  +----------+----------+
                             |
                             v
                    discriminating test
                             |
                             v
                         evidence
                             |
                             +----> next model / next experiment
```

**Long-term direction, and none of it is automated.** The two halves are
consulted separately today and can silently contradict each other. What would
make the loop worth closing is the one sentence above the diagram's left branch:
a simulation should not merely predict a value, it should state **the precision
an experiment must reach to tell two models apart** — and only the right branch
knows whether this instrument can reach it.

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
| [07 Roadmap](docs/07-roadmap.md) | Phase 0 (secure the evidence) → 5 (automate manipulation) → 6 (join the simulation agent). Three things that pay off immediately |
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
| [`photo/`](photo/) | 5 · photo-perturbation (G10, G20–G22) | Implemented. **BLOCKED on the real instrument** until `power_at_sample_mw` is measured and dyes get `bleach_photons` — that refusal is the intended behaviour, and [the transcript above](#a-refusal-is-a-valid-result) is it |
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

---

## Sources used

| Source | Location | Status |
|---|---|---|
| Micro-Manager acquisition metadata, 2,343 records | `D:\data\**\*_metadata.txt` | Obtained (30 GB) |
| ND2 / LIF (separate Nikon and Leica systems) | `D:\data\**\*.nd2`, `*.lif` | Obtained, parser not implemented |
| Experiment protocols | `D:\experiment method` | Obtained, not yet integrated |
| Analysis code | `D:\codes` | Obtained, not yet integrated |
| **Current system MM `.cfg`** | `kb/systems/current.md` | Obtained (`DMD_dualcam.cfg`, 2026-07-03) — most serials not yet obtained |
| Pixel size calibration | [`data/pixel_size.yaml`](data/pixel_size.yaml), mirroring `kb/systems/current.md`; the `.cfg`'s `PixelSize` block carries its 1x column | Obtained (Kinetix, 4x–100x × 1x/1.5x, 2025-04), and **readable by code, and by Micro-Manager itself, since 2026-09-04**. ⚠ **Only the 20x row is a measurement** — the other eleven cells are exactly `p_sensor / (M_obj · M_int)` to every digit they carry, so they return what the formula already returned. The 20x is 0.39 % low at both intermediate settings, i.e. a real 20.078x. ⚠ The `.cfg` presets key on the **Nosepiece alone**, so they are right at intermediate 1x and high by 1.5× at 1.5x — that turret's positions are named nowhere in the `.cfg`. `python -m calibration.cli intermediate-mag <cfg>` reads them. A stage micrometer is still owed |
| Camera row time, disk bandwidth | `kb/calibrations/` | Obtained (2026-08-12) |
| **Illumination power at sample** | `data/light_sources.yaml` | **Not obtained — top blocker** |
| **Hardware spec documents** | Location unspecified | **Not obtained** |

The working PC and the microscope PC are separate, so a live connection is out of
scope. For now this produces offline recommendations only.
→ [07](docs/07-roadmap.md)

---

---

## Running the tests

```console
$ pip install -r requirements.txt -r requirements-mcp.txt
$ pytest -q -rs
883 passed, 3 skipped
```

`pyproject.toml` puts the repository root on `sys.path`, so the bare `pytest`
and `python -m pytest` agree — before it, only the second form worked. The three
skips are modules, not tests: they open with
`pytest.importorskip("pymmcore_plus")` and hold 56 tests that need live
Micro-Manager access. `-rs` names them and their reason in every run, so the
count above cannot quietly shrink. To run those too:

```console
$ pip install -r requirements-micromanager.txt && mmcore install
```

Three requirement files, and the split is the point: `requirements.txt` is the
853 tests that need nothing but numpy and pyyaml, `requirements-mcp.txt` adds
the 30 that exercise the MCP server and is in CI because it is pure Python, and
`requirements-micromanager.txt` is the 56 that need a vendor device-adapter
download and is not.

---

## Public-repository constraints

> Vendor manuals, proprietary DLLs, and commercial correspondence are in no
> commit here — removed from the whole history on 2026-08-28, not just from the
> tip. See [NOTICE](NOTICE.md) for what was removed, what that did and did not
> accomplish, and how to restore the hardware dependencies.

The code is [MIT](LICENSE). Three things here are **not** the repository's to
licence — the vendor piezo adapter, the third-party spectral curves, and the
datasheet figures transcribed into `data/*.yaml` — and
[NOTICE §4](NOTICE.md#4--here-but-not-covered-by-the-licence) names each with
its source. A licence is a claim of ownership, so what it cannot cover is stated
as precisely as what was removed.

---

## References

**What inspired the shape of this one**

- **[`jmsung/einstein`](https://github.com/jmsung/einstein)** — JSAgent, an
  agent for hard mathematical optimization. **Its knowledge base is the part
  this one was built after**: a structured wiki that every later attempt
  queries first, so what one attempt learns compounds instead of evaporating
  when the run ends. [`kb/`](kb/) is that, pointed at an instrument.

**Found while building this — to read**

Neither has been distilled into [`kb/literature/`](kb/literature/) yet, so
nothing from either is a value any gate here may consume.

- **[SmartTrap: automated precision experiments with optical
  tweezers](https://www.nature.com/articles/s41592-026-03129-3)** — Selin *et
  al.*, *Nature Methods*, 2026-06-18
  ([10.1038/s41592-026-03129-3](https://doi.org/10.1038/s41592-026-03129-3)).
  Autonomous optical-tweezers experiments: real-time three-dimensional particle
  tracking, custom electronics, a microfluidics system, and long unattended
  runs, published as an open-source framework. The closest published work to
  items 1 and 4.1–4.2 above, and worth reading **before** committing to one of
  the three trap-timestamp routes — real-time tracking is precisely the
  capability the camera-ownership conflict denies on this instrument, so how
  they arranged the tracking and the trap on one clock is the part to look for.
- **[Thinking microscopes: agentic AI and the future of electron
  microscopy](https://www.nature.com/articles/s41524-026-02077-y)** — Jamali,
  Aghazadeh & Kacher, *npj Computational Materials*, 2026-04-10
  ([10.1038/s41524-026-02077-y](https://doi.org/10.1038/s41524-026-02077-y)).
  The same premise as this repository, in electron microscopy rather than
  optical.
