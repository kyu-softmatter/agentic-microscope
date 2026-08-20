# 2026-08-19 · Lens 5 hardening — the unasked question, and where k_ex comes from

> Not an experiment log. Same shape as
> [`2026-08-19-lens-7-scope.md`](2026-08-19-lens-7-scope.md): `docs/02 §9`
> assumes a recommendation that was actually run, and there is no gate output
> here. This entry exists so the next reader — human or agent — knows which of
> these were decisions and which are still open.

## Context

Lens 5 (`photo/`) has been implemented since 2026-08-12: G10 photobleaching,
G20 saturation / triplet shelving, G21 light-driving, G22 total dose, plus the
trap-heating ownership notice. A review on 2026-08-19 walked the lens end to end
against its own documentation and turned up eight items. Three were fixed
(below); five are recorded as still open.

**Nothing here was executed.** This machine has no runnable Python — `.venv`
points at `C:\Users\Takatori lab\...\python.exe`, which does not exist here — so
`tests/test_photo.py` and `tests/test_photo_gate.py` have not been run against
these changes. Run them on the microscope PC before trusting any of it.

## Decisions

### 1. `photoresponsive` is tri-state, and the unasked state is on the evidence axis

`IlluminationSetup.photoresponsive` was `bool = False`. That default meant a
caller who never asked whether the sample responds to light got G21 passing
with `margin = 10.0` and a message saying the illumination was "treated as
measurement light only" — the gate silent in exactly the case
[`docs/06`](../../docs/06-pitfalls.md) D2 exists for. The accident there is the
unasked question, not a wrong number, and the old default could not tell the
two apart from a confirmed "no".

It is now `bool | None = None` with four distinct behaviours:

| state | meaning | verdict |
|---|---|---|
| `True` + threshold | measured bound in hand | `margin = threshold / irradiance` |
| `True`, no threshold | responds, bound unknown | `BLOCKED` (Phase 0, unchanged) |
| `False` | confirmed inert to this light | passes, `evaluated: true` |
| `None` | **nobody asked** | `warn`, `evaluated: false`, `advances` withheld |

**Why the evidence axis and not Phase 0.** `.claude/agents/photo-perturbation.md`
already specified this ("soften C3 from BLOCKED to WARN, but always flag it"),
and it is the right call: a missing *answer* is not a missing *number*. Bleaching
and saturation can still be judged, so refusing the whole lens would throw away
work it can actually do. Instead the item lands in `assumed_inputs`, which drops
`evidence` to `assumed` and so makes `advances` False by the existing rule. No
new mechanism, and the verdict still cannot advance on silence.

The `None` margin is reported as the ceiling (10.0), following the precedent
`check_total_dose` already set for "not evaluated". **`margin` is the wrong field
to read there** — `evaluated: false` is the one that means something, and the
message says so in words. The alternative, inventing a margin of 1.0 to force a
TIGHT grade, would have been exactly the guessing this project refuses.

Consequence: `photo.cli check` now needs `--not-photoresponsive` to say the
answer out loud. Omitting it is no longer neutral.

### 2. The bare-field excitation chain declares its assumed spectral overlap

Lens 1's `optics.path.Channel.excitation_rate_per_s` weights `σφ` by
`excitation_efficiency() / source_delivery()` — the transmission-weighted mean
of the dye's absorption over the delivered band. `photo.setup`'s local fallback
had no such term, so it computed `σφ` with the overlap silently at 1: the line
treated as though it sat on the absorption peak across its whole width. Real
couplings are well under 1 — ATTO488 (abs peak 500 nm) on this lab's 462–486 nm
green band runs near a half, per
[`config/channels/active-microrheology-probe-tracer.yaml`](../../config/channels/active-microrheology-probe-tracer.yaml).

And `photo.cli` had no `--channel` option at all, so **every CLI run took the
overestimating path**; `from_channel` was unreachable from the command line.

Two changes:

- `IlluminationSetup.excitation_coupling` carries the factor when it is known.
  Absent it, the chain still assumes 1.0 but `excitation_coupling_assumed`
  reports so, which puts it in `assumed_inputs` and withholds `advances`.
- `photo.cli check --channel <yaml> [--channel-name N]` builds through
  `IlluminationSetup.from_channel`, consuming lens 1's rates. It refuses
  `--dye`, `--wavelength-nm`, `--ext-coeff`, `--quantum-yield` and
  `--excitation-coupling` in that mode, because overriding any of them would
  leave the rates inconsistent with the values they were computed from.
  `--bleach-photons` and `--lifetime-ns` stay overridable: neither feeds those
  rates, and the registry has no `bleach_photons` for any dye.

**The bias direction is worth recording, because it is the harmless one.** Too
large a `k_ex` inflates both the excited-state fraction (G20) and the emitted
photon count (G10), so both gates come out *stricter* than the instrument
warrants — false alarms, not false clears. The cost is a wrong instruction
("cut the light"), not a missed perturbation. That is why this was fixed by
declaring the assumption rather than by blocking on it.

### 3. The agent file stops being a second source of truth

`.claude/agents/photo-perturbation.md` still opened with "Status: draft. No code
(pure LLM judgment)" and told the reader to compute C1 and C2 by hand. It was
written 2026-08-11, one day before `photo/` landed. Corrected throughout, with
the substantive fixes being:

- C2 was described as informational, without a G-number, and explicitly as
  something that "cannot enter the overall feasibility grade". It is G20,
  `kind=bias`, and **it does enter the grade.** The file contradicted the code.
- C3 was described as having no G-number. It is G21.
- The Phase 0 list and C2 disagreed with each other about a missing
  `lifetime_ns`: block, or skip the check and note it. The code blocks the whole
  lens; the file now says so and tells the agent not to "skip C2 and carry on".
- The suggested implementation target was `optics/checks.py`. It went to
  `photo/checks.py`.
- "the 14-gate table" → 32.
- The example output invented finding codes (`missing.power_at_sample_mw`,
  `C3 photo_driving`). Replaced with the real ones so they can be grepped.

Also added: a note that this lens has **no `hard` gate**, so `status: FAIL` is
unreachable from inside it — the outcomes are BLOCKED, PASS_WITH_CHANGES, PASS.
That is correct (every check here is `bias` or `info`, and Lens 6 arbitrates
bias findings), but it was nowhere stated, and an agent narrating a FAIL the
gate cannot emit is a real failure mode.

### 4. Stop re-proposing the power measurement

The `missing.power_at_sample` action said "Measure sample-plane power with a
power meter... This is the project's top blocker." Since the 2026-08-19 decision
deferring *all* laser power measurement ([`docs/07`](../../docs/07-roadmap.md)
Phase 0, which explicitly says "do not keep re-proposing it as the immediate
step"), that text put the code at odds with a standing decision.

It now says what is blocked, names the measurement as the eventual fix, notes
the deferral, and states that `BLOCKED` is the honest answer meanwhile. Same
correction in the agent file and in [`docs/05`](../../docs/05-consensus-gate.md)
§Lens 5.

`bleach_photons` is deliberately **not** softened the same way. It is empty for
every dye in the registry, but a literature value would unblock G10 today
without touching the instrument — the cheapest real unlock this lens has, and
not deferred by anything.

## Deliberately not changed

- **A missing `lifetime_ns` still BLOCKs the whole lens**, not just G20. It is
  stricter than the agent file used to imply, and it stays: the alternative is a
  verdict that has quietly dropped a bias gate.
- **`status: FAIL` stays unreachable.** Documented rather than "fixed" — see
  decision 3.
- **`evidence: measured` does not check provenance.** A hand-typed `--power-mw`
  earns `measured` exactly as a registry value would. The agent file sanctions
  this ("you may treat this as measured for this single run"), and with the
  registry empty it is the only way to get an answer at all. But it does sit in
  tension with [`docs/06`](../../docs/06-pitfalls.md) E3 — see open item 3.

## What this leaves as actual Lens 5 work

1. **`bleach_photons` for at least one dye.** G10 has a formula, code and tests,
   and has still never run on a registry entry. Literature value, no instrument
   time.
2. **C4 phototoxicity has no gate and no code.** Absent from the 32-gate table.
   Needs a per-sample dose ceiling; a system-general model is unlikely to exist.
3. **`evidence` has no provenance flag.** Nothing distinguishes a power-meter
   reading from a plausible guess typed at the CLI. `docs/06` E3 says a PASS
   computed from catalog values is not a PASS; today's `measured` cannot tell.
4. **The C5 / D3 scope tension is still unresolved.** `docs/06`'s lens-assignment
   table gives label perturbation to Lens 5; `docs/05`'s "owns" list for Lens 5
   is light-only. The agent file checks it and tags `scope_tension`, which is a
   holding pattern, not an answer.
5. **`kb/samples/` still does not exist.** The tri-state makes the asking
   visible; it does not give the answer anywhere to live. Shared with Lens 4.
6. **Illumination-driven local heating is unimplemented** — needs the medium's
   absorption coefficient, unrecorded. Distinct from trap heating, which is
   ungated by decision (Lens 7).
7. **Committee wiring.** `--channel` closes the Lens 1 → Lens 5 half for the
   excitation chain. Exposure and frame count still come from the user rather
   than from Lens 2's verdict. Phase 3.
8. **`docs/05` §2's gate-kind table still stops at G14.** G10 is in it; G20–G22
   are not, and neither are lens 4/6/8's gates. Out of scope here because
   half-updating a canonical table is worse than leaving it visibly stale.

## What would reopen each decision

| Decision | Reopens if |
|---|---|
| 1 tri-state | `kb/samples/` arrives — then the answer has a home and the default could reasonably come from the sample dossier rather than from the caller |
| 2 coupling | Orchestration lands and Lens 5 always receives a `Channel`. The bare-field path then exists only for what-ifs and tests, and could drop the fallback chain entirely |
| 3 agent file | Any further change to `photo/checks.py` — the file is now specific enough about codes and kinds to go stale again |
| 4 power text | A power-meter session happens. Drop the mW into `data/light_sources.yaml > power_at_sample_mw` and the whole lens flips to computable with no code change |
