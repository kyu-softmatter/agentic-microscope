# 2026-09-07 · Real-time particle-tracking GUI — scope

**Goal (user, 2026-09-07):** a real-time GUI for particle tracking that shows
how bright the particle is, its Brownian-motion statistics, and its
diffusivity — so that the numbers the MATLAB pipeline currently produces hours
later are visible while the bead is still in the trap.

**Status:** scoped, not built. The display half largely exists; the measurement
half does not, and the two cannot be the same stream.

---

## 1. What already exists

[`config/micromanager/live_view.py`](../../config/micromanager/live_view.py)
(1131 lines) is most of a viewer already:

| Capability | Flag | Measured cost |
|---|---|---|
| Live view, stdlib Tk (zlib+base64 PNG) | *(default)* | 43.1 ms / 800² frame |
| Live view, native window | `--cv2-window` | 11.8 ms / 800² frame |
| Bead detect + isolation count, decimated frame | `--track` | ~15 ms (HoughCircles) |
| Bead detect on the **full** 2400² frame | `--gpu` | 18.7 ms GPU vs 90.6 ms CPU |
| Copy frames to shared memory | `--publish NAME` | `runtime/shmview.py` |
| Display someone else's segment, no camera | `--attach NAME` | |

`--publish`/`--attach` is the important one and it already solves the hardest
problem: PVCAM gives a Kinetix to one process at a time, so while a trapping
script owns the camera nothing else can see it. A publisher inside the acquiring
process plus a subscriber in a viewer means you can watch a run **without a
second device claim and without dropping the trap** — and on this instrument
dropping the trap is the expensive move (SAFETY.md §1).

## 2. The blocker, stated plainly

`live_view.py`'s own docstring:

> All of them are for **choosing a field**, never for measuring one. This
> samples the newest frame out of a 30 fps stream and drops the rest by design,
> so no MSD can come out of it.

That is not a limitation to be fixed in place — it is the correct design for a
viewer. A display loop must drop frames to stay responsive. But:

- **Brightness** needs the newest frame. Decimation is fine.
- **Variance / equipartition κ** needs a large *unbiased* sample. Dropped frames
  are acceptable if the drops are not correlated with position, which for a
  display tick they roughly are not.
- **MSD, D, and any PSD** need a **gap-free series with true per-frame
  timestamps**. A dropped frame does not just lose a point, it corrupts the lag
  axis: `msd1d` in every MATLAB script indexes lag by *row offset*, so one
  missing row silently relabels every subsequent lag.

So the GUI cannot compute diffusivity from the frames it displays. This is the
whole architectural point of the design below.

## 3. The shape that follows

```
   acquiring process (owns the camera)          viewer process (owns nothing)
   ┌────────────────────────────────┐           ┌──────────────────────────┐
   │ drain EVERY frame + ElapsedTime│           │  image panel             │
   │   ├─ centroid + flux  ─────────┼──stats──▶ │  flux(t)                 │
   │   ├─ ring buffer (N frames)    │  channel  │  x(t), y(t), phase plot  │
   │   ├─ rolling var → kappa       │           │  MSD log-log + slope-1   │
   │   ├─ rolling MSD → D, plateau  │           │  kappa, D, f_c readouts  │
   │   └─ publish newest frame ─────┼──shm ───▶ │                          │
   └────────────────────────────────┘           └──────────────────────────┘
```

- The **acquirer** is the only thing that touches the camera, and it is the only
  thing entitled to compute statistics, because it is the only thing that sees
  every frame. `config/session/run_wall_diffusion.py` already drains
  gap-free with `ElapsedTime-ms` per frame — that is the frame-handling model to
  reuse, not `live_view.py`'s.
- The **viewer** is `live_view.py --attach` plus panels. It never owns a device,
  so it can be opened, closed and restarted mid-run freely.
- The **stats channel** is small structured data (a few floats per tick), not
  images. `runtime/shmview.py` handles the image side already; the stats side
  can be a second small segment or a JSON line stream — deliberately not decided
  here.

## 4. What to compute, and the traps in each

All of these are ~10 lines and are already specified by
[`analysis/matlab/README.md`](../../analysis/matlab/README.md). The value of
this section is the failure mode next to each.

| Quantity | From | Trap |
|---|---|---|
| Brightness / flux | sum over the bead mask, background-subtracted | The camera is 12-bit in Sensitivity mode (ceiling 4095) and a bead has already read 3500. Report % of ceiling and refuse to quote a flux that clipped. |
| Centroid | intensity-weighted, largest connected component | Matches `position_tracking_5um.m`. No sub-pixel fit, no frame-to-frame linking — a second bead entering the window silently steals the track. |
| `var(x)`, `var(y)` → κ | equipartition, `kT/var` | Needs detrending if anything drifts. And on this sample it does not distinguish held from **stuck** (see §5). |
| MSD → D | short-lag slope / 2 | Motion blur at 20 ms suppresses short-lag MSD; the pipeline's `sinc²` deconvolution with a 0.4 floor is the correction to port. Do **not** copy the dashboards' `MSD - MSD(1)`. |
| MSD plateau → κ | `2kT/MSD_inf` | Only valid once the window is ≫ the corner time `1/(2·pi·f_c)`. Show the window length against that, or the plateau is just the longest lag. |
| PSD, `f_c` | Welch, `nfft` ~2048 | Aliasing: needs `fps >= ~10·f_c`. At 50 fps that caps the κ this can honestly resolve. Compute the implied ceiling and display it. |

**Every readout must carry its own validity condition on screen.** A κ from a
2-second window on a bead whose corner frequency implies a 30-second
correlation time is not a soft number, it is a wrong one, and a bare digit in a
GUI will be believed.

## 5. The finding that makes this GUI worth building

2026-09-07: two catch attempts, both reported **AMBIGUOUS** on excursion
(183 nm, 159 nm — inside the instrument's 110–220 nm hysteresis band), and both
then failed the ramp test — a bead stayed at the start while the trap moved
14.8 µm and 33.7 µm away. Both beads were **stuck to the coverslip**, and the
excursion statistic could not tell that.

This is exactly the failure a live statistics panel would have shown in seconds
instead of two full catch cycles: a stuck bead and a held bead have similar
variance, but their **MSD shapes differ** (a stuck bead has no rollover to a
plateau at the trap's corner time — it is flat from the first lag, at the
localisation-noise floor). The panel that would have caught it is the MSD
log-log with a slope-1 reference, live — which is `plot_single_particle.m`
figure 3, computed while the bead is still there.

So the GUI is not a convenience. **It is the instrument that would have saved
today**, and the ramp test stays mandatory regardless (only moving the trap
proves a catch).

## 6. Deliberately not decided

- The stats-channel format (second shm segment vs JSON lines).
- Whether the panels are Tk (stdlib, already the fallback path), cv2 (fast, no
  widgets), or matplotlib/Qt (now installed, per `requirements-analysis.txt`).
- Whether the live tracker keeps `position_tracking_5um.m`'s threshold+largest-
  component recipe or moves to the `refine()` centroid the closed-loop tracker
  in `config/tweezers/trap_from_tracking.py` already uses (866 µs on CPU, and
  measured *slower* on GPU — do not port it to CuPy).

## 7. Prerequisite that outranks all of it

There is still **no valid px→trap-µm calibration at 1×1**. Today's
`trap_from_tracking.py calibrate` run failed its own checks (anisotropy 197.5 %
against a 5 % bound; bead followed 3–4 % of the commanded drive) because the
bead it seeded on was not trapped. The stored transform remains the 2×2 one from
2026-09-06. Any GUI that reports positions in trap micrometres at 1×1 is
reporting through a transform that does not exist yet.
