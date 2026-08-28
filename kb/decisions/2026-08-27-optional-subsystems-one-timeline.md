# 2026-08-27 · Optional subsystems, one timeline

> Fourth entry from this day, after the two first-light notes. Those established
> what each control surface can do alone; this is about running them together
> when *not all of them are switched on*.
>
> Corrects a real bug in `hardware/orchestrator.py` — see §2. Supersedes the
> architecture in `2026-08-26-parallel-control-architecture.md` on one point
> (the phase machine) and leaves the rest of it standing.

## Request

> "I have confirmed the tweezers, the piezo and the microscope are each
> controlled. They will not always be used together, but I want a parallel-
> structure program managed with a common timestamp. Sometimes some equipment
> may be switched off; the microscope will always be on."
>
> and, on the phase machine specifically: "if the tweezers are not used, go
> straight to the microscope; only when the tweezers are on, release and then
> the microscope." (user, 2026-08-27)

## 1. The microscope is required, and not by convention

It is on the roster whether or not anyone names it, and it cannot be excluded.
Not deference to the user's statement — it follows from what the clocks are. The
camera's per-frame `ElapsedTime-ms` series is the series every other subsystem
is aligned *onto*. A run without it has no shared time base, so "one common
timestamp" would not mean anything. `orchestrator.REQUIRED` records this.

The other two are optional and independently so, which gives four rosters:

| roster | camera handoff | tracks |
|---|---|---|
| microscope | none | 1 |
| microscope + piezo | **none** | 2 |
| microscope + tweezers | full | 2 |
| all three | full | 3 |

## 2. The bug: the handoff was demanded even when there was nothing to hand over

`Session.microscope_setup()` called `require(Phase.CAMERA_RELEASED)`
unconditionally. With the tweezers switched off, nothing ever entered
`tweezers_setup()`, so the phase stayed at `IDLE` and the microscope was
**refused**:

```
this needs phase CAMERA_RELEASED or later; session is at IDLE
```

The microscope was blocked waiting for a release that nobody was ever going to
perform. Worse, the one caller papered over it: `config/session/measure_latency.py`
entered `tweezers_setup()` unconditionally, so a `--piezo`-only latency run
recorded that the tweezers had taken and released a camera they had never
touched.

**Fixed.** The release is required only when the tweezers are on the roster:

| roster | `microscope_setup()` |
|---|---|
| tweezers on | refuses until `CAMERA_RELEASED`, exactly as before |
| tweezers off | runs straight from `IDLE` → `MICROSCOPE_SETUP` |

The rule is unchanged in substance — PVCAM hands a Kinetix to one process at a
time, so tweezers-first is still forced when both want it. What changed is that
the rule is now conditional on there being a second program at all.
`tweezers_setup()` refuses outright when they are absent, since taking the
camera on behalf of a program that is not running would block the microscope for
the rest of the session.

## 3. Tracks: the program keeps its shape when a device is off

`add_track(subsystem, body)` then `run_tracks()`. A track for an absent
subsystem is **dropped and recorded** (`track skipped — subsystem is off`)
rather than guarded at every call site, so the same script serves all four
rosters. Every track is released from one `threading.Barrier`, so the spread
between starts is OS scheduling rather than the sum of three connect times —
measured at **0.04 ms** for three tracks.

Two decisions worth keeping:

- **One track per subsystem, enforced.** This is what confines the NPC-D's
  single DLL instance handle to one thread. Nothing else in the process would
  notice that being violated. It also keeps the tweezers to one command at a
  time, which the GUI requires (-14, "another command active").
- **A failing track sets a cooperative `stop` and its exception comes back in
  its `TrackResult`** instead of escaping `run_tracks`. With three instruments
  live, the other two still need winding down, and one traceback escaping the
  call would skip that. `stop` cannot interrupt anything — a driver inside a
  socket `recv` or a DLL call will not see it — and the docstring says so.

## 4. One timestamp across three clocks: the anchor, and its uncertainty

`Clock` made host events comparable. It did not make *hardware* events
comparable, and hardware is where the timing lives. That gap is now
`Timeline.anchor()`.

Bracket the one command that starts a timed run, and it records the host time of
that start with **half the command's round trip as an explicit uncertainty** —
the hardware began somewhere inside the bracket and that instant cannot be
observed, only bounded. Every later time then comes from the run's own rate
(`host_of_sample`), never from a fresh host stamp. The host is allowed to be
jittery exactly once per run instead of once per event.

`alignment_error_s(a, b)` is the sum of two anchor uncertainties, and it is the
number that decides what may be claimed across subsystems. With the round trips
already measured — 0.69 ms median / 2.60 ms max for `stage.position.command.set`,
1.9 ms for `TRAP_POSITION`, ~4–6 ms for `TRAP_PATT_RELEASE_BP` — "the stage was
at the peak on frame 412" holds at 1 Hz and does not hold at 500 fps. No amount
of Python changes that; a hardware trigger would.

A start command that **raises records no anchor**, only a failure mark. The
hardware's zero is genuinely unknown in that case, and an anchor that looked
usable would hand every later `host_of_sample` a plausible number with nothing
behind it.

### Two clock kinds, because the piezo is about to change from one to the other

Every anchor must name which clock carries the run — there is no default:

| | carried by | error budget |
|---|---|---|
| `HARDWARE` | a preloaded hardware clock: the AOD loop at 50 kHz, the NPC-D's 20 µs servo, the camera's readout | the anchor, and nothing more |
| `HOST_SCHED` | the host, issuing steps against absolute deadlines from one t0 | the anchor **plus** per-step schedule slip |

This distinction is not decoration. The piezo is `HOST_SCHED` **today** and
becomes `HARDWARE` the day `function.waveform`'s sample unit is settled
(`piezo_stage.WAVEFORM_DATA_UNITS`, blocked on one constant-waveform run). Same
script, same trajectory, two different guarantees. A record that did not
distinguish them would make those runs look identical.

Consequence for `alignment_error_s`: for two `HARDWARE` anchors it is the whole
budget; for a `HOST_SCHED` anchor it is a **lower bound**, because the zero of a
host-scheduled loop is known well (its start command is free) while every later
step carries slip. `run_parallel.py` prints both terms so the anchor number is
not read as the whole budget.

## 5. Measured this session: the parallel structure does not cost timing

Two things had been assumed by `2026-08-26-parallel-control-architecture.md` and
were never tested. Both were tested here, offline, on macOS/arm64.

### 5a. The busy-wait window has to exceed the platform's sleep overshoot

`gated_oscillations.py` and `config/piezo/run_sine_hold.py` sleep to just short
of each deadline and spin the last 2 ms. That 2 ms is a **Windows** number, and
it is load-bearing:

| platform | `sleep(48 ms)` overshoot | 2 ms spin tail | 6 ms spin tail |
|---|---|---|---|
| Windows, microscope PC | ~1 ms (repo note; the 60 s piezo run measured slip median 1 µs, max 1.07 ms, 0/6000 overruns) | works | — |
| macOS, dev box | **median 2.9 ms, max 5.0 ms** | slip stays at **2.2 ms** | slip **2 µs** |

On macOS a 2 ms tail sits *inside* the overshoot, so the spin never gets a turn
and the sleep's error lands in the data. `run_parallel._SPIN_S` now defaults per
platform, with `--spin-ms` to override. Anyone reading a 3 ms slip on a Mac and
concluding the host cannot hold a schedule would be diagnosing the wrong thing.

### 5b. Concurrent tracks hold their schedule — the GIL is not the problem

Spinning is a tight Python loop holding the GIL, so concurrent spinners were the
obvious suspect. They are not:

| concurrent tracks | slip median | slip max | overruns |
|---|---|---|---|
| 1 | 3.9 µs | 16 µs | 0 |
| 2 | 4.8 µs | 75 µs | 0 |
| 3 | 4.6 µs | 90 µs | 0 |
| 4 | 3.1 µs | 87 µs | 0 |

50 ms period, 6 ms spin window, 20 steps each, a 0.4 ms stand-in round trip.
Four tracks cost ~70 µs more worst-case slip than one, against a 10 ms period.
**Threads do not degrade host scheduling**, which is the assumption the whole
parallel design rests on and had never been checked.

A first attempt at this measurement blamed the GIL for a 3 ms slip seen with
three tracks. It was wrong: one track showed the same 3 ms, and more tracks
showed *less*. The cause was §5a, not contention.

## 6. The objective check: something only the coordinator can do

`run_parallel.py --calibrated-objective` refuses a run whose objective is not
the one the tweezers' GUI calibration was taken at. Neither driver can make this
check alone: the objective is readable from Micro-Manager, and the calibration
it silently invalidates lives in the Tweez GUI, where it is neither readable nor
announced. Both GUI calibrations die on an objective change and the traps then
land somewhere other than where they are commanded.

This is what the shared state is *for*, and it is the first use of it that a
single subsystem could not have done.

## 7. What changed in code

| file | change |
|---|---|
| `hardware/orchestrator.py` | `Roster` · `Timeline` · `Mark` · `HardwareAnchor` · `Entry` · `Track` · `TrackResult` · `start_spread_s` · `track_report`; `HARDWARE`/`HOST_SCHED`; subsystem tokens `MICROSCOPE`/`PIEZO`; `Session(*present)`, `has`/`absent`/`require_present`, `add_track`/`run_tracks`, `stop`; **`microscope_setup()` release now conditional**; `tweezers_setup()` and `instrument()` refuse an absent subsystem |
| `config/session/run_parallel.py` | **new** — the parallel program: roster from flags, conditional handoff, one track per present subsystem, anchored schedules, alignment budget, merged timeline to CSV. `--dry-run` needs no hardware |
| `config/session/measure_latency.py` | declares its roster instead of always walking the handoff; logs the microscope under `MICROSCOPE`, the piezo under `PIEZO`; reports what an absent subsystem cost |
| `tests/test_orchestrator.py` | 29 → **71** tests, real threads, no devices. Whole suite 791 pass, 3 skipped |

## 8. Deliberately not built

- **A camera-ownership policy.** With the tweezers enrolled, someone has to
  decide whether the Tweez GUI keeps the Kinetix (trap-position readback, no
  `pymmcore` imaging) or releases it (imaging, no trap position). The roster
  makes that choice more visible but does not resolve it, and the underlying
  conflict is still open — see
  `2026-08-27-tweezers-first-light-measured-limits.md` §8. Today's code keeps the
  existing behaviour: the tweezers set up, then release.
- **A camera acquisition path.** The microscope track reads properties; it does
  not acquire. Every device adapter in the lab's MM install fails to load
  against pymmcore 12.5 (device API 75), so no acquisition path can be tested
  from this repo yet. `mmcore install` is the fix and is already on the open
  list. An untested acquisition path is worse than a marked gap.
- **A second piezo drive.** `config/piezo/run_sine_hold.py` already does it with
  the safety gates a motion path needs. `scheduled_loop` demonstrates the same
  absolute-deadline structure read-only, and the swap is one line.
- **A driver facade.** Still deliberately absent, for the reason
  `2026-08-26-parallel-control-architecture.md` gave: three vendor protocols, and
  a facade would have to be kept in step with all of them.

## 9. Prepared offline, to be run at the instrument

Written the same day, against the facts above, so that tomorrow's session is
running experiments rather than writing them.

| script | what it settles | state |
|---|---|---|
| `config/piezo/settle_waveform_units.py` | the generator's sample unit (§7b of the piezo note) — an adaptive constant-waveform ladder over six readings of the value | plan verified offline; `--move --unlock` untried |
| `config/micromanager/make_single_cam_cfg.py` | derives a one-camera config so the Tweez GUI can hold one Kinetix while MM images on the other | derivation verified both directions |
| `config/micromanager/single_cam_{blue,red}_LUNF.cfg` | the two derived configs | generated, never loaded |

**The waveform ladder is adaptive for a safety reason.** A probe is refused if
*any* reading still in play predicts a destination outside the travel, so the
script never issues a command whose landing place it cannot bound under every
hypothesis it is still entertaining. Each probe eliminates readings, which is
what makes the next one safe to widen. `5e6` goes first because it separates all
six readings on its own *and* its worst destination is 5 µm rather than an end
stop; `0` — which puts five of the six readings at the bottom of travel — is
demoted to a confirmation.

Predictions landing exactly on 0 or 600 µm are **flagged, not refused**: those
are the controller's own calibrated range, and "absolute picometres" necessarily
maps every small value near the bottom, so refusing the limits would refuse the
sharpest probe in the ladder. Whether the controller clamps or faults there has
never been tested here, so the operator sees the number in the confirmation
prompt and decides.

**The one-camera config is a two-line derivation, and that is the finding.** In
`DMD_dualcam_LUNF.cfg` the two Kinetix are independent PVCAM devices —
`Camera-1` and `Camera-2` — with **no** Multi-Camera or splitter device wrapping
them, no config group switching `Core,Camera`, and no per-camera preset.
`Kinetix_red` appears in exactly two of 206 lines. So "one owner each" is
expressible in Micro-Manager and always was; nobody had checked. Two things it
does not settle, both at the instrument: which physical body MM opened (PVCAM
enumerates by index, and whether `Camera-1` still means the same body once the
other is held elsewhere is untested — check the serial, not the label), and
whether the trap plane appears on the kept camera at all, which is optics.

`tests/test_session_scripts.py` covers the parts that decide whether a command
is safe to issue: 20 tests, no devices. Writing them caught a bug in the config
generator — `--keep Kinetix_red` reported a correct file as `UNEXPECTED`,
because the parent already names red as `Core,Camera` and the check had the
two-line diff hardcoded. It now asserts invariants instead.

## 10. Still open

1. **Who holds the camera** when the tweezers and Micro-Manager both want it
   (§8, first bullet). The one genuinely unresolved question in the parallel
   architecture — but §9 narrows it: the *configuration* half is done, and what
   remains is whether the optics cooperate.
2. **`mmcore install`**, then anchor a real sequence acquisition against MM's
   `ElapsedTime-ms` series and check the anchor against it. That is the first
   test of whether the alignment machinery reports the truth.
3. **The piezo generator's sample unit** — the script is written (§9), the run
   is not done. Turns the piezo's anchor from `HOST_SCHED` to `HARDWARE` and
   deletes its slip term.
4. **The trigger plumbing** (`function.trigger-inputs.*`,
   `controller.synchronisation.master/slave`, `/Dev1/PFI0`). This is what would
   collapse the alignment budget from milliseconds to microseconds, and it is
   the only thing that would.
5. **A `--spin-ms` measurement on the microscope PC**, to confirm the 2 ms
   Windows default against `sleep` overshoot there rather than inheriting it
   from a note.
