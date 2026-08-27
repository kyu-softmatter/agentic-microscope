# 2026-08-26 · Running the three control surfaces in parallel

> Third entry from this session, after `2026-08-26-microscope-config-control.md`
> and `2026-08-26-tweezers-pattern-vs-direct.md`. Architecture + a feasibility
> audit of five specific operations. Execution stays on the microscope PC.

## Request

Separate Python files per subsystem, running **in parallel**, but sharing one
mechanical time base and able to **measure latency**, with some shared
variables — and within that, the tweezers get set up before pymmcore. Plus:
confirm each of these is actually doable from Python, and whether control is
real-time: launch Tweez · load a project · release the camera · generate and
apply a `.tpf` · control laser power.

## Feasibility, operation by operation

| Operation | From Python? | How, and what is in the way |
|---|---|---|
| **Launch the Tweez GUI** | yes | `subprocess.Popen` on the exe. No command-line arguments are documented (checked `Tweez300SystemInstallationGuide.pdf`), so nothing can be preselected at launch — and the System Manager must already be running and connected. Readiness is now probeable: `OpticalTweezers.wait_until_ready()` |
| **Load a project** | yes | `LOAD_PROJECT` over TCP. Carries traps, wait states, camera settings, GUI calibration **and laser state**; returns 0 even on a partial load |
| **Release the camera** | **not directly** | No camera command exists in the protocol. The manual puts camera changes in the GUI Tree View (p.48), i.e. mouse. **Untested hypothesis worth one experiment:** a project stores "the camera settings" (p.65), so a template saved with *no camera* selected may release it on `LOAD_PROJECT`. Otherwise: manual, or close the GUI (which also drops the traps — unverified) |
| **Generate + apply a `.tpf`** | yes | Generation is pure Python (`hardware/tweezers_patterns.py`); application is `LOAD_PATTERN` + `TRAP_ASSIGN_PATTERN`. Absolute paths only; extension ambiguity and wait states as already recorded |
| **Laser power** | **partial** | *Global* tweezers power is the System Manager's Laser Beam Control — relative 0–1, 1 ≈ 5 W on a Tweez 305 (p.24) — set by mouse or a numeric box, and **not in the TCP command set**. What *is* over TCP: `LASER_ON`/`OFF`, `BEAM_SET_FOCUS`, `BEAM_SET_PARAMS`, and `TRAP_STRENGTH` (per-trap relative, 0–1, which multiplies each pattern point's strength). So the workable split is **global power once from the GUI or a project template, per-trap modulation from Python.** Actual power in W is photodiode-monitored but shown only as a line in the GUI, and this repo's dial→mW calibration is deferred anyway. Separately, the LUN-F confocal laser's per-line power is still blocked on the FT4222 SPI word format |

## Real-time: no, and the architecture has to account for that

There is no hard real-time anywhere in this stack — Windows, no RTOS, a GIL, a
socket into another process's GUI, a vendor DLL. What exists instead is a clean
split between clocks, and the whole design follows from it:

| Clock | Determinism | Reached how |
|---|---|---|
| AOD trap loop | µs, hardware | preload a `.tpf`; the loop advances one point per pass at up to 100 kHz |
| NIDAQ sequencing | µs, hardware | `MaxSequenceLength 1024`, triggered from `/Dev1/PFI0` (`DMD_dualcam_LUNF.cfg`) |
| Camera | per-frame, hardware | MM's own `ElapsedTime-ms` series (`compute/mm_metadata.py`) |
| Piezo trajectory | hardware — rate not yet known | `function.*` waveform generator: upload samples, set iterations, play. Confirmed present in the DLL 2026-08-26; the **sample timebase** is the remaining unknown |
| **Host (Python)** | **soft, ms, unbounded jitter** | everything else |

So: **preload hardware-timed behaviour on each subsystem, start them from a
common trigger, and use the host only to orchestrate and to log.** Never put the
host in a timing loop.

### Measured so far

| Path | Median | p95 | Max | Note |
|---|---|---|---|---|
| `getProperty` (demo adapter, in-process C++) | 0.001 ms | 0.001 ms | 0.007 ms | n=2000, macOS/arm64, this session |
| `setProperty` on a NIDAQ DO line | 0.0054 ms | — | — | measured earlier, `verify_lunf_daq.py` |
| Tweez 300 TCP round trip | **unmeasured** | | | the number that decides whether host-driven trap motion is usable at all |
| NPC-D DLL round trip | **unmeasured** | | | |

Micro-Manager's *software* path is microsecond-scale. Real adapters add
mechanism time (a Nikon turret move is tens to hundreds of ms), but that is the
device moving, not the interface. The tweezers path crosses a socket into
another process's GUI, so expect it to be orders of magnitude worse — and it has
never been measured, which is why `config/session/measure_latency.py` exists.

## Architecture

Drivers stay one-per-file and know nothing about each other. One coordinator
adds the shared pieces:

| File | Role |
|---|---|
| `hardware/microscope.py` · `optical_tweezers.py` · `piezo_stage.py` | the three drivers, unchanged in structure |
| `hardware/orchestrator.py` | `Clock` · `LatencyLog` · `CameraArbiter` · `Phase` · `SharedState` · `Session`. Opens no device |
| `config/session/measure_latency.py` | runs the three concurrently and prints the latency table. `--dry-run` works with no hardware |
| `tests/test_orchestrator.py` | 29 tests, real threads, no devices |

**Threads, not processes.** All three drivers block inside C or I/O — socket
recv, PVCAM, a ctypes call — and each releases the GIL, so they genuinely
overlap. Threads also give the shared variables for free; with processes every
shared value needs IPC *and* a clock-alignment handshake, which is the thing
being avoided. One caveat: `PiezoStage` holds a single DLL instance handle, so
confine it to one thread and never call it from two.

**The host clock is not the experiment clock.** `Clock` exists so host-side
events from all three subsystems are comparable *to each other*, and it records
a wall/monotonic anchor so those stamps can be mapped onto MM's `ElapsedTime-ms`
afterwards. That mapping is a correlation, not a synchronisation, and the
docstring says so where someone might reach for it as if it were.

**The ordering is enforced, not remembered.** `Session.tweezers_setup()` takes
the camera, releases it on exit (including on exception) and advances the phase;
`microscope_setup()` refuses unless the camera is free. Calling it too early
raises `needs phase CAMERA_RELEASED` instead of letting PVCAM fail with an error
that names nothing. `CameraArbiter` is advisory — it cannot stop the Tweez GUI,
a separate Windows process, from grabbing a Kinetix — but it stops *this* code
from making the mistake.

**Readiness probing.** With no query command in the tweezers protocol, liveness
is tested by sending `TRAP_DELETE` against a sentinel name: -25 (no such
element) proves a working GUI and changes nothing, while -15/-17/-18/-19 say
whether to keep waiting or go fix something by hand. That makes "launch the GUI,
then wait" scriptable instead of a guessed `sleep`. `find_gui_port()` scans
2070–2075 — and since the port increments per GUI instance and each instance is
bound to its own camera and calibration, **the port is also the choice of which
camera and calibration you are driving.**

## To settle on the microscope PC

1. **Measure the tweezers TCP round trip** — `measure_latency.py --tweezers`.
   Read-only (the sentinel probe), so it is safe with the laser armed.
2. **Measure the piezo DLL round trip** — `--piezo sim:/NPC6330` first, then the
   real link.
3. **Does a no-camera project template release the Kinetix?** The one experiment
   that would make the whole handoff scriptable.
4. **Does closing the GUI drop the traps,** or does the System Manager hold the
   device state? Decides whether "close the GUI" is an acceptable release.
5. **Is global tweezers laser power restored by `LOAD_PROJECT`?** If yes, power
   becomes selectable from Python via templates, same as calibration.
6. ~~**Does the NPC-D command set have a waveform/trajectory generator?**~~
   **Answered the same day: yes.** `function.*` — upload samples, set count and
   iterations, start/stop/pause/unpause, read state — plus `snapshot.*` triggered
   capture. Established offline from the vendor DLL, so the piezo row in the
   clock table above becomes "µs-class, hardware" rather than unknown, pending
   the sample timebase (which is the one thing still not established). The
   remaining piezo items moved to
   `2026-08-26-piezo-waveform-generator.md`.
