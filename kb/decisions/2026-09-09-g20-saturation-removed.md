---
id: 2026-09-09-g20-saturation-removed
question: "Should the saturation gate stay, given that it blocks on two per-dye constants that are empty for every bead colourant this instrument images?"
date: 2026-09-09
status: current
follows: [2026-09-09-g10-photobleaching-removed]
---

# 2026-09-09 · G20 saturation removed

**Decided by KH.** The gate, its threshold, its two formulas, its tests and its
CLI flags are gone. **Lens 5 stays** — G21 (light-driving) and G22 (total dose)
are untouched. The number `G20` is **vacant and is not reused**.

## Request

> "렌즈 5는 삭제하자."
> — *Let's delete lens 5.*

Asked back with the scope, because the three gates are not in the same
position, and the answer chosen was **G20 only, lens retained**.

## Why

**It had one answer, and that answer was not about the instrument.** G20 gated
the steady-state excited-state fraction `k_ex·τ/(1 + k_ex·τ)` at 0.1. Reaching
`k_ex` needs `σ_abs = 3.82e-21 × ε`, and the occupancy needs `τ_fl`. So the gate
requires **two** per-dye constants. `data/fluorophores.yaml` has neither for
`DragonGreen`, and the file's own note says so: extinction coefficient, quantum
yield, lifetime, photostability and any spectral curve are "published nowhere."
The red bead is worse — it is deliberately not a registry entry at all, both
vendor peaks having been measured wrong on 2026-09-05 and 2026-09-06.

**Those are the two beads in hand.** A gate that cannot evaluate either probe
this lab owns is not gating this instrument.

**It was the same failure as G10, one step further on.** G10 needed
`bleach_photons`, empty for every entry. G20 needs `ext_coeff` *and*
`lifetime_ns`. The 2026-09-09 G10 decision drew the line — *"A gate that has one
answer is not a gate; it is a reminder, and the reminder had been read"* — and
G20 is on the same side of it. `lifetime_ns` being present for 13 named dyes is
what disguised this: the gate works for FITC and AlexaFluor488, and fails for
every particle actually on the bench.

**The trigger.** A drag-calibration proposal for the 5 µm green bead
(2026-09-09) returned `BLOCKED` from this lens on `missing.lifetime`, which
propagated to lens 6's G27 and made the whole committee verdict `INFEASIBLE` —
a verdict about a dye datasheet, not about a setting.

## What was argued against it, and why it did not win

Recorded because it is the strongest case for the other decision.

**G20 was the only gate protecting another lens's assumption.** `docs/04 §3` and
`optics.path.detected_e_per_s` are linear in power throughout. Past saturation
that linearity fails, so lens 1's and lens 2's photon budgets overestimate
signal while dose keeps climbing — and nothing else in the committee notices.
Unlike G10, whose bias was on the measured quantity, **G20's bias was on other
lenses' inputs**, which is a category the ledger has no other guard for.

**Why it did not win.** The protection was conditional on a constant the
instrument does not have, so it was never actually being provided. And the scale
argument bounds the exposure: FITC saturates near 3.5 × 10⁵ W/cm², while the
Aura widefield path delivers **1.1–7.7 W/cm²** at full level
([`illumination-power.yaml`](../calibrations/illumination-power.yaml)) — four to
five orders of magnitude below. For the widefield epi path that is the whole
answer. **For a focused confocal or spinning-disk spot it is not**, and that is
the residual this decision accepts.

## What it cost, stated plainly

- **Nothing now guards the linearity assumption in lenses 1 and 2.**
  `docs/05` Lens 5 and `docs/04 §5` both say so at the point where a reader
  would otherwise assume coverage.
- **`k_ex` feeds no gate at all**, so the spectral-overlap coupling assumption
  left the evidence axis. Two `assumed_inputs` entries went with it — quantum
  yield and overlap coupling — which means **lens 5 can now reach
  `evidence: measured` on a channel where before it could not.** That is a
  consequence of removal, not an improvement in evidence, and it should not be
  read as one.
- **Lens 5 has one gradeable gate left.** For a non-photoresponsive sample the
  feasibility grade rests on G21 alone, with G22 and the trap-heating notice
  `info`. A lens with one gate is close to the condition that retired G10.
- **The `photo.LIMITS` dict is now empty.** This lens has no numeric threshold
  of its own: G21 compares against a per-sample *measured* threshold and G22
  against a caller-supplied ceiling.

## The route back

Not by restoring G20. The observable is **linearity itself** — emission versus
illuminator level at the run's own exposure — which needs no dye identity, the
exact failure mode G20 could not handle. This is the same route back G10 was
given, and the instrument has already done it once for the other bead:
*"Linear in illuminator setting across the range measured (20/40/60 per-mille →
17.4/34.0/48.2 % of ceiling)"*
([`frame-photometry.yaml`](../calibrations/frame-photometry.yaml)).

Two steps, in order, and the order matters:

1. **Meter the Aura CYAN level→mW curve below 5 %, at the 20×.** The only
   measured point below 10 % is `{5: 3}` — one significant figure — and the
   curve is non-linear there (1.30 of linear at 5 %, 1.09 at 10 %), with a
   pedestal suspected. Without this, illuminator non-linearity and dye
   saturation cannot be separated: they are non-linearities in the same product.
2. **Then a level→ADU series on the bead at the run's exposure and binning.**
   Residual curvature in ADU-per-mW *after* dividing by step 1 is dye
   saturation — G20 measured rather than predicted.

That is a lens 6 check on data, or a `kb/calibrations/` entry, not a lens 5
prediction from a constant.

## What changed

Removed: `photo.checks.check_saturation`, `LIMITS["excited_state_fraction_max"]`
(leaving `LIMITS` empty), its `CHECKS` entry and its two `requires` facts
(`excitation_rate`, `lifetime`) from `available_facts`,
`photo.dose.excited_state_fraction`, `photo.dose.saturation_irradiance_w_cm2`,
the `missing.lifetime` finding, the `quantum yield` and `spectral overlap
coupling` entries in `_assumed_inputs`, the `photo/__init__.py` exports, and
`photo.cli`'s `--lifetime-ns`, `--quantum-yield`, `--ext-coeff` and
`--excitation-coupling`. **`IlluminationSetup`'s dye fields and
`resolved_excitation_rate` are deliberately left in place**, populated by
`from_channel` and by `--dye`, read by nothing — the same reasoning the G10
decision used for leaving `perturbation.photobleaching` registered in
`validity/setup.py`.

Sixteen tests went with it; the suite is **1194 passed, 11 skipped** on macOS
(from 1210/11). One test was **retargeted rather than deleted**:
`test_unasked_photoresponsiveness_does_not_block_the_whole_lens` asserted that
an unasked photoresponsiveness still lets the other gates be judged, and it
proved that through G20's margin. It now asserts on G22's, the only other graded
gate. The four spectral-overlap-coupling tests were **deleted, not retargeted** —
their subject was `k_ex`'s effect on a gate, and there is no such gate now. Note
that one of them,
`test_coupling_scales_k_ex_and_so_every_gate_downstream`, had already been
retargeted once by the G10 removal; the second retarget had nowhere left to go.

Documentation: `docs/04 §5` keeps `I_sat` and the occupancy formula and says why
the gate is gone, since the physics did not stop being true; `docs/04`'s gate
table marks the row vacant. `docs/05` Lens 5 records the two consequences above.
The gate count moves 31 → 30 and implemented 28 → 27, in `CLAUDE.md`,
`README.md`, `docs/01`, `docs/03` and `docs/mhs-integration.md`.
`.claude/agents/photo-perturbation.md` — the lens 5 brief — was updated, and
**it was already stale for G10**: that removal did not touch it, so the brief
had been teaching a gate that did not exist for the whole day. C1 and C2 are now
marked as physics rather than gates.

## Falsifying condition

A run on the confocal or spinning-disk path where emission stops rising with
level, and lens 1's or lens 2's photon budget is believed anyway. That is the
case this decision accepts. Finding one is the reason to do the two-step
linearity measurement above — not to restore a gate keyed to a constant the
vendors do not publish.

A second, narrower falsifier: a bead whose colourant *is* identified, with ε and
τ both on record. That does not make this decision wrong — it puts the
experiment outside the scope condition, which is that the probes in hand are
proprietary and unpublished.
