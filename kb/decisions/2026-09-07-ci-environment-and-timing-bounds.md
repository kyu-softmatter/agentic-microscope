---
# frontmatter added 2026-09-09 for kb/INDEX.md. `question` restates this
# file's own title and Request/Context; the link fields read its own
# supersession notes. A retrieval aid, not evidence -- see knowledge/index.py.
id: 2026-09-07-ci-environment-and-timing-bounds
question: "Why did CI go red on three commits that did not cause it, and what may a timing test assert?"
date: 2026-09-07
---

# 2026-09-07 · The runner's environment is not this venv, and two tests were measuring the runner

> Three commits of red CI, one stale assertion, and a timing bound that had
> already been loosened once. None of it was caused by the commits it appeared
> on, and all of it has the same shape: **a claim about the environment,
> written as if it were a claim about the code.**
>
> **What broke.** `tests/test_objective_offsets.py` (added in `062db16`) calls
> `locate_centroid` and `locate_by_correlation`, which defer `import cv2` into
> the function body. The module therefore imports and collects fine, and seven
> tests then raise `ModuleNotFoundError` on a runner that installed only
> `requirements.txt` + `requirements-mcp.txt`. CI was red on `062db16`,
> `fcec864` and `f85cc74` before anyone read the log.
>
> **Why nobody saw it here.** `~/venvs/auto_microscope` has all four stacks,
> including `opencv-python` and `pymmcore_plus`. The suite cannot fail locally
> for a reason that is *an absence*, so the difference between this venv and
> the runner was invisible by construction.
>
> ⚠ **No instrument time, no physics.** This is entirely about the test
> environment. Nothing here changes a gate, a measurement or a hardware path.

## 1. The seven tests skip instead of erroring

`requires_cv2`, a `skipif` on `importlib.util.find_spec("cv2")`, on the five
test functions (seven items, one is parametrized three ways) that reach a
deferred OpenCV import.

**Marked individually rather than by a module-level `importorskip`**, which was
the alternative and would have been one line. That file's fifteen tests are two
different things: the localisation half needs OpenCV, and the offset arithmetic
and loop-closure half — *the half that can be wrong without anyone noticing,
which is why the file says it exists* — needs nothing but numpy. Skipping the
module would have taken eight good tests off CI to fix seven bad ones.

`requirements-analysis.txt` had asserted "Nothing the test suite collects
imports cv2, so CI does not need this file." True when written, false from
`062db16` on. The **conclusion** survived — CI still does not need the file —
so what was corrected is the reason, not the decision: the header now says
seven tests reach it, that they skip, and that an unmarked new one turns CI red
again.

## 2. `tests/ci_emulate.py` — the absences, on demand

Off unless `PYTEST_CI_EMULATE` is set. `ci` hides `cv2` and `pymmcore_plus`
(what the badge runs); `base` also hides `mcp` (`requirements.txt` alone).

It hides each name **two ways at once**, and both are load-bearing:

| Mechanism | Without it |
|---|---|
| A `meta_path` finder that raises on a real `import cv2` | the failure is not reproduced — an unmarked test still passes locally, and the next `062db16` ships |
| `importlib.util.find_spec` answering `None` for the same names | `requires_cv2` cannot decide to skip: a raising finder propagates out of the `skipif` condition and turns a skip into a collection error, a third behaviour belonging to neither environment |

An unrecognised value raises rather than running normally, because a typo in
the variable name would otherwise hand someone a green full run they believed
was an emulated one.

## 3. What a timing test may assert

`test_sleep_until_really_blocks_on_the_real_clock` has now been loosened twice
by the same shared macOS runner and never by a change to `runtime/ticker.py`:

| Date | Measured | Bound before | Response |
|---|---|---|---|
| earlier | 107.8 ms deschedule | 20 ms, unconditional | best-of-five |
| **2026-09-07** | **24.9 ms, best of five** | 20 ms, best-of-five | tight bound only where the machine is owned; 250 ms ceiling on `CI` |

The second measurement **falsifies the sentence the first one added** — *"a
runner that cannot manage it once in five tries is genuinely not usable for
timing"*. That was a claim about GitHub's scheduler dressed as an assertion
about this code. `sleep_until`'s guarantees (it does not return before the
deadline; the overshoot it reports is never negative) are asserted every time,
on any machine. How closely the OS lets it land is a property of the machine,
and on a machine this repository does not own it is not evidence about
anything. 250 ms still fails a spin that never spins or a deadline computed
against the wrong clock, which is what the test is for.

Precedent, in the same file: `test_real_clock_schedule_does_not_drift` asserted
`19 * dt` until the same runner reached `k=61`, and was fixed by dropping the
machine-dependent assertion rather than by widening it. Widening is the weaker
move and is used here only because the quality number is the whole point of
this particular test.

`ON_SHARED_RUNNER = bool(os.environ.get("CI"))` is the only place in the suite
that asks where it is running, and it **widens a tolerance rather than skipping
an assertion**. If that distinction stops holding, this decision is being
misused.

## 4. The counts, re-measured rather than adjusted

By collecting the suite with each optional stack hidden, 2026-09-07:

| Tier | Tests | In CI |
|---|---|---|
| numpy + pyyaml only (`requirements.txt`) | 1,132 | yes |
| `requirements-mcp.txt` | 30 | yes |
| `requirements-micromanager.txt` | 56 | no — separate workflow |
| `requirements-analysis.txt` (OpenCV) | 7 | no — skip |
| **total** | **1,225** | **1,162 run** |

The README had said 866 for the first row. It also said 1,213/1,150 before
these twelve tests for `ci_emulate` itself.

**One number is OS-dependent**, which the README now states: `1162 passed, 10
skipped` is Windows. macOS and Linux report `1161 passed, 11 skipped`, because
`test_runtime_shmview.py` skips one Windows-only segment-lifetime test there.

## Still open

- **Nothing checks that a new test cannot reach a deferred optional import.**
  `ci_emulate` makes it *findable* in one command; it does not make it
  automatic. A CI job that runs `PYTEST_CI_EMULATE=base` would, and does not
  exist.
- **The 250 ms ceiling is a guess, not a measurement.** It is ~10× the worst
  best-of-five seen. If a runner ever trips it, the right response is to read
  the number before widening it again.
- **Whether `CI` is set by every runner this repo will ever use.** Where it is
  not, the tight bound applies and the flake returns — with a clearer message
  than before, but returns.
