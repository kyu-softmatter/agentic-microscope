---
id: 2026-09-10-g17-becomes-a-z-to-depth-converter
question: "Should G17 gate on a depth x mismatch product whose threshold is a checklist trigger, when the operator has imaged well past it?"
date: 2026-09-10
status: current
corrects: [2026-09-10-lens-4-depth-window-and-g18-removed]
---

# 2026-09-10 · G17 stops gating and becomes the z-to-depth converter

**Decided by KH.** `BIAS` → `INFO`. The number is kept and the veto is not.

## Request, and one correction on the way

> "G17에서 실제로 높이를 판단 할 때에는 현미경의 z값과 피에조 스테이지의 위치로
> 계산을 해 얻으니 사용하지 않는 내용이 될 것 같아. 삭제해도 좋아."
> — *When we actually determine the height we compute it from the microscope's
> z and the piezo stage position, so this becomes unused. Fine to delete.*

**The premise as stated does not hold, and saying so changed the outcome.** A z
readout is **mechanical travel**. The focal plane inside the medium moves by
`n_sample/n_immersion` times that travel, because the refraction happens at the
coverslip interface — so reading z more precisely does not remove the factor, it
*is* the factor's input. And it applies in both geometries, which is the part
that is easy to get wrong:

| motion | interface-to-nominal-focus distance | real depth `h = d · n_s/n_i` |
|---|---|---|
| objective up by Δz | falls by Δz | falls by **Δz × 0.878** |
| stage (sample) up by Δz | falls by Δz | falls by **Δz × 0.878** |

Either way it is `d` that changes, so the same ratio appears. Commanding 9 µm
of z reaches **7.90 µm** of real depth; reaching 9 µm of real depth needs
**10.25 µm** of z.

Given that, the decision became **INFO rather than deleted**: *"실질적 z 위치를
사용하는 info로만 사용하자."*

## Why it stopped gating

The screening product was `depth × |Δn| ≤ 1.85 µm`, and **1.85 is
`10 × 0.185`** — `docs/05`'s lens 4 checklist trigger *"does the imaging depth
exceed 10 µm"* evaluated at the oil-into-water mismatch and then generalised.
So for oil into water the "tolerable depth" it produced was **10 µm by
construction**. The gate was capping the depth window on a number that came
from a checklist, and its own comment already conceded the point: *"a screening
heuristic, NOT a wave-optics result."*

Against that: **the operator has imaged a bead well at ~9 µm through the
100x Oil.** `CLAUDE.md` §3 records the precedent — *an operator statement about
their own instrument outranks a shape inferred from a drawing* — and a
checklist trigger is exactly that kind of shape.

## What it reports now

Both directions of the conversion, plus the mismatch and the axial scale error.
Index-matched media get told so explicitly: mechanical z travel *is* optical
depth there, no conversion.

`SampleSetup.imaging_depth_um` is defined as the **real** depth past the
coverslip, so nothing downstream needed adjusting — G16c's wall distance and the
depth window were already in the right units. What this check now does is tell
the operator which number to put there, which is the gap that made the original
request reasonable.

⚠ **Correcting my own earlier claim.** During the lens 4 review I said G16c
takes *commanded z* as `h`, repeating lens 4's subagent. The field's own
docstring says otherwise and the subagent was wrong. G16c was right all along;
what was missing was the converter, not a correction inside G16c.

## What this costs, and it is not small

**1. The depth window's aberration ceiling is gone, and that reverses a
conclusion committed hours earlier.**
[`2026-09-10-lens-4-depth-window-and-g18-removed.md`](2026-09-10-lens-4-depth-window-and-g18-removed.md)
reports the oil objectives' depth window as **EMPTY** — floor 13.9 µm from
G16c against a 10 µm G17 ceiling. With G17 no longer bounding:

| objective | before | **now** |
|---|---|---|
| `100x-Oil` | EMPTY | **13.9 – 100 µm** (ceiling: G16b chamber) |
| `60x-Oil` | EMPTY | 13.9 – 100 µm |
| `40x-WI` | 13.9 – 100 µm | 13.9 – 100 µm (unchanged) |

That entry's central table is superseded; the `corrects` link above is how a
reader finds this. **The objective argument is no longer settled by the
window** — all three now have the same usable band, and the choice returns to
being about the aberration nobody has bounded plus lens 2's sampling margin.

**2. Nothing bounds the mismatch aberration any more.** The per-ray spread is
real and large: at NA 1.45 into water the focal-shift ratio runs **0.878 near
the axis to 0.376 at NA_ray 1.3**, and rays past NA 1.333 are totally
internally reflected and never arrive. That spread *is* the spherical
aberration — there is no single focal plane — and the 12.2 % paraxial figure is
the optimistic end of it. G17 was the only gate that said the depth mattered at
all, and it now says it without a limit.

**3. G17 has left lens 6's bias ledger.** G23 collects `kind == "bias"`, so an
index mismatch no longer appears there. `validity/setup.py` still registers
`geometry.ri_mismatch` in `CORRECTIONS` and `BIAS_SCOPE`, deliberately left as
vocabulary the ledger knows how to handle — the same call the G10 and G18
removals made. Three registered codes now have no emitter.

## The measurement that would settle it properly

The window is empty or not depending on a constant nobody measured. Replacing
it is cheap: **image the bead at 9 / 12 / 14 / 16 / 18 µm and record where it
stops being trackable**, scored with `detection/focus_metric.py`'s
`tenengrad()` / `score_frame()`. That converts the checklist's 10 µm into this
instrument's number, and if the answer is past ~14 µm the oil objectives are
genuinely clear rather than clear by removal.

Offered and not taken today; recorded so the option is not lost.

## Falsifying condition

A run at a depth the old G17 would have refused whose axial distances or
tracking come out wrong in a way the aberration explains. That is the exposure
this decision accepts: the screen is gone, the aberration is not, and the only
thing standing between them is one operator observation at ~9 µm — a depth the
old gate *also* passed.

Narrower: if the depth series above shows the bead degrading before ~14 µm,
then G16c's 13.9 µm floor and the aberration ceiling really do exclude each
other for a 5 µm bead on oil, the empty window was right, and this decision
should be reverted rather than patched.
