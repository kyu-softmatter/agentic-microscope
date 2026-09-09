# The existing MATLAB microrheology pipeline

The analysis this lab already runs, saved here on 2026-09-07 because the
real-time tracking GUI ([`kb/decisions/2026-09-07-realtime-tracking-gui-scope.md`](../../kb/decisions/2026-09-07-realtime-tracking-gui-scope.md))
has to reproduce its quantities live, and "reproduce" needs the originals to
check against rather than a description of them.

**These files are the specification, not a starting point to be improved.**
They encode choices that were made against real data — the exposure-blur
correction floor, the moving-mean detrend during flow, the signed-log median
across replicates — and a live reimplementation that quietly differs in any of
them produces numbers that cannot be compared with any previous result.

Provenance: six came from the user (KH) on 2026-09-07;
`position_tracking_5um.m` came from Saksham's Box folder
(`Takatori Group/Saksham/20260505_LambdaDNA_60SS_3c_5um`) and is his.

---

## The data contract every one of them assumes

This matters more than any single script, because the GUI has to either meet it
or deliberately break it:

| | Value | Where |
|---|---|---|
| Position files | plain text, **2 columns `x y` in PIXELS**, one row per frame | all |
| Two-bead files | 4 columns `Left_x Left_y Right_x Right_y`, **with a header** | `*_2particle.m` |
| `px_to_um` | **0.065** µm/px | hardcoded in every file |
| `frame_time` | **0.02** s (some files 0.020407) | hardcoded in every file |
| `a_um` | 2.5 µm (5 µm bead radius) | hardcoded |
| `kT_um` | 4.045e-3 pN·µm → **T = 293 K = 20 °C** | hardcoded |

⚠ **`frame_time` is hardcoded, never read from metadata.** On this instrument
the achieved frame period equals the exposure (the camera does not honour a
requested interval), so an acquisition at any exposure other than 20 ms
silently puts every frequency axis, every PSD and every diffusivity out by the
ratio. Either acquire at 20.0 ms exposure or edit `frame_time` to the *measured*
period — and measure it from the timestamp column, not from the setting.

⚠ `px_to_um = 0.065` is the **1×1 unbinned** 100x-Oil value. At 2×2 it is
0.130. Nothing in these scripts detects binning.

⚠ **And since 2026-09-09 this repository disagrees with it.** `0.065` is
`6.5/100`, the nominal quotient. Two independent length standards driven 10 µm
at 100× on 2026-09-03 — the closed-loop piezo and the AOD trap, agreeing to
0.24 % — give **0.06453 µm/px**, which `data/pixel_size.yaml` now carries as
`measured` and the seven `.cfg` files match.

The MATLAB value is **left alone here on purpose**: this file documents what
`D:\codes` does, and editing that pipeline is not this repository's to do. What
matters is that the gap is 0.73 %, that it is inside the agreement the operator
stated, and that **every quantity these scripts produce carries it** — the
scaling is not the same for all of them, since `px_to_um` enters displacement
linearly and `⟨x²⟩` quadratically. Lens 6 is the lens that owns whether the
analysis code's assumptions match the settings, and this is exactly the kind of
mismatch it is for.

Filenames carry the metadata, and the parsers are strict:

```
<tag>_passive_<power>_OT<otfactor>_<rep>_5um.txt          # trap held, no drive
<tag>_creepx_<speed>umps_<power>_OT<otfactor>_<rep>_5um.txt   # stage driven
```

`power = <power> * <otfactor>` (base laser setting × OT attenuation). `passive`
⇒ speed 0. A file that does not match is skipped, sometimes silently.

---

## The files

### `position_tracking_5um.m` — stage 1, images → positions
Scans first-level subfolders for a TIFF/OME-TIFF stack, thresholds each frame
(fixed `img_cut = 300`, Otsu fallback), keeps the **largest connected
component**, and takes its **intensity-weighted centroid**. Writes the 2-column
pixel `.txt` every other script reads. `min_area_px = 20²` rejects specks;
`clip_max = 2000` clips hot pixels before weighting.

This is the function the GUI replaces with a live tracker. Note what it is
*not*: no sub-pixel Gaussian fit, no linking between frames, no drift
correction. One bead per frame, chosen by area.

### `plot_single_particle.m` — QC
Per file: phase plot (y vs x, coloured by time), x(t)/y(t), and MSD_x/MSD_y
log-log with a slope-1 reference. `msd1d` is the plain all-pairs estimator,
`mean((x(1:end-lag) - x(1+lag:end)).^2)`. Skips the first 300 frames of any
`creepx` file (flow transient).

**This is the closest existing analogue to the GUI's job** — the same three
views, computed after the fact instead of live.

### `fit_comprehensive_microrheology_v4.m` — κ and G*, from the passive PSD
The most complete single-bead analysis. Groups files by parsed power, Welch-PSDs
each trace (`pwelch`, `nfft = 2048`, Hann, 50 % overlap), averages the spectra
across replicates, then does two independent things:

1. **Oldroyd-B fit.** `lsqnonlin` on the log-PSD against
   `chi = 1/(k + i·omega·g*(omega))`, `g* = gamma_s + Σ gamma_p,i/(1 + i·omega·lambda_i)`
   for 3 modes — returning **κ jointly with the medium's viscosities and
   relaxation times**. Seeded from equipartition, `k_init = kT/var(x)`, and
   bounded to [0.5, 2]·`k_init`.
2. **Kramers-Kronig inversion.** `Im{chi} = -omega·S_xx/(2kT)` from the FDT,
   `Re{chi}` by principal-value integral (no power-law assumption), then
   `G* = (1/chi - k)/(6·pi·a)`.

So **two of the three trap stiffnesses the 2026-09-07 experiment wanted already
exist here**: equipartition (`kT/var`) and full-PSD-shape (`k_fit`).

### `plugflow_fluctuations_passive_moduli_v8.m` — G* under flow
Single-bead, passive vs stage-driven at matched trap power. Three interchangeable
extraction methods (`fluct_method`): `kk` (as above), `tassieri` (normalised
position autocorrelation → Evans Fourier transform, eq. 9), `mason` (MSD →
GSER with a local log-slope `alpha`).

Two details that are easy to get wrong and are load-bearing:

- **Exposure blur is deconvolved**, not ignored: `H² = sinc²(pi·f·T_e)`, and
  `PSD /= max(H², 0.4)`. The 0.4 floor stops the correction exploding where the
  sinc goes to zero.
- **κ during flow uses a detrended variance.** `estimate_kappa_from_component`
  with `mean_method = 'linear'` or `'moving'` (2 s window) removes the
  drag-induced mean displacement so the variance is fluctuation only. Passive
  files use `'none'` — the whole trace.

⚠ **The mean displacement it removes is exactly what a Stokes-drag stiffness
calibration needs** (force balance `kappa = gamma·v/x_eq`). This pipeline
discards it by design. **No script here computes κ from drag** — that was the
one genuinely missing piece found on 2026-09-07, and it is still missing.

### `plugflow_fluctuations_passive_moduli_2particle.m` — two beads
The same, on 4-column files, per bead (Left/Right). Adds a cleaner trap
calibration: `kappa = 2·kT / MSD_plateau`, the plateau taken as the median of
the last 20 % of the MSD curve of the passive file at matched power.

### `dashboard_xy_group_by_power_speed.m` / `..._with_passive_2particle.m`
Overview grids: phase plots and averaged MSDs grouped by (power, speed), passive
as the speed-0 reference, coloured by speed or Weissenberg number. The 2-particle
version does both beads side by side with shared axes.

⚠ Their `msd1d` ends with `MSD = MSD - MSD(1)`, which subtracts the lag-1 value.
That suppresses the localisation-noise offset and **also removes real signal at
short lag** — do not copy it into anything that reports a diffusivity.
`plot_single_particle.m`'s version does not do this.

---

## What the GUI needs from this, shortest path

Live, per frame: centroid (from `position_tracking_5um.m`'s weighted-centroid
recipe, or better), brightness/flux, and a rolling window feeding

- `var(x)`, `var(y)` → `kappa = kT/var` (equipartition)
- `msd1d` on the window → short-lag slope → `D = slope/2`, and the plateau →
  `kappa = 2kT/MSD_inf`
- `pwelch` → corner frequency, and the exposure-blur correction above

Every one of those is ~10 lines and already written down here. The hard part is
not the mathematics, it is the **frame stream**: see the scope document.
