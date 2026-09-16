---
id: 2026-09-11-wall-drag-reaches-the-bias-ledger
question: "Why did a bias that lens 4 measured and reported never reach the lens whose job is reviewing biases?"
date: 2026-09-11
status: current
corrects: []
---

# 2026-09-11 · The trapped wall-drag bias reaches lens 6's ledger

**Decided by KH:** *"wall_drag의 info 분기를 원장에 넣자."* Three changes were
needed, and only the first was the one asked for — the other two are holes the
first one exposed.

## The bias, and why it matters here

Faxén's parallel-to-wall suppression `9a/(16h)` inflates the drag by
`1/(1−s) − 1`. For the 5 µm bead at the ~10 µm depth an oil objective allows,
that is **+16.4% on γ**, and at 9 µm **+18.3%**. On a Stokes-drag calibration —
`κ = γv/x_eq` — that lands **directly on the measured stiffness**, because γ
goes *in* as `6πηa` rather than coming out of a fit. It is the principal bias of
the experiment this instrument is being set up for.

Lens 4 computes it correctly and does not grade it, which is right: a trap *can*
absorb it, because an in-situ corner-frequency calibration at the working height
returns κ and the wall-corrected γ together (`docs/06 D8`,
`kb/expertise/oil-objective-trapping-in-water.md`). Whether the absorption
applies is **lens 6's question**, not lens 4's.

It was not reaching lens 6.

## Three layers had to be fixed, and each hid the next

**1 · The result's `kind` was `INFO`.** `validity.setup.bias_findings` filters
on the *result's* kind, not the `Check` registration's, so an INFO-kind result
was never a candidate for the ledger no matter what its severity said. Fixed by
returning `kind: BIAS` at `MAX_MARGIN` with severity `"info"` — which costs
lens 4 nothing, since 10.0 is never its worst margin and `"info"` stays out of
`PASS_WITH_CHANGES`. The grading moved to lens 6; it did not move into lens 4.

This is the **third** distinct defect on this one branch, and the sequence is
worth keeping because each fix revealed the next:

| when | defect | fix |
|---|---|---|
| until 2026-09-10 | `_ok` → severity `"ok"`, dropped from `findings` | severity `"info"` |
| until 2026-09-11 | `kind: INFO`, so never a ledger candidate | `kind: BIAS` |
| until 2026-09-11 | one code for both branches, so one registry answer | `.trapped` suffix |

**2 · `bias_findings()` required severity `warn` or `fail`.** Widened to
`{"info", "warn", "fail"}`. The reading that justifies it: **a bias-kind result
at severity `"info"` means the origin lens measured a real bias and declined to
GRADE it**, because grading it is somebody else's question. That is different
from an INFO-*kind* result, which means "no bias occurred" or "nobody has
decided yet" — `detection.motion_blur` returns `motion_blur.not_applicable` and
`motion_blur.rate_undecided` at severity `"info"` and both carry `kind: INFO`,
so neither is admitted. **The distinction is the kind, and the filter already
keyed on it.** Audited across all seven lenses: `geometry.wall_drag.trapped` is
the only bias-kind result at severity `"info"` today.

**3 · A distinct code, `geometry.wall_drag.trapped`.** The registries are keyed
by code and the two branches need opposite answers:

- **`geometry.wall_drag.trapped` → `CORRECTIONS`** — the in-situ
  corner-frequency calibration at the working height. **The drag calibration
  *is* that correction**, so declaring it reads clean; not declaring it fails.
- **`geometry.wall_drag` → `UNCORRECTABLE`** — there is no corner frequency
  without a trap, and near-wall drag is deliberately not corrected by formula
  (`kb/decisions/2026-08-19-lens-7-scope.md` §2). So declaring it is a *false
  claim*, which G23 reports louder than leaving it uncorrected, because the
  ledger would otherwise have read clean.

Both get `BIAS_SCOPE = {"pixel_size"}`: wall drag biases γ, hence D and every
force and viscosity read through it — the kinematic quantities. An intensity or
stoichiometry measurement on the same frames is untouched, which is what lets
one session report a biased D and a sound intensity profile.

⚠ **The declaration is a claim about where γ enters, not about the trap.** True
where γ comes *out* of a fit (equipartition, a PSD corner frequency); **false
where it goes *in* as `6πηa`**. The registry cannot tell which the experiment is
doing, so the wording in `CORRECTIONS` says so and both agent briefs repeat it.

## And then the ledger still could not fail on it

With all three fixed, the end-to-end run gave:

```
status=PASS_WITH_CHANGES  feasibility=ROUTINE  advances=True
uncorrected=['geometry.wall_drag.trapped']
```

**The bias was in the ledger, named as uncorrected, and the verdict advanced
anyway.** G23's margin was the worst uncorrected upstream margin, and this
bias's upstream margin is `MAX_MARGIN` **precisely because lens 4 declined to
grade it**. So 10.0 arrived as if it meant headroom, and a HARD gate at 10.0
cannot fail.

Fixed: G23 reports the worst uncorrected **shortfall**, and **drops to 0.0 when
an uncorrected bias arrived with a margin ≥ 1.0.** The rationale is a rule this
repository already states — `CLAUDE.md` §3's **`unevaluated ≠ cleared`** — applied
to a margin instead of a status. A passing margin on an *uncorrected* bias means
ungraded, not small. The upstream number is not destroyed: it moves to
`metrics.worst_uncorrected_margin`, with the codes in
`ungraded_uncorrected_codes` and a note saying why they look like passes.

The mixed case keeps the informative number: one bias at 0.4 and one ungraded
at 10.0 gives margin **0.4**, because a real shortfall says more than the 0.0
floor.

After: `status=FAIL · feasibility=INFEASIBLE · advances=False · margin=0.0`
with the correction undeclared, and `PASS · ROUTINE · advances=True` with it
declared. **That is the behaviour that was wanted: the drag calibration has to
say out loud that it did the in-situ calibration.**

## What changed

- `sample/checks.py` — the trapped branch returns `kind: BIAS` under
  `geometry.wall_drag.trapped`; a comment records all three defects in order so
  the next reader does not undo one of them
- `validity/setup.py` — `_BIAS_SEVERITIES` added (`info`/`warn`/`fail`) with
  the kind-versus-severity distinction spelled out; `CORRECTIONS` and
  `UNCORRECTABLE` entries; two `BIAS_SCOPE` entries
- `validity/checks.py` — the margin rule above; `worst_uncorrected_margin`,
  `ungraded_uncorrected_codes` and `ungraded_note` added to `numbers`, and the
  first two seeded in every branch so the metrics shape does not depend on
  which one ran
- `tests/test_sample_gate.py` — retargeted to the new code, plus tests that the
  two branches use different codes with opposite registry entries, and that
  BIAS-kind still costs lens 4 nothing
- `tests/test_validity_gate.py` — severity `info` admitted, INFO *kind* still
  refused, both wall-drag branches end to end, the ungraded-margin rule, the
  mixed case, and the metrics-shape invariant
- `.claude/agents/sample-optics.md`, `.claude/agents/measurement-validity.md`,
  `docs/05` — the new code, the severity widening, the margin rule, and the
  γ-enters-where caveat

1237 passed, 11 skipped, identical under `PYTEST_CI_EMULATE=ci`.

## Falsifier

**On the severity widening:** a lens starts emitting a BIAS-kind result at
severity `"info"` that is *not* a bias occurrence — a "not applicable" or
"undecided" state mis-tagged as BIAS. Then the ledger fills with non-events and
the filter has to key on something else than kind. The audit above is what makes
that detectable; `tests/test_gate_registry.py` pins the kinds, but nothing yet
pins a result's kind against its meaning.

**On the margin rule:** a bias whose origin lens grades it at `≥ 1.0` and means
it — "measured, small, inside my limit, and I am telling you the headroom".
Then dropping to 0.0 is wrong, because the bias genuinely is small. Note the
current code cannot express that case: a bias gate that passes its own limit
returns via `_ok`, severity `"ok"`, which never reaches the ledger at all. So
the rule is safe as long as that stays true — and if a lens starts reporting
"small but present" at severity `warn`/`info` with a passing margin, this needs
revisiting rather than the gate needing a patch.

**On the registry split:** somebody establishes an absorption route for an
untrapped particle — a local drag measurement that does not need a trap. Then
`geometry.wall_drag` moves from `UNCORRECTABLE` to `CORRECTIONS` and the
two-code split is no longer earning anything.
