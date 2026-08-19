"""Verify LUN-F XL fast blanking through Micro-Manager's NIDAQ adapter.

Wiring (read out of the NIS-Elements device DB, C:\\ProgramData\\Laboratory
Imaging\\Platform\\DeviceDatabase_6_00.dat -> dev_PhysicalDevice[LUN-F]
.sConfiguration, and confirmed against the NIS "LUN-F Configuration" dialog):

    Wave0=405  PowerResource0=FT4222_00294-BOA/AO_A_0  BlankingResource0=Dev1/port0/line2
    Wave1=488  PowerResource1=FT4222_00294-BOA/AO_A_1  BlankingResource1=Dev1/port0/line4
    Wave2=561  PowerResource2=FT4222_00294-BOA/AO_A_2  BlankingResource2=Dev1/port0/line6
    Wave3=640  PowerResource3=FT4222_00294-BOA/AO_A_3  BlankingResource3=Dev1/port0/line8
    m_bEnableTriggering=1  PFI_Terminal0=/Dev1/PFI0

Only the blanking half lives on the PCIe-6323. Per-line POWER is on the LUN-F's
own FT4222 DAC, which Micro-Manager cannot reach -- set the levels once in NIS
(or on the unit), close NIS, then drive blanking from here.

    --dry-run   load + inspect only. Does NOT initialize the port0 device, so
                no DAQ line changes state. Safe with the laser armed.
    --arm       initialize and exercise lines 2/4/6/8. THIS DRIVES THE LASER
                BLANKING LINES. Only run with every line power at 0%, or with
                the CSU-W1 shutter closed and a power meter on the objective.

Blanking polarity (active-high vs active-low) is NOT documented by Nikon and is
not assumed here -- --arm reports what it set so you can watch the meter.
"""

import argparse
import sys
import time

from pymmcore_plus import CMMCorePlus, find_micromanager

HUB = "NIDAQHub"
DO = "LUNF-Blanking"
PORT = "NIDAQDO-Dev1/port0"
FIRST_SLIDER = 2
N_SLIDERS = 7
# wavelength -> MM property on the DO device (absolute port0 line number)
LINES = {"405": "line2", "488": "line4", "561": "line6", "640": "line8"}


def build(core: CMMCorePlus, initialize: bool) -> None:
    core.loadDevice(HUB, "NIDAQ", HUB)
    core.setProperty(HUB, "Device", "Dev1")
    core.initializeDevice(HUB)
    print(f"  hub AOTriggerInputPort = {core.getProperty(HUB, 'AOTriggerInputPort')!r}"
          f"   (NIS uses /Dev1/PFI0 for both grabbers)")
    print(f"  hub MaxSequenceLength  = {core.getProperty(HUB, 'MaxSequenceLength')}")

    core.loadDevice(DO, "NIDAQ", PORT)
    core.setProperty(DO, "Line # of first slider", str(FIRST_SLIDER))
    core.setProperty(DO, "Nr of TTL Sliders", str(N_SLIDERS))
    if not initialize:
        print("  [dry-run] device loaded, NOT initialized -- no line changed state")
        return
    core.initializeDevice(DO)
    exposed = [p for p in core.getDevicePropertyNames(DO) if p.startswith("line")]
    print(f"  sliders exposed        = {exposed}")
    missing = [w for w, ln in LINES.items() if ln not in exposed]
    if missing:
        raise SystemExit(f"  FAIL: no slider for {missing} -- widen 'Nr of TTL Sliders'")


def exercise(core: CMMCorePlus, dwell: float) -> None:
    def all_low() -> None:
        for ln in LINES.values():
            core.setProperty(DO, ln, "0")

    all_low()
    print("\n  all four blanking lines LOW -- confirm the meter reads dark before continuing")
    time.sleep(dwell)
    for wl, ln in LINES.items():
        all_low()
        t = time.perf_counter_ns()
        core.setProperty(DO, ln, "1")
        dt = (time.perf_counter_ns() - t) / 1000.0
        print(f"    {wl} nm -> Dev1/port0/{ln} HIGH   (setProperty {dt:.1f} us)")
        time.sleep(dwell)
    all_low()
    print("  all lines returned LOW")


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--arm", action="store_true")
    ap.add_argument("--dwell", type=float, default=2.0, help="seconds per line (default 2)")
    a = ap.parse_args()

    core = CMMCorePlus()
    core.setDeviceAdapterSearchPaths([str(find_micromanager())])
    print(f"MM: {find_micromanager()}")
    try:
        build(core, initialize=a.arm)
        if a.arm:
            exercise(core, a.dwell)
    finally:
        core.unloadAllDevices()
    return 0


if __name__ == "__main__":
    sys.exit(main())
