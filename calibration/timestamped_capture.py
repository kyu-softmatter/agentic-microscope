"""Sequence capture that keeps every frame's timestamp, not just the frames.

The gap this fills is narrow and it matters. ``calibration/ram_capture.py``
already runs a burst -- but it calls ``popNextImage()``, which throws the
metadata away, and reports one ``elapsed_s`` for the whole sequence. A total
elapsed time cannot align anything: an acquisition whose frames arrived at
33.3 ms intervals and one that stalled for 200 ms in the middle produce the
same number.

And alignment is the entire point. ``hardware/orchestrator.py`` states it in its
own docstring -- **the host clock is not the experiment clock** -- and names the
camera's per-frame ``ElapsedTime-ms`` series as the one every other subsystem
gets aligned onto. A piezo sine and a trap pattern can only be placed against
the frames if the frames carry their own times.

WHAT MMCORE ACTUALLY ATTACHES
-----------------------------
Measured 2026-09-03 against the pymmcore-plus demo config, because guessing tag
names is how this kind of module silently records nothing:

    ElapsedTime-ms      camera clock, ms since acquisition start. AUTHORITATIVE.
    ImageNumber         MMCore's own sequential counter. Gaps prove drops.
    TimeReceivedByCore  absolute wall clock to microseconds. The only tag that
                        ties this run to anything outside it.
    Binning · Camera · Height · Width · PixelType · ROI-X-start · ROI-Y-start

``ElapsedTime-ms`` came back as 6.30, 12.42, 18.87, 25.26, 31.71, 38.11 on six
frames at a 5 ms exposure -- present, monotonic, and quantised to 10 us in that
build (``compute.drops.TIMESTAMP_RESOLUTION_MS`` documents the 1 ms case, which
is what the archive carries; the analysis handles both).

THREE CLOCKS, AND WHICH ONE IS THE RECORD
-----------------------------------------
    ElapsedTime-ms      the record. Every reported interval comes from here.
    ImageNumber         not a clock -- a counter. Its gaps are the only
                        *proof* of a drop, because MMCore raises nothing when
                        it loses a frame (compute/drops.py opening paragraph).
    host perf_counter   recorded per frame and used for **nothing** except
                        showing how far host time drifted from camera time.
                        It is a cross-check, never a substitute.

If ``ElapsedTime-ms`` is missing on a frame, that frame is counted in
``frames_without_timestamp`` and passed to ``compute.drops.analyse`` as such.
It is never backfilled from host time -- an invented timestamp is worse than an
absent one, because it looks like data.

DROP DETECTION IS NOT REIMPLEMENTED HERE
----------------------------------------
``compute/drops.py`` already does it, is tested, and knows about the awkward
parts -- timestamp quantisation, per-(channel, slice) series, gap ratios.
``CaptureResult.drop_report()`` builds ``compute.mm_metadata.FrameTime`` records
and hands them over. The only thing this module adds is ``ImageNumber``, which
the archive path does not have because MM's metadata files do not carry it.
"""

from __future__ import annotations

import json
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from compute.mm_metadata import FrameTime

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus

    from compute.drops import DropReport

#: How long to nap when the circular buffer is empty. Short enough that a
#: 33 ms frame period is never the thing being waited on.
POLL_INTERVAL_S = 0.001

#: Multiple of the nominal sequence duration to wait before giving up, plus
#: SEQUENCE_TIMEOUT_FLOOR_S. Generous on purpose: a timeout here throws away a
#: real acquisition, which is worse than waiting.
SEQUENCE_TIMEOUT_FACTOR = 3.0
SEQUENCE_TIMEOUT_FLOOR_S = 5.0

_DTYPE_BY_BYTES_PER_PIXEL = {1: np.uint8, 2: np.uint16, 4: np.uint32}


def _tag(md, key: str) -> str | None:
    """One metadata tag, or None if this frame does not carry it."""
    try:
        return md.GetSingleTag(key).GetValue()
    except Exception:
        return None


def _float_tag(md, key: str) -> float | None:
    raw = _tag(md, key)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _int_tag(md, key: str) -> int | None:
    value = _float_tag(md, key)
    return None if value is None else int(value)


@dataclass(frozen=True)
class FrameRecord:
    """One frame's three clocks and its place in the sequence."""

    index: int
    """Our own arrival counter. Always dense -- it counts what we received."""

    image_number: int | None
    """MMCore's ``ImageNumber``. **Gaps here are drops.** Sparse by nature."""

    elapsed_ms: float | None
    """``ElapsedTime-ms`` -- the camera clock. The authoritative time."""

    received_by_core: str | None
    """``TimeReceivedByCore`` -- absolute wall clock, microsecond resolution."""

    host_perf_s: float
    """``perf_counter`` at the moment we popped it. Cross-check only."""


@dataclass(frozen=True)
class CaptureResult:
    frames: np.ndarray
    records: tuple[FrameRecord, ...]
    camera: str
    exposure_ms: float
    roi: tuple[int, int, int, int]
    binning: str | None
    pixel_type: str | None
    n_requested: int
    requested_interval_ms: float
    wall_elapsed_s: float

    @property
    def n_captured(self) -> int:
        return len(self.records)

    @property
    def complete(self) -> bool:
        return self.n_captured == self.n_requested

    @property
    def frames_without_timestamp(self) -> int:
        return sum(1 for r in self.records if r.elapsed_ms is None)

    @property
    def timestamps(self) -> tuple[float, ...]:
        return tuple(r.elapsed_ms for r in self.records if r.elapsed_ms is not None)

    @property
    def span_ms(self) -> float | None:
        """Last timestamp minus first, on the camera clock."""
        stamps = self.timestamps
        return None if len(stamps) < 2 else max(stamps) - min(stamps)

    @property
    def achieved_fps(self) -> float | None:
        """Delivered rate **from the camera clock**, not from wall time.

        ``n - 1`` intervals, not ``n``: with 150 frames there are 149 gaps
        between them, and dividing by 150 understates the rate by 0.7%.
        """
        span = self.span_ms
        if span is None or span <= 0:
            return None
        return (len(self.timestamps) - 1) / (span / 1000.0)

    @property
    def image_number_gaps(self) -> tuple[tuple[int, int], ...]:
        """``(after, missing_count)`` for every break in ``ImageNumber``.

        The one drop signal the archive path cannot see, because MM's metadata
        files do not record ``ImageNumber`` at all.
        """
        numbered = [r.image_number for r in self.records if r.image_number is not None]
        gaps = []
        for previous, current in zip(numbered, numbered[1:]):
            if current > previous + 1:
                gaps.append((previous, current - previous - 1))
        return tuple(gaps)

    @property
    def dropped_by_image_number(self) -> int:
        return sum(count for _, count in self.image_number_gaps)

    @property
    def host_vs_camera_drift_ms(self) -> float | None:
        """How far host time diverged from the camera clock over the run.

        Reported so the difference is visible rather than assumed small. It is
        not a correction and must not be used as one.
        """
        stamped = [r for r in self.records if r.elapsed_ms is not None]
        if len(stamped) < 2:
            return None
        host_span_ms = (stamped[-1].host_perf_s - stamped[0].host_perf_s) * 1000.0
        camera_span_ms = stamped[-1].elapsed_ms - stamped[0].elapsed_ms
        return host_span_ms - camera_span_ms

    def frame_times(self) -> tuple[FrameTime, ...]:
        """The timestamped frames as ``compute.mm_metadata.FrameTime``.

        Single channel, single slice -- this module captures from one camera
        with no channel loop, so every frame is in series (0, 0).
        """
        return tuple(
            FrameTime(frame=r.index, channel=0, slice=0, elapsed_ms=r.elapsed_ms)
            for r in self.records
            if r.elapsed_ms is not None
        )

    def drop_report(self) -> DropReport:
        """Hand the series to the repository's own drop detection."""
        from compute.drops import analyse  # noqa: PLC0415  (avoid import cycle)

        return analyse(
            self.frame_times(),
            requested_interval_ms=self.requested_interval_ms or None,
            planned_frames=self.n_requested,
            frames_without_timestamp=self.frames_without_timestamp,
            source=f"{self.camera} live capture",
        )

    def timestamps_csv(self) -> str:
        """Per-frame timestamps as CSV, camera clock first."""
        lines = ["index,image_number,elapsed_ms,interval_ms,received_by_core,host_perf_s"]
        previous: float | None = None
        for r in self.records:
            interval = (
                "" if (r.elapsed_ms is None or previous is None)
                else f"{r.elapsed_ms - previous:.4f}"
            )
            lines.append(
                f"{r.index},"
                f"{'' if r.image_number is None else r.image_number},"
                f"{'' if r.elapsed_ms is None else f'{r.elapsed_ms:.4f}'},"
                f"{interval},"
                f"{r.received_by_core or ''},"
                f"{r.host_perf_s:.6f}"
            )
            if r.elapsed_ms is not None:
                previous = r.elapsed_ms
        return "\n".join(lines) + "\n"

    def write(self, stem: str | Path) -> dict[str, Path]:
        """Write ``<stem>.npy`` and ``<stem>_timestamps.csv``.

        ``.npy`` rather than TIFF because tifffile is not installed on the
        microscope PC and numpy is -- the frames are a plain 3-D array and
        inventing a format dependency to store one is not worth it. The CSV is
        separate so the timestamps can be read without loading the stack.
        """
        stem = Path(stem)
        stem.parent.mkdir(parents=True, exist_ok=True)
        frames_path = stem.with_suffix(".npy")
        stamps_path = stem.with_name(stem.name + "_timestamps.csv")
        settings_path = stem.with_name(stem.name + "_settings.json")
        np.save(frames_path, self.frames)
        stamps_path.write_text(self.timestamps_csv(), encoding="utf-8")
        # Camera, exposure and ROI live in neither the .npy nor the CSV, so a
        # saved capture was not reconstructible without them. They are the
        # difference between a stack of numbers and a measurement.
        settings_path.write_text(
            json.dumps(self._mm_summary(None), indent=2) + "\n", encoding="utf-8"
        )
        return {
            "frames": frames_path,
            "timestamps": stamps_path,
            "settings": settings_path,
        }

    @classmethod
    def from_saved(
        cls,
        stem: str | Path,
        *,
        camera: str | None = None,
        exposure_ms: float | None = None,
        roi: tuple[int, int, int, int] | None = None,
        binning: str | None = None,
        pixel_type: str | None = None,
        requested_interval_ms: float = 0.0,
    ) -> CaptureResult:
        """Rebuild a result from ``write()``'s output, for later conversion.

        Reads ``<stem>.npy`` and ``<stem>_timestamps.csv``, and takes the camera
        settings from ``<stem>_settings.json`` when it is there. Captures written
        before that sidecar existed have to be told: pass ``camera``,
        ``exposure_ms`` and ``roi`` explicitly, and they override the sidecar if
        both are present.

        Nothing is invented. A setting neither found nor passed stays ``None``
        and travels as ``None`` into the OME-XML and the MM summary, where an
        absent field is honest and a guessed one is not.
        """
        stem = Path(stem)
        frames = np.load(stem.with_suffix(".npy"))

        sidecar: dict = {}
        settings_path = stem.with_name(stem.name + "_settings.json")
        if settings_path.exists():
            sidecar = json.loads(settings_path.read_text(encoding="utf-8"))

        records: list[FrameRecord] = []
        rows = stem.with_name(stem.name + "_timestamps.csv").read_text(
            encoding="utf-8"
        ).splitlines()
        for line in rows[1:]:
            if not line.strip():
                continue
            index, image_number, elapsed_ms, _interval, received, host = (
                line.split(",")
            )
            records.append(
                FrameRecord(
                    index=int(index),
                    image_number=int(image_number) if image_number else None,
                    elapsed_ms=float(elapsed_ms) if elapsed_ms else None,
                    received_by_core=received or None,
                    host_perf_s=float(host),
                )
            )

        sidecar_roi = sidecar.get("ROI")
        return cls(
            frames=frames,
            records=tuple(records),
            camera=camera or sidecar.get("Camera") or "unknown",
            exposure_ms=(
                exposure_ms if exposure_ms is not None
                else sidecar.get("ExposureMs") or 0.0
            ),
            roi=tuple(
                roi or sidecar_roi
                or (0, 0, frames.shape[2], frames.shape[1])
            ),
            binning=binning or sidecar.get("Binning"),
            pixel_type=pixel_type or sidecar.get("PixelType"),
            n_requested=len(records),
            requested_interval_ms=requested_interval_ms,
            wall_elapsed_s=0.0,
        )

    # -- Micro-Manager-shaped output ------------------------------------

    def _mm_summary(self, pixel_size_um: float | None) -> dict:
        """The ``Summary`` block, carrying the five fields compute/ reads.

        ``compute.mm_metadata._SUMMARY_NUMBER_RE`` pulls Interval_ms, Frames,
        Width, Height and BitDepth. Everything else here is for a human or for
        MM itself; nothing downstream depends on it.

        BitDepth is **16**, not the 12 the PVCAM adapter's ``PixelType``
        advertises. Measured 2026-09-03 on Kinetix_red: one 512x512 frame held
        12,441 distinct values with a modal spacing of 1 LSB and a maximum of
        34,917, and 12 bits cannot represent any of that. Confirmed by the user
        the same day. Writing 12 here would make every count in the archive
        wrong by a factor of 16.
        """
        intervals = [
            b - a for a, b in zip(self.timestamps, self.timestamps[1:])
        ]
        summary = {
            "Frames": self.n_captured,
            "Width": int(self.roi[2]),
            "Height": int(self.roi[3]),
            "BitDepth": 16,
            "PixelType": "GRAY16",
            "Interval_ms": round(statistics.median(intervals), 4) if intervals else 0.0,
            "Slices": 1,
            "Channels": 1,
            "Positions": 1,
            "Camera": self.camera,
            "Binning": self.binning,
            "ExposureMs": round(self.exposure_ms, 4),
            "ROI": list(self.roi),
            "AchievedFPS": round(self.achieved_fps, 4) if self.achieved_fps else None,
            # Provenance. This file is MM-*shaped*, not MM-written, and a tree
            # scan would otherwise count it as a real prior acquisition. The
            # regex parser ignores unknown keys, so saying so costs nothing.
            "WrittenBy": "agentic-microscope calibration.timestamped_capture",
            "NotWrittenByMicroManager": True,
            "WrittenAt": datetime.now(timezone.utc).isoformat(),
        }
        if pixel_size_um:
            summary["PixelSize_um"] = pixel_size_um
        return summary

    def mm_metadata_json(self, pixel_size_um: float | None = None) -> str:
        """MM-shaped ``_metadata.txt`` text: Summary plus one block per frame.

        Frame blocks are keyed ``FrameKey-<t>-<c>-<z>`` with c = z = 0, which is
        the token ``compute.mm_metadata.TOKEN_RE`` opens a block on. A frame
        whose ``ElapsedTime-ms`` is missing is written **without** that key
        rather than with a fabricated one -- the parser counts it as a frame
        carrying no timestamp, which is the truth.
        """
        doc: dict[str, object] = {"Summary": self._mm_summary(pixel_size_um)}
        for r in self.records:
            block: dict[str, object] = {
                "FrameIndex": r.index,
                "Frame": r.index,
                "ChannelIndex": 0,
                "SliceIndex": 0,
                "PositionIndex": 0,
                "Camera": self.camera,
                "ExposureMs": round(self.exposure_ms, 4),
                "Width": int(self.roi[2]),
                "Height": int(self.roi[3]),
                "ROI-X-start": int(self.roi[0]),
                "ROI-Y-start": int(self.roi[1]),
            }
            if r.elapsed_ms is not None:
                block["ElapsedTime-ms"] = r.elapsed_ms
            if r.image_number is not None:
                block["ImageNumber"] = r.image_number
            if r.received_by_core is not None:
                block["TimeReceivedByCore"] = r.received_by_core
            doc[f"FrameKey-{r.index}-0-0"] = block
        return json.dumps(doc, indent=2) + "\n"

    def write_ome_tiff(
        self,
        stem: str | Path,
        *,
        pixel_size_um: float | None = None,
        mm_layout: bool = True,
    ) -> dict[str, Path]:
        """Write an OME-TIFF plus an MM-shaped ``_metadata.txt`` beside it.

        Two files, because they answer different questions and OME-TIFF alone
        answers only one of them:

            <stem>_MMStack_Pos0.ome.tif        frames + OME-XML, per-plane DeltaT
            <stem>_MMStack_Pos0_metadata.txt   the series compute/ actually parses

        The sidecar is the point. ``compute/mm_metadata.py`` scans
        ``*metadata.txt`` for ``FrameKey`` / ``ElapsedTime-ms`` tokens -- that is
        how all 2,343 archived acquisitions are read -- and it does **not** parse
        OME-XML. Writing only the OME-TIFF would produce a file this repository's
        own drop detection cannot see.

        Per-plane ``DeltaT`` is written in **seconds** (OME's default unit) from
        ``ElapsedTime-ms``. Verified 2026-09-03 that tifffile round-trips the
        per-plane values rather than collapsing them to a single TimeIncrement.

        ``pixel_size_um`` becomes ``PhysicalSizeX/Y``. Pass it only if you know
        its provenance -- 0.065 for 100x/1.0x on this instrument is 6.5/100, the
        nominal, not a graticule measurement (kb/systems/current.md >
        pixel_size_calibration, sourced from a 2025-04 spreadsheet).

        ``mm_layout=False`` drops the ``_MMStack_Pos0`` infix if you would rather
        the filenames stayed plain.
        """
        import tifffile  # noqa: PLC0415  (optional dependency, imported on use)

        stem = Path(stem)
        stem.parent.mkdir(parents=True, exist_ok=True)
        base = stem.name + ("_MMStack_Pos0" if mm_layout else "")
        tif_path = stem.with_name(base + ".ome.tif")
        meta_path = stem.with_name(base + "_metadata.txt")

        delta_t_s = [
            (r.elapsed_ms / 1000.0 if r.elapsed_ms is not None else None)
            for r in self.records
        ]
        exposure_s = self.exposure_ms / 1000.0
        intervals = [b - a for a, b in zip(self.timestamps, self.timestamps[1:])]

        metadata: dict[str, object] = {
            "axes": "TYX",
            # 16, not the 12 the PVCAM PixelType claims -- see _mm_summary.
            # tifffile leaves SignificantBits out unless told, and a reader that
            # trusts it would scale every count by 16.
            "SignificantBits": 16,
            "Plane": {
                "DeltaT": delta_t_s,
                "DeltaTUnit": ["s"] * len(delta_t_s),
                "ExposureTime": [exposure_s] * len(delta_t_s),
                "ExposureTimeUnit": ["s"] * len(delta_t_s),
            },
        }
        if intervals:
            metadata["TimeIncrement"] = statistics.median(intervals) / 1000.0
            metadata["TimeIncrementUnit"] = "s"
        if pixel_size_um:
            metadata["PhysicalSizeX"] = pixel_size_um
            metadata["PhysicalSizeY"] = pixel_size_um
            metadata["PhysicalSizeXUnit"] = "µm"
            metadata["PhysicalSizeYUnit"] = "µm"

        tifffile.imwrite(tif_path, self.frames, ome=True, metadata=metadata)
        meta_path.write_text(
            self.mm_metadata_json(pixel_size_um), encoding="utf-8"
        )
        return {"ome_tiff": tif_path, "mm_metadata": meta_path}


def capture_timestamped(
    core: CMMCorePlus,
    n_frames: int,
    *,
    interval_ms: float = 0.0,
    camera: str | None = None,
    timeout_s: float | None = None,
    on_frame: Callable[[int, np.ndarray], None] | None = None,
    on_frame_every: int = 1,
) -> CaptureResult:
    """Run a sequence of ``n_frames`` and keep every frame's metadata.

    ``interval_ms`` is *requested*, not guaranteed -- whether the camera honours
    it is a property of the camera and its trigger mode, which is exactly why
    the achieved rate is reported from ``ElapsedTime-ms`` afterwards rather than
    assumed to equal the request. ``0`` means as fast as the camera will go.

    The caller owns illumination, ROI, exposure and shutters. This function
    changes no device state; it starts a sequence, drains the buffer, and stops.

    ``on_frame(index, image)`` is called for every ``on_frame_every``-th frame,
    **inside the drain loop**, which is the part to think about: time spent in
    the callback is time not spent emptying the circular buffer, and that buffer
    is finite (``CircularBufferFrameCount``, 20 by default = 0.67 s at 30 fps).
    A slow callback drops frames.

    It is offered anyway, because this module can *prove* whether it cost
    anything -- ``ImageNumber`` gaps and ``drop_report()`` both report
    independently of the callback. Measure, do not assume. If the callback is
    too slow, drain in a thread and display from ``frames`` instead of here.
    """
    if n_frames < 1:
        raise ValueError(f"n_frames must be >= 1, got {n_frames}")

    camera = camera or core.getCameraDevice()
    if not camera:
        raise RuntimeError("no camera device set on the core")

    width, height = core.getImageWidth(), core.getImageHeight()
    bytes_per_pixel = core.getBytesPerPixel()
    dtype = _DTYPE_BY_BYTES_PER_PIXEL.get(bytes_per_pixel)
    if dtype is None:
        raise RuntimeError(f"unsupported bytes per pixel: {bytes_per_pixel}")

    frames = np.empty((n_frames, height, width), dtype=dtype)
    records: list[FrameRecord] = []

    if timeout_s is None:
        nominal_s = n_frames * max(interval_ms, core.getExposure()) / 1000.0
        timeout_s = SEQUENCE_TIMEOUT_FLOOR_S + SEQUENCE_TIMEOUT_FACTOR * nominal_s

    core.startSequenceAcquisition(camera, n_frames, interval_ms, True)
    start = time.perf_counter()
    try:
        while len(records) < n_frames:
            if core.getRemainingImageCount() > 0:
                image, md = core.popNextImageAndMD()
                index = len(records)
                frames[index] = image.reshape(height, width)
                records.append(
                    FrameRecord(
                        index=index,
                        image_number=_int_tag(md, "ImageNumber"),
                        elapsed_ms=_float_tag(md, "ElapsedTime-ms"),
                        received_by_core=_tag(md, "TimeReceivedByCore"),
                        host_perf_s=time.perf_counter() - start,
                    )
                )
                if on_frame is not None and index % on_frame_every == 0:
                    on_frame(index, frames[index])
                continue
            if not core.isSequenceRunning(camera):
                # Camera stopped and the buffer is drained: this is all there is.
                break
            if time.perf_counter() - start > timeout_s:
                break
            time.sleep(POLL_INTERVAL_S)
    finally:
        try:
            core.stopSequenceAcquisition(camera)
        except Exception:
            core.stopSequenceAcquisition()

    wall_elapsed_s = time.perf_counter() - start
    return CaptureResult(
        frames=frames[: len(records)],
        records=tuple(records),
        camera=camera,
        exposure_ms=core.getExposure(),
        roi=tuple(core.getROI()),
        binning=_safe_property(core, camera, "Binning"),
        pixel_type=_safe_property(core, camera, "PixelType"),
        n_requested=n_frames,
        requested_interval_ms=interval_ms,
        wall_elapsed_s=wall_elapsed_s,
    )


def _safe_property(core: CMMCorePlus, device: str, prop: str) -> str | None:
    try:
        return core.getProperty(device, prop)
    except Exception:
        return None
