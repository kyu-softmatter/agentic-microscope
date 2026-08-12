"""Tests for trapping.gate.evaluate -- mirrors tests/test_optics.py's split:
the Phase 0 refusals are right, and the Phase 1/2 aggregation is right.
"""

from __future__ import annotations

from trapping.dynamics import TrapSetup, water_viscosity_pa_s
from trapping.gate import evaluate
from trapping.goa import Bead, Medium, ObjectiveBeam
from trapping.laser import LaserCalibration

SILICA_BEAD = Bead(radius_m=2.5e-6, n=1.45)
BEAM = ObjectiveBeam(na=1.33, wavelength_m=1064e-9)
WATER_20C = Medium(n=1.33, viscosity_pa_s=water_viscosity_pa_s(20.0))

# 100% dial -> 30 mW, marked measured (matches tests/test_trapping.py's
# 30e-3 W fixture power).
MEASURED_CAL = LaserCalibration(points={100.0: 0.03})


def _setup(**overrides) -> TrapSetup:
    defaults = dict(
        bead=SILICA_BEAD,
        medium=WATER_20C,
        beam=BEAM,
        calibration=MEASURED_CAL,
        dial_percent=100.0,
        temperature_measured=True,
    )
    defaults.update(overrides)
    return TrapSetup(**defaults)


# ----------------------------------------------------------- Phase 0 -----


def test_blocked_when_bead_is_outside_the_ray_optics_regime():
    tiny = Bead(radius_m=20e-9, n=1.45)
    v = evaluate(_setup(bead=tiny))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.regime" for f in v.findings)


def test_blocked_when_viscosity_is_not_supplied():
    v = evaluate(_setup(medium=Medium(n=1.33)))  # no viscosity_pa_s
    assert v.status == "BLOCKED"
    assert any("medium.viscosity" in f.message for f in v.findings)


# ------------------------------------------------------- Phase 1/2, pass ---


def test_passes_with_measured_calibration_and_temperature():
    v = evaluate(_setup())
    assert v.status == "PASS"
    assert v.evidence == "measured"
    assert v.advances is True


def test_evidence_downgrades_to_assumed_with_placeholder_calibration():
    v = evaluate(_setup(calibration=LaserCalibration(placeholder_max_w=0.03), temperature_measured=True))
    assert v.status == "PASS"
    assert v.evidence == "assumed"
    assert v.advances is False


def test_evidence_downgrades_to_assumed_with_default_temperature():
    v = evaluate(_setup(temperature_measured=False))
    assert v.evidence == "assumed"
    assert any("temperature" in i for i in v.assumed_inputs)


def test_sampling_is_informational_without_a_detector_fps():
    """Lens 7 doesn't own frame rate -- its absence must not block or fail
    the verdict, only annotate it."""
    v = evaluate(_setup())
    assert v.status == "PASS"
    sampling_findings = [f for f in v.findings if f.code == "sampling.unconfirmed"]
    assert len(sampling_findings) == 1
    assert sampling_findings[0].severity == "info"


# ------------------------------------------------------- Phase 1/2, fail ---


def test_fails_on_a_shallow_trap():
    """1 uW on this bead gives U/kT ~ 0.2, far below the ~10 kT rule of
    thumb for stable confinement."""
    weak_cal = LaserCalibration(points={100.0: 1e-6})
    v = evaluate(_setup(calibration=weak_cal))
    assert v.status == "FAIL"
    assert v.bottleneck == "trap.shallow"


def test_fails_g14_sampling_when_detector_fps_is_too_low():
    """30 mW on this bead needs ~190 fps (see corner-frequency numbers in
    test_trapping_dynamics.py); 50 fps aliases the calibration."""
    v = evaluate(_setup(detector_fps=50.0))
    assert v.status == "FAIL"
    assert v.bottleneck == "sampling.aliased"


def test_passes_g14_sampling_when_detector_fps_is_high_enough():
    v = evaluate(_setup(detector_fps=300.0))
    assert v.status == "PASS"
    assert v.margins["sampling"] >= 1.0
