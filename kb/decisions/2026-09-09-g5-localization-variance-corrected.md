---
id: 2026-09-09-g5-localization-variance-corrected
question: "Why did G5 report that a pixel finer than imaging-Nyquist hurts tracking precision, when CLAUDE.md H4 says the opposite?"
date: 2026-09-09
status: current
corrects: [imaging-priority-hierarchy]
---

# 2026-09-09 · G5's localization variance corrected, three ways

**Decided by KH** during a gate-by-gate review of lens 2, after the gate and
[CLAUDE.md](../../CLAUDE.md) H4 were found to disagree about the same physics.
**H4 was right and the gate was wrong.**

## Request

> "G5에 대해서 2x2로 해도 손해가 없다 라는 뜻인건가?" … "셋 다 고침을로 선택해줘"
> — *Does G5 mean 2×2 costs nothing?* … *Take the "fix all three" option.*

## The disagreement that started it

H4 forbids changing 1×1 to 2×2 on SNR grounds, and gives its reason:

> a Mortensen-style variance argument favours 65 nm pixels for single-particle
> localisation **once background scales per pixel area**

G5's tracking branch *is* that variance argument, and at the light level lens 2
had chosen it answered the other way: raise the illuminator past ~×14 of the
2026-09-06 photometry level and it fired `sampling.wrong_direction`, reporting
that the imaging-Nyquist pixel (109 nm) would localise better than the standing
64.53 nm. **The italicised clause is exactly the condition the gate was not
applying.**

## Why — three defects, and each one pushed the same way

`localization_variance_nm2` implements

```
var = sigma_a^2/N + 8*pi*sigma_a^4*b^2 / (p^2 * N^2),   sigma_a^2 = sigma_psf^2 + p^2/12
```

which is right. What was wrong was everything around it.

**1. The counterfactual held `b` fixed while changing `p`.** G5 grades by
computing the variance twice, at the actual pixel and at the Nyquist pixel, and
it passed the *same* `background_e` to both. Background collected per pixel
scales with pixel area, so holding it fixed leaves `b²/p²` falling as `1/p²` and
manufactures a preference for coarse pixels that no optics produces.

**2. `b` was fed a count where the formula wants a noise.** `b` is the per-pixel
background *standard deviation*, so `b²` is a variance — the background's own
shot variance (numerically its count) plus the read variance. The code squared
the count. At 2.7 e⁻/px that overstates the second term by 2.7×; at 100 e⁻/px,
by 100×.

**3. Read noise was absent entirely.** `effective_read_noise_e` is what G7 uses,
and G5 never saw it — even though **read noise is the term that gives the
optimum a finite location.** Write `b² = βp² + σ_read²`:

```
bg_term = 8*pi*sigma_a^4 * (beta + sigma_read^2/p^2) / N^2
```

The `β` half grows with `p`. Only the `σ_read²/p²` half falls with `p` and then
rises, and only it has a minimum. So the docstring's claim — and
[`docs/04 §2`](../../docs/04-decision-engine.md)'s — that *background* makes the
optimum finite was wrong; an area-scaling background alone makes ever-finer
pixels monotonically better.

## The numbers, on the configuration that raised it

`100x-Oil`, 1×1 (64.53 nm), λ_em 520 nm, σ_PSF 75.3 nm, N = 1709 photons,
background 2.68 e⁻ per 65 nm pixel, effective read noise 1.60 e⁻:

| treatment | 65 nm (1×1) | 109 nm | 129 nm (2×2) | optimum |
|---|---|---|---|---|
| as the gate computed it | 2.01 nm | 2.03 | 2.08 | 80 nm |
| `b` scaled with area only | 2.01 | 2.41 | 2.66 | none in range |
| `b` as a noise only | 1.93 | 2.00 | 2.05 | 62 nm |
| **all three fixed** | **1.98 nm** | 2.06 | **2.11 nm** | **60 nm** |

So the answer to the question that started this: **2×2 is not free.** It costs
about 7 %, the optimum is 60 nm against σ_PSF 75 nm, and the standing 1×1 choice
sits essentially on it — which is what H4 said and what
[`docs/06 §C6`](../../docs/06-pitfalls.md) says.

## What was argued against it, and why it did not win

**The formula is standard, and Thompson et al. do hold `b` fixed while
optimising over `p`.** That is true, and it is why defect 1 is subtle: in the
original treatment `b` is dominated by read noise, which really is fixed per
pixel. The error is not in the formula but in feeding it a pure area-scaling
illuminated background — measured from a frame, on this instrument — and then
varying `p` as if that quantity did not depend on `p`.

## What it cost, stated plainly

**One test asserted the old behaviour and it was asserting a bug.**
`test_sampling_wrong_direction_downgrades_to_pass_with_changes_for_tracking`
used the legacy 100x/1.5x pixel (73.3 nm) against a 140.5 nm Nyquist limit and
expected a fail. Corrected, that camera's optimum is **~72 nm**, so 73.3 nm is
*on* the optimum: 8.67 nm against Nyquist's 9.30 nm. The old code reported
27.42 nm there and put the optimum at 292 nm. The test is retargeted, and
`test_a_pixel_far_below_the_optimum_still_trips_c6` was added at a 4 µm sensor
pixel (26.7 nm at the sample, margin 0.85) so **the pitfall stays reachable** —
the correction had to fix the arithmetic without deleting the warning.

**`detection/recommend.py` moved with it**, since `from-frame`'s reported
localisation precision uses the same function; it now passes each mode's own
effective read noise.

## What it unblocked, which was not the point but matters

The light level had been pinned to a window of roughly **CYAN 36–42/1000** —
bounded below by G7's SNR target and above by this artifact. It is now bounded
above by **G6 saturation**, a `hard` gate on real physics, and the window runs
to about ×48 of the photometry level. That lands the illuminator inside the
region where its own level→mW curve has been metered (≥50/1000), which was lens
5's second-ranked recommendation, and it retires the lens 2 ↔ lens 5 conflict
where lens 5 wanted more light and lens 2 refused it.

## Falsifying condition

A tracking configuration where the corrected G5 clears a pixel size that
measurably localises worse than a coarser one on this instrument. The test is a
bead imaged at two binnings at matched photon count, with the localisation
scatter of a stuck bead compared: 1×1 should beat 2×2 by roughly the 7 % above.
If 2×2 wins, then something not in this expression dominates — most likely that
the real PSF is wider than `psf_sigma_nm` computes, which would move the optimum
up toward 2×2 and make H4's standing choice the wrong one.

Nothing in `kb/calibrations/` records a localisation scatter at either binning
today, so this has never been measured on this bench.
