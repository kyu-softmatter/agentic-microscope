# 2026-08-26 · Tweezers: direct TCP vs generated patterns

> **Decided the same day: `.tpf` patterns** (user, "tpf로 하자"). The concept
> section below is what that decision was made on; the implementation that
> followed it is in "What was built". Execution stays on the microscope PC, so
> the open facts at the bottom are still open — the code reports `BLOCKED` on
> them rather than assuming them.
> Companion to `2026-08-26-microscope-config-control.md` (same session).

## Request

Of the three control surfaces being checked — tweezers patterns, microscope
configuration, piezo pattern generation — this covers the tweezers. Standing
premise from the user: *if Python can drive the hardware directly, a pattern file
is not required.*

## Finding: the premise holds for placement, not for timing

Direct control already works — `TRAP_POSITION <name> <x> <y>` is in
`hardware/optical_tweezers.py` and the whole documented command set is covered.
But the two paths run on different clocks, and that is the whole answer:

| | clock | practical resolution |
|---|---|---|
| direct TCP | host — one socket round trip per move, via GUI → System Manager | ms at best, jitter unbounded and **unmeasured** |
| `.tpf` pattern | hardware — the AOD trap loop advances one point per pass | switching rate, up to 100 kHz |

So a pattern is not an authoring convenience. It is the only way to get (a) a
trajectory whose timing is known, (b) more than one illuminated point per trap —
a light potential landscape, which no single trap position can produce — and
(c) breakpoints, where the trap halts mid-path until released by software or a
hardware trigger.

## Why this lab specifically needs patterns

`config/channels/active-microrheology-probe-tracer.yaml` drives a 5 µm probe on a
bounded random walk at 0–30 µm/s and reads force as
`F = kappa * (x_bead - x_trap)`. That subtraction needs `x_trap(t)` to be known,
and — as that channel file already notes — **the TCP interface has no readout of
any kind**. The command set is write-only: no trap position query, no force, no
trap list. Confirmed against the Command Reference (manual pp. 66–69) this
session; nothing was missing from the existing module.

Which means a TCP-streamed drive gives a trajectory contaminated by host jitter
that cannot be recovered afterwards, because there is nothing to read back
against. A `.tpf` traversed at a fixed switching rate gives an exactly known one.
For an active-microrheology modulus this is a Lens 6 question, not a convenience
question — so **patterns for the drive, direct TCP for setup and quasi-static
placement.**

## What was built

| File | Role |
|---|---|
| `hardware/tweezers_patterns.py` | `.tpf` writer + trap-loop timing model + generators: `circle`, `oscillation`, `raster`, `bounded_random_walk` |
| `hardware/tweezers_drive.py` | spec → `DrivePlan` (timing, slowdown routes, range verdict) → TCP command sequence |
| `config/tweezers/active-microrheology-drive.yaml` | the drive spec for the existing microrheology channel |
| `config/tweezers/run_pattern.py` | `--plan` (offline) · `--write` (emit the `.tpf`) · `--run` (microscope PC, TCP) |
| `tests/test_tweezers_patterns.py` · `tests/test_tweezers_drive.py` | 53 tests; the timing ones reproduce the manual's own worked examples |
| `hardware/optical_tweezers.py` | `load_pattern()` gains a `file_first` switch — see contradiction (1) below |

`plan()` reports rather than decides. With `trapping_range` unrecorded the range
check returns **BLOCKED**, not OK, and `advances` is False — the same idiom the
lens gates use, and the right one here because a pattern outside the calibrated
field is clipped *silently*. The current spec is blocked on exactly the two facts
listed at the bottom, and says so:

    range check   BLOCKED: trapping_range not recorded ...
    advances      NO
      blocked by  range check BLOCKED
      blocked by  the wait_states route needs 422 wait states on trap 'Probe',
                  which TCP cannot set -- give a `project:` template ...

Fill those two in and the same spec plans clean: 2000-point walk, ±7.62 × ±8.00 µm,
507.8 µm per cycle, 422 wait states, 16.9 s cycle, 30.01 µm/s.

`run_pattern.py` never sends `LASER_ON` at any stage — arming a class-4 source
belongs at the GUI with the interlocks in view, not in a generated command list.
`TRAP_ON` is sent, since it only routes an already-on beam.

Pure computation, so it is fully testable offline. The three worked examples on
manual pp. 10–12 come out number for number: 3 traps at 100 kHz → 30 µs/pass →
6 ms per 200-point traversal; 150 Hz → 4 s traversal → 12.5 and 37.5 µm/s on 50
and 150 µm circumferences; and the 5000× slowdown for 5 µm/s. That validates the
arithmetic, **not** that the GUI accepts the files.

**Wait states are not in the TCP command set** — only `BEAM_SET_PARAMS`, which
sets the switching rate globally and therefore changes every pattern-driven trap
at once. `Pattern.dwell(n)` gets the same slowdown by repeating each point n
times in the file, which is per-point instead of per-trap and so strictly more
flexible (slow one arc, leave the rest fast). Cost is file length. If a uniform
per-trap slowdown is what you want and someone is at the GUI anyway, a wait state
is cheaper.

`bounded_random_walk` requires a seed rather than defaulting one. An
unreproducible drive trajectory defeats the reason for using a pattern at all;
the seed is the record, and belongs with the acquisition.

## The slow-drive problem, and the architecture it forces

Worth stating plainly, because it changes the recommended shape of the whole
workflow. The trap loop is fast (100 kHz) and the wanted motion is slow
(0–30 µm/s), so the slowdown factor is inherently ~10³–10⁴. Costed out for the
2000-point walk above at 30 µm/s with two traps in the loop:

| Route | Reachable from Python? | Cost |
|---|---|---|
| A · drop the global switching rate to 236 Hz | yes, `BEAM_SET_PARAMS` | the *other* trap now refreshes at 118 Hz — near the edge of holding anything |
| B · keep 100 kHz, `dwell(423)` | yes, in the `.tpf` | 846,000-point file (~20 MB). Whether the GUI loads that is **untested** |
| C · per-trap wait states = 422 | **no** — GUI only | none; this is the vendor's own answer (manual p. 12 uses 4999) |

So the mechanism the manual intends for exactly this case is the one TCP cannot
set. **`LOAD_PROJECT <file name>` is the way out**: build a project once in the
GUI with the traps and their wait states configured, save it, and have Python
load it and then do everything else. Proposed division of labour:

- **GUI, once, saved as a project template** — trap creation, wait states, repeat
  enable/count, breakpoint Enable/Release bits.
- **Python, per experiment** — `LOAD_PROJECT`, generate and `LOAD_PATTERN` the
  `.tpf`, `TRAP_ASSIGN_PATTERN`, then position / strength / scale / rotation, and
  `GROUP_TRAPS_START_REPEAT` / `TRAP_PATT_RELEASE_BP` to run it.

That keeps per-experiment variation in Python (which is the point) while leaving
the handful of GUI-only properties in a file that does not change between runs.
Route B stays useful where a *non-uniform* slowdown is wanted — dwelling on one
arc of a path and not the rest — which wait states cannot express at all.

## Magnification and calibration — asked 2026-08-26, answered from the manual

**No, magnification is not settable over TCP.** The command set (pp. 66–69) has
no calibration or magnification command of any kind. Magnification is set by an
interactive GUI procedure: drag a scale line across a graticule image and type
the known distance in µm (pp. 37–38). `TRAP_PATT_SCALE` *is* over TCP, but that
scales a pattern about its trap origin — it is not the optical calibration.

There are **two** separate calibrations, and both are objective-dependent:

| | what it maps | how | invalidated by |
|---|---|---|---|
| **GUI calibration** (pp. 35–38) | Beam Position: LCS↔ICS (rotation+translation+scale); Magnification: ICS↔WCS, px→µm | interactive, on a graticule | "exchanged objective (different magnification), camera remounting" |
| **Trapping field calibration** (pp. 28–32) | AOD response — field intensity uniformity and response linearity | automatic, but needs a photodiode placed over the objective, laser off, objective retracted | "switching to different objective … may not be accurate anymore … particularly important when performing e.g. force measurements, **micro rheology**" |

Three consequences worth holding onto:

1. **Calibrations are per-camera** — "each camera has its own calibration data
   attached" (p. 37). This lab has two Kinetix bodies, so *which* camera the
   Tweez GUI is bound to is now a fact the drive spec has to record.
2. **A calibration cannot be started while a project is active** — "only …
   when there is no active project i.e., traps in use, patterns loaded etc."
   (p. 37). So recalibrating means tearing down the traps first; it is not
   something to slot into a running acquisition.
3. **Moving the Nosepiece from `hardware/microscope.py` silently breaks both.**
   Afterwards every `TRAP_POSITION` in µm lands somewhere else and the trapping
   field response is off, and neither interface reports it — the tweezers TCP
   link has no readout, and pymmcore-plus does not know the tweezers exist. The
   `COLLISION_DEVICES` gate already stops an unintended Nosepiece write for the
   glass-crash reason; its comment now records this second one too.

### `LOAD_PROJECT` is the answer, and it carries more than expected

A project file "contains a complete information on objects from Tweez Elements
tree view, **GUI settings (including the camera settings and calibration)**,
ROIs …, and Views. It also contains information on the **state of the laser
operation and beam setting**" (p. 65).

So magnification *is* reachable from Python — indirectly, by loading a project
saved with the calibration you want. Per-objective project templates give
per-objective calibrations, selectable over TCP. That makes `LOAD_PROJECT` carry
traps, wait states, repeat config, breakpoint bits, camera settings, calibration,
**and laser state** — which is a lot for one command, and two of those need care:

- **It can turn the laser on.** An earlier claim in this session that "the laser
  is never armed from here" was wrong and has been corrected in
  `run_pattern.py` and `tweezers_drive.command_sequence`. Save templates with
  the laser off; `--run` now warns when the sequence contains `LOAD_PROJECT`.
- **It can partially succeed and still return 0.** On load the GUI "performs
  multiple checks to avoid possible inconsistencies i.e., due to camera change,
  calibration change" and writes a report — viewable only via *Show Project
  Manager*, not returned over TCP. The manual's own figure shows a load where a
  camera change made the ROIs unusable. A 0 from `LOAD_PROJECT` means "accepted",
  not "everything in it survived".

### "Can I just load the project for the magnification I want?" — asked 2026-08-26

**For the GUI calibration, yes. For the trapping-field calibration, no.** The two
live in different programs, and that split is the whole answer:

| | owner | in a GUI project? | how it is stored |
|---|---|---|---|
| GUI calibration — Magnification (px→µm) + Beam Position (LCS↔ICS) | Tweez 300 **GUI**, ch. p.35–38 | **yes** — "GUI settings (including the camera settings and calibration)", p.65 | project file; also `Calibration/Make Default` · `Use Default`; savable separately |
| Trapping-field calibration — AOD response | Tweez 300 **System Manager**, ch. p.28–32 | **no** | System Manager's own `File/Save` · `Load` · `Clear` |

So per-objective project templates do give per-objective *geometry*, selectable
over TCP — `config/tweezers/*.yaml` now accepts `project:` as a mapping keyed by
Nosepiece label, resolved through `calibration.objective`. But the AOD field
response does not travel with it, and the manual calls redoing it after an
objective change "particularly important when performing e.g. force
measurements, **micro rheology**". Hence a separate `field_calibration:` block,
and a blocker when it disagrees with `calibration.objective`.

Three more things this does not fix:

1. **Loading a project cannot move the nosepiece.** Load the 60× project with the
   40× objective in place and you get a consistent-looking, wrong system — the
   Tweez GUI has no idea which objective is mounted. Order is on the operator:
   change the objective *first*, then load the matching project.
2. **The manual never says `LOAD_PROJECT` *applies* the stored calibration** —
   only that the project *contains* it, and that the load runs consistency checks
   "i.e. due to camera change, calibration change" and writes a report visible
   only in *Show Project Manager*. Whether a mismatch is adopted, rejected, or
   silently drops dependent elements is unresolved from the document. Test it:
   save under 40×, switch to 60×, load it back, read the report.
3. **Recalibrating means tearing down first** — a calibration "can only be
   started when there is no active project i.e. traps in use, patterns loaded"
   (p.37). Not something to slot into a running acquisition.

### The Kinetix is shared with the tweezers GUI

User, 2026-08-26: **the Tweez camera always loads a Kinetix and then releases
it.** So the GUI's camera is one of the two bodies Micro-Manager drives, and
PVCAM hands a camera to one process at a time — whoever opens it first locks the
other out. (This also reconciles the manual, which lists only DirectShow and IDS
uEye camera categories: `TweezGUICamPluginPM` — archived per `manual/README.md` —
is the Photometrics plugin that adds the Kinetix.)

Working order, now recorded in `microscope.SHARED_DEVICES` and the drive spec:

    Tweez GUI takes the Kinetix -> GUI calibration + trap setup (both need a live
    image) -> release -> hardware/microscope.py loads its config -> acquire

The drive itself survives the release: `TRAP_POSITION`, `LOAD_PATTERN` and the
rest need no image, and the GUI can run cameraless (p.34). Only the interactive
parts are lost. `Microscope.connect()` now turns a camera-contended load failure
into a message that names the tweezers GUI instead of an opaque adapter error.

Worth noting the corollary: multiple GUIs can attach to one System Manager, one
camera each, with the **TCP port incrementing per GUI** (2070, 2071, …). So the
port also selects *which camera and which calibration* you are talking to — an
alternative to swapping projects if two magnifications are ever wanted at once.

### The extension collision

While reading the Projects chapter: `.tpf` is claimed for **both** file kinds —
"a text (ASCII) file with extension tpf" for a pattern (pp. 55–56, twice) and
"an XML file with extension tpf" for a project (p. 65). Those are different
formats under one extension, so one is wrong, and `tpf` expands as readily to
*Tweez Project File* as to *Tweez Pattern File*. The single `.tsf` in the manual
is the `LOAD_PATTERN` example, which would fit pattern=`.tsf` / project=`.tpf`.
`Pattern.write()` therefore accepts both rather than guessing (`PATTERN_SUFFIXES`)
— refusing the correct one would be worse, and the GUI validates content anyway.
One command settles it on the microscope PC:
`dir "%ProgramFiles%\Aresis\Tweez\Samples\Patterns"`.

## The `.tpf` format (manual pp. 55–56)

ASCII, extension `.tpf`, header line naming columns in any order:
`colX`, `colY` (µm, relative to the trap position) and `colStr` (0–1, multiplied
by the trap's own strength) are mandatory; `colBP` (breakpoint bits),
`colXB`/`colYB`/`colStrB` (Multitone second point) and `colFocus` are optional.
Vendor samples live in `%Program Files%\Aresis\Tweez\Samples\Patterns`.

Reference numbers, manual p. 6 (Tweez 305, 60× NA 1.0 WI): switching rate up to
100 kHz · trapping range 100×100 µm max, 20×20 µm typical · up to ~1000 trapped
particles, 1–10 typical · force up to ~800 pN, 1–50 pN typical.

## Two contradictions in the manual

1. **`LOAD_PATTERN` argument order.** Command List (p. 68):
   `LOAD_PATTERN <pattern name> <pattern file>`. Worked example (p. 69):
   `LOAD_PATTERN Sample.tsf "Patt 1"` — file first, extension misspelt (`.tsf`;
   `.tpf` everywhere else), and a relative path on the same page that says "File
   paths are absolute". The example is the sloppier of the two, so the Command
   List order stays the default and `file_first=True` flips it. A wrong order
   should return -10 or -27 in the TCP/IP Svr log.
2. **`.tsf` vs `.tpf`** — same example, treated as a typo.

## To settle on the microscope PC

1. `LOAD_PATTERN` argument order (above). One command, resolved from the log.
2. **The trapping range is a trapezoid, not a rectangle** — the GUI draws a
   "green trapezoid" set by the AOD calibration, and points outside it are
   **silently clipped to the edge and not shown graphically**. So an oversized
   generated pattern deforms with no error raised anywhere. `fits_within()` only
   checks a rectangular half-width: necessary, not sufficient. Read the calibrated
   extent off the GUI and record it here.
3. **Breakpoint width from the serial number**: 1 bit at SN < 130, 4 bits at
   SN ≥ 130 (with Enable Bits / Release Bits masks, bitwise AND). SN is in the
   GUI's Connections box. `BREAKPOINT_BITS` is None until someone reads it.
4. **Decimal separator** — floats follow the Windows locale, comma or point.
   `to_tpf(decimal=",")` exists; confirm which the lab PC uses, since a file
   parsed without complaint under the wrong one is the bad case.
5. **Trap-loop slot count** — every trap costs one switching interval per pass,
   so the timing scales linearly with the real trap count. Read it, do not assume
   the pattern is alone in the loop.
6. **Measure the TCP round-trip** while there. It bounds what direct streaming
   can do and is currently a guess; `--roundtrip`-style timing on
   `TRAP_POSITION` would settle it in a minute.

## Not addressed

Laser power calibration (dial% → mW) is still deferred (2026-08-19), so trap
stiffness `kappa` stays uncalibrated and any force from `F = kappa * dx` is
relative. Independent of everything above. Piezo pattern generation — the third
control surface — is not started.
