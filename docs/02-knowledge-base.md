# 02 · Knowledge base

> **Status: sketch.** The schema and structure are settled proposals; the
> contents get filled in once the current system's `.cfg` arrives.

The structure for storing knowledge about existing systems **persistently** so
that later experiment planning and execution can use it. It has to satisfy
three things: a human can open and fix it, an agent can query it, and "why this
value" stays traceable.

---

## 1. Storage layout

```
kb\
├── systems\                    one microscope = one file
│   ├── legacy-nikon-prime95b.md      old setup (for reading the archive)
│   ├── current.md                    current system dossier
│   └── _template.md
│
├── samples\                    imaging recipes per sample system
│   ├── atps-dextran-peg.md
│   ├── actin-network.md
│   ├── liquid-crystal-5cb.md
│   └── active-janus-colloid.md
│
├── decisions\                  recommendation → execution → outcome log (learning loop)
│   └── 2026-08-08-atps-647-tracking.md
│
├── calibrations\               measured values. date and measurer mandatory
│   ├── camera-readout.yaml     ✅ measured 2026-08-12
│   ├── disk-bandwidth.yaml     ✅ measured 2026-08-12
│   ├── illumination-power.yaml planned — the top blocker
│   └── pixel-size.yaml         planned; values currently live in systems/current.md
│
├── expertise\                  expertise captured from conversation → 09
│
├── literature\                 published values a gate needs and nobody here has
│   ├── README.md               measured. Always `evidence: assumed`, so they let a
│   └── _template.md            gate compute instead of BLOCK but never let a
│                               verdict advance. Reasoning in the README, fill-in
│                               form in _template.md; each entry is a placeholder
│                               built to be replaced by a calibration
│
└── envelope.sqlite             quantitative index of the 2,343 acquisitions (generated)
```

**Only markdown + SQLite.** Why no vector DB: embedding search cannot explain
"why was this precedent selected," and it cannot trace back the cause of a bad
recommendation. Precedent search runs on explicit SQL conditions (dye ·
objective · timescale · sample system).

---

## 2. 3-tier normalization

Detail for [01 §3 Principle 2](01-architecture.md).

The tier-3 entries and how each is derived:

| Physical quantity | Formula | Required input | Today |
|---|---|---|---|
| Effective pixel size | `p_sensor·B/(M_obj·M_int)` | sensor pitch, magnification | computable |
| Excitation band | source line × excitation filter × dichroic | spectral curves | partial |
| Emission band | dichroic × emission filter | spectral curves | **missing** |
| Irradiance at the sample | `P/A` | **power-meter measurement** | **missing** |
| Total photon dose | `irradiance × t_exp × N_frames` | the above + exposure | **missing** |
| Measured frame rate | `(N−1)/Δt_total` | tail parsing | computable |
| Collection solid angle | `(1−cosθ)/2` | NA | NA unverified |

**Three entries are empty, so transfer between systems is impossible today.**
→ [03](03-cross-system-transfer.md)

---

## 3. System dossier

One `kb/systems/<id>.md` file describes one microscope.
YAML front matter (machine-readable) + markdown body (human-readable).

```yaml
---
id: current
status: current            # current | legacy | planned
fingerprint: <device-label set + camera chip/serial hash>
sources:                   # what this dossier was derived from
  - {kind: mm_config,  path: ..., date: 2026-08-XX}
  - {kind: nis_export, path: ..., date: 2026-08-XX}
  - {kind: datasheet,  part: ..., }
  - {kind: calibration, path: kb/calibrations/..., date: ...}

stand:      {vendor: Nikon, model: ?, tube_lens_mm: 200, autofocus: PFS}
cameras:    [{ref: data/detectors.yaml#<key>}]    # a list — the current system has two Kinetix
objectives: [{turret: 1, label: ..., mag: ..., na: ..., immersion: ..., verified: false}]
filters:    [{turret: 1, ref: data/filters.yaml#<key>}]
wheels:     [{device: Wheel-A, positions: {0: ..., 1: ...}}]
light:      [{ref: data/light_sources.yaml#<key>}]
magnifiers: [1.0, 1.5]
---
```

The body carries only what computation cannot produce: known problems,
alignment history, what must not be touched, past failures, consumable
replacement intervals.

---

## 4. Device wiring state — the three-way cross-check table

**This is the "microscope hardware and wiring state" that was asked for at the
outset.**

Two control stacks (Micro-Manager, NIS-Elements) sit on the same microscope,
and devices exist that are in neither. Three things have to be recorded
separately.

| Device | Physically present | In MM | In NIS | State recorded | Controlled by |
|---|---|---|---|---|---|
| Camera | ✅ | ✅ | ✅ | ✅ | MM |
| Objective turret | ✅ | ✅ | ✅ | ✅ | MM |
| Filter cube turret | ✅ | ✅ | ✅ | ⚠ label mangled | MM |
| Filter wheel | ✅ | ✅ | ? | ⚠ position labels registered 2026-08-11; **passbands still missing** | MM |
| Light source | ✅ | ✅ | ? | ✅ | MM |
| PFS | ✅ | ✅ | ✅ | ✅ | MM |
| 1.5x intermediate magnifier | ✅ | ✅ | ? | ✅ | MM |
| **Optical tweezers** | ✅ | ❌ | ❌ | ❌ **folder name only** · power measurement deferred by decision (2026-08-19) | separate |
| **Piezo stage** | ✅ | ❌ | ❌ | ❌ | **separate Python** (`hardware/piezo_stage.py`) |
| DMD | ✅ confirmed 2026-08-11 | ✅ | ? | ❌ | MM (pymmcore-plus) |

> - **Intermediate magnifier**: registered as an MM device on the current
>   system. Archive generation C was shot with a config that lacked the device,
>   so its 1.5x survives only in the folder name — *whether a device is
>   registered* and *whether that config was the one used for the acquisition*
>   are separate questions.
> - **DMD**: `ChNames` carries two `DMD_Green` channels while the config had no
>   such device. Resolved 2026-08-11 — physically connected, and registered in
>   the MM `.cfg` as `MightexPolygon1000`, so it is driven through
>   pymmcore-plus (kb/systems/current.md > dmd).
> - **MM version**: the current system is **confirmed MM2**. 91% of the archive
>   (2,137 acquisitions) is MM 1.4.23, so a read-only legacy parser stays
>   necessary.

### Why a three-way cross-check is needed

- **In MM, not in NIS**: data shot with NIS does not retain that setting
- **In NIS, not in MM**: it drops out of MM automation
- **In neither**: no software records it → a human has to write it down
- **In both**: risk of a **simultaneous-access conflict**. If one side holds the
  device, the other fails — or worse, quietly proceeds in the wrong state

### Cross-check procedure (once the `.cfg` is in hand)

1. Extract every `Device,` line from the MM `.cfg` → the MM device list
2. Extract the device list from the NIS-Elements device manager
3. Physical inspection (what is actually attached)
4. Merge the three lists to generate the table above
5. Decide an action for each mismatch: add to MM / record in a sidecar / ignore

Extract alongside from the `.cfg`: the `ConfigGroup,Channel,...` preset
definitions (which device-property combination each channel is), the `Label,`
lines (turret and wheel position names), and `Property,` defaults.

---

## 5. Off-ledger settings — the sidecar

Settings that neither MM nor NIS records are **lost forever unless a human
writes them down at acquisition time.** The archive is the evidence.

Leave an `acquisition.yaml` in every acquisition folder:

```yaml
# kb schema v1 — off-ledger settings only. Nothing MM records may be duplicated.
acquisition: OT0.05_Atto647_Exp80_100x_1.5x_1x1_3
date: 2026-08-08
operator: KH

# What MM2 records does not go here (intermediate magnifier, turret and wheel
# positions, exposure, light level, ...). Only what MM misses.
off_ledger:
  optical_tweezers:
    power_setting: 0.05              # unit and meaning must be stated
    power_unit: "AOM control (0-1)"  # measured mW filled in after calibration
    power_mw_at_sample: null         # ← measurement pending
    wavelength_nm: 1064
    n_traps: 1
  piezo:
    controller: "<name of the separate program>"
    z_range_um: null
    step_um: null
    log_file: null                   # path, if the separate program leaves a log
  emission_path_notes: "AUX mirror removed"

# MM records the position number, but which filter that is depends on the
# .cfg's Label. If the Label is registered, this clause is unnecessary.
ledger_gaps:
  filter_wheel_position: 2           # MM records it only as Filter-0
  filter_wheel_part: null            # ← per-position part info pending

sample:
  system: "ATPS PEG/dextran"
  fluorophore: "ATTO 647N"           # the actual fluorophore, not the conjugate
  concentration: "10 nM"
  chamber: "coverslip #1.5, 100 um spacer"
  medium_ri: 1.34

intent:
  task: tracking                     # imaging | tracking | frap | photometry
  measured_quantity: "MSD -> G*(w)"
  target_precision_nm: 10
  characteristic_time_s: 0.05
```

**The agent's responsibility**: when it proposes a setting, generate a draft of
this file alongside it and **ask explicitly** about the off-ledger items. If it
does not ask, the next person cannot use the data.

---

## 6. Quantitative index (SQLite)

The 2,343 archived acquisitions plus everything acquired from here on, in one
table. For precedent search.

```sql
CREATE TABLE acquisitions (
  acq_id            TEXT PRIMARY KEY,
  path              TEXT,
  system_id         TEXT,      -- decided by fingerprint
  project           TEXT,
  session_date      TEXT,
  folder            TEXT,

  -- device tier
  camera            TEXT,  camera_chip TEXT,
  objective_label   TEXT,  intermediate_mag REAL,  binning INTEGER,
  roi_x INTEGER, roi_y INTEGER, roi_w INTEGER, roi_h INTEGER,
  bit_depth INTEGER, readout_rate TEXT, camera_gain TEXT,
  exposure_ms       REAL,
  filter_cube       TEXT,  filter_wheel TEXT,  light_path TEXT,
  shutter_device    TEXT,
  illum_device      TEXT,  illum_line TEXT,  illum_percent REAL,
  channel_name      TEXT,

  -- physical tier  (NULL means that entry cannot transfer)
  sample_pixel_um   REAL,
  excitation_nm     REAL,  excitation_fwhm REAL,
  emission_band     TEXT,
  irradiance_w_cm2  REAL,          -- NULL without a measured light level
  total_dose_j_cm2  REAL,          -- 〃

  -- measured results
  n_frames          INTEGER,
  requested_fps     REAL,
  measured_fps      REAL,          -- from tail parsing. differs from the request
  duty_cycle        REAL,
  dropped_frames    INTEGER,       -- ElapsedTime difference outliers

  -- parsed from the folder name
  name_dye          TEXT,  name_exposure_ms REAL,  name_illum_percent REAL,
  name_trap_power   REAL,  name_tags TEXT,

  -- sidecar
  sidecar_json      TEXT,
  raw_props_json    TEXT,          -- full device snapshot preserved
  parse_error       TEXT
);

CREATE TABLE device_properties (   -- for deriving system profiles automatically
  system_id TEXT, device TEXT, property TEXT, value TEXT, n_observed INTEGER
);
```

**Keeping `measured_fps` and `requested_fps` separate is the crux.** In the
archive, a requested 10 ms exposure measured 35.67 ms. Record only the request
and the precedent lies.

---

## 7. What the parser has to handle

| Item | Content |
|---|---|
| File size | Up to 44 MB. **Stream the header only** (Summary + first FrameKey + 96 kB tail) |
| Dual schema | MM 1.4.23 (2,137 acquisitions, 91%) differs from 2.0.3. → [reference §10](../reference/observed-systems.md) |
| System fingerprint | Distinguishing by PC name gets it wrong. Use the device-label set + camera chip/serial hash |
| Label typos | `Prime95B` vs `Pirme95B` (20 acquisitions). An alias table is needed |
| Deciding the active illumination | Two light sources are registered at once. Decide on `Core-Shutter` |
| Folder-name parsing | `Las10` = level, `Las488` = wavelength, `Las555_5` = 555 nm at 5%. An integer in 350–800 is a wavelength |
| tail | Measured fps and a **cheap** drop screen from the last `ElapsedTime-ms` and the frame index: `(last − first) / (n − 1)` is the mean delivered interval, so it exceeds the requested interval exactly when frames went missing. It cannot say **where** or **how many** — that needs every timestamp, which is `compute/drops.py` (44 MB is worth reading in full only for the acquisitions this screen flags) |

---

## 8. Sample-system recipes (`kb/samples/`)

Knowledge attached to **what is being imaged**, not to a system. It survives
hardware changes.

`characteristic_scales` (τ_c, ℓ_c) is what steps ①', ②, and ⑦ of the
[04 §1](04-decision-engine.md) decision order consume. The physical model
differs per sample system (diffusion, active-particle run-and-tumble,
interfacial relaxation, ...), so there is no general-purpose calculator — the
values go into the sample-system file itself as structured fields.

```markdown
---
system: ATPS PEG/dextran
characteristic_scales:
  time:
    value_s: null              # missing = no resource allocation possible; fill in even an estimate
    evidence: assumed          # measured | assumed — the advances verdict looks only at this
    method: calculation        # measurement | calculation | literature | expert-judgment
    model: "confinement diffusion: tau_c = ell_c^2 / (2D), D from Stokes-Einstein"
    inputs: {particle_radius_nm: 500, viscosity_pa_s: 0.001}
    measured_by: null          # link to kb/calibrations/... if evidence=measured
    review_after: 2027-02-12
  length:
    value_m: 1.0e-6
    evidence: assumed
    method: literature
    model: "known particle radius (no DLS performed)"
    review_after: 2027-02-12
---
## Optical properties
- Refractive index of the two phases: PEG-rich ?, dextran-rich ?   ← ⚠ measurement needed
- Refractive-index mismatch → spherical aberration and focal shift near the interface

## Fluorescent labeling
- DEX647: the dextran molecular weight sets the phase partitioning and D ← must be recorded
- ATTO 647N: hydrophobic → non-specific adsorption at the interface is possible

## Known pitfalls
- Osmotic pressure shifts the phase composition over time → the baseline moves in long experiments
- Droplet sedimentation / creaming

## Verified settings (per system_id)
| system | objective | exposure | irradiance | measured fps | outcome |
|---|---|---|---|---|---|
```

**Rule**: a value with `evidence: assumed` is used as-is in the frame-rate and
pixel-size calculations — without an estimate there is no way to set exposure
or frame rate at all. But unless `evidence == measured`, `Verdict.advances` in
[05 §5](05-consensus-gate.md) stays `false` — the same rule under which
[04 §3](04-decision-engine.md) refuses to compute when
`power_at_sample_mw` is unmeasured. **Make the number up to compute with; do not
confirm on it.**

If `length.value_m` is smaller than the diffraction limit (`σ_PSF`) or than the
target pixel size — e.g. an actin mesh size below the diffraction limit — that
is the signal that direct resolution is impossible in the first place. No gate
catches this today → [04 §2](04-decision-engine.md).

---

## 9. Decision log (`kb/decisions/`) — the learning loop

Without a record of whether a recommendation actually held, the system does not
improve.

```markdown
# 2026-08-08 · ATPS 647 tracking
## Request
## Proposed setting + rationale (full gate output)
## Setting actually used (and why, if different)
## Outcome
- achieved SNR / localization precision / measured fps / drops
- error against the prediction
## What was learned → which file was fixed
```

Once these accumulate, gate thresholds can be tuned empirically.

---

## 10. Open questions

**Pending (user confirmed)**
- [ ] Current system `.cfg` — full-capability wiring state. Every device,
      preset, and `Label,`
- [ ] Per-position filter wheel parts
- [~] Optical tweezers power measurement (`OT` dial value → mW @ sample) —
      **deliberately deferred (user, 2026-08-19)**, along with all other laser
      power measurement. Not dropped, just not the next task. Until it lands
      `LaserCalibration.points` stays empty and every Lens 7 verdict is
      `evidence: assumed`
      → [`kb/decisions/2026-08-19-lens-7-scope.md`](../kb/decisions/2026-08-19-lens-7-scope.md)

**Not yet in hand**
- [ ] Filter cube identity (whether the archive's `DA/FI/TR10Empty` is still
      the same today)
- [ ] Measured illumination power (line × objective × level)
- [ ] The actual fluorophore and DOL behind `SA647`/`DEX647`/`Phal647`
- [ ] Which Kinetix22 camera mode is actually in use — now **four** of them
      (DynamicRange 16-bit / Speed 8-bit / Sensitivity 12-bit /
      Sub-Electron 16-bit). Updated 2026-08-19: the camera was confirmed to be a
      **Kinetix22 on PCIe**, and its datasheet Rev 2024-10-21 does supply
      read noise, full well, conversion gain, dark current and line time — all
      four modes are now in `data/detectors.yaml > Kinetix22`, so the old note
      here ("absent from the datasheet itself, needs its own measurement") is
      retired. What is still missing is only the **choice**, and it is not a
      detail: full well runs 200 / 1000 / 1000 / 15000 e- across the modes, so
      G6 can pass in one mode and clip in another at the identical light level.
      The one measured data point, `kb/calibrations/camera-readout.yaml`, was
      taken in Sensitivity — identified from its row time, not from a setting
      anyone recorded.
- [ ] Piezo log format — control itself is in hand (`hardware/piezo_stage.py`)
- [ ] Whether to index ND2/LIF (other systems)

**Settled**
- ✅ Control software: **Micro-Manager 2.x**
- ✅ Current system ≠ archive setup
- ✅ The intermediate magnifier is registered as an MM device
- ✅ The piezo is outside MM and NIS. A separate program is possible
