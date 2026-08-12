# 2026-08-10 · Filter- and laser-based labeling/laser recommendation loop

> The decision-log format in `docs/02 §9` (request/proposal/actual result) is meant
> for **experiment execution results**. This entry records a session that designed
> and implemented a tool rather than an experiment, so the format is bent
> accordingly — instead of "settings actually used" and "result", it records "what
> was implemented" and "bugs found". The purpose is the same: keep the next person
> (agents included) from repeating what was learned here.

## Request

"I want to build a recommendation loop for appropriate labeling and lasers for the
system, based on the filter and laser information." The scope was made concrete in
the conversation that followed:
1. Unlike the dichroic, a cube's excitation and emission are individually
   replaceable units
2. Obtain the actual light path per light source (laser/SpectraIII/Aura/DiaLamp/
   optical tweezers)
3. Recognize the dual-camera (Kinetix_red/blue) split
4. **Prefer a single light source** — a workflow that shows candidates per light
   source and lets a human choose

## What was implemented

| File | Role |
|---|---|
| `optics/recommend.py` | `screen()` scores a single candidate · `recommend_labels()` per-line ranking · `recommend_panel()` simultaneous multicolor panel · `compare_sources()` comparison across light sources |
| `config/scopes/current-laser.yaml` | CSU-W1 + LUN-F-XL laser path profile |
| `config/scopes/current-spectra.yaml` | SpectraIII (LightEngine) widefield path |
| `config/scopes/current-aura.yaml` | Aura widefield path |
| `optics/components.py :: Element.as_reflected()` | a view that treats a beamsplitter's reflected side like the transmitted side (for dual camera) |
| `optics/build.py` | supports `{"ref": name, "side": "reflect"}` in filter specifications |
| CLI `python -m optics.cli recommend <scope> [--panel] [--dyes] [--lines]` | |
| CLI `python -m optics.cli sources <scope>... [--dyes] [--lines]` | shows the best panel per light source side by side, **does not choose automatically** |
| `kb/systems/current.md > light_paths` | 4 light sources + the optical tweezers path, with unconfirmed items collected under `known_gaps` |

## Core design decisions and their basis

**`gate.evaluate()` is not used as-is; the four checks (`check_excitation` etc.)
are called directly.** Phase 0 returns BLOCKED immediately if the objective NA and
camera specs are not complete, and in this lab neither NA nor the camera is
settled yet (`kb/systems/current.md`). But those four checks themselves read
neither NA nor read noise/full well, so once you separate "may this channel be
imaged today" (the gate's job) from "does this dye suit this line" (recommend's
job), there was no reason not to compute what is computable now.

**Ranking is by "brightness" (excitation efficiency × emission collection) first,
not by margin; margin is only a hard gate.** Sorting by margin (the minimum across
checks) came first, but since the whole filter registry uses the same
`blocking_od: 6` default, a real case arose where "weakly excited but coincidentally
high blocking margin because the filter sits far away" beat "well excited but
slightly lower margin because the filter sits close" (EGFP got pushed out of first
place at 488nm). Changed so that margin passes anything whose grade is not
INFEASIBLE (<0.2, `checks.GRADES`), and within that set, sorting is by brightness —
which also fits this project's grading philosophy ("HARD means you can proceed",
`docs/05` §3).

**One scope file = one light source.** "Prefer a single light source" already holds
with no code change — `recommend_panel` only uses the lines within one scope, so
splitting scopes per light source makes it impossible for a panel to mix sources.
`compare_sources()` computes each scope separately and only lists them; it **does
not choose**. Which light source suits the sample (need for sectioning,
photobleaching, other reservations, etc.) is an area where this tool has no basis
to judge (`docs/01` principle 5), so it is handed to the human.

**Beamsplitter reflected side = `Element.as_reflected()`.** `Channel.emission`
always reads `.transmission` only, but the dual-camera splitter sends the reflected
side to one of the cameras. Instead of a new field or a change to the `Channel`
structure, the approach taken was to build "a new `Element` with reflectance placed
in the transmittance slot" and insert it — this touches none of the existing code
paths and is expressible in data (YAML) alone (consistent with the `docs/08` §6
philosophy).

## Four bugs found and fixed

**All of them are the "computed with confidence, but the truth was the exact
opposite" type** — precisely the failure mode the `compute-never-infer` principle
exists to prevent.

1. **`Di01-T405/488/568/647` reflection/transmission inverted** (`data/filters.yaml`).
   With `kind: multiband` and the notch reflection bands placed in the top-level
   `bands:`, the code computed "passes only at the 4 laser lines, blocks everything
   else at 6 OD" — the exact opposite of reality (only the 4 lines reflect,
   everything else transmits broadband). Every channel on the laser path came out
   with a fictitious collection≈0. Fixed by splitting them out under a
   `reflection:` subkey.
2. **`Channel.stokes_headroom_nm()` was not looking at the source spectrum**
   (`optics/path.py`). Because a single dichroic reflects 4 laser lines at once,
   the element's "region it can pass" was mistaken for the excitation band — so
   whichever line you used, it showed a "240nm-wide excitation band" and every dye
   got a fictitious spectral-overlap verdict. Fixed to multiply in the source
   spectrum the same way `excitation_blocking_od` does.
3. **Brightness-ignoring ranking** (`optics/recommend.py`, see "Core design
   decisions" above).
4. **`FilterTurret2` "all six slots empty" was wrong** (`kb/systems/current.md`).
   There is in fact a NIR dichroic for coupling in the optical tweezers (OT).
   Corrected from user dictation.

What they share: all three had **an assumption filled in as "this is probably right"
that turned out to be wrong in exactly the opposite direction.** This kind of thing
is only caught by checking at the bench, so regressions were pinned down with tests
(`tests/test_optics.py`, `tests/test_recommend.py`).

## What remains (see `kb/systems/current.md > light_paths > known_gaps`)

- Exact band values for `CSUW1-Dichroic`
- Which of `EM1`/`EM2` sits in front of `Kinetix_red` (the configuration is
  identical so it does not affect calculation — this is for confirming the bench
  wiring)
- Slot number and part name for the `FilterTurret2` NIR dichroic
- Whether the transmitted-light condenser is registered in MM/NIS
- **Not yet put into the `SpectraIII`/`Aura` scopes**: `LappMainBranch1` (it only
  changes light-level distribution; being spectrally irrelevant it was never needed
  for this screening) and `CSUW1-Dichroic` (bands unconfirmed, so still assumed
  neutral)
- **Not yet built**: an optical tweezers (Trap) scope — only mapped as far as the
  sample, and since it was concluded to be unrelated to the detection path, it is
  likely not a target of this recommend loop at all

## Candidate next steps

- Putting the vendor curves for EM1-525/36 and EM1-705/72 into `data/spectra/` is
  expected to lift both channels from HARD to COMFORTABLE (blocking requirement
  7→5 OD)
- Add the Kinetix datasheet QE curve to `data/detectors.yaml`
- After the objective NA is settled, final confirmation via `optics.cli check`
  (this recommend loop is screening, not a final verdict)
