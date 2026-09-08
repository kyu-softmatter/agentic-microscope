---
id: imaging-priority-hierarchy
question: "When a proposal cannot satisfy spatial resolution, image quality, time resolution and light intensity at once, which one yields"
source: expert-judgment
expert: KH
date: 2026-09-07
confidence: high        # the ranking. The `Why` is reconstructed — see §"stated vs reconstructed"
evidence: standing_practice
scope: "Setting selection on the current instrument. Stated in the context of
  single-particle tracking and optical-trap microrheology; NOT confirmed for
  morphology or intensity-profile measurements — see Falsification conditions"
applies_to_systems: [current]
review_after: 2027-09-07
supersedes: null
---

## Verdict

Four axes, ranked by how hard each is defended when a proposal cannot satisfy
them all. **Rank 1 is protected hardest; rank 4 is the free variable that moves
first.**

| Rank | Axis | Standing value on this instrument |
|:---:|---|---|
| 1 | **Spatial resolution** | `100x-Oil` (`6-Plan Apo LmbdD0.13 100x Oil`), **1×1 binning, 0.065 µm/px** at intermediate 1× |
| 2 | **Image quality** (SNR, localisation precision) | whatever the above leaves |
| 3 | **Time resolution** | **20.0 ms exposure ⇒ ~50 fps** (this camera takes the exposure as the period) |
| 4 | **Light source intensity** | Aura **GREEN ~80/1000**, found by a setup scan on the day |

The operative rule: **concede from the bottom up.** To close a shortfall, move
intensity first, then the frame period, then accept lower SNR, and only last
touch magnification, NA or binning. Every concession is reported by name.

Two boundaries on it, both stated with the ranking:

- **Intensity ranks last because it is instrumental, not because photodamage is
  cheap.** It is the axis with a *window* to move inside — bounded above by
  bleaching and light-driving, below by "the analysis cannot work". If that
  window is empty, the answer is not more light: something above has to move,
  visibly.
- **This is a tie-break among `soft` and `bias` trade-offs. It does not
  override a `hard` gate** → [`05 §2`](../../docs/05-consensus-gate.md). Rank 1
  does not buy an oil objective past G17's RI-mismatch depth, and no rank
  raises the disk's write bandwidth (G12a).

## Why — and this half is reconstructed, not stated in these words

Four records already in this repository decide three of the four adjacent
comparisons, which is why the ranking reads as a description of practice rather
than a new rule:

1. **Rank 1 over rank 2 is already a decided case, twice.**
   [`microrheology-standard-conditions`](microrheology-standard-conditions.md)
   (KH, 2026-09-07) records 1×1 binning as deliberate — *"need high resolution
   on particle to track it better"* — and states outright that unbinned is **not
   the SNR-optimal choice and should not be "corrected" to 2×2 on SNR grounds**.
   The same entry records `100x-Oil` chosen *with* the ~17.6 % Faxén drag
   inflation at ~8 µm depth stated and accepted. So spatial resolution was
   defended once against SNR and once against a known, quantified measurement
   bias.
2. **Rank 3 is where the concession has historically landed.** 20.0 ms is not a
   free parameter — every script in `analysis/matlab/` hardcodes `frame_time`,
   so the frame rate is pinned by the analysis rather than chosen against the
   other axes. And the worked example in
   [`09 §2`](../../docs/09-knowledge-capture.md) reads a 647 exposure pinned at
   a 500 ms ceiling (legacy system, 764 acquisitions) as insufficient light, whose
   cost is stated as *"time resolution is sacrificed"* — the concession went to
   the frame rate, not to the pixel.
3. **Rank 4 is the axis that is measured on the day.** README to-do item 9 (KH,
   2026-09-05) puts intensity last in the *selection procedure* and gets it from
   a setup scan kept as a LUT **bracketed at both ends** — not so intense that
   it bleaches, not so dim that the analysis cannot work. An axis whose
   acceptable range is established per sample is the one with room to move,
   which is what makes it the lever.
4. **The ranking has to be separate from the procedure.** Item 9's step 1 is
   *frame rate first, from the purpose* — the opposite end from rank 3. Both
   hold: the frame period is **chosen** first because it bounds everything
   downstream, and **defended** third when the axes collide.

What has *not* been stated is the consequence of reversing the order. The one
direction with a documented cost is rank 1 ↔ rank 2: going to 2×2 doubles the
pixel to 0.13 µm, and a Mortensen-style variance argument favours 65 nm pixels
for single-particle localisation once background scales per pixel area — and
localisation variance is the input to all three κ routes in the microrheology
design, so it propagates into every stiffness on record. That is a reason, but
it is this repository's reasoning, not the expert's stated one.

## Stated vs reconstructed

Kept separate on purpose — [`09 §7`](../../docs/09-knowledge-capture.md) rule 4
forbids lumping a reconstruction and an expert judgment into one claim.

| Part of this entry | Standing |
|---|---|
| The four-way ranking | **Stated by KH, 2026-09-07** |
| Intensity as the free variable that moves first | **Stated by KH, 2026-09-07**, as a clarification of what rank 4 means |
| The `Why` above | **Reconstructed** from the four cited records. KH has not given it in his own words |
| Scope beyond single-particle tracking | **Unstated.** Assumed narrow here rather than assumed general |
| The falsifiers below | **Proposed by this repository**, not by KH |

> **TODO(human):** the `Why` in KH's own words, and whether the scope line
> above is right. If the ranking is meant to be general, this entry's `scope`
> widens and falsifier 5 stops being a falsifier.

## Falsification conditions

1. **A photon-limited localisation measurement inverts ranks 1 and 2.** If the
   achievable photon count puts σ_loc in the regime where the `1/√N` term
   dominates the pixellation term, 2×2 binning *improves* precision and the
   ranking is wrong for that measurement. This becomes checkable — not
   arguable — once `power_at_sample_mw` is measured and the photon budget is
   absolute rather than relative.
2. **If the achieved frame period is ever measured and found not to equal the
   exposure setting**, rank 3's standing value collapses and the frequency axis
   of every stored result needs re-deriving from timestamps. Same falsifier as
   [`microrheology-standard-conditions`](microrheology-standard-conditions.md).
3. **A rate-valued intended quantity outranks this entry.** If what is being
   measured is a rate rather than a displacement — a fast binding or unbinding
   event — time resolution is prior by the definition of the quantity, and this
   ranking does not apply.
4. **A confirmed photoresponsive sample removes the free variable.** Once light
   is a hard-gated axis rather than a windowed one, "concede from the bottom up"
   has nothing to move first, and the tie-break has to be re-derived from
   whatever is left.
5. **A morphology measurement does not need this tie-break.** There, Nyquist
   governs the pixel and rank 1 and rank 2 stop pulling in opposite directions
   — so the entry is inapplicable rather than wrong, and should say so
   explicitly if a morphology run is ever proposed.

## Related

[[microrheology-standard-conditions]] · [[oil-objective-trapping-in-water]] ·
[[coverslip-thickness-in-use]] · [[sample-mount-geometry]]

Working form of the same rule, with the per-lens ownership and the cross-lens
resolutions: [`CLAUDE.md §1`](../../CLAUDE.md).
