---
id: 2026-09-10-lens-8-becomes-a-reporting-section
question: "What is left of lens 8 once every quantity it gated on is either measured during the run, owned by another lens, or unmeasurable in principle?"
date: 2026-09-10
status: current
corrects: []
---

# 2026-09-10 · Lens 8 becomes a reporting section

**Decided by KH**, in three instructions on the same day, each about one check:

> **G32** evaporation · 밀봉 또는 증발률 · 밀봉은 선언 가능 · **"인포로 남겨두자."**
>
> **G31** sedimentation · **"침강 상승 속도와 평형에 도달하는 시간 정도만 계산하고
> 인포로 남겨두자."**
>
> **vibration** · **"삭제, 현미경의 모든 부속이 진동 테이블 위에 있어서 카메라와
> 샘플이 함께 흔들림. 구분 할 방법이 없음."**

With G28/G29/G30 already gone
([`2026-09-10-drift-is-not-a-design-element.md`](2026-09-10-drift-is-not-a-design-element.md)),
that empties the lens of gates. **Lens 8 is the second reporting section**,
after lens 5 the same day: every check INFO, `LIMITS` empty,
`status: REPORT`, `feasibility: "N/A"`, `advances: None`, `reporting_only: True`.

## Why each one stopped judging — three different reasons

**G31 was answering the wrong question, twice over.** It compared the distance a
population settles over the whole acquisition against the depth of field, and
the margin came out **0.00 for every real bead**: 5 µm polystyrene in water
moves 41 µm/min against the 100x oil's 0.375 µm. The gate said INFEASIBLE to
every experiment this instrument runs, including the ones that work.

- **A trapped bead does not settle.** `StabilitySetup` has no `trapped` field,
  so the free-settling velocity was applied to a bead held in a trap. Its axial
  question is answered by comparing the two axial **forces**, which
  `trapping.goa.trap_force` already returns together:

  | | |
  |---|---|
  | buoyant weight, 5 µm polystyrene in water | **0.032 pN** |
  | trap axial force, 100 mW, effective NA 1.333 | **9.56 pN** |
  | ratio | **0.34%** (3.4% at 10 mW; equal at 0.34 mW) |

  **Gravity is 0.34% of the axial force the trap is already applying**, so it
  is not what decides where the bead sits — and free settling at 41 µm/min is
  simply not the same question.

  ⚠ **This entry first argued the point through an axial stiffness, and twice
  got it wrong:** once by closing it with an unsourced `κ_xy/5` ratio (my own
  rule of thumb, withdrawn 2026-09-10), then by declaring the question
  unanswerable without that stiffness. KH supplied the route above on
  2026-09-11 and it needs no stiffness at all. One caveat on it, recorded
  because it is the tempting shortcut: **radiation pressure × the bead's
  cross-section is a bound, not the force** — the bead intercepts the whole
  beam, so the product collapses to `n·P/c` = 445 pN at 100 mW, which is total
  momentum transfer (Q = 1) against the model's Q_z of 0.0215, a factor of 47.
- **The free-settling case already belongs to lens 4.** G19 was rebuilt on a
  total-sedimentation premise hours earlier: it assumes the population has
  reached the floor and computes the areal density there. Two lenses were
  charging one fact against different thresholds.

What replaced it is the pair of numbers that premise needs and nobody was
producing: **the velocity, and the time until it is over.** `t_eq = h/|v|`.
5 µm bead, 100 µm chamber → 41 µm/min, floor in **2.4 min**, 25× inside a 60 min
run. When `t_eq > duration` the report says the population is **still in
transit** and G19's settled-state premise does not hold yet — the one sentence
this check exists to hand lens 4. The equilibrium is the floor and not a
suspended profile because for a micron-scale bead the sedimentation–diffusion
balance sits far below one bead diameter; no Péclet model is claimed here.

**G32 stopped because of an asymmetry in its inputs: sealing is declarable, an
evaporation rate is not.** A sealed chamber is a fact about the plan and it
answers the question outright. Unsealed, the only honest input is a weighed
rate, which is something you do around a run rather than while designing one.
The old gate covered that by returning a **stand-in margin of 0.5** — a number
invented to represent "not quantified", which graded HARD and blocked
`advances` on an acquisition nobody had measured anything about. That was the
last invented number in this lens. The report now says
`UNQUANTIFIED -- not small`, which is the distinction the 0.5 was destroying.

**`vibration` was deleted outright, and on physics rather than timing.** The
check existed to refuse a silent pass: *"a quiet pass on this line is an
absence of evidence, not evidence of stability."* Its premise was that no
measurement channel existed. This session argued the opposite — that the drag
calibration **is** the channel, since a coverslip-stuck bead's PSD in the same
520 fps stream would show mechanical lines riding on the Lorentzian, and
`data/particles.yaml` records 8 of 21 beads immobilised on the glass. **That
argument was wrong**, and KH's answer says why: every part of this microscope
sits on the same isolation table, so **the camera and the sample move
together.** An image can only show their *relative* motion, and common-mode
motion of a rigid assembly cancels out of it. There is no channel to build.

**Keep the asymmetry with drift.** Drift is differential expansion in the
mechanical path between objective and holder, so it does *not* cancel and a
stuck-bead fiducial does see it. That is exactly why `drift_budget` survives and
vibration does not, and it is the distinction to state whenever either comes up.

## One question answered, one model named

KH, on the replacement for G29/G30: *"여전히 DOF_nm가 시간에 따라 드리프트가
일어나는 경우를 상정한거네?"*

**Yes, and the output now says so.** `drift_budget` divides the depth of field
by the duration, which presumes drift is **monotonic and linear for the whole
run**. `drift.py` already recorded why that is the optimistic reading — thermal
drift is worst in the first hour after the enclosure is disturbed, so a real run
front-loads it and can blow the quoted rate early while averaging under it — and
it is pessimistic in the other direction for any run that re-establishes focus
part way through, where the window that matters is the interval between
re-focuses. The message now carries `ASSUMES DRIFT IS MONOTONIC FOR THE WHOLE
RUN`, `assumes_monotonic_drift: True` goes into `metrics`, and the action says
to recompute on the re-focus interval. The two *inputs* are planning inputs; the
monotonicity is a model, and it was being presented as "one division, no
threshold" — which was true of the threshold and false of the model.

## What it costs

**The unconditional drift entry no longer blocks anything.** While lens 8 still
graded, that entry pinned `evidence` to `assumed` and so pinned `advances` to
`False` — that was the mechanism by which drift stopped a long acquisition from
advancing. A reporting section's `advances` is `None`, so there is nothing left
to stop. The entry stays, and `evidence` is still reported, so a *reader* sees
that the bias is uncorrected.

**And lens 8 now feeds lens 6 nothing at all.** G23's ledger collects
`bias`-kind findings; lens 8 has none left. Its drift and evaporation notes live
in `assumed_inputs`, and `validity/gate.py::_evaluate_one` does not read
upstream `assumed_inputs` — only the multi-quantity aggregation at line 307
unions them, and that is across lens 6's *own* per-quantity verdicts. So **the
drift and evaporation biases currently reach a human reader and no gate.**

That gap is **pinned by a test rather than hidden**
(`test_lens_6_can_review_this_lens_verdict`) and is **lens 6's to close, not
lens 8's**: lens 6 is reviewed last by E2, and reaching into it from here is the
coupling that review exists to check. `CLAUDE.md` E4 now says lens 8's ledger
row reads `unevaluated` even when the lens runs. The `mechanical-env` and
`measurement-validity` briefs both instruct carrying the biases across by hand
until it is closed.

## What changed

- `stability/checks.py` — `check_sedimentation` rewritten (velocity, direction,
  `time_to_equilibrium_min`, `equilibrium_before_end`); `check_evaporation`
  rewritten (three INFO branches, no stand-in margin); `check_vibration`
  excised; both `LIMITS` entries removed, so `LIMITS == {}`; `_ok` now returns
  severity `"info"`, which is what makes `check_convening` visible; a `"N/A"`
  entry added to `GRADE_NOTES` so `feasibility_note` is not an empty string
- `stability/gate.py` — `Verdict.status` is `REPORT`; `passed` is
  `status == "REPORT"`; `advances` returns `None`; `to_dict` carries
  `reporting_only: True`; `evaluate` asserts nothing is gradeable and sets
  `feasibility = "N/A"`; **Phase 0 now blocks on `duration` alone** —
  `missing.depth_of_field` and `missing.settling_inputs` are gone, which is
  what finally dissolves the all-or-nothing short-circuit this review opened on
- `stability/setup.py` — `vibration_measured` removed; the comment in its place
  records the common-mode argument
- `stability/cli.py` — the `--vibration-measured` flag gone; **the margins block
  removed** (every entry would be MAX_MARGIN with a full bar, which on this lens
  reads as "the run is stable"); `advances: n/a (reporting section ...)`; exit
  code keys on `status == "REPORT"`
- `stability/__init__.py` — the module docstring leads with the reporting-section
  banner
- `docs/04`, `docs/05`, `CLAUDE.md`, `README.md` — G31/G32 shown as reports;
  `CLAUDE.md` gains a bullet distinguishing the two reporting sections and an E4
  addendum; README's "7 judging lenses" → 6
- `.claude/agents/mechanical-env.md` — reporting-section banner; G31, G32 and
  the vibration sections rewritten; Phase 2's aggregation rules replaced (there
  is no grade to read); the worked example's vibration finding and
  `assumed_inputs` block corrected; the gaps section re-dated and the drift and
  vibration entries resolved
- `.claude/agents/measurement-validity.md` — G31/G32 ledger rows struck through
  with what to do instead; the "lens 8 is invisible" item now states the
  two-channel gap and assigns it
- `validity/setup.py` — `stability.evaporation` in `UNCORRECTABLE` marked
  **dormant** alongside `stability.lateral_drift`; the wording is kept because a
  reviewer carrying the bias across by hand should use it
- `tests/test_advances_rule.py` — `stability` off `LENS_MODULES` and onto a new
  `REPORTING_MODULES`; the photo-specific exception tests parametrised over
  both; a test asserting the two sections **got there for different reasons**
- `tests/test_stability_gate.py` — 36 tests; the G31/G32 blocks rewritten around
  velocity, the equilibrium clock and the absence of a stand-in margin
- `tests/test_gate_registry.py` — snapshot kinds, empty `LIMITS`, the
  unnumbered-check set

1230 passed, 11 skipped, identical under `PYTEST_CI_EMULATE=ci`.

## Open, deliberately

- **G31/G32 keep their numbers while grading nothing.** Lens 5 vacated
  `G21`/`G22` when it became a reporting section; lens 8 did not, because the
  instruction was "leave it as info", not "remove it". The inconsistency is
  visible rather than resolved — a naming decision for KH.
- **No `trapped` field, so the force comparison above is prose in an action
  rather than a number the lens computes.** Both numbers exist in code —
  `trapping.goa.trap_force` returns the axial force, and the buoyant weight is
  radius and density contrast — so wiring it is a cross-lens hand-off (7 → 8)
  rather than new physics. Named here so the next person does not re-derive it.
- **Lens 6 receives nothing from lens 8** — above.

## Falsifier

Somebody finds a measurement lens 8 could make *before* a run that changes the
plan. Then it is a judging lens again and this decision is too broad. The two
candidates worth naming: **stage repeatability**, which is measurable in
principle (the closed-loop piezo reports position, so log commanded against
reported over repeated moves) and would gate any acquisition that revisits a
position; and **a vibration path that bypasses the table** — a cable or tube
bridging it to the floor or enclosure, or a table not actually floating — which
breaks the rigid-body assumption and so escapes the common-mode argument. Note
what that second one would need: not a measurement, but a demonstration that
the assembly is *not* rigid.

The narrower falsifier for G31: if a run's focal plane sits near the chamber
floor, settling brings particles *into* the field rather than out of it, and the
velocity this reports is the rate at which the count rises. The report gives a
direction and a clock and deliberately does not say which way the consequence
points. If that turns out to be decidable from the plan — from a commanded z
against the coverslip datum — then the sign is a design element and the report
is leaving something on the table.
