# 2026-08-19 · Lens 3 hardening — one stream per camera, and where the frame rate comes from

> Not an experiment log. Same shape as
> [`2026-08-19-lens-7-scope.md`](2026-08-19-lens-7-scope.md) and
> [`2026-08-19-lens-5-hardening.md`](2026-08-19-lens-5-hardening.md): `docs/02
> §9` assumes a recommendation that was actually run, and there is no gate
> output here. This entry exists so the next reader — human or agent — knows
> which of these were decisions and which are still open.

## Context

Lens 3 (`compute/`) has been implemented since 2026-08-11: G12 data rate, G13
buffer / capacity / real-time CPU. A review on 2026-08-19 walked the lens
against its own documentation and found that its **declared specialty was not
implemented at all**: `docs/05 §5` and `docs/04 §8` both name post-hoc
`ElapsedTime` drop detection as the thing this lens does that no other lens
does, and a grep of the repository returned zero lines of it. Six further gaps
came out of the same pass. All seven are addressed below.

> **Executed 2026-08-20.** Written on the 19th with no runnable Python; a
> working interpreter arrived at `~/.venvs/experimentalist` (3.12.13) the next
> day and everything below has now been run. **586 tests pass** repo-wide, and
> `compute/drops.py` has been verified against the real `D:\data` archive.
> See "What running it actually changed" at the end — three things only real
> data showed.

## Decisions

### 1. Post-hoc drop detection now exists — `compute/drops.py`

`docs/06 §C5`: when the buffer cannot keep up, frames are discarded and **no
error is raised**; the only trace is an irregular `ElapsedTime-ms` series. Get
the lag time wrong in an MSD and the diffusion coefficient is wholly wrong. Two
new modules:

| File | Role |
|---|---|
| [`compute/mm_metadata.py`](../../compute/mm_metadata.py) | streaming `(FrameKey, ElapsedTime-ms)` reader. Line-by-line regex, not `json.load`, so a several-hundred-MB metadata file need not be materialised. Tolerates both MM generations (`docs/06 §A2`): quoted or bare numbers, pretty-printed or single-line |
| [`compute/drops.py`](../../compute/drops.py) | `analyse` / `analyse_file` / `scan_tree`, plus `DropReport` |
| CLI | `python -m compute.cli drops <metadata.txt>` and `scan <dir> [--contaminated-only]` |

**Three judgement calls inside it, all deliberate:**

- **Median, not mean, and per `(channel, slice)` series.** A drop can only
  lengthen an interval, never shorten one, so the mean is dragged by exactly the
  thing being detected while the median is not. Per-series because an
  interleaved multi-channel acquisition has a bimodal interval distribution —
  a pooled median lands between the two modes and calls every timepoint boundary
  a drop.
- **A gap must clear both `1.5 ×` cadence *and* cadence + 2 timestamp ticks.**
  The ratio alone is wrong for fast acquisitions: at a 2 ms cadence one tick of
  MM's 1 ms resolution is already a 1.5× interval, so every tick would read as a
  dropped frame and an archive sweep would come back declaring the *fastest*
  sessions the dirtiest. The floor only bites there; at 50 ms cadence it is
  inert.
- **It does not diagnose the cause.** A dropped frame and a genuine stall — a
  stage move, an autofocus, a filter change — are the same long interval. The
  report names the frame index and stops. Guessing which it was is exactly the
  kind of inference `docs/01 §3 Principle 1` forbids.

This is the only part of the whole committee that runs on the existing
2,343-acquisition archive today, with no hardware and no Phase 0 input
(`docs/07`, "three things that pay off right now").

### 2. Data rate sums streams — one per camera, not one widened frame

`AcquisitionResourceSetup` now holds `list[Stream]`. The lab runs
Kinetix_red and Kinetix_blue simultaneously, and until today the dual-cam case
had to be smuggled in by doubling the frame width by hand — the trick is
recorded verbatim in
[`2026-08-12-ram-buffer-detour-for-disk-bandwidth.md`](2026-08-12-ram-buffer-detour-for-disk-bandwidth.md).

It gave the right data rate and the **wrong buffer depth**. MMCore counts its
circular buffer in *images*, shared across cameras, so headroom is
`N_buffered / N_arriving_per_second` and the frame geometry cancels. A literal
`CircularBufferFrameCount = 552` is 1.38 s of a 400 frames/s dual-cam stream;
the widened single frame reported 2.76 s. Twice the headroom that exists.

`Stream.from_dimensions` folds `z × c × positions` in for multi-dimensional
acquisitions, and says in its own docstring that the result is an **average**
rate — if the z-sweep is a burst inside a longer timepoint interval the
instantaneous rate is higher and G13a comes out optimistic. Pass the burst rate
directly in that case. The alternative was to model burst structure, which this
repository has no way to verify.

G13c's per-frame CPU budget likewise now divides the **total** arrival rate: two
cameras at 200 fps each leave 2.5 ms per frame, not 5 ms.

### 3. G12c — bytes/pixel comes from the readout mode, and 8-bit is not confirmed

`BYTES_PER_PIXEL = 2` was hard-coded on the correct observation that MM stores
12-bit in a 16-bit container. It is wrong for **8 bit**, and 8 bit is the
Kinetix's `Speed` mode — 500 fps full frame, i.e. precisely the regime where
G12a binds. A 2× error, in the direction that calls a feasible acquisition
INFEASIBLE.

Lens 2 already reads bit depth off `data/detectors.yaml` modes
(`detection.setup.Camera.effective_bit_depth`); lens 3 now uses the same fact
via `Stream.bit_depth` → `resources.bytes_per_pixel_for_bit_depth`.

**What was *not* done: assume the fix.** MMCore reports 1 byte for an 8-bit
pixel type, but whether this lab's PVCAM adapter hands MMCore 8-bit pixels or
upconverts has never been checked, and an adapter is free to do either.
`check_pixel_container` therefore reports **both** rates, pins the verdict to
`assumed`, and names the one-line measurement that closes it
(`core.getBytesPerPixel()` on the real config). Calling it measured on the
strength of how MMCore is documented to behave would be `docs/06 §E3` exactly.

### 4. G12b — a requested frame rate is not evidence

Every number this lens produces scales linearly with `f`, and `docs/06 §C4` is
the measured case: a ~85 Hz camera ceiling delivered 28 Hz, with MM overhead or
the disk — **not the camera** — as the bottleneck. The old `fps` field carried a
docstring saying "achieved (not requested)" and nothing enforced it.

`Stream.fps_source` is now `"measured" | "requested"`, and
`check_fps_provenance` escalates in three steps:

| state | verdict |
|---|---|
| `measured` | passes, informational |
| `requested`, no lens-2 ceiling | `warn`, evidence `assumed`, asks for `detector_max_fps` |
| `requested`, within lens-2 ceiling | still `warn` — §C4's bottleneck was not the camera either |
| `requested`, above lens-2 ceiling | `fail` severity, `margin = max_fps / requested`, feasibility collapses |

**Why bias-kind and not hard.** Frame-rate realizability is lens 2's G9. When
the requested rate is unreachable, lens 3 reports that its own arithmetic rests
on a rate the camera cannot deliver and hands the setting back — it does not
seize a verdict it does not own. Same arrangement as
`trapping.checks.check_sampling`, which gates on `detector_fps` only when lens 2
has supplied one. The 2↔3 pair is now in `docs/01 §4`'s cross-lens table, where
it should have been all along.

### 5. G13d — RAM-capture capacity, ceiling 32 GB

Closes the last open checkbox in the RAM-detour decision log. `ram_capture=True`
turns G12a informational — nothing is written while the camera runs — and makes
G13d the binding hard gate. G13a still applies (the pop loop draining the buffer
into the capture array stalls on CPU instead of disk); G13b still applies (the
burst lands on disk eventually).

**The budget is 32 GB, chosen by the user on 2026-08-19, and it is a policy, not
a measurement.** The machine has 255.65 GB with ~226 GB idle headroom, and the
detour log's own table sketches 200 GB scenarios. But the checkbox directly
above this one — *measure how much RAM the OS, MM, and the DMD/piezo/tweezers
control processes actually hold during an acquisition* — is still open, and
idle headroom is not acquisition headroom. 32 GB is what may be spent while that
is unknown. A budget above it is recorded in `assumed_inputs` and withholds
`advances` rather than being refused.

Flush time is **reported, not gated**: nothing is lost if it is slow, but "the
microscope is tied up for 16 minutes afterwards" is a fact the user needs before
agreeing.

### 6. An unconfirmed bandwidth measurement path is an assumption

[`kb/calibrations/disk-bandwidth.yaml`](../calibrations/disk-bandwidth.yaml)
records 206.8 MB/s and warns in its own note that
`D:\Kyu Hwan Choi\_bench` is not confirmed to be the folder MM streams into. The
gate read the number and ignored the note.

`disk_bandwidth_path_confirmed` now defaults to **false**, which pins every
lens-3 verdict to `evidence: assumed`. A number measured somewhere else on the
same drive is a plausible number, not a measured one — `docs/06 §E3`. Ten
minutes with `calibration.cli disk-bandwidth` pointed at the real save directory
clears it permanently.

### 7. Interpretive half — `.claude/agents/compute-resources.md`

Lenses 4 · 5 · 6 · 8 have a subagent for what has no closed form. Lens 3 is the
opposite case: it is **fully deterministic**, so the agent re-derives nothing.
It gathers inputs, invokes the code, reads the verdict honestly, and carries the
two cross-lens wires (2↔3 inbound frame rate, 3↔6 outbound ROI-vs-statistics and
contaminated-lag-time findings). The file says in its own header that if it and
the code disagree, the code is right.

## What running it actually changed (2026-08-20)

The tests written on the 19th all passed on the first real run except three,
and all three were the **tests** being wrong, not the code: `Verdict.margins`
and `Verdict.metrics` are keyed by the *result* code, so a failing check moves
its own key (`ram_capacity` → `ram_capacity.exceeds_budget`). Every lens in this
repo does that. Worth knowing before writing a caller: **you cannot index
`margins` by a stable check name.** Not changed here — it is a repo-wide
convention and changing it in one lens only would be worse than the wart.

Then `compute/drops.py` was pointed at the real `D:\data` archive (2,353
metadata files, 32 GB, both 1.4.23 and 2.0.3 present). The parser was correct —
a direct `grep -c '"FrameKey-'` matches what it found, on both generations. But
two behaviours only real data could expose:

### Timestamp quantization is coarser than the guard assumed

A 2.0.3 acquisition at 62.5 fps has intervals of **15 ms (1124×) and 16 ms
(1873×)** around a true cadence of 15.63. The median snaps to 16, MAD comes out
`0.00 ms` — a claim of perfectly steady timing — and `throughput_fps` (64.0)
lands *above* `cadence_fps` (62.5), which reads as nonsense.

`QUANTIZATION_GUARD_STEPS` went 5 → 20, and this time derived rather than
picked: MAD moves in whole ticks, so for the `JITTER_WARN_FRACTION` test to be a
measurement rather than a coin flip the threshold must be worth at least two
resolvable ticks — `2 / 0.10 = 20 ms`. `mean_interval_ms` is now reported beside
the median, because the two disagreeing *is* the signature.

### MM's Summary advertises frames nobody got

`100x_1x1__1` records `"Frames": 1000` and contains 58. `100x_1x1__2` records
1000 and contains 44. Both have flawless lag times, and the report called them
CLEAN.

Truncation is now `DropReport.truncated` / `completion_fraction`, kept
**separate from `contaminated`** — the lag times really are fine; it is the
statistics that are not what was planned. `scan --contaminated-only` lists both,
because the flag means "needs looking at", and a run that stopped at 5.8% of its
plan needs looking at. This is a third silent failure of the same family as §C4
and §C5: no error, a complete-looking dataset, and a Summary that keeps
insisting otherwise.

### The first archive sweep (2026-08-20)

`python -m compute.cli scan "D:\data" --contaminated-only`, 2,353 acquisitions,
32 GB, ~25 min:

| | count |
|---|---|
| clean lag times | 1,234 |
| **contaminated** (drops or irregular cadence) | **227** |
| **truncated** (stopped before the planned frame count) | **203** |
| — of which both contaminated *and* truncated | 36 |
| **distinct flagged files** | **394** |
| skipped | 892 |

The 892 skips reconcile exactly: 880 single-frame snapshots, 8 two-frame
acquisitions, and 4 whose frames are split across (channel, slice) series with
fewer than 3 each. None of them can carry a cadence estimate, so refusing is
correct — but the sweep only printed the *count*, not the breakdown, and
working out why took a separate pass over the same 32 GB. `cmd_scan` now prints
a per-reason tally: a skipped file is not a clean one, and the headline counts
read as coverage they do not have without it.

Where the 394 sit:

| top-level folder | flagged |
|---|---|
| ATPS motility induced partitioning | 290 |
| Liquid crystal | 90 |
| Actin rheology | 10 |
| tweezers calibration | 2 |
| Active particle control · ATPS passive particle | 1 each |

The ATPS interface-velocity sessions
(`vel0.5um-s_Las0.12_sub1_{DEX2PEG,PEG2DEX}_...`) are the bulk of the first row:
dozens truncated at 500–1200 of a planned 10,000, several *also* dropping
frames. First place to look before trusting any velocity or MSD from that set.

**The 10 in `Actin rheology` matter out of proportion to their count**, and this
is the finding to carry to Lens 7. They are
`20240816 actin_network\calibration\OT{0.01,0.025,0.05,0.1}_exp10_100x_1x1_*` —
**trap-stiffness calibration runs**, 100 fps, 3000 frames, dropping 3 to 53
frames each. Power-spectrum calibration assumes a uniform sample interval; drop
1.5% of frames at unknown positions and the fitted corner frequency `f_c` is
wrong, so κ is wrong. G14 gates `f_s >= 10 f_c` on that same `f_c`. Every
stiffness number derived from this session is suspect until the spectra are
recomputed on the actual timestamps — which the per-gap frame indices in
`compute.cli drops` make possible.

**This list is the deliverable, not the tool.** `docs/07`'s "archive drop
detection" item asked for exactly this enumeration, and **394 of 1,461
analysable acquisitions (27%)** are contaminated, truncated, or both. Note the
two categories overlap by 36 — adding 227 and 203 double-counts them.

## What this leaves as actual Lens 3 work

1. ~~**Run it.**~~ Done 2026-08-20 — 586 tests pass, both MM generations parse
   against the real archive. See the section above
2. **NDTiff has no `metadata.txt`.** Those datasets scan as zero frames and are
   reported as *skipped*, not clean — named, not covered
2b. **Neither gaps nor truncation are attributed.** A stage move, an autofocus,
   and a dropped frame are the same long interval; a user abort, a full disk,
   and a crash are the same short run. Cross-referencing the Summary's
   `AxisOrder` and position list could separate the first group; nothing does
3. **Committee wiring** — lens 2 computes `max_fps`, lens 3 needs it as
   `--detector-max-fps`, and a human currently carries it between the two CLIs.
   Phase 3 (orchestration). Identical to the gap lens 7 records
4. ~~**The archive sweep itself** has not been run~~ — run 2026-08-20, result
   above and the full list in
   [`kb/calibrations/2026-08-20-archive-drop-scan.txt`](../calibrations/2026-08-20-archive-drop-scan.txt).
   What remains is landing it in `docs/07` Phase 2's `dropped_frames` column,
   which needs the SQLite envelope that does not exist yet
5. **The 10 tweezers-calibration sessions are not re-analysed.** Naming them is
   not fixing them: the power spectra have to be recomputed on the actual
   timestamps before any κ from that session is usable. That work belongs to
   Lens 7 and to `D:\codes`, not here

## What would reopen each decision

| Decision | Reopens if |
|---|---|
| 1 drop detection | A known-clean acquisition reports contaminated, or a known-bad one reports clean — then the tokeniser or the gap threshold is wrong, not the acquisition. The 2026-08-20 archive run cleared the parser on both MM generations, so any future failure is in the thresholds |
| 2 streams | Burst-structured z-stacks turn out to be common; then the average-rate simplification needs replacing with a real duty model, not a warning in a docstring |
| 3 container | One reading of `core.getBytesPerPixel()` in Speed mode. If it returns 2, `bytes_per_pixel_for_bit_depth` is wrong and every 8-bit rate above halves in the wrong direction |
| 4 provenance | Nothing — an achieved rate always beats a requested one. But if orchestration lands, the escalation ladder collapses to "lens 2 hands over its number automatically" |
| 5 RAM ceiling | A measurement of concurrent RAM use during a real acquisition. Then `LIMITS["ram_capture_budget_mb"]` moves and the assumption disappears |
| 6 bandwidth path | A re-measure inside MM's actual save directory — or confirmation that `_bench` already is it |
