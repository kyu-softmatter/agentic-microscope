# Measured spectral curves

If a file is here, **it is used unconditionally** in place of the parametric
approximation.

## Why this matters

A parametric approximation (`center_nm` + `fwhm_nm`) gets the peak position
right but **gets the wings wrong.** And the two central verdicts of the optics
gate — excitation blocking (OD) and inter-channel crosstalk — are decided
entirely in the wings.

If even one approximated spectrum is mixed in, the gate:

- returns `evidence: assumed` → `advances: NO` (the verdict cannot pass the
  proposal)
- raises the blocking requirement from 5 OD to **7 OD**
- demotes a filter-removal proposal from `remove` to `candidate`

In other words, **no optical configuration is confirmed until the measured
curves are in.**

## Format

Two-column text/CSV. Any delimiter — space, tab, or comma.

```
# wavelength_nm   value
400               0.0012
401               0.0013
...
```

- Comments: lines starting with `#` `;` `//` `%`
- If a value exceeds 1.5 it is **treated as a percentage and divided by 100**
  (auto-detected)
- Resampled onto a 300–1100 nm grid (1 nm). Out-of-range is filled with 0

## Where to get them

| Target | Source |
|---|---|
| Filters, dichroics | ASCII download from the Semrock/IDEX or Chroma product page |
| Fluorescent dyes | [FPbase](https://www.fpbase.org) — CSV export |
| Camera QE | Manufacturer datasheet (digitize if only a graph is available) |
| Light source lines | Lumencor datasheet |

## Wiring them up

```yaml
# data/filters.yaml
"FF01-692/40":
  kind: bandpass
  curve: ff01-692-40.txt        # ← path relative to data/spectra/

# data/fluorophores.yaml
ATTO647N:
  curves:
    absorption: atto647n_abs.csv
    emission:   atto647n_em.csv

# data/detectors.yaml
Prime95B:
  qe_curve: prime95b_qe.txt      # or an inline {wavelength: QE} mapping
```

## File naming rule

Use the part number as-is. Lowercase, with `/` replaced by `-`.
`FF01-692/40` → `ff01-692-40.txt`

## Current status

2026-08-10: measured PBS curves for ATTO 488 and ATTO 550 (the identity of the
requested "ATTO 555" was never confirmed — see below) were obtained from the
official ATTO-TEC/Leica downloads and added (`atto488_abs/em.txt`,
`atto550_abs/em.txt`). Measured PhotochemCAD curves for FITC and Acridine Orange
were obtained (`fitc_*.txt`, `acridineorange_*.txt`) but **deliberately not wired
into `curves:` in `data/fluorophores.yaml`, because the solvent/binding state
differs from the actual conditions of use** — see the comment at the top of each
file and the corresponding dye note in the yaml.

For the remaining dyes (Cy5, Alexa Fluor 647/488/555, ATTO 647N, YOYO-1,
SYTO 61, Dragon Green) this round of searching did not turn up genuine
(wavelength, intensity) measured curves — FPbase blocks automated fetching at
Cloudflare, the AAT Bioquest viewer only accepts email requests, the Thermo
SpectraViewer is a JS app so a headless fetch times out, and
fluorophores.tugraz.at still serves its list page (peak values) but returns 500
on the detail pages. If they have to be downloaded by hand in a browser, see the
URL recorded in each dye's `note:`. Until then it runs on parametric
approximations, and the final crosstalk/blocking verdict remains confidence low.
That is intended behavior.
