---
# frontmatter added 2026-09-09 for kb/INDEX.md. `question` restates this
# file's own title and Request/Context; the link fields read its own
# supersession notes. A retrieval aid, not evidence -- see knowledge/index.py.
id: literature-index
question: "What published values are filed here, and what may a literature value be used for that a measurement may not?"
date: 2026-08-28
living: true
status: index
---

# kb/literature/

Published values that a gate needs and nobody here has measured — filed so they
can be *used* without being mistaken for measurements of this instrument.

One file per quantity per subject. `bleach-photons-alexafluor488.md`, not
`smith-2019.md`: the unit of storage is the number a gate consumes, not the paper
it came out of. One paper supplying three quantities becomes three files, each
citing it. Files beginning with `_` are not entries.

**One entry**, [`lifetime-ns-tritc.md`](lifetime-ns-tritc.md) — TRITC's
fluorescence lifetime, which `G20` was refusing for want of. The schema and the
rules were written first so that it did not have to invent them, and they held:
nothing in the template needed changing to file it.

---

## The rule that defines this tier

**A literature value never sets `evidence: measured`, so it never lets a verdict
advance.**

This repository has two evidence tiers, `measured` and `assumed`, and
[04 §1](../../docs/04-decision-engine.md) makes `advances` conditional on
`measured`. A literature value is `assumed`. What it buys is narrower and still
worth having: a gate that was returning `BLOCKED` for want of an input can
instead *compute*, and report a margin, a bottleneck, and a difficulty grade.

The photo-perturbation lens is still the live case, and it is now a real one
rather than an illustration. `lifetime_ns` was `null` for TRITC, so `G20` could
not tell whether emission was linear in power and the lens refused:

```
TRITC @ 555 nm  153.0 W/cm^2  ->  BLOCKED
feasibility: UNKNOWN   evidence: assumed   confidence: none   advances: NO
    [FAIL] missing.lifetime
```

Supply the number — 2.2 ns, free dye in PBS — and it computes:

```
TRITC @ 555 nm  153.0 W/cm^2  ->  PASS
feasibility: ROUTINE   evidence: assumed   confidence: low   advances: NO

     10.00  perturbation.saturation     ##############################
```

**`advances: NO` beside a margin of 10.00 is the point**, and it is sharper than
the version that used to sit here. That one showed a literature value producing
a margin that said *no*, which is easy to accept. This one produces a margin
that says *yes, comfortably* — and still cannot advance a verdict. A passing
verdict is exactly where a reader is tempted to treat an assumed value as a
measured one.

> **This paragraph illustrated `G10` and `bleach_photons` until 2026-09-16.**
> G10 was removed on 2026-09-09 ([kb/decisions/2026-09-09-g10-photobleaching-removed.md](../decisions/2026-09-09-g10-photobleaching-removed.md))
> and the output above it was hypothetical. The photobleaching arithmetic it
> described is kept in [04 §6](../../docs/04-decision-engine.md), which also
> says why the gate went.

If an entry here ever appears to make a verdict advance, that is a bug in the
gate, not a licence.

## What belongs here, and what does not

**Belongs.** A number a gate consumes, which has no local measurement, whose
published value is specific enough to transfer with stated caveats.
`lifetime_ns` per dye is the worked example: `G20` reads it, five of seventeen
dyes are still missing it, and no instrument here can measure it directly —
that needs time-resolved detection this setup does not have.

> This said `bleach_photons` was the top example, *"empty across the whole
> registry"* and listed by 07 Phase 0 as literature-or-decay-curve. **No gate
> consumes it now** — it went with G10 — and `docs/07-roadmap.md` no longer
> names it. Still empty, and no longer a number anything is waiting on, which
> is the difference between a gap and a hole.

**Does not belong.**

- *Vendor datasheet specs.* Those go straight into `data/*.yaml` with the
  datasheet revision named as `source` — see `data/detectors.yaml > Kinetix22` and
  [`manual/README.md`](../../manual/README.md) on which revision to cite. A
  datasheet is the manufacturer describing the part in hand, not a third party
  describing a different one.
- *Background reading.* If no gate consumes a number from it, it is not knowledge
  this system can act on. Method papers that shape a judgment belong in
  [`kb/expertise/`](../expertise/) as a captured prior, with the paper cited
  inside.
- *A value this lab has measured.* That is [`kb/calibrations/`](../calibrations/),
  and it outranks anything here.

## Transfer is the whole difficulty

[03](../../docs/03-cross-system-transfer.md) is about a past instrument in this
lab not transferring to the current one. A published number is that problem at
its worst: different instrument, different dye lot, buffer, oxygen scavenger,
temperature, illumination spectrum and duty cycle. Photobleaching in particular
is often superlinear in intensity through triplet pathways, so a yield measured at
one irradiance is not a constant.

So `measured_on:` is mandatory, and **Transfer conditions** is a mandatory
section. An entry that cannot say what would have to hold for its number to apply
here is not usable, however good the paper is.

## Every entry is built to be replaced

`kb/expertise/` entries carry a falsifier — the observation that would retire
them. For a literature entry that observation is always available and always the
same shape: **measure the quantity here.** When that happens, the value moves to
`kb/calibrations/`, this file gets `superseded_by_measurement:` filled in, and the
gate it feeds can finally advance.

An entry here is therefore a placeholder with a citation, not a conclusion. It is
also a work list: what sits in this folder is exactly what is worth measuring
next.

---

## Schema

Copy [`_template.md`](_template.md) and fill it in — it carries the frontmatter
and every required section, with a note in each explaining what makes that
section useful rather than decorative. It is the authoritative copy; this file
does not repeat it.

## What each section is for

| Section | Contents |
|---|---|
| `## Verdict` | The number, its units, and its uncertainty. Lead with it. |
| `## What it supplies` | Which registry field, which gate, and what that gate did before this entry existed |
| `## Transfer conditions` | What must hold for the published value to apply to this instrument, and what is known not to hold |
| `## Why this does not advance a verdict` | One or two sentences. Present even though the rule is global, because the next reader will ask |
| `## Falsification conditions` | Numbered, as in `kb/expertise/`. The first is always the local measurement that would replace this |
| `## Related` | Links to the gate's code, the registry file, and any `kb/decisions/` entry that scoped it |
