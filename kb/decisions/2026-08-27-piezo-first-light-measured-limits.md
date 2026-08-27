# 2026-08-27 · Piezo first light: the stage moved, and what the record had wrong

> First session in which the NPC-D piezo was **driven** from this repo rather than
> read about. Everything below was measured on the microscope PC over **COM4**
> against the live controller — Prior/Queensgate NPC-D, DLL 2.7.9, firmware
> **6.7.8**, 3 channels, stage `SP-XYZ-600` serial 107866, calibration preset 6
> "Customer 1", axis ids x, y, z on channels 1, 2, 3.
>
> Every number here is an observation from that session. Where it contradicts an
> earlier note, see "Corrections to the record" at the bottom — three separate
> claims in `2026-08-26-piezo-waveform-generator.md` and
> `reference/npcd-command-set.md` turned out to be wrong, and one of them was
> wrong in a direction that matters.
>
> Sibling to `2026-08-27-tweezers-first-light-measured-limits.md`: same day, same
> question asked of the other subsystem. The contrast in the answers is the point
> — the tweezers cannot be read back, and this can.

## What was achieved

The x axis was driven from Python, closed-loop, with every commanded sample read
back. Three drives, in order of how much they establish:

1. **A 1 Hz sine, ±5 µm about 300 µm, 3 cycles.** Achieved 1.0000 Hz.
2. **A 1 Hz sine, ±10 µm about 400 µm, 60 cycles.** 0/6000 overruns.
3. **A four-phase program, ×3:** 3 sine cycles → a quarter cycle up to the peak →
   **2 s hold at the peak** → **step release to centre, 5 s hold**. This is the
   shape the session was actually after, and it is now
   `config/piezo/run_sine_hold.py`.

Absolute positioning works too: commanded 400.0000 µm, measured 399.9987 µm,
`stage.status.in-position.lpf-confirmed.get` = 1.

Z was never commanded — the sample was in focus and stayed that way. That is not
squeamishness, see §7.

## 1. Connecting is one line, and three things about it are not obvious

```python
stage.connect("COM4")
```

- **The link is the bare port name.** No scheme. `sim:/NPC6330` reaches the DLL's
  simulator and looks like a URL, which invites `com:/COM4`, `serial:/COM4`,
  `usb:/COM4`, `COM4:` — all four were tried, all four fail. Only `COM4` opens.
- **`list_devices()` answers `[]`.** `FindDevices` does not enumerate a
  USB-serial controller, so the port cannot be discovered, only named.
- **The port is exclusive, and the vendor GUI takes it.** With NanoBench 6000
  holding a session, `connect()` fails with "could not open comms link to
  'COM4'" — the same message a wrong link string gives, so it reads like a
  syntax problem and is not one. The DLL still loads and `sim:/NPC6330` still
  opens, which is how to tell the two apart.

## 2. The security level decides what *exists*, and this is the trap

At the base level (`controller.security.user.get` → `None`) the controller
reports **188** commands, of which **exactly one** is a `.set`:
`controller.security.user.set`. Raised to User it reports **414**.

`stage.position.command.set` is not unavailable at the base level, it is
**invisible**: `find_commands()` omits it and asking for its signature answers
*"Invalid command name"*. That message reads like *this controller cannot command
a position*, which is the opposite of the truth. Anyone bringing this stage up
without knowing about the security level will conclude the digital path is
read-only.

- The access codes are fixed vendor per-level constants and they are in the GUI's
  own config: `C:/Program Files (x86)/NanoBench 6000/data/config.ini`,
  `[SecurityLevels]` → `User = DEC0DED`, `Super User = B01DFACE`.
- **The `0x` prefix is required.** `controller.security.user.set DEC0DED` answers
  "Not enough parameters for command" — the controller parses the code as a
  number and a bare hex string is not one. `0xDEC0DED` returns `security = User`.
  The "not enough parameters" wording sends you looking for a second argument
  that does not exist.
- **The level is controller-side state that outlives the session.** It was found
  already at `User` at the start of a run, because the vendor GUI had been
  connected earlier and left it there. So an unlock that reports "0 new commands
  became visible" may mean *already unlocked*, not *code rejected*.

At User level: `stage` 161 commands (8 settable), `function` 131 (52),
`resonance-detect` 22, `protection` 21, `diagnostics-logging` 21, `snapshot` 19,
`identity` 14, `scope` 13 (6), `controller` 12 (1).

## 3. Positions are in picometres — established by arithmetic, not by asking

Library manual 5.2 says applications should always check the units. **They
cannot, here.** `GetCommandParameterUnitsType` and its three siblings raise
`OSError: access violation writing 0x...0001`, and on the runs where they answer
instead of crashing they answer an empty string for every parameter and result of
the position commands. So the DLL's units API is not a source of truth on this
controller in either failure mode.

What settles it is a cross-check: `stage.position.calibrated-range.maximum.get`
reads **6.0e8** on all three axes for a stage whose part number is
**SP-XYZ-600**. 6.0e8 pm = 600 µm. No other unit makes that number a travel.
`stage.range.closed-loop.maximum.get` agrees, and
`stage.command.analogue.scaling.get` reads **60**, consistent with 600 µm across
its 10 V analogue input.

**Travel is 0..600 µm on every axis**, x, y and z alike.

### The command step is 32 pm, and it was measured

Commanding channel 1 in 2 pm increments and reading
`stage.position.command.get` back shows the accepted value stepping at +18 pm and
+50 pm from the start — a **32 pm** grid. Not 12.2 nm, which is what this repo
had (§9). 32 pm is *command* quantisation only: what the controller will accept
as distinct. It is ~400× finer than anything the stage delivers, so it never
binds in practice; it matters because a wrong value makes
`Waveform.quantisation_error_pm()` report fiction.

## 4. The DLL's string getters are broken, and the crash is diagnosable

`command_parameters()` / `command_results()` used to call four unit getters per
item and crash. The access violation writes to address `0x1`, which is the
*buffer length* argument being dereferenced as a pointer — so the real 2.7.9
signature is not the five-argument `(inst, name, index, char*, int)` that
`hardware/piezo/vendor/dll_adapter.py` declares. It is not intermittent in the
way it looked: it is deterministic per call site, and the appearance of
intermittency came from different code paths reaching different getters.

This mattered because the pre-move signature check in `try_hardware.py` refuses
to move when it cannot read a signature — correctly — so the crash silently
blocked the first drive attempt. The commanded position sitting at exactly
300.0000 µm afterwards was the tell: a script that had moved and restored would
have left a non-round number.

Fixed by not calling them: `with_units=False` is the default, names are read with
`GetCommandParameterName` which works fine, and the picometre assumption rests on
§3 instead.

## 5. The command-path question, open since 2026-08-19, is answered

On **all three channels**:

| query | value |
|---|---|
| `stage.mode.digital-command.get` | **1** |
| `stage.mode.analogue-command.get` | **0** |
| `stage.mode.closed-loop.get` | 1 |
| `stage.mode.is-sensor-only.get` | 0 |
| `stage.mode.freeze-servo-output.get` | 0 |

The controller acts on the USB/DLL path and **ignores** the analogue input from
`Dev1/ao2`. Raw words for the record: mode `0x0327` on channel 1, `0x0323` on 2
and 3, status `0x0B17` on all three.

**This does not retire the hazard.** Two reasons. The analogue cable is still
physically connected, and MM writes 0 V when it initialises an AO device — 0 V is
0 µm on a path that is inert only as long as the mode says so. And the mode is
*not* immutable: there is no per-bit setter, but `stage.mode-mask.set` and
`stage.mode-only.set` appear at User level and write the raw mode word. So keep
`NIDAQAO-Dev1/ao2` out of every Micro-Manager configuration.

## 6. Host-timed drive: characterised, and good enough

The controller's servo period is 20 µs (`controller.sampling-time.get` =
1.999999949e-005). Python is nowhere near that, and the numbers say by how much.

| | median | max |
|---|---|---|
| `stage.position.measured.get` round trip | 0.42 ms | 1.17 ms |
| `stage.position.command.set` round trip | 0.69 ms | 2.60 ms |

So the link sustains ~890–900 samples/s, and at 1 Hz with 100 samples/cycle
there is 14× of headroom. Over a 60 s run: achieved 1.0000 Hz, mean sample period
10.000 ms, schedule slip median 1 µs and max 1.07 ms, **0/6000 samples arrived
more than one period late**. The four-phase program ×3 (3078 samples) took
30.770 s against a planned 30.780 s, slip max 0.142 ms, 0/3078 overruns.

Absolute deadlines from a single `t0` are why: a slow round trip does not push
the rest of the schedule out.

### What the axis actually does, split by phase

| phase | n | measured span | \|measured−commanded\| median | max |
|---|---|---|---|---|
| sine, ±10 µm at 62.8 µm/s | 900 | 20.1030 µm | 612 nm | 965 nm |
| rise to the peak | 78 | 10.9201 µm | 637 nm | 924 nm |
| **hold at the peak** | 600 | **0.0824 µm** | **9.3 nm** | 53 nm |
| release (10 µm step) | 1500 | 11.5693 µm | 9.1 nm | 10010 nm |

Read that as one sentence: **moving, the axis lags ~600 nm; standing still, it
holds to ~10 nm.** The 612 nm is an *upper bound* on tracking error — the
readback happens after the command, so it carries the stage's settling and one
round trip — and it scales with speed, which is the signature of following error
rather than of noise. The 10010 nm in the release row is the step itself, caught
at the instant it was commanded.

Per-hold detail, three consecutive 2 s holds at 410 µm: drift −18.3, −25.8,
−66.2 nm; stdev 14.2, 13.6, 13.3 nm. Release settles to within 100 nm of centre
in **20.0 ms** every time.

Independent noise floor, with nothing commanded: 2000 reads at 400 µm span
73.9 nm, stdev 12.6 nm, and **no reading further than 1 µm from the median**.
That last number is what makes §7 a hardware finding rather than a readback
artifact.

## 7. The hardware waveform generator is present, and NOT usable yet

`function.*` is 131 commands at User level, in two interfaces:

- **`function.waveform.*`** — a **500 001-sample** buffer, one command per
  sample: `data.set channel index value`, with `count`, `iterations`,
  `repeat-count` (0 = forever) and `sample-period` per channel.
- **`function.waveform-generator.*`** — segment-based: start/end position, start/
  end velocity, duration, type, per-segment trigger outputs. This is the one to
  use for a long smooth path, because it does not cost one command per sample.
  Untouched so far.

Signatures were read off the controller and are recorded in
`piezo_stage.WAVEFORM_PROTOCOL`. `function.command.start`/`stop` take **five**
flags — snapshot, internal channel 0, channels 1–3 — and `pause`/`unpause` take
four. They are not zero-argument commands, which is what this module used to
send.

Two hazards were found, in the order you would meet them.

### 7a. The playback window defaults to the whole buffer

Out of the box: `waveform-start` = 0, `waveform-end` = **500000**, `count` = 1.
Upload 100 samples, start, and it plays the other 499 901 — whatever is in the
buffer — at 20 µs a step. `upload_waveform()` now writes the window as well as
the samples, and `function_start()` refuses a window that reaches past the count.

### 7b. The generator does not read its samples in picometres

The measurement, because this is the one to be believed rather than reasoned
about. A 100-sample sine, ±5 µm about x = 299.9624 µm, in picometres — the unit
`stage.position.command.set` takes. Window set from (0, 500000, 1) to
(0, 99, 100). Sample period set to 10 ms and read back as 9.999999776e-003.
Repeat count 3. Every spot-checked sample read back byte-identical with
`function.waveform.data.get`.

Played, the axis swung over a measured **313.9 µm** — ~31× the 10 µm
peak-to-peak requested — with centre crossings 0.7 to 25 ms apart instead of
1 s. It ended back near 300 µm and `function.command.stop` stopped it.

Not a readback artifact (§6, last paragraph). So the samples are real and their
*unit* is wrong. Two candidates, neither tested:

1. **A DAC code rather than a distance.** 300 µm expressed in picometres
   (3.0e8) overflows a 24-bit code, and wrapping would scatter consecutive
   samples across the travel exactly like this.
2. **An offset rather than an absolute position.**

**The bounded experiment that settles it: a constant waveform** — every sample
the same value — which cannot oscillate whatever the unit, so wherever the stage
parks is the answer. On a lateral axis. Until `WAVEFORM_DATA_UNITS` is filled in,
`function_start()` refuses.

Consequence for planning: the piezo's *hardware-timed* path is one experiment
away, not available. Anything needing trajectory timing tighter than ~1 ms is
blocked on that experiment; anything at 1 Hz with 100 points is served by the
host loop today, with measured margin.

## 8. Corrections to the record

**`reference/npcd-command-set.md` has been regenerated from the controller** (414
names). The previous 178 came from pulling dotted ASCII literals out of the DLL
binary, and that file said plainly that they were a family-wide superset and a
hypothesis to confirm. Confirming moved the count both ways:

- **Hyphens.** Real names carry them — `stage.mode.digital-command.get`,
  `function.waveform-generator.sample-period.get` — and the extraction's regexp
  could not match a hyphen. Whole families were invisible to it:
  `function.waveform-generator.*`, `function.waveform-builder.*`,
  `resonance-detect.*`, `diagnostics-logging.*`. The same blind spot was in
  `piezo_stage._COMMAND_LINE` and in the test that checks every command the
  module sends against the reference — so that test was passing by not seeing
  the names it was meant to check.
- **Names that do not exist here.** `stage.command.digital.scaling.*`,
  `stage.command.analogue.scaling.gain/offset`,
  `identity.software.fpga.version.get`, and the whole `fpga.*`, `peek.*` and
  `system.*` families all answer "Invalid command name".

That last one retracts a claim: **`2026-08-26-piezo-waveform-generator.md` cited
`stage.command.analogue.scaling.gain/offset` alongside
`stage.command.digital.scaling.gain/offset` as "direct evidence" of two
independent command paths.** Those commands do not exist on this controller.
There is a single `stage.command.analogue.scaling.get` (reads 60) and no digital
scaling command at all. The two paths are real — §5 proves it from the mode bits
— but that particular evidence for them was an artifact of reading another
model's command names out of a shared DLL.

Also corrected: the same note said there is **no** `stage.mode.set`, so "the mode
is readable from here but not changeable". Readable, yes. Not changeable, no —
see §5 on `stage.mode-mask.set`.

**`piezo_waveform.OBSERVED` was wrong on both of its numbers.** It carried
0–400 µm travel and a 0.0122 µm step, taken from NIS's analogue abstraction of
this same controller. The travel is 600 µm (§3) and the step is 32 pm (§3) — off
by 200 µm and by a factor of ~380. It is now `CALIBRATED`, with `OBSERVED` kept
as the same object so existing callers and identity checks keep working.

A loose end that follows from it: **NIS's own abstraction is mis-scaled.** Its
device DB maps 0–10 V to 0–400 µm; the controller says 60 µm/V, i.e. 600 µm. If
anyone ever enables the analogue path, NIS's micrometre numbers are wrong by
1.5×. Inert today because `analogue-command` = 0.

## 9. What changed in code

| file | change |
|---|---|
| `hardware/piezo_stage.py` | `WAVEFORM_PROTOCOL` filled in from the controller; `ACCESS_CODES`; `WAVEFORM_DATA_UNITS` gate; `set_position_pm/um`; `travel_pm`; `mode_flags`; `playback_window`; `upload_waveform` implemented (batched, window-setting, verified by readback); `function_start/stop/pause/unpause` send their flags; unit getters no longer called; `get_result` and `unlock` report failures instead of raising `ValueError` |
| `hardware/piezo_waveform.py` | `CALIBRATED` travel 0–600 µm / 32 pm, `OBSERVED` aliased; the "timebase is not known" and "upload refuses" sections replaced with what was measured |
| `config/piezo/run_sine_hold.py` | **new** — the sine → hold-at-peak → release program, with per-phase reporting |
| `reference/npcd-command-set.md` | regenerated from the controller, 414 names |
| `kb/systems/current.md` | piezo entry: driven, characterised, mode question closed, generator hazard recorded |
| `tests/test_piezo_waveform.py` | updated to the measured facts; the hyphen blind spot in the command-name check fixed; `_function_flags` covered. 792 pass |
| `try_hardware.py` | `--resolution-um` default 0.0122 → 32e-6; the confirmation prompt said "in Z" while driving channel 1 |

## 10. Still unknown

1. **The generator's sample unit** (§7b). One constant-waveform run on a lateral
   axis. Everything hardware-timed waits on this.
2. **`iterations` vs `repeat-count`.** Both exist per channel, both were set,
   neither was isolated. `upload_waveform()` leaves both alone unless asked, on
   purpose.
3. **The trigger plumbing.** `function.trigger-inputs.*`,
   `function.trigger-output.*`, `controller.synchronisation.master/slave` — all
   present, none exercised. This is the route to starting the piezo and the
   camera off one edge, which is what
   `2026-08-26-parallel-control-architecture.md` wants.
4. **`snapshot.*`** (19 commands): hardware-timed capture to pair with
   hardware-timed drive. Read the buffer with
   `snapshot.response.data.get channel index`. Untouched.
5. **Super User.** `0xB01DFACE` is in the config file and was never tried;
   whether it exposes `stage.mode.*.set` per bit is unknown, and there is no
   reason to find out yet.
