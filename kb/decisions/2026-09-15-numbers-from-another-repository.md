---
id: 2026-09-15-numbers-from-another-repository
question: "Where does a number computed in another repository live in this knowledge base, and what may it be used for that a measurement may not?"
date: 2026-09-15
status: current
---

# 2026-09-15 · Numbers from another repository

**Decided this session, against a protocol agreed in
[`sim-exp-bridge`](https://github.com/kyu-softmatter/sim-exp-bridge).** Four
rounds of question-and-answer with the Brownian-dynamics agent produced numbers
this repository now depends on. They live in `kb/external/bd/`, they may
motivate a design, and **no gate may clear against them.**

## Request

The simulation agent and this one were being consulted separately and could
silently contradict. A shared repository now carries a question card in each
direction: a claim, the single observable that answers it, the precision needed,
the dimensional primitives, and an assumption declaration. **Neither side's plan
crosses — only the question does**, and each re-derives its own numbers through
its own gates.

That left one thing undecided here: where the other repository's answer comes to
rest, and what citing it licenses.

## Why

**The path has to carry the foreignness, because plans cite by path.** A
frontmatter field does not show at the citation site — a reader following
`../calibrations/foo.md` from a plan sees a calibration. So the namespace is
`kb/external/bd/<thread>.r<N>.md`, and **`kb/calibrations/` is refused
outright**: that directory means "measured on this instrument", and a simulated
`f_c` sitting there would be a lie the path itself tells.

**`may_be_gate_threshold: false` is the default, and the reason is hard rule 3.**
A gate that clears against an imported number emits a margin that reads as
locally measured. Half of that is already prevented: every lens's `advances`
requires `evidence == "measured"`, so an imported input registered in
`_assumed_inputs()` cannot advance a verdict. Nothing stopped a *threshold* from
being imported, and a threshold is what a check refuses against — so the rule is
enforced at the **plan boundary**, where provenance still exists, and not inside
the gates, where an input is a bare float and its origin is unknowable. That is
now mechanical: `knowledge/sidecar.py` refuses a `role: threshold` whose source
points into `kb/external/`.

**Lifecycle is supersession, not deletion.** An import a plan cites graduates
with that plan into `kb/decisions/`, and deleting it dangles a permanent record.
`corrected_by` and `superseded_by` already exist here. The r2 import is the
worked case: r4 withdrew two of its numbers, so it carries `corrected_by` and an
**unedited body** — the correction is a link plus a header note, never a
rewrite, because the body records what was believed when the plan was written.

**One hash per key is not enough, so keys are pinned per round.** The bridge's
manifest holds one value per path, and both a sender's own evolving plan and a
corrected import change hash between rounds. `@r<N>` keys keep every earlier
round's citation verifying. Refreshing an unsuffixed key instead was tried on
the other side and **cascaded** — r4 then needed refreshing, which broke r5 and
r7, which cite r4.

## What it bought, concretely

Four rounds, and the two sides caught errors in each other that neither would
have found alone:

- **BD found ours.** `2*D*t_exp/3` is the free-particle MSD blur term; a trapped
  bead's is `u/3`. Every entry of this plan's `blur on var(x)` column was
  exactly twice too large, and it had already reached the other agent as this
  instrument's own arithmetic.
- **BD found its own, unprompted.** Its `f_c` "recoverable to +1.17 %" was its
  *estimator's* bias, not physics — withdrawn and deliberately **not replaced**.
  A requirement resting on it survived at the same value on a different basis.
- **We found a structural limit neither had stated.** At fixed height the wall's
  whole effect is a scalar on `gamma`, and `k* = k_t d²/kT` carries no drag, so
  all six ladder rungs are one dimensionless run. **No runner can learn a wall
  there** — the gap was being recorded as a missing capability for five rounds
  when it does not expire.
- **A pre-registered falsifier fired.** r1, round one: scatter beyond ~0.4 µm
  once finite `T_obs`, blur and localisation noise are included means the ladder
  does not produce a trapping height. r8 measured 0.433–0.450 µm. The criterion
  was written before the evidence existed, which is the only reason it could
  decide anything.

## What did NOT change, deliberately

**No gate constant moved.** The other side withdrew its own sampling
requirement in favour of this instrument's `G14` and conceded the convention
argument — and `REQUIRED_SAMPLING_RATIO = 10.0` is still 10.0. The number that
came back was **ours**, so what the round established was the *ranking* of the
constraints, not the threshold. A foreign round can motivate a design; it cannot
set a constant that makes a claim about every future experiment.

## Falsifying condition

**This is wrong if an imported number ever has to be a gate threshold for a real
experiment to be possible.** The test is concrete: if a plan is refused, or an
experiment designed worse, purely because a simulated ceiling could not be
enforced by a check, the rule costs more than the disease it prevents and the
honest fix is a margin that inherits foreignness — `m = 1.05 (external-derived)`
— rather than a ban.

It is also wrong if `evidence_class: simulated` ever fails to stop a verdict
advancing. `tests/test_advances_rule.py` is where that shows.

## Open

- **`kb/external/` has no drift check.** An import whose `source_hash` goes
  stale upstream should flag every plan citing it. "Unverifiable" — the upstream
  repository is not on this machine and never on CI — has to be a **third
  state**, not a pass.
- **r7's `gaps[0].kind` is wrong** (`needs_data_transfer`; it is
  `needs_human_action`). The document is sealed and cited, so the correction
  travels in the next round with a `corrects[]` entry.
- **The Lorentzian estimator is unnamed on both sides** after eight rounds, and
  r4 measured that the choice is worth up to +7.9 % on `f_c` — more than every
  declared physics difference except the wall. Until both sides name the fit, an
  agreement on `f_c` between them is uninterpretable at the ~1 % level.
