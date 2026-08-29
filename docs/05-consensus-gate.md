# 05 · The committee and feasibility verdicts

> **Status: sketch.** The grading scheme and verdict schema are settled
> proposals; the per-lens checklists are drafts.

---

## 1. Drop the binary verdict

The initial design was `PASS`/`FAIL`. That was wrong.

**Experiments that must be shot at the measurement limit do exist.** Sometimes
the signal being weak is a known fact and the data is needed anyway. If the gate
can only return `FAIL` in that situation, one of two things happens — the human
turns the gate off, or the human forms the habit of ignoring it. Both are the
worst outcome.

Instead, say **how hard it is**, and compute and show **what would make it
easier**.

---

## 2. Three kinds of gate

The **consequence** of falling short differs, so the handling must differ too.

| Kind | If it falls short | Proceed | Examples |
|---|---|---|---|
| **soft** | Quality degrades only. The data stays valid | ✅ Proceed after flagging the difficulty | Insufficient SNR, insufficient sampling, insufficient statistical power |
| **bias** | **The result is wrong.** Data comes out, but the interpretation is off | ⚠ Proceed with **mandatory** correction if a correction formula exists; stop if not | Motion blur, post-processing filters, missing pixel calibration, light-driven perturbation |
| **hard** | It simply does not work | ❌ Stop | Insufficient excitation blocking, zero excitation coupling, data rate exceeded (drops), saturation |

`bias` is the most dangerous. **Because the data comes out looking plausible**,
it is hard to notice after the fact. The motion blur case in
[04 §5](04-decision-engine.md) is the canonical example — MSD comes out as a
straight line with the wrong slope.

### Classification of gates G1–G14

G12 and G13 each cover several independent criteria, listed separately here
because they differ in **kind** — the two bias rows under G12 are evidence
conditions on the same arithmetic the hard rows gate.

| Gate | Kind | If it falls short |
|---|---|---|
| G1 Excitation coupling | hard | No signal |
| G2 Emission collection | soft | Increase exposure (dose rises) |
| G3 Excitation blocking | hard | Background swamps signal |
| G4 Crosstalk | bias | Channel contamination without unmixing |
| G5 Sampling | soft/bias | Morphology = soft, tracking = **bias** (localization bias) |
| G6 Saturation | hard | Values clip → unrecoverable |
| G7 SNR | soft | Merely noisy |
| G8 Motion blur | **bias** | MSD underestimated. Correction formula exists |
| G9 Frame-rate realizability | hard | Does not run as requested |
| G10 Photobleaching | bias | Intensity decay → correction needed |
| G11 Statistical power | soft | Error bars merely widen |
| G12a Data rate | hard | **Silent frame drops** |
| G12b Frame-rate provenance | bias | Every lens-3 number scales with a rate nobody observed |
| G12c Pixel container | bias | Data rate off by 2× in the 8-bit mode, where it binds |
| G13a Buffer | hard | **Silent frame drops** |
| G13b Capacity | hard | Acquisition stops partway |
| G13c Real-time CPU | hard | Falls behind, then drops |
| G13d RAM capture | hard | Burst does not fit; MemoryError or a truncated run |
| G14 Tweezers sampling | bias | κ calibration value is wrong |

---

## 3. Difficulty grades

Each gate reports its **margin** as a ratio: `m = achieved / required`.

**Why a ratio and not a verdict.** The computation behind a gate is there to fix
the *scale* — the deterministic core answers "off by 2× or by 2000×", which is a
question with a closed form ([01 §1b · 1c](01-architecture.md)). The margin
carries what that cannot: an experiment is aimed at a phenomenon nobody has
measured yet, so the true value may depart from the one the formula produced,
and the formula's assumptions may be what departs. `m` is how much room there is
for that departure. Collapsing it to `PASS` throws away the one number that says
whether a small surprise is survivable.

| m | Grade | Meaning |
|---|---|---|
| ≥ 3 | **ROUTINE** | Comfortable headroom. If it fails, the settings are not to blame |
| 1.5 – 3 | **COMFORTABLE** | Normal |
| 1.0 – 1.5 | **TIGHT** | Fails if conditions slip even slightly. Sample preparation quality decides the outcome |
| 0.5 – 1.0 | **HARD** | Operating at the limit. Low success rate, poor reproducibility. **May proceed** |
| 0.2 – 0.5 | **MARGINAL** | Data comes out but interpret with great care. Effectively meaningless for a bias gate |
| < 0.2 | **INFEASIBLE** | Impossible without improvement |

The overall grade = **the grade of the worst soft/bias gate**. If any hard gate
has `m < 1`, stop regardless of the grade.

### Output format

```
feasibility:  HARD  (m = 0.64, deciding gate: G7 SNR)

  hard gates   all pass ✅
  bias gates   G8 motion blur m=0.9 → correction mandatory (Savin-Doyle)
  soft gates   G7 SNR m=0.64  ← bottleneck
               G11 statistical power m=1.8

This experiment is possible but hard.
· Expected SNR 3.2 (target 5). Localization precision 16 nm (target 10 nm)
· Individual trajectories will be noisy; only the ensemble average will give a
  trustworthy result
· Sample preparation quality (background fluorescence, non-specific adsorption)
  decides success or failure
· Apply the motion blur correction. Without it, G' comes out systematically low
```

---

## 4. Improvement proposals — sensitivity analysis

**Saying only "this is hard" is useless. Compute and show what to fix.**

Take the partial derivative of the bottleneck gate's margin with respect to each
parameter, and report a gain multiplier per intervention. Group interventions
into cost tiers.

### Tiers

| Tier | Examples | Cost |
|---|---|---|
| **0 · Settings** | Readout mode, binning, ROI, exposure, light level | Free, immediate |
| **1 · Light path** | Remove/swap a filter, switch light path to 100%, remove ND | Free ~ part cost |
| **2 · Reagents** | Brighter dye, labeling density, antifade, refractive-index matching | Cheap |
| **3 · Parts** | Emission filter, dichroic, objective | $$ |
| **4 · Instruments** | Camera, light source | $$$$ |
| **5 · Design** | Change the measured quantity, concede time resolution, change the sample system | Conceptual |

### Example output (SNR short by 1.6×)

```
improvement candidates — computed gains

tier 0 (free)
  200MHz 12bit → 100MHz 16bit        ×3.4   effective noise 4.65→1.35 e-
                                            but check max fps (revisit G9)
  2× light level                      ×1.4   √2 (shot-noise limited)
                                            ⚠ 2× bleaching dose → recheck G10
  2x2 binning                         ×2.0   but effective pixel 110→220 nm
                                            ⚠ G5 bias if tracking → not advised

tier 1 (parts or free)
  emission filter 692/40 → 685/70     ×1.4   collection 21% → 30%
  light path AUX → L100               ×?     no gain if already at 100%

tier 2 (reagents)
  ATTO647N → Alexa Fluor 647          ×1.8   ε 150k→270k
                                            ⚠ Φ 0.65→0.33, so actually ×0.9
                                            → a net loss in brightness ε·Φ
  add antifade (Trolox/GLOX)          ×?     suppresses bleaching. Not
                                            quantifiable; needs literature values

tier 3 (parts)
  objective NA 1.45 → 1.49            ×1.15  η_geo 0.352→0.404
                                            poor cost-effectiveness

tier 5 (design)
  frame rate 20 → 10 Hz               ×1.4   2× exposure → √2
                                            ⚠ risks missing the 50 ms
                                              characteristic time
```

**Three points are immediately visible in this table:**

1. **The largest gain is the cheapest** — switching readout mode at ×3.4 is far
   larger than swapping the objective at ×1.15, and it is free. Intuition runs
   the other way.
2. **A dye that looks brighter can actually be dimmer** — ε alone is not enough;
   you have to look at `ε·Φ`.
3. **Every improvement touches another gate** — 2× light is 2× bleaching;
   binning destroys sampling. So **improvement proposals must pass the gates
   again too.**

### Implementation

Attach a `sensitivity()` to each gate: parameter → partial derivative (or finite
difference) of the margin. Record in an intervention catalog
(`data/interventions.yaml`) which parameters each intervention changes and by
how much, then combine and rank them.

```yaml
# data/interventions.yaml (sketch)
- id: readout_16bit
  tier: 0
  cost: free
  changes: {bit_depth: 16, readout_rate: "100MHz 16bit", gain: HDR}
  side_effects: [max_fps_decreases]
- id: emission_filter_685_70
  tier: 3
  cost_usd: 400
  changes: {emission_filter: "FF01-685/70"}
  side_effects: [crosstalk_may_increase]
```

---

## 5. Committee lenses

Details for [01 §4](01-architecture.md). Every lens answers with the same
schema.

```python
@dataclass
class LensVerdict:
    lens: str
    feasibility: str          # ROUTINE .. INFEASIBLE
    margins: dict[str, float] # m per gate
    evidence: str             # measured | assumed
    assumed_inputs: list[str]
    findings: list[Finding]   # severity, code, message, action, numbers
    interventions: list[Intervention]   # improvement proposals + computed gains
    advances: bool            # feasibility >= TIGHT and evidence == measured
                              #   and no hard gate below 1.0
```

### Lens 1 · Optics — implemented

- **Owns**: excitation filter, dichroic, emission filter, ND, polarizer,
  mirrors, light-path port, objective
- **Gates**: G1 G2 G3 G4
- **Specialty**: ablation analysis — actually remove each element from the
  product, recompute, and decide whether it can be dropped
- **Implementation**: `optics/gate.py`

### Lens 2 · Detection — implemented

- **Owns**: exposure, binning, ROI, readout mode, gain, bit depth, frame
  interval, trigger
- **Gates**: G5 G6 G7 G8 G9
- **Key questions**
  - Is the frame rate sufficient relative to the system's characteristic time
  - How far does the sample move during the exposure (motion blur)
  - Is the pixel size **right for the task** (morphology vs tracking — opposite
    directions)
  - Does quantization noise stay below read noise
  - Do the bright regions avoid saturation
- **Checklist**
  - [ ] Has the task type been stated (if not, ask)
  - [ ] Is there a measured `t_row`
  - [ ] Is there a measured background noise level (without it, SNR is an upper
        bound)
  - [ ] Rolling shutter: does the row-to-row time offset matter for a fast
        target
- **Implementation**: `detection/gate.py`

### Lens 3 · Compute resources — implemented

- **Owns**: data rate, circular buffer, storage capacity, real-time processing,
  CPU/RAM
- **Gates**: G12a (disk budget) G12b (frame-rate provenance) G12c (pixel
  container) · G13a (buffer) G13b (capacity) G13c (real-time CPU) G13d
  (RAM-capture capacity)
- **Key questions**
  - Is `R = Σ_streams W·H·bytes·f` below 70% of sustained disk write bandwidth —
    summed over **every camera actually running**, not one widened frame
  - Is that `f` an achieved rate or one somebody typed into MM
  - Is `bytes` the container MM really writes, or an inference from the ADC's
    bit depth
  - Does the buffer hold at least 5 seconds
  - Does the total volume fit in the free space
  - With online processing (tracking, compression) attached, is CPU time per
    frame < 1/f **summed across streams**
  - On the RAM-capture path, does the whole burst fit the authorized RAM budget
- **Specialty**: **the only lens that catches silent failure.** Frame drops
  raise no error and surface only as `ElapsedTime-ms` intervals larger than
  expected
- **Checklist**
  - [ ] One stream per camera — is this a dual-cam acquisition
  - [ ] Where did the frame rate come from (lens 2's ceiling is not an achieved
        rate either)
  - [ ] Which readout mode, and is its container width confirmed
  - [ ] Was the disk bandwidth measured against the folder MM actually saves to
  - [ ] Streaming to disk, or the RAM-capture path
- **Post-hoc verification**: ✅ implemented — `compute/drops.py`,
  `python -m compute.cli drops <metadata.txt>` / `scan <dir>`. Per-series median
  cadence, gap detection, requested-vs-achieved ratio. Runs on the existing
  archive today with no hardware
- **Implementation**: `compute/gate.py` (prospective), `compute/drops.py`
  (post-hoc), `.claude/agents/compute-resources.md` (interpretive half)

### Lens 4 · Sample geometry & optics — implemented

- **Owns**: objective choice, immersion, coverslip thickness, imaging depth,
  chamber
- **Gates**: G15 (NA feasibility) G16 (working distance) **G16b (depth within
  chamber)** **G16c (near-wall drag bound)** G17 (refractive-index mismatch)
  G18 (coverslip thickness) G19 (count in field · overlap)
- **G16c is the worked example of [01 §3 Principle 1b](01-architecture.md)** —
  bound the second-order term instead of demanding an exact model for it. The
  truncated Faxén factor `9a/(16h)` over-states the drag, so "D is low by at
  most this" is a computation, not a guess, and it reproduces `06 D8`'s
  tabulated penalties exactly. With the trap on, D8's in-situ power-spectrum
  calibration absorbs the bias and the bound is reported as INFO; untrapped,
  nothing absorbs it and it goes `bias`
- **G16 and G16b are the two halves of "can this focal plane be reached"**:
  G16 asks whether the objective can reach the depth, G16b whether the sample
  extends that far. Focus past the chamber's far wall and the image is of the
  wall — an empty focal plane looks exactly like a dim one, which is why this
  is worth a gate. Lens 8 holds `chamber_height_um` but spends it only on the
  sedimentation flag (G31), so nothing compared it to the imaging depth before
- **Key questions**
  - Refractive-index matching: immersion / coverslip / medium / sample
  - Imaging depth × RI mismatch → spherical aberration, focal shift
  - Does the WD cover the imaging depth + coverslip
  - **ATPS has different refractive indices in the two phases** — different
    aberration per phase
  - Sample concentration → count in field, overlap, multiple scattering
  - Coverslip thickness tolerance (#1.5 = 170±5 µm; the real spread is wider)
- **Checklist**
  - [ ] Has the medium's refractive index been recorded
  - [ ] Is this an objective with a correction collar, and was it adjusted
  - [ ] Does the imaging depth exceed 10 µm (if so, aberration must be
        quantified)
- **Specialty**: catches a physical impossibility nothing else does — G15 refuses
  an objective used in the wrong immersion medium.
  `optics.components.Objective.collection_efficiency` clamps that case with
  `min(na/n, 1.0)` and returns a plausible collection efficiency instead
- **⚠ G17 is a screening heuristic**, not wave optics. It gates on the
  `depth × |Δn|` product (limit 1.85 µm, anchored on this checklist's own 10 µm
  trigger at the oil-into-water mismatch of 0.185) and reports the paraxial
  focal-shift ratio. It decides whether a real aberration calculation is owed;
  it is not that calculation, and the ratio is not a correction factor
- **Remaining**: a measured coverslip thickness — with the sample-medium index
  settled at 1.333 (2026-08-19) that micrometer reading is the last thing
  holding ordinary verdicts at `evidence: assumed`, **and it is sufficient** —
  the lab mounts 170 µm, which matches every objective's design, so G18 passes
  at margin 10.0 and only the reading itself is missing
  ([`kb/expertise/coverslip-thickness-in-use.md`](../kb/expertise/coverslip-thickness-in-use.md)).
  What holds an oil objective past ~10 µm depth is G17's mismatch, and what
  holds the 40x WI is the unrecorded collar. Per-phase RI for ATPS still
  BLOCKs by design, and is asked at experiment time rather than pre-populated
  ([`kb/decisions/2026-08-19-lens-4-scope.md`](../kb/decisions/2026-08-19-lens-4-scope.md))
- **Implementation**: `sample/gate.py`, plus
  `.claude/agents/sample-optics.md` for the qualitative half (chamber, sample
  concentration judgement, multiple scattering)

### Lens 5 · Photo-perturbation — implemented

- **Owns**: light level, illumination duty, total dose, wavelength choice
- **Gates**: G10 (photobleaching) G20 (saturation · triplet shelving)
  G21 (light-driving) G22 (total dose)
- **Key questions**
  - Photobleaching: what fraction disappears over the whole movie
  - **Does the excitation light drive the sample** — light-driven active
    particles, photo-crosslinking, LC photo-alignment
  - Local heating: absorption × irradiance. Tweezers at 1064 nm heat via water
    absorption
  - Phototoxicity (living samples)
  - Triplet shelving / blinking
- **Specialty**: **only this lens can say "illumination is an experimental
  variable, not a measurement tool."** The optics lens says raise the light for
  SNR; this lens says that ruins the experiment. Surfacing that conflict is the
  committee's reason to exist. **G21 is that check in code** — it refuses to
  compare irradiance against a guessed threshold, so a photoresponsive sample
  with no measured threshold returns BLOCKED
- **⚠ `photoresponsive` is tri-state, and the third state is the important
  one.** `None` means nobody has asked, which is not a confirmed "no": it warns,
  lands in `assumed_inputs`, and withholds `advances` while still letting
  bleaching and saturation be judged. A default of `False` would have made G21
  silent in exactly the case docs/06 D2 is about — the accident there is the
  unasked question, not a wrong number
- **⚠ No `hard` gate lives in this lens**, so `status: FAIL` is unreachable from
  inside it; the outcomes are BLOCKED, PASS_WITH_CHANGES, PASS. Every check here
  is `bias` or `info`, and a bias finding is a claim about what the data will
  mean — which Lens 6 arbitrates
- **Consume lens 1's excitation chain, do not re-derive it.**
  `IlluminationSetup.from_channel` / `photo.cli --channel` take `k_ex` and
  `k_em` from `optics.path.Channel`, where `σφ` is weighted by how well the
  delivered spectrum overlaps the absorption band. The bare-field path has no
  spectra, so without an explicit `excitation_coupling` it sets that overlap to
  1 and reports `k_ex` as assumed. The bias is toward stricter G10/G20 verdicts
  — false alarms rather than false clears, but a false alarm here is still a
  wrong instruction to cut the light
- **⚠ G20 also invalidates other lenses' numbers.** Past saturation, emission
  stops rising with power, so lens 1's and lens 2's photon budgets (which
  assume linearity — `optics.path.detected_e_per_s`) overestimate signal while
  the dose keeps climbing. Nothing else catches this. Note the scale: FITC
  saturates near 3.5 × 10⁵ W/cm², which a widefield field-of-view never
  reaches, but a focused confocal or spinning-disk spot does
- **Not implemented**: illumination-driven local heating (needs the medium's
  absorption coefficient, which is unrecorded) and phototoxicity (needs a dose
  limit per sample). Trap heating is lens 7's and unimplemented there, so G22's
  companion check reports it as unowned rather than assuming it is handled
- **⚠ BLOCKED on the real instrument today**: `power_at_sample_mw` is empty for
  every line of every source, and no dye has `bleach_photons`. That is the
  correct verdict, not a gap in the lens. With laser power measurement deferred
  by decision (2026-08-19, [07 Phase 0](07-roadmap.md)), it is also the expected
  steady state — the lens should say so once and not keep re-proposing the
  measurement. `bleach_photons` is the half that a literature value could
  unblock today without touching the instrument
- **Implementation**: `photo/gate.py`, plus
  `.claude/agents/photo-perturbation.md` for the qualitative half
  (phototoxicity judgement, triplet/blinking behaviour, light-driving physics)

### Lens 6 · Measurement validity — implemented

- **Owns**: whether the result of all of the above yields the intended physical
  quantity without bias
- **Gates**: G11 (statistical power) G23 (bias ledger) G24 (pixel calibration)
  G25 (photometric calibration) G26 (post-processing) G27 (committee coverage)
- **Key questions**
  - Is **the intended quantity actually extractable** from data taken with this
    setting
  - Are all known biases enumerated and correctable
  - Are the required calibrations (pixel size, dark current, flat-field, light
    level) in hand
  - Do post-processing filters break quantitative validity
  - Does statistical power meet the target error
- **Specialty**: the only lens that **also reads the analysis code.** Which
  script in `D:\codes` will process the data changes the setting requirements.
  The gate does not read it — an undeclared `analysis_script` downgrades the
  verdict to `assumed`, and reading it is the agent half's job
- **⚠ Must run last.** Its primary input is the other lenses' verdicts, not
  hardware facts, so running it first leaves it nothing to review. It reads
  them through a structural protocol (`VerdictLike`) because each lens defines
  its own copy of `Verdict`/`Finding` — eight copies, a known gap. The protocol
  does not require `feasibility` even though all eight now have it: `trapping`
  lacked the field until 2026-08-12, and the protocol should not start
  depending on it just because the asymmetry was fixed
- **G23 is HARD, not BIAS.** The upstream gates are the bias gates; G23 is the
  meta-check that they were all dealt with, so its failure means the intended
  quantity does not survive — a veto on this lens's whole purpose. Its margin
  is the worst *uncorrected* upstream bias margin, so the committee's worst
  unhandled problem stays visible rather than being averaged away
- **G23 checks the declaration, it does not believe it.**
  `validity.setup.CORRECTIONS` names the biases a correction exists for
  (crosstalk → unmixing, motion blur → Savin–Doyle, photobleaching → decay
  correction, lateral drift → registration) and `UNCORRECTABLE` the ones it does
  not (RI mismatch, coverslip, saturation, light-driving, evaporation).
  Declaring `geometry.ri_mismatch` in `corrections_applied` used to clear it,
  because the declaration was matched against nothing at all; now the gate
  answers that no such correction is implemented and keeps the bias. A code in
  neither table is accepted — a gate the tables have not caught up with should
  not block work — but it costs the verdict its `measured` grade, so an
  unaudited clearance cannot advance
- **The verdict's unit can be the physical quantity, not the channel.** A
  session's MSD can be biased while its intensity profile is fine, and one
  status cannot say that. `validity.setup.BIAS_SCOPE` records which calibrations
  each bias damages, so the FAIL lands only on the quantities that rest on
  them; a bias the table does not scope damages every quantity, which is the
  conservative default and the only honest one where nothing scopes it. Pass
  `intended_quantities` and `gate.evaluate` judges each separately and returns
  the aggregate, with every per-quantity verdict in
  `metrics["validity.per_quantity"]` and each finding tagged with the quantity
  it belongs to. Out-of-scope biases are named rather than dropped — they still
  stand against the quantities they do damage
- **G27 is currently the only thing that notices the committee never met.**
  There is no orchestrator: each lens is invoked by its own CLI, so a standing
  lens that never ran, or one that returned BLOCKED, would otherwise go
  unremarked. A BLOCKED upstream lens fails G27 — validity cannot sit on top of
  a lens that had no basis to decide
- **Which calibrations matter depends on the quantity.** A wrong pixel size
  ruins a diffusion coefficient and is irrelevant to a stoichiometry;
  flat-field is the reverse. `validity.setup.QUANTITY_REQUIREMENTS` encodes
  that, and an unlisted quantity BLOCKs rather than being checked against
  guessed criteria
- **Implementation**: `validity/gate.py`, plus
  `.claude/agents/measurement-validity.md` for the qualitative half (reading
  the analysis code, judging whether the intended quantity is extractable at
  all)

### Lens 7 · Optical tweezers (conditional) — implemented; heating ungated by decision

- **Gates**: G14
- **Inputs**: particle radius, particle refractive index, medium refractive
  index, wavelength, NA, power at sample, viscosity, temperature, number of
  traps
- **Computes**
  - Regime determination: `a ≪ λ` Rayleigh / `a ≫ λ` ray optics / **the
    intermediate regime needs GLMT**
  - Trap stiffness κ, trap depth U/kT, corner frequency `f_c = κ/(2πγ)`
  - Power splitting for multiple traps
- **Cross-lens constraint**: power-spectrum calibration needs `f_s ≳ 10 f_c` →
  passed to the detection lens
- **⚠ Intermediate regime**: at `a/λ ~ 1` both limits are invalid. **Do not
  answer with an approximation — return BLOCKED**
- **⚠ Local heating is NOT implemented, by decision.** `trapping/` has only
  `confinement`, `trap_depth`, and `sampling` — there is no heating computation
  and none is planned (user, 2026-08-19). Water absorption at 1064 nm changes
  viscosity and therefore D, which contaminates the measured quantity in
  microrheology ([06 D6](06-pitfalls.md)). Nothing catches this, and Lens 5
  deliberately does not cover it either (it handles visible excitation light
  only). It is one of the project's **named** ungated risks, not an oversight —
  [01 §7](01-architecture.md)
- **⚠ No Faxén wall-drag correction, by decision.** `corner_frequency_hz` uses
  the unbounded-medium Stokes drag, so a bead held near the coverslip carries an
  uncorrected bias (+12.7% for a 4 µm bead at h = 10 µm). The sanctioned route
  is in-situ power-spectrum calibration at the actual working height, which
  returns κ and the wall-corrected γ together — and G14 requires that
  calibration regardless
- **Scope**: water-based media only for now (user, 2026-08-19). A non-water
  medium needs its own measured viscosity passed explicitly
  (`--viscosity-pa-s`); the CLI refuses to default one rather than guessing
- **Deferred**: dial-% → mW measured calibration, under the 2026-08-19 decision
  that defers all laser power measurement. Until it lands, `LaserCalibration.points`
  is empty and every trapping verdict is `evidence: assumed`, so none can advance
  → [`kb/decisions/2026-08-19-lens-7-scope.md`](../kb/decisions/2026-08-19-lens-7-scope.md)
- **Implementation**: `trapping/gate.py`

### Lens 8 · Mechanical & environmental (conditional, >30 min) — implemented

- **Owns**: drift (thermal, mechanical), PFS lock state, evaporation,
  sedimentation, vibration, stage repeatability
- **Gates**: G28 (PFS lock) G29 (axial drift) G30 (lateral drift)
  G31 (sedimentation) G32 (evaporation)
- The archive contains sessions where `PFS in Range` reads `Out of Range` — PFS
  can be on without being locked. **G28 catches this and needs no new
  measurement**: it is a state check on metadata that already exists, and an
  unrecorded range flag is itself a failure, because the on state alone cannot
  tell a held focus from a wandered one (docs/06 D7)
- **G31 is the one gate here that works today.** Stokes settling follows from
  particle radius, density contrast and viscosity — sample properties, not
  instrument measurements. It bites hard: a 1 µm polystyrene sphere in water
  settles ~98 µm in an hour against a 0.375 µm depth of field on the 100x oil,
  so the population in the focal plane at the end is not the one that started
  there. Density-matching removes the term entirely
- **⚠ G29 BLOCKS.** No drift rate exists anywhere in the repo, and a guessed one
  would decide the gate wrongly in whichever direction the guess leaned. The
  measurement is cheap: park on a fixed feature with PFS off and log focus every
  few minutes for an hour from a disturbed enclosure
- **⚠ Vibration and stage repeatability are ungated**, and the lens says so
  rather than passing quietly — there is no measurement channel for either. A
  quiet pass on that line is an absence of evidence, not evidence of stability
- **Conditional threshold is reported, not enforced.** docs/01 §4 convenes this
  lens past 30 min, but settling and drift scale continuously with time and do
  not switch on there. Whether to call the lens is the caller's decision; when
  called, it answers
- **Implementation**: `stability/gate.py`, plus
  `.claude/agents/mechanical-env.md` for the qualitative half (vibration, stage
  repeatability, thermal environment, whether the settling figure applies, what
  each remedy costs another lens)

---

## 6. Orchestration

```
generate proposal
   │
   ├─ computational lenses (1·2·3·7) in parallel   ← code. deterministic. fast
   │      any hard gate m<1 → stop immediately, return a revision
   │
   ├─ judgment lenses (4·5·6·8) in parallel        ← LLM subagents
   │      receive the computational lens results as input
   │
   ├─ synthesis
   │      difficulty grade = worst soft/bias gate
   │      improvement proposals = sensitivity analysis of the bottleneck gate
   │
   └─ verdict
         all advance  →  confirmed
         otherwise    →  re-propose with fix instructions (at most 3 rounds)
```

**Why the computational lenses run first**: it prevents the waste of LLM lenses
deliberating over a physically impossible proposal. And the LLM lenses must
receive the computed results **as input** — they must not generate the numbers
themselves.

### Deadlock handling

If it does not converge within 3 rounds, **present the conflict itself to the
human.**

```
There are incompatible requirements.

  Lens 5 (photo-perturbation): light level ≤5%. Above that the Janus particles
                               are light-driven.
                               Basis: [kb/samples/active-janus-colloid.md]
  Lens 2 (detection):          reaching SNR 5 at 20 Hz needs at least 30%.
                               Basis: photon budget calculation [details]

Options:
  (a) lower frame rate to 10 Hz  → light level drops to 15%. Still above 5%
  (b) brighter label             → required light drops proportionally. Reagent
                                   change needed
  (c) accept the light-driven perturbation
                                 → the measured quantity changes from "passive
                                   diffusion" to "light-driven motion"
  (d) excite at a different wavelength
                                 → best if it can avoid the Janus absorption
                                   band. ⚠ needs the absorption spectrum

What would you like to concede?
```

**This is correct behavior, not failure.** Failure would be forcibly papering
over incompatible requirements.

---

## 7. Loosening — how a gate is allowed to become less strict

**Today one `UNKNOWN` among the 32 blocks the verdict.** That is deliberate and
it is the right default *while the record is empty*: with no runs to check a
verdict against, the only defensible thing a gate can do with an unknown is
refuse and name it.

It is not meant to stay that strict. As experiments accumulate and the agent's
verdicts can be compared against what the instrument actually did, strictness
relaxes — **gradually, against the record, and never against confidence.**

### What relaxes, and what does not

| Relaxes | Stays |
|---|---|
| **What counts as sufficient evidence for an input.** The ladder already exists: `BLOCKED` → a literature value that lets the gate compute but never advance ([`kb/literature/`](../kb/literature/)) → measured once → measured repeatedly with a known spread, at which point it becomes a default carrying its own tolerance | **A hard gate's threshold.** Trust does not raise the disk's write bandwidth. If G12a is exceeded the frames drop, on run 1 and on run 500 |
| **Whether a gate is asked at all.** An input that has come back the same on N consecutive runs on this instrument can default instead of prompting | **The bias gates.** A bias gate fails by producing data that looks right, so a record of successful runs is precisely the evidence that cannot detect it. G8, G12b/c, G23–G26 do not loosen on accumulated success |
| **The treatment of "never asked".** Sample photoresponsiveness warns on every run today; a system with a recorded answer should stop being asked | **Saying what was relaxed.** Every loosening is a dated [`kb/decisions/`](../kb/decisions/) entry naming the evidence that bought it, and is revertible — the falsifier field is what makes it revertible |

The promotion target already exists: a value that graduates lands in
[`kb/calibrations/`](../kb/calibrations/) with its date and its scope, so a
relaxation is a *change of tier*, not a lowered bar.

### The hazard, and the only measure that avoids it

*"The agent has not been wrong yet"* is survivorship. **A gate that never fired
is not evidence that it was unnecessary** — it may be evidence that it was never
reached, which is what happened once already: a gate that refused 80 of 83 specs
with zero real failures went unnoticed for weeks because the runner never called
it.

So the quantity to accumulate is **not** the count of runs that went well. It is
**how often a refusal was later shown to have been right** — which requires
recording the outcome of refusals, not only the outcome of acquisitions. Until
refusals carry outcomes, "trust in the agent" has nothing to be measured
against, and a relaxation would be a preference wearing evidence's clothes. The
post-hoc record that would supply it is items 4 and 5 of the README's remaining
work.

---

## 8. Open questions

- [ ] Are the difficulty-grade boundaries (3 / 1.5 / 1.0 / 0.5 / 0.2)
      appropriate — adjust with real use
- [ ] How far to populate the `data/interventions.yaml` intervention catalog
- [ ] How lens 6 should read the analysis scripts in `D:\codes`
- [ ] Should the user be able to explicitly override a gate — it should be
      possible, but **the fact of the override must be recorded in
      kb/decisions**
