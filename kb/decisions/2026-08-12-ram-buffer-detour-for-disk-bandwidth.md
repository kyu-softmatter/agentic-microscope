# 2026-08-12 · Disk bandwidth detour — acquire to RAM first, then flush

> The decision-log format in `docs/02 §9` is meant for **results of experiments
> actually run**. This entry is a design idea not yet executed, so instead of
> "settings actually used" and "result" it records "the proposed detour", "the
> basis for the calculation", and "remaining items to confirm". If this approach
> is actually implemented and run, add the result to this file or create a
> separate decision log.

## Request

Confirm whether Kinetix dual-cam (Kinetix_red/Kinetix_blue), 2400×2400 ROI per
camera, 200 fps, 60 s acquisition is possible on this system.

## Gate output (`compute.cli check`, actually run)

```
python -m compute.cli check --width 4800 --height 2400 --fps 200 \
    --disk-bandwidth-mb-s 206.8 --ram-budget-mb 16000 \
    --acquisition-duration-s 60 --free-disk-gb 2559
```
(The doubled-width trick expresses the combined byte rate of both cameras —
`compute.checks` works on a single stream, so summing two cameras has to be
reflected manually.)

> **Superseded 2026-08-19.** The trick is no longer needed: `compute.setup`
> takes one `Stream` per camera and sums them. The same check is now
> ```
> python -m compute.cli check --stream red:2400x2400@200 --stream blue:2400x2400@200 \
>     --disk-bandwidth-mb-s 206.8 --ram-budget-mb 16000 \
>     --acquisition-duration-s 60 --free-disk-gb 2559
> ```
> which reports the same 4608 MB/s and the same `buffer.too_small` margin of
> 0.69 — with a RAM-derived frame count the two formulations happen to agree.
> They stop agreeing the moment a **literal** `CircularBufferFrameCount` is
> used: MMCore counts its buffer in *images* shared across both cameras, so 552
> frames is 1.38 s of a 400 frames/s dual-cam stream, where the widened single
> frame would have reported 2.76 s. Twice the headroom that exists.

Result: **FAIL / INFEASIBLE**
- `data_rate.exceeds_disk`: margin 0.03 — requires 4608 MB/s (2400×2400×2bytes×200fps×2 cameras)
  vs a disk budget of 145 MB/s (D: drive measured 206.8 MB/s × 0.7, [kb/calibrations/disk-bandwidth.yaml](../calibrations/disk-bandwidth.yaml))
  → **roughly 32× over**. This combination does not work with real-time disk
  writing (silent frame drop).
- `buffer.too_small`: margin 0.69 — a 16GB RAM buffer holds only 3.5 s worth
  (below the 5 s criterion)

The bottleneck is the D: drive itself (SATA SSD class, ~207 MB/s) being unable to
sustain this data rate. To resolve it via ROI/fps: keeping 200fps requires
ROI ≤ ~425×425 px per camera, or keeping 2400×2400 requires dropping to ~6 fps.

## Proposed detour: acquire into RAM first → flush after acquisition

During acquisition, do not write to disk; accumulate every frame in RAM (numpy
array or similar), then flush to disk once acquisition is over. This removes the
real-time disk bandwidth constraint (G12) and changes the constraint to
**"does the entire acquisition fit in RAM"** (the same shape as the G13b capacity
check, but against RAM instead of disk).

### Basis for the calculation

Total system RAM: 255.65 GB (idle usage at measurement time ~29.8 GB, headroom
~226 GB).
2400×2400 dual-cam data rate = 23.04 MB/frame-pair × fps.

| Scenario | RAM required | Verdict |
|---|---|---|
| 200 fps × 60 s (original goal) | ~276 GB | ❌ larger than total RAM (255.65GB) — impossible even using all of it |
| 200 fps × 55 s | ~253 GB | ⚠ practically the entire machine, no headroom for OS/MM — risky |
| 200 fps × **43 s** | ~200 GB | ✅ safe, leaves 55GB headroom |
| **145 fps** × 60 s | ~200 GB | ✅ keeps 60 s, only lowers fps |
| 200 fps × 30 s | ~138 GB | ✅ comfortable headroom |

Post-acquisition disk flush time (at the measured D: 206.8 MB/s): 200 GB ≈ 16
minutes (non-real-time; no other acquisition to this drive during that window).

### Implementation obstacle (unconfirmed)

Micro-Manager's default save mechanism (circular buffer → continuously drained to
disk) most likely does not support this "acquire everything, write once" pattern
out of the box. Since, per the
[project_pymmcore_only_no_nis decision](../../docs/07-roadmap.md), this project
controls devices directly with pymmcore-plus instead of NIS-Elements, it looks
like we will have to write **a custom capture loop that polls frames directly via
pymmcore-plus into a preallocated numpy array and saves once finished**, rather
than MM's standard streaming save — not yet implemented or verified in code.

## What was implemented (2026-08-12)

| File | Role |
|---|---|
| [`calibration/ram_capture.py`](../../calibration/ram_capture.py) | `capture_burst_to_ram()` — fills a preallocated numpy array with frames via MMCore sequence acquisition (nothing written to disk). `flush_to_disk()` — saves to `.npy` after capture ends (fsync included), reports throughput |
| CLI `python -m calibration.cli ram-burst <cfg> --camera <label> --n-frames <N> [--out <path>]` | |
| [`tests/test_ram_capture.py`](../../tests/test_ram_capture.py) | tests pass against the pymmcore-plus demo camera (captures as many frames as requested, rejects invalid input, round-trip match after flush) |

**Confirmed by measurement**: on the demo camera (512×512, 16bit), 8-frame capture
at 91 fps and 5-frame flush at 89 MB/s — the plumbing itself works.
**Still unconfirmed**: running against the lab's real PVCAM/Kinetix adapter, and
**simultaneous dual-camera capture** (`capture_burst_to_ram()` assumes one camera —
running two at once requires either 2 threads or 2 `CMMCorePlus` instances, and
whether the real adapter actually runs them concurrently or serializes them is
unconfirmed; no guessing).

## Remaining items to confirm

- [x] Confirm that "no disk writing during acquisition, RAM only" actually works
      with real MM/pymmcore-plus
      → implemented and verified on the demo camera (`calibration/ram_capture.py`)
- [ ] Re-verify against the real Kinetix/PVCAM adapter (do not assume the demo
      camera and the real adapter behave identically for sequence acquisition)
- [ ] Confirm whether dual-camera (Kinetix_red/Kinetix_blue) capture really runs
      concurrently
- [ ] Measure how much RAM other processes (DMD/piezo/optical tweezers control, the
      OS) actually use during acquisition — the "55GB headroom" in the table above
      is an idle-based estimate
- [x] Decide whether to encode this approach in `compute.checks` as a new check
      (e.g. G13d "RAM capacity")
      → done 2026-08-19, `compute.checks.check_ram_capacity`. Setting
      `ram_capture=True` turns G12a informational (nothing is written while the
      camera runs) and makes G13d the binding hard gate; G13a and G13b still
      apply. **Budget capped at 32 GB** (user, 2026-08-19) rather than the
      machine's 255.65 GB, precisely because the checkbox above it — measuring
      what other processes actually hold — is still open. Anything above 32 GB
      is recorded in `assumed_inputs` and withholds `advances`. Flush time is
      reported, not gated.
      → [`kb/decisions/2026-08-19-lens-3-hardening.md`](2026-08-19-lens-3-hardening.md)
