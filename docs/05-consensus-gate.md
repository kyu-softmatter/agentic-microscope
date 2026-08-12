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

### Classification of the 14 gates

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
| G12 Data rate | hard | **Silent frame drops** |
| G13 Buffer | hard | ″ |
| G14 Tweezers sampling | bias | κ calibration value is wrong |

---

## 3. Difficulty grades

Each gate reports its **margin** as a ratio: `m = achieved / required`.

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
- **Gates**: G12 G13
- **Key questions**
  - Is `R = W·H·2·f` below 70% of sustained disk write bandwidth
  - Does the buffer hold at least 5 seconds
  - Does the total volume fit in the free space
  - With online processing (tracking, compression) attached, is CPU time per
    frame < 1/f
  - Can RAM carry the buffer + OS + analysis
- **Specialty**: **the only lens that catches silent failure.** Frame drops
  raise no error and surface only as `ElapsedTime-ms` intervals larger than
  expected
- **Post-hoc verification**: after acquisition, the variance of `ElapsedTime`
  differences → drop detection. Applicable to the existing archive today
- **Implementation**: `compute/gate.py`

### Lens 4 · Sample geometry & optics — agent draft, no code

- **Owns**: objective choice, immersion, coverslip thickness, imaging depth,
  chamber
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
- **Implementation**: `.claude/agents/sample-optics.md`

### Lens 5 · Photo-perturbation — agent draft, no code

- **Owns**: light level, illumination duty, total dose, wavelength choice
- **Gates**: G10
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
  committee's reason to exist
- **Implementation**: `.claude/agents/photo-perturbation.md`

### Lens 6 · Measurement validity — agent draft, no code

- **Owns**: whether the result of all of the above yields the intended physical
  quantity without bias
- **Gates**: G11 + final review of every bias gate
- **Key questions**
  - Is **the intended quantity actually extractable** from data taken with this
    setting
  - Are all known biases enumerated and correctable
  - Are the required calibrations (pixel size, dark current, flat-field, light
    level) in hand
  - Do post-processing filters break quantitative validity
  - Does statistical power meet the target error
- **Specialty**: the only lens that **also reads the analysis code.** Which
  script in `D:\codes` will process the data changes the setting requirements
- **Implementation**: `.claude/agents/measurement-validity.md`

### Lens 7 · Optical tweezers (conditional) — implemented

- **Gates**: G14
- **Inputs**: particle radius, particle refractive index, medium refractive
  index, wavelength, NA, power at sample, viscosity, temperature, number of
  traps
- **Computes**
  - Regime determination: `a ≪ λ` Rayleigh / `a ≫ λ` ray optics / **the
    intermediate regime needs GLMT**
  - Trap stiffness κ, trap depth U/kT, corner frequency `f_c = κ/(2πγ)`
  - Power splitting for multiple traps
  - Local heating
- **Cross-lens constraint**: power-spectrum calibration needs `f_s ≳ 10 f_c` →
  passed to the detection lens
- **⚠ Intermediate regime**: at `a/λ ~ 1` both limits are invalid. **Do not
  answer with an approximation — return BLOCKED**
- **Remaining**: dial-% → mW measured calibration
- **Implementation**: `trapping/gate.py`

### Lens 8 · Mechanical & environmental (conditional, >30 min) — not implemented

- Drift (thermal, mechanical), PFS lock state, evaporation, sedimentation,
  vibration, stage repeatability
- The archive contains sessions where `PFS in Range` reads `Out of Range` — PFS
  can be on without being locked

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

## 7. Open questions

- [ ] Are the difficulty-grade boundaries (3 / 1.5 / 1.0 / 0.5 / 0.2)
      appropriate — adjust with real use
- [ ] How far to populate the `data/interventions.yaml` intervention catalog
- [ ] How lens 6 should read the analysis scripts in `D:\codes`
- [ ] Should the user be able to explicitly override a gate — it should be
      possible, but **the fact of the override must be recorded in
      kb/decisions**
