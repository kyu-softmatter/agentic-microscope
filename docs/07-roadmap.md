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
| **Illumination power measured** | `power_at_sample_mw` | 30 min | **Largest effect, still the top blocker — but deliberately deferred (user, 2026-08-19): all laser power measurement happens later.** Not forgotten and not dropped; simply not the next task. Until it lands, every dose/SNR number stays relative, and gates that need `power_at_sample_mw` keep returning `BLOCKED` by design |
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
