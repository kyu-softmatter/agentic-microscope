# 2026-08-27 · Tweezers first light: the measured boundary of each control surface

> First session run **against the real instrument** rather than the manual or a
> simulator. Everything below was measured on the microscope PC with the Tweez
> 300 GUI live (Kinetix A24M723015-PVCAM, licence Permanent, GUI calibration
> "100x" taken 2025-12-12), and every "cannot" is a measurement, not a reading
> of the Command Reference.
>
> Corrects two claims in `2026-08-26-tweezers-pattern-vs-direct.md` — see
> "Corrections to the record" at the bottom. Bears directly on
> `2026-08-26-parallel-control-architecture.md`, which did not know about the
> camera-ownership conflict in §7.

## What was achieved

A 1 Hz sine drive, ±10 µm, ran on Trap 1 with a breakpoint at (+10, 0), and a
host-timed protocol held the trap 2.000 s at that breakpoint on each of three
consecutive oscillations. The `.tpf` was generated, loaded and assigned entirely
from Python; the laser was armed on typed confirmation. The three GUI-only
properties that gate it (`Breakpoints > Enable Bits`, `Repeat > Enabled`, laser
power) were set by hand, because nothing else can set them — which is most of
what this note is about.

## 1. There are three control surfaces, not one

| Surface | Reaches | External trigger |
|---|---|---|
| TCP external control, port 2070 | 28 documented commands | yes |
| GUI embedded Python (`Tw300Nodes` node tree) | apparently everything in the Properties panel | **no** |
| GUI, by hand | everything | — |

The middle row is the discovery of the session and also its unfinished business:
it is real, it is undocumented, and nothing in this session managed to reach it.

## 2. TCP: the boundary is now measured, not assumed

`hardware/optical_tweezers.py` covers all 28 documented commands.
**52 further command names were probed** across breakpoints, repeat, wait
states, laser power, camera, generic node access (`GET_NODE`, `SET_NODE`,
`READ_NODE`, `WRITE_NODE`, `GET_PROPERTY`, `SET_PROPERTY`), introspection
(`HELP`, `COMMANDS`, `VERSION`) and group creation. **Every one answered -11
(unknown command).** Each was sent with three junk arguments so that a command
that did exist would fail to parse rather than execute; -11 arrives before
argument parsing, so it is a clean existence oracle.

So the documented set is the whole TCP surface. There is no undocumented way in.

### -22, not -25, for an element that does not exist

`TRAP_DELETE` of a name that does not exist answers **-22 "no resource
selected"**, not the -25 "no such element" the Command Reference implies. Same
for `TRAP_POSITION`, `TRAP_STRENGTH` and `TRAP_PATT_RELEASE_BP` on a bad name.
`READY_STATUSES` was `{0, -25}`, so `is_ready()` was False on a completely
healthy GUI, `wait_until_ready()` always timed out, and `find_gui_port()` always
returned None — and the caller was then told *no GUI answered on 2070-2075*,
which is exactly the misleading diagnosis the probe exists to prevent. Fixed by
adding -22 to `READY_STATUSES`.

Useful side effect: **-22 vs 0 is a non-destructive existence test** for a trap
name. `TRAP_STRENGTH "<name>" 1` answers 0 if the trap exists and -22 if not.
That is the only "query" this write-only interface has.

### -14: back-to-back commands are rejected, and pacing alone is not enough

Sending commands with no gap races the GUI and returns **-14 "another command
active"**. Measured, 24 readiness probes per gap:

| gap | -14 count |
|---|---|
| 0 ms | **16 / 24** |
| 2, 5, 10, 20, 50, 100 ms | 0 / 24 |

But the settling time is **per command**: in the same session a *paced*
`SIMPLE_TRAP_CREATE` came back -14 at a 10 ms gap. Round trips measured later:
`TRAP_POSITION` 1.9 ms, `TRAP_PATT_RELEASE_BP` ~4-6 ms, `SIMPLE_TRAP_CREATE`
22 ms, `BEAM_SET_FOCUS` 54 ms. So no single constant covers the slowest command.

Fixed with both: a 10 ms floor (`MIN_COMMAND_GAP_S`) plus up to 6 re-sends on
-14 (`BUSY_RETRIES`). **Retrying is safe for -14 specifically** because the GUI
answered and its answer was "I did not run this". A *missing reply* must never
be retried — there the command's fate is unknown and `TRAP_POSITION_REL`,
`TRAP_PATT_ROTATION_REL` and `TRAP_PATT_SCALE_REL` would apply twice.
`send_command()` keeps those two cases apart.

This mattered immediately: `command_sequence()` sends six commands through
`do()`, which raises on non-zero, so **before the fix the drive sequence would
have aborted at the second command** — leaving `BEAM_SET_PARAMS` applied and no
pattern loaded.

### Contradictions in the manual, resolved

- **`LOAD_PATTERN` argument order.** The Command List (p.68) gives
  `LOAD_PATTERN <pattern name> <pattern file>`; the worked example (p.69) puts
  the file first. **The Command List is right** — name-first returned 0 on the
  real GUI. `--file-first` is no longer needed for this instrument.
- **Large `.tpf` files load.** 50,000 points / 1.07 MB was accepted by
  `LOAD_PATTERN`. The previous note recorded route B (`dwell`, ~846k points,
  ~20 MB) as untested; 50k is now tested, 846k still is not.
- **The optional 4th column is accepted.** A `.tpf` with
  `colX colY colStr colBP` loaded without complaint.

### `BEAM_SET_PARAMS` overwrites two settings, not one

One command carries **both** the switching rate and the blanking time, so there
is no way to set the rate alone. The lab's standing values are **50 kHz and
3 µs**; the generated sequence used to hardcode a blanking time of 0, which
would have silently discarded the 3 µs. `command_sequence()` and
`blanking_time_note()` now take `blanking_time_us`, and `try_hardware.py` has
`--blanking-us`.

The right way to keep the rate is not to lower it at all: rate is solved as
`points × n_traps / period`, so **`--points 50000` yields exactly 50 kHz** for a
1 s cycle, making `BEAM_SET_PARAMS 50000 3` a no-op against the GUI's current
state. Lowering to 200 Hz (200 points) would also have worked with one trap, but
would have changed a lab-wide setting for no benefit — at ±10 µm the 200-point
step is 200 nm, already far below anything a µm-scale bead resolves.

Cost of staying at 50 kHz, worth recording: blanking 3 µs against a 20 µs dwell
is **15 % of each pass dark**. At 200 Hz it would have been 0.06 %. That 15 % is
the lab's existing operating point, not something the drive introduced.

### `TRAP_PATT_RELEASE_BP` tells you nothing

Four releases in a row all answered 0 — the first with the trap genuinely
waiting at the breakpoint, the rest with the pattern already finished. The only
thing the status distinguishes is whether the trap **exists** (a bad name gives
-22). So **a release protocol cannot confirm a step happened**; it must be timed
from the host, or driven by the hardware trigger. Recorded in the method's
docstring.

Still untested, and it matters for automation: whether a release sent *before*
the trap arrives is remembered (the trap would sail through the breakpoint) or
discarded (it must be re-sent). Every wait in the protocol is therefore computed
from the hardware clock rather than guessed.

## 3. Trap creation: TCP is enough

`SIMPLE_TRAP_CREATE` and `TRACKING_TRAP_CREATE` both answer 0 from Python. So
creating traps — including tracking traps — needs no GUI. What TCP cannot create
is a **trap group** (`GROUP_CREATE`, `TRAP_GROUP_CREATE`, `GROUP_TRAPS_CREATE`,
`GROUP_ADD_TRAP` and five more: all -11).

That asymmetry has a consequence. `GROUP_TRAPS_START_REPEAT` /
`GROUP_TRAPS_STOP_REPEAT` / `GROUP_TRAPS_ON` / `GROUP_TRAPS_OFF` /
`GROUP_TRAPS_RELEASE` all exist in TCP, and `GROUP_TRAPS_START_REPEAT` answers
-22 rather than -11 for every name tried (`"Trap 1"`, `"All"`, `"All Traps"`,
`"Default"`, `"Group 1"`, `"Traps"`, `""`) — the commands are there, there is
just no group to name. **Make one group in the GUI once and repeat control moves
into Python.** That is the cheapest single GUI action available.

Also worth remembering: a tracking trap **joins the trap loop**, so creating one
takes `n_traps` from 1 to 2 and doubles every cycle time. A 1 Hz drive silently
becomes 0.5 Hz. It was deleted before the drive was re-run for this reason.

## 4. Breakpoints: the file was never the hard part

`BREAKPOINT_BITS = 4` on this system. Read off the GUI, where the trap's
Breakpoints properties render as a **four**-character mask (`Enable Bits 0000` /
`Release Bits 1111`), which places it at SN >= 130. That is the mask width
rather than the serial number itself; the Connections box would confirm it
directly.

**The trap that cost the most time: `Enable Bits` defaulted to `0000`.** The
mask is ANDed with `colBP`, so a mask of zero reduces every breakpoint to
nothing — and *nothing reports an error anywhere*. The `.tpf` was correct
(verified: exactly one row with `colBP != 0`, at index 12,500, coordinates
`(10.0000, 0.0000)`), the release command answered 0, and the trap sailed
straight through. Setting `0001` by hand made it stop immediately.

Two consequences:

- Any "the breakpoint does not work" report should check `Enable Bits` **before**
  looking at the pattern file. The file is the easy half.
- `Release Bits` was already `1111`, so release needed no change. Do not assume
  the same on another system.

**The breakpoint triggers on every pass**, which turns out to be a feature: it
is the real gate on the drive. A trap cannot get past the breakpoint without a
release, so `Repeat > Count` only has to be *at least* the number of passes
wanted — set it to 10 and stop releasing after three, and the trap parks at the
breakpoint on the fourth arrival. That sidesteps the `Count` semantics question
entirely.

## 5. Repeat

`Repeat > Enabled` defaults to **False**, and with it off a pattern **traverses
once and parks at the pattern end** rather than cycling. This is the second
GUI-only property that makes a correct drive look broken: the first release
works, the trap finishes its 0.75 s, and every later release does nothing.

`Count` was set to 10 for the three-oscillation run. Whether `Count` means total
passes or repeats-after-the-first is **still unconfirmed** — the run only needed
4 and 10 covered either reading. The final parked position at (+10, 0) is the
observation that would settle it.

## 6. Laser power is not reachable from software at all

The TCP set has `LASER_ON`, `LASER_OFF`, `BEAM_SET_FOCUS`, `BEAM_SET_PARAMS` and
nothing else touching the source. Probed and rejected with -11:
`LASER_SET_POWER`, `LASER_POWER`, `BEAM_SET_POWER`, `BEAM_POWER`,
`LASER_SET_CURRENT`.

Power lives on the GUI's **Laser beam control** panel, and it is neither
settable nor **readable** from Python. So:

> **Laser power is an acquisition parameter that disappears unless someone
> writes it down.** Nothing in this repo can record it after the fact.

`TRAP_STRENGTH` is *not* it — that is a per-trap relative weight in [0, 1],
multiplied by the source power. Both were 1 and 0.5 respectively at different
points today; conflating them would misreport the dose by a factor of two.

`LASER_ON` was sent from Python once, on explicit typed confirmation from the
user after the class-4 hazard and the camera-in-beam-path risk were stated.
`command_sequence()` still never includes it, and that stays right: arming
belongs with a human at the interlocks. The *capability* being in the module is
not the same as it being in a generated list.

## 7. GUI embedded Python: real, undocumented, and not reached

### What it is

`Tw300Nodes.ReadNode(path)` / `WriteNode(path, value)` address the GUI's
property tree directly. `ReadNode` returns `(status, value)` with value as text.
The path convention is **`Traps.<TrapName>.<Properties panel path>`** — from the
vendor's own `PyTool_RheoOne.py`:

```python
TrapNum = Tw300Nodes.ReadNode('Traps.Number')[1]
Tw300Nodes.WriteNode('Traps.Assign Pattern', [Trap, PattName])
Tw300Nodes.WriteNode('Traps.' + Trap + '.Pattern.Wait States', WaitStates)
Tw300Nodes.WriteNode('Traps.Remove Pattern', Trap)
```

So `Pattern.Wait States` — the property the previous note called unreachable
from Python — is written by the vendor from Python. By the same convention
`Traps.Trap 1.Breakpoints.Enable Bits` and `Traps.Trap 1.Repeat.Enabled` should
exist. **That remains inference.** Nothing in this session read or wrote a
single node successfully.

### Why it was not reached

- The modules (`Tw300ToPyComm`, `PyToTw300Comm`, `PyTw300PattGen`,
  `PyTw300DataManager`) are **not on disk**. They are injected by the GUI's
  embedded interpreter, so an external process cannot import them.
- `Tweez300GUIPython.exe` has **no listening socket and no established TCP
  connection**. The GUI↔Python bridge is not network-based. There is no external
  entry point.
- It is undocumented: `Manuals\ReadMe.txt` describes Manuals, Programs, Plugins,
  Utilities and Samples and **never mentions the `\Python` folder**. The init
  script's own comments call these "Tweez Python server internal module".

### The infrastructure that now exists (and how to undo it)

- `TW300PYPATH` is a **User**-scope environment variable, so it is redirectable
  **without admin rights**. The vendor folder in `C:\Program Files` is not
  writable by this account and was **not modified** (timestamps still 2022).
- The 168 KB / 14-file folder was copied to
  `C:\Users\Takatori lab\AppData\Local\Aresis\Tweez300\PyPath`, a survey tool
  `PyTool_NodeDump.py` + `.xml` added, and both `ArTw300ROIPythonTools.xml`
  (registry + menu) and `ArTw300GUIPythonInit.py` (import) edited **in the
  copy**. `TW300PYPATH` now points at the copy.
- Confirmed the GUI runs from the copy: fresh `.pyc` files appeared there while
  the vendor folder's newest is from 2022.
- The embedded interpreter is **Python 3.9.5** (`TW300PYENGDLL=Python39.dll`),
  so tools must be 3.9-compatible. `PyTool_General` was deliberately not
  imported — it pulls in matplotlib, scipy and tkinter.

To revert completely:

```powershell
[Environment]::SetEnvironmentVariable('TW300PYPATH', 'C:\Program Files\Aresis\Tweez300\Python', 'User')
```

then restart the GUI. Nothing else needs undoing.

### The finding that blocks it

A survey called from `ArTw300GUIPythonInit.py` at GUI startup read **0 of 51
paths** — including `System.Version`, which `PyTool_General.py:108` reads and
therefore cannot be absent. **The node tree is not up when the init script
runs.** This is not a naming problem and not fixable by retrying, because
holding the init would hold GUI startup.

Two things left to try, neither yet done:

1. Right-click the **tracking ROI**, not the `Tools` element. The registry is
   named `ArTw300ROIPythonTools.xml` and both vendor tools declare
   `DataSource Name="Probe"`, so PyTools attach to an ROI. `Tools` in Tweez
   Elements offers only rotation / scale / move — those are geometry tools.
2. Find a way to **disconnect and reconnect Python** in the GUI. If that re-runs
   the init script, it runs *after* the GUI model is up and the timing problem
   disappears with no menu needed.

The survey's first version printed no status code, so the all-failed dump could
not be interpreted. It now prints `st=` per path, which is what distinguishes
"no such node" from "engine not ready".

## 8. Trap position *is* readable — but it costs the camera

`PyTool_ForceTime.py:233` unpacks a probe's `.Data` node as five columns:

```python
TimOrg, PrbOrgX, PrbOrgY, TrpOrgX, TrpOrgY = Data[0], Data[1], Data[2], Data[3], Data[4]
```

and `ForceTimeCalc` computes `k * (TrpPos - PrbPos)` — which is exactly the
`F = kappa * (x_bead - x_trap)` that
`config/channels/active-microrheology-probe-tracer.yaml` needs. So **trap
position is logged as a time series**, and a flat `TrpOrgX` would be a far
better breakpoint-state readback than any boolean: it gives arrival time, hold
duration and the achieved frequency at once.

The catch is ownership. `GetToolData` requires `len(Data[1][0]) > 0`, and samples
only accumulate while the Tweez GUI is tracking, which requires the Tweez GUI to
hold the camera.

| | Micro-Manager owns the camera | Tweez GUI owns the camera |
|---|---|---|
| imaging from `pymmcore-plus` | yes | no |
| trap-position readback | **no** — probe collects nothing | yes |

`2026-08-27`: the camera was released to Micro-Manager during this session
(GUI title shows `RELEASED.`), which is why the tracking route could not be
tested. **This conflict is not addressed in
`2026-08-26-parallel-control-architecture.md`** and needs to be, because
active-microrheology force needs bead *and* trap position simultaneously and
only one owner can see both.

### Neither side of the handover is reachable from Python today

Two independent blocks, and they fail for unrelated reasons:

- **Tweez GUI side — structural.** No camera command exists.
  `CAMERA_RELEASE`, `CAMERA_ACQUIRE`, `CAMERA_GRAB`, `CAM_RELEASE` all answer
  -11. The node API might reach it, but see §7: no node has been read yet.
- **Micro-Manager side — a version mismatch, and fixable.** The lab's
  `C:\Program Files\Micro-Manager-2.0` has the right pieces —
  `mmgr_dal_PVCAM.dll` (x64), `pvcam64.dll` and `pvcamDDI.dll` in System32,
  Photometrics PVCam installed, 264 adapters — but **every adapter fails to
  load**, `DemoCamera` included, so it is not PVCAM-specific. Bitness is not the
  problem either: adapter, runtime and our interpreter are all x64.

  The cause is the device-interface version. `pymmcore 12.5.0.75.0` reports
  *Device API version 75, Module API version 10*, while the lab's install dates
  from 2023-12-23 and its adapters predate that. MMCore refuses adapters whose
  interface version does not match.

  `mmcore install` fetches adapters built for API 75 into pymmcore-plus's own
  directory and **does not touch the lab's Micro-Manager install** — which is
  what `requirements.txt` already advises. Not yet run.

Consequence for `calibration/mm_live.py`: its docstring says it has never been
verified against the real PVCAM/Kinetix adapter, only the bundled demo camera.
That is still true, and now we know it cannot be verified until the adapter
version is resolved.

## 9. Timing: the model is confirmed

50,000 points at 50 kHz with one trap in the loop:

| quantity | value |
|---|---|
| cycle | 1.000 s (→ 1 Hz) |
| breakpoint at index 12,500 | 0.250 s after cycle start |
| travel after release | 0.750 s |
| amplitude / peak-to-peak | ±10.0000 µm / 20 µm |
| mean / peak speed | 40.00 / 62.83 µm/s |
| step between points | 0.80 nm mean, 1.30 nm max |
| trapping range recorded | ±40 µm in x and y at 100x (pattern uses 25 %) |

Host-side release timing, measured: a 3.000 s gap between two releases landed at
**3.000003 s (+3 µs)**, and three successive 2.000 s holds each showed 0.0 ms
error. Travel is hardware-clocked by the AOD trap loop and exact; the host is
the only loose end, and at these tolerances it is not the limiting factor.

Being **late** with a release is harmless — the trap waits at the breakpoint
indefinitely, so the hold just runs long. Being **early** is the untested
failure mode (§2).

## 10. The division of labour this implies

The previous note proposed GUI-once-then-Python and was right, but for an
incomplete reason (it thought wait states were the only GUI-only property). The
measured list is longer:

**GUI, once, saved as a project template with the laser OFF:**

- `Breakpoints > Enable Bits` (and `Release Bits` if not already `1111`)
- `Repeat > Enabled` and `Count`
- `Pattern > Wait States`
- **a trap group** — this is the one that hands repeat control to Python
- both calibrations (GUI magnification + beam position; AOD field, which lives
  in System Manager's own File menu and does *not* travel in the project)
- laser power, and **write it down**

**Python over TCP, per experiment:** trap create/delete, position, strength,
rotation, scale, pattern generate/load/assign/delete, switching rate, blanking,
beam focus, trap on/off, breakpoint release, group on/off/repeat once the group
exists.

Saving that template with the laser off also removes the reason this repo
refuses to send `LOAD_PROJECT`: a project file carries "the state of the laser
operation and beam setting" (manual p.65), so a template saved laser-on can
restore laser-on. Saved laser-off, `LOAD_PROJECT` becomes the one command that
restores every GUI-only property in a single line — and it is already in the TCP
set.

## 11. The minimal manual work — operational checklist

Asked directly: *what is the least a human has to do?* The answer follows from
§10, and it is better than it looks, because `LOAD_PROJECT` **is** in the TCP
set. Put every GUI-only property into a saved project and one command restores
all of them.

So the manual work is **one setup session, then almost nothing per run.**

### Once — build the template, save it with the laser OFF

In the trap's Properties:

1. `Breakpoints > Enable Bits` → `0001` (or `1111` to enable every bit). Default
   is `0000`, which silently disables every breakpoint. §4.
2. `Repeat > Enabled` → `True`, and `Count` at least the number of passes
   wanted. Default False makes a pattern traverse once and park. §5.
3. `Pattern > Wait States` if a per-trap slowdown is wanted (not needed for the
   1 Hz sine, which solves its rate from the point count).

In Tweez Elements:

4. **Create one Trap Group containing the trap.** Highest value per click in the
   whole list: group *creation* is the only element creation TCP cannot do, but
   `GROUP_TRAPS_START_REPEAT` / `STOP_REPEAT` / `ON` / `OFF` / `RELEASE` all
   exist. One group, and repeat control becomes programmatic. §3.

In Laser beam control:

5. Set the power **and write the number down**. Neither settable nor readable
   from software, so it vanishes from the record otherwise. §6.

Then:

6. **Turn the laser off and save the project.** This is what makes
   `LOAD_PROJECT` usable: a project carries "the state of the laser operation and
   beam setting" (manual p.65), which is exactly why this repo has refused to
   send it. Saved laser-off, that objection disappears.

### Per run — one thing

Arm the laser. Everything else is scriptable. (Sending `LASER_ON` from Python is
possible and was done once today on typed confirmation, but arming at the GUI
with the interlocks in view remains the default for a class-4 source.)

Returning the camera to the Tweez GUI is also manual, when that is wanted — §8.

### Everything else, from Python over TCP

Trap create/delete including tracking traps · position · strength · rotation ·
scale · pattern generate/load/assign/delete · switching rate · blanking · beam
focus · trap on/off · breakpoint release · group on/off/repeat once the group
exists · `LOAD_PROJECT` · host-timed protocols (measured to +3 µs on a 3 s gap).

### Worth testing, because it would shorten the list

If a project really carries the *beam setting*, it may carry **laser power** too
— in which case a template saved laser-off would restore the power with the
laser still off, and item 5 becomes one-time as well. Test: set a distinctive
power, save, change it, `LOAD_PROJECT`, see whether the panel returns to the
saved value. `LOAD_PROJECT` can be sent from Python, so this needs only the save.

## Corrections to the record

`2026-08-26-tweezers-pattern-vs-direct.md` states two things this session
contradicts:

1. **"the TCP interface has no readout of any kind"** — true of TCP, but the
   sentence was used to argue that `x_trap(t)` is unrecoverable, and §8 shows it
   is logged in the GUI's own probe data. The Lens 6 argument for patterns over
   TCP streaming survives (a streamed trajectory is still host-jittered), but it
   no longer rests on "there is nothing to read back against".
2. **wait states are "no — GUI only"** — true of TCP only. The vendor writes
   `Pattern.Wait States` from the GUI's Python (§7).

Neither changes the decision to drive from `.tpf` patterns. Both change what the
*reason* is, and #1 changes what the microrheology channel can hope to measure.

## Still open

- One successful node read or write. Everything in §7 turns on it.
  **Next action is written up as a runbook:**
  [`kb/systems/PyTool-RUN-FIRST.md`](../systems/PyTool-RUN-FIRST.md) — run
  `PyTool_ApiDump` first, because `dir()`/`inspect` on `Tw300Nodes` needs only
  the import (which demonstrably succeeds) and not the node tree, so it is not
  blocked by the timing problem this section describes.
- Whether an early `TRAP_PATT_RELEASE_BP` is remembered or discarded (§2).
- `Repeat > Count` semantics: total passes, or repeats after the first (§5).
- The device serial number, to confirm `BREAKPOINT_BITS = 4` directly (§4).
- Whether an 846k-point `.tpf` loads (§2 tested 50k).
- How to split camera ownership between Micro-Manager and Tweez tracking (§8).
- `mmcore install`, to get device-API-75 adapters so `pymmcore-plus` can open
  the Kinetix at all. Until then `calibration/mm_live.py` stays unverified
  against the real adapter and the camera cannot be grabbed from this side (§8).
- Whether a saved project carries **laser power** (§11). If it does, the manual
  setup list loses its only per-value item.
- The trapping range was recorded as a ±40 µm **rectangle**; the real edge is a
  trapezoid and `fits_within` only checks the rectangle. Points outside are
  clipped silently.
