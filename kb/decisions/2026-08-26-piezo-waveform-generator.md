# 2026-08-26 · The piezo has a hardware waveform generator

> Fourth and last entry from 2026-08-26, after `microscope-config-control`,
> `tweezers-pattern-vs-direct` and `parallel-control-architecture`. It closes
> open item 6 of the third one — the last gap in the timing picture.
>
> **Partly superseded 2026-08-27, when the controller was actually asked.** The
> headline holds — the generator exists, 131 commands at User security level —
> but two supporting claims below do not, and the generator turned out not to be
> usable yet. Read `2026-08-27-piezo-first-light-measured-limits.md` §8 before
> relying on anything here:
>
> - `stage.command.analogue.scaling.gain/offset` and
>   `stage.command.digital.scaling.gain/offset`, cited below as "direct evidence"
>   of two command paths, **do not exist on this controller**. The two paths are
>   real, but the evidence is `stage.mode.digital-command.get` = 1 with
>   `stage.mode.analogue-command.get` = 0 on all three axes.
> - "no `stage.mode.set` ... readable but not changeable" — readable yes, but
>   `stage.mode-mask.set` and `stage.mode-only.set` do exist at User level.
> - The command list this note reasons from was a `strings` extraction that could
>   not match a hyphen, so it missed whole families and included other models'
>   names. `reference/npcd-command-set.md` is now read from the controller.

## Request

The third of the three control surfaces: piezo-stage pattern generation and
control. The decisive question, framed earlier the same day: **does the NPC-D
command set have a waveform/trajectory generator?** If yes the piezo is a
hardware-timed subsystem like the tweezers' AOD trap loop; if no, it is
host-driven and its timing is as soft as a TCP round trip.

## Answer: yes — and it was answerable offline

**`function.*`, an 11-command hardware waveform generator:**

```
function.waveform.data.set / .get          upload the samples
function.waveform.count.set / .get         how many points
function.waveform.iterations.set / .get    repeat count
function.command.start / stop / pause / unpause
function.state.get                         what it is doing
```

The vendor's own examples name the feature, in the DLL library manual §11.1:
`function_setup` "demonstrates using function playback to construct simple
**raster profiles**", and `function_waveform_demo` "demonstrates using the
waveform generator to construct a waveform". So raster profiles are the
documented use case — exactly the piezo pattern generation being asked about.

**How this was established without the controller.** The command-set manual
("NPC-D-6xx0 NanoMechanism Controller Interface Command Set And Control System")
is not in this repo. But the vendor DLL is — `hardware/piezo/vendor/
controller_interface64.dll` — and it carries its command names as ASCII
literals. Pulling the dotted tokens out gives 178 commands in 10 families,
filed with provenance and its caveats in
[`reference/npcd-command-set.md`](../../reference/npcd-command-set.md).

**That list is a superset, not our command set.** One DLL serves the whole
NPC-D family and the library manual says models have "slightly different command
sets, so this allows the DLL to select the relevant commands" — `function.*` is
documented "For NPC-D-6000 controllers" only. So every name is a hypothesis, and
`config/piezo/verify_piezo_commands.py` is the one command that confirms it
against the real controller.

## What else the extraction turned up

| Family | Why it matters |
|---|---|
| `snapshot.*` (11) | Triggered data capture — set channel and count, arm a trigger step, fire, read the block. **Hardware-timed measurement** to pair with the hardware-timed drive. Nothing like it exists on the tweezers |
| `stage.mode.get` | **The query `kb/systems/current.md` has been asking for since 2026-08-19** — which command input the controller acts on. Note there is no `stage.mode.set`: readable here, not changeable |
| `stage.command.analogue.scaling.*` vs `stage.command.digital.scaling.*` | Independent gain and offset per command path. Direct evidence the controller really does take both the analogue input NIS drives on `Dev1/ao2` and the digital one this repo uses |
| `stage.calibration.preset.*` | Named calibration presets with save/load/delete — a calibration-file concept, as on the tweezers |
| `controller.monitor.input.trigger.get`, `controller.synchronisation.master`/`slave.get` | The likely route to starting the piezo and the camera from one edge |
| `stage.pid.*` | Proportional / differential / feedforward gains — the loop is tunable, and that changes step-response settling |

## The decisive difference from the tweezers

**This interface can be read.** `stage.position.measured.get`,
`function.state.get`, `snapshot.response.data.get` — a commanded trajectory here
can be *verified*, not merely assumed. The tweezers' TCP protocol has no query
command at all, which is why the drive there has to be inferred from the images.
So the piezo is the better instrument to put in a timing-critical role, and the
one where read-back verification of the kind `hardware/microscope.py` relies on
actually transfers.

## What was built

| File | Role |
|---|---|
| `reference/npcd-command-set.md` | the 178 extracted commands, by family, with provenance and the superset caveat |
| `hardware/piezo_waveform.py` | sample generation in picometres: `ramp`, `triangle`, `sine`, `staircase`, `raster_pair`; `StageTravel` bounds + quantisation |
| `hardware/piezo_stage.py` | `verify_command_set()` · `describe_family()` · `position_units()` · `stage_mode()` · `function_state/stop/pause/unpause/start` · a refusing `upload_waveform()`; plus an `allow_motion` gate |
| `config/piezo/verify_piezo_commands.py` | read-only discovery: command-set diff, signatures, units, and `--hazard` for the command-path question |
| `tests/test_piezo_waveform.py` | 34 tests, no DLL |

Three deliberate refusals, each for a stated reason:

1. **`upload_waveform()` raises** while `WAVEFORM_PROTOCOL is None`. The argument
   layout of `function.waveform.data.set` is undocumented here — `strings`
   recovers names, not arities — and guessing arguments at a stage that can
   drive an objective into a coverslip is not worth it. Same stance as
   `lunf_power.PROTOCOL`. It still validates the waveform against the travel
   bounds first, so the range check is useful today.
2. **Out-of-travel waveforms raise rather than clip.** Silent clipping is
   precisely the tweezers' trapping-range failure mode — a deformed trajectory
   with no error anywhere — and it produces data that looks fine and is wrong.
3. **A `Waveform` has a length but no duration.** The generator's timebase — the
   rate it advances one sample, and whether that is fixed, divided, or externally
   triggered — is in the manual we do not have, so `duration_s()` requires a
   sample period to be handed in and will not invent one.

`StageTravel.OBSERVED` carries the 0–400 µm / 0.0122 µm figures from the KB but
says in its own comment that those describe the *analogue* path, not this one —
the digital path has its own scaling. Travel is a required argument, not a
default, because a wrong bound is how a generated waveform ends up in an end
stop.

## To settle on the microscope PC

Run `python config/piezo/verify_piezo_commands.py --link sim:/NPC6330 --hazard`
first — the DLL's own simulator, so nothing physical is at risk — then the real
link. It answers, in one pass:

1. **Is `function.*` actually present on this controller?** If not, the piezo is
   host-driven and that must be written down before anything is planned on it.
2. **The parameter signature of `function.waveform.data.set`** → fills in
   `WAVEFORM_PROTOCOL`. Alternative source: the vendor's `function_waveform_demo`
   example, whose code is in the archived SDK (`manual/README.md`).
3. **Position units** — `get_position_pm()` assumes picometres; library manual
   §5.2 says always check.
4. **`stage.mode.get`** and the two scaling pairs → the analogue-path hazard.
5. **The sample timebase.** Not in the DLL manual; look for it in the command
   signatures (a `time`-typed parameter would settle it) or the demo source.
6. **Whether `controller.synchronisation.*` can start the piezo from the same
   trigger as the camera** — the last piece of running all three on one clock.
