# 2026-08-26 · Microscope configuration control (Phase 5a–5d)

> Same bent format as `2026-08-10-labeling-and-laser-recommend.md`: this session
> implemented a tool, not an experiment, so it records "what was implemented" and
> "bugs found" in place of settings/result.
>
> **First of three entries from 2026-08-26**, in the order they were written:
> this one (microscope configuration) → `2026-08-26-tweezers-pattern-vs-direct.md`
> (the tweezers, and the two calibrations) →
> `2026-08-26-parallel-control-architecture.md` (running all three at once, and a
> feasibility audit of five specific operations). Read them in that order; each
> one changed something in the one before it.

## Request

Check whether three things are controllable from Python — optical-tweezers
patterns, **microscope configuration**, and piezo-stage pattern generation — with
the standing note that *if Python can drive the hardware directly, a pattern file
is not required*. Microscope configuration first; the other two are still open.

## What was implemented

| File | Role |
|---|---|
| `hardware/microscope.py` | `Microscope` — read/compare/generate/apply MM device configuration through pymmcore-plus. Three independent write gates. |
| `config/micromanager/verify_config_control.py` | Microscope-PC verification script, one flag per roadmap stage: `--read` (5a+5b) · `--propose` (5c) · `--roundtrip` (5d) |
| `tests/test_microscope.py` | 36 tests against the bundled demo config; the hazard tests need no MM install |

The API is split along `docs/07-roadmap.md` Phase 5 rather than by device, so the
stage a caller is in decides what it can reach:

- **5a** `snapshot()` · `state()` · `groups()` · `current_preset()`
- **5b** `diff()` · `preset_diff()` — no-ops kept in the result, so "already
  correct" is distinguishable from "could not tell"
- **5c** `define_preset()` · `save_config()` — core-side only, so it stays
  available in read-only mode on purpose
- **5d** `set_property()` · `apply()` · `set_preset()` · `temporarily()`

## Answer to the question asked

**Yes, and no pattern file is needed.** Configuration is direct property/preset
writes, so there is nothing to pre-author: `setProperty` / `setConfig` reach every
MM-registered device, which on this system is the whole Ti2-E stand and children,
both Kinetix cameras, the CSU-W1 group, SpectraIII/AuraIII, the DMD, and the LUN-F
blanking lines. Unchanged: the Splitter, LUN-F per-line power, piezo, and tweezers
are not MM devices (see `current.md > devices_not_in_mm_config`).

Verified on **macOS/arm64 against the demo config only** — `mmcore install` has no
Apple-Silicon nightly, so the real NikonTi2/PVCAM/CSUW1 adapters were not
exercised. That is the same surrogate `calibration/mm_live.py` accepted, and the
same limit applies: MMCore semantics are confirmed, per-adapter behaviour is not.
Running `verify_config_control.py --read` on the microscope PC is what closes it.

## Safety gates, and why three

`allow_write` alone would have conflated three different accidents, so each has its
own switch (all default off):

| Gate | Devices | The accident |
|---|---|---|
| `allow_write` | all | applying an unreviewed state to a running experiment |
| `allow_motion` | `Nosepiece` `ZDrive` `PFSOffset` | glass into glass — an objective change swings a different working distance under an unmoved sample; worse under PFS |
| `allow_laser` | `LUNF-Blanking` | a blanking line opens a class-4 path, and per-line power is whatever NIS last set (`lunf_power.py` cannot read or set it) |

Plus `check_config_file()`, which refuses any `.cfg` declaring
`NIDAQAO-Dev1/ao2` before loading it — the piezo hazard from
`current.md > devices_not_in_mm_config > piezo stage > hazard`. It has to be a
text check: MM writes 0 V during `initializeDevice`, so by the time the core has
loaded the device there is nothing left to prevent. A test asserts the lab's own
`DMD_dualcam_LUNF.cfg` is clean, so an edit that adds one fails in CI rather than
on the bench.

## Bugs found

1. **Read-back by string equality rejected successful numeric writes.** Writing
   `"50"` to a Float property reads back `"50.0000"` — MM echoes the adapter's own
   formatting — so `set_property` raised on a write that had in fact landed. Caught
   by running `--roundtrip Z.Position=50`, not by the unit tests, which until then
   only used string-valued labels. Fixed with a typed comparison
   (`READBACK_RTOL = 1e-3`) that also absorbs genuine device quantisation — a
   Kinetix rounding exposure to a row time, PFSOffset to an encoder count — while
   still failing a write that did not land. `Change.after` always carries the value
   the device actually reported, so exactness stays available to the caller.

## Still open

- **5e** (acquisition + live gate monitoring) not started.
- Real-adapter confirmation on the microscope PC, including the
  `Ti2_Mic_Driver.dll` copy the `mmcore install` build needs.
- Apply *ordering* is the caller's: `apply()` writes in the order given and this
  module has no model of which order is safe (shutter before cube, not after).
  Left explicit rather than guessed.
- Piezo pattern generation — the remaining third of the original question. Not
  started. The decisive unknown is whether the NPC-D command set has a
  waveform/trajectory generator (`find_commands("wave")` against the real
  controller); that answer decides whether the piezo is a hardware-timed
  subsystem or a host-driven one, and it is the last open piece of the timing
  picture in `2026-08-26-parallel-control-architecture.md`.

## Amended later the same day

Two things in this entry were overtaken by what the tweezers work turned up, and
are corrected here so this note is not read on its own and believed:

- **`COLLISION_DEVICES` gates `Nosepiece` for a second, independent reason.**
  Beyond the glass-crash risk recorded above, an objective change silently
  invalidates *both* optical-tweezers calibrations — the GUI px→µm magnification
  and the AOD trapping-field response — and neither is readable over the
  tweezers' TCP link, so afterwards every trap position in µm is wrong with
  nothing reporting it.
- **The Kinetix cameras are not exclusively ours.** The Tweez 300 GUI loads a
  Kinetix and later releases it, and PVCAM is single-owner, so
  `Microscope.connect()` must run *after* the tweezers GUI has let go. That
  ordering is now enforced by `hardware/orchestrator.py` and flagged at the top
  of `config/micromanager/verify_config_control.py`; `microscope.SHARED_DEVICES`
  turns the contended-load failure into a message that names the cause.
