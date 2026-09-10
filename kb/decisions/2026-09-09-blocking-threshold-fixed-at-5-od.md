---
id: 2026-09-09-blocking-threshold-fixed-at-5-od
question: "Should the excitation-blocking requirement rise from 5 OD to 7 OD when the path spectra are parametric rather than measured?"
date: 2026-09-09
status: current
corrects: [2026-08-10_fitc-particle-yoyo1-dna-2color]
---

# 2026-09-09 · The blocking bar is 5 OD in both evidence tiers

**Decided by KH**, during a gate-by-gate review of lens 1. G3's requirement no
longer moves with the evidence tier, and neither does `ablate()`'s internal
blocking floor. **5.0 OD, flat.**

## Request

> "두 경우 모두 5로 고정" … "b는 같이 5로 내릴것"
> — *Fix it at 5 for both cases* … *lower it [the ablation floor] to 5 as well.*

## Why

**The approximation was being charged twice.** A channel built on parametric
band shapes already cannot `advance`: every lens requires
`evidence == "measured"` for that, so a verdict resting on approximated spectra
is capped no matter what its margins say. Raising the threshold on top of that
made one weakness decide the verdict a second time — and the second charge is
the one that lands as a `hard` FAIL, because G3 is `hard` and a margin below
1.0 sets `status = FAIL`.

**The consequence was concrete, not hypothetical.** Two committed channel
configurations sit at **6.1 OD**, which clears 5 and fails 7:

| config | at 7 OD | at 5 OD |
|---|---|---|
| `particle647-yoyo1-2color.yaml` | blocking 0.87 → **FAIL / INFEASIBLE** | blocking 1.22 → PASS_WITH_CHANGES / TIGHT |
| `abvigen-bangs-green-red-2color.yaml` | same | blocking 1.22 / 1.28 → PASS_WITH_CHANGES / TIGHT |

**This repository had already reached that reading and not acted on it.**
`config/channels/abvigen-bangs-green-red-2color.yaml`, 2026-09-05:

> the residual shortfall is an **EVIDENCE penalty, not a physical one** — 6.1 OD
> clears the 5 OD requirement that applies with measured curves, and only fails
> the 7 OD bar that `data/spectra/README.md` imposes precisely because the
> spectra here are parametric approximations.

So the decision does not overturn an analysis; it moves the penalty to the axis
that analysis already said it belonged on.

**And no other gate did this.** Across all eight lenses this was the only
threshold that varied with its own inputs' evidence tier. Everywhere else the
threshold is a physical constant and the evidence tier is handled on the
`evidence` / `advances` axis. G3 was the exception, and the exception was not
recorded as a decision anywhere — it lived only in `data/spectra/README.md` and
in a `LIMITS` comment.

## What was argued against it, and why it did not win

Recorded because it is the real cost.

**A parametric filter has an idealized flat blocking floor and infinitely clean
wings.** `Spectrum.band(..., blocking_od=...)` gives out-of-band transmission
as a constant, where real glass has structure — leakage peaks, and wings that
do not fall as fast as a boxcar. So a parametric 6.1 OD may be a real 4 OD, and
blocking is exactly the quantity where the wings decide the answer. The 2 OD
was a hedge against that, and removing it means a configuration can now pass on
a number that glass may not deliver.

**Why it did not win.** A hedge sized by guess, applied to a `hard` gate, stops
configurations that work — and it cannot distinguish the case it was built for
(a filter whose real wings are worse) from the case it actually hit (a
two-filter stack at 6.1 OD, where the margin is genuine). The honest handling of
"we do not know the wings" is `evidence: assumed`, `advances: NO`, which is what
the verdict now says on its own. A threshold is a claim about physics; an
evidence tier is a claim about what we know. Mixing them made the gate report
the second as if it were the first.

## What changed

- `optics/checks.py`: `LIMITS["blocking_od_assumed"]` (7.0) removed;
  `check_blocking` uses `LIMITS["blocking_od"]` unconditionally. The `assumed`
  flag is still computed and still reported in `numbers`, so the approximation
  stays visible — it just no longer prices itself in.
- `optics/path.py`: `ablate()`'s `blocking_floor` is `min_blocking_od` flat; the
  `+2.0` under `spectra_measured=False` is gone. **`spectra_measured` still
  downgrades every removal to `candidate`**, which is what keeps the removal
  analysis timid on approximate curves — that guard was not touched.
- `docs/04` G3 row, `docs/06` (the removal guards go three → two, with the third
  marked as removed rather than deleted), `data/spectra/README.md` (the claim is
  struck through, not erased).
- **Three tests added, and the reason matters more than the tests.** Neither the
  7 OD escalation nor the `+2.0` had any test, so removing both broke nothing —
  a threshold change passed a green suite twice in one commit. The new tests
  pin the flat floor in both places and assert `blocking_od_assumed` is absent,
  so restoring the penalty is a decision rather than a tweak.

## What is deliberately left alone

The dated commentary in four channel configs and three `kb/systems/` files still
quotes the 7 OD bar. Those are records of what the gate said on the day and are
**marked by this entry, not rewritten** — the same rule the G10 removal applied
to README's session transcripts. `kb/decisions/2026-08-10_fitc-particle-yoyo1-dna-2color.md`
carries the `corrects` link in this entry's frontmatter for that reason.

## Falsifying condition

A configuration that reads 5–7 OD on parametric spectra and, once measured
curves are loaded, comes out **below 5 OD**. That is the case this decision
accepts the risk of: it would show the flat blocking floor really was optimistic
by about the margin that was removed, and that the penalty belonged in the
threshold after all.

The cheap way to look for it: the repository has no measured filter curve for
any element in `data/spectra/` today. The first one loaded is the first test of
this decision, and `particle647-yoyo1-2color.yaml` at 6.1 OD is the
configuration to re-run when it arrives.
