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


class Viewer:
    def __init__(self, core, root, display_px: int, camera: str):
        self.core, self.root, self.display_px = core, root, display_px
        self.camera = camera
        self.label = tk.Label(root, bd=0)
        self.label.pack()
        self.photo = None
        self.n_shown = 0
        root.bind("<Escape>", lambda _e: root.destroy())

    def tick(self) -> None:
        try:
            frame = self.core.getLastImage()
        except Exception:
            # No frame in the buffer yet -- normal for the first few ticks.
            self.root.after(_REFRESH_MS, self.tick)
            return

        small, step = decimate(np.asarray(frame), self.display_px)
        frame8, stats = autoscale(small)
        self.photo = tk.PhotoImage(data=to_png_base64(frame8))
        self.label.configure(image=self.photo)
        self.n_shown += 1
        self.root.title(
            f"{self.camera}  {frame.shape[1]}x{frame.shape[0]} "
            f"(shown 1/{step})  exp {self.core.getExposure():.1f} ms  "
            f"raw {stats['min']}-{stats['max']}  "
            f"stretch {stats['lo']:.0f}-{stats['hi']:.0f}  n={self.n_shown}"
        )
        self.root.after(_REFRESH_MS, self.tick)


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
        Viewer(core, root, args.display, camera).tick()
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
