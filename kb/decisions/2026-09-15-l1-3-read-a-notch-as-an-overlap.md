---
id: 2026-09-15-l1-3-read-a-notch-as-an-overlap
question: "L1.3 failed the lab's only real proposal at m=0.00 on both channels. Was it right?"
date: 2026-09-15
status: current
corrected_by: [2026-09-15-l1-5-explained-nothing]
corrects: [2026-09-15-the-plan-emitter, 2026-09-15-stage-2-the-judgment-seam]
---

# 2026-09-15 · L1.3 read a notch as an overlap

**No, it was not right.** `config/briefs/active-microrheology.yaml` failed
`spectral.overlap` at m=0.00 on both channels — a `hard` gate, so §2 precedence
level 1 stopped the run in tier 1 and the other eight lenses never ran. The
reported Stokes headrooms were **−66 nm** and **−54 nm**.

The excitation is attenuated on that path by **1.9 × 10⁻¹¹**. There is no
overlap. What the check measured was the *support hull of a multiband emission
filter*.

## The measurement

`Channel.stokes_headroom_nm` is `em[0] - ex[1]`, and `Spectrum.support(0.5)`
returns first-index-above-threshold → last-index-above-threshold: **an outer
hull that swallows any notch between bands.**

`MXR00724-EM` is a **penta-band** emitter, matched to the
`Di01-T405/488/568/647` quad dichroic:

| | |
|---|---|
| half-peak bands | 420–460 · **510–531** · 589–623 · 677–711 · 768–849 |
| transmission at 488 nm | **5 × 10⁻⁶** — the line sits in a notch |

On the green channel the `DM A561LP` reflect side cuts above 561 nm, so the
path product keeps two bands: **420–450** and **510–529**. DragonGreen
(em ≈ 520 nm) emits into 510–529.

`support(0.5)` returns the hull `(420, 529)`. So `em[0]` was **420** — the
bottom of a band on the *far side* of the 488 nm excitation — and

```
headroom = em[0] − ex[1] = 420 − 486 = −66 nm
```

The whole path transmits 1.9 × 10⁻¹¹ at 488 nm. The bands are separated by a
notch, and the check called that an overlap.

## This is the same defect the same docstring already describes

`stokes_headroom_nm`'s own text, from the 2026-08-10 repair
([`2026-08-10-labeling-and-laser-recommend.md`](2026-08-10-labeling-and-laser-recommend.md)
item 2):

> a dichroic shared by several laser lines (one multiband element reflecting at
> all of them) has a passive support spanning every line at once. Without the
> source line to pick out which reflection notch is actually lit, the
> "excitation band" looks hundreds of nm wide and falsely overlaps every dye's
> emission.

That was diagnosed, written down, and fixed — **on the excitation side only**,
by multiplying in the source spectrum. The emission side has the identical
defect and got no weighting, so nothing picked out which passband the light
actually arrives in. Five weeks.

**The fix is the symmetric one.** The dye's own emission spectrum is to the
emission side what the source line is to the excitation side:

```python
detected = self.emission_transmission() * self.dye.emission
em = detected.support(0.5)
```

## What it changes, measured on every config in the repository

| config | channel | before | after | L1.2 `blocking` |
|---|---|---:|---:|---|
| active-microrheology | Tracer-DragonGreen | −66 | **+25** | 2.14, passes |
| active-microrheology | Probe-ATTO647N | −54 | **+34** | 2.15, passes |
| demo-probe-tracer | Tracer-ATTO488 | −188 | +19 | **0.023, FAILS** |
| demo-probe-tracer | Probe-ATTO647N | −79 | +8 | **0.027, FAILS** |
| legacy-observed | 647-Cy5 | −355 | −8 | BLOCKED, no filter spec |
| abvigen · aura · particle647 · proposed | 8 channels | 12–29 | 13–29 | unchanged |

Two things in that table matter more than the released rows.

**The eight channels with single-band emitters move by 0–1 nm.** Where the
emitter has one passband, the hull and the dye-weighted band are the same band.
That is the signature of a correct repair of this kind: it is a no-op wherever
the old reading was already right.

**`demo-probe-tracer-2color` still FAILS**, and it is the config L1.3 was
written from — the 2026-09-05 session that went INFEASIBLE at −188 nm
([`2026-09-10-lens-7-measured-stiffness-and-numbering.md`](2026-09-10-lens-7-measured-stiffness-and-numbering.md)).
Its emission path transmits **0.77** at its own excitation line. That is a real
leak, and **L1.2 `excitation_blocking_od` catches it at m=0.023** — the check
that owns attenuation, doing so independently.

## The split this preserves, and why it is the point

L1.3's docstring already draws the line:

> L1.2 is the filter failing to attenuate, this is the bands overlapping in the
> first place. L1.2's action ("add a blocking filter") cannot fix it, which is
> why it needs its own number rather than a branch of L1.2.

The line is right; the implementation did not hold it. **L1.3 measures
separation, L1.2 measures attenuation**, and after this fix each measures only
its own. A path that genuinely passes its excitation now reports a clean
headroom and still fails — which is the property
`tests/test_optics.py::test_a_path_that_really_passes_its_excitation_is_still_caught`
exists to pin, because a "fix" that conflated the two would let a real leak
through and look like a success.

## What this corrects in the record

Two entries written earlier today state the old verdict as a fact. Both carry
`corrected_by` links to this one:

- [`2026-09-15-the-plan-emitter.md`](2026-09-15-the-plan-emitter.md) — *"Both
  channels of `active-microrheology` FAIL L1.3 `spectral.overlap` at m=0.00.
  Only one of those two failures was visible before today."* The **second
  sentence stands**: the per-channel change is what made the red arm's verdict
  visible at all, and it is how both were seen to be wrong rather than one.
- [`2026-09-15-stage-2-the-judgment-seam.md`](2026-09-15-stage-2-the-judgment-seam.md)
  — *"The only real brief in the repository never reaches stage 2."* It does
  now. Lens 1 returns `PASS_WITH_CHANGES`, the run reaches tiers 2 and 3, and
  `designer.cli packets` writes real packets from it.

## What the real proposal says now

Lens 1, both arms, after the fix:

| channel | status | bottleneck | m |
|---|---|---|---|
| Tracer-DragonGreen | `PASS_WITH_CHANGES` · TIGHT | `collection` (L1.4) | 1.41 |
| Probe-ATTO647N | `PASS_WITH_CHANGES` · HARD | `collection.low` (L1.4) | **0.871** |

`collection` is `soft`, so it does not stop tier 1 — the run now goes the whole
way and returns eight more verdicts, none of which had ever been computed for
this proposal. **None of them is an endorsement**: lens 2 is
`not_constructible` for want of an exposure, lenses 3 · 4 · 5 · 9 BLOCK by
name, and lens 6 returns FAIL. That list is the real state of the brief, and
L1.3 had been standing in front of it.

⚠ And `advances` is `False` on both arms regardless: evidence is `assumed`.

## A defect of the same root, not fixed here — and NOT latent

⚠ **Corrected within the hour**
([`2026-09-15-l1-5-explained-nothing.md`](2026-09-15-l1-5-explained-nothing.md)).
The mechanism below is right and "latent" is wrong: it was already live on the
red arm of this same proposal, where ATTO647N peaks at 669 nm and the band
collecting its light starts at **677**. The hull started at 589 — the *green*
channel's neighbouring band — so `589 > 669` was False and the clipping went
unreported on the one channel failing L1.4. **The guess about which dye would
be affected was wrong in the direction of comfort**, and checking took one
script. The paragraph stands as written, as the record of that.

### As written

`check_emission_centering` (L1.5, `optics/checks.py`) takes the same hull:

```python
band = channel.emission_transmission().support(0.5)
clipped = bool(band and band[0] > peak)
```

On today's configs it returns the right answer by luck — the green channel's
hull starts at 420, below DragonGreen's 520 peak, so `clipped` is `False`,
which is correct. **But a dye peaking at 505 nm on this same filter set would
be genuinely clipped** (the band in use is 510–529) and would go unreported,
because 420 < 505.

Not fixed here, and not by the same edit: L1.5 asks *"does the band in use
start past the peak"*, so dye-weighting it is circular — the weighted band is
where the dye emits by construction. It needs the band **containing or nearest
the peak**, which is a different computation. Left as a named hole rather than
bundled into a repair whose evidence does not cover it.

## Falsifying condition

**Two, and the first is the one to watch.**

The dye-weighted band is `support(0.5)` of `path × dye_emission`, so a dye whose
emission spectrum is itself broad enough to reach into a *second* passband of
the emitter would produce a hull again, and the headroom would be measured to
the wrong band's edge once more. None of the seven dyes on file does this; a
long-tailed or multi-peak emitter would. The repair then is a band-finder, the
same one L1.5 needs, and the two should be fixed together.

**And the split fails if a path is found that separates cleanly and leaks
anyway** — L1.3 clean, L1.2 clean, excitation still reaching the detector.
That would mean the two mechanisms do not span the failure and a third is
missing. `blocking` is graded at 5 OD
([`2026-09-09-blocking-threshold-fixed-at-5-od.md`](2026-09-09-blocking-threshold-fixed-at-5-od.md)),
so the candidate shape is a path at 5.5 OD that is nonetheless swamped by a
bright probe — which is a threshold question, not a missing check.
