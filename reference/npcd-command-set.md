# NPC-D controller command set (read from the controller)

> **Provenance.** Read off the live controller on **2026-08-27** over **COM4** --
> Prior/Queensgate NPC-D, firmware **6.7.8**, 3 channels, stage SP-XYZ-600 serial
> 107866 -- with `PiezoStage.find_commands()`, at security level **User**: 414 commands.
>
> ```bash
> python config/piezo/verify_piezo_commands.py --link COM4 --unlock 0xDEC0DED
> ```

## The security level decides what exists

`find_commands()` reports what the **current** security level permits, not what the
controller can do. Locked (`security = None`) it answers **188** commands, of which
exactly **one** is a `.set`: `controller.security.user.set`.
`stage.position.command.set` is not merely unavailable at that level, it is
*invisible* -- asking for its signature answers "Invalid command name", which reads
like "this controller cannot do it" and is not what it means. Raise the level and
the set becomes the 414 commands below.

The access codes are fixed per-level vendor constants and they live in the vendor
GUI's own config file, `C:/Program Files (x86)/NanoBench 6000/data/config.ini`,
section `[SecurityLevels]`: `User = DEC0DED`, `Super User = B01DFACE`. The
controller parses the code as a number, so **the `0x` prefix is required** --
`DEC0DED` answers "Not enough parameters for command", `0xDEC0DED` returns `User`.
The level is controller-side state that outlives the session; the vendor GUI leaves
it raised.

**This file is a User-level snapshot, and there is one more notch on the level.**
`ACCESS_CODES` carries `super-user = 0xB01DFACE`, straight from the same config
file, and it has never been sent. So "414 commands" is a floor, not a total. The
sweep that would settle it, and the correction it would produce, are queued in
[`kb/systems/piezo-superuser-RUN-FIRST.md`](../kb/systems/piezo-superuser-RUN-FIRST.md);
the tool is `config/piezo/dump_command_set.py`.

## What this replaces

An earlier version of this file held 178 names pulled out of the DLL binary with
`strings`, described there as "a superset across the NPC-D family, not this
controller's command set" and "a hypothesis to confirm". Confirming it moved the
count both ways, so the extraction was not merely incomplete:

- **Hyphens.** The real names carry them -- `stage.mode.digital-command.get`,
  `function.waveform-generator.sample-period.get` -- and the extraction's own
  regexp could not match a hyphen, so that whole half of the set was invisible to
  it. Entire families were missed: `function.waveform-generator.*`,
  `function.waveform-builder.*`, `resonance-detect.*`, `diagnostics-logging.*`.
- **Names that do not exist here.** `stage.command.digital.scaling.gain/offset`,
  `stage.command.analogue.scaling.gain/offset`, `identity.software.fpga.version.get`
  and the whole `fpga.*`, `peek.*` and `system.*` families answer "Invalid command
  name" on this controller. They belong to other models, or to a service interface.
  **Unconfirmed, and confirmable:** an "Invalid command name" is exactly what a
  *gated* command answers too -- that is how `stage.position.command.set` read at
  the base level -- so these may be gated at User rather than absent. Every one of
  them is re-asked at each level by `config/piezo/dump_command_set.py` §4.

Parameter and result signatures are not in this list -- `find_commands()` returns
names. Read them per command with `PiezoStage.command_parameters()` /
`command_results()`; the ones this repo depends on are recorded in
`piezo_stage.WAVEFORM_PROTOCOL`. Do **not** ask those calls for units:
`GetCommandParameterUnitsType` and its siblings access-violate (see that method's
docstring), and on the runs where they answer they answer empty.

## 414 commands in 9 families

### `stage.*` (161, 8 settable)

Position command/measured, servo mode, PID, calibration presets, travel bounds, and the stepped (quadrature) input/output. Only 8 of the 161 are `.set`. Two that matter: `stage.position.command.set channel value` is the direct move, in picometres, and `stage.position.calibrated-range.minimum/maximum.get` is the real travel -- 0 and 6.0e8 pm on all three axes here.

The mode is *readable per bit*: `stage.mode.digital-command.get`, `.analogue-command.get`, `.closed-loop.get`, `.is-sensor-only.get`, `.freeze-servo-output.get`. There is no per-bit setter; what exists is `stage.mode-mask.set` / `stage.mode-only.set`, which write the raw mode word, plus `stage.mode.freeze-servo-output.set` and `stage.mode.analogue-command.input-select.set`. Note there is no `stage.command.digital.scaling.*` on this controller at all -- only `stage.command.analogue.scaling.get` (reads 60, consistent with 600 um over a 10 V input). The earlier claim of two independent scalings came from the strings extraction and does not hold here.

```
stage.active-damping.accel.deadband.get
stage.active-damping.accel.gain.get
stage.active-damping.enable.get
stage.active-damping.velocity.deadband.get
stage.active-damping.velocity.gain.get
stage.calibration.preset.configuration-id.get
stage.calibration.preset.current.get
stage.calibration.preset.default.get
stage.calibration.preset.default.save
stage.calibration.preset.exists
stage.calibration.preset.is-factory.get
stage.calibration.preset.load
stage.calibration.preset.name.get
stage.calibration.status.get
stage.closed-loop.pid.accel.feedforward.gain.get
stage.closed-loop.pid.accel.integral.time-constant.get
stage.closed-loop.pid.accel.proportional.gain.get
stage.closed-loop.pid.accel.proportional.set-point-weighting.get
stage.closed-loop.pid.control.get
stage.closed-loop.pid.position.differential.gain.get
stage.closed-loop.pid.position.feedforward.gain.get
stage.closed-loop.pid.position.integral.time-constant.get
stage.closed-loop.pid.position.proportional.gain.get
stage.closed-loop.pid.position.proportional.set-point-weighting.get
stage.closed-loop.pid.velocity.differential.gain.get
stage.closed-loop.pid.velocity.feedforward.gain.get
stage.closed-loop.pid.velocity.integral.time-constant.get
stage.closed-loop.pid.velocity.proportional.gain.get
stage.closed-loop.pid.velocity.proportional.set-point-weighting.get
stage.command-trajectory.braking-deceleration.get
stage.command-trajectory.enable.get
stage.command-trajectory.launch-acceleration.get
stage.command-trajectory.speed.get
stage.command.analogue.high-pass-filter.bode.gain.get
stage.command.analogue.high-pass-filter.bode.phase.get
stage.command.analogue.high-pass-filter.gain.get
stage.command.analogue.high-pass-filter.q.get
stage.command.analogue.high-pass-filter.time-constant.get
stage.command.analogue.low-pass-filter.bode.gain.get
stage.command.analogue.low-pass-filter.bode.phase.get
stage.command.analogue.low-pass-filter.enable.get
stage.command.analogue.low-pass-filter.filter-order.get
stage.command.analogue.low-pass-filter.time-constant.get
stage.command.analogue.scaling.get
stage.command.digital.high-pass-filter.bode.gain.get
stage.command.digital.high-pass-filter.bode.phase.get
stage.command.digital.high-pass-filter.gain.get
stage.command.digital.high-pass-filter.q.get
stage.command.digital.high-pass-filter.time-constant.get
stage.in-position.error-threshold.get
stage.in-position.lpf.time-constant.get
stage.in-position.window-filter.size.get
stage.in-position.window-filter.valid-threshold.get
stage.mode-mask.set
stage.mode-only.get
stage.mode-only.set
stage.mode.analogue-command.get
stage.mode.analogue-command.input-2-invert.get
stage.mode.analogue-command.input-invert.get
stage.mode.analogue-command.input-select.get
stage.mode.analogue-command.input-select.set
stage.mode.closed-loop.get
stage.mode.digital-command.get
stage.mode.freeze-servo-output.disable
stage.mode.freeze-servo-output.enable
stage.mode.freeze-servo-output.get
stage.mode.freeze-servo-output.set
stage.mode.get
stage.mode.in-position-output-select.get
stage.mode.is-sensor-only.get
stage.multi-axis.spacial-correction.2d.enable.get
stage.multi-axis.spacial-correction.2d.status.active.get
stage.multi-axis.spacial-correction.3d.enable.get
stage.multi-axis.spacial-correction.3d.status.active.get
stage.notch-filter.bode.gain.get
stage.notch-filter.bode.phase.get
stage.notch-filter.extended.q.get
stage.notch-filter.extended.time-constant.get
stage.notch-filter.filter-location.get
stage.notch-filter.filter-type.get
stage.notch-filter.q.get
stage.notch-filter.second-filter-q.get
stage.notch-filter.second-filter-time-constant.get
stage.notch-filter.time-constant.get
stage.open-loop.gain.get
stage.open-loop.offset.get
stage.open-loop.output-offset-gain.get
stage.pid.differential.gain.get
stage.pid.differential.time-constant.get
stage.pid.feedforward.gain.get
stage.pid.integral.error-magnitude.max.get
stage.pid.integral.time-constant.get
stage.pid.proportional.gain.get
stage.pid.proportional.set-point-weighting.get
stage.position.absolute-command.get
stage.position.absolute-command.set
stage.position.calibrated-range.maximum.get
stage.position.calibrated-range.minimum.get
stage.position.calibrated-range.range.get
stage.position.command.get
stage.position.command.set
stage.position.low-pass-filter.bode.gain.get
stage.position.low-pass-filter.bode.phase.get
stage.position.low-pass-filter.enable.get
stage.position.low-pass-filter.filter-location.get
stage.position.low-pass-filter.filter-order.get
stage.position.low-pass-filter.q.get
stage.position.low-pass-filter.time-constant.get
stage.position.measured.get
stage.position.measured.is-in-calibrated-range.get
stage.position.measured.is-readable.get
stage.position.output.low-pass-filter.bode.combined-gain.get
stage.position.output.low-pass-filter.bode.combined-phase.get
stage.position.output.low-pass-filter.bode.gain.get
stage.position.output.low-pass-filter.bode.phase.get
stage.position.output.low-pass-filter.enable.get
stage.position.output.low-pass-filter.filter-order.get
stage.position.output.low-pass-filter.time-constant.get
stage.position.stepped-command.get
stage.position.stepped-command.increment
stage.position.stepped-command.set
stage.position.stepped-command.step-size.get
stage.position.stepped-command.steps.get
stage.position.stepped-command.steps.increment
stage.position.stepped-command.steps.set
stage.position.velocity-accel-filter.bode.accel.combined-gain.get
stage.position.velocity-accel-filter.bode.accel.combined-phase.get
stage.position.velocity-accel-filter.bode.gain.get
stage.position.velocity-accel-filter.bode.phase.get
stage.position.velocity-accel-filter.bode.velocity.combined-gain.get
stage.position.velocity-accel-filter.bode.velocity.combined-phase.get
stage.position.velocity-accel-filter.time-constant.get
stage.range.auto-balance.in-progress.get
stage.range.auto-balance.measurement-sweep.trigger
stage.range.auto-balance.select-on-startup.get
stage.range.auto-balance.trigger
stage.range.closed-loop-command.maximum.get
stage.range.closed-loop-command.minimum.get
stage.range.closed-loop.maximum.get
stage.range.closed-loop.minimum.get
stage.range.closed-loop.range.get
stage.status.in-position.lpf-confirmed.get
stage.status.in-position.unconfirmed.get
stage.status.in-position.window-filter-confirmed.get
stage.status.servo-output-at-limits.get
stage.status.stage-connected.get
stage.status.stage-moving.get
stage.stepped.input.debounce-time.get
stage.stepped.input.enable.get
stage.stepped.input.is-quadrature.get
stage.stepped.input.reverse-direction.get
stage.stepped.input.step-direction.is-rising-edge.get
stage.stepped.output.is-quadrature.get
stage.stepped.output.quadrature.hold-time.get
stage.stepped.output.reverse-direction.get
stage.stepped.output.select.get
stage.stepped.output.send-full-value.get
stage.stepped.output.step-direction.hold-time.get
stage.stepped.output.step-direction.is-rising-edge.get
stage.stepped.output.step-direction.settle-time.get
stage.stepped.output.step-size.get
```

### `function.*` (131, 52 settable)

**The hardware waveform generator, and it is real on this controller.** Two interfaces live here. `function.waveform.*` is the sample buffer: `data.set channel index value` one sample at a time, `count.set` samples per iteration, `sample-period.set` in seconds (2.0e-5 out of the box, the servo clock), `iterations.set`, `repeat-count.set` where 0 means forever. `function.waveform-generator.*` is a second, higher-level interface that describes a trajectory as *segments* -- start/end position, start/end velocity, duration, type -- with per-segment trigger outputs; it is the one to use for a long smooth path, because it does not cost one command per sample. `function.waveform-builder.staircase.*` builds a staircase from parameters. `function.command.start/stop` take five flags (snapshot, internal channel 0, channels 1-3), `pause/unpause` take four. `function.trigger-inputs.*` and `function.trigger-output.*` are the route to starting the piezo and the camera off one edge -- present, not yet exercised.

```
function.command.pause
function.command.soft-stop
function.command.start
function.command.stop
function.command.unpause
function.state.get
function.trigger-inputs.enabled.disable-inputs
function.trigger-inputs.enabled.enable-inputs
function.trigger-inputs.enabled.get
function.trigger-inputs.pause.get
function.trigger-inputs.pause.set
function.trigger-inputs.soft-stop.get
function.trigger-inputs.soft-stop.set
function.trigger-inputs.start.get
function.trigger-inputs.start.set
function.trigger-inputs.stop.get
function.trigger-inputs.stop.set
function.trigger-inputs.unpause.get
function.trigger-inputs.unpause.set
function.trigger-output.fire
function.trigger-output.pulse-time.get
function.trigger-output.pulse-time.set
function.waveform-builder.staircase.check
function.waveform-builder.staircase.clear
function.waveform-builder.staircase.hold-duration.get
function.waveform-builder.staircase.hold-duration.set
function.waveform-builder.staircase.is-bidirectional.get
function.waveform-builder.staircase.is-bidirectional.set
function.waveform-builder.staircase.prepare
function.waveform-builder.staircase.prepare-start
function.waveform-builder.staircase.repeat-count.get
function.waveform-builder.staircase.repeat-count.set
function.waveform-builder.staircase.return-hold-duration.get
function.waveform-builder.staircase.return-hold-duration.set
function.waveform-builder.staircase.return-step-duration.get
function.waveform-builder.staircase.return-step-duration.set
function.waveform-builder.staircase.start-hold-duration.get
function.waveform-builder.staircase.start-hold-duration.set
function.waveform-builder.staircase.start-position.get
function.waveform-builder.staircase.start-position.set
function.waveform-builder.staircase.start-step-duration.get
function.waveform-builder.staircase.start-step-duration.set
function.waveform-builder.staircase.step-distance.get
function.waveform-builder.staircase.step-distance.set
function.waveform-builder.staircase.step-duration.get
function.waveform-builder.staircase.step-duration.set
function.waveform-builder.staircase.steps.get
function.waveform-builder.staircase.steps.set
function.waveform-builder.staircase.trigger-output.delay.get
function.waveform-builder.staircase.trigger-output.delay.set
function.waveform-builder.staircase.trigger-output.trigger.get
function.waveform-builder.staircase.trigger-output.trigger.set
function.waveform-generator.check-waveform
function.waveform-generator.clear
function.waveform-generator.count.get
function.waveform-generator.count.set
function.waveform-generator.failed-at-segment-index.get
function.waveform-generator.failure-cause.get
function.waveform-generator.prepare-start
function.waveform-generator.prepare-waveform
function.waveform-generator.prepare-waveform-status.get
function.waveform-generator.repeat-count.get
function.waveform-generator.repeat-count.set
function.waveform-generator.repeat-end.get
function.waveform-generator.repeat-end.set
function.waveform-generator.repeat-start.get
function.waveform-generator.repeat-start.set
function.waveform-generator.sample-period.get
function.waveform-generator.sample-period.set
function.waveform-generator.segment.continue-position-velocity.get
function.waveform-generator.segment.continue-position-velocity.set
function.waveform-generator.segment.duration.get
function.waveform-generator.segment.end-position.get
function.waveform-generator.segment.end-velocity.get
function.waveform-generator.segment.parameter.get
function.waveform-generator.segment.parameter.set
function.waveform-generator.segment.start-position.get
function.waveform-generator.segment.start-velocity.get
function.waveform-generator.segment.trigger-output.during-trigger-count.get
function.waveform-generator.segment.trigger-output.during-trigger-count.set
function.waveform-generator.segment.trigger-output.during-trigger-offset.get
function.waveform-generator.segment.trigger-output.during-trigger-offset.set
function.waveform-generator.segment.trigger-output.during-trigger.get
function.waveform-generator.segment.trigger-output.during-trigger.set
function.waveform-generator.segment.trigger-output.end-trigger-offset.get
function.waveform-generator.segment.trigger-output.end-trigger-offset.set
function.waveform-generator.segment.trigger-output.end-trigger.get
function.waveform-generator.segment.trigger-output.end-trigger.set
function.waveform-generator.segment.trigger-output.start-trigger-offset.get
function.waveform-generator.segment.trigger-output.start-trigger-offset.set
function.waveform-generator.segment.trigger-output.start-trigger.get
function.waveform-generator.segment.trigger-output.start-trigger.set
function.waveform-generator.segment.type.get
function.waveform-generator.segment.type.set
function.waveform-generator.soft-stop-at-end.get
function.waveform-generator.soft-stop-at-end.set
function.waveform-generator.trigger-output.end-trigger.get
function.waveform-generator.trigger-output.end-trigger.set
function.waveform-generator.trigger-output.start-trigger.get
function.waveform-generator.trigger-output.start-trigger.set
function.waveform-generator.waveform-duration.get
function.waveform.command-transition.get
function.waveform.command-transition.set
function.waveform.count.get
function.waveform.count.set
function.waveform.data.get
function.waveform.data.set
function.waveform.iterations.get
function.waveform.iterations.set
function.waveform.repeat-count.get
function.waveform.repeat-count.set
function.waveform.repeat-end.get
function.waveform.repeat-end.set
function.waveform.repeat-start.get
function.waveform.repeat-start.set
function.waveform.sample-period.get
function.waveform.sample-period.set
function.waveform.soft-stop-at-end.get
function.waveform.soft-stop-at-end.set
function.waveform.steps-per-sample.get
function.waveform.steps-per-sample.set
function.waveform.steps-per-trigger-out-pulse.get
function.waveform.steps-per-trigger-out-pulse.set
function.waveform.trigger-at-sample-end.get
function.waveform.trigger-at-sample-end.set
function.waveform.trigger-out-event.get
function.waveform.trigger-out-event.set
function.waveform.waveform-end.get
function.waveform.waveform-end.set
function.waveform.waveform-start.get
function.waveform.waveform-start.set
```

### `resonance-detect.*` (22, 0 settable)

Drives the stage to find its mechanical resonance. Not exercised -- it moves the stage by design.

```
resonance-detect.capture.commanded-position.magnitude.get
resonance-detect.capture.error.magnitude.get
resonance-detect.capture.measured-position.magnitude.get
resonance-detect.capture.peak-error.frequency.get
resonance-detect.capture.peak-error.magnitude.get
resonance-detect.capture.status.get
resonance-detect.capture.trigger
resonance-detect.frequency-range.maximum.get
resonance-detect.frequency-range.resolution.get
resonance-detect.protective-shutdown.capture.commanded-position.magnitude.get
resonance-detect.protective-shutdown.capture.error.magnitude.get
resonance-detect.protective-shutdown.capture.measured-position.magnitude.get
resonance-detect.protective-shutdown.capture.peak-error.frequency.get
resonance-detect.protective-shutdown.capture.peak-error.magnitude.get
resonance-detect.protective-shutdown.capture.status.get
resonance-detect.protective-shutdown.clear
resonance-detect.protective-shutdown.enable.get
resonance-detect.protective-shutdown.error-threshold.get
resonance-detect.protective-shutdown.error-time.get
resonance-detect.protective-shutdown.frequency-range.maximum.get
resonance-detect.protective-shutdown.frequency-range.minimum.get
resonance-detect.protective-shutdown.state.get
```

### `diagnostics-logging.*` (21, 0 settable)

Dump controller, stage and snapshot settings to the vendor log. Diagnostic only.

```
diagnostics-logging.controller.since-last-service.current.max-negative.get
diagnostics-logging.controller.since-last-service.current.max-positive.get
diagnostics-logging.controller.since-last-service.fan-on.time.get
diagnostics-logging.controller.since-last-service.fan-on.total.get
diagnostics-logging.controller.since-last-service.power-on.time.get
diagnostics-logging.controller.since-last-service.power-on.total.get
diagnostics-logging.controller.since-last-service.shutdowns.total.get
diagnostics-logging.controller.since-last-service.temperature.max.get
diagnostics-logging.controller.this-power-on.current.max-negative.get
diagnostics-logging.controller.this-power-on.current.max-positive.get
diagnostics-logging.controller.this-power-on.fan-on.time.get
diagnostics-logging.controller.this-power-on.fan-on.total.get
diagnostics-logging.controller.this-power-on.power-on.time.get
diagnostics-logging.controller.this-power-on.power-on.total.get
diagnostics-logging.controller.this-power-on.shutdowns.total.get
diagnostics-logging.controller.this-power-on.temperature.max.get
diagnostics-logging.stage.since-last-service.current.max-negative.get
diagnostics-logging.stage.since-last-service.current.max-positive.get
diagnostics-logging.stage.since-last-service.power-on.time.get
diagnostics-logging.stage.since-last-service.power-on.total.get
diagnostics-logging.stage.since-last-service.shutdowns.total.get
```

### `protection.*` (21, 0 settable)

Overcurrent and thermal interlocks with status. Read before a long unattended scan; both read 0x00000000 here.

```
protection.fan.heatsink.off-temperature.get
protection.fan.heatsink.on-temperature.get
protection.fan.mode.get
protection.fan.psu.off-temperature.get
protection.fan.psu.on-temperature.get
protection.fan.state.get
protection.overcurrent.current.get
protection.overcurrent.detect-threshold.get
protection.overcurrent.detect-time.get
protection.overcurrent.status.get
protection.thermal.heatsink.overtemperature-clear-threshold.get
protection.thermal.heatsink.overtemperature-clear-time.get
protection.thermal.heatsink.overtemperature-detect-threshold.get
protection.thermal.heatsink.overtemperature-detect-time.get
protection.thermal.heatsink.temperature.get
protection.thermal.psu.overtemperature-clear-threshold.get
protection.thermal.psu.overtemperature-clear-time.get
protection.thermal.psu.overtemperature-detect-threshold.get
protection.thermal.psu.overtemperature-detect-time.get
protection.thermal.psu.temperature.get
protection.thermal.status.get
```

### `snapshot.*` (19, 7 settable)

Triggered data capture -- the hardware-timed *measurement* to pair with the hardware-timed drive above. Set a response channel and a capture count, arm a trigger step or a trigger input, `snapshot.fire`, then read the block back with `snapshot.response.data.get channel index`.

```
snapshot.capture.count.get
snapshot.capture.count.set
snapshot.fire
snapshot.response.count.get
snapshot.response.data-select.get
snapshot.response.data.get
snapshot.stop
snapshot.trigger-inputs.start-delay.get
snapshot.trigger-inputs.start-delay.set
snapshot.trigger-inputs.start.get
snapshot.trigger-inputs.start.set
snapshot.trigger-inputs.stop.get
snapshot.trigger-inputs.stop.set
snapshot.trigger.from-target.get
snapshot.trigger.from-target.set
snapshot.trigger.step.get
snapshot.trigger.step.set
snapshot.trigger.to-target.get
snapshot.trigger.to-target.set
```

### `identity.*` (14, 0 settable)

Part numbers, serials, dates, firmware. This controller: firmware 6.7.8, stage `SP-XYZ-600` serial 107866, axis ids x, y, z on channels 1, 2, 3.

```
identity.hardware.bootloader-version.get
identity.hardware.caldate.get
identity.hardware.mandate.get
identity.hardware.part.get
identity.hardware.platform-version.get
identity.hardware.serial.get
identity.software.part.get
identity.software.reldate.get
identity.software.version.get
identity.stage.axisid.get
identity.stage.caldate.get
identity.stage.mandate.get
identity.stage.part.get
identity.stage.serial.get
```

### `scope.*` (13, 6 settable)

Route an internal signal to an output or into the snapshot buffer (`scope.routing.to-output.set`, `scope.routing.to-snapshot.set`) with its own gain and offset, and read one measurement directly.

```
scope.data-select.get
scope.data-select.set
scope.measurement.get
scope.routing.output-scaling.gain.get
scope.routing.output-scaling.gain.set
scope.routing.output-scaling.offset-voltage.get
scope.routing.output-scaling.offset-voltage.set
scope.routing.output-scaling.offset.get
scope.routing.output-scaling.offset.set
scope.routing.to-output.get
scope.routing.to-output.set
scope.routing.to-snapshot.get
scope.routing.to-snapshot.set
```

### `controller.*` (12, 1 settable)

Channel count, status, security, sampling time, TCP/IP settings. Two entries carry more weight than their size suggests: `controller.sampling-time.get` reads 1.999999949e-005, the 20 us servo period that is also the waveform generator's default step; and `controller.security.user.set` is the one `.set` command that exists at the base security level.

```
controller.analogue-inputs.get
controller.channels.get
controller.sampling-time.get
controller.security.lock
controller.security.user.get
controller.security.user.set
controller.sensor-only.get
controller.status.get
controller.synchronisation.master.get
controller.synchronisation.slave.get
controller.tcpip-comms.ip-address.get
controller.tcpip-comms.tcp-port.get
```
