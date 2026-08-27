"""Measure host-to-instrument latency for all three control surfaces, in parallel.

Answers the question that decides what can be driven from Python at all: how
long does one command take, and how much does it vary? Numbers in hand for
comparison -- ``core.setProperty`` on a NIDAQ line measured 5.4 us
(config/micromanager/verify_lunf_daq.py). The tweezers TCP round trip and the
piezo DLL round trip have never been measured.

    --dry-run              stub drivers, no hardware. Proves the ordering and
                           the shared clock/log work. Runs anywhere.
    --tweezers             Tweez 300 GUI over TCP
    --micromanager CFG     Micro-Manager, via pymmcore-plus
    --piezo LINK           NPC-D piezo, via the vendor DLL ("sim:/NPC6330" for
                           the DLL's own simulator)
    --parallel             run the selected subsystems concurrently, in threads,
                           instead of one after another

EVERY MEASUREMENT HERE IS READ-ONLY
-----------------------------------
Nothing moves. The tweezers are probed with ``TRAP_DELETE`` against a sentinel
name -- the GUI answers -25 (no such element) and changes nothing, which is the
only liveness test a write-only protocol allows. Micro-Manager is measured with
``getProperty`` and the piezo with a measured-position read. So a read latency
is a *lower bound* on control latency: a write that moves a turret or a stage
also waits for the mechanism. Good enough for the question being asked, which is
whether the host can be in a timing loop at all.

ORDERING
--------
The tweezers GUI and Micro-Manager share a Kinetix and PVCAM is exclusive, so
``--tweezers`` and ``--micromanager`` together walk the enforced handoff in
hardware/orchestrator.py: tweezers first, camera released, then MM. Running the
two in ``--parallel`` is allowed only because both measurements here are
read-only and the tweezers probe needs no camera at all -- the Tweez GUI runs
cameraless (Tweez300UserManual p.34).
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from hardware.orchestrator import (  # noqa: E402
    MICROMANAGER,
    TWEEZERS,
    OrchestratorError,
    Phase,
    Session,
)

N_DEFAULT = 200


# ---- per-subsystem probes: each takes (session, n) and logs its own ops ----


def probe_tweezers(session: Session, n: int, host: str, port: int) -> None:
    from hardware.optical_tweezers import OpticalTweezers, TweezersError

    with session.instrument(TWEEZERS, "connect"):
        tweez = OpticalTweezers(host=host, port=port)
    try:
        with session.instrument(TWEEZERS, "wait_until_ready"):
            tweez.wait_until_ready(timeout=30.0)
        for _ in range(n):
            with session.instrument(TWEEZERS, "probe (TRAP_DELETE, no-op)"):
                status = tweez.probe()
            session.state.set("tweezers_last_status", status)
    except TweezersError as exc:
        print(f"   tweezers: {exc}", file=sys.stderr)
    finally:
        tweez.close()


def probe_micromanager(session: Session, n: int, cfg: Path, mm_dir: Path | None) -> None:
    from hardware.microscope import Microscope, MicroscopeError

    try:
        with session.instrument(MICROMANAGER, "connect (load config)"):
            scope = Microscope.connect(cfg, mm_dir=mm_dir)
    except MicroscopeError as exc:
        print(f"   micromanager: {exc}", file=sys.stderr)
        return
    try:
        with session.instrument(MICROMANAGER, "state() full read"):
            state = scope.state()
        session.state.set("objective", state.get("Nosepiece") or state.get("Objective"))
        device, prop = _pick_readable(scope)
        for _ in range(n):
            with session.instrument(MICROMANAGER, f"getProperty {device}.{prop}"):
                scope.core.getProperty(device, prop)
    finally:
        scope.close()


def _pick_readable(scope) -> tuple[str, str]:
    """A state device's Label if there is one -- the closest analogue to the
    properties a configuration change actually writes."""
    for device, kind in scope.devices().items():
        if kind == "StateDevice":
            return device, "Label"
    return "Core", "TimeoutMs"


def probe_piezo(session: Session, n: int, link: str, channel: int) -> None:
    from hardware.piezo_stage import PiezoStage, PiezoStageError

    try:
        with session.instrument("piezo", "load DLL"):
            stage = PiezoStage()
    except PiezoStageError as exc:
        print(f"   piezo: {exc}", file=sys.stderr)
        return
    try:
        with session.instrument("piezo", f"connect {link}"):
            stage.connect(link)
        for _ in range(n):
            with session.instrument("piezo", "position.measured.get"):
                pos = stage.get_position_um(channel)
            session.state.set("piezo_um", pos)
        stage.disconnect()
    except PiezoStageError as exc:
        print(f"   piezo: {exc}", file=sys.stderr)
    finally:
        stage.close()


def probe_stub(session: Session, n: int, subsystem: str, delay_s: float) -> None:
    """Stand-in with a known cost, so --dry-run exercises the machinery."""
    for _ in range(n):
        with session.instrument(subsystem, "stub op"):
            time.sleep(delay_s)
    session.state.set(f"{subsystem}_done", True)


# ---- driving ------------------------------------------------------------


def run(tasks: list[tuple[str, callable]], parallel: bool) -> None:
    if not parallel:
        for name, fn in tasks:
            print(f"   -> {name}")
            fn()
        return
    print(f"   -> {len(tasks)} subsystems in parallel: {', '.join(n for n, _ in tasks)}")
    threads = [threading.Thread(target=fn, name=name) for name, fn in tasks]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="stub drivers, no hardware")
    ap.add_argument("--tweezers", action="store_true")
    ap.add_argument("--micromanager", type=Path, metavar="CFG")
    ap.add_argument("--piezo", metavar="LINK", help='COM port, IP, or "sim:/NPC6330"')
    ap.add_argument("--parallel", action="store_true")
    ap.add_argument("-n", type=int, default=N_DEFAULT, help=f"ops each (default {N_DEFAULT})")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=2070)
    ap.add_argument("--mm-dir", type=Path, default=None)
    ap.add_argument("--piezo-channel", type=int, default=1)
    ap.add_argument("--camera", default="Kinetix_red")
    a = ap.parse_args()

    if not (a.dry_run or a.tweezers or a.micromanager or a.piezo):
        ap.error("choose at least one of --dry-run/--tweezers/--micromanager/--piezo")

    session = Session(camera=a.camera)
    print(f"clock anchored at wall {session.clock.anchor[0]:.3f}; "
          f"camera under arbitration: {session.camera.camera}")

    # Phase 1 -- whatever needs the camera in the tweezers GUI's hands. Nothing
    # measured here needs it, so this is the ordering being honoured, not used.
    print("\n-- phase 1: tweezers hold the camera ----------------------")
    tweezer_tasks: list[tuple[str, callable]] = []
    if a.dry_run:
        tweezer_tasks.append(
            (TWEEZERS, lambda: probe_stub(session, a.n, TWEEZERS, 0.0002))
        )
    if a.tweezers:
        tweezer_tasks.append(
            (TWEEZERS, lambda: probe_tweezers(session, a.n, a.host, a.port))
        )
    with session.tweezers_setup():
        run(tweezer_tasks, a.parallel)
    print(f"   camera released; phase now {session.phase.name}")

    # Phase 3 -- Micro-Manager may take the camera, and the piezo is unrelated
    # to it, so both can run here.
    print("\n-- phase 3: micro-manager may take the camera ------------")
    try:
        session.microscope_setup()
    except OrchestratorError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    later: list[tuple[str, callable]] = []
    if a.dry_run:
        later += [
            (MICROMANAGER, lambda: probe_stub(session, a.n, MICROMANAGER, 0.0001)),
            ("piezo", lambda: probe_stub(session, a.n, "piezo", 0.0003)),
        ]
    if a.micromanager:
        later.append(
            (MICROMANAGER, lambda: probe_micromanager(session, a.n, a.micromanager, a.mm_dir))
        )
    if a.piezo:
        later.append(
            ("piezo", lambda: probe_piezo(session, a.n, a.piezo, a.piezo_channel))
        )
    run(later, a.parallel)
    session.start_running()

    print("\n-- latency ------------------------------------------------")
    print(session.latency.report())
    print("\n   read-only measurements: a lower bound on control latency.")
    print("   For reference, setProperty on a NIDAQ line measured 0.0054 ms")
    print("   (config/micromanager/verify_lunf_daq.py).")

    print("\n-- shared state -------------------------------------------")
    for key, (stamp, value) in sorted(session.state.snapshot().items()):
        print(f"   {key:26} = {value!r}   (set at t={stamp:.4f}s, "
              f"age {session.state.age_s(key):.4f}s)")
    print(f"\n   phase {session.phase.name}, "
          f"{len(session.latency.ops)} ops on one timeline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
