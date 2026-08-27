# NPC-D controller command set (extracted, superset)

> **Provenance.** Extracted 2026-08-26 from the vendor DLL shipped in this repo,
> `hardware/piezo/vendor/controller_interface64.dll`
> (md5 `27ef8e1cf7dc83d7fef469ae2e549cbb`), by pulling dotted ASCII literals out of the binary:
>
> ```bash
> strings -n 6 hardware/piezo/vendor/controller_interface64.dll \
>   | grep -E '^[a-z]+\.[a-z0-9.]+$' | sort -u
> ```
>
> One hit was dropped by hand: `identity.stage.part.` with a trailing dot, which
> is the prefix the DLL builds `identity.stage.part.number.get` and friends from,
> not a command. `piezo_stage.reference_commands()` re-parses this file by shape
> (`^[a-z]+(\.[a-z0-9]+)+$`) and would reject it anyway.

## Read this caveat before relying on any name below

**This is a superset, not our controller's command set.** One DLL serves the
whole NPC-D family, and the library manual is explicit that models have
"slightly different command sets, so this allows the DLL to select the relevant
commands" -- the `function.*` family, for instance, is documented as "For
NPC-D-6000 controllers" only. So every name here is a **hypothesis to confirm**,
and the confirmation is one command against the real controller:

```bash
python config/piezo/verify_piezo_commands.py --link sim:/NPC6330
```

which diffs `PiezoStage.find_commands()` against this file and dumps the real
parameter and result signatures for the families that matter.

**Parameter signatures are not here at all** -- `strings` recovers names, not
arities. They live in "NPC-D-6xx0 NanoMechanism Controller Interface Command Set
And Control System", which is **not in this repo** (only the DLL library manual
is). Two ways to get them without it: query the DLL, since
`command_parameters()` / `command_results()` report name, units type and units
per argument -- and library manual 5.2 says applications should *always* check
units rather than assuming picometres, which `get_position_pm()` currently does
-- or read the vendor example `function_waveform_demo`, whose source is in the
archived SDK under `D:\backup\...\experimentalist_installers\manual\`
(manual/README.md).

## 178 commands in 10 families

### `function.*` (11)

**The hardware waveform generator.** Upload samples, set the point count and an iteration count, then start/stop/pause/unpause. `function.state.get` reads back what it is doing. The vendor's own examples name it directly: `function_setup` "demonstrates using function playback to construct simple **raster profiles**" and `function_waveform_demo` "demonstrates using the waveform generator to construct a waveform" (library manual 11.1).

```
function.command.pause
function.command.start
function.command.stop
function.command.unpause
function.state.get
function.waveform.count.get
function.waveform.count.set
function.waveform.data.get
function.waveform.data.set
function.waveform.iterations.get
function.waveform.iterations.set
```

### `stage.*` (44)

Position command/measured, PID gains, named calibration presets, and -- separately -- `stage.command.analogue.scaling.*` vs `stage.command.digital.scaling.*`, which is direct evidence the controller takes both an analogue command input (the one NIS drives on Dev1/ao2) and a digital one (this DLL), with independent gain and offset. `stage.mode.get` exists with **no** matching set: the input mode is readable but not settable from here.

```
stage.calibration.preset.current.get
stage.calibration.preset.default.get
stage.calibration.preset.default.save
stage.calibration.preset.delete
stage.calibration.preset.exists
stage.calibration.preset.load
stage.calibration.preset.name.get
stage.calibration.preset.name.set
stage.calibration.preset.save
stage.calibration.status.get
stage.command.analogue.scaling.gain.get
stage.command.analogue.scaling.gain.set
stage.command.analogue.scaling.get
stage.command.analogue.scaling.offset.get
stage.command.analogue.scaling.offset.set
stage.command.digital.scaling.gain.get
stage.command.digital.scaling.gain.set
stage.command.digital.scaling.offset.get
stage.command.digital.scaling.offset.set
stage.mode.get
stage.pid.differential.gain.get
stage.pid.differential.gain.set
stage.pid.feedforward.gain.get
stage.pid.feedforward.gain.set
stage.pid.proportional.gain.get
stage.pid.proportional.gain.set
stage.position.actuator.command.get
stage.position.actuator.measured.get
stage.position.command.get
stage.position.command.set
stage.position.linearise.correction.get
stage.position.measured.get
stage.position.output.scaling.gain.get
stage.position.output.scaling.gain.set
stage.position.output.scaling.offset.get
stage.position.output.scaling.offset.set
stage.position.scaling.gain.get
stage.position.scaling.gain.set
stage.position.scaling.offset.get
stage.position.scaling.offset.set
stage.stepped.input.enable.get
stage.stepped.input.enable.set
stage.stepped.output.select.get
stage.stepped.output.select.set
```

### `snapshot.*` (11)

Triggered data capture: set a channel and a capture count, arm a trigger step, fire, then read the block back. Hardware-timed *measurement* to go with the hardware-timed drive above.

```
snapshot.capture.count.get
snapshot.capture.count.set
snapshot.fire
snapshot.response.channel.get
snapshot.response.channel.set
snapshot.response.count.get
snapshot.response.count.set
snapshot.response.data.get
snapshot.stop
snapshot.trigger.step.get
snapshot.trigger.step.set
```

### `scope.*` (1)

A single measurement read; its relationship to the snapshot family is unknown.

```
scope.measurement.get
```

### `controller.*` (27)

Channel count, status, reset, security, fan, and a large monitor group (supply rails, heatsink temperature, spare test points). Two entries matter for timing: `controller.monitor.input.trigger.get` and `controller.synchronisation.master`/`slave.get`.

```
controller.channels.get
controller.channels.set
controller.diagnostics.log.controller.settings
controller.diagnostics.log.snapshot.data
controller.diagnostics.log.snapshot.settings
controller.diagnostics.log.stage.settings
controller.fan.mode.get
controller.fan.mode.set
controller.monitor.input.spare.get
controller.monitor.input.stepped.a.get
controller.monitor.input.stepped.b.get
controller.monitor.input.trigger.get
controller.monitor.reference.10v.get
controller.monitor.reference.2v5.get
controller.monitor.reference.5v.get
controller.monitor.spare.ff.get
controller.monitor.spare.tp70.get
controller.monitor.spare.tp71.get
controller.monitor.supply.2v5.get
controller.monitor.temperature.heatsink.get
controller.reset
controller.security.lock
controller.security.user.get
controller.security.user.set
controller.status.get
controller.synchronisation.master.get
controller.synchronisation.slave.get
```

### `protection.*` (12)

Overcurrent and thermal interlocks, with enable and status. Read these before trusting a long unattended scan.

```
protection.fan.mode.get
protection.fan.mode.set
protection.fan.state.get
protection.overcurrent.current.get
protection.overcurrent.enable.get
protection.overcurrent.enable.set
protection.overcurrent.status.get
protection.thermal.enable.get
protection.thermal.enable.set
protection.thermal.heatsink.temperature.get
protection.thermal.psu.temperature.get
protection.thermal.status.get
```

### `fpga.*` (29)

Low-level FPGA registers -- ADC enables and delays, position-monitor acquisition, run state. Not an application-level interface; do not write these without the command-set manual.

```
fpga.ai.adc.delay.get
fpga.ai.adc.delay.set
fpga.ai.adc.enable.get
fpga.ai.adc.enable.set
fpga.ai.read
fpga.debug.mode.get
fpga.debug.mode.set
fpga.ff.adc.delay.get
fpga.ff.adc.delay.set
fpga.ff.adc.enable.get
fpga.ff.adc.enable.set
fpga.ff.read
fpga.posmon.120khz.enable.get
fpga.posmon.120khz.enable.set
fpga.posmon.adc.acquire.get
fpga.posmon.adc.acquire.set
fpga.posmon.adc.enable.get
fpga.posmon.adc.enable.set
fpga.posmon.adc.select.get
fpga.posmon.adc.select.set
fpga.posmon.read
fpga.psu.delay.get
fpga.psu.delay.set
fpga.register.get
fpga.register.set
fpga.run.get
fpga.run.set
fpga.status.get
fpga.version.get
```

### `identity.*` (36)

Part numbers, serials, calibration and manufacture dates, firmware version. `piezo_stage.identity()` already uses `identity.software.version.get`.

```
identity.hardware.caldate.get
identity.hardware.caldate.set
identity.hardware.mandate.get
identity.hardware.mandate.set
identity.hardware.part.get
identity.hardware.part.number.get
identity.hardware.part.number.set
identity.hardware.part.prefix.get
identity.hardware.part.prefix.set
identity.hardware.part.set
identity.hardware.part.suffix.get
identity.hardware.part.suffix.set
identity.hardware.serial.get
identity.hardware.serial.set
identity.software.fpga.version.get
identity.software.part.get
identity.software.reldate.get
identity.software.version.get
identity.stage.actuator.get
identity.stage.actuator.set
identity.stage.axisid.gamma
identity.stage.axisid.get
identity.stage.axisid.phi
identity.stage.axisid.set
identity.stage.axisid.theta
identity.stage.axisid.x
identity.stage.axisid.y
identity.stage.axisid.z
identity.stage.caldate.get
identity.stage.caldate.set
identity.stage.mandate.get
identity.stage.mandate.set
identity.stage.part.get
identity.stage.part.set
identity.stage.serial.get
identity.stage.serial.set
```

### `peek.*` (5)

Raw memory reads (byte/short/long/float/double). Diagnostic only.

```
peek.byte
peek.double
peek.float
peek.long
peek.short
```

### `system.*` (2)

Raw read and write. Diagnostic only.

```
system.read
system.write
```
