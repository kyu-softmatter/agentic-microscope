---
id: 2026-09-10-lens-7-measured-stiffness-and-numbering
question: "Why could lens 7 not be told a stiffness it had measured, why did two hard gates grade a placeholder, and what should the unnumbered hard checks be called?"
date: 2026-09-10
status: current
corrects: [2026-08-19-lens-7-scope]
---

# 2026-09-10 · Lens 7 takes a measured stiffness, stops grading fiction, and gets its numbers

Three items from the gate-by-gate review, decided together by KH.

## 1. An entry for a measured stiffness

`TrapSetup` knew `dial_percent` and a calibration, and nothing else. Every κ
came through `dial → power → ray-optics model`, so the 3.65–4.5 pN/µm that
2026-09-03 measured **three independent ways** had nowhere to go, and G14 was
judged on the model's κ alone. That is what blocked the drag calibration.

`measured_stiffness_n_per_m` now exists, and `stiffness_n_per_m()` returns the
value with its provenance — a measurement wins.

**What it overrides, and what it does not:**

| check | uses the measured κ | why |
|---|---|---|
| G14a confinement | ✅ | κ only |
| G14c sampling | ✅ | `f_c = κ/2πγ` — **the one that mattered** |
| `trap.power_window` | ✅ (comparison) | says whether it sits in the window |
| **G14b trap depth** | ❌ | **U comes from the power, not from κ** |

**G14b stays on the model deliberately.** It *could* be rescaled — `U/κ` is a
constant of this model, both being linear in power, which is the same property
that makes `power_window`'s floor scale-free. But using it to correct `U`
assumes the model's error is in its *response to power* rather than in its
*shape*, and nothing establishes that. So the depth is the model's, and where
model and measurement disagree by more than 2× the message says so rather than
quietly rescaling:

> ⚠ The model's stiffness is 53× the measured one at this dial, and this depth
> comes from the same model at the same power — so treat it as carrying the
> same factor.

**That ratio is a number this lens could not produce until today**, because it
needs both κs at once — and asking for it immediately exposed that it needs a
**third** input, which is the correction below.

### The dial the measurement was taken at, and the defect that surfaced

I first computed the ratio as *model at the proposal's dial ÷ measurement*, and
quoted **53×** from it. That is not a statement about the model: it answers
"how does the model at dial X compare with a measurement at some unknown dial
Y". The comparison needs the model evaluated at the **measurement's own**
power.

Asked for that dial, the answer was (KH, 2026-09-10):

> **Unknown — and it was not 50 %.**

Searched and confirmed unrecoverable: `2026-09-03-three-subsystems-first-light.md`
has no dial, no laser level and no intensity for the trap; its one "hold power
down" line is about camera saturation. And `2026-09-04-closed-loop-trapping-measured.md`
records that the trap laser's power is *"neither settable nor readable"*, so it
is a physical setting on the Aresis GUI that no log captured.

So `measured_stiffness_dial_percent` is now a separate field, and
`model_over_measured()` returns **None** without it. `check_trap_depth` then
says the depth *cannot be checked* against the measurement rather than quoting
a ratio — the gap is visible in every verdict instead of buried here.

**What "not 50 %" buys**, which is the worst branch removed but not the
question closed. At the 100x Oil, model κ against the measured 3.87 pN/µm:

| dial | mW | model κ | model ÷ measured |
|---|---|---|---|
| 0.5 % | 6.1 | 2.09 | **0.54** |
| 1 % | 12.2 | 4.18 | **1.08** |
| 2 % | 24.3 | 8.37 | 2.16 |
| 5 % | 60.8 | 20.9 | 5.40 |
| 10 % | 120 | 41.2 | 10.6 |
| 20 % | 240 | 82.7 | 21.4 |
| ~~50 %~~ | ~~601~~ | ~~206~~ | ~~53~~ — **excluded** |

Near 1 % the model is right. The plausible remainder still spans 0.5× to ~21×,
so "not 50 %" narrows the answer by a lot and settles nothing. **Single digits
or tens of percent** is the one further recollection that would close it.

## 2. Two hard gates were grading a placeholder

`confinement` and `trap_depth` had **empty `requires`**, and Phase 0 only
blocks a check whose `requires` is unmet — so they always ran, on whatever the
dial produced, placeholder or not. `available_facts` had exactly one fact
(`medium.viscosity`), which gated only `sampling`.

Two facts added:

```
laser.calibrated   the power is real, so the model can be evaluated
stiffness          κ is knowable at all -- measured, or modelled on a real power
```

and `confinement → ("stiffness",)`, `trap_depth → ("laser.calibrated",)`,
`sampling → ("stiffness", "medium.viscosity")`.

**`--placeholder-power` now returns BLOCKED** rather than a graded verdict.
Confirmed as intended (KH): refusing is the repo's answer to a number nobody
measured, and the alternative was two `hard` gates on fiction. A measured κ
alone unblocks the two κ-only checks and leaves `trap_depth` blocked, which is
the correct split.

## 3. The numbering

| was | is | kind |
|---|---|---|
| `confinement` — **unnumbered** | **G14a** | hard |
| `trap_depth` — *"G14's escape-resistance half"* | **G14b** | hard |
| `sampling` — G14 | **G14c** | hard |
| `stokes` (lens 1) — **unnumbered** | **G3b** | hard |

Sub-lettered on lens 3's convention (`G12a–c`, `G13a–d`) rather than given new
numbers at the top of the range: G14's three are one question asked three ways
— can this trap hold this bead, deeply enough, and can the camera see it move.

`G3b` sits under G3 because it is the same failure family, excitation reaching
the detector, by a different mechanism: G3 is the filter failing to attenuate,
G3b is the bands overlapping in the first place. **G3's action ("add a blocking
filter") cannot fix it**, which is why it needs its own number rather than a
branch.

Both were `hard` and in no table, so a proposal could be stopped by something a
reader could not look up — and `stokes` has actually done it: the 2026-09-05
two-colour config went INFEASIBLE on `spectral.overlap 0.00`, a Stokes headroom
of −188 nm.

**The six `info` checks stay unnumbered** — `effective_na`, `power_window`,
`centering`, `port`, `trap_heating`, `convening`, `vibration`. A number means
"this can fail and stop or bias the result", which is the rule
`tests/test_gate_registry.py` enforces.

**The gate count does not move.** 27 = G1–G32 less the five vacant; sub-letters
are extra rows under a base number, not new numbers. The table now has 30 rows.

## 4. The thing this exposed, which was not on the list

> "근데 앞으로 파워를 모를 일이 있나?" — *will there ever be a case where we
> don't know the power?*

Rarely, now. But the case that replaces it was **crashing**: the measured curve
covers 5–80 %, `power_at` refuses to extrapolate past 80 %, and that refusal
reached the operator as a **traceback**. Asking for dial 90 % is an ordinary
thing to do and deserves a verdict. It now returns `BLOCKED` on
`missing.power_at_this_dial`, naming the calibrated range and why 80 % is the
top row (100 % over-ranged the meter).

## Falsifying condition

For (1): the 2026-09-03 dial turning out to have been well above ~1 %. Then the
model is optimistic by whatever factor, `trap.power_window`'s floor — which is
`10·kT/(U/κ)` and rests on the model's `U/κ` — is wrong by the same, and the
window's lower end stops meaning anything even though its G14 ceiling survives
(that end needs only γ and the frame rate).

For (2): a configuration where refusing is worse than computing — someone who
knowingly wants a rough answer off the placeholder and gets nothing. The
`--placeholder-power` flag still exists; what changed is that it no longer
produces a *graded* verdict.
