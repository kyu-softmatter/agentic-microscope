# 04 · Decision engine

The part that fixes settings **by computation**. This is the region where the LLM
does not judge. Every expression here is closed-form, and with an input missing
it refuses rather than inventing a value.

> The numerical examples in this document come from the archive (the old setup).
> They must be recomputed with current system values.
> → [reference/observed-systems.md](../reference/observed-systems.md)

---

## 1. Decision order

The degrees of freedom cannot be fixed in an arbitrary order. There is an order
in which **a later step does not invalidate an earlier one**, and physics sets
that order.

```
 ① Physical quantity to measure + target precision   ← the human gives this
        │
 ①' System's characteristic time τ_c · length ℓ_c    ← kb/samples/<system>.md
        │            (measure if measurable, otherwise a theoretical estimate
        │             + evidence=assumed)
        │
 ② τ_c  →  required frame rate f
        │            (τ_c/10, or f ≳ 10·f_c with optical tweezers)
        │
 ③ f  →  exposure ceiling   t_exp ≤ 1/f − t_readout
        │  plus the motion-blur ceiling (§5)
        │
 ④ target precision  →  required detected photons N  (§4, localization
        │                                             precision inverted)
        │
 ⑤ N / t_exp  →  required detected electron rate  →  required excitation
        │         irradiance   (§3, photon budget inverted)
        │
 ⑥ irradiance  →  photobleaching dose · photo-perturbation check
        │          (if exceeded, back to ②)
        │
 ⑦ ℓ_c + objective · intermediate mag · binning  →  sampling check
        │            (§2, reflects both ℓ_c and the task dependence)
        │
 ⑧ ROI  →  recompute t_readout from ③ + statistical power check (§7)
        │
 ⑨ Data rate · buffer · storage check                (§8)
```

②↔⑥ and ③↔⑧ are cycles. If they do not converge the requirements are
**incompatible**, and that fact is itself the output
([01 §3 Principle 5](01-architecture.md)).

**Evidence grade of ①'**: even with `evidence: assumed` (a theoretical
estimate), the value is used as-is in the later steps. But the final `advances`
stays `false` unless `evidence: measured` — the same rule as
`power_at_sample_mw` in §3. → [02 §8](02-knowledge-base.md)

---

## 2. Space — sampling

### Effective pixel size

$$p_{\text{sample}} = \frac{p_{\text{sensor}} \times B}{M_{\text{obj}} \times M_{\text{int}}}$$

`PixelSizeUm` is `0.0` in every archived file, so this **must** be computed.

For the old setup (11 µm pitch, B=1):

| Objective | Intermediate mag | p_sample |
|---|---|---|
| 100x | 1.5x | 73.3 nm |
| 100x | 1.0x | 110 nm |
| 60x | 1.0x | 183 nm |
| 40x | 1.0x | 275 nm |
| 20x | 1.0x | 550 nm |
| 10x | 1.0x | 1,100 nm |

> ⚠ These are computed, not calibrated. Measure the per-magnification pixel size
> once with a stage micrometer or a grating and put those values in the profile.
> A 3–5% discrepancy between calculation and measurement is common. (Current
> system: `kb/systems/current.md` > `pixel_size_calibration`.)

### Diffraction limit

$$r_{\text{Rayleigh}} = \frac{0.61\,\lambda_{em}}{NA} \qquad
\sigma_{\text{PSF}} \approx \frac{0.21\,\lambda_{em}}{NA} \qquad
\text{DOF} \approx \frac{n\,\lambda}{NA^2}$$

### ⚠ The optimal pixel size runs in opposite directions depending on the task

**This is the easiest thing in this engine to get wrong.**

| Task | Criterion | 100x/NA1.45, λ=668 nm |
|---|---|---|
| **Morphology / structure** | Nyquist: `p ≤ r/2` | r = 281 nm → **p ≤ 140 nm** |
| **Single-particle tracking** | optimal near `p ≈ σ_PSF` | σ = 97 nm → **p ≈ 100 nm** |

Applying Nyquist mechanically in tracking and slicing the pixel finer **makes
the precision worse.** The Thompson–Larson–Webb / Mortensen localization
variance:

$$\sigma_{\text{loc}}^2 = \frac{\sigma_a^2}{N} + \frac{8\pi\,\sigma_a^4\,b^2}{p^2 N^2},
\qquad \sigma_a^2 = \sigma_{\text{PSF}}^2 + \frac{p^2}{12}$$

- the first term (photon shot noise) gets worse as `p` grows, because of `p²/12`
- the second term (background noise) gets **better** as `p` grows (`1/p²`)

→ in real conditions, where background exists, a finite optimal `p` exists. All
of this lab's microrheology falls in that regime.

**Gate implementation**: take the task kind (`imaging` / `tracking`) as an input
and switch the criterion accordingly. If the task is not stated, **ask.** Do not
use a default.

### ⚠ If ℓ_c is below the diffraction limit, resolution is impossible to begin with

If `characteristic_scales.length` in `kb/samples/<system>.md` (e.g. actin mesh
size, ATPS interface thickness) is smaller than `σ_PSF`, no amount of shrinking
the pixel resolves that structure directly. Passing the sampling gate (the two
criteria above) means nothing then — **the problem is the optical diffraction
limit, not the camera.** There is still no gate for this verdict.

---

## 3. Photon budget

### The whole chain

```
source power P [W]  (measured at the sample plane)
   ↓  divide by illuminated area A
irradiance  I = P/A  [W/cm²]
   ↓  divide by photon energy hc/λ
photon flux  φ = I λ /(hc)  [photons cm⁻² s⁻¹]
   ↓  absorption cross-section
excitation rate  k_ex = σ_abs · φ · (spectral overlap)  [s⁻¹]
   ↓  quantum yield
emission rate  k_em = k_ex · Φ_F
   ↓  objective collection solid angle
   ↓  emission path transmission × camera QE
detection rate  k_det = k_em · η_geo · T_em · QE   [e⁻/s/molecule]
   ↓  exposure time
signal per frame  S = k_det · t_exp  [e⁻]
```

**Absorption cross-section** (ε in M⁻¹cm⁻¹):

$$\sigma_{\text{abs}} = 3.82\times10^{-21}\,\varepsilon \quad [\text{cm}^2]$$

**Geometric collection efficiency** — the largest term in the photon budget, and
the one most often dropped from back-of-envelope estimates:

$$\eta_{\text{geo}} = \frac{1-\cos\theta}{2}, \qquad \sin\theta = \frac{NA}{n}$$

| Objective | η_geo | of 4π |
|---|---|---|
| 100x NA 1.45 oil (n=1.518) | **0.352** | 35.2% |
| 60x NA 1.20 water (n=1.333) | **0.282** | 28.2% |
| 10x NA 0.30 air | **0.0230** | 2.3% |

Implemented as `optics/components.py :: Objective.collection_efficiency` and
covered by tests.

### Saturation

$$I_{\text{sat}} = \frac{hc}{\lambda\,\sigma_{\text{abs}}\,\tau_{\text{fl}}}$$

As `k_ex → 1/τ_fl` the linear model above overestimates. Triplet shelving
arrives earlier, at lower intensity. **The photon budget above does not model
saturation** — `optics.path.detected_e_per_s` is linear in power throughout — so
the warning is lens 5's job: `photo.checks.check_saturation` (G20) gates the
steady-state excited-state fraction `k_ex τ/(1 + k_ex τ)` at 0.1, the same
threshold expressed as an occupancy rather than as `I ≳ 0.1·I_sat`. Past it,
this section's numbers and lens 2's SNR are both overestimates while dose keeps
climbing.

### ⚠ Without a measured light level this whole section is void

If `power_at_sample_mw` is empty, `detected_e_per_s()` **returns `None`.** It
does not invent a number. All that is possible then is relative comparison
within the same instrument.

```python
# archive state, as-is
ch.detected_e_per_s()  # -> None

# after 30 minutes with a power meter
ch.detected_e_per_s(power_mw_at_sample=1.0, illuminated_area_um2=100*100)  # -> a value
```

The measurement procedure is in the header of
[data/light_sources.yaml](../data/light_sources.yaml).

---

## 4. SNR and precision

### SNR

With the spot spread over `n_pix` pixels:

$$\text{SNR} = \frac{N_{\text{sig}}}
{\sqrt{N_{\text{sig}} + N_{\text{bg}} + N_{\text{dark}} + n_{\text{pix}}\,\sigma_{\text{read}}^2}}$$

- `N_sig` : signal electrons = `k_det · t_exp`
- `N_bg` : background (autofluorescence, scattering, out-of-focus fluorescence) —
  **must be measured.** Not computable
- `N_dark` : dark current × t_exp
- `σ_read` : differs pixel to pixel on an sCMOS (fixed pattern). Using the mean
  alone is optimistic

### ⚠ Quantization noise in 12-bit mode swamps read noise

Computing the two modes actually used in the archive:

| Mode | full well | bits | e⁻/ADU | quantization noise `q/√12` | read noise | **effective noise** |
|---|---|---|---|---|---|---|
| `100MHz 16bit` / HDR | 80,000 | 16 | 1.22 | 0.35 e⁻ | ~1.3 e⁻ | **1.35 e⁻** |
| `200MHz 12bit` / Full well | 62,000 | 12 | 15.14 | **4.37 e⁻** | ~1.6 e⁻ | **4.65 e⁻** |

Choosing 12-bit for speed makes the **effective noise 3.4× larger.** On a weak
signal, SNR gets 3.4× worse with it. `full_well` and `bit_depth` are in the
metadata, so this calculation is always possible — it is not inference.

> Read noise itself needs a datasheet check. The quantization term is settled.

### Saturation margin

$$N_{\text{peak}} < 0.7 \times \text{full well}, \qquad
\text{ADU}_{\text{peak}} < 0.9 \times 2^{\text{bits}}$$

`Offset = 100 ADU` (observed) has to be subtracted before computing.

### Target precision → required photon count

Invert the localization expression from §2 for `N`. The lower bound with no
background:

$$N \gtrsim \frac{\sigma_a^2}{\sigma_{\text{loc,target}}^2}$$

Example: `σ_PSF = 97 nm`, `p = 110 nm`, target `σ_loc = 10 nm`
→ `σ_a² = 97² + 110²/12 = 9409 + 1008 = 10417 nm²`
→ `N ≳ 104` detected photons. With background, far more.

---

## 5. Time — exposure, frame rate, motion blur

### Frame period

$$t_{\text{frame}} = \max\!\left(t_{\text{exp}} + t_{\text{overhead}},\; t_{\text{readout}}\right)$$

**Rolling-shutter sCMOS readout scales with row count only.**

The row time can be back-calculated from archive metadata (two independent files
agree):

| ROI height | `Timing-ReadoutTimeNs` | per row |
|---|---|---|
| 176 rows | 1,809,000 ns | 10.28 µs |
| 186 rows | 1,912,000 ns | 10.28 µs |

→ **10.28 µs/row**. From which:

| ROI height | readout | theoretical max fps |
|---|---|---|
| 1608 (full) | 16.53 ms | 60.5 |
| 402 | 4.13 ms | 242 |
| 176 | 1.81 ms | 553 |
| 108 | 1.11 ms | 901 |

**Narrowing the width buys nothing.** The height has to come down. The archive's
crops are mostly square, but if speed was the goal, **a wide short ROI is faster
at the same pixel count.**

### ⚠ In practice only a third of the theoretical value was reached

Observed: 10 ms exposure, ROI 176 rows → camera limit ~85 Hz.
Yet `ActualInterval-ms = 35.67` → **28 Hz measured, duty cycle 28%.**

The camera is not the bottleneck. It is MM overhead, the disk, or the circular
buffer. → the jurisdiction of the compute resources lens (§8), and **the reason
the KB has to record the "measured frame rate," not the "requested frame
rate."**

### Motion blur — decisive in microrheology

If the particle travels farther than the PSF during exposure `t_exp`, the signal
smears. Worse than that is **a systematic bias in the MSD**.

Savin–Doyle correction (one dimension, uniform exposure):

$$\langle \Delta x^2 \rangle_{\text{meas}}(\tau)
= 2D\left(\tau - \frac{t_{\text{exp}}}{3}\right) + 2\varepsilon^2$$

- `−2D·t_exp/3` : dynamic error (blur). **Underestimates** the MSD
- `+2ε²` : static localization error. **Overestimates** the MSD

At short lags the two terms cancel each other and can produce **a plausible but
wrong straight line.** Hand that to GSER as-is and the moduli come out wrong.

**Gate**: the relative bias at the shortest lag `τ_min = 1/f`

$$\left|\frac{t_{\text{exp}}/3}{\tau_{\min}}\right| < 0.1
\quad\Longleftrightarrow\quad t_{\exp} < 0.3\,\tau_{\min}$$

That is, **duty cycle at or below 30%**. The archive's 28% happens to satisfy
this. Pushing to `t_exp = 1/f` (duty 100%) produces a 33% bias at the shortest
lag.

---

## 6. Photobleaching budget

Total photons emitted per molecule:

$$N_{\text{emitted}} = k_{em} \times t_{\exp} \times N_{\text{frames}}$$

Given the dye's `bleach_photons` (mean photons emitted before bleaching):

$$f_{\text{bleached}} = 1 - \exp\!\left(-\frac{N_{\text{emitted}}}{N_{\text{bleach}}}\right)$$

**Gate**: `f_bleached < 0.2` over the whole movie, otherwise an intensity-decay
correction must be possible.

`bleach_photons` is still empty in
[data/fluorophores.yaml](../data/fluorophores.yaml). Without it this gate is
`BLOCKED`, and the qualitative `photostability` grade is not a substitute.
Implemented as `photo.checks.check_photobleaching`, which returns exactly that
`BLOCKED` today with an action naming the missing value.

> Photobleaching is often **superlinear** in illumination intensity (triplet
> pathways). The expression above is a lower bound.

---

## 7. ROI — trading speed against statistical power

Shrinking the ROI buys speed but cuts the particle count in the field.

$$N_{\text{particles}} = c \times \text{FOV}_x \times \text{FOV}_y \times h$$

The statistical error of a microrheology ensemble average is roughly
`1/√(N_particles × N_frames)`. Quartering the area to gain 4× in frame rate
quarters the particle count, so **the net gain can vanish.**

**Gate**: take the target lag range and target error, back out the required
`N_particles × N_frames`, and check that the proposed ROI satisfies it.

---

## 8. Compute resources

### Data rate

$$R = \sum_{\text{streams}} W \times H \times \text{bytes/px} \times f \quad [\text{B/s}]$$

The sum is over **streams, one per camera actually running**. This lab runs two
Kinetix simultaneously, so a dual-camera acquisition is two terms — not one
wider frame. A z-stack or channel loop multiplies a single camera's frames
instead; `Stream.from_dimensions` folds `z × c × positions` into that stream's
`f`, but only as an **average** rate. If the z-sweep is a burst that finishes
well inside one timepoint interval, the instantaneous rate into the buffer is
higher and the buffer gate below comes out optimistic.

| Configuration | Data rate | Verdict |
|---|---|---|
| 1608² · 16bit · 60 fps | **310 MB/s** | NVMe required. A SATA SSD (~500 MB/s) is risky on sustained writes too |
| 1608² · 12bit (stored as 16bit) · 30 fps | 155 MB/s | SATA SSD is fine |
| 176² · 16bit · 550 fps | 34 MB/s | comfortable |
| 2400² · 16bit · 200 fps · **×2 cameras** | **4608 MB/s** | 32× over the measured D: budget — this is the case that produced the RAM-capture detour |

> **bytes/px is not bits/8.** MM stores 9–16 bit in a 16-bit container, so a
> 12-bit mode still costs 2 bytes/pixel. At **8 bit** MMCore reports 1 byte, and
> the Kinetix's 8-bit `Speed` mode is the fast one (500 fps full frame) — so the
> container width moves the data rate by 2× exactly where this gate binds, and
> in the direction that would call a feasible acquisition infeasible. Whether
> this lab's PVCAM adapter really hands MMCore 8-bit pixels rather than
> upconverting **has never been checked**: G12c reports both numbers and refuses
> to call either measured until it is.

### Circular buffer (RAM)

$$\text{buffer} = N_{\text{frames}} \times W \times H \times 2 \text{ bytes}$$

Observed: `CircularBufferFrameCount = 552`, `CircularBufferAutoSize = ON`

| Frame size | 552-frame buffer |
|---|---|
| 176 × 160 | 31 MB |
| 1608 × 1608 | **2.85 GB** |

With `AutoSize ON`, MM sizes it to available RAM. If the buffer cannot absorb the
data rate there are **frame drops**, and they happen silently — the only sign is
`ElapsedTime-ms` intervals turning irregular.

**Gate**:

| # | Criterion | Kind |
|---|---|---|
| G12a | `R < 0.7 ×` sustained disk write bandwidth | hard |
| G12b | the `f` in `R` is an **achieved** rate, not a requested one | bias |
| G12c | the `bytes/px` in `R` is the container MM actually writes | bias |
| G13a | buffer `≥ 5 seconds'` worth of frames (to absorb transient stalls) | hard |
| G13b | `total volume = R × acquisition time < free space` | hard |
| G13c | with real-time processing attached, CPU time per frame `< 1/f_total` | hard |
| G13d | on the RAM-capture path, whole burst `≤` the authorized RAM budget | hard |

MMCore counts its circular buffer in **images**, and shares it across cameras.
So G13a's headroom is `N_buffered / N_arriving_per_second` and the frame
geometry cancels — which is what keeps it correct when two cameras run at
different ROIs. G13c's budget is likewise set by the **total** arrival rate:
two cameras at 200 fps each leave 2.5 ms per frame, not 5 ms.

### G12b — a requested frame rate is not evidence

Every quantity above scales linearly with `f`, and [§C4](06-pitfalls.md) is the
measured case where that mattered: a ~85 Hz camera ceiling delivered 28 Hz, with
MM overhead or the disk — *not* the camera — as the bottleneck. So clearing lens
2's realizability ceiling (G9) is necessary and not sufficient; only an observed
rate closes G12b, and the way to get one is the post-hoc analysis below.

G12b is graded **bias**, not hard: frame-rate realizability belongs to lens 2.
When a requested rate exceeds lens 2's ceiling, lens 3 reports that its own
arithmetic rests on a rate the camera cannot deliver, lets the feasibility grade
collapse, and hands the setting back — it does not seize a verdict it does not
own.

### G13d — the RAM-capture path

Holding the whole burst in memory and flushing afterwards
([`kb/decisions/2026-08-12-ram-buffer-detour-for-disk-bandwidth.md`](../kb/decisions/2026-08-12-ram-buffer-detour-for-disk-bandwidth.md),
implemented in `calibration/ram_capture.py`) removes the real-time disk
constraint entirely — nothing is written while the camera runs — and replaces
G12a with a hard capacity ceiling. G13a still applies: the pop loop draining the
circular buffer into the capture array can stall too, just on CPU rather than
disk. G13b still applies: the burst lands on disk eventually.

The budget is **32 GB** (user, 2026-08-19). The machine has 255.65 GB, but what
the OS, MM, and the DMD/piezo/tweezers control processes hold *during* an
acquisition has never been measured — so 32 GB is an authorized ceiling, not a
measurement of what is free. Anything above it is recorded as an assumption.

Flush time (`total / measured bandwidth`) is reported but not gated: nothing is
lost if it is slow, but "the microscope is tied up for 16 minutes afterwards" is
a fact the user needs before agreeing.

**Post-hoc verification**: ✅ implemented — `compute/drops.py`,
`python -m compute.cli drops <metadata.txt>` for one acquisition and
`scan <dir>` for a sweep. Per `(channel, slice)` series, the **median** interval
is the cadence — a drop can only lengthen an interval, never shorten one, so the
mean is dragged by exactly the thing being detected while the median is not. An
interval clearing both `1.5 ×` cadence and cadence + 2 timestamp ticks is a gap
hiding `round(Δt / cadence) − 1` frames. The second condition only bites on fast
acquisitions, where one tick of MM's 1 ms resolution is already a 1.5× interval
and every tick would otherwise read as a drop.

Read the result as `cadence_fps` vs `throughput_fps`: the gap between them *is*
the drop rate. It cannot distinguish a dropped frame from a genuine stall (stage
move, autofocus, filter change) — it names the frame index and leaves the cause
to whoever knows what the acquisition was doing.

The same pass reports **truncation**: MM's Summary `Frames` is what was
*planned*, and an acquisition stopped early keeps advertising it. That is
tracked separately from contamination, because a short run's lag times can be
perfectly uniform — two calibration runs in this archive are 58 and 44 frames of
a planned 1000, and both are otherwise clean.

Two cautions the real archive taught, both now handled in code (verified
2026-08-20 against `D:\data`, 2,353 files):

- Below a 20 ms cadence the jitter figure is quantization-limited and is
  reported as such. MAD moves in whole 1 ms ticks, so the 10% warn threshold
  would be decided by rounding rather than by the data.
- When the true interval falls between two ticks, the median snaps to one of
  them and `throughput_fps` can come out **above** `cadence_fps`. A real 2.0.3
  acquisition reads median 16.00 ms, mean 15.63 ms, intervals alternating 15/16.
  Both are reported; the mean is the honest one there.

---

## 9. Hard gate summary

All decided in code. If even one fails, the proposal is void.

| # | Gate | Criterion | Required input | If missing |
|---|---|---|---|---|
| G1 | Excitation coupling | `ex_eff > 0`, ≥ 20% of ideal | dye absorption, source, excitation path | BLOCKED |
| G2 | Emission collection | `spectral_collection ≥ 15%` | dye emission, emission path, QE | BLOCKED |
| G3 | Excitation blocking | `≥ 5 OD` (7 OD with approximate spectra) | emission path curves | BLOCKED |
| G4 | Crosstalk | `< 5%` | all channel spectra | BLOCKED |
| G5 | Sampling | per task (§2) | NA, pixel pitch, magnification, **task kind** | ask |
| G6 | Saturation margin | `peak < 0.7 × full well` | full well, photon budget | BLOCKED |
| G7 | SNR | at or above target | measured light level, measured background | BLOCKED |
| G8 | Motion blur | `t_exp < 0.3 τ_min` | D or τ_c | ask |
| G9 | Frame-rate realizability | `f ≤ 1/max(t_exp, t_readout)` | row time, ROI | computable |
| G10 | Photobleaching | `< 20%` over the whole movie | `bleach_photons`, photon budget | BLOCKED |
| G11 | Statistical power | target error met | particle concentration, target precision | ask |
| G12 | Data rate | a `< 0.7 ×` disk bandwidth · b `f` is achieved not requested · c container width is the one MM writes | measured disk bandwidth, achieved fps, confirmed bytes/px | measurement required |
| G13 | Buffer · capacity · CPU · RAM | a `≥ 5 seconds' worth` · b fits free disk · c CPU/frame `< 1/f_total` · d RAM burst `≤` budget | RAM, frame size, duration, free disk | computable |
| G14 | Tweezers sampling | `f_s ≥ 10 f_c` | κ, viscosity, particle radius | BLOCKED |
| G15 | NA feasibility | `NA ≤ n_immersion` | NA, immersion medium | BLOCKED |
| G16 | Working distance | free WD `≥` imaging depth | WD, imaging depth, coverslip | BLOCKED |
| G16b | Depth within chamber | chamber height `≥` imaging depth | chamber height, imaging depth | skipped (INFO) |
| G16c | Near-wall drag bound | `9a/(16h) ≤ 10%`, **upper bound** (absorbed if trapped) | particle radius, imaging depth, trap state | skipped (INFO) |
| G17 | Refractive-index mismatch | `depth × \|Δn\| ≤ 1.85 µm` (screening) | immersion n, medium n, depth | BLOCKED (depth); medium n defaults to the settled 1.333, but ATPS/birefringent media BLOCK |
| G18 | Coverslip thickness | `\|actual − design\| ≤ 5 µm`, or collar adjusted | coverslip thickness | assumed (design value) |
| G19 | Count in field · overlap | nearest neighbour `≥ 3 ×` resolution | concentration, field size, λ_em | skipped (INFO) |
| G20 | Saturation · triplet shelving | excited-state fraction `≤ 0.1` | irradiance, ε, lifetime | BLOCKED |
| G21 | Light-driving | irradiance `<` sample threshold | irradiance, measured threshold | BLOCKED if photoresponsive; **warns if never asked** |
| G22 | Total dose | `≤` stated ceiling | irradiance, exposure plan | reported (INFO) |
| G23 | Bias ledger | every bias that damages this quantity is absent, or cleared by a correction that exists | other lenses' verdicts, declared corrections | BLOCKED |
| G24 | Pixel calibration | measured, when the quantity needs it | measured pixel size | BLOCKED |
| G25 | Photometric calibration | background · dark · flat-field measured | those frames | BLOCKED |
| G26 | Post-processing | no linearity-breaking filter | declared filters | BLOCKED |
| G27 | Committee coverage | every standing lens returned, none BLOCKED | other lenses' verdicts | BLOCKED |
| G28 | PFS lock | on **and** In Range, both recorded | both metadata flags | BLOCKED |
| G29 | Axial drift | total drift `≤ 0.5 ×` depth of field | measured drift rate, DOF | BLOCKED |
| G30 | Lateral drift | total drift `≤` tolerance | measured drift rate, tolerance | skipped (INFO) |
| G31 | Sedimentation | settling `≤` depth of field | radius, Δρ, viscosity | BLOCKED |
| G32 | Evaporation | `≤ 5%` of volume lost | sealed, or a measured rate | warns unquantified |

G15–G19 are lens 4's, G20–G22 lens 5's, G23–G27 lens 6's, G28–G32 lens 8's; the
numbers are new. This table previously stopped at G14 because lenses 4 and 8 had
no gate IDs at all, lens 5 had only G10 and lens 6 only G11.

G23–G27 read **other lenses' verdicts** rather than hardware facts, which is
why lens 6 has to run last.

**G23 is not a count.** Two tables in `validity/setup.py` do the work the count
cannot:

- `BIAS_SCOPE` says which calibrations a bias damages, so the FAIL lands on the
  affected physical quantity instead of the session. Motion blur ruins an MSD
  and leaves an integrated intensity alone; bleaching is the reverse. A bias the
  table does not scope damages **every** quantity — the conservative default,
  and the honest one where nothing in these docs scopes it (light-driving and
  saturation move the sample itself, crosstalk puts another channel's particles
  in the frame). Out-of-scope biases are named in the verdict, not dropped: they
  still stand against the quantities they do damage.
- `CORRECTIONS` and `UNCORRECTABLE` say whether a declared correction exists at
  all. Declaring `geometry.ri_mismatch` used to clear it, because the
  declaration was matched against nothing; now the gate answers that no such
  correction is implemented and keeps the bias. A code in neither table is
  accepted — a gate the tables have not caught up with should not block work —
  but it costs the verdict its `measured` grade, so an unaudited clearance
  cannot advance.

Together those let one session report a biased MSD and a sound intensity
profile: pass `intended_quantities` and each is judged separately, with the
aggregate carrying every per-quantity verdict.

**`BLOCKED` is not `FAIL`.** FAIL means "this setting is physically bad";
BLOCKED means "there is no basis on which to decide." Neither advances to the
next step, but the action differs: FAIL means change the setting, BLOCKED means
**go measure or go find the datasheet.**

---

## 10. Implementation status

| Section | Content | Status |
|---|---|---|
| §2 diffraction · collection | `Objective.resolution_nm`, `collection_efficiency`, `depth_of_field_nm` | ✅ covered by tests |
| §3 photon budget | `Channel.detected_e_per_s` (`None` without a light level) | ✅ covered by tests |
| §3 spectra | excitation efficiency · collection · blocking · crosstalk | ✅ covered by tests |
| G1–G4 | `optics.gate.evaluate` | ✅ covered by tests |
| §2 sampling gate (G5) | task-dependent branch, `detection.gate.evaluate` | ✅ covered by tests (2026-08-11) |
| §4 SNR · saturation (G6, G7) | `detection.gate.evaluate` | ✅ covered by tests (2026-08-11) |
| §5 timing · blur (G8, G9) | `detection.gate.evaluate` | ✅ covered by tests (2026-08-11) |
| §6 bleaching (G10) | `photo.gate.evaluate` | ✅ covered by tests (2026-08-12) — BLOCKED on the real instrument until `power_at_sample_mw` and `bleach_photons` exist |
| §5 dose · saturation · light-driving (G20–G22) | `photo.gate.evaluate` | ✅ covered by tests (2026-08-12) |
| §7 statistical power (G11) | `validity.gate.evaluate` | ✅ covered by tests (2026-08-12) |
| bias ledger · calibrations · post-processing (G23–G27) | `validity.gate.evaluate` | ✅ covered by tests (2026-08-12); bias scoping + correction registry + per-quantity verdicts added 2026-08-20 |
| drift · settling · evaporation (G28–G32) | `stability.gate.evaluate` | ✅ covered by tests (2026-08-12) — G29 BLOCKED until a drift rate is measured |
| §8 compute resources (G12, G13) | `compute.gate.evaluate` | ✅ covered by tests (2026-08-11) |
| §9 tweezers (G14) | `trapping.gate.evaluate` (corner frequency → required fps) | ✅ covered by tests |
| sample geometry (G15–G19) | `sample.gate.evaluate` (RI mismatch, WD, coverslip, overlap) | ✅ covered by tests (2026-08-12) |
