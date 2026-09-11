---
id: 2026-09-11-the-emission-collection-layer
question: "How should the committee know which codes its lenses can emit, when the answer had been hand-counted wrong three times?"
date: 2026-09-11
status: current
corrects: [2026-09-11-wall-drag-reaches-the-bias-ledger]
---

# 2026-09-11 · The emission collection layer

**Asked for by KH** rather than having the bias registries hand-reconciled:
*"추후에 모든 방출 정보를 모으는 레이어를 하나 만들거야."* The reasoning was
that a table edited to match today's emitters drifts again on the next gate
change — and it had already done so twice in one week.

New package **`committee/`**. Not a lens: the eight lenses judge a proposal,
this judges the **wiring between them**.

```
python -m committee.cli emissions     # every code, every lens, kind + severity
python -m committee.cli reconcile     # vs lens 6's bias registries
python -m committee.cli invisible     # computed at severity "ok", so never printed
python -m committee.cli parser        # sites the parser could not read
```

## Derived, not declared

The obvious design was an `EMITS` constant in each of the eight `checks.py`
files. Rejected: it would restate what the code already says and so could
disagree with it, which is the failure this layer exists to stop, and
`CLAUDE.md` §7 already says **one definition, one file**.

So the table is **parsed**, and the parser's blindness is made detectable:
`committee.unparsed_sites(lens)` returns every `CheckResult`/`_ok` construction
site it did not understand, and a test asserts that set is empty for all eight
lenses. **A silent parse miss is worse than not having the layer**, because it
would confidently report that a code cannot reach the bias ledger when it can.

**104 emission sites** across 8 lenses, each carrying its address, the check it
came from, the emitted code, the result's kind, the severity, whether it reaches
`findings`, and whether it reaches lens 6's ledger.

## It corrected its own predecessor twice

The hand-written snapshot in `tests/test_gate_registry.py` was wrong in two
different ways, and both were found by building this.

**First error — scanning by registration instead of by result.** The original
count scanned only checks whose `Check` registration was `BIAS`. But
`validity.setup.bias_findings` filters on the **result's** kind, and three
BIAS-kind results come out of INFO-registered checks in lens 4:
`geometry.depth_window.empty` and `geometry.count_in_field.{crowded,jammed}`.
Seven unregistered emitters became nine, then eight. Caught and fixed by hand
earlier the same day.

**Second error — reading one branch of a conditional.** `detection/checks.py`
builds the code with a ternary:

```python
return CheckResult(
    "sampling" if ok else "sampling.wrong_direction",
    BIAS, margin, "ok" if ok else "fail", ...
```

The regex matched the literal after `CheckResult(` and so saw only `sampling`
at severity `ok` — from which the test concluded that the code *could not reach
the ledger whatever the registry said*, and asserted it. **It can:
`sampling.wrong_direction` is BIAS at severity `fail`.** Eight unregistered
emitters, not seven. Nothing but a parse would have said so; the same blind
spot also hid `sampling.undersampled` entirely.

**And the layer's own first run had the mirror-image bug.** Taking the cross
product of the two conditionals invented `("sampling", "fail")` — BIAS-kind,
findings-visible, and impossible, since the two conditionals share one
condition. It duly appeared as an unregistered ledger code somebody would have
been sent to register. `committee.emissions._pair` now zips branches when the
tests are structurally equal and falls back to the product otherwise, so it
over-reports rather than under-reports. Three counting errors on one question
is the argument for parsing it.

## What it reports today

| | count | |
|---|---|---|
| agreed | **4** | `crosstalk`, `motion_blur.biased`, `geometry.wall_drag`, `geometry.wall_drag.trapped` — the only codes whose declaration this repository can check |
| registered, no emitter | **7** | `geometry.coverslip`, `geometry.ri_mismatch`, `perturbation.{photobleaching,saturation,light_driving}`, `stability.{evaporation,lateral_drift}` |
| emitted, no registry | **8** | `fps_provenance.{requested,unmeasured,unrealizable}`, `geometry.count_in_field.{crowded,jammed}`, `geometry.depth_window.empty`, `pixel_container.unconfirmed`, **`sampling.wrong_direction`** |

**`reconcile` exits 1 and is deliberately not wired into the test suite as a
failure.** The drift is known and is KH's to close through this layer. What the
suite does assert is the *shape* — that the three sets are exactly these — so a
new gate shows up as a decision rather than as noise.

Lens 3's three `fps_provenance.*` remain the most consequential: frame-rate
provenance biases every timing-derived quantity, the drag calibration's
velocity included, and no table says whether it is correctable after the fact.

## A second consumer, for free

`committee.invisible_computations()` lists the **34 sites** that compute a
result at severity `"ok"`, which every `gate.py` drops from `findings` — so
they exist only in `metrics`, which no CLI prints. That is the defect class
that recurred five times through this review. The layer does not judge which
are defects; the line drawn on 2026-09-11 does that (*a pass that rests on
"this does not apply to you" is a decision; a pass that rests on "you have it"
is a fact*). It lists the candidates, and it noticed that nothing from lenses
5, 7 or 8 is on the list — because their `_ok` says `"info"`.

## What changed

- `committee/__init__.py`, `committee/emissions.py`, `committee/cli.py` — new
- `tests/test_committee_emissions.py` — 20 tests, the parser's coverage and its
  conditional handling first, the reconciliation second
- `tests/test_gate_registry.py` — the two hand snapshots and their regex
  removed, replaced by a pointer test; the comment records both errors so the
  next person does not re-derive them
- `CLAUDE.md` §5, `docs/01`'s tree — the new command and package

1274 passed, 11 skipped, identical under `PYTEST_CI_EMULATE=ci`.

## Falsifier

**A lens starts building a code in a way `ast` cannot follow** — from a dict
lookup, an f-string, a helper that returns the code. `unparsed_sites` catches
it and the test fails, which is the design; but if that becomes common, parsing
is the wrong approach and per-lens declarations validated against runtime
observation is the next thing to try.

**Or: the reconciliation is never acted on.** The layer makes the drift visible
and exits non-zero, and it can do nothing about a report nobody reads. If the
7-and-8 are still 7-and-8 in a month, then this replaced a wrong hand count
with an accurate ignored one, and the honest fix is to wire `reconcile` into CI
as a failure and force the tables closed.
