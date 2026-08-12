"""Live Micro-Manager queries via pymmcore-plus.

For the two Phase-0 items that need a live device connection rather than a
one-off measurement: camera row time (``ReadoutTimeNs / ROI높이``) and which
physical camera EM1/EM2 each feed (docs/07-roadmap.md, kb/systems/current.md
"known_gaps"). Needs a working Micro-Manager 2.0 device-adapter install
(``mmcore install``, or the lab's own MM2 setup) -- meant to run on the
microscope PC, not the offline work PC this repo otherwise targets.

Verified against pymmcore-plus's own bundled demo camera (tests/
test_calibration_mm_live.py) -- NOT against the lab's real PVCAM/Kinetix
adapter, which is only reachable from the microscope PC. In particular,
``_READOUT_HINT`` matches the demo camera's ``ReadoutTime`` property; the
real adapter may expose it under a different name, unit, or not at all.
"""

from __future__ import annotations

from dataclasses import dataclass

from pymmcore_plus import CMMCorePlus, DeviceType


def _normalize(name: str) -> str:
    return name.lower().replace(" ", "").replace("_", "").replace("-", "")


# Not a confirmed PVCAM/Kinetix property name -- a substring guess to surface
# candidates for a human to confirm, per compute-never-infer. See module
# docstring.
_READOUT_HINT = _normalize("readout time")


@dataclass(frozen=True)
class PropertyCandidate:
    device: str
    name: str
    raw_value: str


def connect(cfg_path: str | None = None) -> CMMCorePlus:
    """Load a Micro-Manager ``.cfg`` file. ``None`` loads pymmcore-plus's
    bundled demo config -- useful for a smoke test, not a real measurement.
    """
    core = CMMCorePlus()
    if cfg_path is None:
        core.loadSystemConfiguration()
    else:
        core.loadSystemConfiguration(cfg_path)
    return core


def list_cameras(core: CMMCorePlus) -> list[str]:
    return list(core.getLoadedDevicesOfType(DeviceType.CameraDevice))


def roi_height(core: CMMCorePlus, camera: str) -> int:
    """Rows in ``camera``'s currently configured ROI.

    ``getROI(label)`` returns ``[x, y, width, height]``; row time is defined
    against height (the number of rows read out), not width.
    """
    return core.getROI(camera)[3]


def readout_time_candidates(core: CMMCorePlus, camera: str) -> list[PropertyCandidate]:
    """Device properties on ``camera`` whose name suggests a per-frame
    readout time. Ranked-by-nothing, resolved-by-nobody-but-you: some
    adapters expose several readout-related properties (e.g. a selectable
    readout *speed* alongside the resulting *time*), and only the adapter's
    own documentation can say which one feeds ``ReadoutTimeNs``.
    """
    return [
        PropertyCandidate(camera, name, core.getProperty(camera, name))
        for name in core.getDevicePropertyNames(camera)
        if _READOUT_HINT in _normalize(name)
    ]


def snap_mean_intensity(core: CMMCorePlus, camera: str) -> float:
    """Set ``camera`` as the active core camera, snap one frame, return its
    mean pixel value.

    Used to correlate an external filter-wheel change (e.g. toggling EM1 in
    NIS-Elements, which pymmcore-plus cannot see or control -- see
    kb/systems/current.md "known_gaps" (2a)) against which camera's signal
    actually moves.
    """
    core.setCameraDevice(camera)
    core.snapImage()
    return float(core.getImage().mean())
