---
id: 2026-09-15-the-brief-was-wrong-about-the-dye
question: "The brief's own gap text said ATTO647N has no extinction coefficient. Does it?"
date: 2026-09-15
status: current
---

# 2026-09-15 · The brief was wrong about the dye, and right about the conclusion

**It has one.** `data/fluorophores.yaml > ATTO647N` carries
`ext_coeff_M1cm1: 150000`, `quantum_yield: 0.65` and `lifetime_ns: 3.5`.

Found by **lens 5**, convened on this brief for the first time on 2026-09-15
and reporting it unprompted as a D12 item — *prior analysis is a source, and
verifying its arithmetic is part of treating it as one.* It checked three
claims in one gap's text. Two were wrong and the third was nearer the truth
than a flat denial.

## The text as it stood

`config/briefs/active-microrheology.yaml > gaps[light_driving_threshold_w_cm2]`,
written 2026-09-13:

> **Per-dye**, and empty for every proprietary bead colourant here. **This is
> the missing input that made lens 5 a reporting section.**
> ⚠ AND IT IS BOTH ARMS, not only the dim one. Checked 2026-09-13 against
> `data/fluorophores.yaml`: Dragon Green has neither ext_coeff nor quantum
> yield, and **ATTO647N has a quantum yield (0.65) but NO ext_coeff either.**
> So the absolute photon budget is uncomputable for the probe as well as the
> tracer, and every SNR number this proposal produces is relative.

Note that it says *"Checked 2026-09-13 against data/fluorophores.yaml"*. The
file has not changed since. **A claim that names its source and misreads it is
harder to catch than one with no source at all** — the citation is what makes
it look settled.

## The three claims

### 1 · "Per-dye" — wrong. It is per-sample.

`photo/setup.py` declares `light_driving_threshold_w_cm2` inside the
sample-photoresponse block, beside `photoresponsive`, and its own comment says
*"Sample-specific and not derivable."* Its home is `kb/samples/`, which does
not exist.

This is not pedantry about a field's owner. A **radical scavenger in the
buffer** moves the threshold without moving any dye constant, and that is one
of the two reasons the operator gave for demoting this lens
([`2026-09-10-lens-5-becomes-a-reporting-section.md`](2026-09-10-lens-5-becomes-a-reporting-section.md)).
Filed as per-dye, the gap points at the wrong resolver: it reads as a
literature lookup when it is a question about the preparation.

### 2 · "ATTO647N has NO ext_coeff either" — wrong, and the conclusion survives anyway

| | ext_coeff | quantum yield | lifetime | `verified` |
|---|---|---|---|---|
| **ATTO647N** | **150 000** | **0.65** | **3.5 ns** | `false` |
| **DragonGreen** | — | — | — | `false` |

DragonGreen is the genuinely empty one, and its entry says so in its own words:
a Bangs proprietary bead dye, those three published nowhere, and FITC values
must not be substituted.

**The conclusion is still right and its reason moves**, which is the part worth
carrying forward. The absolute photon budget is uncomputable on both arms — but
for the probe the missing input is not a dye constant, it is the **irradiance**,
because `kb/calibrations/illumination-power.yaml` records no illuminated area at
40×.

That difference is not cosmetic, because the two gaps have different **ranks**:

| | rank | resolver | action |
|---|---|---|---|
| `illuminated_area_um2__at_40x` | **R2** | measurable, unmeasured | establish the field at 40× |
| a per-dye constant for a proprietary colourant | **R3** | nobody | recorded as ungated |

Attributing the probe arm's blockage to R3 filed a measurable thing as an
unmeasurable one. An R2 goes on the calibration queue; an R3 is a recorded
absence. **The wrong reason for a right conclusion cost the queue an entry.**

⚠ `verified: false` on ATTO647N still matters, for a different question: the
emission *curve* is a reconstruction from a peak and a FWHM, which is what
[the L1.5 entry](2026-09-15-l1-5-explained-nothing.md)'s falsifier rests on.
"Has an extinction coefficient" and "has a measured spectrum" are two claims and
this entry only settles the first.

### 3 · "This is the missing input that made lens 5 a reporting section" — nearer than a denial

Lens 5 reported this as simply false. It is not quite. The 2026-09-10 entry
records **both**:

- the operator's own two reasons — *mitigations the irradiance cannot see*
  (the scavenger), and *absent sample information, which is the normal state*;
- and, separately, that the lens *"had already been hollowed out"*, because
  **G10 and G20 were both keyed to per-dye constants empty for every dye** and
  went on 2026-09-09.

So the empty constants **retired two gates**; the operator's two reasons
**decided the demotion**. The brief compressed two steps into one. Recorded
here at that resolution rather than corrected to the opposite error.

## What no version of the gap said

The dye constants **do** reach this lens, and are then unread. Verified
2026-09-15:

```
dye.ext_coeff, dye.quantum_yield  ->  IlluminationSetup.resolved_emitted_per_s
                                  ->  available_facts() adds "emitted_rate"
```

and no entry in `photo/checks.py`'s `CHECKS` names `emitted_rate` in its
`requires` — `light_driving` asks for `irradiance`, `total_dose` and
`trap_heating` for nothing. **Computed, declared, and unread.**

That is a dead fact rather than a wrong one, so it breaks nothing today. It is
worth knowing because it is the shape a registry drifts into, and because
anyone reading `available_facts` would reasonably assume something consumes
what it declares.

## Why

**A brief is a source and is treated as one**, which is the whole basis of
`Fact` being a triple rather than a number. The corollary is D12: a source's
arithmetic gets checked, including when the source is the operator's own
earlier reasoning. Nothing in this repository had checked this brief's prose
against the file it cites, because the brief is an *input* — the gates read its
values and never its `why`.

**And the checking came from a subagent rather than from code**, which is the
part to notice. `designer/judgment.py` validates a judgment verdict nine ways
and validates the brief zero ways; the gaps' `why` fields are unreachable by any
test. A judgment lens reading its own inputs sceptically is the only mechanism
that would ever have caught this, and it caught it on the first run.

## Falsifying condition

**If the corrected text is itself unchecked, this entry is the same failure one
generation on.** Every claim above names a file and a key, and the three
verifications were run rather than recalled — but no test asserts any of them,
and the brief's `why` fields remain unreachable by the suite. The concrete
exposure: if `data/fluorophores.yaml > ATTO647N` later loses `ext_coeff_M1cm1`
(a correction from a measured curve, say), this entry becomes wrong silently and
`tests/` will pass.

A test that pinned a dye constant would be the wrong fix — it would freeze a
value the file exists to own. The right one is narrower and not written here:
**a brief's `why` should be able to cite a `file > key` in a form something can
resolve**, so a citation that no longer reads as claimed is a failure rather
than prose.
