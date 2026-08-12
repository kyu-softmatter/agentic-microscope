"""Phase-0 hardware calibration measurements (docs/07-roadmap.md).

Scripts to run once this repo is reconnected to the microscope PC -- the
work PC this repo otherwise targets never touches real hardware (see
README "The working PC and the microscope PC are separate").
Deliberately excludes
illumination power (``power_at_sample_mw``): that one needs a power meter at
the sample plane, not code, and is being measured separately.

    from calibration import measure_write_bandwidth   # no extra deps

``calibration.mm_live`` (camera readout time, EM1/EM2 camera probing) needs
pymmcore-plus and a working Micro-Manager device-adapter install
(``mmcore install``, or the lab's own MM2 setup) -- it is imported lazily by
``calibration.cli`` so importing this package doesn't require either.
"""

from .disk_bandwidth import DiskBandwidthResult, measure_write_bandwidth

__all__ = [
    "DiskBandwidthResult",
    "measure_write_bandwidth",
]
