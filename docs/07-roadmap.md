# 07 · Roadmap

> **Status: sketch.** The phase order and the prerequisites are settled
> proposals; there is no schedule.

One principle: **each phase has to be useful on its own.** A design that only
becomes usable once everything is finished never finishes.

---

## Phase 0 · Securing the evidence — where we are

What is blocked right now is not code but **facts**. The gates already run; they
return `BLOCKED` only because there is no input to compute from.

| Task | Output | Cost | Status |
|---|---|---|---|
| Current system MM `.cfg` | `kb/systems/current.md` | — | ✅ in hand (2026-07-03) |
| ↳ check for `Label,` lines | filter wheel / turret position names | — | ✅ done |
| NIS-Elements device list | three-way cross-check table [02 §4] | — | ✅ done (2026-08-11). EM1/EM2 camera assignment settled (EM1=Kinetix_red/EM2=Kinetix_blue), EM2 filter configuration independently confirmed, DM=CSUW1-Dichroic and CSUW1-Filter_Red/Blue=EM1/EM2 duplicates merged, FilterTurret2 · CondenserTurret · DMD physical wiring all resolved — see kb/systems/current.md |
| Parts per filter wheel position | `data/filters.yaml` | — | in hand |
| Fluorescent dye data | `data/fluorophores.yaml` | — | in hand |
| Objective barrel engravings | NA · WD · coverslip | 10 min | ✅ done (2026-08-11) — catalog cross-check (2026-08-10) + barrel cross-check (2026-08-11), user-confirmed |
| **Illumination power measured** | `power_at_sample_mw` | 30 min | **Largest effect, still the top blocker — deferred 2026-08-19 for want of a meter, and a meter is being borrowed as of 2026-08-29, so it is next once it arrives (widefield sources first; see the update below).** The original decision, kept for the record: *deliberately deferred (user, 2026-08-19): all laser power measurement happens later.* Not forgotten and not dropped; simply not the next task. Until it lands, every dose/SNR number stays relative, and gates that need `power_at_sample_mw` keep returning `BLOCKED` by design |
| Measured pixel size calibration | `ConfigPixelSize` (registered in MM2) | 30 min | ✅ in hand (Kinetix, 2025-04) |
| Disk sustained-write bandwidth | `kb/calibrations/disk-bandwidth.yaml` | 10 min | ✅ in hand (2026-08-12) — D: drive 206.8 MB/s (4GB measured). Whether it is exactly the folder MM saves into is unconfirmed — if not, re-measure. Since 2026-08-19 the gate stops letting that slide: `disk_bandwidth_path_confirmed` defaults to false, which pins every lens-3 verdict to `evidence: assumed` until someone confirms the folder |
| Camera row time | `ReadoutTimeNs / ROI height` | 5 min | ✅ in hand (2026-08-12) — `kb/calibrations/camera-readout.yaml`. The real PVCAM adapter property `Timing-ReadoutTimeNs` = 8,475,000 (ns strongly implied by the name; not yet cross-checked against a document) → row time ≈ 3531.2 ns/row (at ROI height 2400 rows). Loaded from `dual_cam_test.cfg` (PVCAM only, no NikonTi2/Mightex) rather than `DMD_dualcam.cfg` — reason in the note below |

**Measuring the light level is the biggest unlock.** That one thing opens the
absolute photon budget, makes it possible to compute exposure time from scratch,
and makes all future data transferable to another system.
→ [03 §5](03-cross-system-transfer.md)

**Deferred by decision (2026-08-19).** The user has put *all* laser power
measurement off until later, so this unlock is not the next move — do not keep
re-proposing it as the immediate step. Two consequences to hold onto: committee
verdicts that depend on absolute dose remain relative-only (Lens 5 in
particular), and the LUN-F per-line power path is blocked on its own separate
problem anyway (the FT4222H SPI word format — see
[`hardware/lunf_power.py`](../hardware/lunf_power.py) and
`kb/systems/current.md > devices_not_in_mm_config`), so measuring before that
path exists would only characterise the laser at whatever power NIS last left
it at.

**Update, 2026-08-29 — the missing precondition is arriving.** A power meter is
being borrowed (Saksham), which removes the practical half of the reason this
was deferred. The 2026-08-19 decision stands as a record of why it was not the
next task for six weeks; it is not a standing instruction to keep deferring once
the instrument is on the bench. The scoping in the paragraph above survives
intact and is what to follow: **measure the widefield sources first**
(SpectraIII, AuraIII), where the number is meaningful the moment it is taken,
and treat the confocal lines as contingent on the LUN-F per-line power path,
since without it a measurement records whatever power NIS last left the laser
at. It is now item 0 of the README's remaining work.

**The code to run once the hardware is connected is ready in
[`calibration/`](../calibration/)** (disk bandwidth, camera row time, EM1/EM2
camera discrimination, RAM burst capture) — illumination power is the only item
code cannot substitute for (a power meter measurement is required).
`calibration.disk_bandwidth` is hardware-independent and covered by tests.
`calibration.mm_live` (camera row time, EM discrimination) needs pymmcore-plus
and passes its tests against the demo camera — **2026-08-12: confirmed against
the real PVCAM adapter as well** (see the table above).

**2026-08-12 environment note**: the pymmcore-plus MM build fetched by
`mmcore install` (interface v75) lacks `Ti2_Mic_Driver.dll` (Nikon vendor SDK,
not included in the distribution), which blocked loading the `NikonTi2` adapter
— resolved by copying just that DLL from the lab's existing installation
(`C:\Program Files\Micro-Manager-2.0`). Now every device in `DMD_dualcam.cfg`
except the DMD (`MightexPolygon1000`) — stand, CSU-W1, EM1/EM2, cameras, light
sources — loads through pymmcore-plus in one go. The DMD itself still does not:
its vendor support package is pinned to interface v71 and does not match the v75
core (separate unresolved item, not urgent).

**Verification**: `python -m optics.cli check <current-system channel>` returns
`advances: YES` instead of `BLOCKED`.

---

## Phase 1 · Completing the computational lenses

All pure computation, so it can be developed and tested without hardware.
The formulas are already laid out in [04](04-decision-engine.md).

| Lens | Gates | Prereq | Output |
|---|---|---|---|
| 1 Optics | G1–G4 | — | ✅ **done** |
| 2 Detection | G5 G6 G7 G8 G9 | camera spec, row time | ✅ **done** (2026-08-11, `detection/`) |
| 3 Compute resources | G12a–c G13a–d | measured disk bandwidth | ✅ **done** (2026-08-11, `compute/`); deepened 2026-08-19 — multi-stream data rate, bit-depth-aware container, G12b frame-rate provenance, G12c container confirmation, G13d RAM-capture capacity, and the post-hoc `compute/drops.py` |
| 7 Optical tweezers | G14 | — | ✅ **gate wiring done** (2026-08-10, `trapping/`) — the dial-% → mW calibration is deferred (2026-08-19), so its verdicts stay `evidence: assumed` |

Lenses 2·3·7 all use the **same schema** as Lens 1: `Check` /
`CheckResult(margin)` / `Verdict(status, evidence, advances)` (each lens's own
`checks.py`/`gate.py`), including the `feasibility` grade. Lens 7 was the last
lens without one; it was added 2026-08-12, because without a grade the lens
could not honour [05](05-consensus-gate.md)'s rule that a verdict advances only
at `TIGHT` or better. Every gradeable check in Lens 7 is HARD, so its grade is
simply the worst hard margin.
Check each with `python -m trapping.cli check --dial 100` /
`python -m detection.cli check ...` / `python -m compute.cli check ...`.
→ [08 §0](08-optical-path-spec.md)

**Resolved 2026-08-18.** Lens 7 used to raise on any objective whose design NA
exceeded the sample medium's index — every oil objective on an aqueous sample.
That was a modelling limit reported as physics: those objectives do trap, at an
NA clipped to the medium's index by total internal reflection at the
coverslip/sample interface, and for micron beads the clipped stiffness lands
within ~3% of an index-matched objective's. `ObjectiveBeam.effective_na()` now
clips, `checks.check_effective_na` reports the three limits that ride along
(stiffness is an upper bound; spherical aberration unmodelled; depth pinned by
G17, which brings an uncorrected Faxén wall-drag bias), and the unmodelled
aberration is recorded as an assumed input so a clipped configuration cannot
report `advances`. Grounded in a user observation —
[`kb/expertise/oil-objective-trapping-in-water.md`](../kb/expertise/oil-objective-trapping-in-water.md).

**Scope decided 2026-08-19 (user).** Four things that read like gaps in Lens 7
are decisions. The roadmap should stop proposing them as next steps:

| Item | Decision |
|---|---|
| Local heating at 1064 nm | **Will not implement.** Deliberately ungated and named as such — [01 §7](01-architecture.md), [06 D6](06-pitfalls.md) |
| Faxén wall-drag correction | **Will not correct by formula.** In-situ power-spectrum calibration at the working height absorbs it instead — [`kb/expertise/oil-objective-trapping-in-water.md`](../kb/expertise/oil-objective-trapping-in-water.md) |
| dial-% → mW calibration | **Deferred**, under the same 2026-08-19 decision that defers all laser power measurement (Phase 0 above). Until it lands `LaserCalibration.points` stays empty and every trapping verdict is `evidence: assumed` |
| Non-water media viscosity | **Out of scope for now.** Water only. The CLI already refuses to default a viscosity for a non-water medium, and `--viscosity-pa-s` takes a measured value if an ATPS experiment ever needs one |

→ [`kb/decisions/2026-08-19-lens-7-scope.md`](../kb/decisions/2026-08-19-lens-7-scope.md)

What genuinely remains is wiring, not physics. G14's `f_s ≥ 10·f_c` comparison
is only verified when `--detector-fps` is passed by hand; without it the lens
prints an informational note and does not block the verdict. Lens 2
(`detection/`, 2026-08-11) already computes the realizable frame rate (`max_fps`
in `check_frame_rate`), but the two CLIs are not connected — a human reads the
Lens 2 output and hands it to `trapping.cli check --detector-fps`. Automatic
wiring belongs to Phase 3 (committee orchestration).

Also:
- **Difficulty grade + sensitivity analysis**
  ([05 §3–4](05-consensus-gate.md)) — margin is already in Lens 1; what remains
  is `data/interventions.yaml` and the improvement ranking
- ~~**Tweezers intermediate regime**~~ — done. At `a/λ ~ 1` neither Rayleigh nor
  ray optics is valid, and `trapping.gate` returns `BLOCKED` there rather than
  an approximation (`goa.ray_optics_regime`, gated on the Mie size parameter
  x < 0.3 / x > 10)
- **ℓ_c diffraction-limit gate** (new, 2026-08-12) — if
  `characteristic_scales.length` in `kb/samples/<system>.md` is smaller than
  `σ_PSF`, the structure cannot be resolved directly even if sampling passes.
  A check Lens 2 (G5) does not have today.
  → [04 §2](04-decision-engine.md)

**Verification**: feed in conditions actually used in the past and the gates
point out that session's problems on their own (647 exposure 500 ms, duty 88%,
despeckle).

---

## Phase 2 · Building the knowledge base

| Task | Output |
|---|---|
| MM metadata indexer (1.4 + 2.0) | `kb/envelope.sqlite`, 2,343 acquisitions |
| System fingerprint → automatic generation classification | `system_id` |
| Folder-name parser | `name_*` columns |
| tail parsing → `measured_fps`, drop detection | **measured, not requested** — ✅ the detector itself is done (`compute/drops.py`, 2026-08-19); what remains is running it over the archive and landing the result in SQLite |
| Sidecar schema + generator | `acquisition.yaml` |
| Draft sample-system recipes | `kb/samples/*.md` (the `characteristic_scales` (τ_c, ℓ_c) field is now mandatory → [02 §8](02-knowledge-base.md)) |

**First by-product**: run drop detection across the whole archive and enumerate
which sessions are contaminated. This delivers value right now, with no new
experiments.

**Verification**: "show me precedents that tracked with 647 in ATPS" → answered
by SQL, with each precedent's physical quantities and known defects alongside.

---

## Phase 3 · The agent layer

This is where it becomes a "chatbot".

```
D:\experimentalist\
├── CLAUDE.md                      always-loaded operating instructions
└── .claude\
    ├── skills\
    │   ├── scope-setup\           setting recommendation (main workflow)
    │   ├── knowledge-capture\     expertise capture [09]
    │   └── system-onboard\        build the KB on receiving a new .cfg
    └── agents\
        ├── sample-optics.md       Lens 4   ← draft in place
        ├── photo-perturbation.md  Lens 5   ← draft in place
        ├── measurement-validity.md Lens 6  ← draft in place
        └── mechanical-env.md      Lens 8   ← draft in place
```

- The computational lenses (1·2·3·7) run in code first, and **their results are
  the input to the judgment lenses.** The LLM never makes up the numbers itself
- Committee orchestration + deadlock handling ([05 §6](05-consensus-gate.md))
- The expertise capture loop ([09 §3](09-knowledge-capture.md))
- Teaching mode ([09 §5](09-knowledge-capture.md))
- **A declared tool surface**, so the model calls this repository instead of
  reading a CLI's help text — half built, see below

**Half of the tool surface exists, 2026-08-31.**
[`mcp_server/`](../mcp_server/) exposes the **two hardware paths** — tweezers and
piezo — as 9 MCP tools in four tiers (`plan` · `write` · `read` · `move`), each
tier declared in the tool's own MCP annotations. It was built hardware-first by
decision: those two are the subsystems with no abstraction at all, so if a tool
surface can go over them honestly the Micro-Manager path is the smaller version
of the same job. 30 tests, and CI runs them.

Two properties carried over from the gates, because an MCP client is a model and
not a person at a prompt. **A refusal is a value, not an exception** — an MCP tool
that raises reads as *this tool is broken*, and a model that believes a tool is
broken routes around it, so `advances: false`, `check: REFUSED`, `refused: true`
and `available: false` all arrive as results with their reasons and with what
would have happened. And **nothing in the `plan` tier recomputes anything**: each
tool calls the entry point `config/`'s own scripts call, so a tool and a script
that disagree is a bug rather than a difference of opinion.

**What remains is the larger half: the eight lenses.** Each lens's CLI would have
to grow a `--json` — two of eight have one — and hand its `argparse` parser over
as the tool schema, so the CLI and the tool surface cannot drift apart. That is
the piece that would let a model run the committee rather than only reach the
instrument, and it is not started.
→ [`kb/decisions/2026-08-31-mcp-hardware-server-scope.md`](../kb/decisions/2026-08-31-mcp-hardware-server-scope.md)

**Verification**: a junior says "I want to track 647 in ATPS" — and out comes
questions → computation → committee → difficulty grade → a setting proposal with
its basis and its failure signatures.

**Verification of the tool surface** is narrower and separate: the same verdict,
reached by a model calling the tools, matches the one the CLIs print. For the
hardware half that is the next hardware task — see the note at the end of
[Phase 5](#phase-5--automating-microscope-operation).

---

## Phase 4 · Experiment planning

Move up from settings to experiment design. One more committee joins:
**the experiment-planning perspective** (hypothesis → measured quantity →
required precision → statistical design).

The per-subsystem committee asks "will this setting work"; the planning
committee asks "does this experiment answer the question". Different stages, so
separate gates.

- **Secure τ_c · ℓ_c** (measure by preference; otherwise theoretical estimate +
  `evidence: assumed`) — the first action of this committee and the input to the
  per-subsystem committee. Recorded in `characteristic_scales` in
  `kb/samples/*.md` → [04 §1](04-decision-engine.md) ①'
- Control and replicate design
- Measured quantity → required precision, worked backwards
- Connect to the analysis pipeline in `D:\codes` (Lens 6 already references it)
- Protocol document generation

---

## Phase 5 · Automating microscope operation

**Do not start before Phase 0–3 are finished.** Automatically pushing unverified
settings into the instrument is dangerous.

**Fact check (2026-08-10)**: every instrument appearing in this dossier
(microscope stand, confocal, light sources/lasers, DMD, optical tweezers, piezo
stage) is Python-controllable, confirmed verbally by the user — one precondition
for starting this Phase is resolved.

**Control interface decision (2026-08-11)**: this project **does not use the
NIS-Elements control path** — every device registered in MM is controlled through
pymmcore-plus only. The DMD (MightexPolygon1000) had its registration confirmed
directly against a measured MM `.cfg` on the microscope PC
(`kb/systems/current.md > dmd`). Devices that are not registered in MM and were
previously recorded as "NIS-Elements only" — the LUN-F-XL laser combiner,
CSUW1-Dichroic/Splitter/EM1 — cannot go through the NIS path under this
decision, so **how to reach them through pymmcore-plus (a separate path: direct
SDK, serial, etc.) becomes a new task** — to be picked up after Phase 0–3, as
before.

**LUN-F direct connection — deferred to a later task (2026-08-20).** Getting the
LUN-F talking to the PC directly is proving hard enough that it is no longer the
next thing to work on. Deferred, not abandoned. State at the moment of
deferral, so it can be resumed without re-deriving it:

- **on/off (blanking) already works** — NI PCIe-6323 digital lines
  `Dev1/port0/line2/4/6/8`, MM's stock NIDAQ adapter,
  `config/micromanager/DMD_dualcam_LUNF.cfg`.
- **per-line power does not** — reachable over the FTDI FT4222H, but Nikon does
  not document the DAC word format, so `set_power()` refuses by design.
- **untried next move**: cable the chassis straight over USB-B; only fall back
  to a USBPcap capture if that turns up nothing.
  **2026-08-29: the cable has arrived**, so this is no longer deferred for want
  of hardware. First question is whether the chassis enumerates at all;
  discovery stays read-only (enumerate and read descriptors, no `LASER_ON`, no
  guessed DAC byte). It is item 0b of the README's execution boundary, and it
  gates the confocal half of the power measurement.
  → [`hardware/lunf_power.py`](../hardware/lunf_power.py),
  `kb/systems/current.md > devices_not_in_mm_config`

**Interim plan: verify everything except the confocal laser first (2026-08-20).**
Rather than wait on the LUN-F, check that the rest of the system behaves
correctly. Two things make this a clean split rather than a compromise:

1. The confocal laser and the epi-fluorescence lamps are **mutually exclusive
   anyway** — FilterTurret1's cube (`MXR00724-DM`/`-EM`) is built for the LED
   bands, not the laser lines (`kb/systems/current.md > light_paths >
   mutual_exclusions`). Widefield and transmitted-light work never wanted the
   laser on, so nothing is being worked around.
2. Everything in those paths is already reachable: Ti2-E stand and its children
   (Nosepiece, FilterTurret1, CondenserTurret, LightPath,
   IntermediateMagnification, LappMainBranch1, PFS), both Kinetix cameras,
   SpectraIII/AuraIII, and the DMD are all MM-registered and load under
   pymmcore-plus. The Splitter is the one element in these paths that is not —
   it stays a manual step.

**"Excluding confocal" means without laser excitation — not without the
CSU-W1.** The CSU-W1 optics cannot be excluded even if we wanted to:
`CSUW1-Dichroic` is always on and `EM1`/`EM2` always sit in front of the
cameras, in every path including transmitted light. So those three get exercised
by this work regardless, which is useful — they are MM-registered and confirmed
live (2026-08-12), as are `CSUW1-Bright`, `CSUW1-Port`, and `CSUW1-Shutter`.

Scope, then:

| In scope now | Path | Reachability |
|---|---|---|
| Widefield epi (SpectraIII, AuraIII) | `widefield-spectra3` · `widefield-aura` | MM |
| Transmitted light (DiaLamp, condenser BF/DF, polarizer/analyzer) | `transmitted-light` | condenser in MM; pol/analyzer manual |
| Objectives, FilterTurret1, LightPath, intermediate mag, PFS | shared | MM |
| Cameras ×2, EM1/EM2, CSUW1-Dichroic, CSUW1-Bright/Port/Shutter | shared | MM |
| DMD pattern illumination | `widefield-spectra3` | MM |
| Piezo stage | — | own DLL path (`hardware/piezo_stage.py`) |
| Optical tweezers | `optical-tweezers` | own TCP path |
| LappMainBranch1 (couples Aura in / DMD share) | shared | MM — `Device,LappMainBranch1,NikonTi2` in `DMD_dualcam_LUNF.cfg` |
| Splitter | shared | **manual only** — no `Device,` line in any config here |

What this deliberately cannot settle, so it does not get claimed later: any
confocal channel plan end to end, per-line laser power, and whether the
mutual-exclusion constraint holds in practice. Those wait on the LUN-F.

In stages:

| Stage | Scope | Safeguard | Status |
|---|---|---|---|
| 5a | **Read** state (pymmcore-plus) | hardware untouched | built 2026-08-26 |
| 5b | Show a **comparison** of recommendation vs current state | ″ | built 2026-08-26 |
| 5c | **Generate** an MM ConfigGroup preset (not applied) | human applies it | built 2026-08-26 |
| 5d | **Apply** after human confirmation | confirmation required · revertible | built 2026-08-26 |
| 5e | Run the acquisition + live gate monitoring | abort on anomaly | not started |

**5a–5d built 2026-08-26** — [`hardware/microscope.py`](../hardware/microscope.py),
driven by [`config/micromanager/verify_config_control.py`](../config/micromanager/verify_config_control.py)
(`--read` = 5a+5b, `--propose` = 5c, `--roundtrip` = 5d). Writes are gated by three
independent switches, all default off: `allow_write`, `allow_motion`
(Nosepiece/ZDrive/PFSOffset — glass into glass), `allow_laser` (LUNF-Blanking).
`check_config_file()` refuses any `.cfg` declaring `NIDAQAO-Dev1/ao2` before it
loads, which is the piezo hazard below.

Verified against the bundled demo config on macOS/arm64 only — `mmcore install` has
no Apple-Silicon nightly, so **the real NikonTi2/PVCAM/CSUW1 adapters are still
unexercised**. Same surrogate and same limit as `calibration/mm_live.py`: MMCore
semantics confirmed, per-adapter behaviour not. Running `--read` on the microscope
PC closes it — remember the `Ti2_Mic_Driver.dll` copy.
→ [`kb/decisions/2026-08-26-microscope-config-control.md`](../kb/decisions/2026-08-26-microscope-config-control.md)

MM2 is settled, so the `.cfg` ↔ preset round trip is possible as planned.
→ [08 §7](08-optical-path-spec.md)

**The piezo** is outside MM, so it needs its own path. To include it in the
automation, either (a) register it as an MM device, (b) integrate with a separate
program, or (c) leave it a manual step and record it in the sidecar. (c) was the
default — **and (b) got much more attractive on 2026-08-26**: the NPC-D
controller turns out to have a **hardware waveform generator** (`function.*` —
upload samples, set count and iterations, start/stop/pause/unpause, read state),
which the vendor's own examples describe as building "simple raster profiles",
plus `snapshot.*` triggered capture. So the piezo can hold a trajectory in
hardware like the AOD trap loop does, and unlike the tweezers **its state is
readable**, so a commanded trajectory can be verified. First established
offline from the vendor DLL, then **settled on the controller itself**
(2026-08-27) —
[`reference/npcd-command-set.md`](../reference/npcd-command-set.md) is now 414
names read over COM4, and the `function.waveform-generator.*` and
`function.waveform-builder.*` families were among those the DLL route could not
see at all
([`scope`](../kb/decisions/2026-08-29-device-discovery-scope.md)); sample
generation in
[`hardware/piezo_waveform.py`](../hardware/piezo_waveform.py); confirm on the
controller with
[`config/piezo/verify_piezo_commands.py`](../config/piezo/verify_piezo_commands.py).
Uploading still refuses by design until the argument layout of
`function.waveform.data.set` is read off the DLL.
→ [`kb/decisions/2026-08-26-piezo-waveform-generator.md`](../kb/decisions/2026-08-26-piezo-waveform-generator.md)

**Running all three at once** is scoped 2026-08-26 too. The drivers stay
one-per-file; [`hardware/orchestrator.py`](../hardware/orchestrator.py) adds only
the shared pieces — one monotonic clock, a latency log, a camera arbiter, and the
setup phases — and opens no device. Threads rather than processes: all three
drivers block inside C or I/O and release the GIL, and threads give the shared
variables for free. **The host clock is not the experiment clock**: preload
hardware-timed behaviour per subsystem (AOD trap loop · NIDAQ sequencing ·
camera), trigger from one edge, and use the host only to orchestrate and log.
Measured this session: `getProperty` median 1 µs (n=2000, demo adapter); the
tweezers TCP and piezo DLL round trips are still unmeasured —
[`config/session/measure_latency.py`](../config/session/measure_latency.py) takes
them read-only.
→ [`kb/decisions/2026-08-26-parallel-control-architecture.md`](../kb/decisions/2026-08-26-parallel-control-architecture.md)

**The tweezers** are outside MM too, and scoped 2026-08-26: direct TCP for setup
and quasi-static placement, generated `.tpf` patterns for anything whose *timing*
enters the result — the trap loop clocks a pattern in hardware at up to 100 kHz,
while TCP is host-timed with unmeasured jitter and no readback of any kind to
check it against. Built the same day: `.tpf` writer and trap-loop timing model in
[`hardware/tweezers_patterns.py`](../hardware/tweezers_patterns.py), drive
planning in [`hardware/tweezers_drive.py`](../hardware/tweezers_drive.py), and
[`config/tweezers/run_pattern.py`](../config/tweezers/run_pattern.py)
(`--plan` offline · `--write` emits the `.tpf` · `--run` sends TCP). The manual's
worked examples are reproduced in the tests; nothing has been run against the GUI
yet. The one structural gap: per-trap **wait states**, the vendor's mechanism for
slow driven motion, are GUI-only — so the shape is a GUI-built project template
loaded over `LOAD_PROJECT`, with patterns and everything else generated per
experiment from Python. `plan()` returns `BLOCKED` while the calibrated trapping
range is unrecorded, because an oversized pattern is clipped silently.
→ [`kb/decisions/2026-08-26-tweezers-pattern-vs-direct.md`](../kb/decisions/2026-08-26-tweezers-pattern-vs-direct.md)

*(Two dates in that paragraph have since moved: "nothing has been run against
the GUI yet" was true until 2026-08-27, when a 1 Hz ±10 µm sine drive ran on
Trap 1 with a host-timed 2 s breakpoint hold — and wait states turn out to be
GUI-only over *TCP* only, since the GUI's embedded Python writes them.
→ [`kb/decisions/2026-08-27-tweezers-first-light-measured-limits.md`](../kb/decisions/2026-08-27-tweezers-first-light-measured-limits.md))*

**Both of these now have an MCP surface, 2026-08-31.**
[`mcp_server/`](../mcp_server/) puts the piezo and the tweezers behind 9 MCP
tools, which is the same two paths this section has been scoping and the reason
they were chosen first ([Phase 3](#phase-3--the-agent-layer)). It changes nothing
about the drivers underneath; it is a declared interface over them, so a model
reaches the instrument through the same entry points
[`config/tweezers/run_pattern.py`](../config/tweezers/run_pattern.py) and
[`config/piezo/verify_piezo_commands.py`](../config/piezo/verify_piezo_commands.py)
already use. The two moving tools (`tweezers_run`, `piezo_move`) are refused by
default, and `tweezers_run` needs `allow_laser` as well as `allow_motion`.

**It has not reached a device, and that is the next hardware task.** The vendor
DLL is not on the working PC and the Tweez GUI is not listening on it, so the
`read` and `move` tiers have been exercised only along their refusal and
unavailable paths — the claim today is *the interface is correct*, not *the
interface works*. Three checks, in this order:

| # | Check | Why here |
|---|---|---|
| 1 | `piezo_read_state` against `sim:/NPC6330`, then COM4 | The DLL's own simulator, so nothing can be hurt. If the identity, channels and travel do not match what `verify_piezo_commands.py` prints, the tool is not the thin wrapper it claims to be — which is the real risk, not a crash |
| 2 | `piezo_move` on `sim:` with `AGENTIC_MICROSCOPE_ALLOW_MOTION=1` | The one path with no test coverage, on a device that cannot be damaged |
| 3 | `tweezers_probe` with the GUI live | `reachable: true` with a status is the whole claim; `tweezers_run` stays refused |

**The piezo goes first because of the asymmetry this section already found.** Its
state is readable and it has a simulator, so a commanded position can be checked
against a measured one. The tweezers have neither — no trap readback over TCP and
no simulator — so a tool there can be checked only against the GUI by eye. Same
contrast as the two first-light notes of 2026-08-27, and it is why the order is
not arbitrary.

**One repair belongs with this trip to the bench.**
[`hardware/optical_tweezers.py`](../hardware/optical_tweezers.py) has no safety
switch of its own, unlike `hardware/microscope.py` and
`hardware/piezo_stage.py`: its constructor opens the socket and all 28 commands
including `laser_on()` are directly callable. First light armed the laser on a
typed confirmation *in the calling script*, which is why the gap never showed.
Today `mcp_server/switches.py` is the only brake in that path. The switch belongs
in the driver — where the other two put theirs, and where MHS puts device safety
limits ([`mhs-integration.md`](mhs-integration.md)) — and it changes six call
sites, which is why it was not done as a side effect of adding the server.
→ [`kb/decisions/2026-08-31-mcp-hardware-server-scope.md`](../kb/decisions/2026-08-31-mcp-hardware-server-scope.md)

---

## Phase 6 · Joining the simulation agent

**Do not start before Phase 4.** This phase feeds the experiment-planning
committee and consumes what it defines; without it a computed τ_c has nowhere to
land.

The counterpart is
[**Brownian-Dynamics Agent**](https://github.com/kyu-softmatter/Brownian-Dynamics-Agent)
— the same architecture pointed at the integrator instead of the instrument, and
built from the same lessons. The case for joining them, with the physics numbers
behind it, is in the README:
→ [Future work](../README.md#toward-a-model-to-experiment-loop).
What follows is only what would have to exist **here**.

### The interface is a quantity, not an API

Nothing is gained by importing each other's modules; two repositories that share
code share one bug surface instead of producing two independent verdicts. What
crosses is a serialized physical quantity with its provenance and its tier
attached — the same shape both sides already store internally.

| What crosses | Direction | Consumed by | Today |
|---|---|---|---|
| τ_c · ℓ_c · `D` · κ | sim → scope | ①' and then G5 · G8 · G11 · G14 | a human estimate, `evidence: assumed` |
| predicted effect size and its tolerance | sim → scope | Phase 4 planning: required precision → §4 photon count | not represented at all |
| measured `T`, size distribution, salt, ζ | scope → sim | its SI specification stage, closing tier-1 *choices* | not exchanged |
| the bias ledger for the intended quantity (G23) + the Savin–Doyle terms (§5) | scope → sim | its validation stage — added to the prediction, not subtracted from the data | not exchanged |
| achievable localization precision · frame rate · duration | scope → sim | its design-power check: *can this design decide this item at all?* | not exchanged |

### Preconditions, in order

1. **A shared quantity serialization.** Both sides speak SI with a provenance
   and a tier already; what is missing is one file format for *"particle
   diameter, measured, tier 1, ±3 %"* that both can read and neither can strip
   the tier off.
2. **A provenance kind for computed values.** `measured` and `assumed` are the
   only two tiers here ([`kb/literature/`](../kb/literature/)), and a simulated
   τ_c is neither. It needs its own, with the simulation's own gate verdict as
   its falsifier.
3. **`kb/samples/`**, from Phase 4 — the place `characteristic_scales` lands
   whether it was measured or computed.
4. **Sealed predictions on their side.** Their item 1, not ours: an unsealed
   prediction handed to an instrument produces an experiment designed around a
   post-hoc rationalization.
5. **The wiring**, which is small once 1–4 exist.

### What this phase must not do

- **A simulated number must never set `evidence: measured`.** Same rule as
  [`kb/literature/`](../kb/literature/), and for a sharper reason: if a computed
  threshold can advance a verdict, the loop closes on itself — the simulation
  supplies the threshold, the gate clears against it, and the experiment
  confirms the simulation that designed the experiment.
- **No shared code**, per the interface note above.
- **No claim that a mismatch is physics** until the bias ledger for that
  quantity is clean. Lens 6 already judges each `intended_quantities` entry
  separately, which is the granularity a comparison against simulation needs.

---

## Dependencies

```
Phase 0 (facts) ─────┬─────────────────────────▶ prerequisite for everything
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
Phase 1                    Phase 2
  computational lenses       knowledge base
   └─ can be developed        └─ possible from the archive
      without hardware           alone; can start now
        │                         │
        └────────────┬────────────┘
                     ▼
              Phase 3 (agents)
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
  Phase 4 (planning)      Phase 5 (operation automation)
        │                         │
        └────────────┬────────────┘
                     ▼
        Phase 6 (join the simulation agent)
         └─ also waits on the other repo:
            sealed predictions, and a shared
            quantity vocabulary
```

**Phases 1 and 2 can run in parallel, and both proceed substantially without
Phase 0.** What can be done right now: the archive indexer and drop detection.

---

## Three things that pay off right now

Doable before Phase 0 is finished, and each useful independently.

1. **Archive drop detection** — enumerate contaminated sessions from
   `ElapsedTime` differences. Immediately re-evaluates how much to trust
   existing analysis results.
   **✅ done (2026-08-20)**: `python -m compute.cli scan "D:\data"
   --contaminated-only`, 2,353 acquisitions, 32 GB, ~25 min, no hardware and no
   Phase 0 input. Result: **1,234 clean · 227 contaminated · 203 truncated ·
   892 skipped** (the skips are single- and two-frame snapshots, which cannot
   carry a cadence estimate). 36 acquisitions are both contaminated and
   truncated, so the distinct total is **394 of the 1,461 analysable
   acquisitions — 27%.** The ATPS interface-velocity set
   (`vel0.5um-s_..._{DEX2PEG,PEG2DEX}_...`) is the concentration: dozens stopped
   at 500–1200 of a planned 10,000, several also dropping frames. Both MM schema
   generations parse. Details and the file list:
   [`kb/decisions/2026-08-19-lens-3-hardening.md`](../kb/decisions/2026-08-19-lens-3-hardening.md)
2. **Despeckle impact assessment** — determine how much the post-processing
   actually affected quantitative analysis of the data taken with it on
3. **Duty cycle audit** — decide whether the motion blur bias in microrheology
   sessions can be corrected retroactively with Savin-Doyle
