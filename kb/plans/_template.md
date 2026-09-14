---
# One hardware run, written BEFORE it happens -> docs/05 §6 stage 5.
# Copy to kb/plans/YYYY-MM-DD-<slug>.md and fill in. Check it with
#   python -m knowledge.cli plan-check
# which refuses a plan whose shape a skill would misread.
#
# When the run happens this entry gains `Setting actually used`, `Outcome` and
# `What was learned`, and graduates into kb/decisions/ -- the format is the one
# in docs/02 §9 and this file is its first half.
id: YYYY-MM-DD-slug
question: "What is this run for, as a question"
date: YYYY-MM-DD
status: planned                 # planned | run | abandoned
subsystems: [microscope]        # microscope · tweezers · piezo
                                # (hardware.orchestrator.SUBSYSTEMS; microscope
                                #  is always in the roster)
---

# YYYY-MM-DD · Title

**Machine half:** `kb/plans/YYYY-MM-DD-<slug>.yaml`, same slug — one run, one
name, two readers. It carries only what a check reads; everything else is in
this file, in Preconditions and Sequence.

## Request

The goal in the operator's words, before it is turned into settings. If it was
stated in conversation, quote it.

## Proposed setting + rationale

The committee's output. **Every number here came from a gate or from `kb/`;
none of it was originated in this file** (CLAUDE.md rule 2). Cite the entry, not
`kb/INDEX.md`.

## Committee verdict

| Lens | Verdict | Deciding gate | m | Evidence |
|---|---|---|---|---|
| 1 optics |  |  |  |  |
| 2 detection |  |  |  |  |
| 3 compute |  |  |  |  |
| 4 sample |  |  |  |  |
| 5 photo |  |  |  |  |
| 6 validity |  |  |  |  |

**Not evaluated.** `unevaluated` is not `cleared` (CLAUDE.md §3), so name every
lens that was not convened and why. Lens 7 with no trap and lens 8 under ~30 min
are absences, not passes (CLAUDE.md §2 E4). If every lens ran, say that here
instead — the section may not be silent.

- …

## Preconditions

Checked before anything moves. Each one refuses the run on its own; none of them
is a formality.

- [ ] … — *checked by:* …

### Instrument state no gate reads

**This is where the settings the committee never sees are set** (KH,
2026-09-14). The operator's parameter inventory lists about thirty of them, and
they are deliberately absent from `plan.yaml`: a device property no check reads
would make the plan tier 2 and end its portability (CLAUDE.md §2), and the plan
interpreter leaves every parameter no check reads at its current value — so if
it is not written here, **nobody sets it**.

Each row is set by a person and confirmed by something *observed*. Delete the
blocks this run does not touch; do not delete a block to make the list shorter.

| Block | Set | Confirmed by |
|---|---|---|
| light path · L100 / eyepiece / camera port | | |
| filter turret 1 (lower) · turret 2 (upper) | | |
| condenser · 0 ND / 1 block / open | | |
| dia lamp · level, and on only while the camera is on | | |
| LAPP branch on/off · CSU on/off · disk in/out | | |
| confocal disk speed · aperture size | | ⚠ neither is in the KB (R2) |
| PFS · z-drive | | |
| camera fan speed · trigger mode · shutter mode · clear cycle | | |
| tweezers · trap positions, active, strength, breakpoints, pattern | | |
| piezo · initial x/y/z, lock, time unit, distance unit, channel↔axis | | |

**Objective at load time is not on this list and not an imaging decision.**
Load with a low-magnification objective in place, whatever the measurement
wants (SAFETY §2, README item 10, CLAUDE.md §2 E7).

## Sequence

[SAFETY §8](../../SAFETY.md) is the standing setup order and is **not** repeated
here. This table is only what is specific to this run.

**A return code is not a confirmation** (SAFETY §0): on the tweezers, six wrong
states and success are the same byte. Every row's confirmation is something
*observed* — a bead that moved, a frame that changed, a readback from a device
that has one.

| # | Subsystem | Action | Flag required | Confirmed by |
|---:|---|---|---|---|
| 1 |  |  |  |  |

## Stop conditions

What aborts the run, and **what state it leaves the instrument in**. An abort
that leaves the laser armed and the stage mid-travel is not a stop condition.

- …
