---
id: 2026-09-10-lens-3-review-outcomes
question: "What did the gate-by-gate review of lens 3 change, and should G12a be removed because its disk-bandwidth input is carried as assumed?"
date: 2026-09-10
status: current
---

# 2026-09-10 · Lens 3 review — five outcomes

Decided by KH during the gate-by-gate committee review. No gate was removed.

## 1. G12a's action text named a lever that does not work

It said *"Reduce ROI, frame rate, or stream count."* At the readout limit —
which is where this camera runs — **reducing ROI height buys nothing**:

```
R = W · H · 2 · f      and      f = 1/(H · row_time)
⇒  R = W · 2 / row_time            ← height cancels
```

Measured across an 8× range of heights, all identical:

| ROI | fps | data rate |
|---|---|---|
| 512×1024 | 277 | 290 MB/s |
| 512×512 | 553 | 290 MB/s |
| 512×256 | 1106 | 290 MB/s |
| 512×128 | 2212 | 290 MB/s |
| **192**×512 | 553 | **109 MB/s** |

Shrinking the height to go faster is the natural thing to do on a rolling
shutter, and it is exactly the move that does not help here. The action text now
says **width**, shows the cancellation, and notes that height is lens 2's
frame-rate knob rather than a data-rate one.

## 2. G12b consumes lens 2's `fps_usable_max`, and the field was renamed

`detector_max_fps` → **`usable_fps_ceiling`** (CLI: `--detector-max-fps` →
`--usable-fps`). The old name invited the hardware maximum, and lens 2 now
reports three numbers — `fps_hardware_max`, `fps_at_duty_limit`,
`fps_usable_max`. Passing the hardware figure lets G12b clear a rate **G8 would
refuse**, because on this camera the fastest *realizable* rate and the fastest
rate with an acceptable duty cycle are different numbers. The field wants the
min, which is `fps_usable_max`.

## 3. A `bias` gate warning at margin 10.00 printed as headroom

`fps_provenance.requested` and `pixel_container.unconfirmed` both warn while
reporting `MAX_MARGIN`, because their penalty sits on the **evidence axis** —
they land in `assumed_inputs` and block `advances` — rather than against a
threshold. That is the same structure as the 2026-09-09 blocking-threshold
decision (*charge the approximation once, on the evidence axis*) and it is
correct.

**What was wrong was the display.** In the margin list a warning printed as
`10.00` with a full bar, which reads as cleared — the one thing this repository
refuses to let a margin do. Those entries now print:

```
    ungraded  fps_provenance.requested     <- warns, see findings
```

`MAX_MARGIN` on a warning means "no threshold was crossed", not "lots of room",
and the two now look different.

⚠ **The same shape exists in lens 4 (`count_in_field`) and lens 8
(`vibration`), and only lens 3's renderer was changed.** Each lens prints its
own margins by design — there is no shared reporter — so applying this
consistently is a follow-up, not part of this change.

## 4. G12a stays. Its input is measured; only its *location* is unconfirmed

The question was whether to delete the gate because `disk_bandwidth_mb_s` is
carried as `assumed`. **No**, and the premise needs correcting.

`kb/calibrations/disk-bandwidth.yaml` records a real measurement: random-data
write plus `fsync` — so OS write-behind cannot inflate it — 4 GB in 19.3 s =
**206.8 MB/s**, `verified: true`, taken on the microscope PC, by
`calibration.disk_bandwidth.measure_write_bandwidth`. The single caveat is in
its own note: nobody has confirmed that `D:\Kyu Hwan Choi\_bench` is the folder
Micro-Manager streams multi-page TIFFs into for this system.

So this is a **location** question, not a measurement question, and G12a is the
gate that catches the failure mode that is silent and destroys the data
(`docs/06 §C5`: frames are discarded with no error raised). Deleting it to
escape an `assumed` tier would remove the check and keep the risk.

**How to confirm, and it is one command.** Read the save directory off a recent
acquisition's own metadata, then:

```
python -m calibration.cli disk-bandwidth "<MM save directory>" --size-gb 4
```

The gate's `assumed_inputs` text now carries that command and states the
distinction, so the next reader is told what closes it instead of being told the
number is doubtful.

## 5. G13d's RAM ceiling raised 32 GB → 128 GB

Authorized by KH 2026-09-10. Half of the machine's 255.65 GB.

**Still an authorization, not a measurement** — that is the distinction the
2026-08-19 note made and this one keeps. How much RAM the OS, MM and the
DMD/piezo/tweezers control processes hold during an acquisition has never been
measured, and that remains an open checkbox in
`2026-08-12-ram-buffer-detour-for-disk-bandwidth.md`. **What changed is the
operator's tolerance, not the evidence.**

For the drag calibration at 136 MB/s this moves the RAM-capture ceiling from
**3.9 minutes to 15.7 minutes**, which covers a full velocity sweep with
repeats rather than a single pass.

`tests/test_gate_registry.py::test_thresholds_are_pinned[compute]` failed on
this change, which is the test written the day before doing exactly its job; the
snapshot was updated in the same commit with the reason attached.

## What was NOT changed

Nothing was removed. Two gates looked operationally inert and both survived
scrutiny:

- **G13c (`realtime_cpu`)** is set only in tests today, but the scoped
  real-time tracking GUI has measured numbers — 18.7 ms GPU, 90.6 ms CPU on a
  full 2400² frame — against a **1.92 ms** per-frame budget at 520 fps.
  Margins 0.10 and 0.02. G13c is the encoded form of that decision's *"the
  display and the measurement cannot be the same stream"*.
- **G12c (`pixel_container`)** only fires on 8-bit, and 8-bit cannot reach
  SNR 10 with this bead, so it has never fired. Dormant for a
  **sample-dependent** reason rather than a structural one, and it costs
  nothing.

And on cost: lens 3 evaluates in **0.011 ms**, against lens 1's 1.146 ms. It is
the cheapest lens in the repository, so no gate here is worth removing to save
computation — removing one saves nothing measurable.

## Falsifying condition

For (4): a bandwidth measurement in the confirmed Micro-Manager save directory
that comes in materially below 206.8 MB/s. Every G12a verdict on record would
then have been computed against a budget that was too generous, and the
acquisitions that passed it would need `compute.cli drops` run over them.

For (5): a RAM-capture acquisition near the new 128 GB ceiling that pages,
stalls the pop loop, or is killed by the OS. That is the case this authorization
accepts without evidence, and it is the reason the note keeps saying so.
