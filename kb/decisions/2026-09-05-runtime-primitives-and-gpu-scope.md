# 2026-09-05 · Real-time primitives ported in, and the GPU/WSL2 question settled

> Two unrelated things in one session, joined only by both being about where
> work should run.
>
> **First**, three real-time primitives were lifted out of the Takatori-lab
> bacteria stack (`C:\Users\Takatori lab\Desktop\bacteria3`, a worktree of
> `bacteria2`) and rebuilt as `runtime/`. That stack drives a different
> instrument — a DMD rig for patterned-illumination bacteria experiments — but
> it has run these three patterns on real hardware, and this repository was
> about to need each of them in two places.
>
> **Second**, whether GPU work here wants WSL2. It does not, and the reason is
> not performance.
>
> ⚠ **No instrument time.** The primitives are tested against fake cores and
> injected clocks; nothing in `runtime/` has seen a Kinetix. The GPU numbers
> are real measurements, but on this workstation's RTX A4000 against synthetic
> arrays, not against a live acquisition. Both limits are restated at the
> bottom.
>
> Follows `2026-09-04-closed-loop-trapping-measured.md`, whose
> `track_bead_during` is the loop `runtime.frames` is meant to replace and
> deliberately has not yet.

## What was implemented

| File | Role |
|---|---|
| `runtime/frames.py` | `Latest` — one-slot frame ring. `FrameSource` — daemon thread that drains Micro-Manager's circular buffer and publishes only the newest frame, counting what it dropped |
| `runtime/ticker.py` | `sleep_until()` — sleep to nearly a deadline then busy-spin. `Ticker` — fixed-period loop clock, schedule from tick index, explicit missed-period policy |
| `runtime/shmview.py` | `ShmPublisher` / `ShmSubscriber` — rate-capped shared-memory frame channel, so a live view runs in a second process |
| `config/micromanager/live_view.py` | `--publish NAME` on the acquiring side, `--attach NAME` as a camera-free viewer, `attach_loop()` |

120 new tests (`tests/test_runtime_{frames,ticker,shmview}.py`,
`tests/test_live_view_attach.py`); suite 996 → **1116 passed**. Nothing new
imports cv2, pymmcore or cupy at module scope, so CI still collects everything
on `requirements.txt` alone.

`scipy 1.18.1` was installed into the venv this session, to get a CPU baseline
for the GPU comparison below. **No module in this repository imports it**, so
it is deliberately not in any `requirements-*.txt` yet.

---

## 1. Why these three, and what was changed rather than copied

None of the three is a transcription. Each had something wrong for this rig.

### `Latest` — the sequence number had to change meaning

The bacteria original increments its counter **per call to `put`**, so a
consumer can detect that *a* frame was replaced but not how many camera frames
went past. Here `seq` is the index of the image **popped out of the camera
buffer**, so gaps between the `seq` values a consumer observes are exactly the
frames it never saw.

That distinction is the whole reason to port this. `track_bead_during` in
`config/tweezers/trap_from_tracking.py` polls `core.getLastImage()` and
de-duplicates by comparing three pixels — `raw[0,0]`, `raw[-1,-1]` and the
centre — because at a 50 Hz tick against a 30 fps camera roughly a third of
ticks see the same frame twice. `getLastImage` *peeks*; it removes nothing, so
nothing in that path can count. Popping counts. `source.fresh(last_seq)`
answers both "is this new?" and "how many did I miss?" with no image
comparison.

⚠ **Do not mix the two on one core.** `popNextImage` removes images and
`getLastImage` does not, so a `FrameSource` running while other code still
polls `getLastImage()` on the same core leaves both reading a buffer the other
mutates.

### `Ticker` — the missed-period policy had to become a parameter

The bacteria stack hardcodes *skip the missed ticks* into four separate loops
(`lib/controller.py:139-233` is the one its own docstring calls canonical;
`pi_test.py`, `pattern_test.py` and `chamber_session.py` each carry a copy).
Four copies of a timing loop is four places for the timing to diverge, which is
the argument for extracting it at all.

But this repository's `stream_sine` does the **opposite** — it iterates a
pre-computed position schedule and sends every point, late, reporting the
cumulative lateness. Which behaviour is right is a physics question:

* `catch_up=True` moves the trap to where the waveform says it should be *now*
  and drops the backlog. A skipped point thins the drive.
* `catch_up=False` (today's behaviour) sends a burst of stale positions after a
  stall. That deforms the waveform in a way `column_from_fit` cannot see.

Arguably the first is the better drive. It is also a change to a drive that has
produced a measurement, so **both are offered and nothing was rewired**.
Deciding it needs a run with the stage tracked, comparing the fitted amplitude
under each.

### `ShmPublisher` — the header was missing the sensor shape

The bacteria header carries only the *published* shape, which left `run_viz.py`
reconstructing the decimation from a hardcoded native size — a constant that is
wrong the first time anyone sets an ROI. Here the header is
`<Qdiiii` = version, ts, vh, vw, **full_h, full_w**, so a subscriber drawing an
overlay can map its own pixels back to sensor pixels and from there to microns.

Decimation also changed from *cap the width* to **cap the longest edge**, which
matches `live_view.py --display` ("longest on-screen edge") and bounds the
payload at `max_w²` — the property that makes the fixed allocation in §2
possible. Capping width alone leaves a portrait frame taller than the cap.

### Why a process and not a thread — the rule, and why it matters here

Split on the GIL:

* **Thread** when the work is a C extension that releases it and needs the
  frame buffer for free. `popNextImage` blocks in C++; numpy/OpenCV/CuPy
  kernels release the GIL for their duration. `FrameSource` costs the control
  loop almost nothing and hands over the array by reference.
* **Process** when the work is Python bytecode or a GUI event loop, which holds
  the GIL. `cv2_loop` measures its own tick at ~38 ms full-frame, all of it
  Python frames plus highgui event pumping. Tk is worse — `PhotoImage` is a
  measured 43.1 ms of zlib+base64 per 800×800 frame, entirely under the GIL.

On **this** rig there is a second, harder reason. PVCAM hands a Kinetix to one
process at a time (`hardware/microscope.SHARED_DEVICES`), so during a run the
acquiring process is the *only* one that can see the camera — watching a run
meant not running one, and the way to get the camera back is the one move worth
avoiding, because dropping a trap is expensive. `--publish` / `--attach` gives
a live view with no second device claim.

Publish cost, measured on 2400×2400 uint16, 60 publishes:

| | |
|---|---|
| `try_publish` that publishes | **1.14 ms** median (1.74 max) at `max_w=640`; 3.98 ms at `max_w=1200` |
| `try_publish` the rate cap rejects | **0.30 µs** median |

A 50 Hz loop publishing at the 10 fps default pays 1.14 ms on one tick in five
and 0.3 µs on the rest — about **0.3 %** of the budget. The expensive knob is
`max_w`, not `max_fps`: the payload is quadratic in it.

---

## 2. Three Windows shared-memory behaviours that are not in the docs

All three were found by running the tests on this machine, and all three would
have been silent misbehaviour in the field. They are the most transferable part
of this session.

### Page rounding made the publisher recreate its segment every frame

Windows rounds a `SharedMemory` allocation up to a page, so a 288-byte request
reports back as `size == 4096`. The first version compared
`SharedMemory.size` against the size *requested* to decide whether to reuse the
segment; the comparison never matched, so the segment was destroyed and
recreated **on every publish** — which reset the version counter to 1 each
time, so a subscriber saw exactly one frame and then nothing, and had its
mapping pulled out from under it. Compare against the requested size, not the
reported one.

### A segment cannot be resized while a subscriber holds a handle

A handle keeps the name alive, so freeing and recreating raises
`FileExistsError` (`WinError 183`). A publisher that fitted its segment to each
frame therefore **took the run down whenever a viewer happened to be attached
and the ROI changed**. Fixed by allocating once at `HEADER_SIZE + max_w²`
(410 kB at the default) and never resizing; a smaller frame just leaves the tail
of the buffer unread. This removes the failure rather than reporting it.

Relatedly: two *live* publishers on one name cannot be merged **or** taken over
on Windows, so that case now raises a diagnostic instead of a bare `WinError
183` that names no cause. On POSIX the same branch is a genuine stale-segment
takeover, which is the only place the two platforms need different code.

### `unlink()` is a no-op, so "publisher gone" looks like "publisher idle"

A subscriber's mapping stays **valid** after the publisher exits; the pixels
simply stop changing. `poll()` returns `None` for both cases, so a viewer that
only redraws on arrival will show a dead feed as though it were live.
`ShmSubscriber.age` is the discriminator.

This produced a real logic bug worth recording on its own: the first
`attach_loop` drew its `STALE` banner inside the *arrival* branch, where `age`
is zero by construction — **the banner could never fire**. The redraw is now
gated on `got is not None or stale != was_stale`, so it fires once on the
transition and does not burn a core redrawing an unchanging frame.

### And one on the primitives themselves

`sleep_until`'s busy-spin (`while now() < deadline: pass`) **never terminates
under an injected clock that only advances when `sleep` is called.** The first
test file hung on it. Tests either pass `spin_margin=0` (removing the spin) or
use a clock that advances per `now()` call. This is a property of busy-waiting,
not a defect, but it is exactly the kind of thing that costs an hour twice.

Writing the tests also found a missing check in `Ticker`: `stop_event` was only
read *before* the wait. Most of a tick is inside `sleep_until`, so a stop
arriving 10 ms into a 1 s wait still cost a whole extra tick body — and for a
body that moves a stage or a trap, one more tick is the difference between
stopping and not.

---

## 3. GPU: where it wins on this instrument, and where it loses

Measured 2026-09-05 on the microscope PC — RTX A4000 16 GB, driver 595.97,
`cupy-cuda12x` 14.2.0, `scipy` 1.18.1, numpy 2.5.2. Transfers are **charged**
to the GPU column, which is the honest accounting for a pipeline that reads
frames off a camera into host memory.

### Full-frame array work — GPU wins, sometimes enormously

2400×2400 float32, upload included:

| operation | CPU scipy | GPU CuPy | |
|---|---|---|---|
| `median_filter` 5×5 | 2890 ms | 4.08 ms | **708×** |
| `gaussian_filter` σ=3 | 174 ms | 4.15 ms | **42×** |
| `uniform_filter` 27 | 98.6 ms | 4.39 ms | **22×** |
| `label()` on a threshold mask | 54.7 ms | 7.68 ms | **7.1×** |
| `gaussian_filter` σ=3, 512² | 6.29 ms | 0.83 ms | 7.6× |

For reference, `cv2.blur(27)` on the same frame is 17.0 ms — OpenCV's CPU box
filter is 5.8× faster than scipy's, so **which CPU baseline you pick changes
the apparent speedup by an order of magnitude**. Against cv2 the same GPU call
is 4.05×, of which **2.3 ms (55 %) is the upload**; the kernel alone is 1.9 ms
(8.8×). Quote the baseline or the number means nothing.

### The closed-loop tracker — GPU is *slower*

| | |
|---|---|
| `refine()`, 60 px window, 3 passes, CPU numpy | **866 µs** |
| the same on CuPy, transferring only the window | **1627 µs** → **0.53×** |

Launch overhead and PCIe dominate a 121×121 window. Putting the trapping
tracker on the GPU would make it **1.9× worse**. There is also a one-off cost
that a control loop cannot pay inside a tick: **CuPy's first kernel call
JIT-compiles, measured at 69 ms.** Any GPU use inside a loop needs an explicit
warm-up before the loop starts.

### The rule

> **GPU only when the array is ≳1 MB and the work is outside a tick.**

* ✅ post-hoc batch analysis, deconvolution, 3-D stack filtering, deep-learning
  segmentation, full-frame live detection (already done — `live_view.py --gpu`,
  90.6 ms CPU → 18.7 ms GPU, and per `requirements-analysis.txt` that is a
  *capability* rather than a speedup, since 90.6 ms fits no usable tick)
* ❌ closed-loop tracking, trajectory fitting, trap command streaming

### An incidental finding: `refine()`'s cost is `np.percentile`, not the GPU

Per call on a 121×121 window:

| | |
|---|---|
| `np.percentile(w, 10)` | **151 µs** |
| `np.partition` for the same value | **59 µs** |
| `w.sum()` | 5.0 µs |
| the whole centroid arithmetic | 40.5 µs |

Three passes means percentile alone is ~450 µs of `refine()`'s 866 µs. The fix
is a **CPU one-line change, not a GPU port** — 4 % of a 50 Hz tick down to
1.6 %. Not applied: `percentile` interpolates linearly between order statistics
and `partition` returns an actual element, so the two differ slightly on a
121² sample, and this is the closed-loop trapping path. It needs an
equivalence check on recorded frames before it goes in.

---

## 4. WSL2 is not an option here, and performance is not the reason

WSL2 reaches the GPU through a `/dev/dxg` paravirtualisation layer over the
same Windows WDDM driver, so there is no kernel-level speedup to be had — the
usual reasons to want it are ecosystem ones (TensorFlow ≥ 2.11 dropped native
Windows GPU; JAX, RAPIDS/cuCIM, DALI, StarDist are Linux-only or effectively
so). **This repository uses none of them.**

What rules it out is that the entire hardware layer is Windows-bound:

| Layer | Transport | In WSL2 |
|---|---|---|
| MM devices (Ti2-E, Kinetix ×2, SpectraIII/Aura, CSU-W1, DMD) | Windows DLLs — `Ti2_Mic_Driver.dll`, PVCAM | ✗ cannot load |
| Prior/Queensgate piezo | vendor `controller_interface64.dll` + COM4 + pywin32 | ✗ no COM |
| Aresis Tweez 300 | TCP 2070 — but only to the **Windows GUI application** | ~ TCP reaches it; the GUI is still Windows |
| Kinetix ownership | PVCAM grants to one process | ✗ cannot claim |

So the acquiring process must be native Windows, and the GPU already works
there: CuPy is in production in `live_view.py --gpu`. Adding WSL2 would split
the pipeline across an OS boundary for **zero GPU gain**, and put the large
image data on the `/mnt/c` 9p path, which is the one thing that genuinely is
slow.

---

## Still open

1. **`FrameSource` has never seen a Kinetix.** Three things to check on the
   rig, all properties of the PVCAM adapter rather than of this code: that
   `getRemainingImageCount`/`popNextImage` are the right pair for
   `startContinuousSequenceAcquisition`; whether `max_drain=4` is enough
   headroom (a rising `dropped` with a flat `published` means it is not); and
   whether popping changes what a concurrent `getLastImage()` elsewhere in the
   process returns.
2. **`track_bead_during` was deliberately not rewired.** Swapping in
   `FrameSource` moves the frame timestamp from the tick's clock to *arrival*,
   which changes the constant mid-exposure lag `column_from_fit` removes — a
   measurement-affecting change to a path that has produced a result. It
   probably improves accuracy; that has to be shown, not assumed.
3. **`stream_sine`'s `catch_up` choice** — see §1.
4. **`refine()`'s `percentile` → `partition`** — see §3, needs an equivalence
   check.
5. **`CUDA_PATH` is unset**, so CuPy emits
   `UserWarning: CUDA path could not be detected` on every import. Harmless —
   the headers are in the `[ctk]` extra's nvidia wheels at
   `…\site-packages\nvidia\cuda_runtime\include\` — but it clutters every log.
6. **`scipy` is installed in the venv but declared nowhere.** Either something
   starts using it and it goes in a `requirements-*.txt`, or it should come
   back out.
7. **`--attach`'s real cv2 window has not been opened.** The display loop is
   covered by tests with cv2 stubbed, and the two-process channel is covered by
   tests that spawn a real second interpreter, but highgui itself was not
   exercised on this path.
