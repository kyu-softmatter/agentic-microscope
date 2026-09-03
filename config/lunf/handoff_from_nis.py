"""Hand the LUN-F over from NIS to Python, and prove the fiber shutter survived.

THE PROBLEM THIS EXISTS FOR
---------------------------
Three things about the LUN-F are only reachable through NIS:

    the fiber shutter   `Fiber1` in the LUN-F Pad. Not exported from
                        v6_w32_device_LUNF.dll -- SetShutterState,
                        CLxLUNFShutter and ILxDeviceShutter are string-table
                        and RTTI names, not entry points.
    the DAC levels      until lunf_power.PROTOCOL is named, the only way to set
                        a per-line voltage is the NIS slider.
    nothing else        blanking is ours; see config/lunf/probe_lunf.py.

And NIS holds Dev1's port0 exclusively while it runs, so Python cannot drive the
blanking lines alongside it (-200587). The two cannot share, which forces a
handoff: let NIS open the shutter and set the levels, then take the DAQ.

WHAT IS ACTUALLY BEING TESTED
-----------------------------
On 2026-09-02 the shutter was observed open with NIS gone, and separately the
user reported that closing NIS closes `Fiber1`. Those do not reconcile, and the
test that would have separated them never ran: a `taskkill` was issued against a
stale PID and returned "process not found", so nothing was killed. The
`kb/decisions/2026-09-02-lunf-first-light-measured-limits.md` §9 entry records
observations rather than a mechanism, deliberately.

This script runs the missing test properly:

    force-kill, then light  -> the shutter closes on NIS's *clean* shutdown
                               path, which a SIGKILL-equivalent skips. Handoff
                               is a supported workflow.
    force-kill, then dark   -> the LUN-F closes it on loss of the USB link, i.e.
                               a watchdog. No handoff is possible and headless
                               operation needs the protocol from Nikon.

It **refuses to run if NIS is not already up**, which is the specific way the
first attempt failed silently.

SAFETY
------
A force-kill can leave a laser emitting with no software owning it. Before
running: know how you will turn it off again. The reliable route is to restart
NIS and close it normally -- that is the behaviour being exploited here. This
script also closes all four blanking lines when it finishes, which gates the
light off even if the shutter stays open.

    python config/lunf/handoff_from_nis.py --dry-run   # inspect, kill nothing
    python config/lunf/handoff_from_nis.py --kill
"""

from __future__ import annotations

import argparse
import ctypes as C
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_lunf import WL, OPEN, CLOSED, Daq, FTD2XX, FT4222_SERIAL  # noqa: E402

NIS_IMAGE = "nis_ar.exe"
FT_OPEN_BY_SERIAL = 1


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


def ft4222_free() -> bool | None:
    """True if interface A can be opened by us, i.e. NIS has let go of it."""
    try:
        os.add_dll_directory(os.path.dirname(FTD2XX))
        d2 = C.WinDLL(FTD2XX)
    except OSError:
        return None
    h = C.c_void_p()
    rc = d2.FT_OpenEx(FT4222_SERIAL, FT_OPEN_BY_SERIAL, C.byref(h))
    if rc == 0:
        d2.FT_Close(h)
        return True
    return False


def daq_free(daq: Daq) -> bool:
    """Reserve-only probe of one blanking line. Never writes a level, so the
    shutter state cannot be disturbed by asking."""
    line = WL["561"][0]
    t = C.c_void_p()
    daq.d.DAQmxCreateTask(b"", C.byref(t))
    try:
        if daq.d.DAQmxCreateDOChan(t, line.encode(), b"", C.c_int32(0)) != 0:
            return False
        rc = daq.d.DAQmxTaskControl(t, C.c_int32(4))       # Reserve
        if rc == 0:
            daq.d.DAQmxTaskControl(t, C.c_int32(5))        # Unreserve
            return True
        return False
    finally:
        daq.d.DAQmxClearTask(t)


def report(daq: Daq, when: str) -> None:
    print(f"  [{when}] nis_ar.exe pids   : {nis_pids() or 'none'}")
    print(f"  [{when}] FT4222 A openable : {ft4222_free()}")
    print(f"  [{when}] Dev1 line6 free   : {daq_free(daq)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="inspect only, kill nothing")
    g.add_argument("--kill", action="store_true", help="force-kill NIS and test the shutter")
    ap.add_argument("--nm", default="561", choices=sorted(WL))
    ap.add_argument("--period", type=float, default=0.5)
    ap.add_argument("--repeat", type=int, default=10)
    a = ap.parse_args()

    daq = Daq()
    pids = nis_pids()
    print("BEFORE")
    report(daq, "before")
    print()

    if not pids:
        print(f"!! {NIS_IMAGE} is not running -- nothing to hand over from.")
        print("   Start NIS, open Fiber1, set the line you want, confirm it emits,")
        print("   then run this again. Refusing rather than reporting a null result:")
        print("   the first attempt at this test failed exactly here, silently.")
        return 2

    if a.dry_run:
        print("[dry-run] NIS is up and holding the hardware. Re-run with --kill to")
        print("          force-kill it and see whether the fiber shutter survives.")
        return 0

    print(f"-> taskkill /F on {NIS_IMAGE} {pids}")
    rc = subprocess.run(["taskkill", "/F"] + sum([["/PID", str(p)] for p in pids], []),
                        capture_output=True, text=True)
    print(f"   {rc.stdout.strip() or rc.stderr.strip()}")
    if rc.returncode != 0:
        print("!! kill failed -- aborting rather than guessing at the state")
        return 1

    for _ in range(40):
        if not nis_pids():
            break
        time.sleep(0.25)
    else:
        print("!! process still present after 10 s -- aborting")
        return 1

    time.sleep(1.5)
    print("\nAFTER")
    report(daq, "after")

    line = WL[a.nm][0]
    print(f"\n-> blinking {a.nm} nm on {line}: {a.repeat}x {a.period}s on/off")
    print("   THIS IS THE ANSWER -- watch the sample\n")
    t0 = time.time()
    try:
        daq.close_all()
        time.sleep(0.5)
        for i in range(1, a.repeat + 1):
            daq.write_line(line, OPEN)
            time.sleep(a.period)
            daq.write_line(line, CLOSED)
            time.sleep(a.period)
            print(f"   t+{time.time()-t0:5.1f}s  blink {i}/{a.repeat}", flush=True)
    finally:
        daq.close_all()
        print("\n   all blanking CLOSED")

    print(f"\nDid {a.nm} blink after the force-kill?")
    print("  yes -> the shutter survives a kill, so NIS's clean shutdown is what")
    print("         closes it. Handoff works: bootstrap in NIS, kill, drive here.")
    print("  no  -> the LUN-F closes the shutter when the host link drops. No")
    print("         handoff; headless operation needs Nikon's protocol.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
