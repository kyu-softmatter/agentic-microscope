# Live demo — three examples for an advisor walkthrough

> **Purpose**: type these in, live, and show the committee working. ~10 minutes.
> **Written**: 2026-08-18. Every command below was executed and every quoted
> number is real output, not an illustration.
> **Language**: English throughout (commands, output, narration).

## The one experiment behind all three demos

A single physical setup, so the advisor only has to hold one picture in mind:

| | Target A — the probe | Target B — the tracers |
|---|---|---|
| what | **5 µm polystyrene sphere** | 0.5 µm polystyrene spheres |
| how many | 1 (or 2, for pair interaction) | dilute, ~50–200 in field |
| held by | **1064 nm optical trap** | nothing — freely diffusing |
| driven | **random direction, 0–30 µm/s** | advected by the probe's flow |
| fluorophore | **ATTO647N** — 640 ex, 668 em | **ATTO488** — 488 ex, 520 em |
| camera | Kinetix_red (transmit side of DM A561LP) | Kinetix_blue (reflect side) |
| measures | **force on the probe**, position controlled | the flow field / bath response |

Active microrheology: drive a probe at a known velocity, read the force from the
trap, and watch the medium respond through the tracers. Both colours are acquired
**simultaneously** on the two cameras — at 30 µm/s a sequential channel switch of
even 4 ms would put a 120 nm registration error between the two populations,
comparable to the whole PSF.

Setup once per session:

```bash
cd "path\to\experimentalist"
```

The three demos are then: **it designs**, **it catches what would have looked
fine**, and **it refuses to make things up**.

---

# Demo 1 — It designs the experiment, and the numbers are physics

**Say**: "I describe the experiment. Nothing here is the model's opinion — every
number comes from a closed form in the code."

### 1a. Which objective, and why

```bash
python -m sample.cli check --objective 40x-WI --imaging-depth-um 20
```

Then the same question for the oil objective:

```bash
python -m sample.cli check --objective 100x-Oil --imaging-depth-um 20
```

The first grades `HARD` with `geometry.ri_mismatch` at margin **10.00**; the
second grades `MARGINAL` with the same check at **0.50** and says:

> Refractive-index mismatch 0.185 (oil n = 1.518 vs sample medium n = 1.333) at
> 20.0 um depth exceeds the 10.0 um screening limit. Spherical aberration grows
> with depth and the axial scale is off by 12.2%.

**Point to make**: the water objective wins on an aqueous sample, and the tool
says *by how much* and *why*, not just which.

### 1b. The force curve on the 5 µm probe

```bash
python -m trapping.cli force-curve --dial 100 --max-power-w 0.01634 --n-traps 1 --radius-um 2.5 --n-bead 1.57 --n-medium 1.333 --na 1.25 --n-points 8
```

```
bead: r=2.5 um  n=1.57   medium n=1.333   NA=1.25  lambda0=1064.0 nm
laser: dial=100.0%  n_traps=1  -> 16.3400 mW at this trap

   dx (um)   F_radial (pN)    F_axial (pN)
     0.000         -0.0000          1.3872
     0.350         -1.9969          1.4097
     ...
     2.100        -17.1375          4.6328

radial stiffness at x=0: 5.6638 pN/um
```

This is a port of the lab's own `GOA_ab.m` (Ashkin's ray-optics model), with two
sign/geometry errors in the MATLAB corrected — documented at the top of
[`trapping/goa.py`](../../trapping/goa.py).

**Point to make**: 16.34 mW at the sample gives κ = 5.66 pN/µm and ~18.7 pN of
escape force. Stokes drag on this bead at 30 µm/s is 1.42 pN, so there is a 13×
margin. And note the stderr line it prints unprompted:

> note: laser calibration is a placeholder ... Pass measured dial%->W points
> before trusting absolute force numbers.

### 1c. The full trapping verdict

```bash
python -m trapping.cli check --dial 100 --max-power-w 0.01634 --n-traps 1 --radius-um 2.5 --n-bead 1.57 --n-medium 1.333 --na 1.25 --viscosity-pa-s 1.0016e-3 --detector-fps 240
```

```
trap: r=2.5 um bead, n_traps=1, dial=100.0%   ->  PASS
NA:       design 1.25  (fully admitted by n=1.333)
evidence: assumed   confidence: low   advances: NO

  margins (achieved / required; 1.0 = exactly at the limit)
      1.26  sampling             ############
     10.00  effective_na         ##############################
     10.00  trap.confinement     ##############################
     10.00  trap.depth           ##############################
```

**Point to make — the two-axis verdict.** It says `PASS` *and* `advances: NO`.
The physics is fine; the evidence is not, because the dial%→mW curve has never
been measured. A `PASS` that cannot advance is the design working as intended:
it will not let an unmeasured input be laundered into a confirmed setting.

### 1d. Do the tracers stay in the focal plane, and are there enough of them

```bash
python -m stability.cli check --duration-min 1 --objective 40x-WI --emission-nm 520 --axial-drift-nm-per-min 5 --pfs-on --pfs-in-range --particle-radius-um 0.25 --delta-density 50 --viscosity 1.0016e-3 --sealed
```

`PASS`, `TIGHT`, sedimentation margin **1.09** — polystyrene tracers hold for a
one-minute movie with almost nothing to spare.

```bash
python -m validity.cli power --n-particles 200 --n-frames 14400 --target-error 0.05
```

Relative error **0.059%** against a 5% target — **84.9× headroom**.

**Point to make**: statistics are not the constraint here. That is a licence to
keep the tracer concentration *low*, which also keeps them from crowding the
field and from being dragged into the trap.

---

# Demo 2 — It catches the error that would have produced a publishable-looking figure

**Say**: "These are the two mistakes I would actually have made. Neither one
crashes. Both would have produced clean-looking data and a wrong number."

### 2a. "Let's use more power so we don't lose the bead"

Same command as 1c, with the laser at 100 mW instead of 16.34 mW:

```bash
python -m trapping.cli check --dial 100 --max-power-w 0.100 --n-traps 1 --radius-um 2.5 --n-bead 1.57 --n-medium 1.333 --na 1.25 --viscosity-pa-s 1.0016e-3 --detector-fps 240
```

```
      0.20  sampling.aliased     ##

    [FAIL] sampling.aliased
           240 fps is below the 1169 fps G14 needs to resolve a 117 Hz corner
           frequency without aliasing bias.
        -> Raise the frame rate (lens 2), or lower power / use a softer trap to
           bring the corner frequency down.
```

**Point to make — this is the counterintuitive one.** Raising the power made the
experiment *worse*. A stiffer trap has a higher corner frequency, and once
`f_c` outruns the camera the Brownian spectrum aliases and the trap calibration
is biased — so the force you report is wrong. There is a clean identity behind
it, worth writing on the board:

```
dx = γv/κ   and   f_c = κ/(2πγ)     ⟹     f_c = v/(2π·dx)
```

The sampling requirement depends only on drive speed and the bead lag you
tolerate — **not on bead size and not on laser power**. So "more power for
safety" buys nothing but a faster camera requirement.

### 2b. "Silica tracers are cheaper and brighter"

Same command as 1d, with the density contrast of silica instead of polystyrene:

```bash
python -m stability.cli check --duration-min 1 --objective 40x-WI --emission-nm 520 --axial-drift-nm-per-min 5 --pfs-on --pfs-in-range --particle-radius-um 0.25 --delta-density 1000 --viscosity 1.0016e-3 --sealed
```

```
feasibility: INFEASIBLE
      0.05  stability.sedimentation

    [WARN] stability.sedimentation
           The population settles 8.2 um over 1 min against a 0.44 um depth of
           field (18x). What is in the focal plane at the end is not the
           population that was there at the start, so any ensemble average mixes
           two different samples.
```

**Point to make**: the failure mode is not "blurry images." It is that your
ensemble average silently averages two different samples. Nothing in the movie
would look wrong. Margin 0.05 versus 1.09 is the entire difference between
silica and polystyrene, and it is one line of input.

### 2c. Bonus — the objective question the advisor will ask

They will say: *"but I've trapped PS in water with the 100x oil, it works fine."*
They are right, and the tool now agrees — with the bill attached:

```bash
python -m trapping.cli check --dial 100 --max-power-w 0.01634 --n-traps 1 --radius-um 2.5 --n-bead 1.57 --n-medium 1.333 --na 1.45 --viscosity-pa-s 1.0016e-3 --detector-fps 240
```

```
NA:       design 1.45  ->  effective 1.333 (clipped by TIR in n=1.333)
assumed:  ... spherical aberration at the NA 1.45 -> 1.333 index step
          (not modelled; computed stiffness is an upper bound)

    [info] effective_na.clipped_by_tir
           Design NA 1.45 is clipped to an effective 1.333 by total internal
           reflection at the coverslip/sample interface. The trap still works --
           but every number in this verdict now carries three limits: (1)
           stiffness is an UPPER BOUND ... (2) spherical aberration ... is NOT
           modelled here ... (3) that index step also pins how deep you may work
           ... adds a Faxen wall-drag bias that this lens does not correct.
```

**Point to make**: it traps, and 60x-Oil and 100x-Oil are *identical* for
trapping because both clip to the same effective NA — all three objectives agree
within 3%. So the objective is an imaging choice, not a trapping one. What oil
costs is quantitative: G17 pins you within ~10 µm of the glass, where a 5 µm
bead carries a **+16.4% Faxén wall-drag bias** (+39.1% at 5 µm height) that this
lens does not correct.
The verdict still `PASS`es, and still refuses to `advance`. Recorded in
[`kb/expertise/oil-objective-trapping-in-water.md`](../../kb/expertise/oil-objective-trapping-in-water.md),
sourced to the observation itself.

---

# Demo 3 — It refuses to make things up, and names the missing fact

**Say**: "This is the part I actually care about. Four different refusals, four
different missing facts, each one naming what to go measure."

### 3a. The two-colour optical plan

```bash
python -m optics.cli check config/channels/demo-probe-tracer-2color.yaml
```

```
overall: BLOCKED - insufficient information
optical lens verdict: HOLD  (assumed inputs present - measure, do not infer)

    [FAIL] missing.detector
           Detector 'Kinetix' is missing pixel pitch, read noise or full well.
           Sampling, SNR and saturation are uncomputable.
        -> Add 'Kinetix' to data/detectors.yaml from its datasheet. Do not
           substitute a similar camera.
```

The Kinetix datasheet has **no full-well figure at all**. The obvious move is to
borrow the Prime95B's 80,000 e⁻ — same vendor, same sensor family. The gate says
*do not*.

### 3b. The illumination dose

```bash
python -m photo.cli check --dye ATTO647N --wavelength-nm 640 --exposure-ms 1.0 --n-frames 14400 --frame-interval-ms 4.167 --area-um2 39200 --trap-on
```

```
ATTO647N @ 640 nm  irradiance unknown   ->  BLOCKED

    [FAIL] missing.power_at_sample
           ... The metadata's percent setting is not a physical quantity and does
           not transfer between instruments.
        -> Measure sample-plane power with a power meter ... This is the
           project's top blocker -- it cannot be computed, only measured.

    [FAIL] missing.bleach_photons
           ... docs/04 §6: the qualitative `photostability` grade is explicitly
           not a substitute.
```

**Point to make**: 2,343 archived acquisitions record `Spectra-Red_Level: 10`.
A percent is not a physical quantity. This is the single measurement that unlocks
the most — 30 minutes with a power meter — and no amount of code substitutes for
it.

### 3c. A bead outside the model's regime

Ask for the same trap on a 1 µm bead instead of 5 µm:

```bash
python -m trapping.cli check --dial 100 --max-power-w 0.01634 --n-traps 1 --radius-um 0.5 --n-bead 1.57 --n-medium 1.333 --na 1.25 --viscosity-pa-s 1.0016e-3
```

```
->  BLOCKED
    [FAIL] missing.regime
           Mie size parameter x=3.94 puts this bead in the 'intermediate'
           regime, not ray optics -- a GOA force number here would be fiction.
        -> Use Rayleigh scattering theory (x<0.3) or full Lorenz-Mie theory /
           GLMT (x~1) instead; trapping.goa only covers x>10.
```

**Point to make**: the ray-optics model would have happily returned a number.
It is the *only* place a wrong answer would have been invisible — the number
would look like all the others. This is why the probe has to be ≥ 2.55 µm: that
is where `x = 2πnr/λ` crosses 10 at 1064 nm in water.

### 3d. And it knows the committee never convened

```bash
python -m validity.cli check --quantity velocity --target-error 0.05 --n-particles 200 --n-frames 14400 --pixel-size-measured --upstream-passed trapping,sample,compute
```

```
velocity   ->  FAIL      feasibility: INFEASIBLE
      0.00  validity.committee_coverage

    [FAIL] validity.committee_coverage
           The committee did not reach a reviewable state — never ran: optics,
           detection, photo. A verdict on whether the intended quantity survives
           cannot be given while a standing lens is missing or had no basis to
           decide.
```

It also refuses to be fooled by the command line itself:

> ! upstream verdicts for trapping, sample, compute were DECLARED on the command
> line, not computed. G23's bias ledger has nothing to review because a declared
> verdict carries no findings — so a PASS here does not mean the biases were
> checked.

**Closing line**: "Three of eight lenses are blocked, and the system says so out
loud rather than giving me a number I would have believed. The blockers are
facts, not code — a power meter reading, a datasheet value, and two filter
passbands."

---

## Appendix — if the advisor pushes on a number

| Question | Answer | Where |
|---|---|---|
| Why 5 µm and not 1 µm? | ray optics needs `x > 10` → diameter ≥ 2.55 µm at 1064 nm in water | [`trapping/goa.py`](../../trapping/goa.py) `ray_optics_regime` |
| Why 16 mW? | κ = 5.66 pN/µm holds the 1.42 pN drag at 30 µm/s to a 250 nm lag | Demo 1b |
| Why 240 fps? | G14 `f_s ≥ 10 f_c`, `f_c = 19.1 Hz` → 191 fps required | Demo 1c, margin 1.26 |
| Why 1.0 ms exposure? | 24% duty → 8.0% MSD bias, under the 10% Savin–Doyle limit | [docs/04 §5](../04-decision-engine.md) |
| Why polystyrene? | silica sediments 8.2 µm/min vs a 0.44 µm depth of field | Demo 2b |
| Why is the probe red and tracers green? | ATTO647N leaks 0.0% into green and absorbs 0.00 at 488; dim population gets the QE 0.95 channel | [`config/channels/demo-probe-tracer-2color.yaml`](../../config/channels/demo-probe-tracer-2color.yaml) |
| Can the disk keep up? | no — 3195 MB/s vs a measured 144.8 MB/s budget, 22× over; RAM burst gives ~63 s | [kb/decisions/2026-08-12](../../kb/decisions/2026-08-12-ram-buffer-detour-for-disk-bandwidth.md) |

**Known rough edge, if asked**: `trapping.cli check` needs `--viscosity-pa-s`
passed explicitly whenever `--n-medium` is not exactly `1.33`, because the water
viscosity table is only keyed to water. Using `1.333` (the project's standing
default for an aqueous medium) trips this. It is a refusal, not a crash, and
arguably the table should accept 1.333 — a real small inconsistency worth fixing.
