---
id: 2026-09-11-per-lens-check-addresses
question: "Should the committee's gates keep a flat G1-G32 numbering after ten of the numbers went vacant?"
date: 2026-09-11
status: current
corrects: []
---

# 2026-09-11 · Flat gate numbers become per-lens addresses

**Decided by KH**, deferred from earlier in the review — *"렌즈 점검을 모두
완료한 뒤에 다시 번호를 매길거야"* — and settled once every lens had been
reviewed. Offered four schemes, KH chose **per-lens addressing**.

```
L<lens>.<n>        lens number from docs/01 §4, then the check's position in it
```

**43 checks, all addressed.** 19 `hard` · 6 `bias` · 3 `soft` can fail; 15
`info` only report.

| lens | addresses | | lens | addresses |
|---|---|---|---|---|
| 1 optics | L1.1–L1.7 | | 5 photo | L5.1–L5.3 |
| 2 detection | L2.1–L2.5 | | 6 validity | L6.1–L6.4 |
| 3 compute | L3.1–L3.7 | | 7 trapping | L7.1–L7.6 |
| 4 sample | L4.1–L4.7 | | 8 stability | L8.1–L8.4 |

## Why, and the reason is structural rather than cosmetic

**A flat number space made a gate number a global resource.** Removing lens 5's
gates punched holes that lenses 6 and 8 then had to document, and by the end of
this review the space held **ten vacancies in thirty-two** and **five gates
with letter suffixes** — `G12a–c`, `G13a–d`, `G16b/c`, `G14a–c`, `G3b` — each
letter added because the next integer was already spoken for. Per-lens
addressing makes a removal local and absorbs the letters into ordinary numbers.

Two consequences that matter more than the tidiness:

**1 · Eleven checks got a documented identity for the first time**, two of them
`hard`. They had always run, and a proposal could be stopped by something that
appeared in no table anywhere. They were left unnumbered deliberately, on a
real objection: *a number would advertise it as a gate*, and
`stability.drift_budget` and `trapping.temperature_basis` cannot fail. The
address scheme dissolves that objection, because **an address is a location,
not a claim that something can fail** — and the `kind` printed beside it is
what says that. `L8.4 info` cannot be misread as a gate.

**2 · The address lives in the check's docstring, not in its list position.**
So inserting or reordering a check does not renumber its neighbours; a new
check takes the next free number in its lens.
`tests/test_gate_registry.py::test_every_check_has_the_address_it_is_supposed_to`
holds the map, so a drift fails a test rather than quietly renaming a gate
somebody cited.

## What was rejected, and why

- **Flat dense renumber `G1…G22`.** Tidiest single sequence, but it leaves the
  cause in place: the next removal punches a hole again. Same rewrite cost.
- **Keep the numbers, fix only the three inconsistencies.** Cheapest by far
  (~20 mentions), and it leaves ten vacancies and five letter suffixes.
- **Dual scheme: G-numbers as historical IDs, addresses as working labels.**
  No rewrite at all, but two names for one thing.

## Ten numbers are retired, not translated

`G10` `G11` `G18` `G20` `G21` `G22` `G26` `G28` `G29` `G30`. Each named a gate
that no longer exists, so **a reference to `G20` points at something that was
removed, and the reason is the useful part.** They are not reused and not
mapped to any address. `docs/04` carries the table.

Note two of them did not vanish so much as change status: `G21` and `G22` are
now the `L5.1` and `L5.2` **reports**, because lens 5 stopped judging on
2026-09-10. The retired table says so rather than mapping them, since a
sentence written about G21-the-gate is not true of L5.1-the-report.

## `kb/` keeps the old numbers, on purpose

432 of the ~1,780 G-number mentions are in `kb/`, across 37 files, and they
stay. Those entries are **dated records** — one is *named*
`2026-09-09-g20-saturation-removed.md` — so rewriting them would falsify the
history they exist to hold. The bridge is `docs/04`'s `was` column plus its
retired table, and the `(was Gxx)` note each carried-forward check keeps in its
own docstring. **New writing uses addresses.**

868 references were translated across 76 files: `docs/`, `.claude/agents/`, the
eight lens packages, `tests/`, `README.md`, `CLAUDE.md`, `config/`,
`calibration/`.

## Three tests retired with the flat space

`test_every_gate_number_in_code_is_documented`,
`test_vacant_numbers_are_claimed_by_nothing`,
`test_optics_numbers_only_g3b_in_code` and
`test_the_set_of_unnumbered_checks_does_not_grow_silently` all existed to
police a flat space: that a claimed number appeared in `docs/04`, that a vacant
one was claimed by nothing, that lens 1 had exactly one number in code while
`G1`–`G4` lived only in the document, and that the unnumbered set did not grow.
**Every one of those conditions is now structurally impossible**, so they were
replaced rather than adapted:

- `test_every_check_has_the_address_it_is_supposed_to` (per lens)
- `test_every_check_in_every_lens_is_addressed` — and the count is 43
- `test_addresses_are_dense_and_lens_numbered`
- `test_no_retired_gate_number_is_reused_or_translated`
- `test_the_old_numbers_are_still_recoverable_from_the_code`

That last one is the one to keep: it asserts that every carried-forward address
still says which gate it was, so a reader arriving from `kb/` or from a commit
message lands in the right place.

## One caveat the old table hid

`docs/04` used to give `G12`, `G13` and `G14` as **single rows covering their
sub-letters**, so seven compute checks and three trapping checks shared three
rows. Splitting them was part of this change, and it is why the table grew from
22 rows to 43 without anything being added to the code.

1256 passed, 11 skipped, identical under `PYTEST_CI_EMULATE=ci`.

## Falsifier

A check moves between lenses. Its address would have to change, which is
exactly what the scheme promises not to do — and unlike the flat space there is
no way to keep the old label, because the label encodes the lens. If that
happens, the honest move is to retire the old address the way the ten G-numbers
were retired, not to translate it.

The weaker falsifier: if lens numbering itself changes. `docs/01 §4` fixes 1–8
and the pipeline rework (planned 2026-09-11) could renumber the lenses, at
which point every address moves at once. Worth knowing before that work starts;
the mapping test is what would catch it.
