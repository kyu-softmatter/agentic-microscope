---
id: lifetime-ns-tritc
quantity: "data/fluorophores.yaml > TRITC > lifetime_ns"
question: "What fluorescence lifetime should be assumed for TRITC so that G20
  can say whether emission is still linear in power, and under what conditions
  was the published value obtained"
source: literature
citation: "Nanguneri S, Flottmann B, Herrmannsdorfer F, Kuner T, Heilemann M.
  Single-molecule super-resolution imaging by tryptophan-quenching-induced
  photoswitching of phalloidin-fluorophore conjugates. Microsc Res Tech
  77(7):510-516, 2014. -- Corroborated in a different solvent by: Brismar H,
  Trepte O, Ulfhake B. Spectra and fluorescence lifetimes of lissamine
  rhodamine, tetramethylrhodamine isothiocyanate, Texas Red, and cyanine 3.18
  fluorophores. J Histochem Cytochem 43(7):699-707, 1995."
doi: "10.1002/jemt.22349"
doi_corroborating: "10.1177/43.7.7608524"
filed_by: <initials>
date: 2026-09-16
confidence: low
evidence: assumed
gate: G20
scope: "TRITC excited in its 547 nm absorption band, on this instrument's
  imaging paths and at their measured powers. NOT for a diffraction-limited
  focus: the value's headroom under G20 is large at widefield irradiance and
  shrinks toward the tweezers regime (see What it supplies). Not for the ATPS
  phases or a sucrose-loaded buffer until the medium is on record --
  [[sample-medium-refractive-index]]."
applies_to_systems: [current-spectra, current-laser]
measured_on: "**Filed value (Nanguneri 2014):** free TRITC diluted in **PBS**
  to 1 uM, lifetime spectrometer (PicoQuant FluoTime 100 Compact), pulsed
  (5 MHz) laser diode at 575 nm, lifetimes from the manufacturer's software.
  Optical density kept below 0.05 `to guarantee linearity in the absorption and
  emission processes`. Temperature at the sample: not stated.
  **Corroborating value (Brismar 1995):** free TRITC in **ethanol** (that
  paper's other three dyes in distilled water), confocal laser scanning
  microscope, TCSPC, pulsed dye laser at 572 nm, x10 NA 0.30, cooled (-20 C)
  PMT, 0.2 mm glass capillary; mean power at the specimen below 0.5 mW
  unattenuated and typically ~10 uW, which that paper states is `well below
  those reported to cause saturation of the fluorophores`. **Both are
  unsaturated-regime lifetimes, which is the regime G20's linear assumption
  needs.**"
review_after: 2027-09-16
supersedes: null
superseded_by_measurement: null
---

> **`filed_by` is unfilled deliberately.** It attests that a person checked the
> citation against the paper, and the draft this came from was produced by a
> tool that cannot give that signature. Everything else below is quoted from
> the two papers, from `data/*.yaml`, or from a run of this repository's own
> `photo` gate.
>
> **The `## What it supplies` output needs the `photo/cli.py` fix** in the pull
> request this one depends on. Without it `python -m photo.cli` raises
> `TypeError` on every invocation, so a reviewer cannot reproduce the
> before/after below.

## Verdict

**2.2 ns**, free TRITC in **PBS** (Nanguneri 2014). *"For the TRITC
fluorophore, we measured a fluorescence lifetime of 2.2 ns for the free
fluorophore, 1.7 ns in the presence of 30 mM tryptophan, and 2.3 ns for the
dye-phalloidin conjugate."* Reported to two significant figures with no
uncertainty stated.

**Two independent papers, two instruments, two solvents**, which is the
condition `confidence:` is keyed to here:

| Source | Form | Solvent | tau |
|---|---|---|---|
| **Nanguneri 2014** | free dye | **PBS** | **2.2 ns** |
| Nanguneri 2014 | phalloidin conjugate | PBS | 2.3 ns |
| Nanguneri 2014 | free dye + 30 mM tryptophan | PBS | 1.7 ns |
| Brismar 1995 | free dye | **ethanol** | 1.58 ns (SD 10 ps) |
| Brismar 1995 | IgG conjugate | not restated | 3.32 ns + 1.4 ns |

**The PBS value is filed because this instrument's samples are aqueous.** The
1.58 ns is the same quantity in ethanol and is kept as the independent
cross-check: two techniques -- a CSLM/TCSPC and a PicoQuant lifetime
spectrometer -- at 572 and 575 nm, landing 1.4x apart across a solvent change
that would be expected to move it. `confidence: low` stands rather than rising:
they agree in magnitude, not to a figure.

**The free-dye form is filed, not a conjugate**, because `TRITC` in this
registry is not an immunoconjugate: `data/particles.yaml` records it as an
explicit **stand-in** for a rhodamine/TRITC-class bead dye whose vendor
excitation *and* emission specs were both measured wrong here, so
`ex_peak_nm`/`em_peak_nm` stay null and *"channels use an explicit TRITC
stand-in."*

**And the two papers disagree about what conjugation does**, which is worth more
than either number: Brismar's IgG conjugate goes *up* 1.74 ns and becomes
double-exponential, while Nanguneri's phalloidin conjugate stays flat
(2.2 -> 2.3 ns) and the paper attributes its quenching to a static
dye-tryptophan complex rather than to binding. So "conjugated" is not one
condition, and a bead matrix is a third thing again -- see Transfer conditions.

Nanguneri's decays for TRITC are single-valued as reported; the biexponential
fits in that paper are for ATTO 488 (3.0 ns / 82 %, 0.7 ns / 18 % with
tryptophan). `photo/dose.py` takes one scalar, so nothing has to be collapsed
here.

## What it supplies

- **Field:** `data/fluorophores.yaml > TRITC > lifetime_ns`, currently `null`.
  6 of 17 dyes in the registry are missing it.
- **Gate:** `G20`, saturation / triplet shelving, in `photo/checks.py`, against
  `excited_state_fraction_max: 0.1`.
- **Before this entry:** `photo/gate.py` `_missing_inputs()` emits
  `missing.lifetime` at severity `fail`. Run against the registry as it stands:

      TRITC @ 555 nm  153.0 W/cm^2  ->  BLOCKED
      feasibility: UNKNOWN   confidence: none   advances: NO
        [FAIL] missing.lifetime

  No margin, no bottleneck, no difficulty grade for any TRITC setting.
- **After**, same command with `--lifetime-ns 2.2`:

      TRITC @ 555 nm  153.0 W/cm^2  ->  PASS
      feasibility: ROUTINE   evidence: assumed   confidence: low   advances: NO
        10.00  perturbation.saturation     ##############################

  G20 computes, and `photo.dose.saturation_irradiance_w_cm2(85000, 2.2, 555)`
  becomes available too -- **which is why TRITC and not one of the other five.**
  TRITC already carries `ext_coeff_M1cm1: 85000`; `SYTO61` and `DragonGreen`
  carry no extinction coefficient, so a lifetime alone would move them from one
  missing input to another, and `DEX647`, `SA647` and `Phal647` share one
  nominal 270000 across three different conjugates.

**And the margin says which of the two rows matters, which is: neither.**
G20 crosses `f = 0.1` at `k_ex*tau = 1/9`, so the boundary irradiance is

| candidate | G20's boundary |
|---|---|
| 1.58 ns (Brismar, ethanol) | 7.75 x 10^4 W/cm^2 |
| **2.2 ns (filed)** | **5.57 x 10^4 W/cm^2** |
| 2.3 ns (phalloidin conj.) | 5.33 x 10^4 W/cm^2 |
| 3.32 ns (IgG conj.) | 3.69 x 10^4 W/cm^2 |

The measured power at the sample for the band that excites TRITC --
`Spectra > Green`, 15.3 mW at 20x, `data/light_sources.yaml` -- is **153 W/cm^2**
over a 100x100 um field, **241x below** the strictest of the four, and
1.5 x 10^4 W/cm^2 even over a 10x10 um field. So the saturation margin is
clamped at its ceiling for every candidate, and **the whole spread -- 1.58 to
3.32 ns, a factor of 2.1 -- does not reach the verdict at this instrument's
imaging powers.** It would reach it in a diffraction-limited focus, which is
the tweezers regime and not this gate's.

That is the honest size of what this entry buys: it converts a refusal into a
computed margin with two to three orders of magnitude of headroom, and it does
not claim to resolve the number to better than a factor of two. **Both are
worth stating** -- the second is why the first is safe.

## Transfer conditions

What has to hold for this number to apply here:

1. **The excited-state fraction stays far below 0.1.** It does, by the table
   above -- which is what makes conditions 2 and 3 tolerable rather than
   disqualifying. Read the other way: at a tight focus this entry stops being
   safe before it stops being available.
2. **The illumination is in the 547 nm absorption band** and the setting is one
   whose power at the sample is on record (`Spectra > Green` or
   `LUN-F-XL > 561`, at 4x / 10x / 20x). Elsewhere the irradiance is itself
   assumed and the comparison above cannot be made.
3. **The instrument class matches, unusually.** The paper's lifetimes were
   recorded on a confocal laser scanning microscope and this instrument's
   CSU-W1 is one. That narrows the transfer gap; a 1995 confocal is still not
   this confocal.

What is known **not** to hold:

1. **~~The solvent.~~ Resolved by the second paper.** This read *"free TRITC
   was dissolved in ethanol and this instrument's samples are aqueous"* while
   Brismar was the only source. Nanguneri measures the same quantity in **PBS**,
   which is the condition here, so the filed value no longer carries a solvent
   mismatch -- and the 1.58/2.2 gap is now evidence about the solvent rather
   than a gap in the entry.
2. **The environment is a third one the paper did not measure.** Its rows are
   free dye, IgG-conjugated, and in tissue; MS's `TRITC` is a stand-in for a dye
   **embedded in a polystyrene bead**. The paper's own conclusion is that
   *"changes in spectra and fluorescence lifetimes may be a useful tool to gain
   information about the chemical environment of the fluorophores"* -- the
   quantity is being proposed as an environment probe, and this is a different
   environment. There is no `TRITC in tissue` row at all; TRITC was left out of
   those tests.
3. **The registry row it will sit beside is a catalogue nominal.**
   `data/fluorophores.yaml`'s header says of every row: *"The values below are
   all catalog nominal values ... parametric band(peak+FWHM) gets the peak
   position right but the wings wrong."* So the `ext_coeff_M1cm1: 85000` this
   lifetime is multiplied by in `saturation_irradiance_w_cm2` is itself
   unverified. The product of two nominals is not better than either.
4. **`TRITC` is one name over several things.** `aliases: [TRITC555, tritc]`
   does not distinguish free dye from conjugate from bead -- and the two papers
   do not even agree on what conjugation does to the lifetime (up 1.74 ns on
   IgG; flat on phalloidin). One registry name spans values the sources measure
   as different, by different amounts, in different directions.

## Why this does not advance a verdict

`evidence: assumed`, so `advances` stays `NO` regardless of the margin
([04 §1](../../docs/04-decision-engine.md)) -- confirmed in the run above, which
reports `advances: NO` beside a margin of 10.00. This entry lets `G20` compute
instead of refuse. It does not claim anyone measured TRITC's lifetime on this
instrument, in this bead, under this illumination.

## Falsification conditions

1. **A saturation power series on this instrument, which it can actually do.**
   A direct lifetime needs time-resolved detection this setup does not have, so
   the falsifier is the quantity G20 is really about: acquire emission versus
   power on a fixed TRITC-class field and find where emission departs from
   linear. `k_ex*tau = 1` at excited-state fraction 0.5, so the departure fixes
   `tau` given the irradiance -- and the irradiance is available, because
   `data/light_sources.yaml` carries **measured** `power_at_sample_mw` for both
   usable bands. **The table above says what this run would cost:** the
   departure sits near 10^5 W/cm^2, so a widefield series will not reach it and
   the measurement needs a deliberately tight focus. On arrival: move the value
   to `kb/calibrations/`, set `superseded_by_measurement:`, and G20 can advance.
2. **A further published value that moves `k_ex*tau` across 1/9 at an
   irradiance this instrument uses.** Not a percentage: the four values already
   in hand span 2.1x and none of them changes the verdict here, so a
   disagreement has to be larger than the spread already recorded to matter.
3. **Transfer condition 1 turning out to be false** -- any setting that puts the
   sample near 10^4 W/cm^2 or above, at which point which row was filed starts
   to matter and none of them is the right environment.

## Related

- `photo/checks.py` -- G20 and `excited_state_fraction_max: 0.1`
- `photo/dose.py` -- `excited_state_fraction`, `saturation_irradiance_w_cm2`
- `photo/gate.py` -- `_missing_inputs()`, which emits `missing.lifetime` today
- `photo/cli.py` -- **broken**; see the note at the top of this entry
- `data/fluorophores.yaml` -- the field, and the catalogue-nominal header
- `data/particles.yaml` -- where `TRITC` is recorded as a stand-in, and where
  the vendor's excitation and emission specs are both disproved
- `data/light_sources.yaml` -- the measured `power_at_sample_mw` that makes
  falsification condition 1 available and sizes it
- `kb/expertise/sample-medium-refractive-index.md` -- why ATPS and sucrose are
  outside `scope`
- `kb/decisions/2026-09-09-g10-photobleaching-removed.md` -- G10 was the live
  case `kb/literature/README.md` still describes; G20 is the live case now, and
  the same commit left `photo/cli.py` broken

---

**On the second paper's other numbers.** Nanguneri 2014 also reports 939 photons
per single-molecule localization for TRITC and 822 for ATTO 488, an on/off rate
ratio of 1023 for phalloidin-TRITC, and quantum yields dropping to 27 % (TRITC)
and 48 % (ATTO 488) on conjugation. **None of those is a field
`data/fluorophores.yaml` carries**, and MS's rule for that case is explicit: *"If
no gate consumes a number from it, it is not knowledge this system can act on.
Method papers that shape a judgment belong in `kb/expertise/` as a captured
prior, with the paper cited inside."* The 27 % quantum-yield drop on conjugation
is the strongest candidate there, since `quantum_yield: 0.28` is in the registry
and is a catalogue nominal for the unconjugated dye.

It reports **no lifetime for Alexa Fluor 647**, so it does not supply
`Phal647`'s missing `lifetime_ns` -- which is what this draft's own README
guessed it was for, before the paper was read.
