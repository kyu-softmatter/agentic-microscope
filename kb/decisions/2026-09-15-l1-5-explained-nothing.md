---
id: 2026-09-15-l1-5-explained-nothing
question: "L1.5 exists to explain L1.4's low collection. Why was it silent on the one channel that fails it?"
date: 2026-09-15
status: current
corrects: [2026-09-15-l1-3-read-a-notch-as-an-overlap]
---

# 2026-09-15 · L1.5 owned the explanation and gave none

L1.5's own docstring states the division of labour: *"`collection` owns the
grade; this owns the explanation."* On `active-microrheology`'s red arm — the
only channel in the repository failing L1.4 `collection.low`, at m=0.871 — it
explained nothing. It reported `emission.centering`, the clean branch.

**The peak is 8 nm outside its own passband and half the light is being thrown
away.** ATTO647N emits at 669 nm; the band that collects it is **677–701**;
**49.8 %** of the QE-weighted emission falls below the band edge, and the
filters pass **15.9 %** of what the camera could see.

## Same root cause as L1.3's, one check over

```python
band = channel.emission_transmission().support(0.5)   # a HULL
clipped = bool(band and band[0] > peak)
```

`support(0.5)` runs from the bottom of the lowest band the path passes to the
top of the highest. On the red arm that hull starts at **589 nm** — the bottom
of the `MXR00724-EM` 589–623 band, which is the *green* channel's neighbour and
a band ATTO647N never reaches. So `589 > 669` was `False`, and the clipping
went unsaid.

[`2026-09-15-l1-3-read-a-notch-as-an-overlap.md`](2026-09-15-l1-3-read-a-notch-as-an-overlap.md)
named this as a latent defect the same day and **understated it**. That entry
predicted the mechanism correctly and guessed the wrong instance:

> *"On today's configs it returns the right answer by luck … But a dye peaking
> at 505 nm on this same filter set would be genuinely clipped and would go
> unreported."*

The mechanism was right. It was not latent — it was already live on the red arm
of the lab's real proposal, and on the channel whose collection verdict most
needed it. **Predicting a hole and then guessing at whether it is occupied is
worth less than looking**, which took one script.

## The fix, and why it is not L1.3's fix

`Spectrum.bands(threshold)` decomposes what `support` hulls: every contiguous
run above the threshold, in order, with `support == (bands[0][0],
bands[-1][1])`. For a single passband the two agree, which is why reading the
hull as "the band" went unnoticed in both checks.

`Channel.detection_band_nm()` then picks **the band the light actually lands
in**: of the path's bands, the one collecting the most QE-weighted dye
emission. Not the band *containing the peak* — that begs L1.5's own question,
since a clipped peak is by definition outside its band.

**L1.3 must keep its dye-weighted support and must not use this.** The two ask
different questions and the answers differ:

| | asks | so it uses |
|---|---|---|
| **L1.3** | where does the detected **light** start | the dye-weighted support — it is about the light |
| **L1.5** | where does the **filter's** passband start | the band's own edge — it is about the filter |

Weighting L1.5 would move the edge inward, so a dye peaking 0.5 nm inside its
band would read as clipped when the filter is not clipping it. And the reverse
substitution is worse: on a path with no emission filter the whole grid is
**one** band, so its edge is 300 nm and every dye would "overlap" its own
excitation — the hull bug again by a different route. That is
`demo-probe-tracer-2color`, and
`tests/test_optics.py::test_l1_3_does_not_use_the_band_edge_and_must_not` pins
it.

**So L1.3's first falsifier is not retired by this work.** That entry warned
that a dye broad enough to reach a *second* passband would make the weighted
product a hull again; `bands()` now exists, but L1.3 correctly does not use it,
so the exposure is unchanged.

## What every channel says now

Reported as a finding, with the fraction below the band edge — the actionable
half, since 1 nm past a narrow dye's peak and 8 nm past a broad one cost very
different amounts.

| config | channel | L1.5 | m | below the edge |
|---|---|---|---:|---:|
| abvigen-bangs | Red-Abvigen | `peak_clipped` | 0.491 | 46 % |
| **active-microrheology** | **Probe-ATTO647N** | **`peak_clipped`** | **0.318** | **50 %** |
| aura-widefield | Red-Abvigen | `peak_clipped` | 0.252 | 59 % |
| proposed-2color | 647 | `peak_clipped` | 0.542 | 42 % |
| abvigen · active · aura | the three green arms | `centering` | 0.40–0.65 | — |
| particle647-yoyo1 | both | `centering` | 0.78–0.83 | — |
| proposed-2color | 488 | `centering` | 0.976 | — |

**Only active-microrheology's red arm is newly reported.** The other three
`peak_clipped` rows were already firing; what they gain is the fraction.

⚠ **And that is the pattern worth taking to the operator: every far-red arm on
this bench is clipped, 42–59 %.** Four channels, three independent filter sets,
four dyes. This is not one config's mistake — it is where these emission
filters' red bands sit relative to these dyes' peaks. Nothing in this entry
says which to change; `collection` grades it and L1.5 now says why, which is
the whole of what the code is entitled to claim.

## Why

A check classified `INFO` is classified that way because another check owns the
grade — L1.5 says so in its own docstring, and the reason is sound: grading
both would double-count one weakness. But **the price of not grading is that
the finding is the entire product.** A `soft` check that reports the wrong
number still moves a margin and gets argued with; an `INFO` check that reports
the wrong branch is simply read and believed, because nothing downstream
depends on it enough to contradict it.

That is why this went five weeks and why L1.3's much louder version of the same
bug was found first: L1.3 was stopping runs.

## Falsifying condition

**The band choice is wrong if the most-collecting band is not the one the
experiment means to use.** It is chosen by collected QE-weighted emission, so a
dye whose emission is split nearly evenly between two passbands would have the
band picked by a small difference, and `band[0]` would jump between them on a
minor spectral revision. No dye on file is within 2× on two bands; a
quantum-dot or a multi-peak label would be. The signature is `band_start_nm`
moving discontinuously when nothing about the filter changed.

**And the 49.8 % is a shape assumption, not a measurement — checked, not
suspected.** It is `∫ em·QE` below the band edge with `em` area-normalized, so
it inherits whatever `data/fluorophores.yaml` carries. ATTO647N there is
`em_peak_nm: 669`, `em_fwhm_nm: 45`, **`verified: false`** and no `curves:`
entry, so `Fluorophore.from_spec` builds the emission from
`Spectrum.fluorophore_band(669, 45)` — a reconstructed asymmetric band, not a
vendor curve and not a measurement on this bench.

What that does and does not undermine:

- **The band edge is hard.** `band_start_nm = 677` comes from
  `MXR00724-EM`'s transmission, not from the dye.
- **The sign is hard.** 669 < 677 holds for any plausible emission shape; the
  peak is outside the passband.
- **The fraction is soft.** 49.8 % is what a 45 nm-FWHM reconstruction puts
  below 677 nm. A real ATTO647N curve is red-tailed, so the true figure is
  plausibly *lower* — which would make the report an overstatement in the
  direction that alarms. **Read it as "about half", and measure the curve
  before quoting it to a supplier.**

**`evidence` is `assumed` on both arms of this channel regardless**, so no
verdict here can advance on it either way.
