---
id: 2026-09-15-phase-0-was-all-or-nothing
question: "A gate BLOCKs on one missing number. Should it discard the checks that did not need it?"
date: 2026-09-15
status: current
---

# 2026-09-15 · A block is not a blackout

**No.** Every gate's Phase 0 returned `BLOCKED` and threw away every check
result, including the results of checks whose own inputs were all present.
**All nine now run what they can.**

And converting the last seven surfaced the thing that matters most in this
entry: **a block was hiding a genuine `hard` stop on the repository's own
brief.** See §The stop nobody could see.

## Who found it

All three judgment subagents, independently, the first time they were convened
on a real proposal
([`2026-09-15-stage-2-the-judgment-seam.md`](2026-09-15-stage-2-the-judgment-seam.md)):

| Lens | What it lost |
|---|---|
| **4** | *"`check_depth_window` does not read `imaging_depth_um` at all … Phase 0 being all-or-nothing suppressed the one check that would have told the operator which depths are allowed."* |
| **5** | *"`trap_heating` requires NOTHING and reads only `setup.trap_on` … a check whose entire purpose is to stop an unowned risk vanishing was suppressed by an unrelated missing number, on a proposal where its trigger is live."* |
| **6** | *"The same defect appears in lens 5 and in MY OWN gate. **Three gates in one run, same mechanism**: an architectural defect, not three incidents."* |

Lens 4's is D6 inverted — refusing for want of a value instead of reporting
where the verdict changes. Lens 5's is darker: the check exists **only** to
name an ungated risk (E3, lens 7 silent on heating is not heating cleared), and
it was silenced by a number it does not read.

## What changed

The BLOCKED return gains a **Phase 0b**: the checks whose `requires` are a
subset of `available_facts` run, and their results go into `findings`,
`margins` and `metrics`.

**The status does not move.** `BLOCKED`, `confidence: none`, `feasibility`
unchanged — `UNKNOWN` in lens 4, and `UNKNOWN` rather than `N/A` in lens 5,
because *a report that could not be written is not the same as one that was*
and only Phase 2 may claim `N/A`. `advances` stays `False` (lens 4) and `None`
(lens 5). Nothing advances, no feasibility is claimed; a runnable check's
result is reported instead of thrown away.

`_as_findings` is factored so Phase 0b and Phase 2 share one definition. **A
partial run reported in a different shape from a full one is a partial run
nobody can compare.**

## What it recovered on the real proposal

`config/briefs/active-microrheology.yaml`, lens 4, still `BLOCKED` on
`missing.imaging_depth`:

> **Usable focal depth 14.1 to 160.0 µm above the coverslip**: floor from L4.4
> near-wall drag (a = 2.50 µm), ceiling from L4.2 free working distance. Work
> near the top of the band — the wall term falls as 1/h and nothing else in the
> window prefers the bottom.

and

> **Index-matched**: mismatch 0.0000 between water and the sample medium.
> Mechanical z travel IS optical depth here — no conversion, and no
> depth-dependent mismatch aberration.

*"Tell me a depth"* became *"pick one between 14.1 and 160, and work near the
top."* The second is the one **positive** statement supporting the 40× WI
departure, and it had been discarded on every run.

Lens 5 recovered `perturbation.total_dose` and
`perturbation.trap_heating_unowned` — the trap-heating handoff now reports
itself on every trapped run instead of needing a subagent to carry it by hand.

## The finding underneath the fix: `requires` understates what a check reads

**This is not a mechanical edit, and that is the useful part.** Letting the
runnable checks run surfaced two crashes, one per lens, and the two needed
*different* answers.

### Lens 4 · `depth_window` declared `()` and had a requirement

Four of this lens's checks carry `requires=()` with comments saying a missing
input *"must skip the check, not BLOCK the gate"* — they return
`evaluated=False`. `depth_window` carried the same `()` and called
`free_working_distance_um`, which raises on a `wd_um` of `None`.

**The empty tuple was conflating two claims**: *"I handle my own absences"* and
*"I have no requirements."* Fixed by declaring the requirement it has:
`("working_distance",)`. With no working distance the check is now skipped
rather than crashed.

### Lens 5 · `light_driving` needs a fact `requires` cannot express

It divided by `light_driving_threshold_w_cm2` without declaring it. But the
threshold is needed **only when `photoresponsive` is True**, and declaring it
unconditionally would block a sample confirmed *not* photoresponsive, which
needs no threshold at all. A static tuple cannot say that. So the check handles
its own absence and returns `evaluated=False` — lens 4's convention, applied
where the tuple cannot reach.

**Both defects were unreachable before.** Every path into either check went
through a gate that had already returned, which is why the type checker, the
suite and `committee reconcile` were all silent. **Phase 0 was not hiding a
missing feature; it was hiding two wrong declarations.**

## A second-order effect worth knowing

`designer/judgment.py`'s `_skipped_checks` derives the "did not run" list from
`verdict.margins` against the registry, so Phase 0b **shrank it to the truth**.
Lens 4's skipped list went from eight entries to one (`working_distance`,
which needs the depth the lens is blocked on); lens 5's from three to one
(`light_driving`, which needs the irradiance it is blocked on).

In both cases the single remaining entry is the check the block is *actually
about*. That is the list doing what it was built for rather than restating the
block eight times.

## The stop nobody could see

`config/briefs/active-microrheology.yaml` now **stops in tier 1**:

```
velocity velocity.time_base: a `hard` gate at m < 1 stops the run
                             and returns a revision (§2 precedence level 1)
```

L9.1, at m = 0.00. The brief's own text says it — *"L9.1 FAILS on every real
configuration … the distance half of the scale is corroborated to 0.24 %; the
TIME half has never been checked"* — and CLAUDE.md's memory of this repository
says it. **Nothing enforced it**, because:

- Phase 0 discarded `velocity.time_base` along with every other check;
- and the `missing.*` findings that survived carry **`kind: None`**, so
  `designer.run._first_hard_failure` — which filters on `kind == "hard"` —
  found nothing to stop on.

So the lens read `BLOCKED`, the run continued, and every later lens deliberated
past a hard failure that §2 precedence level 1 says stops everything. **Two
mechanisms had to agree for it to hide, and both were incidental.**

The corrected reading is also the more useful one. "BLOCKED on five missing
inputs" is a list of questions; "L9.1 at m = 0.00" is one **R2 measurement**
somebody must make — *drive a known distance at a known commanded velocity and
time it independently* — and until it exists this proposal cannot proceed at
all. That is a different instruction.

## The third and fourth `requires` repairs

Converting the last seven produced two more, and the third is a **new kind**:

### Lens 7 · a check that refuses by *raising*

`trapping.goa` raises `ValueError` outside the ray-optics regime — *"a GOA
force number here would be fiction; use Rayleigh scattering or GLMT instead."*
Four checks go through it (`confinement`, `trap_depth`, `sampling`,
`power_window`) and none declared it. The gate already computed the regime for
its own `missing.regime` blocking finding, so **the fact existed and was simply
not in the vocabulary**; every path into those four went through a gate that had
already returned.

Repaired as lens 4's was — `available_facts` gains `regime.ray_optics` and the
four checks declare it. Note the precedent in that same registry: `confinement`
and `trap_depth` had **empty** `requires` until 2026-09-10 and were *"grading a
stiffness derived from a placeholder dial -> mW map. Two hard gates on
fiction."* This is the third round of the same audit on the same six checks.

### Lens 7 · and one return that correctly gets no Phase 0b

`evaluate`'s first BLOCKED return is a `ValueError` handler for a dial above the
calibrated range (5–80 %; 100 % over-ranged the meter). **No Phase 0b there**,
deliberately: every check either takes `stiffness` or `laser.calibrated`, both
of which come from the power, or is one of the two audited `requires=()`
checks, which would report the same thing at any dial. *A dial above the
calibrated range is not a partial answer; it is a request the curve cannot
serve at all.*

**Lens 6's own gate was among the nine**, and it named the defect in itself.

## And one gap Phase 0b does not close

A check that **ran and passed quietly** is in neither of
`designer/judgment.py`'s two subject sources: `_own_findings` takes only
findings (severity ≠ `ok`) and `_skipped_checks` only non-runs. Lens 6 named
this about itself — *"`validity.bias_ledger` at 10.0 and
`validity.pixel_calibration` at 10.0 appear in `margins` and in `metrics` but
emitted no finding, so the two checks where my judgement differs most from the
gate's had to go into `unevaluated` with `code: null`"* — and its example is
the strongest available: an **empty** bias ledger reports full headroom, while
lens 4 had identified an uncorrectable bias on the intended quantity in prose.

Phase 0b makes more checks run and therefore makes *more* of them pass quietly.
So it widens this gap slightly rather than narrowing it.

**Closed the same day, and in the two places it turned out to live** →
[`2026-09-15-an-empty-ledger-is-not-a-clean-one.md`](2026-09-15-an-empty-ledger-is-not-a-clean-one.md).

## ⚠ This stales the plan it was found from

`kb/plans/2026-09-15-active-microrheology.{md,yaml}` records the first full
committee run, and **it no longer describes what this code produces.** Checked
rather than assumed: the three judgment verdicts now draw 10 and 4 refusals
against the post-Phase-0b packets.

The cause is precise and is not a defect. A skipped check appears as a subject
under its **registered** code (`trap_heating`); a check that runs appears under
its **emitted** code (`perturbation.trap_heating_unowned`). The agents ruled on
the registered codes, because that is what they were handed. So every recovered
check is now an `invented-subject` in the old verdict and a `silence` in the
new packet — both correct.

⚠ **And after the last seven gates, the plan is stale in a second and larger
way**: that brief no longer reaches stage 2 at all. It stops in tier 1 on L9.1,
so there are no packets, no judgment halves, and the plan's three `judged` rows
describe a stage that cannot now run on it. Re-emitting it is not a re-pin and
not a re-convening — **it needs the velocity time base measured first.**

**Left as is rather than hand-edited.** The plan is `emit`'s output and
patching a generated file to match code it was not generated from is the one
thing the `brief.sha256` pin exists to make visible. Refreshing it means
re-convening lenses 4 · 5 · 6 against the new packets; the plan in git is the
record of the run that happened, which is what a dated `kb/plans/` entry is
for. **Nothing downstream may read it as current**, and the seven unconverted
gates mean it would stale again anyway when they land.

## Falsifying condition

**The taxonomy already needed a third entry, so assume a fourth.** The
falsifier as first written said "if a third audit produces a third kind of
repair, the two patterns above are not the taxonomy" — and the trapping audit,
run within the hour, produced exactly that: a check that refuses by raising,
on a fact the gate computes and the vocabulary omits. Three kinds now:

| | repair |
|---|---|
| declares `()` and has a requirement | declare it (`depth_window`, and lens 7's four) |
| needs a fact only *conditionally* | the check handles its own absence (`light_driving`) |
| refuses by **raising** on a computed condition | put the condition in `available_facts` |

⚠ The second is the one with no mechanism behind it. `requires` is a static
tuple and cannot say "only when `photoresponsive` is True", so that repair
rests on a convention — four of lens 4's checks and one of lens 5's — that
nothing enforces. **A check adopting it silently and then not handling its
absence would crash exactly as `depth_window` did**, and only a Phase-0b run
with that input missing would notice.

**And if a recovered check is ever read as a partial clearance, the status
guard is insufficient.** The defence today is that `status`, `feasibility`,
`confidence` and `advances` all stay where a block puts them — but `margins` is
now populated on a BLOCKED verdict, and lens 6 has already shown that a margin
read without its context reads as headroom. The signature to watch: a plan or a
reader quoting a Phase-0b margin as evidence the lens was satisfied.
