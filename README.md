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
> The sharpest instance measured so far, 2026-09-04: `SIMPLE_TRAP_CREATE`,
> `TRAP_POSITION` and `TRAP_ON` **all returned `0` with the laser unarmed**,
> while the GUI showed the trap's `Active` = false and nothing was trapped. Six
> commands that would report or set that state all answer `-11, unknown
> command`. So "the trap is on" is not a fact any code here can establish.
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

**28 is the count that flatters the bench. The number that predicts the work is
eight — the ways a thing here can be reached.** Those 28 arrive through **six**
Micro-Manager adapters (`NikonTi2` 15 · `CSUW1` 7 · `NIDAQ` 2 · `Lumencor` 2 ·
`PVCAM` 1 · `SerialManager` 1) from **eight manufacturers** (Nikon, Yokogawa,
Lumencor, Photometrics, National Instruments, Aresis, Prior/Queensgate,
Mightex; FTDI as well if a transport chip counts). But the adapter count is the
easy half. Sorted by how far a piece of code can actually get:

| How it is reached | What is there | What that costs |
|---|---|---|
| **Loads and reads back** through one MM adapter | the 28 | nothing — this is the case everything else is measured against |
| **Loads; state not interpretable** | `CondenserTurret`. Positions 0/1 are labelled `ND`/`Shutter`; **2–6 are bare** (`"3-"`…`"7-"`). Both bright-field and dark-field condensers exist on it (operator, 2026-08-19) | MM will report a position and cannot say which of the two optics is in the path. Dark-field vs bright-field is not a readable fact |
| **Outside MM, readable** | piezo stage (Prior/Queensgate NPC-D) — vendor DLL + COM4, commands in picometres, reads back every sample | a second driver and a second clock, but a commanded position can be checked against a measured one |
| **Outside MM, no readback at all** | optical tweezers (Aresis Tweez 300) — TCP to its GUI, 28 commands | `0` means "the GUI accepted", not "it happened". Six distinct wrong states and a success are the same byte ([SAFETY §0](SAFETY.md)) |
| **Outside MM, protocol undocumented** | LUN-F-XL confocal laser (Nikon) — FTDI FT4222 SPI. Writable, but the DAC word format is one of nine candidate framings | levels write and are not *commandable*: you cannot ask for 50 %. [`hardware/lunf_power.py`](hardware/lunf_power.py) refuses to transmit |
| **Loads, but only on a v71 core** | Polygon1000 DMD (Mightex) — vendor package pinned to MM interface **v71** against the v75 core | the one device that does not load through **pymmcore-plus**, which floors at `pymmcore>=11.10.0.74.0`. It loads fine through raw `pymmcore==11.1.1.71.2`, and `DMD_dualcam_LUNF.cfg` then loads complete (31 devices, 912×1140 SLM) — measured 2026-09-07, recipe and the SDK warning in [`kb/decisions/2026-09-07-dmd-on-v71-and-blue-flip.md`](kb/decisions/2026-09-07-dmd-on-v71-and-blue-flip.md) |
| **Physically present, software-invisible** | `Splitter` (no `Device,` line in any `.cfg`), polarizer (angle adjustable, off-ledger), analyzer (angle fixed), the transmitted-path colour filter, the coverslip (a micrometer reading) | these invalidate a run without leaving a trace. The `Splitter`'s unverified position was the last suspect standing in the 2026-09-04 blackout, precisely because it was the one nobody could check |
| **On the bench, not in the record** | **temperature-controlled stage** — stated by the operator 2026-09-06 and, until then, absent from this repository entirely | see below. This is the tier that cannot be found by enumerating anything |

**The last row is the one worth reading twice, and it is not a device problem.**
`kb/systems/` had no entry for a temperature stage and `stability/` (lens 8) has
no temperature input at all — while this README argues in two separate places
that an unmeasured temperature is a top-tier uncertainty: sample temperature at
the coverslip is **3–8 %, one-sided** in the error budget of the only real
measurement here ([below](#current-status)), and on the simulation side `T = 300 K`
is *"the most damaging soft spot … worth −4 % to −14 % on every timescale it
computes, because water's viscosity is 2.06 %/K sensitive"* — followed by **"a
thermometer reading ends that."** A stage that controls the quantity was on the
bench the whole time. Nothing enumerable would have surfaced it; only the
operator saying so did, which is what
[09](docs/09-knowledge-capture.md) is for and why it is called the real purpose
of this project. → [`kb/systems/current.md`](kb/systems/current.md) now carries
the stub; the make, range and whether it is software-reachable are `TODO(human)`.

> **Development context.** An independent project, developed primarily during
> evenings and weekends alongside full-time postdoctoral research at Stanford,
> begun in early July 2026. It is built on **one** instrument — the microscope
> in Prof. Sho Takatori's lab, Stanford Chemical Engineering — and every
> calibration, expertise note and device record here is that instrument's,
> labelled as such. Not a supported product.
>
> **Companion projects — four axes of one system.**
> [`Brownian-Dynamics Agent`](https://github.com/kyu-softmatter/Brownian-Dynamics-Agent)
> applies the same provenance and validation rules to simulation. It asks what
> the physical system should do; this asks whether the instrument can measure
> the difference well enough to decide.
> [`research-topic`](https://github.com/kyu-softmatter/research-topic)
> asks which question is worth asking at all, and holds the definitions of rigor
> that the others enforce — **a sketch; nothing is built there yet**.
> [`librarian-agent`](https://github.com/kyu-softmatter/librarian-agent) keeps
> the knowledge findable across all of them and reports when it has gone stale:
> six read tools run over an index of **this** repository, and no knowledge has
> moved yet. **No working repository depends on either of the two.**
> → [below](#toward-a-model-to-experiment-loop)

---

## What works today

Every lens computes and returns a verdict. What that verdict is allowed to
claim is a separate question, and mostly the answer is *not yet* — which is the
design, not a gap.

| | |
|---|---|
| **8 review lenses** | optics · detection · compute resources · sample geometry · photo-perturbation · measurement validity · optical tweezers · mechanical & environmental |
| **26 deterministic gates** | G1–G32 less the vacant `G10`, `G18`, `G20`, `G21`, `G22` and `G28`, each classified `hard` / `bias` / `soft` by what its failure costs. **23 are implemented** — `G2`–`G4` carry a threshold and a default verdict in [04](docs/04-decision-engine.md) and appear in no Python file; `G10` and `G20` went on 2026-09-09, `G18`, `G21` and `G22` on 2026-09-10 — the last two when **lens 5 became a reporting section rather than a judging lens**; `G28` moved to the hardware execution stage on 2026-09-10; none of the six numbers is reused → [below](#two-more-axes-and-the-questions-neither-working-repo-asks) → [05 §2](docs/05-consensus-gate.md) |
| **Provenance on every input** | `measured` vs `assumed`, with a separate `advances` axis that only `measured` can satisfy. Literature values compute but never advance → [`kb/literature/`](kb/literature/) |
| **2,343 prior acquisitions** | normalized out of Micro-Manager metadata into transferable physical quantities, across two schema generations |
| **1,225 tests, 1,162 on CI** | offline; the instrument is not required to run any of them. The badge covers 1,162 — of the rest, 56 need a Micro-Manager device-adapter install and 7 need `opencv-python`, and `PYTEST_CI_EMULATE=ci` reproduces the runner's environment here → [running the tests](#running-the-tests) |
| **A 28-device instrument** | what Micro-Manager loads from `single_cam_red_noDMD.cfg` — Ti2-E and its 14 sub-devices, one Kinetix, seven CSU-W1 devices, two Lumencor engines, NIDAQ hub + LUN-F blanking, serial manager. Tweezers and piezo sit outside those 28 → [above](#agentic-microscope) |
| **Hardware drivers** | microscope (pymmcore-plus), optical tweezers (TCP), piezo stage (vendor DLL), trap patterns, piezo waveforms, and a shared-clock orchestrator |
| **First light on real hardware** | piezo and optical tweezers each driven from this repository, **separately** — 2026-08-27. **All three subsystems together on one clock — 2026-09-03**, with per-frame timestamps; κ = 3.65–4.5 pN/µm from three independent routes |
| **Live detection driving the trap** | 2026-09-04, operator-gated: GPU detection on the full frame picks an isolated particle, the trap is placed on it and ramped to the field origin. Four beads of five caught and carried 11–26 µm at 98.6–99.8 % follow → [`kb/decisions/2026-09-04-closed-loop-trapping-measured.md`](kb/decisions/2026-09-04-closed-loop-trapping-measured.md) |
| **Two-species sorting on both cameras** | 2026-09-05, operator-triggered: one keypress surveys each species under its own line, plans collision-free corridors, and transports up to 9 per species into columns at x = ±18 µm, looping rounds until the candidate pool dries. Five fields, 34 rounds, **47 of 72 beads parked**; best field 13 of 18 slots. Four of the five runs ended out of *candidates*, not out of slots → [`config/session/sort_core.py`](config/session/sort_core.py) |
| **Real-time primitives, off the hot path** | [`runtime/`](runtime/) — a one-slot frame ring with a drain-and-keep-newest camera thread, a fixed-period loop clock that cannot drift, and a rate-capped shared-memory channel so a live view runs in a second process instead of competing for the GIL. Ported from the lab's bacteria stack; **not yet run against a camera** → [`kb/decisions/2026-09-05-runtime-primitives-and-gpu-scope.md`](kb/decisions/2026-09-05-runtime-primitives-and-gpu-scope.md) |
| **Guarded stage motion, and the first measured lens offsets** | 2026-09-07. [`hardware/focus.py`](hardware/focus.py) writes `ZDrive` behind four guards — `allow_motion`, PFS must not be servoing, every sweep capped at `min(2800–3200 µm window, centre + 0.4 × free working distance)`, and readback on every move. Autofocus sweeps coarse→fine and takes the peak by parabola. **The dry ladder is measured**: 10x **−36.771**, 20x **−40.144 µm** from 4x on a fluorescent monolayer at 555 ex / 605 em, with a **0.293 µm** loop closure across three rotations. x/y is recorded as *invalid* rather than measured — identical particles mean each lens locks onto a different one → [`kb/calibrations/objective-offsets.yaml`](kb/calibrations/objective-offsets.yaml) |
| **A written hazard account** | [`SAFETY.md`](SAFETY.md) — laser classes, the objective/coverslip collision procedure, camera ownership order, and the failure modes that return `0`. **First draft, not yet operator-reviewed** |
| **An MCP surface over both bespoke paths** | tweezers and piezo as 9 MCP tools in four tiers, the two moving ones refused by default, verified end to end over stdio but **not yet against a device** → [below](#an-mcp-surface-over-the-two-bespoke-paths) |
| **Refusal paths that hold** | `hardware/lunf_power.py` is complete as transport and refuses to transmit, because the DAC word format is undocumented and a guessed byte goes into a laser driver |

What is **not** true today, stated here so nothing above implies it: **no MCP
tool has reached a device**, and no experiment has been executed end to end by
the agent. Those are the
[current execution boundary](#current-execution-boundary).

Two items that stood in that list until 2026-09-04 have to be narrowed rather
than kept or dropped. **A feedback loop does now close** — live detection picks
a particle, the trap is placed on it, and the trap is moved with the bead
following — but it is **gated by a keypress at every stage and it serves
selection, not measurement**: the live path samples the newest frame and drops
the rest by design, so nothing it produces can become an MSD. And frames *are*
analysed while the camera is streaming, for the same purpose. What is still
absent is the thing item 5 is about: analysis that runs against **a measurement
in progress** and changes it, with the per-frame provenance record that would
make the changed run judgeable.

One correction the 2026-09-03 run forced, kept here rather than quietly
dropped: `Breakpoints > Enable Bits` is `0000`, so `TRAP_PATT_RELEASE_BP`
returns `0` while doing nothing. **Every release-round-trip latency figure
measured before that date is precision on a command with no effect.**

Three more, from the 2026-09-05 sorting session. Each is something this
repository asserted, and none of them is true. **The Tweez GUI has no
trap-count ceiling**: 160 named traps were created and deleted cleanly in one
pass, so the `-20 "requested resource not supported"` that `sort_core.py`
attributed to running out of trap slots was something else — and that claim had
already been used in argument against trapping more particles at once.
**`10012` on a Kinetix is usually a wedge, not contention**: property reads keep
answering correctly while any acquisition times out, releasing the camera in the
GUI changes nothing, and one standalone snap on that body clears it. `SAFETY.md`
§4 frames every camera failure as ownership order, which cost three launches
before the alternative was tested. And **`sort_two_species.py` did not import
`sort_core.py`** — it was a standalone copy, so a fix on the keypress path
reached one of the two paths, not both. ✅ **Consolidated 2026-09-06**, and
what the copies had actually drifted in is the part worth keeping: all six
shared functions were numerically identical over 20 000 random cases, while
four carried *fuller docstrings in the CLI than in the shared module* — so the
divergence was real and running in documentation, which is the state in which
the next one goes unnoticed. The better documentation moved into `sort_core.py`
and [`tests/test_sort_one_copy.py`](tests/test_sort_one_copy.py) now fails if
either file defines a shared name again. It also deleted `rms_nm`, dead code
implementing the held-bead test this repository measured wrong five times out
of five.

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
    [FAIL] missing.bleach_photons            <- G10, REMOVED 2026-09-09
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
  |  COMMITTEE          8 lenses . 26 gates (7 judging lenses)      |
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
  |  [ a device-level standard would land HERE, or beside it ]        |
  |  It replaces the per-vendor half of the drivers below and the     |
  |  discovery rung above. It does NOT touch the 26 gates, which sit  |
  |  over any transport, and MCP is the layer above again -- how an   |
  |  agent reaches tools and context at all.                          |
  |                                                                   |
  |  Of the seven non-baseline reachability tiers above, THREE would  |
  |  collapse into the first (a readable vendor DLL, a self-          |
  |  describing turret, a version-locked package that adopted it) --  |
  |  and FOUR would not: no readback, an undocumented protocol, an    |
  |  analog element, and a device nobody wrote down.                  |
  |                                             docs/mhs-integration  |
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
  |  kb/sessions/      one file per working day: what was attempted,  |
  |                    what failed and why, what state the instrument |
  |                    was left in. README.md indexes them and tracks |
  |                    where each running project actually stands.    |
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
documents, 26 gates (G1–G32 less G10, G18, G20, G21, G22, G28), 1,237 tests passing. The badge above reports
1,162 of them — 56 need a Micro-Manager device-adapter install and run in a
separate workflow, and 7 need `opencv-python`, which is stated at the top of each file in
[`.github/workflows/`](.github/workflows/) and again under [running the
tests](#running-the-tests). The six standing
lenses — optics, detection, compute resources, sample geometry,
photo-perturbation, measurement validity — and both conditional lenses —
optical tweezers, mechanical/environmental — each compute their verdict and
report it through their committee gate. Lenses 4 · 5 · 6 · 8 additionally carry
the qualitative half of their judgment as LLM subagents in
[`.claude/agents/`](.claude/agents/), layered on top of their code, because part
of what they weigh has no closed form. Three things are deliberately left
ungated and named as such: vibration (no measurement
channel exists), local heating at 1064 nm ([06 D6](docs/06-pitfalls.md)), and
near-wall Faxén drag ([06 D8](docs/06-pitfalls.md)), which is absorbed by
in-situ trap calibration rather than corrected by formula. **Stage
repeatability left that list on 2026-09-07**: revisiting 4x after three
nosepiece rotations closed to **0.293 µm**, so the retract-rotate-return now
has a measured bound rather than an assumption →
[`kb/calibrations/objective-offsets.yaml`](kb/calibrations/objective-offsets.yaml).

What is blocking progress is mostly **facts, not code** — the gates run, but
return `BLOCKED` for want of measured inputs. Illumination power at the sample is
the top blocker: `power_at_sample_mw` is empty for every registered light source,
and it cannot be substituted by code (a power meter is required). The remaining
hardware measurements have runnable scripts in
[`calibration/`](calibration/), and results already collected are in
[`kb/calibrations/`](kb/calibrations/). → [Phase 0](docs/07-roadmap.md)

**`BLOCKED` is the current default, not the permanent one.** One `UNKNOWN`
among the 26 gates blocks the verdict today, which is the only defensible
setting while there is no record to check a verdict against. As experiments
accumulate, strictness relaxes — but against the record rather than against
confidence, by promoting an input's evidence tier rather than lowering a
threshold, and never on a hard gate or a bias gate. What has to be accumulated
for that is **the outcome of refusals**, not the count of runs that went well.
→ [05 §7](docs/05-consensus-gate.md)

**First end-to-end run: 2026-09-04, operator-guided.** A single experiment —
wall-hindered Brownian motion of sedimented 5 µm carboxylate polystyrene beads
in a closed 1 mm PDMS well — was carried from a bare question ("suggest a
sample geometry") through all eight lenses, into device state on the
instrument, and out as timestamped image stacks with zero dropped frames and a
run record naming every assumption they rest on. That path had never been
walked before.

**It was a commissioning run, and the committee said so.** No lens returned
`advances: YES`. Lenses 5 and 8 returned `BLOCKED` (no measured power at the
sample; no drift rate anywhere in `kb/calibrations/`), lens 4 graded
`INFEASIBLE` on the near-wall drag that *was* the measurand, and lens 6's
ruling was explicit: run it, label it commissioning, and **report no hindrance
ratio from it**. Calling this a successful measurement would be wrong; calling
it a successful *run* is precisely right, and the distinction is the one
[05 §7](docs/05-consensus-gate.md) is built on.

A `D` **was** extracted later the same day, over 9 independent fields on a
300 µm grid: `D‖ = 0.03951 ± 0.00039 µm²/s` (SEM 1.1 %, field SD 3.0 %, 173 of
235 isolated beads from 2692 detections), `D/D_bulk = 0.461`, inverting through
the full Faxén series to a mean gap of 373 nm and `h/a = 1.149`. It is robust
to ±0.9 % across three treatments of the MSD intercept and `d ln D / d ln h`
is 1.73. **It is still not a measurement of the wall effect**, because lens 6's
`BLOCKED` items are what dominate the error budget and none of them were
closed: sample temperature at the coverslip (3–8 %, one-sided, unmeasured),
Faxén truncation at `h/a = 1.15` (3–5 %), and the bead radius CV (2–5 %). The
number's use is that it makes a *testable prediction about the medium* — pure DI
water would put the gap at 889 nm, so 373 nm implies an ionic strength of
roughly 0.05–0.1 mM. Measuring the medium's conductivity would confirm or break
it.

**The same day, the loop was closed to the optical trap.** Live GPU detection
now hands a chosen particle to the tweezers: five cycles of detect → trap →
ramp-to-origin at 100×, four beads caught and carried 11–26 µm to the field
origin at 98.6–99.8 % follow, driven from Python over TCP with the laser armed
by hand. That fixed the px → trap-µm orientation (four quadrants, four
catches — nothing but the right rotation and handedness does that) and measured
the trap origin to `(584.42, 584.38) ± (0.68, 0.48)` px, a systematic
`(−1.013, −1.015) µm` from the frame centre. The scale is still nominal, and
the session also **falsified the test used to check the catch**: a bead's RMS
excursion was wrong in five cycles out of five, because a bead stuck to the
coverslip sits as still as a trapped one. Moving the trap and watching whether
the bead comes separates them completely.
→ [`kb/decisions/2026-09-04-closed-loop-trapping-measured.md`](kb/decisions/2026-09-04-closed-loop-trapping-measured.md)

**What the run actually yielded was six falsified records** — and that, not the
data, is the return on it:

| Record | What it said | What the instrument said |
|---|---|---|
| `lapp_branch` | `mirror_in` couples Aura to the sample | **The record was right; the `.cfg`'s labels were swapped.** Following it turned the light off and cost a diagnosis session, and the branch was booked as falsified for two days before the operator's 2026-09-05 mapping showed the mislabelled enum was the fault. `State 1` is the Aura position and everything now pins the integer |
| `Splitter` `current_position` | `1` (unverified since 2026-08-10) | Not readable at all — it is not in the `.cfg`. Now `null` |
| Z retract direction | "+Z is probably the retracted direction" | Backwards. Z → 0 is the safe park (KH) |
| `IntermediateMagnification` | a state device, per `calibration.cli intermediate-mag` | a **MagnifierDevice**. The tool mismatched it and reported "0 positions" |
| `sample/aberration.py` Faxén term | "a bound, and it errs the safe way" | Not a bound below `h/a ≈ 1.70`. At `h/a = 1.05` it understates the drag |
| PVCAM despeckle | enabled in every archive generation ([06 C1](docs/06-pitfalls.md)) | a **sticky camera default that returns on every config load** — not carelessness. Dark-frame max 148 ADU with it on, 1193 with it off |

Every one was found because a gate or a script refused rather than proceeding,
and **five of the six were corrected by the operator supplying a fact the
repository had wrong or did not hold** — which is what "operator-guided" means
here, and why this is not yet an autonomous loop.

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
of the chain and jump the queue anyway — each was waiting only on being at the
instrument. **0b is done as of 2026-09-02**; 0a is now waiting on nothing but
half an hour, and 0c on a DLL that is still not on this PC. Then five: **1–3
are the missing path from a committee verdict to a running instrument** —
**item 1 is done as of 2026-09-03** — 4 is the first real use of that path, and
the only test of whether any of the rest was right; **5 is the next step**, is
what a run does with what it is seeing while it is still happening, and
**was started on 2026-09-04**, where its first rung returned a negative result.
Items 1–3 sit between stages 5d and 5e, and 5 is 5e itself
→ [07 Phase 5](docs/07-roadmap.md#phase-5--automating-microscope-operation).

> **Every item below that moves hardware — 0a, 0b, 0c, 1, 4, 5 — is gated on
> [`SAFETY.md`](SAFETY.md) first.** Read it before the laser is armed, before a
> nosepiece write, and before the piezo is unlocked. It is a first draft and
> not yet operator-reviewed.
A note on how this would look under Anthropic's Model Hardware Standard is in
[`docs/mhs-integration.md`](docs/mhs-integration.md), deliberately off the main
line. It is a description of this bench written against that standard's stated
problems rather than a case for adopting it, and its two most useful entries are
a failure and an absence: a held-bead test this repository built and then
falsified in five cycles of five, and a temperature-controlled stage that was on
the bench for two months while nothing here knew it existed.

- [ ] **0a · Measure the illumination power at the sample.** Outside the 1→5
  chain and ahead of all of it. This is the one blocker in the whole repository
  that **code cannot substitute for**, and it was deferred on 2026-08-19 partly
  because no meter was available.

  **The equipment excuse is gone.** A power meter was in hand by 2026-09-02 —
  it is one of the two things that made the LUN-F SPI probe's consequence
  boundable enough to run (0b §6). So this is now blocked on nothing but doing
  it, and `power_at_sample_mw` is still `{}` for **every line of every
  registered source** as of 2026-09-04.

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

  Two limits to hold onto, so the measurement is not oversold. It **did** unblock
  lens 5 once the illuminated area followed the same day, and G10 — the one gate
  it could not have unblocked — was removed rather than left waiting for a dye
  constant nobody has. And it is **immediately meaningful for the widefield
  sources**
  (SpectraIII, AuraIII) but contingent for the confocal lines: until the LUN-F
  per-line power path exists, measuring those characterises the laser at
  whatever power NIS last left it at, not at a power this repository can command
  → [07 Phase 0](docs/07-roadmap.md).

- [x] **0b · Reach the confocal laser without going through NIS-Elements.**
  ✅ **Done 2026-09-02**, and it answered more than it was asked
  → [`kb/decisions/2026-09-02-lunf-first-light-measured-limits.md`](kb/decisions/2026-09-02-lunf-first-light-measured-limits.md).

  The LUN-F-XL (405 · 488 · 561 · 640 nm, feeding `CSUW1-Hub`) is **the only
  laser on this instrument** and was reachable only through NIS-Elements, which
  the 2026-08-11 decision had taken out of the control path entirely. It is now
  driven from Python with NIS not running: wavelength selection and on/off per
  line, **blanking polarity measured as active-HIGH** where Nikon documents
  nothing, and — the part nothing in the record had established — **the DAC is
  writable.** A 32-frame probe extinguished 561 while leaving 640 emitting, so
  the FT4222 SPI link reaches the DAC and writes are channel-selective; nine
  candidate framings alternated full-scale against zero with the blanking line
  held open made 561 flicker, so **arbitrary levels write, not just zero.**

  The one-bit question was answered too: the chassis **does** enumerate as its
  own USB device — **COM8**, an FT232R with a vendor-programmed EEPROM, and NIS
  never opens it. But that turned out not to be the way in. NIS's own "USB"
  control mode *is* the FT4222 (`v6_w32_device_LUNF.dll` contains no `COM` or
  `baud` strings at all), so COM8 is a separate link whose command set is
  entirely unknown and nothing has ever been sent to it.

  Two things closed negatively, which is worth as much. **The AO route is
  dead** — the PCIe-6323's four AO channels against the LUN-F's four lines was
  suggestive and wrong, tested per-channel and at rate with the blanking held
  open, no flicker; no one needs to propose it again. And **nothing about the
  LUN-F can be read back, at all**, which puts it with the tweezers rather than
  the piezo.

  **The successor item is narrower: name the DAC word format.** It is one of
  **nine** candidate framings (§6), and three bisection rounds would settle it.
  Until then levels are writable but not *commandable* — you cannot ask for
  50 %. [`hardware/lunf_power.py`](hardware/lunf_power.py) still refuses to
  transmit without `PROTOCOL` set, which is the right default for a byte going
  into a laser driver.

  Note what changed about the discovery rule, because it was a deliberate
  relaxation and not a lapse.
  [`2026-08-29-device-discovery-scope.md`](kb/decisions/2026-08-29-device-discovery-scope.md)
  forbids writing to a device to learn what it does. Two things made the
  consequence boundable — measured blanking, so the laser can be gated off in
  software before any byte is sent, and a power meter — and every frame in the
  probe carried **data = 0** with all four blanking lines closed, so no
  candidate could raise the output. The rule's *purpose* held. The relaxation
  was the operator's explicit call.

- [ ] **0c · Confirm the MCP surface reaches the hardware.** Built 2026-08-31
  ([`mcp_server/`](mcp_server/), 9 tools, 30 tests) and verified end to end over
  stdio — handshake, tool list, a plan matching what
  [`config/tweezers/run_pattern.py`](config/tweezers/run_pattern.py) prints, a
  refused move. **No tool has reached a device**, and that is still true after
  2026-09-04 — but for only one of the two reasons it used to be true, so the
  wording matters.

  **The tweezers half is no longer blocked by the instrument.** The Tweez GUI
  answered on port 2070 all through the 2026-09-04 session and this repository
  drove it — created a trap, positioned it, armed it, streamed positions — so
  check 3 below is now a 30-second job rather than a wait. What it went through
  was [`hardware/optical_tweezers.py`](hardware/optical_tweezers.py) **directly,
  not the MCP server**, which is exactly the distinction this item exists to
  keep: the driver reaching a device says nothing about whether the nine tools
  wrapping it do.

  **The piezo half is still blocked, and it is the equipment.**
  `controller_interface64.dll` and its 32-bit sibling are not on this PC
  (re-checked 2026-09-04), so the `read` and `move` tiers have still only been
  exercised along their refusal and unavailable paths. Until that changes the
  claim is *the interface is correct*, not *the interface works*.

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
  unconditionally.

  The camera-ownership conflict is **unresolved but no longer untested.** On
  2026-09-04 a full session ran with Micro-Manager owning `Kinetix_red` while
  TCP drove the trap, which is the workaround the 2026-08-27 note predicted and
  is now demonstrated rather than argued: trap commands survive the GUI
  releasing the camera. What that does *not* fix is the case the conflict was
  raised for — active microrheology needs bead **and** trap position at the
  same instant, and the trap position on that route is commanded rather than
  read, so it is known only to the host clock.

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
     camera's clock** — the three routes under item 1 are its precondition.
     2026-09-04 settled the *spatial* half of that and only the spatial half:
     the trap's origin is measured to ±0.7 px and its orientation confirmed, so
     a commanded position converts to camera pixels. *When* the trap was there
     is still host-clock only. And
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

  **Started 2026-09-04, and the first rung came back with a negative result
  worth more than the rung.** The first bullet below — detect whether a bead is
  held — was built and **measured wrong in five cycles out of five**. A bead's
  RMS excursion over 1.5 s called four held beads free and one unheld bead
  held, because *a bead stuck to the coverslip sits as still as a trapped one*
  and *a bead just trapped is still travelling into the well*. No threshold
  fixes that; the statistic does not separate the populations.

  What does separate them is **moving the trap and seeing whether the bead
  comes** — 98.6–99.8 % against 2.9 %, nothing in between. Which is this
  section's own principle arriving from an unexpected direction: on an
  instrument with no readback, measuring the result *is* the readback, and here
  the measurement had to be an **action**. A passive observation of the frames
  could not answer the question at all. That is a constraint on every rung
  above, not a detail of this one.

  What exists after that session: full-frame GPU detection at 36 Hz, targeting
  through a px → trap-µm transform whose orientation and origin are now
  measured, placement, a speed-limited ramp, and arrival verified by comparing
  the bead's travel against the trap's. What is still missing is everything
  that makes it a *run*: it advances on a keypress rather than a criterion, it
  samples the newest frame and drops the rest, and no per-frame record of the
  decisions exists → [`kb/decisions/2026-09-04-closed-loop-trapping-measured.md`](kb/decisions/2026-09-04-closed-loop-trapping-measured.md).

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

**The switches, by name, and what they are set to.** `.mcp.json` launches the
server through [`mcp_server/bootstrap.py`](mcp_server/bootstrap.py), which
resolves an interpreter that can actually `import mcp` — no `uv`, which appears
nowhere in this repository, and since 2026-09-06 no hardcoded path either
(to-do item 11) — and its `env` block ships both switches **off**:

```json
"env": {
  "AGENTIC_MICROSCOPE_ALLOW_MOTION": "0",
  "AGENTIC_MICROSCOPE_ALLOW_LASER":  "0"
}
```

So on a fresh session **every move-tier call answers `refused: true`**. That is
the configured default, not a broken server and not a bug to route around —
which is worth stating here because it is the first thing anyone meets, and the
paragraph above only explains why a refusal is a value, not that it is what you
will get.

**Two operational surprises, both harmless and both easy to misread as faults.**

- **The running server holds the log file.** It keeps
  `%LOCALAPPDATA%\pymmcore-plus\pymmcore-plus\logs\pymmcore-plus.log` open, so
  every *other* script started while it runs prints a `PermissionError`
  log-rotation traceback at startup. Noise, not a device fault.
- **Count server instances by parent process, not by process.** Each instance
  appears as **two** processes: the venv `python.exe` launched by `claude.exe`,
  plus a base-interpreter child carrying an identical command line and creation
  timestamp. Measured 2026-09-05: four `mcp_server.server` processes were two
  instances, both with live `claude.exe` parents and neither orphaned. Counting
  raw processes double-counts every instance and invents a leak that is not
  there — and killing them breaks whichever live session owns them.

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
  landing in it propagates into 26 gates.
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

### Two more axes, and the questions neither working repo asks

Both working repositories take the scientific question from a human, and both
hand their evidence back to one. Two others are meant to sit in those places —
one to propose the question, and one to keep what came back **including the
failures, which is the part that gets skipped.**

| Axis | Repository | Asks | Status |
|---|---|---|---|
| **Topic** | [`research-topic`](https://github.com/kyu-softmatter/research-topic) | which question is worth asking | sketch only. **Nothing built** |
| **Experiment** | **this repository** | what the instrument can actually record | running |
| **Simulation** | [`Brownian-Dynamics Agent`](https://github.com/kyu-softmatter/Brownian-Dynamics-Agent) | what the physical system should do | running |
| **Knowledge** | [`librarian-agent`](https://github.com/kyu-softmatter/librarian-agent) | where the answer already is, and whether it has gone stale | read tools running over an index of this repository. **Nothing migrated** |

Two things neither working repository can own, and they turned out to belong in
different places:

**1 · A knowledge base both can read → `librarian-agent`.** This repository has
one, and it is **bound to the instrument** — `kb/systems/current.md` is which
machine this microscope actually is, and a simulation cannot use that. The
domain-neutral half needs somewhere else to live, and custody of it is a job on
its own: a store that only accumulates goes stale, and this repository already
carries the symptom. Seven `[[wikilinks]]` in `kb/` point at entries nobody
wrote, `G2`–`G4` carry a threshold in `docs/04` and appear in no Python file,
and `kb/expertise/oil-objective-trapping-in-water.md` — the entry
`research-topic` holds up as the model challenge — carries no falsification
section where five of the six beside it do. **All four were found by that
repository's drift report rather than by reading.**

**2 · The definitions of rigor, in one place.** This repository enforces 32
gates; the simulation side enforces ten rigor axes. They were built independently
and converged on the same shape — division by axis rather than by person, a
deterministic gate, default-to-`BLOCKED`, a falsifier attached to every judgment,
and an LLM that originates no number. **That convergence is the argument for a
third place:** what two projects reached without consulting each other is not
domain-specific, and keeping one copy of it beats keeping two that drift.

The intended shape is a loop rather than a pipeline, and **that is why the risk is
worth stating out loud**: components that feed each other will amplify whatever
bias they share. `research-topic` carries that objection as a registered
conflict, and its answer is that a topic may only enter the loop in a form the
working repositories can falsify.

**No dependency runs the other way.** Nothing here imports, reads or waits on
either of the two, and if neither is built, nothing here breaks. `librarian-agent`
reads this repository and writes nothing to it; anything it proposes arrives as a
pull request.

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

## To do

**Items 1–5** were raised by the operator (KH) at the end of the 2026-09-04
wall-diffusion session. Each one is here because something that session needed
was missing, and the "why it cost something" line is the point — an item without
it drifts into a wish list.

**Items 6–11** were raised by KH on 2026-09-05. They are a different kind of
item: not a missing datum but a missing *procedure* — things the operator does
well by hand, or knows to ignore, that nothing in the repository states in a
form anyone else could follow.

Their cost lines vary in strength and each says which it is. **9** and **10**
carry the operator's procedure verbatim and have real costs attached (a
hand-authorised ±300 µm box that set a published error bar; a triple of
settings passed as bare flags). **7** turned out to be nearly closed once KH
supplied the measured Z sign — and closing it revealed that the repository had
been carrying the *reverse* of the truth in a safety file. **6** and **8** still
need the operator's numbers before they mean anything.

Item 7 is the argument for keeping this section: the correction came out of one
sentence from KH, could not have been derived from the code, and the code was
confidently wrong in the dangerous direction.

### 1. A particle and dye information sheet

One row per stock: catalogue number, diameter and its CV, density, **surface
chemistry**, dye excitation/emission, ε, Φ, τ, `bleach_photons`, and the
storage buffer's ionic strength.

*What it cost on 2026-09-04:* the bead's dye was never identified, so lens 5
returned **BLOCKED** on `missing.bleach_photons` *and* `missing.lifetime` —
`bleach_photons` is empty for **every** dye in `data/fluorophores.yaml`, so
G10 had nothing to count against. (G10 was removed on 2026-09-09 for that very
reason, so half of that refusal would not recur — `missing.lifetime` still
would, and the sheet is still worth building.) The channel had to run on a proxy
(`ATTO550`), and lens 1's `collection` **FAIL** turned out to be an artifact of
that proxy's 576 nm emission rather than a real problem — the operator's
confirmation of 605 nm cleared it. `docs/06-pitfalls.md` D4 already says a
conjugate name is not a fluorophore name; "5 µm red PS bead" is a product
description, not a photophysics record.

And the field that mattered most was not photophysics at all: **carboxylate**
surface chemistry plus DI water puts the bead ~1 µm off the coverslip instead
of the 126 nm gravity alone would give, which moved the predicted `D‖/D_bulk`
from 0.39 to 0.58. The measurand's controlling parameter came out of a line
that no sheet currently holds.

### 2. Many more experimental geometries, to exercise the decision layer

The committee has been run end to end on exactly one geometry — sedimented,
untrapped, near-wall, single colour, widefield. Whole branches have never been
executed against real inputs: `sample.gate`'s Phase-0 blocks for multiphase and
birefringent media, G16c's *trapped* absorption route, the confocal path, the
dual-camera split, ATPS per-phase reasoning. A gate that has never refused a
real experiment is a gate nobody has tested.

### 3. The filter-wheel pass bands

EM1/EM2 positions 0–4 are `multi / 405 / 488 / 555 / 647` and all carry
`registry: null` in `kb/systems/current.md`. The labels are named by
**excitation** line, not by the emission band they pass (KH 2026-09-04). The
2026-08-11 correction in that file explicitly retracted the
`88000v2-Quad/455-50/525-36/605-52/705-72` set as EM1's filters — another
element's data had been attached there by mistake — so `EM1-605/52` in
`data/filters.yaml` is **not** confirmed to be in this wheel.

*What it cost:* the channel config for 2026-09-04 listed `EM1-605/52` as an
emission element and lens 1 computed `collection` and `emission.centering`
with it in the path. Lens 1 flagged it in `assumed_inputs`, but "curve not
measured" and "this filter may not be in this wheel at all" are different
problems and only the first was noticed. The run went ahead on `multi`, which
is known to pass red and to block the PFS IR that lens 8 warned about.

> **TODO(human):** the actual centre and FWHM for positions 1–4. Then link them
> into `data/filters.yaml` and decide whether `555` beats `multi` for the
> ex555/em605 channel — it should, if it is a bandpass, because `multi` also
> opens three bands we do not use.

### 4. Connect the Splitter position to the configuration file

The `Splitter` (dual-camera image splitter, `{0: 100/0 mirror, 1: DM A561LP,
2: open}`) is **not in the Micro-Manager `.cfg`** — its absence was settled
2026-08-12. So nothing can read it back, and the recorded position ages in
silence.

*What it cost:* `current_position: 1` had stood unverified since 2026-08-10.
On 2026-09-04 `Kinetix_red` returned frames statistically identical to a dark
frame while **every** software-readable element in the path checked out, and
the Splitter was the last suspect standing precisely because it was the one
nobody could check. It is now recorded as `current_position: null` with
position 2's consequence written down ("the red camera is the only one that
sees light"), which is honest but still not readable.

The general form of this item, worth stating because it is not only the
Splitter: **an element MM cannot read is an element whose record drifts.**
Either get it into the `.cfg`, or make the acquisition record the operator's
assertion about it the way `run_wall_diffusion.py` does for the 1064 nm
emission state.

### 5. The trapping range, and the rest of the px → trap-µm transform

Two numbers stand between the closed-loop trapper and being able to reach any
particle in the field.

**The trapping field's half-extents.** ✅ **Stated for the 100× on 2026-09-06,
and the shape claim changed with it.** The operator's statement — *"trapping
area is always square, the center of the square is located in the middle of the
camera view, the square size is around (−40 µm to 40 µm) in x and y"* — settles
±40 µm at 100× Oil and **contradicts the trapezoid** this item was named after.
The contradiction is recorded rather than resolved by preference: an operator's
statement about their own instrument outranks a shape read off a GUI drawing,
since a square drawn in perspective looks like a trapezoid. So the rectangular
range check is now believed *sufficient* and not merely necessary — and if a
pattern ever deforms while passing it, that belief is the first thing to
re-examine.

*What it cost on 2026-09-04:* nothing yet, and that was luck. Points outside
the calibrated field are **clipped silently by the GUI and not drawn**, so an
over-long reach lands the trap somewhere else with no error on either side.
`--max-offset-um` is a placeholder — 30 µm was used because the nearest
isolated bead was 23–29 µm out — and it is a guard against a limit nobody had
measured.

*What it cost on 2026-09-05, and what remained after the statement:* the
stand-in had quietly become a design limit. `TRAP_HALF_RANGE_UM = 40.0` was
hardcoded in **four separate files** (`sort_core.py`, `sort_two_species.py`,
`live_dualcam_view.py`, `trap_brightest.py`), three of them with no comment
saying where it came from. Once the operator stated the number, the defect
stopped being *"a placeholder in four copies"* and became something narrower
and worse: **a verified 100× value applied whatever objective was in place.**
The AOD covers a wider sample field at lower magnification, so at 40× it is
simply a different quantity — and
[`hardware/tweezers_drive.py`](hardware/tweezers_drive.py) had refused an
unrecorded `trapping_range` since it was written, with
`test_range_check_blocked_not_passed_when_unrecorded` holding that line, while
the four literals bypassed it.

✅ **Fixed 2026-09-06.** [`data/trapping_range.yaml`](data/trapping_range.yaml)
is the one source, keyed on objective and mirroring
`kb/systems/current.md > optical_tweezers > trapping_range`;
`optics.components.trapping_range_um` is the one reader; and
`sort_core.resolve_half_range_um` resolves it from the nosepiece and **refuses
for any objective whose extent has never been stated** — which is all five
others. There is deliberately no scaling rule: deriving 40× from 100× by a
magnification ratio would produce a plausible number with no provenance, which
is what the literals were. The slot count now follows the field instead of
being fixed at 9 → [`tests/test_trapping_range.py`](tests/test_trapping_range.py).

Two things that fix does *not* buy. The 100× figure is `evidence: stated`, not
`measured` — nobody has read it off the *Beam Position* calibration — and only
the central 80×80 µm of the ~156 µm field is reachable at 100×, so at a 10 µm
slot pitch the two-species sort still has 9 destinations per species: 18 beads
against 43–50 detected *per species* per survey. **That ceiling is now a
measured property of the instrument rather than an artefact of a literal**,
which changes what to do about it — widen the field or shrink the pitch, not
edit a constant.

**The scale.** The orientation and origin are settled (four catches in four
quadrants; origin to ±0.7 px), but `um_per_px` is still the nominal 0.065 and
the ramps cannot measure it: the bead's starting pixel is where the *bead* was,
not where the trap was *commanded*, and solving the matrix from that mixes the
two (it comes out 12 % anisotropic, which is the contamination, not the
optics). One 5 µm 1 Hz sine on a bead **already sitting in the trap** closes
it — `trap_from_tracking.py calibrate` — and takes about ten seconds.

That nominal 0.065 is **the same number as item 8's unmeasured 100× pixel
size**, not a coincidence of value: `provisional_transform` builds the transform
out of `um_per_px` directly. The sine measures the trap's end of it; item 8's
`PixelSize` blocks are the camera's end. Both are needed and neither is
sufficient alone.

> **TODO(human):** read the trapezoid half-extents off the GUI at 100× and put
> them in `config/tweezers/*.yaml` `trapping_range`, which has been `null` on
> purpose since 2026-08-26 for exactly this reason.

### 6. A proper focus sequence

The *instrument* half exists and the *protocol* half does not.
`config/session/focus_monitor.py` reads `ZDrive` and both cameras a few times a
second, scores each frame (Tenengrad normalised by the frame's own median, so it
measures sharpness and not brightness), and reports the Z of peak focus per
camera — with `beads`/`area`/`%ceil` alongside, because one scalar hides the
ways focus can lie. **It never writes `ZDrive`**, or anything else in
`COLLISION_DEVICES`, on purpose: the 100× Oil has 130 µm of working distance,
the stand runs no escape on a software Z move, and the Z sign convention is
unmeasured (SAFETY.md §2). The operator turns the knob; the script names the
peak afterwards.

So what is missing is not the metric — it is the sequence around it:

- **The sweep itself, per objective.** How far either side of the expected
  plane, and how slowly. A 4× and a 100× Oil do not share a search window, and
  the peak's resolution is only as good as the sweep was fine. Nothing records
  what was used.
- **Where the peak goes afterwards.** `focus_monitor.py` prints a Z; nothing
  consumes it. Handing it to PFS, or writing it back as the sample plane, is
  currently the operator retyping a number.
- **The failure case.** No peak, or two peaks (both cameras disagreeing is
  meaningful on the dual-cam path — it is a splitter/parfocality signal, not a
  focus one). The script reports; it does not adjudicate.
- **The `%ceil` interaction.** Above 95 % the peak is a lower bound rather than
  a measurement. That bound belongs in the sequence, since it couples focus
  directly to item 9's light level.

*What it cost:* not yet a loss — the two-person loop has worked every time it
was run. The cost is that `ZDrive ≈ 2959 µm` (2026-09-03, 100× with a trapped
bead, PFS `In Range`) is a *single* measured value standing in for "where the
sample is", and both collision guards in `_require_clear_of_sample` lean on it
through `SAMPLE_Z_WINDOW_UM`. A written sequence is what would let that number
be re-established on demand rather than trusted.

> **TODO(human):** the z-range and knob speed you actually sweep at 100× Oil and
> at 20×, and whether the found peak should be written back into
> `SAMPLE_Z_WINDOW_UM`'s provenance or left as a per-session note.

### 7. A safe sequence to change the objective lens

**Mostly closed 2026-09-05.** SAFETY.md §2 holds the rule, the measurement
behind it (rotating 4× → 100× Oil moved `ZDrive` **+0.000 µm** — the incoming
lens arrives wherever the outgoing one was), two sign-free guards in
`Microscope._require_clear_of_sample`, and — since KH measured the Z sign — the
operator's ordered sequence itself.

What remains is narrower: the sequence is **prose in a safety file, not
something that runs**. Nothing enforces the order, nothing records that the
post-change tweezers re-verification happened, and the two guards can only
refuse a bad write — they cannot carry out a good one.

The unresolved pieces, all already named in §2 and worth pulling into one place:
- ~~**The Z sign convention is UNMEASURED.**~~ **Resolved 2026-09-05: KH
  measured it — smaller Z is retracted**, so `Z_RETRACT_DIRECTION = -1` and
  the sequence is writable. It is now in `SAFETY.md` §2:
  `Z → 0`, rotate, `Z → 2800`, re-focus.
  ⚠ This **reversed** the guess the repository had been carrying (+Z
  retracted, inferred from a rotation at `ZDrive = 8288.740` that broke
  nothing). Under the measured convention that rotation drove the incoming lens
  ~5.3 mm *past* the sample plane, so nothing broke because nothing was there
  to hit.

  **And as of 2026-09-06 the instrument carries it too.** All six configs now
  declare `FocusDirection,ZDrive,1` — increasing Z moves toward the sample —
  where the field had been `0` = *unknown* for as long as the configs have
  existed, i.e. the measurement lived in `SAFETY.md` prose and one Python
  constant and Micro-Manager could not answer the question at all. That is the
  same failure as items 4 and 8 in a third place: **a value MM cannot answer
  is a value that has to be remembered.** `PFSOffset` stays `0`, because its
  sign has never been measured and it is also a collision device — the one
  remaining unmeasured direction on one.
- **PFS `Out of Range` authorises nothing.** It can veto a rotation, never
  permit one. Any sequence must not read it as an all-clear.
- **The change invalidates both GUI tweezers calibrations** — the GUI's px→µm
  magnification and the AOD field response — and neither is readable over TCP.
  So the sequence does not end at the nosepiece write; it ends after a known
  amplitude has been driven and measured (2026-09-03: commanded ±10.000 µm,
  measured 9.9672 and 10.0852 µm).
- **But the repository's own OT↔camera transform partly survives, by design.**
  The 2026-09-04 run measured it (§1 of
  `kb/decisions/2026-09-04-closed-loop-trapping-measured.md`) and the two
  surviving halves are surviving on purpose:
  - *Orientation* — rotation and handedness, `y` flipped because image `y` runs
    down — was confirmed by four beads in four quadrants, all trapped, all
    following the ramp home at 98.6–99.8 %. It is a property of the optical
    layout, not of magnification.
  - *Origin* — `TRAP_ORIGIN_OFFSET_UM = (-1.013, -1.015)` — is stored in **µm
    and not pixels** precisely so it "stays right at another magnification or
    ROI" (`trap_sequence.py:168`).
  - *Scale* is the half that does not survive, and it enters through
    `um_per_px` — which is item 8's number. `provisional_transform` builds both
    `b` and `p0` from it, so the objective-change sequence has to re-supply the
    pixel size **and** re-measure the trap scale (the ~10 s sine on a bead
    already in the trap, item 5) before any `TRAP_POSITION` in µm means
    anything again.
- It also invalidates the `PixelSize` presets' assumption if the intermediate
  magnification moved with it — see item 8.

*What it cost:* "**I rotated the nosepiece at Z = 8288.740 µm before being told
the rule. It did not crash, and that was luck, not clearance**" (SAFETY.md §2).
The guards exist because of that. The sequence does not yet.

### 8. Finish the pixel → µm information in every `.cfg`

**Done 2026-09-06 — all six configs now carry a filled `PixelSize` block**, the
root of the tree first so no regeneration re-inherits the gap. What is *not*
closed by that is the provenance: five of the six rows are still arithmetic,
and the two holes below are untouched by filling anything in.

| Config | `PixelSize` block |
|---|---|
| `single_cam_red_noDMD.cfg` | filled 2026-09-04 |
| `dualcam_noDMD.cfg` | filled 2026-09-06 |
| `dualcam_twocolour.cfg` | filled 2026-09-06 |
| `DMD_dualcam_LUNF.cfg` | filled 2026-09-06 — **the root parent** |
| `single_cam_blue_LUNF.cfg` | filled 2026-09-06 |
| `single_cam_red_LUNF.cfg` | filled 2026-09-06 |

*What it cost, while it was open:* on an empty block `getPixelSizeUm()` answers
**0.0** — not an error, a plausible-looking zero — so anything asking the
instrument for its own scale got nothing. Confirmed live 2026-09-06 with the
100× Oil in place. `DMD_dualcam_LUNF.cfg` was the **root of the whole tree** —
the declared parent of the other four directly, and of
`single_cam_red_noDMD.cfg` through `single_cam_red_LUNF.cfg` — so the three
blocks filled before it were fixes applied *downstream* of a parent that still
answered 0.0, and the next derived file would have inherited the gap again.
That is why it was filled first this time.

Two known holes remain in all six, and neither is closed by filling a block —
which is the point worth keeping: **the `.cfg` now answers, but it answers with
arithmetic.** Trading a loud-looking 0.0 for a plausible nominal is only an
improvement because the number is marked, and `set_pixel_size.py --audit`
prints `(measured)` or `(nominal)` per row:
- **Only the 20× row is measured** (0.32373 vs a nominal 0.325 — a real
  20.078×). The other five are exactly 6.5/M. See `data/pixel_size.yaml`.
- **The presets key on the `Nosepiece` alone and assume intermediate 1×**,
  because `IntermediateMagnification` has no `Label` lines to key on. At 1.5×
  every value is high by exactly 1.5×, and that property is **read-only over
  MM** (one property, `Magnification`, no setter) — a manual change at the
  stand. Close it with `python -m calibration.cli intermediate-mag <file>`.

This is the same general failure as item 4: an element MM cannot read is an
element whose record drifts. Here it is the intermediate magnification.

**And the trap consumes this number.** `trap_sequence.provisional_transform`
builds the whole OT↔camera map out of `um_per_px` — the matrix as
`b = (1/um_per_px) · diag(1, −1)` and the origin as
`p0 = centre + TRAP_ORIGIN_OFFSET_UM / um_per_px` — so **item 5's "scale still
nominal 0.065" and this item's unmeasured 100× pixel size are the same number**,
and a pixel size wrong by *x* % puts every `TRAP_POSITION` in µm wrong by *x* %.
The 20× row is the reason to expect that is nonzero: measured 0.32373 against a
nominal 0.325 is a real 20.078×, so the nominal magnifications are *not* exact
on this stand, and 0.065 has never been checked at all. Measuring it closes a
gate input and a targeting error at once.

> ✅ The three empty blocks were filled 2026-09-06 with
> `python config/micromanager/set_pixel_size.py <file> --objective <M> --write`
> for all six objectives, parent first. `DMD_dualcam_LUNF.cfg` is a parent — if
> its children are ever regenerated from it, re-audit rather than assume.
>
> **TODO(human):** a measured `um_per_px` for the five unmeasured objectives,
> and the intermediate magnification's actual position when each config is used.
> **Both are what the filled blocks still do not give you** — the code half is
> done and the measurement half is not.

### 9. A selection process for frame rate, exposure time, and light intensity

**The operator's process, stated by KH 2026-09-05.** It is not a formula, and
the order is the content:

1. **Frame rate first, from the purpose.** Not from the camera's capability and
   not from what the light will allow — from what the measurement needs to
   resolve. Everything downstream is bounded by the frame period this fixes.
2. **Exposure time *and* interval time, from the frame rate.** Two numbers, not
   one. Exposure is bounded above by the frame period and by the blur allowed at
   the sample's speed; the interval is the remaining gap, and it is the lever
   that sets **illumination duty independently of exposure** — the same 10 ms
   exposure at 100 fps and at 1 fps are two very different doses.
3. **Light intensity from a setup scan, not from arithmetic.** Sweep the source
   level and keep the *profile* — a LUT bracketed at both ends: **not so intense
   that it bleaches, not so dim that the analysis cannot work.** Intensity is
   the one leg of the triple that is measured on the day, against this sample,
   rather than derived.

Step 3 is the part with no home yet, and it is the interesting one, because the
LUT's two bounds **are** the tie-break the committee otherwise has to argue
about. Raising light for SNR (lenses 1 · 2) and the dose budget (lens 5) pull in
opposite directions — `01 §4` files this as a cross-lens constraint — and a
measured window between "too dim to analyse" and "too intense to survive"
replaces that argument with a lookup. If the window comes back **empty**, that
is the real result: no light level works, and something upstream has to move
(frame rate, dye, objective, binning). Step 1 does not get to be revised
silently.

The order also matches what the code already assumes. `detection.cli` takes
`--target-fps` as an **input** — its own help says *“desired frame rate, for
G9”* — never as something it computes, which is step 1 encoded as an argument.
`calibration/timestamped_capture.py` carries `requested_interval_ms` separately
from exposure and reports the achieved `Interval_ms` back, which is step 2's two
numbers already kept apart. So steps 1 and 2 are wired; step 3 is where the
record stops.

**Two different LUTs, and the difference matters — confirmed KH 2026-09-05.**
`data/light_sources.yaml` already specifies one of them and holds
`power_at_sample_mw: {}` — empty for every line — with a 30-minute power-meter
recipe in its header ("Record mW for each line × each objective × level
10/25/50/75/100%") and the blunt admission that "not a single measured output
value exists, so absolute photon-budget calculation is currently impossible."

| | what it measures | why it is needed |
|---|---|---|
| **Power LUT** | level % → mW / (W cm⁻²) at the sample plane, per line × objective | makes the setting a *physical quantity*. Metadata keeps only `Spectra-Red_Level: 10`, and a percent means nothing on another instrument (docs/03) |
| **Working LUT** | level % → usable SNR window for *this* sample and dye | what KH actually scans at setup. Sample-specific, expires when the sample does |

The working LUT is the operator's step 3 and is what gets used on the day. The
power LUT is what makes it transferable and what unblocks the absolute photon
budget. **Neither substitutes for the other** — KH confirmed the split rather
than collapsing it — and only the power one has a written procedure today. So
the deliverable for step 3 is two artifacts with different lifetimes: the power
LUT is measured once per objective and survives until the optics change, the
working LUT is measured per sample and expires with it.

*What it cost:* the triple shows up as hand-passed flags with nothing recording
the reasoning behind them —
`measure_red_bead_em1.py --intensity 50 --exposure-ms 33.33`,
`live_dualcam_view.py --cyan 3 --green 40 --exposure-ms 10`,
`focus_monitor.py --cyan 50 --green 50`. With the process above unwritten, two
runs on the same sample can pick different triples and neither is wrong on the
record. And the dose half cannot close yet regardless: lens 5 returned
**BLOCKED** on `missing.bleach_photons` on 2026-09-04 (item 1), so the "too
intense" bound of the working LUT is currently found by eye rather than
predicted.

> **TODO(human):** the scan you actually run at setup — which levels you step
> through, what you look at to call the top of the window (visible bleaching
> over N frames? a drop in tracked count?), and whether the result is worth
> keeping per sample in `kb/calibrations/` or is genuinely single-use.

### 10. A sample-limit protocol — find the edges, then keep the map

**The operator's protocol, stated by KH 2026-09-05.** Three steps, and step 1
is a safety step disguised as a convenience:

1. **Load the sample with a LOW-magnification objective in place.** A 4× or 10×
   has millimetres of working distance, so the front element cannot be reached
   by the sample or the operator's hand during loading. Contact is simply not a
   concern at that magnification — which makes **objective choice a load-time
   safety decision**, not only an imaging one. `SAFETY.md` §2 covers the Z
   direction of the same risk; this is the other half of it and is written
   nowhere.
2. **Then move the motorised stage slowly and find the sample's edges.** Follow
   the boundary and **save the positions as you go** — around 20 points is
   enough to describe it.
3. **Make a map** from those points.

What the map buys is a *measured* answer to "where is the sample", which every
later XY decision currently guesses at: grid placement, how far a trap may
reach, tiling, and whether a field near the edge is even usable.

*What it cost:* the number is already in the repository, as an assertion.
`config/session/run_wall_diffusion_grid.py` reasons its 3×3 grid out to
**"±300 µm of stage travel authorized by the operator (KH, 2026-09-04)"** — a
sentence in a docstring. Not a measurement, not a constant, not enforced
anywhere. And it **set the error bar**: 300 µm spacing is the smallest grid that
clears the 260 µm field on every pair including diagonals, nine fields put ~25 %
uncertainty on the standard error, and *"at ±200 µm only 5 positions are
clean"* — at which point three fields would put 71 % on it and the error bar
would mean nothing. So an unmeasured sample extent propagated straight into the
statistical power of the measurement, through a hand-authorised box.

Two things make this the same shape as items 7 and 8:

- **Nothing enforces the box in either direction.** `XYStage` is **not** in
  `COLLISION_DEVICES`, `Microscope` exposes no stage-motion API, and the grid
  script moves XY with `core.setXYPosition(...)` on the raw MMCore
  (`run_wall_diffusion_grid.py:236`). A boundary map is only as good as
  something that refuses to leave it.
- **The map expires like the working LUT (item 9).** It belongs to a *mount*,
  not to the instrument — so it needs the same per-sample lifetime and the same
  honest expiry, rather than aging silently the way the Splitter position did
  (item 4).

**Answered 2026-09-09 (KH)**, all five in the order they were asked:

| | Answer |
|---|---|
| **Loading objective** | **4×.** `data/objectives.yaml` gives it 20 mm of working distance at nosepiece position 0 — the front element cannot be reached during loading, and it is already the resting position |
| **What counts as the edge** | **Both, declared per map.** A real chamber part is used in separate experiments; the standing mount is unspaced, where the boundary is the drop's own contact line ([`sample-mount-geometry.md`](kb/expertise/sample-mount-geometry.md), whose scope already anticipated this). So a map carries an `edge_kind`, and the detection criterion differs by it: a glass wall is a step, a contact line is a meniscus gradient |
| **Stage speed** | **Per magnification** — so derived, not stated. Consecutive frames have to overlap or the edge is skipped between them, which fixes `v_max ≈ field × (1 − overlap) / frame period`. The field comes from the pixel size, and at 4× that is `evidence: nominal`; only 20× is measured (`data/pixel_size.yaml`) |
| **Polygon or box** | **Polygon.** The ~20 points are the measurement and the box is computable from them, so keeping only the box discards the shape. Storage does not decide it — the difference is under a kilobyte |
| **Per sample or per mount** | **Per load.** Remeasured every time a sample goes on, whatever the `edge_kind` |

**What "per load" costs, and it is not small.** The property to check stops being
"is there a map" and becomes "is this map the one for what is on the stage right
now" — and **nothing in the stack can see a sample change.** MM reports the same
coordinates before and after a swap, so this is the failure of items 4 and 8
again: a value MM cannot answer is a value that has to be remembered. The map
therefore needs a load token the operator sets when they load, and travel is
refused without one. There is no way to infer it.

**And one prerequisite is not measured.** The protocol measures at 4× and images
at 100×, but the same stage coordinate does not put the same point of the sample
at the camera centre under two objectives — that difference is the parcentric
offset, and [`kb/calibrations/objective-offsets.yaml`](kb/calibrations/objective-offsets.yaml)
records it as **`NOT MEASURED`**: only z was taken, and the note adds that "image
y runs down and that rotation has never been measured for this path". The fix has
a name and is already written —
`config/session/measure_objective_offsets.py --calibrate-xy` — it has simply not
been run.

> **TODO(human):** the frame overlap fraction the sweep should hold, and what
> the load token is in practice — a number typed at load time, a sample id, or
> something read off the chamber.

### 11. Make the Python environment discoverable, and stop rebuilding it

**Raised by KH 2026-09-05: "I don't want to install venv and uv every time."**
Half of that is a real gap and half is a rumour, and separating them is the
whole item.

**The rumour first: `uv` is not needed and never was.** It appears **nowhere in
this repository** — no `.md`, `.toml`, `.txt` or `.json` mentions it. The
install path in "Running the tests" is plain
`pip install -r requirements.txt -r requirements-mcp.txt`. `uv` is absent from
this machine and the MCP server starts anyway. Any note claiming the server
needs `uv` is false and should be deleted rather than worked around.

**The interpreter half: ✅ fixed 2026-09-06.** `.mcp.json` used to name it
outright, and that one line was two defects:

```json
"command": "C:\\Users\\Takatori lab\\venvs\\auto_microscope\\Scripts\\python.exe",
"args": ["-m", "mcp_server.server"]
```

**It carried a Windows account name**, so the server was configured for exactly
one login. And it was **the only file in the repository that knew where the venv
lived**, so every cold start re-derived it.

*What the first defect cost — and it is not "silently", which is what this
section said until now.* It failed loudly, in this session, on the macOS machine
the repository is edited from:

```text
ENOENT: Executable not found in $PATH:
  C:\Users\Takatori lab\venvs\auto_microscope\Scripts\python.exe
```

The message was clear; what was silent was the *consequence*, because a
hardware MCP server that never connects looks exactly like one that was never
configured. **That is the failure mode this repository is otherwise built
against** — the MCP section above argues at length that a refusal must be a
value rather than an error, because a model that believes a tool is broken
routes around it, and an absent server is the strongest form of that.

*What the second cost:* `python -m pytest` answered **"No module named pytest"**
on the system Python, and the venv had to be found by searching the filesystem
before the suite could run at all. A small tax, paid every time anyone or
anything starts cold.

Both are closed by [`mcp_server/bootstrap.py`](mcp_server/bootstrap.py), and
`.mcp.json` is now machine-independent:

```json
"command": "python",
"args": ["mcp_server/bootstrap.py"]
```

The bootstrap is **stdlib-only on purpose** — it is launched by whatever
`python` is on PATH, which is precisely the interpreter that does *not* have the
dependencies. It tries `$AGENTIC_MICROSCOPE_PYTHON`, then the interpreter
running it, then `$VIRTUAL_ENV`, then `.venv/` beside the repo, then
`~/venvs/auto_microscope` **named without the account**; verifies each can
actually `import mcp` before choosing it; and **refuses with the install command
on stderr** rather than handing the client an interpreter that would die inside
the MCP handshake, where the failure reads as a broken server instead of a
missing package. Diagnostics go to stderr only — stdout is the JSON-RPC channel,
and one stray `print` is indistinguishable from the malformed-server failure
above. → [`tests/test_mcp_bootstrap.py`](tests/test_mcp_bootstrap.py)

Note what was *not* wrong with the old line: the venv living outside the
repository. `~/venvs/auto_microscope` (Python 3.12.10, built 2026-08-11)
survives a clean checkout, which is a real argument for keeping it there — so
the search covers user-home locations as well as repo-local ones instead of
insisting on a `.venv/`. **It does not need recreating.**

**Still open — versions are not pinned.** Four requirement files, no lockfile.
"Do not rebuild the venv" is a hope rather than a guarantee, because a rebuild
would not reproduce the current one. Note the tension with
[`.gitignore`](.gitignore), which ignores `uv.lock` on the stated grounds that
the `requirements*.txt` bounds are deliberately loose and a committed lock
"would quietly become the real specification" — so pinning is a decision to
make, not an oversight to correct.

> **TODO(human):** whether you want the requirement files pinned so a rebuild is
> reproducible, against `.gitignore`'s argument that a lockfile would silently
> become the specification. The venv-location question is settled by the
> bootstrap: either location now works.

---

## Document map

| Document | Contents |
|---|---|
| [01 Architecture](docs/01-architecture.md) | Overall design, layers, 5 design principles, committee composition, folder structure |
| [02 Knowledge base](docs/02-knowledge-base.md) | 3-tier normalization, **three-way device wiring cross-check**, off-ledger settings, SQLite schema |
| [03 Cross-system transfer](docs/03-cross-system-transfer.md) | Current instrument ≠ past instrument. What transfers and what does not |
| [04 Decision engine](docs/04-decision-engine.md) | Decision order, photon budget / SNR / sampling / timing formulas, the 26 gates |
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
| [`photo/`](photo/) | 5 · photo-perturbation (G21–G22) | Implemented, and **computing since 2026-09-09** — power and illuminated area were measured that day, so irradiance exists at 20×. **G10 and G20 were both removed the same day** ([04 §6](docs/04-decision-engine.md), [`kb/decisions/2026-09-09-g20-saturation-removed.md`](kb/decisions/2026-09-09-g20-saturation-removed.md)); each was keyed to a per-dye constant that is empty for every dye, so neither could ever return anything but `BLOCKED` on this instrument's proprietary bead colourants. The transcript above is what it used to refuse, kept because [a refusal is still a valid result](#a-refusal-is-a-valid-result) |
| [`validity/`](validity/) | 6 · measurement validity (G11, G23–G27) | Implemented. Reviews the other lenses' verdicts, so **call it last**. Judges each `intended_quantities` entry separately — a biased MSD and a sound intensity profile can come out of one session — and checks a declared correction against a registry rather than believing it. G27 is currently the only thing that notices the committee never convened |
| [`stability/`](stability/) | 8 · mechanical & environmental (G29–G32) | Implemented, conditional on acquisitions over 30 min. **G28 (PFS lock) moved to the hardware execution stage 2026-09-10** — it read `PFS in Range` as the servo state and that property reports the coverslip. G31 (sedimentation) works today; G29 BLOCKED until a drift rate is measured; vibration and stage repeatability ungated |
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
1162 passed, 10 skipped
```

That count is **Windows**. macOS and Linux report `1161 passed, 11 skipped` —
one Windows-only segment-lifetime test in
[`tests/test_runtime_shmview.py`](tests/test_runtime_shmview.py) skips there,
so the badge's three platforms do not all print the same number.

**Which interpreter?** This is the question that cost a filesystem search on
every cold start (to-do item 11), and the answer is now printable rather than
remembered:

```bash
python mcp_server/bootstrap.py --dry-run
```

It prints the path of an interpreter that has the dependencies, or exits
non-zero naming what to install. On this instrument's PC that is the venv at
`~/venvs/auto_microscope` (Python 3.12.10, outside the repo so it survives a
clean checkout); it does not need recreating.

`pyproject.toml` puts the repository root on `sys.path`, so the bare `pytest`
and `python -m pytest` agree — before it, only the second form worked. The ten
skips are two different things. **Three are modules, not tests**: they open with
`pytest.importorskip("pymmcore_plus")` and hold 56 tests that need live
Micro-Manager access. **Seven are individual tests** in
[`tests/test_objective_offsets.py`](tests/test_objective_offsets.py), the
localisation half, which calls OpenCV through `locate_centroid` and
`locate_by_correlation`; the offset arithmetic and loop-closure tests in the
same file run everywhere, which is the half that can be wrong silently. `-rs`
names all ten and their reason in every run, so the count above cannot quietly
shrink. To run those too:

```console
$ pip install -r requirements-micromanager.txt && mmcore install
```

Four requirement files, and the split is the point: `requirements.txt` is the
1,132 tests that need nothing but numpy and pyyaml, `requirements-mcp.txt` adds
the 30 that exercise the MCP server and is in CI because it is pure Python,
`requirements-micromanager.txt` is the 56 that need a vendor device-adapter
download and is not, and `requirements-analysis.txt` is 7 localisation tests
that call OpenCV and skip without it. Measured 2026-09-07 by collecting the
suite with each optional stack hidden, not by adding the numbers up.

**Reproducing the runner's environment locally.** This venv has all four stacks,
which is why a test that reaches into an uninstalled one passes here and errors
there — it did, for three commits after `062db16`. So the absences are
emulatable rather than remembered:

```console
$ PYTEST_CI_EMULATE=ci pytest -q -rs      # what the badge runs
1162 passed, 10 skipped
$ PYTEST_CI_EMULATE=base pytest -q -rs    # requirements.txt alone
1139 collected
```

It hides `cv2` and `pymmcore_plus` two ways at once, and both are needed: an
import hook so a real `import cv2` *fails* — which is what reproduces the
breakage, rather than merely tolerating it — and `find_spec` answering `None`,
which is what lets a `requires_cv2` marker choose to skip instead of erroring
inside its own condition. Inert unless the variable is set, and an unrecognised
value refuses rather than quietly giving a full run
→ [`tests/ci_emulate.py`](tests/ci_emulate.py).

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
