# MHS — a note, not a plan

> Anthropic previewed the **Model Hardware Standard** on 2026-08-27, after this
> project's hardware layer was written. It is kept out of the README on purpose.
> The scientific-validity layer here is the part that should stay useful
> whichever hardware abstraction wins, and rewriting the project's identity
> around a standard announced two days ago would be positioning rather than
> engineering. Independent convergence is the more interesting observation, and
> recording it here is enough. If an integration actually happens, this file is
> where it gets designed.

## What MHS is, and where it would touch this

**[Model Hardware Standard](https://www.anthropic.com/news/model-hardware-standard-research-preview),
research preview, announced 2026-08-27.** A shared specification for agents to
operate physical devices: `read` / `write` primitives, **devices discoverable
in a standard format** so that agents and instruments find each other *"without
needing a bespoke 'translator' program"*, **device-level safety limits enforced
in the driver**, model-agnostic and reachable over MCP.

It lands on three things here at once. This repository *is* three bespoke
translators — pymmcore-plus, a 28-command TCP surface, a vendor DLL — plus
[`hardware/orchestrator.py`](../hardware/orchestrator.py) gluing them onto one
clock, which is item 1. Standard-format discovery would put a self-describing
device on **rung 1** of the discovery ladder and retire the
`strings`-over-a-DLL rung for anything that adopts it
([scope](../kb/decisions/2026-08-29-device-discovery-scope.md)). And safety
limits declared *in the driver* are item 3's reviewer expressed one layer
down — complementary rather than redundant: MHS would enforce *this axis
cannot exceed this travel*, while the reviewer still decides *this script
should not be run at all*.

**What it would not fix, which is most of what is blocking today.** Not one
named blocker above disappears: Nikon still does not document the LUN-F's DAC
word format, the Tweez GUI still owns the camera exclusively and its TCP set
still has no camera command, the DMD's vendor package is still pinned to MM
interface v71, and `power_at_sample_mw` still needs a power meter. **A
standard makes an integration cheap; it does not document an undocumented
protocol, and it does not perform a measurement.** It also moves only *how* a
device is reached, never *whether the setting is a good idea* — the 32 gates
sit above any transport and are unaffected either way.

So the decision criterion, rather than an open-ended look: evaluate when the
preview is reachable or the standard is open-sourced **and** at least one
device on this bench has a driver. Otherwise writing MHS drivers for three
instruments ourselves is the same integration work with an extra specification
to satisfy — and none of the vendors here (Nikon, Photometrics, Aresis,
Prior/Queensgate, Mightex) is among the announced partners, though Danaher and
MBF Bioscience are, which is microscopy-adjacent. **The zero-cost move
meanwhile is to keep the swap cheap**, and the shape is already right: one
driver per file, an orchestrator that opens no device, and a read/write split
whose write side is already gated by `allow_write` · `allow_motion` ·
`allow_laser`.

---
