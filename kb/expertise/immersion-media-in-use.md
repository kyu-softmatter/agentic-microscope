---
id: immersion-media-in-use
question: "Which immersion media are actually in use on the current nosepiece, and
  what refractive index should the optics code use for each"
source: user_statement + vendor_datasheet
expert: KH
date: 2026-08-12
confidence: high
scope: "kb/systems/current.md > objectives (6-position nosepiece) — 40x WI, 60x Oil,
  100x Oil"
applies_to_systems: [current, current-laser, current-spectra, current-aura]
review_after: 2027-08-12
supersedes: null
---

## Verdict
Two immersion media are in use, and both already match what the code assumes:

| Objective | NA | Immersion | Product | n (nd, 589nm) |
|---|---|---|---|---|
| 40x (pos 3) | 1.25 | **water** | — | 1.333 (`IMMERSION_N`) |
| 60x Oil (pos 4) | 1.42 | **oil** | Nikon Type F Non-Fluorescing | 1.518 |
| 100x Oil (pos 5) | 1.45 | **oil** | Nikon Type F Non-Fluorescing | 1.518 |

`optics/components.py` `IMMERSION_N["oil"] = 1.518` is therefore **not a generic
placeholder** — it is the correct nd for the oil this lab actually uses. Same for
`water = 1.333`. Provenance for the oil row is upgraded from assumed to
vendor-specified.

Nikon Type F spec (Edmund Optics #75-384): nd = 1.518, Abbe vd = 41, spec
temperature 23 °C, non-fluorescing (chosen for low autofluorescence), PCB-free.

## Why this matters beyond the single number

**1. nd is specified at 589nm, but this lab images at 405/488/561/647nm.**
Abbe vd = 41 gives an F–C dispersion of

    nF - nC = (nd - 1)/vd = 0.518/41 = 0.0126

so the oil's refractive index varies by ~0.013 across 486-656nm, and by more than
that at 405nm (which lies outside the F–C interval). The code currently uses a
single scalar 1.518 for every wavelength. Consequences:

- `Objective.collection_efficiency()` uses `n_medium`. For the 100x at NA 1.45,
  taking n = 1.5054 instead of 1.518 moves collection efficiency 0.3520 -> 0.3656
  (+3.9% relative) — small, but it is a systematic term in a photon budget that
  is otherwise carefully computed. Verified by direct computation, not estimated
- The RI-mismatch / focal-shift gate planned for Lens 4 is a *difference* of
  refractive indices, so a 0.013 error there is proportionally much larger

**2. NA <= n_immersion is a hard physical limit, and nothing checks it.**
`optics/components.py:301` computes `ratio = min(self.na / self.n_medium, 1.0)`.
The `min` **silently clamps** a physically impossible configuration instead of
flagging it. Present margins are real but not large:

- 100x NA 1.45 in oil: 1.45 < 1.518, margin 0.068 (and shrinking with wavelength,
  since n falls as lambda rises)
- 40x NA 1.25 in water: 1.25 < 1.333, margin 0.083

A dry/water objective mistakenly recorded as its oil variant, or an oil entry with
the wrong n, would pass silently with clamped output rather than BLOCKED. This is a
candidate hard gate for Lens 4.

**3. Temperature.** The oil is specified at 23 °C. Immersion oil dn/dT is on the
order of -3e-4 to -4e-4 per °C, so a few degrees of room-temperature drift shifts n
by ~1e-3 — comparable to the dispersion above. Room temperature is not recorded
anywhere. Relevant to Lens 4 and to Lens 8 (mechanical & environmental).

## The sample medium is a separate value
This entry covers the **immersion** refractive index only. The **sample medium**
refractive index now has a recorded default of 1.333 (assumed, not measured) —
see [[sample-medium-refractive-index]]. Combining the two gives a 0.185 mismatch on
both oil objectives and zero on the 40x WI, which is the substance of
`docs/06-pitfalls.md` D5. ATPS remains excluded from that default: its two phases
have different RI, so one number will not do.

## Falsification conditions
1. The lab switches oil type (Type N nd = 1.515 vs Type F nd = 1.518 — the two are
   sold side by side and are easy to confuse); re-check `IMMERSION_N`
2. The 40x is used dry or with oil rather than water — its NA 1.25 is only
   achievable with water, so this would silently clamp per the gap above
3. A wavelength-dependent RI model replaces the scalar, at which point the
   `IMMERSION_N` dict is no longer the right shape

## Related
[[sample-medium-refractive-index]] (not yet recorded) ·
kb/systems/current.md > objectives · docs/06-pitfalls.md D5 ·
docs/05-consensus-gate.md > Lens 4 · optics/components.py `IMMERSION_N`
