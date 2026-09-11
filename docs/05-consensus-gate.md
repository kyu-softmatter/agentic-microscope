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
| ~~G11 Statistical power~~ | — | **removed 2026-09-11**: it counted independent samples and the frames of one trapped bead are correlated. `soft` survives elsewhere (optics.collection, detection.sampling, detection.snr), so §2's level-3 tie-break still has work |
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
               G23 bias ledger       m=1.8

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
                                            ⚠ 2× bleaching dose (ungated since 2026-09-09)
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

### ⚠ Neither G8 nor G9 owns the frame period (2026-09-09)

The frame period is an input to both and a decision belonging to neither, so
`Acquisition` carries it explicitly with a provenance:

| `fps_source` | set by | G9 | G8 |
|---|---|---|---|
| `undecided` | neither field supplied | INFO — reports the realizable rate | **INFO — reports the duty at the camera's floor as an upper bound, ungraded** |
| `requested` | `target_fps` | grades realizability (`hard`) | grades duty at that period, labelled requested |
| `measured` | `achieved_fps` | grades against the observed rate | grades duty at the observed period |

`measured` and `requested` are the same two tokens as lens 3's
`compute.setup.FPS_SOURCES`, because **G12b is this same distinction seen from
the data-rate side**; `undecided` is lens 2's addition, since lens 3 cannot
compute a data rate without a rate at all.

**Why the two do not merge.** They share `t_frame` and conflict over it, which
makes it a cross-gate constraint rather than one gate. G9 asks a hardware
question and is `hard`; G8 asks a measurement question and is `bias`. Merging
them would force a single kind, and [05 §2](#2-three-kinds-of-gate)'s precedence
runs on that kind — a merged gate would either stop a proposal over a
correctable MSD bias or wave through a physically unreachable frame rate.

**Why `undecided` reports instead of failing.** A gate that fails on a period
nobody has chosen is failing a decision that has not been made. The rate is
settled in synthesis, with lens 3's bandwidth arithmetic and lens 7's `G14`
sampling requirement in hand (KH, 2026-09-09) —
[`kb/decisions/2026-09-09-frame-period-is-not-a-gate-input.md`](../kb/decisions/2026-09-09-frame-period-is-not-a-gate-input.md).

**Both gates report the window, from their own end** (KH, 2026-09-09), so
synthesis takes a `min` instead of re-deriving either:

| number | from | meaning |
|---|---|---|
| `fps_hardware_max` | G9 | `1/t_frame` — the readout ceiling at this ROI |
| `fps_at_duty_limit` | **both** | `0.3/t_exp` — the fastest rate this exposure keeps duty ≤ 30% at |
| `fps_usable_max` | G9 | the `min` of the two, and which one binds |
| `exposure_max_ms` | G8 | `0.3 × t_frame` — the longest exposure at the period in use |
| `roi_height_min_px` | G8 | the smallest ROI whose readout is long enough for this exposure |

⚠ **`roi_height_min_px` exists because there is no minimum frame rate to give.**
The period is `max(t_exp, t_readout)` and this camera has no interval control, so
*slowing down means lengthening the exposure*, which drives duty toward 100 %
rather than away from it. ROI height is the only lever that buys a longer period
at a fixed exposure. A gate that answered "run slower" here would be wrong on
this instrument, and G8's action text says so explicitly.

### Lens 5 · Photo-perturbation — implemented

- **Owns**: light level, illumination duty, total dose, wavelength choice
- **Gates**: G21 (light-driving) G22 (total dose).
  **G20 (saturation · triplet shelving) was removed 2026-09-09** and its number
  is not reused — `kb/decisions/2026-09-09-g20-saturation-removed.md`
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
  lands in `assumed_inputs`, and withholds `advances` while still letting the
  dose be judged. A default of `False` would have made G21
  silent in exactly the case docs/06 D2 is about — the accident there is the
  unasked question, not a wrong number
- **⚠ No `hard` gate lives in this lens**, so `status: FAIL` is unreachable from
  inside it; the outcomes are BLOCKED, PASS_WITH_CHANGES, PASS. Every check here
  is `bias` or `info`, and a bias finding is a claim about what the data will
  mean — which Lens 6 arbitrates
- **⚠ Since G20 went, no gate in this lens consumes a dye constant.**
  `IlluminationSetup.from_channel` still carries `k_ex` and `k_em` from
  `optics.path.Channel`, and `--dye` still fills ε, Φ and τ from the registry,
  but nothing reads them: G21 compares irradiance against a per-sample measured
  threshold and G22 accumulates energy. So the two build paths now differ only
  in the label they print, and the `excitation_coupling` assumption is no longer
  on the evidence axis
- **⚠ The linearity assumption is now unguarded, and it is not this lens's any
  more.** Past saturation, emission stops rising with power, so lens 1's and
  lens 2's photon budgets (which assume linearity —
  `optics.path.detected_e_per_s`) overestimate signal while the dose keeps
  climbing. **Nothing catches this today.** Note the scale: FITC saturates near
  3.5 × 10⁵ W/cm², which a widefield field-of-view never reaches, but a focused
  confocal or spinning-disk spot does — so the exposure is real for the
  spinning-disk and confocal paths and negligible for widefield epi
- **Not implemented**: illumination-driven local heating (needs the medium's
  absorption coefficient, which is unrecorded) and phototoxicity (needs a dose
  limit per sample). Trap heating is lens 7's and unimplemented there, so G22's
  companion check reports it as unowned rather than assuming it is handled
- **⚠ Historical, superseded 2026-09-09**: `power_at_sample_mw` is empty for
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
- **Gates**: G23 (bias ledger) G24 (pixel calibration) G25 (photometric
  calibration) G27 (committee coverage)
- **⚠ G11 and G26 left on 2026-09-11** and neither number is reused. **G11 was
  the only quantity this lens computed**, so the lens now computes nothing at
  all — every check reads another lens's verdict or a declaration, and `LIMITS`
  is empty. `1/sqrt(N_p × N_f)` counts *independent* samples, and one trapped
  bead at 520 fps has 6.3 correlated frames per relaxation time: it read 0.566%
  where ~2.0% is defensible. **G26** gated on a self-declared `despeckle`
  boolean nobody verifies, and `detection/recommend.py` already refuses on the
  same fact where it does damage
  → [`kb/decisions/2026-09-11-g11-and-g26-removed.md`](../kb/decisions/2026-09-11-g11-and-g26-removed.md)
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

### Lens 8 · Mechanical & environmental (conditional, >30 min) — **reporting section**

- **⚠ NOT A JUDGING LENS AS OF 2026-09-10** — the second reporting section,
  after lens 5 the same day. Every check is INFO, `LIMITS` is empty, and
  `stability.gate.evaluate` returns `status: REPORT`, `feasibility: "N/A"`,
  `advances: None`. **Nothing in lens 8 can pass or fail**, so it cannot stop a
  proposal and cannot bless one
  → [`kb/decisions/2026-09-10-lens-8-becomes-a-reporting-section.md`](../kb/decisions/2026-09-10-lens-8-becomes-a-reporting-section.md)
- **Owns**: drift (thermal, mechanical), PFS lock state, evaporation,
  sedimentation, vibration, stage repeatability — and **reports on two of
  them**
- **Reports** (numbers kept, grading gone): G31 (settling velocity and the time
  to equilibrium) G32 (evaporative concentration) plus `drift_budget` (the
  drift rate the run could absorb) and `convening`
- **⚠ THREE GATES LEFT THIS LENS ON 2026-09-10** and none of the numbers is
  reused: G28 (PFS lock), G29 (axial drift), G30 (lateral drift). G28 was
  reading the wrong property — `kb/decisions/2026-09-10-g28-moves-to-the-hardware-stage.md`.
  G29 and G30 were reading the right one at the wrong time:

  > **A planning gate judges a proposal from what is known before the run
  > starts.** *"실험 중 측정해야한다면 디자인 요소로는 적합하지 않은듯"* — KH,
  > 2026-09-10. If it has to be measured during the experiment, it is not a
  > design element.

  Both drift rates *are* obtainable here — `config/session/focus_monitor.py`
  already logs `ZDrive` and both cameras several times a second, and most of the
  beads in `data/particles.yaml` are stuck to the coverslip and serve as lateral
  fiducials — which is why the answer was to move the judgement rather than
  demand the data. `compute.drops` is the precedent: it reads an acquisition
  that already ran, from its own timestamps.
  `kb/decisions/2026-09-10-drift-is-not-a-design-element.md`
- **What replaced them reports instead of gating.** `stability.drift_budget`
  (INFO, unnumbered) inverts the question: duration and depth of field are both
  planning inputs, so the lens publishes **the drift rate the run could
  absorb** — 6.3 nm/min for one full DOF on the 100x oil over an hour, half
  that for half a DOF — and leaves the measurement to the run. No threshold:
  one DOF is a definition, not a limit
- **Drift costs the evidence tier permanently.** The `assumed_inputs` entry for
  it is unconditional, so **this lens can never report `evidence: measured`**
  and a long acquisition never `advances` on lens 8 alone. Deliberate: the
  dominant bias on a long run is not discharged by planning it well
- The archive contains sessions where `PFS in Range` reads `Out of Range` — PFS
  can be on without being locked. **The hardware stage catches this; no gate does, and it needs no new
  measurement**: it is a state check on metadata that already exists, and an
  unrecorded range flag is itself a failure, because the on state alone cannot
  tell a held focus from a wandered one (docs/06 D7)
- **G31 reports a velocity and a clock.** Stokes settling follows from particle
  radius, density contrast and viscosity — sample properties, not instrument
  measurements — and 5 µm polystyrene in water moves **41 µm/min**, reaching the
  bottom of a 100 µm chamber in **2.4 min**. It stopped comparing that to the
  depth of field on 2026-09-10, for two reasons: **a trapped bead does not
  settle**, and gravity is not what decides where it sits. The buoyant weight
  is **0.032 pN** against the trap's own axial force of **9.56 pN at 100 mW**
  (`trapping.goa.trap_force`'s second return value, already computed beside the
  radial stiffness), so **gravity spends 0.34% of the axial budget** — and that
  ratio **needs no κ_z**, because the gravitational sag and the scattering
  offset divide by the same one (KH, 2026-09-11). This lens also has no
  `trapped` field), and the free-settling case is **lens 4's G19**,
  which assumes the settled state this now reports the arrival time of.
  Density-matching removes the term entirely
- **⚠ Lens 8 contributes nothing to lens 6's bias ledger.** G23 collects
  `bias`-kind findings and lens 8 has none left. Its drift and evaporation
  notes live in `assumed_inputs`, and lens 6's single-quantity path does not
  read upstream `assumed_inputs` — only the multi-quantity aggregation unions
  them, and that is across lens 6's own verdicts. **So the drift bias currently
  reaches a human reader and no gate.** Open, and lens 6's to close
- **⚠ Vibration is gone from the lens entirely**, and not for want of a
  measurement channel: **every part of this microscope sits on the same
  isolation table, so the camera and the sample move together.** An image shows
  their *relative* motion and common-mode motion of a rigid assembly cancels
  out of it, so a stuck-bead PSD in the acquisition would not supply it either.
  Contrast drift — differential expansion in the path between objective and
  holder, which does not cancel — and that asymmetry is why `drift_budget`
  survives. **Stage repeatability remains ungated and has no check at all**
- **Conditional threshold is reported, not enforced.** docs/01 §4 convenes this
  lens past 30 min, but settling and drift scale continuously with time and do
  not switch on there. Whether to call the lens is the caller's decision; when
  called, it answers
- **Implementation**: `stability/gate.py`, plus
  `.claude/agents/mechanical-env.md` for the qualitative half (vibration, stage
  repeatability, thermal environment, whether the settling figure applies, what
  each remedy costs another lens)

---

## 6. Orchestration — goal to instrument

**The chain is KH's, stated 2026-09-09.** Seven stages, and the committee of
§5 is only the third of them. What each stage *is* comes from that statement;
where the artefacts live and how the stages are split between code, subagent
and skill is this repository's proposal on top of it — the two are separated in
"Stated vs proposed" at the end.

| | Stage | Runs as | Exists? |
|---:|---|---|---|
| 1 | **Question** — a research goal, in the operator's words | conversation | not formalised |
| 2 | **Interpretation** — goal → a concrete setting proposal | main agent | not formalised |
| 3 | **Verification** — the eight lenses | code + subagents | ✅ code for all 8; agent files for 5 |
| 4 | **Decision** — difficulty grade, interventions, or a deadlock handed up | main agent | ✅ §3 · §4 · below |
| 5 | **Hardware plan** — one `kb/plans/` entry per run | main agent writes it | ✗ designed 2026-09-09, not built |
| 6 | **Skill dispatch** — one skill per subsystem, each reading that plan | `.claude/skills/` | ✗ the directory does not exist |
| 7 | **Actuation** — the skill calls the instrument | MCP | ⚠ **half.** See below |

### Stage 3, corrected

```
proposal
   │
   ├─ 1 · 2 · 3 (+7 if trapping)   code, in parallel   deterministic, fast
   │      any hard gate m<1 → stop immediately, return a revision
   │
   ├─ 4 · 5 (+8 if >30 min)        subagents, parallel
   │      receive the computed results as input
   │
   ├─ 6                            subagent, alone, last
   │      reviews the verdicts of every lens above
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

**Lens 6 is not in the parallel block, and used to be.** It reviews what the
other lenses returned, so it cannot run beside them. The precedence this sits
under — the gate's *kind* outranking the lens, and the nine exceptions — is
[`CLAUDE.md §2`](../CLAUDE.md).

Three lenses have no agent file: 1, 2 and 7 are code only. That is not an
oversight — their verdicts have a closed form — but it does mean **there is no
qualitative half to ask** when one of them returns something surprising.

### Stage 5 · the hardware plan

One markdown file per run, in `kb/plans/YYYY-MM-DD-<slug>.md`. It is deliberately
the **first two sections of the decision-log format** in
[02 §9](02-knowledge-base.md) — `Request` and `Proposed setting + rationale` —
so that when the run happens, the same entry gains `Setting actually used`,
`Outcome` and `What was learned`, and graduates into `kb/decisions/`. A plan
that was never run stays visible as one, because the index renders its `status`.

It exists so that stage 6 has something to read that is **not the conversation**.
A skill that reconstructs the intent from chat history is a skill that will one
day reconstruct it wrong.

### Stage 6 · one skill per subsystem

Each skill reads the plan, takes only the part addressed to its own subsystem,
and supplies the context that subsystem needs — which flags are required, which
calibrations the last objective change invalidated, what the driver's refusals
mean. Nothing here decides anything the committee did not already decide.

### Stage 7 · what can actually be reached

⚠ **Half of the instrument has no tool surface.** [`mcp_server/`](../mcp_server/)
is the tweezers and the piezo — nine tools. **The Micro-Manager path is absent
entirely**: no objective, no `ZDrive`, no `XYStage`, no camera. So stages 6–7 can
be written today for two subsystems out of the set the committee reasons about.

⚠ And **no MCP tool has reached a device** ([07 Phase 5](07-roadmap.md)). On
2026-09-09 the server did not start at all in one session — `CONNECTION_CLOSED`.

### The knowledge base, at every stage

Any stage may need something out of `kb/`, and the route depends on the shape of
the answer, not on the stage:

| Need | Route | Why |
|---|---|---|
| Which entry answers this | [`kb/INDEX.md`](../kb/INDEX.md) | 40 lines. Read it before grepping 710 KB |
| A specific value, with provenance | the entry itself | **Cite the entry, never the index line** ([09 §7](09-knowledge-capture.md)) |
| A lens's own record | the lens's subagent reads it directly | `2026-08-19-lens-*.md` are 5–17 KB and named after the lens. A round trip through the main agent buys nothing |
| The same answer for several lenses | main agent fetches once, hands it down | One read, N recipients |
| Digest a large entry | a subagent | `kb/systems/current.md` is 1,634 lines. A subagent burns that in its own window and returns a summary — at the cost that a summary is not a citation |
| **Write** anything to `kb/` | a **skill**, on the main agent | [09 §7](09-knowledge-capture.md) requires asking the operator for the `Why` and the falsifier, **and a subagent cannot ask a human anything.** It runs to completion and reports |

The read side is a candidate for MCP tools over
[`knowledge/index.py`](../knowledge/index.py), which would make the citation
shape structural rather than instructed — a tool has no model in it to
paraphrase with. The constraint is that **an MCP result lands in the caller's
context**, so every such tool must be bounded: a section, not a file.

### Stated vs proposed

| | Source |
|---|---|
| The seven stages, in this order | **KH, 2026-09-09** |
| A plan file that the hardware skills read, one skill per subsystem | **KH, 2026-09-09** |
| The plan lives under `kb/` | **KH, 2026-09-09** |
| Main agent, not a subagent, fetches from `kb/` on a lens's behalf | **KH, 2026-09-09** |
| `kb/plans/` specifically, and its graduation into a decision record | this repository |
| Lens 6 alone and last | this repository, correcting the earlier diagram |
| The read/write split in the table above | this repository |

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
| **Whether a gate is asked at all.** An input that has come back the same on N consecutive runs on this instrument can default instead of prompting | **The bias gates.** A bias gate fails by producing data that looks right, so a record of successful runs is precisely the evidence that cannot detect it. G8, G12b/c, G23–G25 do not loosen on accumulated success |
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
