---
id: 2026-09-10-lens-4-depth-window-and-g18-removed
question: "Where may the focal plane actually sit, given that four gates each bound the imaging depth from a different side, and does G18 still earn a margin?"
date: 2026-09-10
status: current
---

# 2026-09-10 · Lens 4 reports a depth window, and G18 is removed

> ⚠ **§1's empty-window table is SUPERSEDED, the same day.** G17 stopped gating
> hours later ([`2026-09-10-g17-becomes-a-z-to-depth-converter.md`](2026-09-10-g17-becomes-a-z-to-depth-converter.md)),
> so its 10 µm ceiling no longer bounds the window and **the oil objectives are
> no longer empty** — all three read 13.9 – 100 µm, bounded by the chamber. The
> mechanism described below is unchanged and the G18 half stands; only the
> ceiling that came from G17 is gone. Read the two together.

Decided by KH during the gate-by-gate review.

## Request

> "G16c는 벽 근처에서 작업을 하면 안좋기 때문에, 최대한 높은 곳으로 이동할 수
> 있도록 하한선을 제공해주는 입장. G16은 워킹디스턴스로 최대 측정가능 거리를
> 알려주는 것. G16b는 스페이서를 고려해서 측정가능 거리를 보정하는 것. 즉 이
> 세가지를 통해서 우리는 샘플의 하한과 상한을 고려하고자 함. 결과물로 샘플
> 위치의 상한과 하한을 함께 내보내자."
> "G18은 이미 다른데서 고려를 하고있으니 삭제."

## 1. The depth window

Four gates bound the imaging depth and a reader had to invert four margins by
hand to learn where the focal plane may sit. `geometry.depth_window` (INFO) now
reports the band:

| end | owner | expression |
|---|---|---|
| **floor** | G16c near-wall drag | `h ≥ 9a/(16 × 0.10)` = `5.625 a` |
| ceiling | G16 free working distance | `WD − max(0, coverslip − design)` |
| ceiling | G16b chamber height | the spacer correction on the same budget |
| ceiling | G17 index mismatch | `1.85/|Δn|` — an aberration limit, not a reach one |

The ceiling reported is the `min` of whichever apply, and the message names
which one binds. **Depths are measured from the coverslip's inner surface.**

`INFO` on purpose: every bound it restates is already graded by its owner, so
grading the window would double-count. What it adds is the case no single margin
can express.

### It is immediately decisive, and that was not the intent

For the drag calibration — 5 µm bead, `a` = 2.475 µm — **the window is empty on
both oil objectives**:

| objective | floor (G16c) | ceiling | window |
|---|---|---|---|
| `100x-Oil` | 13.9 µm | **10.0 µm** (G17) | **EMPTY** |
| `60x-Oil` | 13.9 µm | **10.0 µm** (G17) | **EMPTY** |
| `40x-WI` | 13.9 µm | 100 µm (G16b chamber) | **13.9 – 100 µm** |

There is no depth at which a 5 µm bead on an oil objective is both far enough
from the wall and inside the index-mismatch screen. The two bounds are
individually satisfiable and jointly are not — which is exactly why no margin
said so, and why lens 4's subagent could only phrase it as prose ("there is no
depth with this objective at which the wall term is small").

**This turns the objective question from an argument into arithmetic.** The
40x WI's window is bounded by the *chamber*, not by the objective, and it is
index-matched so the G17 term disappears. Note what this does **not** do: it
does not overrule CLAUDE.md H4, and lens 2's `sampling` margin at 108.3 nm/px
is still the hard gate that rules out the 1.5× intermediate variant. The window
is an input to that conflict, not its resolution.

The floor scales with radius (`5.625 a`), so a sub-micron probe reopens the oil
objectives — `a ≤ 1.78 µm` makes the 100x window non-empty.

### One implementation note that generalises

The window's *passing* branches were written with `_ok(...)`, whose severity is
`"ok"` — and `sample/gate.py` drops `severity == "ok"` from `findings`. So the
number the operator asked for was computed and then discarded, visible only in
`metrics`. Changed to severity `"info"`.

**This is the same defect as G16c's `trapped` branch**, which is still open: a
report that must be seen cannot use `_ok`. Worth a sweep across the lenses.

## 2. G18 removed

**The coverslip is still in this lens twice, and that is why the margin was
safe to drop.** G16 subtracts coverslip excess over design from the
working-distance budget — 190 µm glass against a 170 µm design costs 20 µm of
reach, asserted by `test_coverslip_excess_still_comes_off_the_working_distance`.
And an unmeasured coverslip is still an `assumed_input`, so it still withholds
`advances` at no margin. What went is the graded `|actual − design| ≤ 5 µm`.

**What the removal does lose, stated plainly:** the *optical* consequence of an
off-design coverslip. G16 covers the geometry — can you still reach — and G17
covers index mismatch through the medium, but neither covers the spherical
aberration a wrong glass thickness introduces in the design path. Nothing checks
that now.

**The collar was not part of the coverslip and did not go with it.** The 40x WI
is the only objective on the nosepiece with a correction collar, and it is also
the objective §1's window recommends for this measurement, so losing the check
there would have been the worst possible place. The condition moved to
`sample/gate.py::_assumed_inputs`: an unadjusted collar still withholds
`advances`, it just no longer carries a margin. That matches the reasoning for
the removal — the collar is a knob nothing else records, not a threshold.

`G18` is **vacant and not reused**. `validity/setup.py`'s `CORRECTIONS` still
registers `"geometry.coverslip"`, deliberately left as vocabulary the ledger
knows how to handle — the same call the G10 removal made.

## What is still open

**The datum.** The window is quoted from the coverslip's inner surface, and
nothing establishes that surface today. The parts exist —
`hardware/focus.py`'s `FocusAxis.position_um()`, `plan_span()`,
`FocusCurve.peak_z_um()`, and `detection/focus_metric.py`'s `score_frame()` —
but there is no routine that finds the coverslip specifically (as opposed to
the sharpest object in the field) and stores it as `z0`, and nothing reports
`h = z − z0` against this window while an acquisition runs. Requested by KH the
same day; scoped, not built.

## Falsifying condition

For the window: a run at `h` inside the reported band whose drag or aberration
is nonetheless unacceptable. The floor rests on `9a/(16h) ≤ 10 %`, which is a
screening limit chosen to sit with this repo's other bias limits rather than
measured, and the ceiling on G17's `1.85 µm`, which its own comment calls a
screening heuristic and not a wave-optics result. Both ends are order-of-
magnitude, and the window should be read that way.

For the G18 removal: a measured coverslip that differs enough from design to
degrade the PSF while still leaving working distance to spare. G16 would pass
it, `assumed_inputs` would say only that nobody measured it, and no gate would
report the aberration. That is the case this decision accepts.
