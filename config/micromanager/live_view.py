"""Live camera view through pymmcore-plus, in pure stdlib Tk.

    python config/micromanager/live_view.py --cfg config/micromanager/single_cam_red_noDMD.cfg
    python config/micromanager/live_view.py --cfg CFG --exposure-ms 5 --line GREEN --intensity 200
    python config/micromanager/live_view.py --cfg CFG --roi 512 --display 700

WHY THIS EXISTS RATHER THAN MICRO-MANAGER STUDIO
------------------------------------------------
MM Studio has a better viewer than this will ever be, and for setup work --
oiling an objective, focusing, hunting for beads -- it is the right tool:
``C:\\Program Files\\Micro-Manager-2.0\\ImageJ.exe``.

The reason to have this anyway is **camera ownership**. PVCAM hands a Kinetix to
one process at a time (hardware/microscope.SHARED_DEVICES), so a live view in MM
Studio and a scripted acquisition from this repo cannot coexist -- every switch
between looking and running costs a handoff, and a handoff is where the Tweez
GUI's claim on the other body gets renegotiated too. This viewer runs on the
*same* ``CMMCorePlus`` a run would use, so looking and acquiring are one owner.

It is deliberately small: no histogram, no LUTs, no overlays, no saving. Tk 8.6
reads base64 PNG, and stdlib ``zlib`` writes one, so the whole display path
needs nothing that is not in the standard library -- which matters because the
venv on the microscope PC has no matplotlib, no OpenCV and no Qt (checked
2026-09-03).

(PGM would be less code and Tk claims to support it, but ``PhotoImage(data=)``
answers "couldn't recognize image data" for base64 P5 -- Tk's base64 path covers
GIF and PNG only. Measured 2026-09-03, not assumed.)

LIGHT IS OFF UNLESS YOU ASK FOR IT
----------------------------------
No line is enabled and the shutter stays shut without ``--line`` *and*
``--intensity``. Autoshutter is turned **off** so the light state is exactly
what was asked for rather than something MM opens and closes around frames, and
so the exit path can guarantee it goes dark: the line is disabled and the
shutter closed in a ``finally``, including on an exception or a window close.

THE TURRET SHUTTERS ARE IN SERIES, AND BOTH GATE THE IMAGE
----------------------------------------------------------
User, 2026-09-03: "for the imaging and trapping you have to turn on the shutter
on turret 1 and 2." The Ti2-E carries two filter turrets in series, each with
its own shutter (``Turret1Shutter``, ``Turret2Shutter``), so **either one closed
is a black frame** no matter what the light engine is doing. Enabling a line
opens both, because a viewfinder that cannot see is not worth having.

**They are left open on exit, and that is the whole point.** Turret 2 slot 1 is
the optical-tweezers path -- the NIR dichroic that couples 1064 nm to the
objective plus its 750/SP blocker (data/filters.yaml > OT-Dichroic-750LP) -- so
closing that shutter drops a live trap and whatever was held in it.

The first version of this restored their prior state instead, which was wrong in
the exact case that matters: the prior state is *closed* (that is why the field
was black and why the shutters had to be opened at all), so "restore" and "drop
the trap" were the same action. Closing the viewer must never be able to lose a
bead. Pass ``--close-turret-shutters`` if you actually want them shut on the way
out, and only when nothing is trapped.

The light engine is a different matter and *is* taken down on exit -- its line
is disabled and its shutter closed -- because leaving excitation on bleaches the
sample and nothing depends on it staying lit.

Worth knowing rather than discovering: ``Turret2Shutter`` gates a class-4
1064 nm beam path and is **not** in ``hardware/microscope.LASER_DEVICES``, which
covers only ``LUNF-Blanking``. Opening it here is not gated as a laser action.

``--intensity`` is the adapter's own unit, per-mille of full scale (0-1000), not
a percentage -- 200 is 20%. Read it off the device, not from a manual.

WHAT IT CANNOT TELL YOU
-----------------------
The displayed image is autoscaled per frame between two percentiles, so
**brightness on screen carries no absolute information** -- a dim field and a
bright one look the same once the sample fills the range. The raw 16-bit
min/max/percentiles are printed in the window title for that reason. Nothing
here is a photometric measurement, and no frame it shows is saved.
"""

from __future__ import annotations

import argparse
import base64
import struct
import sys
import tkinter as tk
import zlib
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

#: Display refresh. Faster than this buys nothing -- Tk redraws cost more than
#: the camera does at any rate we care about here.
_REFRESH_MS = 50

#: Autoscale percentiles. The low one clips read noise, the high one keeps a
#: single hot pixel from flattening the whole field.
_LO_PCT, _HI_PCT = 2.0, 99.8

#: Ti2-E turret shutters, in series -- either closed is a black frame.
_TURRET_SHUTTERS = ("Turret1Shutter", "Turret2Shutter")


def _png_chunk(tag: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + tag + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))


def to_png_base64(frame8: np.ndarray) -> bytes:
    """An 8-bit 2-D array as base64 8-bit-greyscale PNG, for tk.PhotoImage.

    ``compresslevel=1``: this is a viewfinder in a redraw loop, so the encode
    has to be cheaper than the frame interval. Level 1 on a 800x800 frame is a
    fraction of a millisecond; level 9 is not, and buys nothing that is ever
    written to disk.
    """
    height, width = frame8.shape
    # PNG wants a filter-type byte in front of every scanline; 0 = none.
    scanlines = np.hstack(
        [np.zeros((height, 1), dtype=np.uint8), frame8]
    ).tobytes()
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n"
           + _png_chunk(b"IHDR", ihdr)
           + _png_chunk(b"IDAT", zlib.compress(scanlines, 1))
           + _png_chunk(b"IEND", b""))
    return base64.b64encode(png)


#: Grey levels reserved in the indexed palette. The rest of the 256 entries
#: carry the marker colours.
_GREY_LEVELS = 250

#: Marker colours by palette index. Colour encodes the one thing the operator
#: is deciding -- whether a bead is far enough from its neighbours to be
#: localizable -- so a field that reads mostly green is the field to use.
_ISOLATED, _CROWDED = 250, 251
_MARKER_RGB = {_ISOLATED: (90, 220, 90), _CROWDED: (235, 80, 80)}


def _palette() -> bytes:
    pal = bytearray()
    for i in range(_GREY_LEVELS):
        v = round(i * 255 / (_GREY_LEVELS - 1))
        pal += bytes((v, v, v))
    for i in range(_GREY_LEVELS, 256):
        pal += bytes(_MARKER_RGB.get(i, (0, 0, 0)))
    return bytes(pal)


_PLTE = _palette()


def to_png_base64_indexed(index8: np.ndarray) -> bytes:
    """An indexed 8-bit array as base64 palette PNG (colour type 3).

    Colour costs nothing here, which is the reason for the indirection.
    Truecolour PNG (type 2) needs three bytes per pixel and measured **41.1 ms
    per 800x800 frame against 20.1 ms for greyscale** -- enough to matter
    against a 100 ms tick that already spends 28 ms in Hough. An indexed image
    is one byte per pixel like greyscale, and measured **19.1 ms**: marginally
    *cheaper* than the greyscale path, because quantizing to 250 levels
    compresses slightly better than 256. Verified 2026-09-04 that
    ``tk.PhotoImage`` accepts it.
    """
    height, width = index8.shape
    rows = np.hstack([np.zeros((height, 1), dtype=np.uint8), index8])
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 3, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n"
           + _png_chunk(b"IHDR", ihdr)
           + _png_chunk(b"PLTE", _PLTE)
           + _png_chunk(b"IDAT", zlib.compress(rows.tobytes(), 1))
           + _png_chunk(b"IEND", b""))
    return base64.b64encode(png)


def autoscale(frame: np.ndarray) -> tuple[np.ndarray, dict]:
    """Percentile-stretch to 8 bits, and report what the raw range was."""
    lo, hi = np.percentile(frame, (_LO_PCT, _HI_PCT))
    stats = {
        "min": int(frame.min()),
        "max": int(frame.max()),
        "lo": float(lo),
        "hi": float(hi),
    }
    if hi <= lo:
        return np.zeros(frame.shape, dtype=np.uint8), stats
    scaled = (frame.astype(np.float32) - lo) * (255.0 / (hi - lo))
    return np.clip(scaled, 0, 255).astype(np.uint8), stats


def decimate(frame: np.ndarray, target: int) -> tuple[np.ndarray, int]:
    """Integer-stride subsample so the long edge fits ``target`` pixels.

    Nearest-neighbour on purpose: this is a viewfinder, and an averaging
    downsample would hide exactly the single-pixel saturation worth seeing.
    """
    step = max(1, int(np.ceil(max(frame.shape) / target)))
    return frame[::step, ::step], step


def centre_roi(core, size: int) -> tuple[int, int, int, int]:
    """A centred square ROI of ``size``, clipped to the sensor."""
    core.clearROI()
    full_w, full_h = core.getImageWidth(), core.getImageHeight()
    size = min(size, full_w, full_h)
    return ((full_w - size) // 2, (full_h - size) // 2, size, size)


class Tracker:
    """Rough live detection and linking, for choosing a field. Not a measurement.

    WHAT IT IS FOR, AND WHAT IT IS NOT FOR
    --------------------------------------
    This answers the question the operator actually has while hunting for a
    field -- how many beads, how many are far enough from a neighbour to be
    localizable, and are they moving or stuck -- and nothing else. It cannot
    produce a diffusion coefficient, for a reason that is structural rather
    than a matter of effort: ``live_view`` runs
    ``startContinuousSequenceAcquisition`` and reads ``getLastImage()`` every
    50 ms, so it samples the newest frame at 20 Hz out of a 30 fps stream. It
    *drops frames by design*. An MSD needs the contiguous series with its
    timestamps, which is what ``capture_timestamped`` drains.

    And there is a second reason, learned the hard way on 2026-09-04: the
    tracker used for the measurement had to be changed twice that day -- once
    to make the centroid invariant to intensity scale, once to iterate it to
    convergence -- and each change altered D by several percent. Only the saved
    raw frames made those fixes possible. A live tracker that consumed frames
    and kept positions would have baked the first version's bias into the
    result, and that bias was invisible: it showed up as an apparent D that
    rose with lag and a negative MSD intercept.

    HOW IT IS CHEAP ENOUGH
    ----------------------
    It runs on the frame the viewer has already prepared: ``decimate`` has
    already subsampled to ~800 px and ``autoscale`` has already produced the
    8-bit array that ``cv2.HoughCircles`` requires anyway. Measured 2026-09-04
    on a 2400x2400 frame: blur+Hough costs 217 ms at full resolution and
    **28.5 ms at 800 px, keeping 86% of the detections**. So the decimation the
    display already does is what makes this affordable, and running it at full
    resolution is not an option. Ring drawing is confined to each circle's
    bounding box; the obvious full-frame version cost 1798 ms per tick.

    WHY HOUGH AND NOT SOMETHING CHEAPER
    -----------------------------------
    Hough is 5.7x the cost of the cheapest alternative and it is still the
    right choice, because the number this tool exists to produce is the
    *isolated* count and the cheap detectors get it wrong in opposite
    directions. Measured on one field against the full-resolution offline
    detector (196 objects, 60 isolated at nn >= 12 um):

        HoughCircles                 28.1 ms   167 objects   63 isolated   +5%
        Otsu + connectedComponents    5.2 ms   138 objects   74 isolated  +23%
        dilate local maxima           9.0 ms   435 objects   30 isolated  -50%

    ``dp=2`` halves the accumulator resolution and **halves the cost, 28.0 ms
    to 14.9 ms, while moving the isolated count from +3 to -1 against the same
    ground truth** -- so it is both faster and marginally more accurate here.
    That is not a paradox: the accumulator's resolution sets how precisely a
    centre is voted, and this tool never needs a precise centre. It needs a
    count, and it compares neighbour distances against a 12 um threshold that
    is 37 displayed pixels wide.

    Otsu merges touching beads into one blob that the area filter then
    discards, so it misses neighbours and **over**-reports isolation. Local
    maxima have no size or shape criterion at all, so they invent neighbours
    and **under**-report it by half. Hough votes on the radius, which is
    exactly the criterion that separates one bead from two, and lands within
    5%. At the 100 ms tick that tracking uses, 28 ms is 28% of the budget --
    the cost only mattered while this was being squeezed into 50 ms.

    WHY THE READOUT IS NUMBERS AND THE RINGS ARE ONLY RINGS
    ------------------------------------------------------
    At the measured D, a bead moves 631 nm in 2 s -- 5.8 sensor px, or 2.4 px
    on a 1000 px display. Trails are invisible on this timescale, so drawing
    them would be decoration. What discriminates a moving bead from a stuck one
    is the *number*, and 2 s of history is ample for it: the per-tick step is
    0.9 px against a neighbour spacing of ~65 px, so linking cannot mislink.
    """

    #: A bead counts as stuck if it moves less than this over the history span.
    #:
    #: It has to clear the *detection* noise, not the localization noise of the
    #: offline tracker. Hough's centre is accumulator-quantized to roughly half
    #: a displayed pixel, and a displayed pixel here is 0.10833 x 3 = 325 nm --
    #: so a threshold of 150 nm, which is what this was first set to, classifies
    #: Hough's own rounding and reported 50 of 168 beads as stuck on a field
    #: where essentially none are (2026-09-04). At 300 nm the threshold sits
    #: just under one displayed pixel, and over a 4 s span the expected
    #: Brownian motion is 892 nm -- about 3x it. That ratio is the whole
    #: justification, and it is why the span is 4 s rather than 2.
    STUCK_NM = 300.0

    def __init__(self, px_um: float, isolation_um: float,
                 refresh_ms: int = _REFRESH_MS, history_s: float = 4.0):
        self.px_um = px_um
        self.isolation_um = isolation_um
        self.refresh_ms = refresh_ms
        # History is held in SECONDS, not frames, so changing the refresh rate
        # does not change what "moving" means. That matters because tracking
        # runs at a slower refresh than plain viewing.
        self.n_hist = max(2, int(round(history_s * 1000.0 / refresh_ms)))
        self.hist: list[np.ndarray] = []
        self.counts = {}
        self.iso_mask = np.zeros(0, dtype=bool)

    def update(self, frame8: np.ndarray, step: int) -> np.ndarray:
        """Detect on the displayed 8-bit frame. Returns circles as (x, y, r)."""
        try:
            import cv2  # noqa: PLC0415  (optional -- only --track needs it)
        except ImportError:
            self.counts = {"error": "cv2 not installed"}
            return np.empty((0, 3))

        # Nominal 5 um bead radius in *displayed* pixels. Hough votes on the
        # radius, which is what lets it reject aggregates -- two touching beads
        # do not fit one circle of the expected size.
        r = 2.5 / (self.px_um * step)
        found = cv2.HoughCircles(
            cv2.GaussianBlur(frame8, (9, 9), 2), cv2.HOUGH_GRADIENT, dp=2,
            minDist=int(max(6, 1.4 * r)), param1=80, param2=22,
            minRadius=int(max(3, 0.7 * r)), maxRadius=int(max(6, 1.5 * r)))
        c = np.empty((0, 3)) if found is None else found[0]

        self.hist.append(c[:, :2].copy())
        if len(self.hist) > self.n_hist:
            self.hist.pop(0)

        um = self.px_um * step
        n_iso = 0
        self.iso_mask = np.zeros(len(c), dtype=bool)
        if len(c) > 1:
            d = np.linalg.norm(c[:, None, :2] - c[None, :, :2], axis=-1)
            np.fill_diagonal(d, np.inf)
            self.iso_mask = d.min(axis=1) * um >= self.isolation_um
            n_iso = int(self.iso_mask.sum())

        # moving vs stuck, from the oldest history frame we still hold. Nearest
        # neighbour over the whole history span, which is safe because the span
        # (~2 s, 5.8 sensor px) is far below the neighbour spacing (~65 px).
        n_moving = n_stuck = 0
        if len(self.hist) >= self.n_hist and len(c) and len(self.hist[0]):
            old = self.hist[0]
            d = np.linalg.norm(c[:, None, :2] - old[None, :, :], axis=-1)
            moved = d.min(axis=1) * um * 1e3          # nm over the history span
            n_stuck = int((moved < self.STUCK_NM).sum())
            n_moving = int(len(c) - n_stuck)

        self.counts = {"detected": int(len(c)), "isolated": n_iso,
                       "moving": n_moving, "stuck": n_stuck,
                       "history_s": len(self.hist) * self.refresh_ms / 1000.0}
        return c

    def summary(self) -> str:
        if "error" in self.counts:
            return f"track: {self.counts['error']}"
        c = self.counts
        if not c:
            return "track: warming up"
        return (f"track: {c['detected']} detected  "
                f"GREEN {c['isolated']} isolated (nn>={self.isolation_um:.0f}um)  "
                f"RED {c['detected']-c['isolated']} crowded  "
                f"{c['moving']} moving  {c['stuck']} stuck "
                f"(<{self.STUCK_NM:.0f}nm)  [{c['history_s']:.1f}s]")


def index_with_rings(frame8: np.ndarray, circles: np.ndarray,
                     isolated: np.ndarray) -> np.ndarray:
    """Quantize to the palette and ring each detection in its category colour.

    Green for isolated, red for crowded, because that is the decision the
    operator is making. Drawn per circle inside its own bounding box: the
    obvious version, one full-frame ``mgrid`` per circle, is N x H x W and
    measured **1798 ms per tick** on 170 circles at 800 px -- 36x the budget it
    was then trying to fit. Confined to the box it is 8 ms.
    """
    idx = (frame8.astype(np.uint16) * (_GREY_LEVELS - 1) // 255).astype(np.uint8)
    if not len(circles):
        return idx
    H, W = idx.shape
    for (cx, cy, r), iso in zip(circles, isolated):
        pad = int(r) + 2
        x0, x1 = max(0, int(cx) - pad), min(W, int(cx) + pad + 1)
        y0, y1 = max(0, int(cy) - pad), min(H, int(cy) + pad + 1)
        if x1 <= x0 or y1 <= y0:
            continue
        yy, xx = np.mgrid[y0:y1, x0:x1]
        d2 = (xx - cx) ** 2 + (yy - cy) ** 2
        ring = (d2 >= (r - 1) ** 2) & (d2 <= (r + 1) ** 2)
        idx[y0:y1, x0:x1][ring] = _ISOLATED if iso else _CROWDED
    return idx


class Viewer:
    def __init__(self, core, root, display_px: int, camera: str,
                 tracker: "Tracker | None" = None,
                 refresh_ms: int = _REFRESH_MS):
        self.core, self.root, self.display_px = core, root, display_px
        self.camera = camera
        self.tracker = tracker
        self.refresh_ms = refresh_ms
        self.label = tk.Label(root, bd=0)
        self.label.pack()
        self.status = None
        if tracker is not None:
            self.status = tk.Label(root, bd=0, anchor="w",
                                   font=("TkFixedFont", 9))
            self.status.pack(fill="x")
        self.photo = None
        self.n_shown = 0
        root.bind("<Escape>", lambda _e: root.destroy())

    def tick(self) -> None:
        try:
            frame = self.core.getLastImage()
        except Exception:
            # No frame in the buffer yet -- normal for the first few ticks.
            self.root.after(self.refresh_ms, self.tick)
            return

        small, step = decimate(np.asarray(frame), self.display_px)
        frame8, stats = autoscale(small)
        if self.tracker is not None:
            circles = self.tracker.update(frame8, step)
            idx = index_with_rings(frame8, circles, self.tracker.iso_mask)
            self.status.configure(text=self.tracker.summary())
            self.photo = tk.PhotoImage(data=to_png_base64_indexed(idx))
        else:
            # Untouched greyscale path -- there is no reason to requantize a
            # frame that carries no markers.
            self.photo = tk.PhotoImage(data=to_png_base64(frame8))
        self.label.configure(image=self.photo)
        self.n_shown += 1
        self.root.title(
            f"{self.camera}  {frame.shape[1]}x{frame.shape[0]} "
            f"(shown 1/{step})  exp {self.core.getExposure():.1f} ms  "
            f"raw {stats['min']}-{stats['max']}  "
            f"stretch {stats['lo']:.0f}-{stats['hi']:.0f}  n={self.n_shown}"
        )
        self.root.after(self.refresh_ms, self.tick)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cfg", required=True, type=Path, help="Micro-Manager .cfg")
    ap.add_argument("--exposure-ms", type=float, default=None,
                    help="camera exposure; unset leaves whatever the device has")
    ap.add_argument("--roi", type=int, default=None, metavar="PX",
                    help="centred square ROI, in sensor pixels; unset = full frame")
    ap.add_argument("--binning", default=None, help='e.g. "1x1", "2x2"')
    ap.add_argument("--display", type=int, default=800, metavar="PX",
                    help="longest on-screen edge (default 800)")
    ap.add_argument("--light-device", default="LightEngine", metavar="LABEL",
                    help="which engine the line lives on: LightEngine "
                         "(SpectraIII, COM3) or Aura (AuraIII, COM7)")
    ap.add_argument("--line", default=None, metavar="NAME",
                    help="light-engine line to enable, e.g. GREEN. Off unless given")
    ap.add_argument("--intensity", type=float, default=None, metavar="0-1000",
                    help="line intensity in the adapter's per-mille unit")
    ap.add_argument("--refresh-ms", type=int, default=None, metavar="MS",
                    help="display tick. Default 50 (20 Hz) for plain viewing "
                         "and 100 (10 Hz) with --track, because tracking costs "
                         "a measured 34.7 ms median and 70 ms worst case -- "
                         "which fits a 100 ms tick with room and does not fit "
                         "a 33 ms one. The tracking history is held in seconds, "
                         "so the tick rate does not change what 'moving' means")
    ap.add_argument("--track", action="store_true",
                    help="detect beads live with cv2.HoughCircles and report "
                         "how many are isolated, moving and stuck. FIELD "
                         "SELECTION ONLY -- this samples the newest frame at "
                         "20 Hz out of a 30 fps stream, so it drops frames by "
                         "design and cannot produce an MSD. Runs on the frame "
                         "the display has already decimated to 8 bits, which "
                         "is what makes it affordable: 28.5 ms at 800 px "
                         "against 217 ms at 2400 px")
    ap.add_argument("--track-isolation-um", type=float, default=12.0,
                    metavar="UM",
                    help="a bead counts as isolated when its nearest "
                         "neighbour is at least this far. 12 um is set by the "
                         "localization geometry, not by hydrodynamics: the "
                         "disk is ~27 px in radius, so a centroid window big "
                         "enough to hold it cannot exclude a closer neighbour "
                         "(default 12)")
    ap.add_argument("--close-turret-shutters", action="store_true",
                    help="shut Turret1/2Shutter on exit. OFF by default: "
                         "Turret2Shutter is the 1064 trap path and closing it "
                         "drops a live trap. Only use with nothing trapped")
    args = ap.parse_args()

    if (args.line is None) != (args.intensity is None):
        ap.error("--line and --intensity go together: both, or neither")

    from pymmcore_plus import CMMCorePlus  # noqa: PLC0415  (slow import)

    core = CMMCorePlus()
    core.loadSystemConfiguration(str(args.cfg))
    camera = core.getCameraDevice()
    shutter = core.getShutterDevice()
    lit = False
    turret_shutters_before: dict[str, bool] = {}

    try:
        if args.binning is not None:
            core.setProperty(camera, "Binning", args.binning)
        if args.roi is not None:
            core.setROI(*centre_roi(core, args.roi))
        if args.exposure_ms is not None:
            core.setExposure(args.exposure_ms)

        # Autoshutter off first: it is what would otherwise reopen the shutter
        # per frame, and the point of the exit path is that dark means dark.
        core.setAutoShutter(False)
        core.setShutterOpen(False)
        if args.line is not None:
            engine = args.light_device
            if args.line not in core.getDevicePropertyNames(engine):
                lines = sorted(p for p in core.getDevicePropertyNames(engine)
                               if p.isupper())
                ap.error(f"{engine} has no line {args.line!r}. It has: "
                         f"{', '.join(lines) or '(none)'}")
            core.setProperty(engine, f"{args.line}_Intensity", args.intensity)
            core.setProperty(engine, args.line, 1)
            # The shutter role points at whichever engine the .cfg named, which
            # is not necessarily the one being driven -- opening it would then
            # open the *other* engine and leave this one dark. Point it here.
            core.setShutterDevice(engine)
            core.setShutterOpen(True)
            lit = True

            # Both turret shutters are in series with the image. Record what
            # they were so exit restores rather than forces -- Turret 2 is the
            # 1064 trap path and may be holding a bead.
            for label in _TURRET_SHUTTERS:
                try:
                    turret_shutters_before[label] = core.getShutterOpen(label)
                    core.setShutterOpen(label, True)
                    print(f"  {label}: {turret_shutters_before[label]} -> True")
                except Exception as exc:
                    print(f"  {label}: could not open ({exc})")
            print(f"LIGHT ON: {engine}.{args.line} at {args.intensity:.0f}/1000 "
                  f"(per-mille, so {args.intensity / 10:.1f}%). "
                  f"Closes when this window closes.")
            if shutter != engine:
                print(f"  note: shutter role moved {shutter} -> {engine} "
                      "for this session, and restored on exit.")
        else:
            print("Light off (no --line given) -- expect a dark field.")

        print(f"{camera}: {core.getImageWidth()}x{core.getImageHeight()}, "
              f"exposure {core.getExposure():.1f} ms. Esc or close the window to stop.")

        core.startContinuousSequenceAcquisition(0)
        root = tk.Tk()
        if args.refresh_ms is None:
            args.refresh_ms = 100 if args.track else _REFRESH_MS
            if args.track:
                print(f"display tick set to {args.refresh_ms} ms (10 Hz) for "
                      "tracking; pass --refresh-ms to override")
        tracker = None
        if args.track:
            px_um = core.getPixelSizeUm()
            if not px_um:
                print("--track needs a pixel size and getPixelSizeUm() "
                      "answers 0.0 -- no PixelSize preset matches this "
                      "nosepiece position. See config/micromanager/"
                      "set_pixel_size.py", file=sys.stderr)
                return 2
            tracker = Tracker(px_um, args.track_isolation_um, args.refresh_ms)
            print(f"TRACKING: Hough on the displayed 8-bit frame, "
                  f"pixel {px_um:.5f} um, isolation "
                  f"{args.track_isolation_um:.0f} um. Field selection only -- "
                  f"this samples 20 Hz out of 30 fps and cannot make an MSD.")
        Viewer(core, root, args.display, camera, tracker,
               args.refresh_ms).tick()
        root.mainloop()
    finally:
        for step, action in (
            ("stop acquisition", lambda: core.stopSequenceAcquisition()),
            ("close shutter", lambda: core.setShutterOpen(False)),
            ("disable line", lambda: core.setProperty(
                args.light_device, args.line, 0) if lit else None),
            # NOT restored by default -- see the module docstring. Closing
            # Turret2Shutter drops a live 1064 trap, and its prior state is
            # closed, so restoring it is exactly the thing not to do.
            ("close turret shutters", lambda: [
                core.setShutterOpen(label, False)
                for label in turret_shutters_before
            ] if args.close_turret_shutters else
                print(f"  left open: {', '.join(turret_shutters_before)} "
                      "(closing Turret2Shutter would drop a live trap)")
                if turret_shutters_before else None),
            ("restore shutter role", lambda: core.setShutterDevice(shutter)
             if lit and shutter != args.light_device else None),
            ("restore autoshutter", lambda: core.setAutoShutter(True)),
            ("unload devices", lambda: core.unloadAllDevices()),
        ):
            try:
                action()
            except Exception as exc:  # keep going -- later steps still matter
                print(f"cleanup warning ({step}): {exc}")
        print("[dark, camera released]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
