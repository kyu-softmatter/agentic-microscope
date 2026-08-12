# 06 · Pitfalls

**What actually goes wrong** with this data and this science. Not generalities —
only what was confirmed across the 2,343 archived acquisitions and what bears
directly on this lab's measurements.

Each item is tagged with **which gate/lens catches it**. An item with no gate
means nothing catches it yet.

---

## A. Data & metadata

### A1. `PixelSizeUm` is `0.0` in every file 🔴

Pixel size calibration was never set in Micro-Manager. **All 2,343
acquisitions.**

- Every spatial measurement so far (MSD, diffusion coefficient, particle size,
  interface position) rests on an **external calibration value**, and the
  metadata does not say where that value came from
- You can compute `11 µm / magnification`, but that normally disagrees with a
  measured calibration by 3–5%
- The diffusion coefficient scales as the **square** of pixel size. 3% error →
  6% error in D

**Action**: measure it with a stage micrometer/grid for each magnification
combination and register it in MM2's `ConfigPixelSize`. From then on it is
recorded automatically.
→ No gate. **Lens 6 (Measurement validity) must catch this**

### A2. MM 1.4 and 2.0 have different schemas 🟡

Generation A (2,137 acquisitions = 91%) is MM 1.4.23.

| | MM 1.4 | MM 2.0 |
|---|---|---|
| Pixel | `PixelSize_um` | `PixelSizeUm` |
| ROI | `Summary.ROI` array | FrameKey string |
| Start time | **absent** | `StartTime` |
| Camera per frame | **absent** | `Camera` |

**A single parser loses 91% of the data.**
The current system is settled on MM2, but the legacy parser for reading the
archive is still needed.

### A3. Identifying a system by computer name is wrong 🟡

There are three PC names but the hardware fingerprints are effectively one
family. Conversely, the device configuration changed on the same PC
(`LightEngine` added in generation B).

**Action**: fingerprint = set of device labels + hash of camera chip/serial.

### A4. Turret position is not a stable identifier 🟡

Turret position 4 was **physically swapped** between generations,
`Plan Apo Lmbd 60x Oil` → `Plan Apo VC 60x WI`. Identify the objective by
position number and immersion and NA come out wholly wrong.

### A5. Device labels contain typos 🟢

20 acquisitions record `Prime95B` as `Pirme95B` (a typo in the config).
Match labels without an alias table and those 20 disappear.

### A6. The `Las` token in folder names means two different things 🟡

- `Las10` → 10% level
- `Las488` → 488 nm wavelength
- `Las555_5` → the 555 nm line at 5%

An integer in 350–800 has to be read as a wavelength. Otherwise you get "laser
at 488%".

### A7. Sometimes the folder name is more honest than the metadata 🟡

Generation C was shot with a config that had no `IntermediateMagnification`
device, so the 1.5x survives **only in the folder name**. Even when a device is
registered, whether *that config was the one used for the acquisition* is a
separate question.

**Lesson**: when metadata and folder name disagree, **record the disagreement
itself** and ask the human. Never pick a side automatically.

---

## B. Optics

### B1. Filter information is effectively absent 🔴

| Item | State |
|---|---|
| `FilterTurret1-Label` | `1-DA/FI/TR10Empty` in 2,312 acquisitions — the string is mangled, the part cannot be identified |
| `Wheel-A-Label` | `Filter-0` in 2,292 acquisitions — **the position labels were never registered in the .cfg** |

And **764 acquisitions shot 647-Cy5 through `DA/FI/TR` (3-band).** That does not
add up physically. Either the cube is really a 4-band, or the wheel is selecting
emission and is invisible, or the label is wrong.

→ The optics gate rejects this channel as `BLOCKED`. **That is intended
behavior.**
> **On receiving a `.cfg`, the first thing to check is whether it has `Label,`
> lines.** Without them the filter wheel will be recorded as `Filter-0` forever.

### B2. Two light sources sit in the config at once 🟡

Generation B has both `Spectra` (Spectra X) and `LightEngine` (Spectra III)
registered, and the level values of the unused one persist in the metadata.

**The active illumination must be determined from `Core-Shutter`.** Read the
level values alone and you get it wrong.

### B3. The light path may not go to the camera 🟡

`LightPath-Label`: `4-L100` (100% to camera) in 1,728 acquisitions vs `3-AUX` in
564. Parked on AUX, the camera signal is absent or much reduced.
"The signal is weak" may be caused by this rather than by the light level.
→ Gate `path.port_split` ✅

### B4. Removing a filter raises the signal — but usually you must not 🔴

The ablation calculation says removing the emission filter raises the signal by
+43%. **That is an illusion produced by the idealized blocking floor of the
approximated spectra.** In real glass, backscattered excitation light swamps the
signal.

→ Guarded three ways in the implementation:
1. If the emission path has only one spectrally selective element, it is
   unconditionally `required`
2. With approximated spectra, the blocking requirement rises 5 OD → 7 OD
3. With approximated spectra the verdict is `candidate`, not `remove` (not an
   instruction until confirmed on the bench)

### B5. Raising objective NA buys less than you think 🟢

| Intervention | Collection efficiency gain | Cost |
|---|---|---|
| NA 1.45 → 1.49 | **×1.15** | objective $$$ |
| 12bit → 16bit readout | **×3.4** (noise) | free |

The opposite of intuition. → [05 §4](05-consensus-gate.md) sensitivity analysis

---

## C. Detection & quantification

### C1. On-camera despeckle post-processing is enabled 🔴

```
Prime95B-PP  1   ENABLED: Yes     DESPECKLE BRIGHT LOW/HIGH, threshold 125
Prime95B-PP  2   ENABLED: Yes     DESPECKLE DARK LOW,        threshold 125
Prime95B-PP  3   ENABLED: Yes     DESPECKLE DARK HIGH,       threshold 80
Prime95B-PP  4   ENABLED: Yes     threshold 75
```

**It was on in every generation.** Despeckle replaces pixels crossing the
threshold with a neighbor value. As a result:

- pixel-value **linearity breaks** → no photometric quantification
- noise becomes **spatially correlated** → the maximum-likelihood assumption of
  subpixel localization collapses
- a dim single particle mistaken for a "dark speckle" **can be erased**
- and the image looks cleaner for it → **hard to notice**

It must be off for quantitative experiments. Data already taken cannot be
recovered retroactively.
→ No gate. **Lens 6 must catch this**

### C2. Quantization noise in 12-bit mode swamps read noise 🟡

| Mode | e⁻/ADU | Quantization noise | read noise | Effective |
|---|---|---|---|---|
| 100MHz 16bit / HDR | 1.22 | 0.35 e⁻ | ~1.3 | **1.35 e⁻** |
| 200MHz 12bit / Full well | 15.14 | **4.37 e⁻** | ~1.6 | **4.65 e⁻** |

Choose 12-bit for speed and effective noise is **3.4×**. At weak signal that is
3.4× worse SNR too. `full_well` and `bit_depth` are in the metadata, so this is
always computable.

### C3. A rolling shutter responds only to the **row count** 🟡

Row time **10.28 µs** (independently confirmed in two archive files).

- 1608 rows → 16.53 ms → 60.5 fps
- 176 rows → 1.81 ms → 553 fps
- **narrowing the width buys nothing at all**

The crops in the archive are mostly square. If speed was the goal, **a wide,
short ROI is far faster at the same pixel count.**

A rolling shutter also exposes each row at a different time. Fast-moving targets
acquire geometric distortion.

### C4. Requested and measured frame rate differed by 3× 🔴

10 ms exposure, 176-row ROI → camera limit ~85 Hz.
But `ActualInterval-ms = 35.67` → **measured 28 Hz.**

The camera is not the bottleneck. It is MM overhead, disk, or the circular
buffer.

**The KB must record `measured_fps`.** Keep only the requested value and
precedent lies. → Gates G12 G13

### C5. Frame drops happen silently 🔴

When the buffer cannot keep up with the data rate, frames are discarded and **no
error is raised.** It surfaces only as irregular `ElapsedTime-ms` intervals.

Get the lag time wrong in an MSD calculation and the diffusion coefficient is
wholly wrong.

**Action**: always check the variance of `ElapsedTime` differences after
acquisition. This can be applied to the archive right now, and should be.

### C6. "Finer pixels are always better" is false 🔴

| Task | Optimal pixel | 100x/NA1.45, 668 nm |
|---|---|---|
| Morphology & structure observation | Nyquist `p ≤ r/2` | ≤ 140 nm |
| **Single-particle tracking** | `p ≈ σ_PSF` | ≈ 100 nm |

$$\sigma_{\text{loc}}^2 = \frac{\sigma^2 + p^2/12}{N} + \frac{8\pi(\sigma^2+p^2/12)^2 b^2}{p^2 N^2}$$

The background term goes as `1/p²`, so **larger pixels make it better.** There
is a finite optimum. Apply Nyquist mechanically to a tracking experiment and
precision gets worse.

→ Gate G5. **With no task type given, do not fall back to a default — ask.**

---

## D. Sample & photophysics

### D1. Motion blur biases MSD systematically 🔴

**The most dangerous item in this lab's microrheology.**

$$\langle \Delta x^2 \rangle_{\text{meas}}(\tau) = 2D\left(\tau - \frac{t_{\exp}}{3}\right) + 2\varepsilon^2$$

- Blur term `−2D·t_exp/3` : MSD **underestimated**
- Static error `+2ε²` : MSD **overestimated**

At short lags the two terms cancel and out comes **a plausible straight line
with the wrong slope**. Push it through GSER and `G*(ω)` is wholly wrong. And
the plot looks fine.

Gate: `t_exp < 0.3 τ_min` (duty ≤ 30%).
28% of the archive happens to satisfy it, but the 647 channel (500 ms exposure)
needs checking.

### D2. The excitation light drives the sample 🔴

`Active particle control`, `ATPS motility induced partitioning` — light-driven
active colloids. **The excitation light is an experimental variable, not a
measurement tool.**

- Optics lens: "raise the light level for SNR"
- Photo-perturbation lens: "that light is pushing the particle"

Surfacing this conflict is the reason the committee is split.
Similar cases: LC photo-alignment, FRAP where the imaging light has already
begun bleaching, photo-crosslinking.

### D3. Phalloidin stabilizes actin 🔴

Measure actin rheology with `Phal647` and **you are changing the very thing you
measure.** Phalloidin stabilizes F-actin, altering the filament length
distribution and the dynamics.

This is not the only case where the label changes the sample:
- **ATTO 647N**: strongly hydrophobic, so it adsorbs non-specifically at
  interfaces and hydrophobic domains → distorts ATPS partitioning
- **Dextran-647**: molecular weight decides the phase partitioning and D — not
  reproducible if unrecorded
- **Acridine Orange**: emission **shifts** 526 → 650 nm with binding state.
  Model it with a single spectrum and the 647-channel crosstalk is completely
  wrong

### D4. A conjugate name is not a fluorophore name 🟡

`SA647`, `DEX647`, `Phal647` all mean nothing more than "something 647".
Alexa 647 / ATTO 647N / DyLight 650 differ widely in ε, Φ, and photostability.

| | ε (M⁻¹cm⁻¹) | Φ | ε·Φ |
|---|---|---|---|
| Alexa 647 | 270,000 | 0.33 | 89,100 |
| ATTO 647N | 150,000 | 0.65 | **97,500** |

By ε alone Alexa looks 1.8× brighter, but **the actual brightness is slightly
higher for ATTO.** And **DOL** (fluorophores per molecule) moves it by another
several-fold.

### D5. ATPS has different refractive indices in its two phases 🟡

Within one field of view the aberration differs per phase. Crossing the
interface produces a focal shift. Not negligible for depth-direction
measurements or for tracking near the interface.

The medium refractive index has never been recorded. → Lens 4

### D6. Tweezers at 1064 nm heat and leak 🟡

- **Local heating** from water absorption at 1064 nm → viscosity changes, so D
  changes. In microrheology it contaminates the measured quantity itself.
  **Not implemented**: `trapping/` computes only `confinement`, `trap_depth`,
  and `sampling` — Lens 7 is otherwise complete, but has no heating check
- **Leakage** into the detection path — the reason the optics gate holds its
  grid out to 1100 nm
- The tweezers are outside MM, so the power leaves no trace in the metadata
  (only the folder name `OT0.005`)

### D7. PFS can be on without being locked 🟡

There are sessions with `PFS-FocusMaintenance: On` but `PFS in Range: Out of
Range`. Record only the on state and you cannot tell whether focus was actually
held. **Both must be recorded.**

---

## E. Methodology

### E1. Do not take a precedent as the target 🔴

"We shot it this way last time, so let's do that" **replicates past mistakes.**

Example: the DEX647 tracking precedent ran an 88% duty cycle → 29% motion blur
bias. Take that as the target and the bias is inherited.

**Precedent is the starting point; the physics gates are the judge.**
→ [03 §6](03-cross-system-transfer.md)

### E2. `BLOCKED` and `FAIL` are different 🟡

- `FAIL` — this setting is physically bad → **change the setting**
- `BLOCKED` — there is no basis to judge → **measure it or find the datasheet**

Blur the two and the reaction becomes "the gate keeps blocking me" — then it
gets turned off.

### E3. A PASS computed from catalog values is not a PASS 🔴

Blocking (OD) and crosstalk are decided in the **far wings** of the spectra.
A parametric approximation is useless exactly there. Only the peak position is
right.

→ Enforced through `Verdict.evidence`. `PASS` + `assumed` = `advances: NO`

### E4. A binary verdict disables the gate 🟡

Experiments that must be shot at the measurement limit do exist. Return only
`FAIL` and the human turns the gate off.

Replaced with **difficulty grade + improvement proposals**.
"This experiment is HARD. You may proceed, with these conditions attached.
Switching to 16-bit improves it ×3.4." → [05](05-consensus-gate.md)

### E5. An improvement has to pass the gates again 🟡

- 2× light → SNR ×1.4, **2× bleaching dose** (recheck G10)
- 2×2 binning → SNR ×2, **effective pixel 110→220 nm** (destroys G5 if tracking)
- switch to 16-bit → noise ×0.29, **max fps drops** (recheck G9)

**No improvement is free.** A sensitivity analysis must always report the side
effects along with the gain.

---

## Severity legend

🔴 The result is wrong or the experiment becomes meaningless — must be addressed
🟡 Loss of quality or efficiency, or risk of misinterpretation
🟢 Good to know

---

## Nothing catches these yet

Items **currently missed** because no gate exists:

| Item | Owner |
|---|---|
| A1 missing pixel calibration | Lens 6 |
| C1 despeckle post-processing | Lens 6 |
| D2 light-driven perturbation | Lens 5 |
| D3 sample perturbation by the label | Lens 5 |
| ~~D5 refractive-index mismatch~~ | ~~Lens 4~~ — now caught: `sample.gate` G17 (2026-08-12) |
| D6 tweezers heating | Lens 7 — the one gap in an otherwise implemented lens |
