---
id: dualcam-sorting-session-brief
question: "How should a fresh session pick up the dual-camera + optical-tweezers
  particle-sorting work without re-deriving what 2026-09-05 already established"
source: session synthesis
expert: KH
date: 2026-09-05
confidence: medium
scope: "current-laser / current-aura paths, Kinetix22 x2, Aresis Tweez 300"
applies_to_systems: [current-laser, current-aura]
review_after: 2026-12-05
supersedes: null
---

## Purpose

The 2026-09-05 session established a lot that is expensive to re-derive and easy
to get wrong. This is the handover. **Read §1 before touching hardware** — three
of the five items there fail silently.

The goal that motivates it: **spatially sort two particle species with the
optical trap, one to the left and one to the right, under real-time dual-camera
view.**

---

## 0. Paste-ready opening prompt for a fresh session

> We are doing dual-camera imaging with the optical tweezers, and the goal is
> **spatial sorting**: detect two fluorescent particle species in real time and
> use the trap to move one species left and the other right.
>
> Our particles sediment onto the coverslip and undergo Brownian motion there,
> so treat the working system as **2D at the glass**, not a bulk suspension.
>
> Start by reading, in this order:
> `kb/systems/dualcam-sorting-session-brief.md` (this file — the state and the
> plan), `kb/systems/dualcam-config-corrections-pending.md` (what is wrong with
> the config file and what is read-only), and `data/particles.yaml` (the
> particles, and the `materials:` refractive-index fallback).
>
> Do not re-derive the numbers in those files. Do not trust a vendor datasheet
> without checking it against the instrument — one of ours is demonstrably
> wrong. Do not trust a tweezers return code as evidence that anything
> happened.
>
> Tell me what is blocking the sort before proposing settings.

---

## 1. Pre-flight — five checks, three fail silently

| # | check | correct value | if wrong |
|---|---|---|---|
| 1 | `CSUW1-Port` | **`blue_red` / State 1** | **SILENT.** `Kinetix_blue` gets no light. The cfg never sets this — see corrections §2 |
| 2 | `CSUW1-Filter_Blue` | **position 2** = FF01-515/30 | **SILENT.** Position 9 `open` = no emission filter at all |
| 3 | `CSUW1-Filter_Red` | **position 4** = FF01-680/42, *or* **position 3** = FF01-595/31 — measure which (§5.2) | **SILENT.** `multi` passes everything, so the red arm also sees green emission |
| 4 | all six `PP` flags, **both** cameras | `No` | data is modified irreversibly; reverts on every config load |
| 5 | `LappMainBranch1` | **State 1** (ignore the label — it lies) | no light at all, and it looks like a dead dye |

Checks 1–3 were all in the wrong position at some point during 2026-09-05.

Then: peaks near **1500–2500 ADU** (ceiling is 4095, 12-bit — a bead already hit
3500 at 5% power), and `PFS-FocusMaintenance` on for anything long.

---

## 2. Recommended particles

### Use now: the two carboxyl beads

`bangs-dragongreen-5um-cooh` (FCDG008 lot 14941) + `abvigen-red-5um-cooh`
(AFR-0500-COOH). They straddle the 561 nm splitter, so **one lands on each
camera**, and they are otherwise matched: 4.95 vs 5.0 µm, both carboxyl, bulk D
within 0.7%.

**Do not use `abvigen-blue-4um-nh2` for sorting.** Amine is positive near
neutral pH and clean glass is negative, so it is electrostatically **attracted**
to the coverslip. For a sample that already sits on the glass, that is the
difference between a bead you can drag and a bead that is stuck. Its 450 nm
emission also shares `Kinetix_blue` with Dragon Green, so the splitter cannot
separate it from the green bead anyway.

### Buy this: Bangs FCFR008, Flash Red 5.0 µm carboxyl PS

The single highest-value procurement. It is on the same catalogue page as
FCDG008 — `Fluorescent Carboxyl Polystyrene`, 4.80–5.20 µm spec — so it gives a
pair that differs **only in the label**: same vendor, same size spec, same
PS/DVB-COOH chemistry, same ~1% solids format, and a real lot certificate.

That matters because **the Abvigen red particle's datasheet is wrong.** It
claims 620 nm excitation; on the instrument it was excited by CYAN and GREEN
(max at GREEN) and **not at all by RED**, the reverse of what 620 nm predicts.
Bangs' data, by contrast, verified: its lot titer and sphere geometry reproduce
the quoted 23.8 Å² parking area to 4.6%, and the lot description confirmed
Dragon Green's 480/520.

⚠ One thing to confirm before ordering: **that Flash Red's emission sits above
561 nm**, so it reflects to `Kinetix_red`. Ask Bangs for the dye peaks and a lot
sheet. Its siblings at 5.0 µm — Envy Green (FCEG008) and Glacial Blue
(FCGB008) — both emit **below** 561 nm and would share a camera with Dragon
Green, so Flash Red is the only 5 µm sibling on that page that straddles the
splitter.

---

## 3. Recommended setup for sorting

### Objective: 40x WI — and this is an imaging decision, not a trapping one

`kb/expertise/oil-objective-trapping-in-water.md` settles it directly: for a
bead far larger than the focus, stiffness is set by the bead's own geometry, so
40x WI / 60x Oil / 100x Oil **agree within 3%** (0.433 / 0.421 / 0.421 pN/µm per
mW on a 4 µm PS bead). Its conclusion, quoted: *"the objective choice is an
imaging decision, not a trapping one — pick on effective pixel size and field of
view."*

On that basis 40x WI wins for sorting:

| | field (2400²) | µm/px | 5 µm bead | Brownian step / 30 ms |
|---|---|---|---|---|
| 100x Oil | 156 µm | 0.065 | 77 px | 0.7 px |
| **40x WI** | **390 µm** | 0.163 | 31 px | 0.3 px |
| 20x | 780 µm | 0.325 | 15 px | 0.1 px |

A 390 µm field gives real room for a left bin and a right bin; 156 µm is cramped
for a ±50 µm sort. 40x WI is also **water immersion, so index-matched** — it
loses nothing to the oil-into-water clipping that costs the oil objectives their
NA, and that penalty is worst for exactly our case, large beads.

⚠ **The cost is a calibration session.** The Aresis Tweez 300's *Magnification*
(px→µm) and *Beam Position* (LCS↔ICS) calibrations are **per objective**, live in
the GUI, are interactive, and cannot be automated — they need an actually
trapped bead and ≥3 mouse-picked points. The 2026-09-04 closed-loop work was at
100x. So: **first sorting attempt at 100x** on the existing calibration, then
move to 40x WI once recalibrated.

### Illumination: CYAN alone if it suffices

CYAN excites **both** species — Dragon Green at its 480 peak, and the red bead
to ~2000 ADU. One line, two emissions, split onto two cameras, genuinely
simultaneous. Simplest possible arrangement.

⚠ **Do not add GREEN to boost the red channel** unless check 2 above is
satisfied. GREEN (~550 nm) sits *below* the 561 nm splitter edge, so
backscattered excitation reflects straight onto `Kinetix_blue` — the same camera
as Dragon Green's emission.

**UPDATE 2026-09-06: check 2 is now satisfiable, so GREEN is back on the table
— and it is worth having.** With FF01-515/30 (500.0-530.0 nm) in the blue arm,
GREEN backscatter at ~550 nm is out of band and blocked, which was the entire
objection. That matters because the red bead is **brightest under GREEN**
(~3500 ADU vs ~2000 under CYAN, 2026-09-05 at 4x). So the strongest simultaneous
arrangement is now **CYAN + GREEN together**: CYAN drives Dragon Green at its 480
peak, GREEN drives the red bead at its measured maximum, each backscatter is
rejected by its own arm's bandpass, and both species still land on separate
cameras. CYAN alone remains the simpler starting point and is still sufficient.

⚠ One thing this cannot compute: **if the red arm ends up on FF01-595/31
(579.5-610.5 nm), GREEN's own band may leak into it.** `data/light_sources.yaml`
records the Aura's five lines as names only — no centre, no width — so how far
GREEN extends to the red is unknown and unmodellable. With FF01-680/42 the
question does not arise. Check it directly: illuminate a *bead-free* field with
GREEN and read `Kinetix_red`.

### Frame rate: full frame is plenty

A sedimented 5 µm bead moves **0.04–0.07 µm per 30 ms frame** (0.3–1.1 px,
sub-pixel, and less near a wall where mobility is hindered). Full frame at 30 ms
is 33 fps and the readout ceiling is 118 fps, so tracking is comfortable without
an ROI.

This is the opposite of the stiffness measurement: G14 wanted 3159 fps to sample
a 316 Hz corner frequency, which needs a **90-row ROI, 5.8 µm tall — barely one
bead**. Sorting does not need that; do not let the G14 number drive the ROI.

---

## 4. Why this instrument suits sorting: the splitter is the classifier

**Species identity is "which camera saw it."** Because the two emissions
straddle 561 nm, `Kinetix_blue` sees only green beads and `Kinetix_red` sees only
red ones. No spectral unmixing, no ratiometric analysis, no colour thresholding —
the dichroic does the classification in hardware, for free. That is the property
that makes real-time sorting tractable here, and it is why the pairing must
straddle the splitter rather than merely being "two different colours."

### The force budget is not a constraint

Dragging a trapped 5 µm bead laterally along the glass, at 175 pN/µm and ~600 pN
peak radial force:

| wall drag | γ | v_max |
|---|---|---|
| bulk | 4.7e-8 | 12,800 µm/s |
| ×3 (near wall) | 1.4e-7 | 4,280 µm/s |
| ×10 (very close) | 4.7e-7 | 1,280 µm/s |

The proven ramp — a 5 µm 1 Hz sine — peaks at **31 µm/s**, i.e. 40–140× inside
budget even with severe wall drag. Drag is not what limits this.

### Throughput is what limits it

One trap moves one bead at a time. A 50 µm out-and-back at the proven 31 µm/s is
~3.2 s of pure travel, so tens of beads per session is the realistic scale once
detection, approach and verification are counted — the 2026-09-04 run managed 5
cycles. **This sorts tens, not thousands.** If throughput matters, the lever is
multiple simultaneous traps (the Tweez AOD time-shares them), not faster ramps.

---

## 5. What is actually blocking the sort

1. ~~**Emission filters, both arms.**~~ **RESOLVED 2026-09-06.** The operator
   supplied the part numbers — the Semrock set matched to the
   `Di01-T405/488/568/647` dichroic already in the path:

   | pos | label | part | passband | camera |
   |---|---|---|---|---|
   | 1 | `405` | FF01-432/36-32 | 414.0-450.0 | `Kinetix_blue` |
   | 2 | `488` | FF01-515/30-32 | 500.0-530.0 | `Kinetix_blue` |
   | 3 | `555` | FF01-595/31-32 | 579.5-610.5 | **`Kinetix_red`** |
   | 4 | `647` | FF01-680/42-32 | 659.0-701.0 | `Kinetix_red` |
   | 0 | `multi` | quad-band, same four bands, part number still missing | — | both |

   All confirmed by the operator 2026-09-06, including that **each camera has its
   own wheel in front of it** — so the two arms are independently selectable,
   which is what the two-camera plan requires.

   ⚠ **The label names the excitation line, not the passband.** Position 3 reads
   `555` and its filter passes 579.5-610.5 nm, i.e. entirely *above* the splitter
   edge — so it is a red-arm filter despite a label that suggests otherwise.

   ⚠ **Do not use position 0.** The quad passes both candidate red bands, which
   looks like useful insurance, but every excitation line here has one of its
   four bands blueward of it, so it opens an anti-Stokes window and costs 0.6 OD:
   `optics.cli check` returns INFEASIBLE where the single bands return HARD. A
   multiband emitter is for reading bands sequentially on ONE camera; this path
   already splits at 561 nm.

   All four are registered in `data/filters.yaml` and are candidates in
   `config/scopes/current-laser.yaml`. `optics.cli check` on the two-colour
   channel moves **INFEASIBLE → HARD**: excitation blocking 0.09 → **6.09/6.11
   OD**, Stokes headroom −188/−79 → **+12/+19 nm**, crosstalk margin **10.00**
   (scale maximum). `optics.cli recommend --panel` picks the same pairing
   independently. The residual FAIL is the 7 OD *parametric* bar, not physics —
   6.1 OD clears the 5 OD bar that applies with measured curves, so the remaining
   action is loading Semrock's free transmission curves into `data/spectra/`.
   Full detail and the crosstalk table: `dualcam-config-corrections-pending.md`.
2. **The red particle's real emission is unknown — and it now decides which
   filter goes in the red arm.** Its 620 nm excitation spec is disproved, so
   680 nm emission is also in doubt. With the passbands known, that uncertainty
   has a price tag (parametric shapes, fraction of each dye's total emission
   reaching a camera):

   | | red arm = 595/31 | red arm = 680/42 |
   |---|---|---|
   | red bead if em 680 | 0.002% | **50.8%** |
   | red bead if em ~590 | **41.5%** | 4.8% |
   | Dragon Green leaking in | 4.2% (**1 : 10** vs its own channel) | 0.002% (**1 : 25,000**) |

   So 680/42 is the clean classifier and 595/31 is the sensitive one, and they
   fail in opposite directions.

   **And the filter choice drags the excitation line with it** — 595/31 cannot be
   paired with the 640 line at all, since 579.5-610.5 nm is blueward of 640 and
   that is anti-Stokes. The two hypotheses are two whole configurations:

   - **A — em 680 (published):** excite **640**, filter **680/42**, crosstalk
     1 : 25,000. Clean. This is what the channel config encodes today.
   - **B — TRITC-class, ~550 ex / ~590 em (what the instrument showed):** excite
     **561 or Aura GREEN**, filter **595/31**. +19 nm Stokes headroom and 6.39 OD,
     the best blocking of any variant — but crosstalk 1 : 10.

   The instrument evidence favours **B** (RED gave nothing, GREEN was the
   maximum, which a 620/680 dye cannot do). Under B the 640 line is useless for
   this bead, so A is not a fallback from B — it is a different experiment.

   **The measurement is cheap:** run the red-only control through positions 3 and
   4 and compare peak ADU. Do this before anything else spectral. It also
   sharpens the FCFR008 purchase — confirm Flash Red emits inside **659-701 nm**,
   not merely above 561.
3. **Two cameras, no `Multi Camera` device — but `runtime/` is the likelier
   answer.** There is no Utilities `Multi Camera`, so Micro-Manager offers no
   single co-timestamped two-channel stream, and `Core-Camera` addresses one
   body at a time.

   Do not reach for that device first. `runtime/` (added 2026-09-05,
   `kb/decisions/2026-09-05-runtime-primitives-and-gpu-scope.md`) already
   provides the three pieces this needs: `runtime.frames.FrameSource` drains
   Micro-Manager's circular buffer on a thread and publishes only the newest
   frame **with an honest count of what it dropped**;
   `runtime.ticker.Ticker` gives a non-drifting fixed-period control loop; and
   `runtime.shmview.ShmPublisher` / `ShmSubscriber` put the live view in a
   *second process* so drawing cannot steal the control loop's interpreter —
   which is exactly the real-time-view requirement. The publisher is already
   named per camera (`ShmPublisher("kinetix_red")`), so two publishers is the
   natural dual-camera shape.

   ⚠ Two real caveats. **Nothing in `runtime/` has seen a Kinetix** — it is
   tested against fake cores and injected clocks, by its own admission. And its
   documented shape is *"one process owns the camera and the trap"*, singular;
   whether one `Core` will run `startContinuousSequenceAcquisition` on both
   bodies at once, and how far apart the two streams' timestamps then drift, is
   the open question. The Brownian step is sub-pixel per frame (§3), so modest
   skew is tolerable — but that is an argument for measuring the skew, not for
   assuming it away.
4. **Trap confirmation.** `TRAP_ON` returns 0 with the laser unarmed, so no
   return code proves a trap. Confirm only by moving the trap and seeing whether
   the bead follows. A stuck bead reads as still as a trapped one — which is
   exactly the failure mode a sedimented-on-glass sample invites.
5. **Objective calibration** if moving off 100x (§3).

---

## Related

`kb/systems/dualcam-config-corrections-pending.md` (config faults, read-only
set, derived readout timing) · `data/particles.yaml` ·
`config/channels/abvigen-bangs-green-red-2color.yaml` ·
`kb/expertise/oil-objective-trapping-in-water.md` ·
`kb/expertise/sample-mount-geometry.md` ·
`kb/decisions/2026-09-04-closed-loop-trapping-measured.md` ·
`kb/decisions/2026-09-05-runtime-primitives-and-gpu-scope.md` · `runtime/` ·
[[dualcam-needs-port-set-by-hand]] · [[cameras-are-12bit-ceiling-4095]] ·
[[lab-particles-are-in-data-particles-yaml]]
