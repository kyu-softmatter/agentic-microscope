---
id: 2026-09-11-a-pass-that-decides-must-be-visible
question: "Which passing branches of a judging lens have to appear in findings, and which may stay silent?"
date: 2026-09-11
status: current
corrects: []
---

# 2026-09-11 · A pass that decides must be visible; a pass that states a fact need not

**Decided by KH**, choosing the narrowest of three options offered for lens 6's
eight `_ok` call sites: *"(a) 결정을 담은 통과 분기만 `"info"` — 특히 194줄
(스코핑)과 217줄(감사 안 된 해제 경고). 가장 좁고 이번 세션의 선례와
일치합니다."*

## The line

> **A pass that rests on "this does not apply to you" is a DECISION and must be
> visible. A pass that rests on "you have it" is a FACT and may stay silent.**

The four decisions each **turned a check off on the strength of a lookup
table** — and if the table is wrong, a silent pass is exactly how nobody finds
out:

| branch | what it decided | from |
|---|---|---|
| G23 out-of-scope | every upstream bias is harmless to *this* quantity | `BIAS_SCOPE` |
| G23 declaration-accepted | the declared corrections clear the applicable biases | `CORRECTIONS` |
| G24 not-on-critical-path | this quantity does not depend on pixel size | `QUANTITY_REQUIREMENTS` |
| G25 not-photometric | this quantity does not rest on photometric calibration | `QUANTITY_REQUIREMENTS` |

The four facts stay on `_ok`: no upstream bias at all, pixel size required and
measured, every photometric calibration required and measured, every standing
lens returned. A reader can reconstruct each from the inputs.

Two of the four decisions were specifically worth rescuing:

- **G23's out-of-scope ruling carried an instruction**, not just a verdict —
  *"they still stand against the quantities they do damage — judge those
  separately."* At severity `"ok"` the ruling and the instruction both vanished,
  so a verdict said nothing at all about a bias it had just dismissed.
- **G23's declaration-accepted branch contained a warning inside a pass** —
  *"no correction is registered for X, so that clearance is unaudited and the
  verdict cannot be `measured`."* It reached `assumed_inputs` and never
  `findings`. And this branch is **the one place the ledger can be talked out
  of a FAIL**, on the strength of a declaration the gate cannot verify: that
  the correction exists is checked, that it was applied is not.

## Why this keeps happening: the helper is misnamed

Every `gate.py` in this repository drops `severity == "ok"` from `findings`
(nine files share the line), so anything returned through `_ok` lives only in
`metrics`, which no CLI prints. **`_ok` reads as "not graded" and behaves as
"not visible", and those are different things.**

This was the **fifth and sixth** instance of the same defect inside one review:

| lens | where | fixed |
|---|---|---|
| 5 | G20's saturation report | 2026-09-09 (gate removed) |
| 4 | `wall_drag`'s trapped branch — an 18.3% drag inflation | 2026-09-10 |
| 7 | `_ok` across the lens | 2026-09-10 |
| 8 | `_ok`, and `convening` with it | 2026-09-10 |
| 6 | G23 ×2, G24, G25 | **here** |

Lenses 5 and 8 became reporting sections, so "make everything `info`" was the
right answer there. Lens 6 is a judging lens with three `hard` gates, so it is
not — hence the narrower rule above. The `_ok` docstring now states the rule at
the point of use, which is the only place it will be read.

## What a clean verdict looked like before

Four margins at 10.00, `advances: YES`, and **zero findings**. The entire basis
of the verdict was in `metrics`. It now prints the branch that turned a gate
off, and nothing else.

## What changed

- `validity/checks.py` — four branches return severity `"info"` directly, each
  with an `action` naming the table the pass rests on and what a wrong entry
  would cost; `_ok`'s docstring carries the rule and the five prior instances
- `tests/test_validity_gate.py` — six tests: a pass that turns a gate off is
  visible, a pass that rests on having the calibration stays silent, clearing
  by declaration is visible, an unaudited clearance reaches `findings` and not
  only `evidence`, an empty ledger stays silent, and **the count** — exactly
  four `_ok` sites, with `"ok"` constructed nowhere else, so the narrowness is
  pinned rather than described
- `tests/test_validity_scope.py` — the out-of-scope test now asserts both the
  `metrics` count and the finding; `test_findings_carry_the_quantity_they_belong_to`
  got stronger, since one bias across two quantities now produces two
  differently-tagged findings (`{"diffusion": "fail", "intensity": "info"}`),
  which is what per-quantity judgement is for

1248 passed, 11 skipped, identical under `PYTEST_CI_EMULATE=ci`.

## Falsifier

A clean verdict becomes noisy enough that readers stop reading it. The rule
above is a guess about where that threshold is — four lines on a four-check
lens — and the count test is what makes drift visible. If a lens ends up
printing a paragraph per pass, the answer is not to re-silence the decisions
but to separate *rationale* from *findings* in `CheckResult`, which was option
(c) and was rejected as too wide for now (it touches all eight lenses).

The narrower falsifier: if one of the four "facts" turns out to rest on a table
too. `committee_coverage`'s *"every **standing** lens returned"* is the
candidate — it is a fact given the definition of standing, and `STANDING_LENSES`
omits both conditional lenses, so the sentence is true and the reader's likely
reading of it is false. That hole is deferred to the pipeline rework
(2026-09-11) rather than papered over here.
