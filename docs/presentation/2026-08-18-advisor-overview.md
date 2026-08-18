# experimentalist — what it is, in two pages

*For sharing. Written 2026-08-18. Every number below was produced by running the
code, not estimated.*

---

## In one sentence

It is an agent that designs microscope experiments: you describe the physics you
want to measure, and it returns settings that are executable on **our** current
instrument — with the reasoning, the assumptions, and the missing measurements
attached. A proposal is confirmed only after it survives review by eight
subsystem "lenses," each of which owns a specific set of settings and can veto.

The design goal is narrow and deliberate: **it must never invent a number.**
Anything with a closed form is computed in Python; anything not on record is
refused by name. The LLM's job is to gather inputs and interpret results, not to
estimate physics.

---

## Why not just ask a chatbot

Three structural reasons, each of which shaped the architecture.

**1. Past settings do not transfer.** We have 2,343 archived Micro-Manager
acquisitions from the old Nikon + Photometrics setup. `Exposure=80ms,
Spectra-Red_Level=10` is meaningless on the current system — different camera,
different light source, different filters. What transfers is the *physical
quantity* that setting produced: photon flux at the sample, effective pixel size,
excitation/emission bands, total dose. So the knowledge base normalizes
everything through three tiers — raw string → device value → physical quantity —
and only tier 3 is allowed to cross between instruments.

**2. Illumination is sometimes an experimental variable, not a measurement
tool.** For light-driven active colloids, FRAP, or photo-induced aggregation,
"raise the light to improve SNR" is optically correct and experimentally
ruinous. One optimizer cannot hold both; two lenses that are allowed to disagree
can.

**3. The optimum depends on the analysis, not just the sample.** Morphology wants
Nyquist sampling; single-particle tracking is optimal near σ_PSF ≈ one pixel.
These pull in **opposite** directions. Applying Nyquist mechanically gives the
wrong pixel size for microrheology.

---

## How a verdict works

Every lens returns two independent axes, and the committee only looks at their
conjunction:

| Axis | Question | Values |
|---|---|---|
| `status` | Is it physically sound? | `PASS` / `PASS_WITH_CHANGES` / `FAIL` / `BLOCKED` |
| `evidence` | Were the inputs **measured** or assumed? | `measured` / `assumed` |
| `advances` | `status == PASS` **and** `evidence == measured` | `YES` / `NO` |

So a lens can report `PASS` and `advances: NO` in the same breath — the physics
checks out, but it ran on catalog nominals rather than measurements, and the
committee will not let an unmeasured input be laundered into a confirmed setting.
`BLOCKED` is likewise distinct from `FAIL`: it means *the question cannot be
answered yet*, and it names the specific fact to go get.

Every `FAIL` must carry a concrete fix instruction, and the revise-and-re-review
loop is capped at three rounds. If eight lenses cannot converge, the system
hands the human the conflict itself ("photo-perturbation needs ≤5% power;
detection needs ≥30% for SNR 5 at 20 Hz — pick one of these three trade-offs")
rather than papering over an incompatibility. That is intended behaviour, not a
failure mode.

---

## The committee

Six standing lenses, two conditional. Split by **subsystem**, not by discipline,
so that jurisdiction over each setting is unambiguous and a veto is already a
work order.

| # | Lens | Owns | Code |
|---|---|---|---|
| 1 | Optics | filters, dichroics, objective, light path | `optics/` |
| 2 | Detection | exposure, binning, ROI, readout, frame interval | `detection/` |
| 3 | Compute resources | frame rate, buffer, storage, bandwidth | `compute/` |
| 4 | Sample geometry & optics | objective, immersion, coverslip, depth | `sample/` |
| 5 | Photo-perturbation | light level, duty cycle, total dose | `photo/` |
| 6 | Measurement validity | does all of the above yield the intended quantity, unbiased | `validity/` |
| 7 | Optical tweezers *(conditional)* | trap stiffness κ, U/kT, corner frequency | `trapping/` |
| 8 | Mechanical & environmental *(conditional, >30 min)* | drift, PFS lock, sedimentation, evaporation | `stability/` |

The point of a committee is the **cross-lens** constraints that no single lens
sees: motion blur biasing MSD (2↔6), trap stiffness raising the frame-rate
requirement (7↔2), SNR light driving active particles (1↔5), a smaller ROI
weakening statistical power (3↔6), refractive-index mismatch growing with depth
(4↔1).

Current state: all eight lenses implemented — 32 hard gates, ~11,900 lines of
Python, 498 tests passing. Lenses 4, 5, and 6 also have LLM subagent
counterparts for the qualitative half of their judgment.

---

## What it actually does — one worked example

Active microrheology, which is a real experiment we would run: a 5 µm
polystyrene probe held in a 1064 nm trap and driven at up to 30 µm/s, with 0.5 µm
tracers reporting the bath response, two colours acquired simultaneously on the
two Kinetix cameras.

**It designs.** Given the objective and depth it grades `40x-WI` as `HARD` and
`100x-Oil` as `MARGINAL`, quoting the refractive-index mismatch (oil n = 1.518
vs medium 1.333 makes the axial scale off by 12.2% at 20 µm). It computes the
force curve from a port of our own `GOA_ab.m` — 16.34 mW gives κ = 5.66 pN/µm
against 1.42 pN of Stokes drag, a 13× margin — and it sets 240 fps from the
`f_s ≥ 10 f_c` requirement, not from habit.

**It catches errors that would have produced a clean-looking figure.** Two I
would plausibly have made:

- *"Use more laser power so we don't lose the bead."* This makes the experiment
  **worse**: a stiffer trap has a higher corner frequency, and once f_c outruns
  the camera the Brownian spectrum aliases and the trap calibration is biased.
  There is a tidy identity behind it — dx = γv/κ and f_c = κ/2πγ give
  f_c = v/(2π·dx), so the sampling requirement depends only on drive speed and
  tolerated lag, not on bead size or laser power.
- *"Silica tracers are cheaper and brighter."* Flagged `INFEASIBLE`: silica
  settles 8.2 µm/min against a 0.44 µm depth of field, so the ensemble average at
  the end of the movie is over a different population than at the start. Nothing
  in the images would look wrong. Polystyrene passes with margin 1.09; silica
  fails at 0.05, and it is one line of input.

**It refuses rather than guess.** Ask for the same trap on a 1 µm bead and it
returns `BLOCKED`, not a number: the Mie size parameter x = 3.94 is outside ray
optics, so "a GOA force number here would be fiction." That is the one place a
wrong answer would have been invisible.

---

## What is blocking it: facts, not code

The gates run. They return `BLOCKED` for want of measured inputs — which is the
honest state of the instrument record, and the most useful thing the project has
turned up.

| Missing fact | Consequence | How to get it |
|---|---|---|
| **Illumination power at the sample plane** | Lens 5 is entirely blocked; every dose quantity undefined | ~30 min with a power meter, per line and level. **Cannot be computed.** |
| Dye `bleach_photons` | No photobleaching budget to count against | literature or a measured decay curve |
| Kinetix full well | Sampling, SNR, saturation uncomputable | not in the datasheet; vendor query |
| Two filter passbands, drift rate, laser dial% → mW | narrower blocks in lenses 1, 7, 8 | filter labels; one drift measurement; one calibration curve |

All 2,343 archived acquisitions record illumination as `Spectra-Red_Level: 10`.
A percent is not a physical quantity, and no amount of code substitutes for the
measurement. Everything else on the Phase 0 list has a runnable script in
`calibration/` and needs only a session on the microscope PC.

---

## The longer-term point

The computational gates are half of it. The other half is the knowledge that no
computation produces: that this sample changes composition 30 minutes after prep;
that a 647 exposure which crept to 500 ms is really a report that the light level
was insufficient; that this objective is unusable past 20 µm unless the
correction collar is set. That knowledge currently lives in one person's head and
gets re-explained to each new student.

So the knowledge base is plain markdown + SQLite — greppable, git-versioned,
human-editable, every entry tagged with its source (`measurement` > `datasheet` >
`calculation` > `expert-judgment` > `literature` > `precedent`) and with what
would refute it. No vector store, because "why was this value recommended" has to
stay traceable. Recommendations and their actual outcomes are recorded in
`kb/decisions/`, which is what closes the loop.

---

## If you want to look at it

- Design: [`docs/01-architecture.md`](../01-architecture.md) through
  [`docs/09-knowledge-capture.md`](../09-knowledge-capture.md) — the pitfalls
  list ([`06`](../06-pitfalls.md)) is the one grounded in our own data.
- 10-minute live walkthrough, every command verified:
  [`docs/presentation/2026-08-18-advisor-demo.md`](2026-08-18-advisor-demo.md).
- To run one yourself:

  ```
  python -m optics.cli check config/channels/demo-probe-tracer-2color.yaml
  ```

**The ask:** a power meter reading at the sample plane. It is 30 minutes of
instrument time and it unblocks more of this system than any amount of further
coding.
