---
id: 2026-09-09-g10-photobleaching-removed
question: "Should the photobleaching gate stay, given that it has never returned anything but BLOCKED and its only unshared lever is the dye?"
date: 2026-09-09
status: current
---

# 2026-09-09 · G10 photobleaching removed

**Decided by KH.** The gate, its threshold, its tests and its plumbing are gone.
The number `G10` is **vacant and is not reused** — a later gate taking it would
make every reference in the history ambiguous.

## Request

> "G10는 삭제해도 될듯, 현재 다른 렌즈들이 노출과 이미징을 최적화 하고있고,
> 어쩔 수 없이 해당 다이를 사용해야하는 경우가 더 많음"
> — *G10 can be deleted. The other lenses are already optimising exposure and
> imaging, and more often than not you have no choice about which dye to use.*

## Why

Two reasons, and the second is the one that decides it.

**It never worked.** G10 computed `f_bleached = 1 − exp(−N_emitted/N_bleach)`
against a 20 % limit, and `N_bleach` is `bleach_photons` — a per-dye constant
that is empty for every dye in `data/fluorophores.yaml` and that no measurement
on this instrument supplies. Every evaluation returned `BLOCKED`. A gate that
has one answer is not a gate; it is a reminder, and the reminder had been read.

**Its levers are already owned, except the one nobody has.** A bleaching gate
can name three things: acquisition length, light level, and dye. The first two
are governed by G22 (total dose) and G20 (saturation), which now compute — power
and illuminated area were measured the same day
([`illumination-power.yaml`](../calibrations/illumination-power.yaml)). The
third is the operator's point: the sample dictates the label far more often than
the label is chosen. So G10's unique contribution was advice that could not be
taken.

## What was argued against it, and why it did not win

Recorded because it is the strongest case for the other decision, and because a
future reader deserves it rather than a one-sided note.

G10 was a `bias` gate, and `bias` is the kind docs/05 §2 calls most dangerous:
*"Because the data comes out looking plausible, it is hard to notice after the
fact."* Photobleaching biases a tracking run in a way that is invisible in the
data — localisation precision decays through the movie, so an MSD fitted across
it mixes two noise regimes.

**That argument is about the quantity, not about this gate.** A prospective
gate keyed to a dye constant cannot deliver it on this instrument, and has not
in the months it existed. The bias is real and the gate was not.

## What it cost, stated plainly

**Photobleaching has left lens 6's bias ledger.** G23 collects `bias` findings
from the other lenses; nothing now emits `perturbation.photobleaching`, so a run
whose intensity halved will get a clean ledger and lens 6 will not say
otherwise.

The code is **deliberately left registered** in `validity/setup.py` — in
`CORRECTIONS` ("intensity-decay correction") and in `BIAS_SCOPE` (damaging
`background`, `dark_current`, `flat_field`, `linearity`). It is vocabulary the
ledger already knows how to handle, it costs nothing to keep, and it means
whatever emits that code next drops in without touching lens 6.

## The route back

Not by restoring G10. The observable is the **decay itself**, which is
measurable in the acquisition and needs no dye identity at all — the failure
mode G10 could not handle was the unidentified dye, and a decay measurement is
indifferent to it. This instrument has already produced one:
**+2.19 % first-15 vs last-15 frames over 5 s**, Aura GREEN at 50/1000, 33.33 ms,
100× ([`kb/systems/current.md`](../systems/current.md)) — a measured near-absence
of bleaching under standing conditions, obtained without any dye's
`bleach_photons`.

That is a **lens 6 check on data**, not a lens 5 prediction from a constant, so
it would take a new number in `validity/` rather than G10's. Nothing in
`analysis/` or `calibration/` computes it today.

## What changed

Removed: `photo.checks.check_photobleaching`, `LIMITS["bleached_fraction_max"]`,
its `CHECKS` entry, `photo.dose.bleached_fraction` and
`emitted_photons_per_molecule`, `IlluminationSetup.bleach_photons`, the
`missing.bleach_photons` finding, `photo.cli`'s `--bleach-photons`,
`Dye.bleach_photons` and the field's line in `data/fluorophores.yaml`'s schema.
Ten tests went with it; the suite is 1260 passed, 7 skipped.

One test was **retargeted rather than deleted**:
`test_coupling_scales_k_ex_and_so_relaxes_the_bleaching_margin` asserted that
assuming perfect spectral overlap overstates `k_ex` and so makes the gates
stricter than the instrument warrants. That property belongs to `k_ex`, not to
G10. The obvious substitute — G20's margin — turned out to be vacuous, because
the reference setup sits far enough from saturation that both margins clip at
`MAX_MARGIN` and the excited fraction rounds to 0.0. It now asserts on `k_ex`
directly, where the factor of two is visible.

Documentation: [04 §6](../../docs/04-decision-engine.md) keeps the formulas and
says why the gate is gone, since the physics did not stop being true. The gate
count moves 32 → 31 and implemented 29 → 28, in `CLAUDE.md`, `README.md`,
[01](../../docs/01-architecture.md), [03](../../docs/03-cross-system-transfer.md)
and `docs/mhs-integration.md`. Two README passages are historical transcripts of
sessions where G10 refused; they are **marked, not rewritten** — what the gate
said on the day is what it said.

## Falsifying condition

A run where the intensity decays enough to bias the result, and no other gate
notices. That is the case this decision accepts, and finding one is the reason
to build the retrospective check rather than to restore G10.
