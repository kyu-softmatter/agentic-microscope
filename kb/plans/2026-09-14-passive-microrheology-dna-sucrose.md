---
id: 2026-09-14-passive-microrheology-dna-sucrose
question: "What is the linear microrheology of 3c* lambda-DNA in 55% sucrose, from the fluctuations of a trapped 5 um probe"
date: 2026-09-14
status: planned
subsystems: [microscope, tweezers]
---

# 2026-09-14 · Passive microrheology, lambda-DNA / 55 % sucrose

## Request

Operator (KH), 2026-09-13, in conversation:

> "I want passive microrheology, 5um abbigen green particle in fluorescently
> labeled lambda dna solution in 55%sucrose solution (solvent visocisty 50cP)
> with dna at 3c* (total viscosity 0.3Pa.s)"

Revised in the same session: the probe is **`abvigen-red-5um-cooh`** (the
standing probe), the bead is **held in the optical trap** rather than freely
diffusing, temperature is **20 °C**, and the working depth is **20 µm** above
the coverslip rather than the standing ~8 µm.

The measurement is the **first of two**. It exists partly to produce
`lambda`, the DNA relaxation time, which parameterises the plug-flow run that
follows it ([2026-09-14-plugflow-microrheology-dna-sucrose](2026-09-14-plugflow-microrheology-dna-sucrose.md)).

## Proposed setting + rationale

Every number below came from a gate or from `kb/`. Sample properties
(eta = 0.3 Pa.s, eta_solvent = 50 cP, 3c*, 20 °C, 5 µm) are the operator's,
supplied 2026-09-13.

| Axis | Value | Source |
|---|---|---|
| Objective | `100x-Oil`, position 6 | [microrheology-standard-conditions](../expertise/microrheology-standard-conditions.md) |
| Binning / pixel size | 1x1, **0.06453 µm/px** | `data/pixel_size.yaml`, measured |
| Camera / mode | `Kinetix_red`, 16-bit `DynamicRange` | standing conditions; `data/detectors.yaml` |
| Exposure ⇒ period | **20.0 ms ⇒ ~50 fps** | standing; locked by `frame_time = 0.02` in `analysis/matlab/` |
| Illumination | Aura **GREEN**, start ~80/1000, **set by counts** | standing conditions; SAFETY §6 |
| ROI | **232 x 232 px** (3x the 77.5 px bead) | standing "2-3x the particle" |
| Working depth | **20 µm** above the coverslip | lens 4, see below |
| Trap stiffness target | **alpha ~= 1.0-1.5 pN/µm** | derived below; found empirically, see Sequence |
| Segmentation | **8 particles x 12 min** | derived below |

**Why 20 µm and not the standing ~8 µm.** Lens 4's `geometry.ri_mismatch`
screening limit is `1.85/|dn|`. Against an assumed sample index of 1.43 the
limit moves from ~10 µm (aqueous) to ~21 µm, and 20 µm clears at **m = 1.05**
while 25 µm (0.84) and 30 µm (0.70) do not. Working at 20 µm instead of ~8 µm
cuts the Faxen wall-drag inflation from the **+17.6 %** quoted in
[microrheology-standard-conditions](../expertise/microrheology-standard-conditions.md)
to a few percent. ⚠ **This depends entirely on the sample index, which is
unmeasured** — see Preconditions.

**Why alpha ~= 1.0-1.5 pN/µm.** The trap high-passes the medium: only
relaxations faster than `tau_trap = gamma/alpha` are observed, with
`gamma = 3*pi*eta*D = 14.14 pN.s/µm` from the operator's viscosity. At
alpha = 1.4 that is **tau_trap ~= 10 s**, opening the window out to ~10 s DNA
modes. Equipartition then gives `rms<x> = sqrt(kT/alpha) = 54-64 nm`
(0.8-1.0 px at the measured pixel size) — comfortably above the localisation
floor, unlike the **4.8 nm per frame** a *freely diffusing* bead would show in
this medium, which is what ruled out the untrapped design.

**Why 8 x 12 min and not one 90-minute run.** Statistically the two are
identical: `N_indep = T/(2*tau_trap) = 267` either way, **stat. error 8.6 %**.
Lens 3 passes both (5.4 MB/s, 2.6 % of the measured disk), so **memory and
bandwidth are not the constraint**. Segmentation is chosen for four other
reasons: no measured axial drift rate exists in `kb/calibrations/` and the
depth of field is ~445 nm; the only bleaching datum on record is +2.19 % over
**5 s**, which cannot be extrapolated to 90 min on one bead; a bead lost at
minute 70 costs one segment rather than everything; and 3.88 GB per file keeps
each stack loadable. 12 min also holds each file just under the 4 GB boundary,
and gives a max usable lag of 72 s = 7x `tau_trap`.

## Committee verdict

| Lens | Verdict | Deciding gate | m | Evidence |
|---|---|---|---|---|
| 1 optics | not run | — | — | needs the dye entry; `abvigen-red-5um-cooh` is registered but the run was not executed in the design session |
| 2 detection | **BLOCKED** | `missing.photon.signal` | — | assumed; "a computed value here would be fiction" |
| 3 compute | PASS_WITH_CHANGES | `data_rate`, `capacity` | 10.00 | assumed — 50 fps is *requested*, not achieved (G12b) |
| 4 sample | PASS (at n=1.43) | `geometry.ri_mismatch` | **1.05** | **assumed index**; coverslip thickness also assumed |
| 5 photo | not run | — | — | convene with lens 1 per E6 |
| 6 validity | not run | — | — | convene last |
| 7 trapping | PASS | `sampling` | 2.37 | assumed dial%→mW; stiffness is an **upper bound** |
| 8 mechanical | **BLOCKED** | `missing.axial_drift_rate` | — | nothing in `kb/calibrations/` records a drift rate |

**Not evaluated.** `unevaluated` is not `cleared`:

- **Lens 1, 5 and 6 were not convened.** The design session stopped at the
  blocking inputs; they must run before the instrument is touched.
- **Trap heating is ungated by decision** (CLAUDE.md E3, [06 D6](../../docs/06-pitfalls.md)).
  Over 1 W of 1064 nm is available at the sample and `dD/D = 2.74 %/K`, so
  heating biases exactly the quantity being measured. **No gate will catch
  this.** Record it in lens 6's bias ledger as `unevaluated`.
- **Lens 7's PASS rests on a placeholder power.** Its implied stiffness is
  ~187 pN/µm, far stiffer than the measured 3.65-4.5 pN/µm
  ([2026-09-03-three-subsystems-first-light](../decisions/2026-09-03-three-subsystems-first-light.md)).
  The PASS is conservative in the sampling direction but is not evidence.
- **Lens 4's PASS is conditional on an index nobody has measured.** At n = 1.33
  the same gate returns m = 0.49 at this depth, and lens 7 returns
  `trap.shallow` FAIL at n = 1.45. The verdict flips across the plausible range.

## Preconditions

- [ ] **Refractive index of the actual buffer** — *checked by:* refractometer
      reading. 55 % sucrose is the named exception in
      [sample-medium-refractive-index](../expertise/sample-medium-refractive-index.md),
      which requires a `BLOCKED` rather than the 1.333 default. This single
      number decides the 20 µm depth **and** whether the trap holds at all.
- [ ] **Temperature is a reading, not nominal** — *checked by:* thermometer at
      the sample. `dD/D = 2.74 %/K`; the falsifier in
      [microrheology-standard-conditions](../expertise/microrheology-standard-conditions.md)
      is >2 K.
- [ ] **Axial drift rate on record** — *checked by:* park on a fixed feature,
      PFS off, log focus every few minutes for an hour from a disturbed
      enclosure; write to `kb/calibrations/`. Cannot be computed.
- [ ] **One test frame for photometry** — *checked by:* `peak_adu` between a
      third and a half of 65535, written to `kb/calibrations/frame-photometry.yaml`.
      The nearest record is a 5 µm DragonGreen bead at 2x2 / 10 ms / CYAN
      3/1000 and does not transfer.
- [ ] **Trap calibration valid for `100x-Oil`** — *checked by:* drive a known
      amplitude and **measure** it. An objective change silently invalidates
      both GUI calibrations and neither is readable over TCP (SAFETY §2).
- [ ] **Both turret shutters open** — *checked by:* a non-black live frame.
- [ ] **`NIDAQAO-Dev1/ao2` absent from the loaded `.cfg`** — *checked by:*
      `microscope.check_config_file()`, which reads the file as text before
      loading (SAFETY §3).

## Sequence

[SAFETY §8](../../SAFETY.md) is the standing setup order and is not repeated.
Specific to this run:

| # | Subsystem | Action | Flag required | Confirmed by |
|---:|---|---|---|---|
| 1 | microscope | Load sample with a **4x or 10x** in the path | — | the low-mag objective visibly in the light path |
| 2 | microscope | Find sample edges, build a map | `--allow-motion` | edge positions recorded |
| 3 | microscope | Change to `100x-Oil` **at the stand or in NIS** | — | objective read back from the nosepiece |
| 4 | tweezers | Re-verify trap calibration: drive a known amplitude | `--allow-laser` | **measured** displacement in camera data matches the command |
| 5 | microscope | Focus to **20 µm above the coverslip**; record `ZDrive` | `--allow-motion` | `ZDrive` readback, and the coverslip surface located first |
| 6 | tweezers | Trap one bead at a **low** dial setting | `--allow-laser` | bead visibly held, and it does not translate with the stage |
| 7 | microscope | Record 60 s at 50 fps; compute `alpha = kT/var(x)` | — | `alpha` printed from the frames, not assumed |
| 8 | tweezers | Adjust dial, repeat 7 until `alpha` = 1.0-1.5 pN/µm | `--allow-laser` | measured `alpha` in range; **dial % written down by hand** |
| 9 | microscope | Close the live view | — | viewer window gone |
| 10 | microscope | Acquire **12 min** at the run ROI | — | `ImageNumber` continuous; achieved rate from `ElapsedTime-ms` span |
| 11 | microscope | Check drops and bleaching | — | `compute.cli drops`; first-10 % vs last-10 % mean |
| 12 | — | Release bead, trap a new one at the **same z**, repeat 6-11 | — | 8 segments total, each with its own `alpha` |

**A return code is not a confirmation** (SAFETY §0). Every confirmation above is
something observed in camera data or read back from a device that has a
readback. The Tweez 300 has none.

## Stop conditions

- **Bead lost mid-segment** → discard that segment only; do not splice.
  Instrument state: laser stays armed, stage untouched, trap a new bead.
- **Focus drift moves the bead out of the 445 nm depth of field** → stop the
  segment, re-focus to the recorded `ZDrive`, restart the segment. Do not
  re-focus *during* a segment.
- **`alpha` cannot be brought into 1.0-1.5 pN/µm** → stop and escalate
  (CLAUDE.md H5). Do not silently accept a stiffer trap; it masks the slow
  modes this run exists to measure.
- **Peak counts exceed ~95 % of 65535** → stop, lower the Aura level, restart.
  Saturation is unrecoverable in post.
- **Refractive index comes back near 1.45** → **abort the whole run.** Lens 7
  returns `trap.shallow` FAIL and the trap will not hold. Instrument state:
  laser off at the GUI, stage centred, objective left at `100x-Oil`.
- **Any abort** leaves: light down (the `finally` path, not a force-kill),
  laser disarmed at the GUI, and the recorded `ZDrive` written to the session
  log so the next attempt starts from a known height.
