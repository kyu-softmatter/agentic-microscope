# 2026-09-04 · Closed-loop trapping: what the live tracker can hand the trap

> Second session against the real instrument, and the first to close the loop
> between live detection and the optical trap. Everything below was measured on
> the microscope PC with the Tweez 300 GUI live, `6-Plan Apo LmbdD0.13 100x Oil`
> at 1× intermediate (0.065 µm/px, 1200×1200 ROI = 78 µm field), Aura GREEN at
> 2 %, laser armed by hand by the operator.
>
> Follows `2026-08-27-tweezers-first-light-measured-limits.md`. Corrects two
> claims made **within this session** — see "Retractions" at the bottom.

## What was achieved

Five cycles of *detect isolated particles → put the trap on the one nearest the
field centre → ramp it to the origin and hold*, driven by the space bar in one
window (`config/tweezers/trap_sequence.py`). Four of the five beads were caught
and carried 11–26 µm to the origin:

| trap target, µm | ramp, µm | bead moved, µm | follow |
|---|---|---|---|
| (−15.5, +16.5) | 22.67 | 22.63 | **99.8 %** |
| (−10.1, −4.5) | 11.03 | 10.89 | **98.7 %** |
| (+16.3, +19.8) | 25.68 | 0.74 | 2.9 % |
| (+17.5, +2.6) | 17.68 | 17.43 | **98.6 %** |
| (−19.4, +11.1) | 22.39 | 22.33 | **99.7 %** |

The trap was created, positioned, armed and driven entirely from Python over
TCP. `LASER_ON` was never sent from code.

## 1. The px → trap-µm transform: orientation confirmed, origin measured, scale still nominal

The obstacle was never the plumbing. `TRAP_POSITION` takes µm, the tracker
answers in pixels, and the map between them carries an **unknown rotation and
an unknown handedness** — the GUI *Beam Position* calibration is documented as
LCS↔ICS rotation + translation + scale (manual pp.35–38), and 2026-08-27
established there is no TCP command to read it back. Eight orientations agree
with "the origin is the field centre" and seven of them send the trap somewhere
mirrored or rotated.

**Orientation: confirmed.** Four beads in four different quadrants were all
targeted through the provisional matrix — nominal scale, zero rotation, y
flipped because image y runs down — all four were trapped, and all four
followed the ramp home at 98.6–99.8 %. Nothing but the correct rotation and
handedness does that four times in four directions.

**Origin: measured.** All five holds came to rest at

```
p0 = (584.42, 584.38) ± (0.68, 0.48) px      (SEM, n = 5; SD 1.52, 1.08)
```

in the 1200×1200 ROI — **(−15.58, −15.62) px** from the frame centre. The two
axes agree to **0.04 px** against a per-hold scatter of 1.30 px, which is what
makes it one systematic offset rather than five coincidences. As a physical
place that is **(−1.013, −1.015) µm**, and it is stored in µm
(`trap_sequence.TRAP_ORIGIN_OFFSET_UM`) precisely so it survives a change of
magnification or ROI, where a pixel count would not.

Why both axes come out equal is not explained here. It is worth knowing before
it gets treated as noise.

**Scale: still nominal, and these ramps cannot fix it.** The bead's starting
pixel is where the *bead* was; the trap's starting position is where it was
*commanded*. Those differ by the initial bead-to-trap offset, so solving the
2×2 from two ramps mixes that unknown in — it comes out **12 % anisotropic**,
which is the contamination and not the optics (a rotation+translation+scale map
has equal singular values by construction). Only a drive applied to a bead
**already sitting in the trap** measures the matrix, which is what the sine in
`trap_from_tracking.py` is for. It was skipped this session at the operator's
request.

## 2. TCP return codes are not evidence that a trap exists

`SIMPLE_TRAP_CREATE`, `TRAP_POSITION` and `TRAP_ON` all answered **0
(success)** while the GUI showed the trap's `Active` = **false** and nothing
was trapped. Six candidate commands for reading or setting that state —
`LASER_STATE`, `GET_LASER`, `LASER_STATUS`, `TRAP_STATE`, `TRAP_ACTIVE`,
`TRAP_SET_ACTIVE` — all answered **−11, unknown command**, extending the
2026-08-27 probe.

The cause was mundane: **the laser was not armed.** Once the operator armed it
at the GUI the identical sequence trapped four beads out of five. So the
commands were always right and the statuses were always uninformative: `0`
reports that the GUI accepted the command, not that there is light in the
sample. Laser power remains neither settable nor readable, so *"the commands
succeeded"* and *"a trap exists"* are independent facts and only a human can
check the second.

This is the same shape as the two traps of 2026-08-27 (`Enable Bits 0000`,
`Repeat > Enabled False`): a correct command sequence made to look broken by
GUI-only state, with no error anywhere.

## 3. A bead's excursion does not tell you whether it is held

`trap_sequence` judged each catch by the target bead's RMS excursion over
1.5 s, against a 150 nm cut — a free 5 µm bead near the coverslip covers
√(2·D·t) ≈ 350 nm at the D measured on 2026-09-04, and a held one tens of nm,
so the separation looked ample.

**It was wrong in five cycles out of five.**

| RMS | verdict | the ramp then said | |
|---|---|---|---|
| 208 nm | diffusing | held (99.8 %) | wrong |
| 189 nm | diffusing | held (98.7 %) | wrong |
| 101 nm | **held** | **not held (2.9 %)** | wrong |
| 193 nm | diffusing | held (98.6 %) | wrong |
| 229 nm | diffusing | held (99.7 %) | wrong |

Four false negatives and a false positive. Moving the threshold cannot fix it,
because the statistic does not separate the populations:

- **A bead stuck to the coverslip sits as still as a trapped one.** That is the
  101 nm reading, and it is why that bead did not come with the trap. Sticking
  is common in this sample — the 2026-09-04 diffusion work found beads with
  effectively no motion.
- **A bead just trapped is still travelling into the well.** Its first second
  of excursion is that approach, not thermal motion in a well.

The second confusion is removable and is now removed (`GRAB_SETTLE_S = 0.8 s`
discarded before the window opens; a settled held bead read **28 nm**). The
first is not removable by watching a still bead at all.

**The test that works is to move the trap and see whether the bead comes.**
98.6–99.8 % against 2.9 %, with nothing in between — a cleaner separation than
the excursion ever offered, and it is the same ramp the operator wanted anyway
for bringing the bead to the centre. The excursion is still printed, as an
observation, labelled as not deciding anything.

## 4. Move a held bead on a ramp, never in one command

A single `TRAP_POSITION` to the origin asks for the whole displacement inside
one 15 ms command — an implied ~1000 µm/s over a 17 µm trip, far past anything
a trap holds. The bead is left behind and the trap arrives empty. Positions are
interpolated at `--speed-um-s` (5 µm/s here, 4.5 s for a 22 µm trip), and
arrival is checked by comparing how far the bead moved against how far the trap
did — which is what produced the table in §1.

The reverse move is deliberately **not** a ramp. Releasing a bead to look for
the next one sends `TRAP_OFF`, which lets it go where it is; ramping the trap to
the next target would drag it along and undo the work.

## 5. Timing, measured rather than estimated

Per-stage display tick, instrumented in the loop (1200×1200 ROI, GPU
detection):

| stage | tick | rate |
|---|---|---|
| LIVE (no detection) | 16.7 ms | 60 Hz |
| DETECT | 28.0 ms | 36 Hz |
| TRAP | 29.9 ms | 33 Hz |
| OSCILLATE (detector off) | 25.5 ms | 39 Hz |
| HOLD | 30.6 ms | 33 Hz |

Detection is ~12 ms of the tick and is skipped once a bead has been chosen. The
target refine kept **3912 of 3927** attempts across a 6840-frame session —
0 empty windows, 15 jumps — so the tracker was never the limiting factor.

`TRAP_POSITION` round trips in **1.3 ms**, but `send_command` sleeps out a 10 ms
floor first, making it **15.6 ms** in practice. With the floor removed, 28 of 40
came back −14 busy, so the floor is doing real work and ~100 Hz is the ceiling
for position streaming.

## 6. What the sample looked like, and one thing to change

At 100× in a 78 µm field, 25–36 objects were detected with only 3–10 isolated
past a 12 µm nearest-neighbour cut, and **nothing isolated within ~23 µm of the
centre** on several passes. That makes every reach a long one, every ramp slow,
and it puts the target near the edge of a trapping range whose extent is still
unknown.

A 12 µm cut is stricter than the job needs: a 5 µm bead has to be far enough
that the trap grabs one particle, not 12 µm clear. Lowering `--isolation-um`
to ~8 would put candidates much nearer the origin.

## Still open

- **The green trapping trapezoid's half-extents at 100×.** GUI-only, and it
  decides whether targeting can reach across the whole 78 µm field or only its
  middle. `--max-offset-um` is a placeholder (30 µm was used), and points
  outside the real range are *clipped silently and not drawn*, so an unchecked
  reach fails with no error on either side.
- **The scale.** One sine on a bead already in the trap settles it. §1.
- **Why the origin offset is equal in x and y** to 0.04 px.
- **The trap's drag-speed limit and hence its force.** Not measured — see the
  retraction below. 5 µm/s works; the ceiling is unknown.
- **Laser power.** Still unreadable by any means, so it is an acquisition
  parameter that exists only if a human writes it down. `--laser-note` puts it
  in the log because there is nowhere else for it to go.

## Retractions

Both of these were asserted earlier in the same session and are wrong.

- **"The drive got 21 samples in 5 s because the tick is slow."** It is not.
  The drive aborted on the `--max-offset` guard: the bead sat 17.5 µm out, +5 µm
  of x drive reached 22.4 µm, and the guard was being applied per tick,
  mid-flight. The instrumentation in §5 shows the OSCILLATE tick at 39 Hz,
  which is ~195 samples in a 5 s drive. The guard now refuses before the first
  command and names the fix (bring the bead to the origin first).
- **"The trap drags between 5 and 10 µm/s, so its force is ~0.5–1 pN."** No
  basis. The 3 % follow at 10 µm/s and the 3 % follow at 5 µm/s are both
  explained by beads that were never held, and four beads followed at 5 µm/s.
  There is no measured speed limit and therefore no force estimate.
