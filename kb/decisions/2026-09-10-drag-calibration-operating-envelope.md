---
id: 2026-09-10-drag-calibration-operating-envelope
question: "What frame rate, ROI and acquisition length can a Stokes-drag trap calibration on a 5 um DragonGreen bead actually use, and which constraint sets each one?"
date: 2026-09-10
status: current
---

# 2026-09-10 · Operating envelope for the 5 µm drag calibration

Computed from lenses 2, 3 and 7 during the gate-by-gate review. **Not a
measurement** — every number here is arithmetic over measured inputs, and the
two inputs that are *not* measured are named at the bottom. The plan for the run
itself goes to `kb/plans/` once lenses 4–8 have returned; lens 8 is still
BLOCKED for want of a drift rate.

Sample and optics fixed: `bangs-dragongreen-5um-cooh` (4.95 µm, confirmed by KH
2026-09-10), `100x-Oil` at 1×1, **0.06453 µm/px** measured, Kinetix22 /
Kinetix_blue, Aura CYAN, ~9 µm above the coverslip.

## The mode is not a choice

| mode | verdict |
|---|---|
| **DynamicRange** (16 bit, well 15000, 3.749 µs/row) | **the only usable mode** |
| SubElectron (16 bit, well 1000, 60.1 µs/row) | caps at **130 fps** → fails G14's 132 |
| Sensitivity (12 bit, well 1000, 3.5312 µs/row) | cannot reach SNR 10 |
| Speed (8 bit, well 200, 0.625 µs/row) | cannot reach SNR 10 |

The two failures are the same arithmetic. `detection.photometry.snr` charges the
**whole spot's** read noise against the **peak pixel's** signal, and the bead
covers 4988 px at 1×1, so `n_pix·σ_read²` is 12,769 e⁻² in DynamicRange and SNR
10 needs about **899 e⁻ in the peak pixel**. Against G6's 0.7 × full-well rule
that rules out any mode with a well below ~1284 e⁻ — which is three of the four.

⚠ **That convention is worth a look before it is leaned on.** Peak-pixel signal
against summed read noise is internally inconsistent (a summed signal belongs
with a summed noise), and it is the single assumption that eliminates two modes.
With `n_pix = 1` all four modes clear SNR 10. Raised for lens 2, not settled.

## Two axes, and they are independent

At the readout limit — which is where this runs — the frame period is
`H × row_time` and the data rate is `W × 2 bytes / row_time`:

- **ROI width sets the data rate and nothing else.** G12a's 145 MB/s budget
  (0.7 × 206.8) gives **W ≤ 271 px**.
- **ROI height sets the frame rate and nothing else.** `fps = 1/(H × 3.749 µs)`.

**Reducing ROI height does not reduce the data rate.** 512×1024, 512×512,
512×256 and 512×128 all sit at 290 MB/s, because halving the height doubles the
rate. This is the single most useful fact in the lens and G12a's own action text
(*"Reduce ROI, frame rate, or stream count"*) does not say it.

## The envelope, at W = 256 px (136 MB/s throughout)

| ROI H | fps | exposure ceiling (duty ≤ 30 %) | CYAN needed | buffer for 5 s | G14 |
|---|---|---|---|---|---|
| 128 | **2084** | 0.144 ms | 94 ‰ | 10,420 | ok |
| 192 | 1389 | 0.216 ms | 63 ‰ | 6,947 | ok |
| 256 | 1042 | 0.288 ms | 47 ‰ | 5,210 | ok |
| 384 | 695 | 0.432 ms | 31 ‰ | 3,474 | ok |
| **512** | **521** | 0.576 ms | 23 ‰ | 2,605 | ok |
| 1024 | 260 | 1.152 ms | 12 ‰ | 1,303 | ok |
| 2021 | **132** | 2.273 ms | 6 ‰ | 660 | **limit** |
| 2400 | 111 | 2.699 ms | 5 ‰ | 556 | fails |

**Usable frame rate: 132 – 2084 fps**, and neither end is set by the gate a
reader would guess:

- the **ceiling** is the bead, not the exposure or the duty cycle. 4.95 µm is
  77 px and the drag excursion adds up to 15 px, so the ROI cannot go below
  ~128 rows. The exposure would allow 12 rows.
- the **floor** is G14, `f_s ≥ 10 f_c`, at the measured κ ≈ 3.87 pN/µm
  (`2026-09-03-three-subsystems-first-light.md` §9) giving f_c = 13.2 Hz.

## Capacity

8.19 GB/min at W = 256.

| duration | volume | disk (2559 GB free) | RAM (32 GB authorized) |
|---|---|---|---|
| 1 min | 8.2 GB | ok | ok |
| **3.9 min** | 32 GB | ok | **RAM limit** |
| 30 min | 246 GB | ok | exceeded |
| **5.2 h** | 2559 GB | **disk limit** | exceeded |

The RAM-capture path buys 3.9 minutes here, which is ample for a velocity sweep
of 5–30 s steps but not for a continuous run. Note the 32 GB is an
authorization, not a measurement — the machine has 255.65 GB and what the OS,
MM and the control processes hold during acquisition has never been measured
(`compute/checks.py` LIMITS, user 2026-08-19).

## The operating point chosen inside it

**ROI 256 × 512 · exposure 0.45 ms · CYAN 36 ‰ · 520 fps · DynamicRange 16-bit ·
CircularBufferFrameCount 3200**

```
lens 2   PASS               frame_rate 1.00  sampling 1.07  snr 1.19
                            motion_blur 1.28  saturation 7.40
lens 3   PASS_WITH_CHANGES  data_rate 1.06   buffer 1.23    136 MB/s
```

Chosen off the boundary deliberately: solving for the limits put snr,
motion_blur and frame_rate all at exactly 1.00 at once, which is a solution and
not a setting. 256 px of width is 16.5 µm, against the 12.4 µm that 192 px gives
— the narrower ROI has more data-rate headroom (1.42) and less room for the bead
plus its 1 µm excursion.

## A correction this produced

Earlier runs in this review passed `--row-time-us 3.5312` while asking for
DynamicRange. **3.5312 µs is Sensitivity's measured row time; DynamicRange is
3.749 µs**, so those numbers were 6.2 % optimistic: 553 fps was really 521, the
duty-limited exposure 0.542 ms was really 0.576, and G12a's width ceiling 256 px
was really 271.

The useful residue is an evidence fact: **only Sensitivity has a measured row
time** on this camera (`kb/calibrations/camera-readout.yaml`, 8,475,000 ns over
2400 rows). DynamicRange's 3.749 is a datasheet value, which is why lens 2
reports `evidence: assumed` once the override is removed — correctly.

## What would change this

- **A measured row time for DynamicRange.** One full-frame readout timing on
  that mode moves lens 2 from `assumed` to `measured` and is the cheapest of
  the three open items.
- **A measured achieved frame rate** (`compute.cli drops` on an acquisition's
  own `ElapsedTime-ms`, taken as the span over `n−1` intervals since that
  metadata is quantised to 1 ms). This is the only route to `fps_source =
  "measured"` and therefore the only way lens 3 can advance.
- **A disk bandwidth measured in the confirmed Micro-Manager save directory.**
  `kb/calibrations/disk-bandwidth.yaml` flags its own 206.8 MB/s as measured
  somewhere else, and G12a multiplies it by 0.7.

## Falsifying condition

An acquisition at the recommended point whose `ElapsedTime-ms` series gives an
achieved rate materially below 520 fps. `docs/06 §C4` is precisely that case —
an 85 Hz ceiling delivering 28 Hz with MM overhead, not the camera, as the
bottleneck — and nothing in this envelope accounts for MM overhead, because no
measurement of it exists. If the achieved rate comes in low, every row of the
table above is a ceiling rather than a rate, and the frame-rate floor (G14's
132 fps) is the number at risk.

Second falsifier, narrower: if `n_pix_spot` in the SNR convention is changed to
the peak pixel, three modes come back and the "DynamicRange is the only usable
mode" conclusion is void. That is a lens 2 question and it is open.
