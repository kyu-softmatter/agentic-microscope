"""detection.recommend -- one measured frame -> mode and exposure.

The gate direction (settings -> verdict) is covered by test_detection_gate.py.
This file covers the inverse, and in particular the claim the whole module rests
on: that a frame taken in *one* mode yields photon rates valid for *every* mode.
"""

from __future__ import annotations

import math

import pytest

from detection.photometry import snr
from detection.recommend import (
    FrameMeasurement,
    compare_modes,
    electron_rates,
    exposure_ceiling_saturation,
    exposure_for_snr,
    validate,
)
from optics.components import find_detector

# The illustrative frame used throughout: Kinetix22 in Sensitivity, 50 ms,
# offset 100 / background 300 / peak 1500 ADU, spot over 9 pixels.
SENS_FRAME = dict(
    exposure_ms=50.0,
    mode="Sensitivity",
    peak_adu=1500.0,
    background_adu=300.0,
    offset_adu=100.0,
    n_pix_spot=9,
    despeckle_off=True,
)


@pytest.fixture
def kinetix22():
    det = find_detector("Kinetix22")
    assert det is not None, "data/detectors.yaml must carry the Kinetix22 entry"
    return det


# ------------------------------------------------------------- rates -----


def test_electron_rates_from_a_sensitivity_frame(kinetix22):
    """(peak - bg) * gain / t, with gain = full_well / 2**bits = 1000/4096."""
    signal, background = electron_rates(FrameMeasurement(**SENS_FRAME), kinetix22)
    assert signal == pytest.approx(5859.4, rel=1e-4)
    assert background == pytest.approx(976.6, rel=1e-4)


def test_rates_are_mode_independent(kinetix22):
    """The claim the module rests on.

    A mode changes conversion gain, bit depth, read noise and line time -- the
    digitisation. It does not change how many photoelectrons the pixel
    collects. So the *same* light, digitised in a different mode, must give the
    same e-/s. If this ever fails, one frame no longer serves every mode and
    the whole from-frame workflow collapses.
    """
    sens = kinetix22.modes["Sensitivity"]
    dr = kinetix22.modes["DynamicRange"]
    g_sens = sens.full_well_e / (2**sens.bit_depth)
    g_dr = dr.full_well_e / (2**dr.bit_depth)

    # Re-digitise the identical charge in DynamicRange, keeping the same offset.
    signal_e = (SENS_FRAME["peak_adu"] - SENS_FRAME["background_adu"]) * g_sens
    background_e = (SENS_FRAME["background_adu"] - SENS_FRAME["offset_adu"]) * g_sens
    bg_adu = SENS_FRAME["offset_adu"] + background_e / g_dr
    dr_frame = FrameMeasurement(
        exposure_ms=SENS_FRAME["exposure_ms"],
        mode="DynamicRange",
        peak_adu=bg_adu + signal_e / g_dr,
        background_adu=bg_adu,
        offset_adu=SENS_FRAME["offset_adu"],
        n_pix_spot=SENS_FRAME["n_pix_spot"],
        despeckle_off=True,
    )

    a = electron_rates(FrameMeasurement(**SENS_FRAME), kinetix22)
    b = electron_rates(dr_frame, kinetix22)
    assert a[0] == pytest.approx(b[0])
    assert a[1] == pytest.approx(b[1])


def test_derived_conversion_gain_tracks_the_datasheet(kinetix22):
    """``full_well / 2**bits`` vs the datasheet's stated conversion gain.

    Rev 2024-10-21 states 0.23 / 0.85 / 0.25 / 0.015 e-/count. Three modes agree
    inside the rounding of the vendor's own two-significant-figure numbers.
    **Speed does not**: 200/256 = 0.781 against a stated 0.85, an 8.8% gap. That
    gap lands directly in any ADU->e- conversion of a Speed-mode frame, which is
    a reason to take the calibration frame in Sensitivity or DynamicRange
    instead. Pinned here so a registry edit cannot widen it silently.
    """
    stated = {
        "DynamicRange": 0.23,
        "Speed": 0.85,
        "Sensitivity": 0.25,
        "SubElectron": 0.015,
    }
    gaps = {}
    for name, g_stated in stated.items():
        mode = kinetix22.modes[name]
        derived = mode.full_well_e / (2**mode.bit_depth)
        gaps[name] = abs(derived - g_stated) / g_stated

    assert gaps["DynamicRange"] < 0.01
    assert gaps["Sensitivity"] < 0.03
    assert gaps["SubElectron"] < 0.02
    assert 0.05 < gaps["Speed"] < 0.12   # known, documented, not silent


# --------------------------------------------------------- inversions -----


def test_exposure_for_snr_round_trips_through_photometry_snr():
    """The inversion must be the exact inverse of the gate's own SNR.

    If these two ever disagree, the recommender proposes exposures the gate
    then rejects -- which is worse than having no recommender.
    """
    S, B, D, n, sigma, target = 5859.4, 976.6, 3.0, 9, 1.2021, 5.0
    t = exposure_for_snr(S, B, D, n, sigma, target)
    achieved = snr(S * t, B * t, D * t, n, sigma)
    assert achieved == pytest.approx(target, rel=1e-9)


def test_read_noise_makes_short_exposures_disproportionately_expensive():
    """Required exposure is not simply proportional to 1/signal.

    The ``n_pix * sigma^2`` term is exposure-independent, so at short exposures
    it dominates -- which is why a low-read-noise mode can beat a faster one.
    Halving read noise must shorten the required exposure.
    """
    args = (5859.4, 976.6, 3.0, 9)
    quiet = exposure_for_snr(*args, 0.70, 5.0)
    loud = exposure_for_snr(*args, 2.01, 5.0)
    assert quiet < loud


def test_saturation_ceiling_counts_background(kinetix22):
    """The pixel does not know which electrons were interesting.

    ``checks.check_saturation`` omits background from its peak; this module does
    not, which makes it stricter and therefore safe. Dropping the background
    term must lengthen the ceiling.
    """
    mode = kinetix22.modes["Sensitivity"]
    with_bg = exposure_ceiling_saturation(
        5859.4, 976.6, 3.0, mode.full_well_e, mode.bit_depth, 100.0
    )
    without_bg = exposure_ceiling_saturation(
        5859.4, 0.0, 3.0, mode.full_well_e, mode.bit_depth, 100.0
    )
    assert without_bg > with_bg
    assert with_bg == pytest.approx(0.7 * 1000 / (5859.4 + 976.6 + 3.0), rel=1e-6)


# ---------------------------------------------------------- refusals -----


def test_clipped_peak_is_refused(kinetix22):
    """A clipped peak is a lower bound, not a measurement."""
    frame = FrameMeasurement(**{**SENS_FRAME, "peak_adu": 4000.0})
    codes = [r.code for r in validate(frame, kinetix22)]
    assert "peak_clipped" in codes


def test_despeckle_on_is_refused(kinetix22):
    """docs/06-pitfalls.md C1: linearity breaks, so ADU->e- is meaningless."""
    frame = FrameMeasurement(**{**SENS_FRAME, "despeckle_off": False})
    codes = [r.code for r in validate(frame, kinetix22)]
    assert "despeckle_on" in codes


def test_unknown_mode_is_refused_with_an_action(kinetix22):
    frame = FrameMeasurement(**{**SENS_FRAME, "mode": "Turbo"})
    refusals = validate(frame, kinetix22)
    assert [r.code for r in refusals] == ["unknown_mode"]
    assert refusals[0].action  # every refusal carries a fix, never a complaint


def test_a_good_frame_is_not_refused(kinetix22):
    assert validate(FrameMeasurement(**SENS_FRAME), kinetix22) == []


# ------------------------------------------------------ mode compare -----


def test_at_20_fps_read_noise_orders_the_modes(kinetix22):
    """Not full well -- which is the counter-intuitive part.

    With the spot over 9 pixels the ``n_pix * sigma^2`` term dominates, so the
    ranking follows read noise (0.70 < 1.20 < 1.60 < 2.01) even though full well
    spans 75x across the same four modes. Saturation only binds in Speed.
    """
    options = compare_modes(
        FrameMeasurement(**SENS_FRAME),
        kinetix22,
        target_snr=5.0,
        target_fps=20.0,
        task_kind="tracking",
        roi_height_px=256,
    )
    assert all(o.feasible for o in options)
    assert [o.mode for o in options] == [
        "SubElectron",
        "Sensitivity",
        "DynamicRange",
        "Speed",
    ]
    binding = {o.mode: o.binding_constraint for o in options}
    assert binding["Speed"] == "saturation (G6)"
    assert binding["Sensitivity"] == "motion blur (G8)"


def test_at_100_fps_motion_blur_kills_every_mode(kinetix22):
    """The interesting failure: the answer is not "pick another mode".

    G8's ceiling at 100 fps is 3.0 ms and no mode reaches SNR 5 that fast, so
    the fix is upstream -- more light, a brighter label, or a lower frame rate.
    A recommender that answered with a mode here would be lying.
    """
    options = compare_modes(
        FrameMeasurement(**SENS_FRAME),
        kinetix22,
        target_snr=5.0,
        target_fps=100.0,
        task_kind="tracking",
        roi_height_px=256,
    )
    assert not any(o.feasible for o in options)
    assert all(o.exposure_ms is None and o.max_fps is None for o in options)


def test_readout_alone_can_block_a_mode(kinetix22):
    """Sub-Electron's 60.1 us/line over 256 rows is 15.4 ms.

    Longer than a 100 fps frame period, and no exposure shortens readout --
    only the row count does (docs/06-pitfalls.md C3), which is an ROI decision,
    not a mode one. The note has to say so.
    """
    options = compare_modes(
        FrameMeasurement(**SENS_FRAME),
        kinetix22,
        target_snr=5.0,
        target_fps=100.0,
        task_kind="tracking",
        roi_height_px=256,
    )
    sub = next(o for o in options if o.mode == "SubElectron")
    assert any("readout alone" in n for n in sub.notes)


def test_motion_blur_ceiling_only_applies_to_tracking(kinetix22):
    """Morphology imaging has no MSD to bias (docs/04 §2's task dependence)."""
    kw = dict(target_snr=5.0, target_fps=100.0, roi_height_px=256)
    tracking = compare_modes(
        FrameMeasurement(**SENS_FRAME), kinetix22, task_kind="tracking", **kw
    )
    imaging = compare_modes(
        FrameMeasurement(**SENS_FRAME), kinetix22, task_kind="imaging", **kw
    )
    assert not any(o.feasible for o in tracking)
    assert any(o.feasible for o in imaging)


def test_chosen_exposure_is_the_minimum_that_meets_the_target(kinetix22):
    """Longer only adds dose (lens 5) and blur (G8), so it is never chosen."""
    options = compare_modes(
        FrameMeasurement(**SENS_FRAME),
        kinetix22,
        target_snr=5.0,
        target_fps=20.0,
        task_kind="tracking",
        roi_height_px=256,
    )
    for o in options:
        if o.feasible:
            assert o.exposure_ms == pytest.approx(o.exposure_for_snr_ms)
            assert o.snr_achieved == pytest.approx(5.0, rel=1e-6)


# ------------------------------------------------------ the QE flag ------


def test_kinetix22_qe_curve_is_borrowed_and_says_so():
    """The Kinetix22 QE curve is the Kinetix's, by one-time authorization.

    ``qe_verified: false`` must therefore reach ``Spectrum.measured``, so the
    gate lists it in ``assumed_inputs`` and the channel cannot advance on it.
    Before Detector.from_spec read that key, an inline eyeballed curve arrived
    as measured=True and silently bought evidence it had not earned.
    """
    det = find_detector("Kinetix22")
    assert det is not None
    assert det.qe.measured is False
    # ...and it is a curve, not the flat qe_peak fallback: QE must fall in the red.
    assert det.qe.at(650.0) < det.qe.at(550.0)


def test_eyeballed_kinetix_and_prime95b_curves_are_unmeasured_too():
    """Both carry `qe_verified: false` and were read off graphs by eye."""
    for name in ("Kinetix", "Prime95B"):
        det = find_detector(name)
        assert det is not None, name
        assert det.qe.measured is False, name


def test_localization_precision_is_reported_for_the_chosen_exposure(kinetix22):
    from detection.recommend import localization_precision_nm

    options = compare_modes(
        FrameMeasurement(**SENS_FRAME),
        kinetix22,
        target_snr=5.0,
        target_fps=20.0,
        task_kind="tracking",
        roi_height_px=256,
    )
    signal, background = electron_rates(FrameMeasurement(**SENS_FRAME), kinetix22)
    winner = next(o for o in options if o.feasible)
    sigma = localization_precision_nm(winner, signal, background, 97.0, 65.0)
    assert sigma is not None and math.isfinite(sigma) and sigma > 0
