---
id: sample-medium-refractive-index
question: "What refractive index should be assumed for the sample medium when the
  experiment does not state one"
source: user_statement
expert: KH
date: 2026-08-12
updated: 2026-08-19
confidence: high
evidence: confirmed_default
scope: "Default for all systems. Applies to the sample medium only, not to the
  immersion medium — see [[immersion-media-in-use]]"
applies_to_systems: [current, current-laser, current-spectra, current-aura]
review_after: 2027-08-12
supersedes: null
---

## Verdict
**`n_medium = 1.333`** (pure water, 20 °C, 589 nm) when the experiment does not
specify otherwise. KH confirmed 2026-08-12 that samples are generally
water-based, and **settled the value on 2026-08-19**: 1.333 is what lens 4 uses,
and falling back to it is no longer treated as an assumption.

**What changed on 2026-08-19, and what did not.** Before, any gate consuming this
value had to report `evidence: assumed`, which meant lens 4 could not advance on
an ordinary aqueous sample. `sample/gate.py::_assumed_inputs` no longer lists it.
This is a **confirmed default, not a refractometer reading** — the distinction
still matters, and what makes it defensible is that 1.333 is a literature
constant for water rather than a lab-specific parameter. Contrast
`power_at_sample_mw`, which is instrument-specific and therefore still BLOCKs
lens 5: "we know what water is" and "we never measured our own laser" are not
the same kind of gap.

A real dilute aqueous buffer (PBS and similar) runs slightly higher, roughly
1.334-1.337 depending on salt load, so 1.333 remains a lower bound on an aqueous
medium rather than an exact value. That spread sits **inside** `sample`'s
`LIMITS["matched_ri_tolerance"] = 0.005`, whose code comment says it exists to
cover "ordinary buffer-vs-water differences" — so confirming the water value does
not quietly weaken G17's `index-matched` verdict for the 40x WI, the one case
where a 0.003 error would be the entire signal. That is what makes this safe; if
the tolerance is ever tightened below ~0.005, this entry has to be revisited.

## The consequence this unblocks: oil objectives are badly mismatched

With the sample medium at 1.333 and the immersion media now known
([[immersion-media-in-use]]), the RI mismatch per objective is:

| Objective | Immersion n | Sample n | Mismatch | First-order axial scaling |
|---|---|---|---|---|
| 40x WI (NA 1.25) | 1.333 | 1.333 | **0.000** | none — matched |
| 60x Oil (NA 1.42) | 1.518 | 1.333 | **0.185** | 0.878 |
| 100x Oil (NA 1.45) | 1.518 | 1.333 | **0.185** | 0.878 |

For the oil objectives the paraxial focal-shift ratio is
`n_sample / n_immersion = 1.333/1.518 = 0.878`, i.e. a nominal 10 µm of z travel
corresponds to about **8.78 µm actual depth — a 12.2% axial scaling error** if
uncorrected. Spherical aberration from the same mismatch grows in proportion to
depth (`docs/06-pitfalls.md` D5).

**So for aqueous samples the 40x WI is the RI-matched choice and the oil
objectives are not**, despite their higher NA. That trade — NA versus RI match — is
precisely a Lens 4 verdict, and it opposes what Lens 1 would say from collection
efficiency alone (the 100x oil collects 0.352 vs the 40x WI's 0.326). Surfacing
that conflict is the committee's purpose.

> The 0.878 ratio is a **paraxial first-order** estimate. At NA 1.42-1.45 the
> high-angle treatment differs and the effective focal shift is depth- and
> NA-dependent. Do not report a corrected depth from this number alone; use it to
> decide whether the correction matters, then compute properly. Per
> `docs/05-consensus-gate.md`, an approximation must not be passed off as an answer.

## Where this default must NOT be applied

These are the "unusual cases" — the default is wrong for all of them, and a gate
should refuse rather than silently substitute 1.333:

- **ATPS (dextran/PEG)** — the project's main sample system. The two phases have
  *different* refractive indices, both above water, and `docs/05` Lens 4 calls this
  out explicitly. One scalar cannot describe it; each phase needs its own value, and
  the interface itself refracts
- **Glycerol or sucrose** in the medium (density matching, viscosity tuning) — these
  raise n substantially, toward 1.47 for high glycerol
- **High salt / high polymer concentration** generally
- **Non-aqueous media** — liquid crystal 5CB is birefringent (n_o ~1.53,
  n_e ~1.71), so a single isotropic n is meaningless

For these the gate should return `BLOCKED` with an action naming the measurement,
not fall back to the default.

## Temperature and wavelength

- Water dn/dT ~ -1e-4 per °C, so a few degrees of room drift moves n by ~1e-4 —
  an order of magnitude less sensitive than the immersion oil, and negligible
  against the 0.185 mismatch above
- Water dispersion (vd ~55.7) gives `nF - nC ~ 0.0060`, about half the oil's
  0.0126. Across 405-647 nm the mismatch itself is therefore mildly
  wavelength-dependent, but it stays near 0.185 to within a few parts in a thousand

## Falsification conditions
1. A refractometer reading of the actual buffer differs from 1.333 by more than
   0.005, which would matter for the matched 40x WI case (where the mismatch is
   nominally zero) far more than for the oil objectives
2. The sample turns out to contain glycerol, sucrose, or high polymer as standard
   practice, making the water default wrong by default rather than by exception
3. An ATPS experiment is run through a Lens 4 gate and the gate uses this default
   instead of blocking — that is an implementation bug, not a change in the fact

## Related
[[immersion-media-in-use]] · kb/systems/current.md > objectives ·
docs/06-pitfalls.md D5 · docs/05-consensus-gate.md > Lens 4 ·
.claude/agents/sample-optics.md
