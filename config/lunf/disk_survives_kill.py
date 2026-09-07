r"""Does the CSU-W1 pinhole disk survive the NIS force-kill?

    python config/lunf/disk_survives_kill.py --dry-run
    python config/lunf/disk_survives_kill.py --kill --disk-confirmed-spinning

THE QUESTION THIS EXISTS FOR
----------------------------
`handoff_from_nis.py` established that the LUN-F fiber shutter survives a
force-kill of NIS, which made the handoff a supported workflow for *laser*
control (`kb/decisions/2026-09-02-lunf-first-light-measured-limits.md` §9).

On 2026-09-07 the confocal path was driven from this repository for the first
time, and the frames came back **bright but wrong**: 5–53x contrast over
AllOff, and a stationary pinhole grid where the sample should be. Spectral peak
over median on a 400 px central crop reached 210,347 on the blue arm, while the
one condition with no signal at all sat at 129 — so the grid is in the
illumination, not the sensor. Period ~46.8 px = 30.3 µm at the sample.

The disk was not spinning. Two explanations survive that observation and this
script separates them:

    the kill stops the disk    -> the handoff cannot produce a confocal image
                                  at all. A hard limit, and one worth knowing
                                  before anyone builds on it.
    it was never started       -> the disk just needs spinning up once in NIS
                                  and the handoff is fine for confocal too.

WHY THIS IS "KILL, THEN WATCH" AND NOT "BEFORE VERSUS AFTER"
------------------------------------------------------------
The spinning baseline **cannot be measured from here.** While NIS is up it
holds the Ti2 and a camera, so Micro-Manager cannot load at all — there is no
way to take the "disk spinning" reference frame through this repo. That half
has to be confirmed by eye in NIS, which is why `--disk-confirmed-spinning` is
a required, explicit flag rather than something this script checks. It cannot
check it. Passing that flag is you asserting it.

The script then samples repeatedly after the kill rather than once, because a
disk that coasts down would read as "survived" if you only looked immediately.
A rising periodicity ratio across the delays is a spin-down.

WHAT IT MEASURES
----------------
For each delay: one frame with 488 open, one with all blanking closed, then the
ratio of the largest off-centre power-spectrum term to the median on a central
crop of the difference. Low ratio = smooth illumination = spinning. High ratio
= a stationary grid. The 2026-09-07 numbers put the two regimes orders of
magnitude apart, so this does not need a delicate threshold.

488 rather than 561 because it is by far the brighter line on this sample
(53x versus 5.2x contrast), which makes the metric least ambiguous.

SAFETY
------
This force-kills NIS, which leaves the LUN-F shutter open with no software
owning it — the same exposure `handoff_from_nis.py` documents. Know your exit
route before running: **restart NIS and close it normally.** That is the only
way to close `Fiber1`; it is not reachable from this repo. This script closes
all four blanking lines, both turret shutters and both light engines on every
exit path including Ctrl+C, so the light is gated off even while the shutter
stays open.

It does not move the objective, Z, or PFSOffset, and writes nothing in
`hardware.microscope.COLLISION_DEVICES`.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO = Path(__file__).resolve().parents[2]
#: No DMD in this one, so it loads on the ordinary v75 core. The DMD needs an
#: interface-71 core (kb/decisions/2026-09-07-dmd-on-v71-and-blue-flip.md) and
#: nothing here wants it.
DEFAULT_CFG = REPO / "config" / "micromanager" / "dualcam_noDMD.cfg"

NIS_IMAGE = "nis_ar.exe"
SPECTRA_LINES = ("VIOLET", "BLUE", "CYAN", "TEAL", "GREEN", "YELLOW", "RED", "NIR")
AURA_LINES = ("UV", "CYAN", "GREEN", "RED", "NIR")
BLANKING = ("line2", "line4", "line6", "line8")

#: 2026-09-07: the two regimes were 129 (no signal, smooth) against
#: 25,978-210,347 (stationary grid). Anything between is a real result and
#: should be reported rather than rounded to a verdict.
SMOOTH_MAX = 2_000
GRID_MIN = 10_000


def nis_pids() -> list[int]:
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {NIS_IMAGE}", "/NH"],
                         capture_output=True, text=True).stdout
    pids = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].lower() == NIS_IMAGE.lower():
            try:
                pids.append(int(parts[1]))
            except ValueError:
                pass
    return pids


def pinhole_ratio(diff: np.ndarray, crop: int = 400) -> tuple[float, float]:
    """(peak/median power ratio, period in px) of the strongest periodicity.

    Off-centre only: the DC and near-DC terms carry the illumination envelope,
    which is smooth in both regimes and would swamp the comparison.
    """
    h, w = diff.shape
    y0, x0 = (h - crop) // 2, (w - crop) // 2
    c = diff[y0:y0 + crop, x0:x0 + crop].astype(np.float64)
    c = c - c.mean()
    p = np.abs(np.fft.fftshift(np.fft.fft2(c))) ** 2
    n = p.shape[0]
    yy, xx = np.mgrid[:n, :n]
    r = np.hypot(yy - n // 2, xx - n // 2)
    p[r < 4] = 0.0
    med = float(np.median(p[r >= 4]))
    peak = float(p.max())
    py, px = np.unravel_index(p.argmax(), p.shape)
    dist = float(np.hypot(py - n // 2, px - n // 2))
    period = n / dist if dist > 0 else float("nan")
    return (peak / med if med > 0 else float("inf")), period


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true",
                   help="check preconditions and print the checklist; kill nothing")
    g.add_argument("--kill", action="store_true",
                   help="force-kill NIS, then watch the periodicity")
    p.add_argument("--disk-confirmed-spinning", action="store_true",
                   help="REQUIRED with --kill: you have seen the disk spinning in NIS. "
                        "This script cannot verify it -- MM cannot load while NIS is up.")
    p.add_argument("--cfg", default=str(DEFAULT_CFG))
    p.add_argument("--nm", default="488", choices=("405", "488", "561", "640"))
    p.add_argument("--exposure-ms", type=float, default=200.0)
    p.add_argument("--binning", default="2x2")
    p.add_argument("--turret1-state", default="1",
                   help="FilterTurret1 position. ANY non-zero works -- 0 holds the "
                        "MXR00724 multiband cube, which blocks the confocal path "
                        "(measured 2026-09-07: state 0 gave 1.00x contrast, states "
                        "1/2/3 gave 5.16/5.15/5.13x, i.e. they are empty slots).")
    p.add_argument("--delays", default="0,5,15,30,60",
                   help="seconds after the kill at which to sample")
    p.add_argument("--out", default=None, help="directory for the JSON report")
    a = p.parse_args(argv)

    line_prop = {"405": "line2", "488": "line4", "561": "line6", "640": "line8"}[a.nm]
    delays = [float(x) for x in a.delays.split(",") if x.strip()]

    pids = nis_pids()
    print(f"[before] {NIS_IMAGE} pids : {pids if pids else 'none'}", flush=True)

    if not pids:
        print("\nREFUSING: NIS is not running, so there is nothing to hand off from\n"
              "and no reason to believe the disk was ever spun up. Start NIS, spin\n"
              "the disk, confirm it by eye, then re-run.", flush=True)
        return 2

    if a.dry_run:
        print("\n[dry-run] NIS is up. Before running with --kill:\n"
              "   1. confirm in NIS that the pinhole disk is SPINNING -- the grid\n"
              "      texture must be absent in a live confocal view\n"
              "   2. know your exit route: restarting NIS is the only way to close\n"
              "      Fiber1 afterwards\n"
              "   3. re-run with --kill --disk-confirmed-spinning", flush=True)
        return 0

    if not a.disk_confirmed_spinning:
        print("\nREFUSING: --kill needs --disk-confirmed-spinning.\n"
              "This script cannot check whether the disk is spinning, because MM\n"
              "cannot load a camera while NIS holds it. Confirm it by eye in NIS\n"
              "first; passing the flag is you asserting that you did.", flush=True)
        return 2

    print(f"\n-> taskkill /F on {NIS_IMAGE} {pids}", flush=True)
    rc = subprocess.run(["taskkill", "/F"] + sum([["/PID", str(x)] for x in pids], []),
                        capture_output=True, text=True)
    print("   " + (rc.stdout or rc.stderr).strip(), flush=True)
    t_kill = time.perf_counter()
    if nis_pids():
        print("   NIS still present -- aborting rather than reporting a null result",
              flush=True)
        return 1

    from pymmcore_plus import CMMCorePlus

    core = CMMCorePlus()
    print(f"\nloading {a.cfg}", flush=True)
    core.loadSystemConfiguration(a.cfg)
    core.setAutoShutter(False)

    def sp(dev: str, prop: str, val: str) -> None:
        try:
            core.setProperty(dev, prop, val)
        except Exception as e:
            print(f"   ! {dev}.{prop}={val}: {str(e)[:60]}", flush=True)

    def blanking(**kw: str) -> None:
        for ln in BLANKING:
            sp("LUNF-Blanking", ln, "0")
        for ln, v in kw.items():
            sp("LUNF-Blanking", ln, v)

    def shutdown() -> None:
        blanking()
        for L in SPECTRA_LINES:
            sp("LightEngine", L, "0")
            sp("LightEngine", f"{L}_Intensity", "0")
        sp("LightEngine", "State", "0")
        for L in AURA_LINES:
            sp("Aura", L, "0")
            sp("Aura", f"{L}_Intensity", "0")
        sp("Aura", "State", "0")
        sp("Turret1Shutter", "State", "0")
        sp("Turret2Shutter", "State", "0")

    def snap(cam: str) -> np.ndarray:
        core.setCameraDevice(cam)
        core.setExposure(a.exposure_ms)
        core.snapImage()
        return np.asarray(core.getImage()).astype(np.float32)

    rows: list[dict] = []
    try:
        blanking()
        sp("LightEngine", "State", "0")
        sp("Aura", "State", "0")
        sp("FilterTurret1", "State", a.turret1_state)
        sp("CSUW1-Bright", "BrightFieldPort", "Confocal")
        sp("CSUW1-Shutter", "State", "Open")
        sp("CSUW1-Dichroic", "Label", "on")
        sp("CSUW1-Port", "Label", "blue_red")
        sp("CSUW1-Filter_Blue", "Label", "488")
        sp("CSUW1-Filter_Red", "Label", "555")
        sp("Turret1Shutter", "State", "1")
        sp("Turret2Shutter", "State", "1")
        cam = "Kinetix_blue" if a.nm == "488" else "Kinetix_red"
        sp(cam, "Port", "Dynamic Range")
        sp(cam, "Binning", a.binning)
        # Port change resets post-processing, so this must follow it.
        for i in range(1, 7):
            sp(cam, f"PP  {i}   ENABLED", "No")

        print(f"\n{a.nm} nm on {cam}, {a.exposure_ms:.0f} ms, bin {a.binning}, "
              f"FilterTurret1 state {a.turret1_state}", flush=True)
        print(f"\n{'t+s':>6} {'contrast':>9} {'peak/median':>12} {'period px':>10}  verdict",
              flush=True)

        for d in delays:
            while (time.perf_counter() - t_kill) < d:
                time.sleep(0.05)
            blanking(**{line_prop: "1"})
            time.sleep(0.35)
            on = snap(cam)
            blanking()
            time.sleep(0.35)
            off = snap(cam)
            ratio, period = pinhole_ratio(on - off)
            contrast = float(np.percentile(on, 99.9) / max(np.percentile(off, 99.9), 1.0))
            if ratio <= SMOOTH_MAX:
                v = "SMOOTH -- disk spinning"
            elif ratio >= GRID_MIN:
                v = "GRID -- disk stopped"
            else:
                v = "AMBIGUOUS -- report as measured"
            t = time.perf_counter() - t_kill
            print(f"{t:6.1f} {contrast:8.2f}x {ratio:12.0f} {period:10.1f}  {v}", flush=True)
            rows.append({"t_after_kill_s": round(t, 2), "contrast": round(contrast, 3),
                         "peak_over_median": round(ratio, 1),
                         "period_px": round(period, 2), "verdict": v})
    finally:
        shutdown()
        print("\nall blanking closed, both engines off, both turret shutters closed",
              flush=True)
        print("REMINDER: Fiber1 may still be open. Restart NIS and close it normally.",
              flush=True)
        try:
            core.unloadAllDevices()
        except Exception:
            pass

    if rows:
        first, last = rows[0], rows[-1]
        print("\nCONCLUSION")
        if all(r["verdict"].startswith("SMOOTH") for r in rows):
            print("  The disk SURVIVES the kill. The 2026-09-07 grid was because it had\n"
                  "  never been spun up, not because the kill stops it. The handoff is\n"
                  "  usable for confocal -- spin the disk in NIS first.")
        elif all(r["verdict"].startswith("GRID") for r in rows):
            print("  The disk STOPS at the kill. The handoff cannot produce a confocal\n"
                  "  image; it is a laser-control workflow only. Record this as a hard\n"
                  "  limit against §9.")
        elif first["verdict"].startswith("SMOOTH") and last["verdict"].startswith("GRID"):
            print(f"  SPIN-DOWN: smooth at t+{first['t_after_kill_s']}s, grid by "
                  f"t+{last['t_after_kill_s']}s. The disk coasts. Any confocal frame\n"
                  "  after a kill has a shelf life, and it needs measuring properly\n"
                  "  before anything depends on it.")
        else:
            print("  Mixed. Read the table rather than this line.")

    if a.out:
        d = Path(a.out)
        d.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        f = d / f"disk_survives_kill_{stamp}.json"
        f.write_text(json.dumps({
            "utc": stamp, "cfg": a.cfg, "nm": a.nm, "line": line_prop,
            "exposure_ms": a.exposure_ms, "binning": a.binning,
            "turret1_state": a.turret1_state, "killed_pids": pids,
            "smooth_max": SMOOTH_MAX, "grid_min": GRID_MIN, "samples": rows,
        }, indent=2), encoding="utf-8")
        print(f"\nwrote {f}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
