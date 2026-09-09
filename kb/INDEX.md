# kb/INDEX.md

**Generated. Do not edit by hand.**
`python -m knowledge.cli write` rebuilds it from each file's
frontmatter; `tests/test_kb_index.py` fails when the two disagree.

Pointers only -- id, date, the question the entry answers, and what has
superseded or corrected it since. **No value, conclusion or quotation is
repeated here**, so a line in this file is never a citation: open the
entry and cite that (docs/09 §7). The `question` lines are restatements
of each file's own title and Request/Context section, not new claims.

## `kb/systems/` — 6 entries

What this instrument is, as measured.

- **[current](systems/current.md)** · living
  What devices, objectives, filters, cameras and calibrations does this instrument actually have, and which of those are measured?
- **[PyTool-RUN-FIRST](systems/PyTool-RUN-FIRST.md)** · 2026-08-27 · runbook
  How do you ask the Tweez 300 embedded Python what its API is, in one session at the microscope PC?
- **[aresis-support-email-draft](systems/aresis-support-email-draft.md)** · 2026-08-27 · draft
  What would this project ask Aresis support for, about the embedded-Python node API?
- **[piezo-superuser-RUN-FIRST](systems/piezo-superuser-RUN-FIRST.md)** · 2026-08-27 · runbook
  How do you get the NPC-D piezo to report its whole command set at super-user level, in one session at the microscope PC?
- **[dualcam-config-corrections-pending](systems/dualcam-config-corrections-pending.md)** · 2026-09-05
  What is wrong with config/micromanager/DMD_dualcam_LUNF.cfg, and what is the live device state under it, as observed on 2026-09-05
- **[dualcam-sorting-session-brief](systems/dualcam-sorting-session-brief.md)** · 2026-09-05
  How should a fresh session pick up the dual-camera + optical-tweezers particle-sorting work without re-deriving what 2026-09-05 already established

## `kb/expertise/` — 8 entries

Durable expert judgment. Each carries a `Why` and a falsifier.

- **[current-laser-green-band-single-slot](expertise/current-laser-green-band-single-slot.md)** · 2026-08-10
  On the current-laser scope (LUN-F-XL + CSU-W1), can two dyes excited at 488nm and emitting in the 500-530nm band be seen simultaneously as distinguishable channels
- **[immersion-media-in-use](expertise/immersion-media-in-use.md)** · 2026-08-12
  Which immersion media are actually in use on the current nosepiece, and what refractive index should the optics code use for each
- **[sample-medium-refractive-index](expertise/sample-medium-refractive-index.md)** · 2026-08-12
  What refractive index should be assumed for the sample medium when the experiment does not state one
- **[oil-objective-trapping-in-water](expertise/oil-objective-trapping-in-water.md)** · 2026-08-18
  Can the oil-immersion objectives trap particles in an aqueous sample, and does their higher design NA buy a stronger trap
- **[coverslip-thickness-in-use](expertise/coverslip-thickness-in-use.md)** · 2026-08-20
  What coverslip thickness does this lab mount on, and does it match what the objectives are corrected for
- **[sample-mount-geometry](expertise/sample-mount-geometry.md)** · 2026-08-20
  How are this lab's samples mounted, and what does that geometry decide for lens 4
- **[imaging-priority-hierarchy](expertise/imaging-priority-hierarchy.md)** · 2026-09-07
  When a proposal cannot satisfy spatial resolution, image quality, time resolution and light intensity at once, which one yields
- **[microrheology-standard-conditions](expertise/microrheology-standard-conditions.md)** · 2026-09-07
  What conditions does a microrheology run on this instrument default to, and which of them are choices rather than constants

## `kb/decisions/` — 23 entries

Dated design and scope choices, in the order they were made.

- **[2026-08-10-labeling-and-laser-recommend](decisions/2026-08-10-labeling-and-laser-recommend.md)** · 2026-08-10
  How should a dye-and-laser recommendation loop be built for this instrument, and what did implementing it find wrong in the filter and light-source records?
- **[2026-08-10_fitc-particle-yoyo1-dna-2color](decisions/2026-08-10_fitc-particle-yoyo1-dna-2color.md)** · 2026-08-10
  Can FITC-coated particles and YOYO-1-labelled DNA be imaged as two distinguishable channels in one frame on the current-laser scope?
- **[2026-08-12-ram-buffer-detour-for-disk-bandwidth](decisions/2026-08-12-ram-buffer-detour-for-disk-bandwidth.md)** · 2026-08-12 · proposed not run
  Can a dual-Kinetix acquisition that exceeds the disk write bandwidth be rescued by acquiring to RAM first and flushing afterwards?
- **[2026-08-19-lens-3-hardening](decisions/2026-08-19-lens-3-hardening.md)** · 2026-08-19
  What does lens 3 hold fixed after hardening -- one stream per camera -- and where does the frame rate it budgets against come from?
- **[2026-08-19-lens-4-scope](decisions/2026-08-19-lens-4-scope.md)** · 2026-08-19
  What will the sample-geometry lens model, and what is deliberately outside it?
- **[2026-08-19-lens-5-hardening](decisions/2026-08-19-lens-5-hardening.md)** · 2026-08-19
  What question was lens 5 not asking, and where does its excitation rate k_ex come from?
- **[2026-08-19-lens-7-scope](decisions/2026-08-19-lens-7-scope.md)** · 2026-08-19
  What will the optical-trapping lens model, and what is deliberately outside it?
- **[2026-08-26-microscope-config-control](decisions/2026-08-26-microscope-config-control.md)** · 2026-08-26
  How does this repository read and write Micro-Manager device state safely, and what did building that surface find wrong in the configs?
- **[2026-08-26-parallel-control-architecture](decisions/2026-08-26-parallel-control-architecture.md)** · 2026-08-26 · superseded in part by [2026-08-27-optional-subsystems-one-timeline](decisions/2026-08-27-optional-subsystems-one-timeline.md) · corrected by [2026-08-27-tweezers-first-light-measured-limits](decisions/2026-08-27-tweezers-first-light-measured-limits.md)
  Can the microscope, the tweezers and the piezo be driven from one program at once, and what is each operation actually able to do?
- **[2026-08-26-piezo-waveform-generator](decisions/2026-08-26-piezo-waveform-generator.md)** · 2026-08-26 · superseded in part by [2026-08-27-piezo-first-light-measured-limits](decisions/2026-08-27-piezo-first-light-measured-limits.md)
  Does the NPC-D piezo have a hardware waveform generator, and can this repository drive the stage from it?
- **[2026-08-26-tweezers-pattern-vs-direct](decisions/2026-08-26-tweezers-pattern-vs-direct.md)** · 2026-08-26 · superseded in part by [2026-08-27-tweezers-first-light-measured-limits](decisions/2026-08-27-tweezers-first-light-measured-limits.md)
  Should the traps be driven by direct TCP commands or by generated `.tpf` pattern files?
- **[2026-08-27-optional-subsystems-one-timeline](decisions/2026-08-27-optional-subsystems-one-timeline.md)** · 2026-08-27
  How does one timeline stay correct when not every subsystem is switched on, and how are three clocks anchored to it?
- **[2026-08-27-piezo-first-light-measured-limits](decisions/2026-08-27-piezo-first-light-measured-limits.md)** · 2026-08-27
  What did the NPC-D piezo do when it was driven from this repository for the first time, and what did the record have wrong?
- **[2026-08-27-tweezers-first-light-measured-limits](decisions/2026-08-27-tweezers-first-light-measured-limits.md)** · 2026-08-27
  What can each tweezers control surface actually do, measured against the live Tweez 300 GUI rather than read out of the manual?
- **[2026-08-29-device-discovery-scope](decisions/2026-08-29-device-discovery-scope.md)** · 2026-08-29
  What may a device fact be learned from, and which discovery routes are ruled in or out?
- **[2026-08-31-mcp-hardware-server-scope](decisions/2026-08-31-mcp-hardware-server-scope.md)** · 2026-08-31
  What does the MCP server expose, and why the two hardware paths rather than the eight committee lenses?
- **[2026-09-02-lunf-first-light-measured-limits](decisions/2026-09-02-lunf-first-light-measured-limits.md)** · 2026-09-02
  What did the LUN-F combiner answer when driven from this repository, and why is the analogue-output route dead?
- **[2026-09-03-three-subsystems-first-light](decisions/2026-09-03-three-subsystems-first-light.md)** · 2026-09-03
  What did the instrument say back when trap, piezo and camera were driven on one timeline for the first time?
- **[2026-09-04-closed-loop-trapping-measured](decisions/2026-09-04-closed-loop-trapping-measured.md)** · 2026-09-04
  What can a live tracker hand the optical trap, and how well does a detected particle end up where it was commanded?
- **[2026-09-05-runtime-primitives-and-gpu-scope](decisions/2026-09-05-runtime-primitives-and-gpu-scope.md)** · 2026-09-05
  Which real-time primitives were brought in from the bacteria stack, and where should GPU work run?
- **[2026-09-07-ci-environment-and-timing-bounds](decisions/2026-09-07-ci-environment-and-timing-bounds.md)** · 2026-09-07
  Why did CI go red on three commits that did not cause it, and what may a timing test assert?
- **[2026-09-07-dmd-on-v71-and-blue-flip](decisions/2026-09-07-dmd-on-v71-and-blue-flip.md)** · 2026-09-07
  Does the DMD load from this repository, and why can the blue camera image flip not live in the `.cfg`?
- **[2026-09-07-realtime-tracking-gui-scope](decisions/2026-09-07-realtime-tracking-gui-scope.md)** · 2026-09-07 · scoped not built
  What would a real-time particle-tracking GUI show, and why can the display and the measurement not be the same stream?

## `kb/literature/` — 1 entries

Published values nobody here has measured.

- **[literature-index](literature/README.md)** · living, since 2026-08-28 · index
  What published values are filed here, and what may a literature value be used for that a measurement may not?

## `kb/sessions/` — 2 entries

The day's narrative.

- **[sessions-index](sessions/README.md)** · living, since 2026-09-07 · index
  What happened on each working day, and where does each running thread stand?
- **[2026-09-07](sessions/2026-09-07.md)** · 2026-09-07
  Why was the microrheology attempt abandoned without acquiring data, and what did the failure establish?

## `kb/calibrations/` — not indexed here

Measured constants, as `.yaml` and one `.txt` rather than prose, so
they carry no frontmatter to generate a line from. Each one opens with
a header comment naming the command that produced it and the gate that
consumes it, which is the same information a line here would carry --
so listing them would be the duplication this file exists to avoid.
