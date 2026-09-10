"""Tests for trapping.gate.evaluate -- mirrors tests/test_optics.py's split:
the Phase 0 refusals are right, and the Phase 1/2 aggregation is right.
"""

from __future__ import annotations

import pytest

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


# ------------------------------------ TIR-clipped NA is reported, not vetoed ---
#
# 2026-08-18: an oil objective on an aqueous sample used to BLOCK this lens.
# It now computes -- but the cost has to be visible, and it must not advance
# on an upper bound.

OIL_BEAM = ObjectiveBeam(na=1.45, wavelength_m=1064e-9)  # 100x-Oil
WATER_OBJ_BEAM = ObjectiveBeam(na=1.25, wavelength_m=1064e-9)  # 40x-WI


def test_oil_objective_is_no_longer_blocked():
    v = evaluate(_setup(beam=OIL_BEAM, detector_fps=300.0))
    assert v.status == "PASS"
    assert not any(f.code.startswith("missing.") for f in v.findings)


def test_clipped_na_is_reported_as_a_finding_with_its_limits():
    v = evaluate(_setup(beam=OIL_BEAM, detector_fps=300.0))
    finding = next(f for f in v.findings if f.code == "effective_na.clipped_by_tir")
    assert finding.severity == "info"
    assert finding.numbers["design_na"] == 1.45
    assert finding.numbers["effective_na"] == WATER_20C.n
    # the three limits the user has to carry away
    assert "UPPER BOUND" in finding.message
    assert "spherical aberration" in finding.message
    assert "Faxen" in finding.message


def test_clipped_na_does_not_change_the_feasibility_grade():
    """The new check is INFO, so it must not veto or re-grade -- an oil
    objective's trap is as feasible as the water objective's."""
    oil = evaluate(_setup(beam=OIL_BEAM, detector_fps=300.0))
    water = evaluate(_setup(beam=WATER_OBJ_BEAM, detector_fps=300.0))
    assert oil.feasibility == water.feasibility
    assert oil.status == water.status == "PASS"


def test_clipped_na_blocks_advances_on_unmodelled_aberration():
    """Everything else measured, so the only thing standing between this
    verdict and `advances` is the aberration nobody has bounded."""
    oil = evaluate(_setup(beam=OIL_BEAM, detector_fps=300.0))
    assert oil.advances is False
    assert oil.evidence == "assumed"
    assert any("spherical aberration" in a for a in oil.assumed_inputs)


def test_index_matched_objective_still_advances():
    """The differential the change is for: same experiment, matched objective,
    nothing assumed -- this one is allowed through."""
    water = evaluate(_setup(beam=WATER_OBJ_BEAM, detector_fps=300.0))
    assert water.assumed_inputs == []
    assert water.evidence == "measured"
    assert water.advances is True


# ------------------------------------------- the power proposal (2026-09-10)


def test_a_passing_check_still_reports_its_number():
    """`_ok` set severity "ok", which trapping/gate.py drops from findings --
    so on a configuration where everything passed, the only visible finding
    was the TIR notice. The numbers ARE this lens: stiffness, trap depth in
    kT, corner frequency. Same correction as sample/ G16c and photo/ today.
    """
    v = evaluate(_setup(detector_fps=520.0))
    codes = {f.code for f in v.findings}
    assert {"trap.confinement", "trap.depth", "sampling"} <= codes
    for c in ("trap.confinement", "trap.depth", "sampling"):
        assert next(f for f in v.findings if f.code == c).severity == "info"


def test_the_power_window_is_free_of_the_uncalibrated_dial_scale():
    """THE property that makes proposing a power defensible.

    The dial% -> mW map is a placeholder and the laser's power is neither
    readable nor settable, so any mW figure is fiction. Both ends of the
    STIFFNESS window escape it: the ceiling is 2*pi*gamma*f_s/10 (gamma and
    the frame rate only), and the floor is 10*kT/(U/kappa), where U/kappa is
    constant because the GOA stiffness and trap depth are both linear in
    power. Rescaling the placeholder by 100x must move neither.
    """
    from trapping.dynamics import LaserCalibration

    a = evaluate(_setup(detector_fps=520.0, calibration=LaserCalibration(placeholder_max_w=1.0)))
    b = evaluate(_setup(detector_fps=520.0, calibration=LaserCalibration(placeholder_max_w=100.0)))
    ma = a.metrics["trap.power_window"]
    mb = b.metrics["trap.power_window"]

    assert ma["kappa_min_pn_per_um"] == pytest.approx(mb["kappa_min_pn_per_um"], rel=1e-9)
    assert ma["kappa_max_pn_per_um"] == pytest.approx(mb["kappa_max_pn_per_um"], rel=1e-9)
    # And the stiffness the dial computes to DOES move -- that is the fiction.
    assert mb["kappa_at_this_dial_pn_per_um"] > ma["kappa_at_this_dial_pn_per_um"]


def test_the_ceiling_is_g14_inverted():
    """kappa_max = 2*pi*gamma*f_s/10, i.e. exactly the stiffness whose corner
    frequency is a tenth of the frame rate."""
    import math

    v = evaluate(_setup(detector_fps=520.0))
    m = v.metrics["trap.power_window"]
    gamma = m["gamma_pn_s_per_um"]
    # rel 1e-4, not tighter: both figures in `numbers` are rounded for
    # display, so recomputing from the rounded gamma cannot match to 1e-6.
    assert m["kappa_max_pn_per_um"] == pytest.approx(2 * math.pi * gamma * 52.0, rel=1e-4)
    assert m["corner_frequency_max_hz"] == pytest.approx(52.0)


def test_the_measured_stiffness_sits_inside_the_window():
    """The only way to use this lens quantitatively today: it cannot be TOLD a
    measured stiffness, but the window can be compared against one. 2026-09-03
    measured 3.65-4.5 pN/um three independent ways.
    """
    v = evaluate(_setup(detector_fps=520.0))
    m = v.metrics["trap.power_window"]
    for measured in (3.65, 3.87, 4.5):
        assert m["kappa_min_pn_per_um"] <= measured <= m["kappa_max_pn_per_um"]


def test_no_ceiling_without_a_frame_rate_from_lens_2():
    """G14 sets the ceiling, and G14 needs an achieved frame rate this lens
    does not own."""
    v = evaluate(_setup())
    m = v.metrics["trap.power_window"]
    assert "kappa_max_pn_per_um" not in m
    f = next(f for f in v.findings if f.code == "trap.power_window")
    assert "No ceiling" in f.message


def test_a_slow_camera_can_empty_the_window():
    """At a low enough frame rate G14's ceiling drops below the trap-depth
    floor and no stiffness works -- the same shape as lens 4's empty depth
    window, and a case no single margin can express."""
    v = evaluate(_setup(detector_fps=1e-4))
    assert any(f.code == "trap.power_window.empty" for f in v.findings)


# ------------------------------- the measured 1064 curve (2026-09-10) -------


def test_the_measured_1064_curve_is_the_default_and_is_measured():
    """kb/calibrations/illumination-power.yaml's `optical_tweezers` row, KH
    2026-09-09. That file says outright "SAFETY.md §1 said this dial was
    uncalibrated; it is not any more" -- and this lens went on using the
    placeholder until 2026-09-10.
    """
    from trapping.laser import MEASURED_1064_20X_W, LaserCalibration

    cal = LaserCalibration(points=MEASURED_1064_20X_W)
    assert cal.measured is True
    assert cal.power_at(50.0) == pytest.approx(0.633)
    assert cal.power_at(5.0) == pytest.approx(0.064)


def test_it_refuses_to_extrapolate_past_the_meter():
    """100 % over-ranged the meter, so 80 % is the top row and the file's
    1275 mW at 100 % is `assumed`. It is deliberately not in the points, and
    `power_at` refuses rather than guessing."""
    from trapping.laser import MEASURED_1064_20X_W, LaserCalibration

    cal = LaserCalibration(points=MEASURED_1064_20X_W)
    assert cal.power_at(80.0) == pytest.approx(1.020)
    with pytest.raises(ValueError, match="exceeds the highest calibrated"):
        cal.power_at(100.0)


def test_the_placeholder_was_off_by_1_27_not_by_40():
    """THE CORRECTION this measurement forced.

    The gap between the model's stiffness and the measured 3.65-4.5 pN/um was
    read as a fault in the dial -> mW map. It is not: the placeholder
    (dial% x 10 mW) undershoots the measured curve by a flat 1.27x at every
    level. So the discrepancy was never in the power scale, and where it
    actually sits is settled by one number nobody recorded -- the dial the
    2026-09-03 session ran at.
    """
    from trapping.laser import MEASURED_1064_20X_W, LaserCalibration

    measured = LaserCalibration(points=MEASURED_1064_20X_W)
    placeholder = LaserCalibration(placeholder_max_w=1.0)
    for dial in (5.0, 10.0, 30.0, 50.0, 80.0):
        ratio = measured.power_at(dial) / placeholder.power_at(dial)
        assert ratio == pytest.approx(1.27, abs=0.02)


def test_the_model_reproduces_the_measured_stiffness_near_dial_one_percent():
    """And so the ray-optics model is not 40x optimistic -- it agrees.

    On the measured curve, dial 0.879 % (11.3 mW) gives exactly the 3.87 pN/um
    that 2026-09-03 measured three independent ways, and dial 1 % gives
    4.40 pN/um -- 14 % high, which for a model whose own docstring calls it an
    upper bound (unmodelled Fresnel roll-off at the critical angle, no
    spherical aberration) is agreement rather than failure.

    What this does NOT establish is the dial that session used. If it was ~1 %
    the model is validated to 14 %; if it was 50 % the model is ~53x
    optimistic. That one unrecorded number decides it.
    """
    import math

    from trapping.dynamics import Bead, Medium, ObjectiveBeam
    from trapping.goa import radial_stiffness_n_per_m
    from trapping.laser import MEASURED_1064_20X_W, LaserCalibration

    cal = LaserCalibration(points=MEASURED_1064_20X_W)
    bead = Bead(radius_m=2.475e-6, n=1.57154)
    med = Medium(n=1.33, viscosity_pa_s=1.002e-3)
    beam = ObjectiveBeam(na=1.45)

    kappa_1pct = radial_stiffness_n_per_m(cal.power_at(1.0), bead, med, beam) * 1e6
    assert kappa_1pct == pytest.approx(4.40, abs=0.05)
    assert 0.9 < kappa_1pct / 3.87 < 1.2


def test_the_objective_is_the_remaining_assumption_not_the_dial():
    """The dial -> mW map is measured now, so it left assumed_inputs. What
    replaced it is narrower and true: that curve was taken at the 20x, and
    every other objective's 1064 figure in that file is an estimate off a
    vendor plot. The text cites the file."""
    from trapping.laser import MEASURED_1064_20X_W, LaserCalibration

    v = evaluate(
        _setup(
            calibration=LaserCalibration(points=MEASURED_1064_20X_W),
            # 50, not the fixture's 100: the measured curve tops out at 80 %
            # and refuses to extrapolate, which is the behaviour wanted.
            dial_percent=50.0,
            temperature_measured=True,
            detector_fps=520.0,
        )
    )
    assert not any("dial% -> mW calibration" in a for a in v.assumed_inputs)
    assert any("illumination-power.yaml" in a for a in v.assumed_inputs)


# --------------------- the objective correction table (2026-09-10) ---------


def test_the_table_computes_where_filled_and_refuses_where_empty():
    """kb/calibrations/objective-transmittance.yaml. A filled cell computes
    whatever its tier -- "our purpose is rough estimation, so some error is
    fine" (KH) -- and an empty one raises, because there is no number to be
    roughly right with.
    """
    from trapping.laser import objective_ratio_to_20x

    assert objective_ratio_to_20x("20x").ratio == 1.0
    assert objective_ratio_to_20x("20x").tier == "reference"
    assert objective_ratio_to_20x("100x-Oil").ratio == pytest.approx(0.95)
    assert objective_ratio_to_20x("40x-WI").ratio == pytest.approx(0.74)
    assert objective_ratio_to_20x("100x-Oil", "488").tier == "read-from-plot"

    # 10x at 1064: no curve exists and the direct readings were retracted.
    with pytest.raises(KeyError, match="no power ratio"):
        objective_ratio_to_20x("10x")


def test_only_a_measured_tier_may_advance():
    """The tiers are not decoration: `reference`/`measured` are the two that
    CLAUDE.md §3 lets a verdict advance on."""
    from trapping.laser import objective_ratio_to_20x

    assert objective_ratio_to_20x("20x").measured is True
    assert objective_ratio_to_20x("100x-Oil").measured is False
    assert objective_ratio_to_20x("100x-Oil", "488").measured is False


def test_the_measured_visible_ratios_stay_per_source():
    """They disagree by up to 0.21 at the same objective and wavelength -- the
    Spectra runs 1.14-1.24 at the 4x against 1.01-1.07 for the other two. A
    property of the glass alone could not do that, so collapsing them would
    attribute a source's fill factor to the lens."""
    from trapping.laser import measured_source_ratio_to_20x

    spectra = measured_source_ratio_to_20x("4x", "640", "Spectra").ratio
    aura = measured_source_ratio_to_20x("4x", "640", "Aura").ratio
    assert spectra == pytest.approx(1.242)
    assert aura == pytest.approx(1.038)
    assert spectra - aura > 0.15


def test_the_objective_correction_actually_moves_the_power():
    """Otherwise the table would be a document nothing consumes. 633 mW at the
    20x becomes 601 mW through the 100x Oil."""
    from trapping.laser import MEASURED_1064_20X_W, LaserCalibration

    common = dict(
        calibration=LaserCalibration(points=MEASURED_1064_20X_W),
        dial_percent=50.0,
        temperature_measured=True,
    )
    at_20x = _setup(**common)
    at_100x = _setup(objective_key="100x-Oil", **common)
    assert at_20x.weakest_power_w() == pytest.approx(0.633)
    assert at_100x.weakest_power_w() == pytest.approx(0.633 * 0.95)


def test_an_unset_objective_says_the_power_is_the_20x_s():
    """Silence must not read as "this is the right objective"."""
    from trapping.laser import MEASURED_1064_20X_W, LaserCalibration

    v = evaluate(
        _setup(
            calibration=LaserCalibration(points=MEASURED_1064_20X_W),
            dial_percent=50.0,
            temperature_measured=True,
            detector_fps=520.0,
        )
    )
    assert any("the power used is the 20x's" in a for a in v.assumed_inputs)
