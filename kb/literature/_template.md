---
id: <quantity>-<subject>                 # = filename without .md, e.g. bleach-photons-alexafluor488
quantity: "data/fluorophores.yaml > AlexaFluor488 > bleach_photons"
question: "<the question this entry answers, and under what conditions the
  published value was obtained>"
source: literature
citation: "<authors>. <title>. <journal> <volume>(<issue>):<pages>, <year>."
doi: "10.<...>"
filed_by: <initials>
date: <YYYY-MM-DD>                       # when this was filed, not when published
confidence: low                          # low unless independent papers agree
evidence: assumed                        # never `measured` — this tier cannot advance a verdict
gate: <G__ or null>
scope: "<which samples/channels/objectives this may be applied to>"
applies_to_systems: [current, current-laser, current-spectra, current-aura]
measured_on: "<instrument, dye lot, buffer, oxygen scavenger, temperature,
  irradiance, duty cycle — whatever the paper states. Say `not stated` where it
  does not; that absence is itself a transfer condition>"
review_after: <YYYY-MM-DD>
supersedes: null
superseded_by_measurement: null           # -> kb/calibrations/<file> once measured here
---

## Verdict

**<value> <units>** (<uncertainty, or the range across sources>).

State the number first, then how it was arrived at. If the paper reports a
different quantity and this one is derived — e.g. `bleach_photons = Φ_fl / Φ_b`
— show the arithmetic with the inputs, so a reader can redo it when a better
Φ_fl arrives.

## What it supplies

- **Field:** `<data/*.yaml path>`
- **Gate:** `<G__>` in `<module>/checks.py`
- **Before this entry:** `<what the gate returned — usually BLOCKED, and on what
  finding>`
- **After:** `<what it returns now — a computed margin, and roughly what value>`

Name the gate's behaviour on both sides. An entry that does not change what a
gate can do is not worth filing.

## Transfer conditions

What has to hold for this number to apply to this instrument:

1. <condition — e.g. irradiance stays below the regime where the published
   measurement was taken>
2. <condition — e.g. same buffer / oxygen scavenger, or none in either case>

What is known **not** to hold:

1. <difference — e.g. a different dye lot, a different immersion medium, live
   cells versus buffer>

If this list is empty, it has not been thought about. There is always at least
one difference between a paper's conditions and this microscope.

## Why this does not advance a verdict

`evidence: assumed`, so `advances` stays `NO` regardless of the margin
([04 §1](../../docs/04-decision-engine.md)). This entry lets `<G__>` compute
instead of refuse; it does not claim anyone measured `<quantity>` on this
instrument. The replacement is <the local measurement named in §1 of
Falsification conditions below>.

## Falsification conditions

1. **A local measurement of `<quantity>`.** <How: which script in
   `calibration/`, or what apparatus. This is not a hypothetical — it is the
   reason this entry is temporary.> On arrival: move the value to
   `kb/calibrations/<file>`, set `superseded_by_measurement:` above, and the gate
   becomes able to advance.
2. <a later paper, or a measurement in the same conditions, disagreeing by more
   than <threshold> — say what threshold matters for the gate's verdict, not what
   is merely statistically different>
3. <a condition in Transfer conditions turning out to be false>

## Related

- `<module>/checks.py` — the gate that consumes this
- `<data/*.yaml>` — the registry field
- `kb/decisions/<file>` — the decision that scoped this quantity, if any
- `kb/expertise/<file>` — a prior that bears on it, if any
