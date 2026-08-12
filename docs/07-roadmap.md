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
| **Illumination power measured** | `power_at_sample_mw` | 30 min | **Largest effect, the only remaining top blocker** — power-meter measurement, still to be done |
| Measured pixel size calibration | `ConfigPixelSize` (registered in MM2) | 30 min | ✅ in hand (Kinetix, 2025-04) |
| Disk sustained-write bandwidth | `kb/calibrations/disk-bandwidth.yaml` | 10 min | ✅ in hand (2026-08-12) — D: drive 206.8 MB/s (4GB measured). Whether it is exactly the folder MM saves into is unconfirmed — if not, re-measure |
| Camera row time | `ReadoutTimeNs / ROI height` | 5 min | ✅ in hand (2026-08-12) — `kb/calibrations/camera-readout.yaml`. The real PVCAM adapter property `Timing-ReadoutTimeNs` = 8,475,000 (ns strongly implied by the name; not yet cross-checked against a document) → row time ≈ 3531.2 ns/row (at ROI height 2400 rows). Loaded from `dual_cam_test.cfg` (PVCAM only, no NikonTi2/Mightex) rather than `DMD_dualcam.cfg` — reason in the note below |

**Measuring the light level is the biggest unlock.** That one thing opens the
absolute photon budget, makes it possible to compute exposure time from scratch,
and makes all future data transferable to another system.
→ [03 §5](03-cross-system-transfer.md)

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
| 3 Compute resources | G12 G13 | measured disk bandwidth | ✅ **done** (2026-08-11, `compute/`) |
| 7 Optical tweezers | G14 | — | ✅ **gate wiring done** (2026-08-10, `trapping/`) — only the measured calibration remains |

Lenses 2·3·7 all use the **same schema** as Lens 1: `Check` /
`CheckResult(margin)` / `Verdict(status, evidence, advances)` (each lens's own
`checks.py`/`gate.py`). Lenses 2 (`detection/`) and 3 (`compute/`) use Lens 1's
full schema including the `feasibility` grade. Only Lens 7 still has no
`feasibility` (it has fewer kinds of check than Lens 1, so there is not enough
basis for a grade table) — revisit when a SOFT/BIAS-flavored check is eventually
added to Lens 7.
Check each with `python -m trapping.cli check --dial 100` /
`python -m detection.cli check ...` / `python -m compute.cli check ...`.
→ [08 §0](08-optical-path-spec.md)

Remaining gaps in Lens 7 (as of 2026-08-10): no **measured** dial-% → mW
calibration points (`LaserCalibration.points` is empty, so evidence always comes
out assumed); medium viscosity only has a temperature-interpolation table for
water, other media such as ATPS unsupported; G14's `f_s ≥ 10·f_c` comparison can
only be verified optionally, through the `--detector-fps` parameter (without it,
only an informational note is printed; it does not block the overall verdict).
Lens 2 (`detection/`, 2026-08-11) now computes the realizable frame rate
(`max_fps` in `check_frame_rate`), but the two CLIs are not yet wired together
automatically — a human has to read the Lens 2 output and hand it to
`trapping.cli check --detector-fps`. Automatic wiring belongs to Phase 3
(committee orchestration).

Also:
- **Difficulty grade + sensitivity analysis**
  ([05 §3–4](05-consensus-gate.md)) — margin is already in Lens 1; what remains
  is `data/interventions.yaml` and the improvement ranking
- **Tweezers intermediate regime** — at `a/λ ~ 1` neither Rayleigh nor ray
  optics is valid. Do not answer with an approximation; return `BLOCKED`
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
| tail parsing → `measured_fps`, drop detection | **measured, not requested** |
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
        └── mechanical-env.md      Lens 8
```

- The computational lenses (1·2·3·7) run in code first, and **their results are
  the input to the judgment lenses.** The LLM never makes up the numbers itself
- Committee orchestration + deadlock handling ([05 §6](05-consensus-gate.md))
- The expertise capture loop ([09 §3](09-knowledge-capture.md))
- Teaching mode ([09 §5](09-knowledge-capture.md))

**Verification**: a junior says "I want to track 647 in ATPS" — and out comes
questions → computation → committee → difficulty grade → a setting proposal with
its basis and its failure signatures.

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

In stages:

| Stage | Scope | Safeguard |
|---|---|---|
| 5a | **Read** state (pymmcore-plus) | hardware untouched |
| 5b | Show a **comparison** of recommendation vs current state | ″ |
| 5c | **Generate** an MM ConfigGroup preset (not applied) | human applies it |
| 5d | **Apply** after human confirmation | confirmation required · revertible |
| 5e | Run the acquisition + live gate monitoring | abort on anomaly |

MM2 is settled, so the `.cfg` ↔ preset round trip is possible as planned.
→ [08 §7](08-optical-path-spec.md)

**The piezo** is outside MM, so it needs its own path. To include it in the
automation, either (a) register it as an MM device, (b) integrate with a separate
program, or (c) leave it a manual step and record it in the sidecar. (c) is the
default.

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
```

**Phases 1 and 2 can run in parallel, and both proceed substantially without
Phase 0.** What can be done right now: the archive indexer and drop detection.

---

## Three things that pay off right now

Doable before Phase 0 is finished, and each useful independently.

1. **Archive drop detection** — enumerate contaminated sessions from
   `ElapsedTime` differences. Immediately re-evaluates how much to trust
   existing analysis results
2. **Despeckle impact assessment** — determine how much the post-processing
   actually affected quantitative analysis of the data taken with it on
3. **Duty cycle audit** — decide whether the motion blur bias in microrheology
   sessions can be corrected retroactively with Savin-Doyle
