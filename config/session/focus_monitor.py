r"""Watch both cameras while a human turns the focus knob, and report the peak.

    python config/session/focus_monitor.py --seconds 90 --cyan 50 --green 50
    python config/session/focus_monitor.py --seconds 90 --out D:\data\focus

WHAT THIS DOES, AND WHAT IT REFUSES TO DO
-----------------------------------------
It READS `ZDrive` and both cameras, several times a second, and records a focus
score per camera against the Z it was measured at. At the end it reports the Z
of peak focus for each camera.

**IT NEVER WRITES `ZDrive`, or anything else in
`hardware.microscope.COLLISION_DEVICES`.** Focus is driven by the operator at
the stand, which is where SAFETY.md §2 puts it: the 100x Oil has 130 um of
working distance, and the stand runs no escape on a software Z move. The Z sign
convention was measured on 2026-09-05 (`Z_RETRACT_DIRECTION = -1`, smaller Z
retracts) and that does NOT change this script: knowing which way is out does
not make a software Z sweep safe on a stand that will not escape for you. So
this script is the instrument half of a two-person loop: you turn the knob, it
tells you where the peak was.

That division has a real payoff beyond safety. You do not have to FIND focus by
eye -- sweep slowly through it and the recorded curve names the best Z
afterwards, to whatever resolution you swept at.

THE FOCUS METRIC
----------------
Tenengrad (Sobel gradient energy) on the frame, normalised by the frame's own
median so it does not simply track brightness. For fluorescent beads a
defocused image is dimmer AND softer, and a raw gradient sum would reward
"brighter" even when it is more blurred -- e.g. more light from a wider
illuminator setting would look like better focus. Normalising makes it a
sharpness measure.

Reported alongside it, because a single scalar hides the ways focus can lie:

    beads       compact objects whose area falls in a window COMPUTED from the
                effective pixel size and the bead diameter (`bead_area_window`),
                not a fixed one. At 100x with 2x2 binning, 0.130 um/px, a 5 um
                bead is ~38 px across and ~1160 px in AREA -- three orders off
                the 2-40 px that was correct at 4x. A count that RISES as focus
                sharpens is the honest signal.
    area        median area of those objects, in px. This is the check on the
                count: if it sits far from the ~1160 px a 5 um bead should
                cover, the things being counted are not beads.
    %ceil       brightest pixel as a percentage of the 16-bit ceiling. The bar
                is 95%, not 100% -- above that the peak is a lower bound rather
                than a measurement and `from-frame` refuses it.

BOTH CAMERAS AT ONCE
--------------------
Kinetix_blue (Dragon Green, CYAN) and Kinetix_red (the Abvigen red bead, GREEN)
are read on every tick, so this also answers a question the run depends on and
that nothing has checked yet: whether the two arms are PARFOCAL. They share one
objective but sit behind different tube paths and a splitter, so their best Z
can differ. If the two peaks disagree by more than the depth of field (377 nm
green / 414 nm red at NA 1.45, from `optics.cli check`), the two channels cannot
both be in focus at once and that is a bias on any two-colour comparison --
report it rather than splitting the difference silently.

LIGHT
-----
Both lines on for the whole window, so this is a dose (lens 5). Default 50/1000
each, which is 10x below the 500/1000 the run's 1.8 ms exposure was budgeted
for, because this uses a much longer exposure to make beads easy to see. The
`finally` takes the light down, including the engine's master `State` -- the
property whose omission produced a whole fake measurement on 2026-09-06.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# The focus score itself lives in `detection/focus_metric.py` as of 2026-09-07,
# because `hardware/focus.py` -- the guarded Z sweep -- needs the same metric,
# and two copies of a score is exactly how the 4x bead-area window survived
# into a 100x run and counted debris instead of beads.
#
# `DEFAULT_CEILING` is imported AS `CEILING` so this script's %ceil numbers stay
# byte-identical to what it printed before the extraction. That is
# back-compatibility, not endorsement: 65535 is right only while the camera sits
# on a 16-bit port, and these Kinetix bodies read 12-bit (ceiling 4095) on their
# default one. See that module's docstring.
from detection.focus_metric import (
    CLIP_FRACTION,
    DEFAULT_CEILING as CEILING,
    bead_area_window,
    score_frame as measure,
)

# The lab console is cp1252, and this script prints box-drawing and warning
# glyphs. Without this, the first table row raises UnicodeEncodeError from
# inside the sampling loop -- which on 2026-09-06 looked like "the loop took no
# samples", because the run was piped with stderr discarded and so the
# traceback was invisible while the header and the `finally` both printed fine.
# `errors="replace"` rather than a glyph purge: degrading a character is the
# right failure, losing the measurement is not.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ⚠ BINNING AND PIXEL SIZE, MEASURED 2026-09-06.
# `core.getPixelSizeUm()` ALREADY ACCOUNTS FOR BINNING: with the 100x-1x preset
# it returns 0.065 at bin 1x1, 0.130 at 2x2 and 0.260 at 4x4. So it must be read
# AFTER the binning is set and must NOT be multiplied by the bin factor.
# This file used to read it before setting binning and then multiply by 2, which
# gave the right 0.130 only because of that statement order -- load a config that
# already had 2x2, or reorder these two blocks, and it silently became 0.260.
# Reading it after and not scaling removes the ordering dependency entirely.
#
# `trap_from_tracking.pixel_size_um()` used to behave the OPPOSITE way -- it
# reads the table in data/pixel_size.yaml, which is keyed on objective x
# intermediate magnification only and so returned 0.065 at ANY binning. Fixed
# 2026-09-06: it now multiplies by the bin factor, names the binning in its
# provenance string, refuses non-square binning, and cross-checks against
# getPixelSizeUm(). The two paths now agree or refuse.

REPO = Path(__file__).resolve().parents[2]
DEFAULT_CFG = REPO / "config" / "micromanager" / "dualcam_twocolour.cfg"

LINES = ["UV", "CYAN", "GREEN", "RED", "NIR"]

ARMS = [
    # camera, the Aura line that feeds it, label
    ("Kinetix_blue", "CYAN", "green-DG"),
    ("Kinetix_red", "GREEN", "red-Abv"),
]


def light_off(core, engine: str) -> None:
    for prop, value in [("State", "0")] + [(l, "0") for l in LINES] + \
                       [(f"{l}_Intensity", "0") for l in LINES]:
        try:
            core.setProperty(engine, prop, value)
        except Exception:
            pass


def light_on(core, engine: str, levels: dict[str, int]) -> None:
    """Both lines at once. `State` is the engine's master shutter -- without it
    nothing comes out however the lines are set, and Core.Shutter is
    LightEngine rather than Aura so autoshutter never opens this one."""
    for line in LINES:
        core.setProperty(engine, line, "0")
        core.setProperty(engine, f"{line}_Intensity", "0")
    for line, per_mille in levels.items():
        core.setProperty(engine, f"{line}_Intensity", str(int(per_mille)))
        core.setProperty(engine, line, "1")
    core.setProperty(engine, "State", "1")
    core.waitForDevice(engine)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--cfg", default=str(DEFAULT_CFG))
    p.add_argument("--preset-group", default="TwoColour")
    p.add_argument("--preset", default="GreenRed-Widefield")
    p.add_argument("--no-preset", action="store_true",
                   help="do not apply the TwoColour preset (leave the path as found)")
    p.add_argument("--light-device", default="Aura")
    p.add_argument("--cyan", type=int, default=50, help="CYAN per-mille, feeds Kinetix_blue")
    p.add_argument("--green", type=int, default=50, help="GREEN per-mille, feeds Kinetix_red")
    p.add_argument("--exposure-ms", type=float, default=20.0)
    p.add_argument("--binning", default="2x2")
    p.add_argument("--roi", type=int, default=0,
                   help="centred square ROI in binned px; 0 = full frame, which is "
                        "what you want while hunting for beads")
    p.add_argument("--bead-um", type=float, default=5.0,
                   help="bead diameter, for the plausible-area window (both "
                        "species here are ~5 um)")
    p.add_argument("--seconds", type=float, default=90.0)
    p.add_argument("--interval-s", type=float, default=0.5)
    p.add_argument("--out", default=None, help="directory for the CSV and JSON")
    args = p.parse_args(argv)

    from pymmcore_plus import CMMCorePlus

    core = CMMCorePlus()
    print(f"loading {args.cfg}", flush=True)
    core.loadSystemConfiguration(args.cfg)

    if not args.no_preset:
        core.setConfig(args.preset_group, args.preset)
        core.waitForConfig(args.preset_group, args.preset)
        print(f"applied {args.preset_group}/{args.preset} "
              f"(restores post-processing off, which resets on every load)", flush=True)

    objective = core.getStateLabel("Nosepiece")
    print(f"objective: {objective}   pixel {core.getPixelSizeUm()} um/px "
          f"at bin {core.getProperty(ARMS[0][0], 'Binning')}", flush=True)

    core.setAutoShutter(False)
    for cam, _line, _label in ARMS:
        core.setCameraDevice(cam)
        core.setProperty(cam, "Binning", args.binning)
        core.clearROI()
        if args.roi:
            w, h = core.getImageWidth(), core.getImageHeight()
            if args.roi < min(w, h):
                core.setROI((w - args.roi) // 2, (h - args.roi) // 2, args.roi, args.roi)
        core.setExposure(args.exposure_ms)
        print(f"  {cam}: bin {core.getProperty(cam,'Binning')} "
              f"frame {core.getImageWidth()}x{core.getImageHeight()} "
              f"{core.getExposure():.1f} ms", flush=True)

    # Pixel size AFTER the binning is set, and not scaled -- see the note at the
    # top of the file.
    binned_um = core.getPixelSizeUm()
    area_px = bead_area_window(binned_um, args.bead_um)
    print(f"effective pixel {binned_um:.4f} um/px at bin {args.binning}; "
          f"a {args.bead_um} um bead is ~{args.bead_um/binned_um:.1f} px across, "
          f"so a bead counts as {area_px[0]}-{area_px[1]} px", flush=True)

    rows: list[dict] = []
    try:
        light_on(core, args.light_device, {"CYAN": args.cyan, "GREEN": args.green})
        print(f"\nlight ON: CYAN {args.cyan}/1000 + GREEN {args.green}/1000\n", flush=True)
        print("TURN THE FOCUS KNOB SLOWLY THROUGH FOCUS. Sweep past the peak and "
              "back if you can --", flush=True)
        print("the curve is what names the best Z, so a slow pass beats a lucky "
              "stop.\n", flush=True)
        print(f"{'t':>5} {'ZDrive':>10} {'PFS':>10} | "
              f"{'blue sharp':>11} {'beads':>6} {'area':>6} {'%ceil':>6} | "
              f"{'red sharp':>10} {'beads':>6} {'area':>6} {'%ceil':>6}", flush=True)

        t0 = time.perf_counter()
        while (t := time.perf_counter() - t0) < args.seconds:
            try:
                z = float(core.getPosition("ZDrive"))
            except Exception:
                z = float("nan")
            try:
                pfs = str(core.getProperty("PFS", "PFS in Range"))
            except Exception:
                pfs = "?"
            row = {"t_s": round(t, 2), "z_um": z, "pfs": pfs}
            for cam, _line, label in ARMS:
                core.setCameraDevice(cam)
                core.snapImage()
                m = measure(np.asarray(core.getImage()), area_px)
                for k, v in m.items():
                    row[f"{label}.{k}"] = v
            rows.append(row)
            b = {k.split(".")[1]: v for k, v in row.items() if k.startswith("green-DG.")}
            r = {k.split(".")[1]: v for k, v in row.items() if k.startswith("red-Abv.")}
            print(f"{t:5.1f} {z:10.3f} {pfs:>10} | "
                  f"{b['sharp']:11.4f} {b['beads']:6d} {b['bead_area_med']:6.0f} "
                  f"{b['peak_pct_ceiling']:6.1f} | "
                  f"{r['sharp']:10.4f} {r['beads']:6d} {r['bead_area_med']:6.0f} "
                  f"{r['peak_pct_ceiling']:6.1f}", flush=True)
            time.sleep(max(0.0, args.interval_s))
    except KeyboardInterrupt:
        print("\ninterrupted", flush=True)
    finally:
        light_off(core, args.light_device)
        print("\nlight OFF", flush=True)

    if not rows:
        print("no samples taken.", flush=True)
        return 1

    # ── where was focus? ────────────────────────────────────────────────────
    print("\n" + "=" * 72, flush=True)
    print("FOCUS PEAKS", flush=True)
    print("=" * 72, flush=True)
    summary: dict = {"objective": objective, "pixel_um_unbinned": px_um,
                     "exposure_ms": args.exposure_ms, "binning": args.binning,
                     "cyan_per_mille": args.cyan, "green_per_mille": args.green,
                     "n_samples": len(rows)}
    peaks: dict[str, float] = {}
    for _cam, _line, label in ARMS:
        vals = [(rw[f"{label}.sharp"], rw["z_um"], rw[f"{label}.beads"]) for rw in rows]
        best = max(vals, key=lambda v: v[0])
        z_span = (min(v[1] for v in vals), max(v[1] for v in vals))
        peaks[label] = best[1]
        summary[label] = {"best_sharp": best[0], "best_z_um": best[1],
                          "beads_at_best": best[2],
                          "z_swept_um": [z_span[0], z_span[1]]}
        print(f"  {label:9s} peak sharpness {best[0]:.4f} at ZDrive = {best[1]:.3f} um"
              f"   ({best[2]} beads)", flush=True)
        print(f"            Z swept {z_span[0]:.3f} -> {z_span[1]:.3f} um "
              f"({z_span[1]-z_span[0]:.3f} um)", flush=True)

    # Did the knob actually move? A flat Z makes every peak meaningless.
    z_all = [rw["z_um"] for rw in rows if np.isfinite(rw["z_um"])]
    if z_all and (max(z_all) - min(z_all)) < 0.5:
        print("\n  ⚠ ZDrive moved less than 0.5 um over the whole window, so these "
              "'peaks' are\n    noise on a stationary stage, not a focus curve. "
              "Turn the knob during the run.", flush=True)
        summary["verdict"] = "no Z sweep -- peaks meaningless"
    else:
        dz = peaks["green-DG"] - peaks["red-Abv"]
        summary["parfocal_offset_um"] = dz
        # Depth of field at NA 1.45, from optics.cli check on the channel config.
        dof_um = 0.377
        print(f"\n  parfocality: blue peak - red peak = {dz:+.3f} um", flush=True)
        if abs(dz) <= dof_um:
            print(f"    within the {dof_um:.3f} um green depth of field -- the two "
                  f"arms are parfocal to\n    the resolution of this sweep, so one Z "
                  f"focuses both channels.", flush=True)
            summary["verdict"] = "parfocal within depth of field"
        else:
            print(f"    ⚠ LARGER THAN THE {dof_um:.3f} um DEPTH OF FIELD. The two "
                  f"channels cannot both be\n    in focus at once: at the blue peak "
                  f"the red bead is defocused and vice versa.\n    That is a bias on "
                  f"any two-colour comparison, not a nuisance to average\n    away -- "
                  f"a defocused bead is dimmer and wider, which moves both its "
                  f"photometry\n    and its apparent size. Re-run to confirm it "
                  f"reproduces before treating it as\n    a property of the optics "
                  f"rather than of one sweep.", flush=True)
            summary["verdict"] = f"NOT parfocal: {dz:+.3f} um > {dof_um} um DoF"

    worst_clip = max(max(rw[f"{lab}.clip_frac"] for lab in ("green-DG", "red-Abv"))
                     for rw in rows)
    worst_ceil = max(max(rw[f"{lab}.peak_pct_ceiling"] for lab in ("green-DG","red-Abv"))
                     for rw in rows)
    summary["worst_peak_pct_ceiling"] = worst_ceil
    print(f"\n  brightest pixel reached {worst_ceil:.1f}% of the 16-bit ceiling",
          flush=True)
    if worst_ceil >= 100.0 * CLIP_FRACTION:
        print(f"    !! AT OR ABOVE {100*CLIP_FRACTION:.0f}% OF FULL SCALE -- that peak "
              f"is a LOWER BOUND, not a\n    measurement. A clipped bead has a flat "
              f"top, which flattens the focus metric\n    too and reads as a focus "
              f"plateau. Turn the light down and re-run before\n    trusting any of "
              f"it.", flush=True)
    if worst_clip > 1e-4:
        print(f"\n  ⚠ clipping reached {100*worst_clip:.3f}% of pixels. A clipped bead "
              f"has a flat top,\n    which flattens the focus metric too and can read "
              f"as a focus plateau. Lower\n    --cyan/--green or --exposure-ms and "
              f"re-run.", flush=True)
        summary["clipping_warning"] = worst_clip

    if args.out:
        outdir = Path(args.out)
        outdir.mkdir(parents=True, exist_ok=True)
        keys = list(rows[0].keys())
        csv = outdir / "focus_curve.csv"
        with csv.open("w", encoding="utf-8", newline="") as fh:
            fh.write(",".join(keys) + "\n")
            for rw in rows:
                fh.write(",".join(str(rw[k]) for k in keys) + "\n")
        summary["utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        (outdir / "focus_summary.json").write_text(
            json.dumps(summary, indent=2, default=str), encoding="utf-8")
        print(f"\n  curve: {csv}", flush=True)

    print("\n  ZDrive was never written by this script. Set the peak Z at the stand.",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
