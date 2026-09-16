"""Tests for the optical lens.

These check two different things and the distinction matters:

* the **physics** is right (collection efficiency, band shapes, integrals)
* the **refusals** are right — the gate must decline to bless a configuration
  it cannot actually verify, which is the property that keeps it honest
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from optics import Channel, Objective, Spectrum, build_channel, evaluate
from optics.build import build_channels
from optics.components import Detector, Element, find_filter
from optics.path import ablate
from optics.spectra import GRID


# ---------------------------------------------------------------- spectra --


def test_grid_covers_nir_trapping_wavelength():
    """1064 nm trap leakage into the detection path has to be checkable."""
    assert GRID[0] <= 300 and GRID[-1] >= 1064


def test_constant_integrates_to_span():
    s = Spectrum.constant(1.0)
    assert s.integrate() == pytest.approx(GRID[-1] - GRID[0], rel=1e-6)


def test_band_is_centred_and_has_right_width():
    s = Spectrum.band(640, 30, peak=1.0, blocking_od=6)
    assert s.peak_nm() == pytest.approx(640, abs=1.0)
    lo, hi = s.support(0.5)
    assert (lo + hi) / 2 == pytest.approx(640, abs=1.0)
    assert (hi - lo) == pytest.approx(30, rel=0.1)


def test_band_blocks_out_of_band():
    s = Spectrum.band(640, 30, blocking_od=6)
    assert s.at(500) < 1e-5
    assert s.at(640) > 0.9


def test_edge_filter_direction():
    lp = Spectrum.edge(650, kind="long")
    sp = Spectrum.edge(650, kind="short")
    assert lp.at(700) > 0.9 and lp.at(600) < 1e-4
    assert sp.at(600) > 0.9 and sp.at(700) < 1e-4


def test_fluorophore_band_is_asymmetric_in_wavelength():
    """Emission modelled in wavenumber space must carry a red tail."""
    em = Spectrum.fluorophore_band(669, 45, side="emission")
    peak = em.peak_nm()
    red = em.at(peak + 40)
    blue = em.at(peak - 40)
    assert red > blue, "emission band should have the longer tail to the red"


def test_area_normalized_is_unit_area():
    s = Spectrum.fluorophore_band(519, 45, side="emission").area_normalized()
    assert s.integrate() == pytest.approx(1.0, rel=1e-6)


def test_parametric_spectra_are_flagged_unmeasured():
    assert Spectrum.band(500, 20).measured is False
    assert Spectrum.fluorophore_band(500, 40).measured is False
    assert Spectrum.from_curve([400, 500], [0.1, 0.9]).measured is True


# ------------------------------------------------------------- objective --


@pytest.mark.parametrize(
    "na,immersion,expected",
    [
        # (1 - cos(asin(NA/n)))/2, worked out by hand
        (1.45, "oil", 0.35203),    # asin(1.45/1.518) = 72.80 deg
        (1.20, "water", 0.28229),  # asin(1.20/1.333) = 64.16 deg
        (0.30, "air", 0.02303),    # asin(0.30)       = 17.46 deg
    ],
)
def test_collection_efficiency(na, immersion, expected):
    obj = Objective("test", 100, na, immersion)
    assert obj.collection_efficiency() == pytest.approx(expected, abs=1e-4)


def test_collection_efficiency_matches_closed_form():
    obj = Objective("o", 60, 1.20, "water")
    theta = math.asin(1.20 / 1.333)
    assert obj.collection_efficiency() == pytest.approx((1 - math.cos(theta)) / 2)


def test_resolution_scales_inversely_with_na():
    lo = Objective("lo", 100, 0.75, "air").resolution_nm(519)
    hi = Objective("hi", 100, 1.45, "oil").resolution_nm(519)
    assert hi < lo
    assert hi == pytest.approx(0.61 * 519 / 1.45)


def test_psf_sigma_matches_docs_worked_example():
    """docs/04 §2: 100x/NA1.45, lambda_em=668nm -> sigma_PSF=97nm."""
    obj = Objective("100x", 100, 1.45, "oil")
    assert obj.psf_sigma_nm(668.0) == pytest.approx(97.0, abs=1.0)
    assert obj.psf_sigma_nm(519) == pytest.approx(0.21 * 519 / 1.45)


# ---------------------------------------------------------- detector modes --


def test_detector_from_spec_parses_kinetix_modes():
    """data/detectors.yaml's Kinetix modes/frame_rate_by_roi_fps blocks
    exist but were silently ignored before -- detection (lens 2) needs
    them for L2.3 (quantization noise) and L2.5 (row time)."""
    from optics.components import detectors

    kinetix = detectors()["kinetix"]
    assert set(kinetix.modes) == {"Speed", "Sensitivity", "DynamicRange"}
    speed = kinetix.modes["Speed"]
    assert speed.bit_depth == 8
    assert speed.read_noise_e == pytest.approx(2.0)
    assert speed.line_time_us == pytest.approx(0.625)
    assert kinetix.frame_rate_by_roi_fps["3200x1600"]["pcie"] == 1000


def test_detector_from_spec_parses_prime95b_full_well_per_mode():
    from optics.components import detectors

    prime = detectors()["prime95b"]
    fullwell_mode = prime.modes["FullWell-12bit"]
    assert fullwell_mode.bit_depth == 12
    assert fullwell_mode.full_well_e == pytest.approx(62000)
    hdr_mode = prime.modes["HDR-16bit"]
    assert hdr_mode.full_well_e == pytest.approx(80000)


# ------------------------------------------------------- refusal behaviour --


def _detector() -> Detector:
    qe = Spectrum.constant(0.9, "qe")
    return Detector("cam", qe, pixel_um=11.0, read_noise_e=1.3, full_well_e=80000)


def test_unknown_filter_blocks_the_verdict():
    """An element with no passband on record must not yield a PASS."""
    ch = build_channel(
        {
            "name": "x",
            "dye": "ATTO647N",
            "objective": {"label": "o", "magnification": 100, "na": 1.45,
                          "immersion": "oil", "verified_na": True},
            "detector": "Prime95B",
            "source": ["Spectra", "Red"],
            "dichroic": "DA/FI/TR10Empty",   # kind: unknown in the registry
            "emission": ["FF01-692/40"],
        }
    )
    v = evaluate(ch)
    assert v.status == "BLOCKED"
    assert v.advances is False


def test_missing_na_blocks():
    ch = build_channel(
        {
            "name": "x",
            "dye": "ATTO647N",
            "objective": {"label": "o", "magnification": 100},  # no NA
            "detector": "Prime95B",
            "source": ["Spectra", "Red"],
            "emission": ["FF01-692/40"],
        }
    )
    v = evaluate(ch)
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.na" for f in v.findings)


def test_unknown_detector_blocks():
    ch = build_channel(
        {
            "name": "x",
            "dye": "ATTO647N",
            "objective": {"label": "o", "magnification": 100, "na": 1.45,
                          "immersion": "oil", "verified_na": True},
            "detector": "SomeCameraWeNeverAdded",
            "source": ["Spectra", "Red"],
            "emission": ["FF01-692/40"],
        }
    )
    v = evaluate(ch)
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.detector" for f in v.findings)


def test_assumed_inputs_never_advance():
    """The core honesty property: catalogue values give triage, not approval."""
    ch = build_channel(
        {
            "name": "647",
            "dye": "ATTO647N",
            "objective": {"label": "o", "magnification": 100, "na": 1.45,
                          "immersion": "oil", "verified_na": True},
            "detector": "Prime95B",
            "source": ["Spectra", "Red"],
            "excitation": ["FF01-640/14"],
            "dichroic": "FF650-Di01",
            "emission": ["FF01-692/40"],
        }
    )
    v = evaluate(ch)
    assert v.passed, "physics should be fine for a sane 647 path"
    assert v.evidence == "assumed"
    assert v.advances is False
    assert v.assumed_inputs


# ------------------------------------------------------------- physics ----


def test_mismatched_line_gives_no_excitation():
    """A 470 nm line cannot excite a 644 nm dye; that must be a hard FAIL."""
    ch = build_channel(
        {
            "name": "bad",
            "dye": "ATTO647N",
            "objective": {"label": "o", "magnification": 100, "na": 1.45,
                          "immersion": "oil", "verified_na": True},
            "detector": "Prime95B",
            "source": ["Spectra", "Cyan"],
            "emission": ["FF01-692/40"],
        }
    )
    v = evaluate(ch)
    assert v.status == "FAIL"
    assert any(f.code == "excitation.none" for f in v.findings)


def test_missing_emission_filter_fails_blocking():
    """With nothing but a source in the path, backscatter reaches the camera."""
    ch = Channel(
        name="naked",
        dye=build_channel(
            {"name": "d", "dye": "ATTO647N", "detector": "Prime95B",
             "objective": {"label": "o", "magnification": 100, "na": 1.45,
                           "immersion": "oil", "verified_na": True},
             "source": ["Spectra", "Red"]}
        ).dye,
        objective=Objective("o", 100, 1.45, "oil", verified_na=True),
        detector=_detector(),
        source=build_channel(
            {"name": "d", "dye": "ATTO647N", "detector": "Prime95B",
             "objective": {"label": "o", "magnification": 100, "na": 1.45,
                           "immersion": "oil", "verified_na": True},
             "source": ["Spectra", "Red"]}
        ).source,
        emission=[],
    )
    assert ch.excitation_blocking_od() < 1.0


def test_blocking_bar_is_five_od_in_both_evidence_tiers():
    """L1.2's threshold does not move with the evidence tier (KH, 2026-09-09).

    It used to rise 5 OD -> 7 OD for parametric spectra. Nothing pinned that,
    which is why removing it broke no test -- so the replacement behaviour is
    pinned here instead. The approximation is charged once, on the evidence
    axis (``advances`` needs ``evidence == "measured"``), not twice.
    kb/decisions/2026-09-09-blocking-threshold-fixed-at-5-od.md
    """
    from optics.checks import LIMITS, check_blocking

    assert "blocking_od_assumed" not in LIMITS, (
        "the parametric-spectra blocking penalty was removed on 2026-09-09; "
        "restoring it is a decision, not a tweak"
    )

    ch = build_channel(
        {
            "name": "647",
            "dye": "ATTO647N",
            "objective": {"label": "o", "magnification": 100, "na": 1.45,
                          "immersion": "oil", "verified_na": True},
            "detector": "Prime95B",
            "source": ["Spectra", "Red"],
            "emission": ["EM1-705/72"],
        }
    )
    r = check_blocking(ch, [])
    assert r.numbers["required_od"] == LIMITS["blocking_od"] == 5.0


def test_ablation_blocking_floor_does_not_move_with_the_evidence_tier():
    """`ablate()` carried the same +2 OD penalty L1.2 did, and lost it the same
    day (KH, 2026-09-09). Neither had a test, which is why both changes broke
    nothing -- so the floor is pinned by construction here.

    What still makes the removal analysis timid on approximate curves is the
    `candidate` downgrade, which `test_approximate_spectra_downgrade_removals`
    covers; this test only asserts the floor stopped moving.
    """
    import inspect

    from optics.path import ablate

    src = inspect.getsource(ablate)
    assert "blocking_floor = min_blocking_od\n" in src, (
        "ablate()'s blocking floor must be min_blocking_od flat -- the "
        "spectra_measured +2.0 penalty was removed 2026-09-09"
    )
    assert "spectra_measured else 2.0" not in src


def test_blocking_still_reports_that_the_spectra_were_approximated():
    """Fixing the threshold must not hide the approximation.

    The evidence axis is where it is now carried, so ``assumed`` has to keep
    coming out of the check even though it no longer changes ``required_od``.
    """
    from optics.checks import check_blocking

    ch = build_channel(
        {
            "name": "647",
            "dye": "ATTO647N",
            "objective": {"label": "o", "magnification": 100, "na": 1.45,
                          "immersion": "oil", "verified_na": True},
            "detector": "Prime95B",
            "source": ["Spectra", "Red"],
            "emission": ["EM1-705/72"],
        }
    )
    r = check_blocking(ch, [])
    if r.severity == "ok":
        assert "required_od" in r.numbers
    else:
        assert r.numbers["assumed"] is True


def test_sole_emission_filter_is_never_suggested_for_removal():
    """Leaving only a dichroic in the detection path is not an option."""
    ch = build_channel(
        {
            "name": "647",
            "dye": "ATTO647N",
            "objective": {"label": "o", "magnification": 100, "na": 1.45,
                          "immersion": "oil", "verified_na": True},
            "detector": "Prime95B",
            "source": ["Spectra", "Red"],
            "dichroic": "FF650-Di01",
            "emission": ["FF01-692/40"],
        }
    )
    results = {a.element: a for a in ablate(ch, spectra_measured=True)}
    assert results["FF01-692/40"].verdict == "required"


def test_pure_loss_element_is_flagged():
    """A polarizer in a non-polarization path costs ~58% and buys nothing."""
    base = {
        "name": "488",
        "dye": "AlexaFluor488",
        "objective": {"label": "o", "magnification": 100, "na": 1.45,
                      "immersion": "oil", "verified_na": True},
        "detector": "Prime95B",
        "source": ["Spectra", "Cyan"],
        "dichroic": "Di03-R405/488/561/635",
        "emission": ["FF01-525/45"],
    }
    without = build_channel({**base, "excitation": ["FF01-475/35"]})
    with_pol = build_channel(
        {**base, "excitation": ["FF01-475/35", "Polarizer-Linear"]}
    )
    assert with_pol.relative_signal() < without.relative_signal()

    entry = {a.element: a for a in ablate(with_pol, spectra_measured=True)}
    assert entry["Polarizer-Linear"].verdict == "remove"
    assert entry["Polarizer-Linear"].signal_gain > 1.5


def test_ablation_is_timid_when_spectra_are_approximated():
    ch = build_channel(
        {
            "name": "488",
            "dye": "AlexaFluor488",
            "objective": {"label": "o", "magnification": 100, "na": 1.45,
                          "immersion": "oil", "verified_na": True},
            "detector": "Prime95B",
            "source": ["Spectra", "Cyan"],
            "excitation": ["FF01-475/35", "Polarizer-Linear"],
            "dichroic": "Di03-R405/488/561/635",
            "emission": ["FF01-525/45"],
        }
    )
    entry = {a.element: a for a in ablate(ch, spectra_measured=False)}
    assert entry["Polarizer-Linear"].verdict == "candidate"


def test_crosstalk_detected_between_overlapping_channels():
    """Two dyes sharing a detection band must trip the crosstalk check."""
    shared = {
        "objective": {"label": "o", "magnification": 100, "na": 1.45,
                      "immersion": "oil", "verified_na": True},
        "detector": "Prime95B",
        "dichroic": "FF650-Di01",
        "emission": ["FF01-692/40"],
        "source": ["Spectra", "Red"],
    }
    a = build_channel({**shared, "name": "a", "dye": "ATTO647N"})
    b = build_channel({**shared, "name": "b", "dye": "AlexaFluor647"})
    assert a.crosstalk_from(b) > 0.5, "near-identical dyes must show crosstalk"

    v = evaluate(a, [b])
    assert any(f.code == "crosstalk" for f in v.findings)


def test_well_separated_channels_have_low_crosstalk():
    green = build_channel(
        {
            "name": "488", "dye": "AlexaFluor488",
            "objective": {"label": "o", "magnification": 100, "na": 1.45,
                          "immersion": "oil", "verified_na": True},
            "detector": "Prime95B", "source": ["Spectra", "Cyan"],
            "dichroic": "Di03-R405/488/561/635", "emission": ["FF01-525/45"],
        }
    )
    red = build_channel(
        {
            "name": "647", "dye": "ATTO647N",
            "objective": {"label": "o", "magnification": 100, "na": 1.45,
                          "immersion": "oil", "verified_na": True},
            "detector": "Prime95B", "source": ["Spectra", "Red"],
            "dichroic": "Di03-R405/488/561/635", "emission": ["FF01-692/40"],
        }
    )
    assert green.crosstalk_from(red) < 0.05
    assert red.crosstalk_from(green) < 0.05


def test_photon_budget_returns_none_without_power_calibration():
    """No measured mW at the sample -> no absolute number, by design."""
    ch = build_channel(
        {
            "name": "647", "dye": "ATTO647N",
            "objective": {"label": "o", "magnification": 100, "na": 1.45,
                          "immersion": "oil", "verified_na": True},
            "detector": "Prime95B", "source": ["Spectra", "Red"],
            "dichroic": "FF650-Di01", "emission": ["FF01-692/40"],
        }
    )
    assert ch.detected_e_per_s() is None


def test_photon_budget_is_computable_once_calibrated():
    ch = build_channel(
        {
            "name": "647", "dye": "ATTO647N",
            "objective": {"label": "o", "magnification": 100, "na": 1.45,
                          "immersion": "oil", "verified_na": True},
            "detector": "Prime95B", "source": ["Spectra", "Red"],
            "dichroic": "FF650-Di01", "emission": ["FF01-692/40"],
        }
    )
    rate = ch.detected_e_per_s(
        power_mw_at_sample=1.0, illuminated_area_um2=100 * 100
    )
    assert rate is not None and rate > 0
    # Doubling the power must double the rate (linear, no saturation model).
    doubled = ch.detected_e_per_s(
        power_mw_at_sample=2.0, illuminated_area_um2=100 * 100
    )
    assert doubled == pytest.approx(2 * rate, rel=1e-9)


# --------------------------------------------------------- dual-camera split --
# Splitter = "DM A561LP" sends >561 nm to Kinetix_red, <561 nm to Kinetix_blue
# (kb/systems/current.md). Channel only ever reads .transmission, so the
# reflected-side camera needs a view where reflectance stands in for it.


def test_reflected_element_swaps_transmission_and_reflection():
    el = find_filter("DM A561LP", position="shared")
    refl = el.as_reflected()
    assert refl.transmission.at(500) == pytest.approx(el.reflection.at(500))
    assert refl.reflection.at(500) == pytest.approx(el.transmission.at(500))


def test_reflected_and_transmitted_sides_are_spectrally_complementary():
    el = find_filter("DM A561LP", position="shared")
    refl = el.as_reflected()
    # long-wavelength (red) camera: transmits above the edge
    assert el.transmission.at(650) > 0.9
    assert el.transmission.at(500) < 0.1
    # short-wavelength (blue) camera: reflects below the edge
    assert refl.transmission.at(500) > 0.9
    assert refl.transmission.at(650) < 0.1


def test_element_without_reflectance_refuses_a_reflected_view():
    el = find_filter("FF01-692/40", position="emission")  # plain bandpass, no R
    with pytest.raises(ValueError):
        el.as_reflected()


def test_build_channel_accepts_ref_side_dict_for_the_reflected_port():
    kwargs = dict(
        dye="AlexaFluor488",
        objective={"label": "o", "magnification": 100, "na": 1.45,
                   "immersion": "oil", "verified_na": True},
        detector="Prime95B",
        source=["Spectra", "Cyan"],
        dichroic="Di03-R405/488/561/635",
    )
    red = build_channel(
        {**kwargs, "name": "red-port", "emission": ["FF01-525/45", "DM A561LP"]}
    )
    blue = build_channel(
        {
            **kwargs,
            "name": "blue-port",
            "emission": ["FF01-525/45", {"ref": "DM A561LP", "side": "reflect"}],
        }
    )
    # AlexaFluor488 emits at ~519 nm, below the 561 nm split - it belongs on
    # the reflected (blue) port, not the transmitted (red) one.
    assert blue.spectral_collection() > red.spectral_collection()


def test_build_channel_rejects_an_unknown_side():
    with pytest.raises(ValueError):
        build_channel(
            {
                "name": "bad",
                "dye": "AlexaFluor488",
                "objective": {"label": "o", "magnification": 100, "na": 1.45},
                "detector": "Prime95B",
                "source": ["Spectra", "Cyan"],
                "dichroic": "Di03-R405/488/561/635",
                "emission": [{"ref": "DM A561LP", "side": "sideways"}],
            }
        )


# ------------------------------------------- L1.3: separation, not attenuation --
#
# The emission half of the 2026-08-10 repair, left undone for five weeks.
# `Channel.stokes_headroom_nm` weights the EXCITATION by the source line so a
# shared multiband dichroic is not mistaken for a 240 nm-wide passband; the
# emission side had the identical defect and no weighting, so a multiband
# EMITTER's support hull was mistaken for the band in use.
#
# The excitation-side twin of these is
# tests/test_recommend.py::test_stokes_headroom_uses_the_source_line_not_the_whole_shared_dichroic


def test_the_emission_filter_this_rests_on_is_multiband():
    """The data fact the rest of these depend on. If `MXR00724-EM` ever stops
    being a penta-band emitter, these tests are asserting nothing."""
    el = find_filter("MXR00724-EM")
    v = el.transmission.values
    above = v >= 0.5 * v.max()
    bands = np.sum(above[1:] & ~above[:-1]) + int(above[0])

    assert bands >= 4, "a penta-band emitter, not a single passband"
    assert el.transmission.at(488) < 1e-4, "488 nm sits in a notch"


def _active_channels():
    return build_channels("config/channels/active-microrheology-probe-tracer.yaml")


def test_a_notch_is_not_an_overlap():
    """The failure this fixes. On the green channel the path's support hull runs
    420-529 because the emitter's 420-460 band is also open, while the dye emits
    into 510-529 alone -- so `em[0]` was 420, the bottom of a band on the FAR
    SIDE of the 488 line, and the headroom came out -66 nm on a path that
    attenuates the excitation by 1.9e-11."""
    green = _active_channels()[0]

    hull = green.emission_transmission().support(0.5)
    assert hull[0] < 486 < hull[1], "the hull really does span the excitation line"
    assert green.emission_transmission().at(488) < 1e-9, "and the line is blocked"

    assert green.stokes_headroom_nm() > 0


def test_both_arms_of_the_real_proposal_clear_l1_3():
    """It stopped the lab's only real brief in tier 1 on both channels, at
    m=0.00, for a reason that was not true -- `python -m designer.cli run` gets
    past tier 1 because of this."""
    for channel in _active_channels():
        verdict = evaluate(channel, others=[c for c in _active_channels()
                                            if c.name != channel.name])
        assert not any(
            f.code == "spectral.overlap" for f in verdict.findings
        ), channel.name


def test_a_single_band_emission_filter_is_unaffected():
    """The signature of a correct repair of this kind: where the emitter has
    one passband, the hull and the dye-weighted band are the same band, so the
    number does not move. Four configs and eight channels behave this way."""
    for channel in build_channels("config/channels/proposed-2color.yaml"):
        assert channel.stokes_headroom_nm() >= 20.0


def test_a_path_that_really_passes_its_excitation_is_still_caught():
    """THE GUARD ON THE GUARD. L1.3 measures separation; L1.2 measures
    attenuation. A "fix" that conflated them would let a real leak through, so
    this pins the split: `demo-probe-tracer-2color` transmits 0.77 at its own
    excitation line, now reports a clean Stokes headroom, and must still FAIL.
    """
    channels = build_channels("config/channels/demo-probe-tracer-2color.yaml")
    for channel in channels:
        assert channel.emission_transmission().at(
            channel.source.spectrum.peak_nm()
        ) > 0.5, "this path really does pass its own excitation"
        assert channel.stokes_headroom_nm() > 0, "and L1.3 no longer objects"

        verdict = evaluate(channel, others=[c for c in channels
                                            if c.name != channel.name])
        assert verdict.status == "FAIL"
        assert any(f.code == "blocking.insufficient" for f in verdict.findings)


# --------------------------------- L1.5: the band in use, not the whole element --
#
# The same hull defect as L1.3's, one check over, and named as a latent hole in
# that entry before it was found to be live.


def test_bands_decompose_what_support_hulls():
    """`support` is `(bands[0][0], bands[-1][1])`. For a single passband the
    two agree, which is why reading the hull as "the band" went unnoticed."""
    el = find_filter("MXR00724-EM")
    bands = el.transmission.bands(0.5)
    hull = el.transmission.support(0.5)

    assert len(bands) >= 4
    assert (bands[0][0], bands[-1][1]) == hull
    for lo, hi in bands:
        assert lo <= hi
    assert all(a[1] < b[0] for a, b in zip(bands, bands[1:])), "disjoint, in order"


def test_the_collecting_band_is_where_the_light_lands():
    """Chosen by collected QE-weighted emission, not by which band contains
    the peak -- that question begs the one L1.5 asks, since a clipped peak is
    by definition outside its own band."""
    green, red = _active_channels()

    assert green.detection_band_nm() == (510.0, 529.0)
    assert red.detection_band_nm() == (677.0, 701.0)

    # And in both cases the hull's lower edge belongs to a band the dye never
    # reaches, which is the whole defect.
    assert green.emission_transmission().support(0.5)[0] == 420.0
    assert red.emission_transmission().support(0.5)[0] == 589.0


def test_l1_5_now_explains_the_red_arms_low_collection():
    """It reported nothing. ATTO647N peaks at 669 nm, the band collecting its
    light starts at 677, and the hull started at 589 -- so `589 > 669` was
    False and the clipping went unsaid on the one channel failing L1.4
    `collection.low` at m=0.871. `collection` owns the grade and this owns the
    explanation; it was not explaining."""
    red = _active_channels()[1]
    verdict = evaluate(red, others=[_active_channels()[0]])

    # Asserted as a list rather than `next(...)`: the regression is the
    # finding being ABSENT, and a StopIteration out of a generator reads as a
    # broken test rather than as the thing the test caught.
    found = [f for f in verdict.findings if f.code == "emission.peak_clipped"]
    assert found, "the clipping must be reported, not merely be true"
    clipped = found[0]
    assert clipped.numbers["band_start_nm"] == 677.0
    assert clipped.numbers["em_peak_nm"] == pytest.approx(669.0)
    #: Half the QE-weighted emission sits below the band edge. The actionable
    #: half of "the peak is clipped": 1 nm past a narrow dye's peak and 8 nm
    #: past a broad one cost very different amounts.
    assert clipped.numbers["fraction_below_band_nm"] == pytest.approx(0.498, abs=0.01)


def test_l1_5_is_unchanged_where_the_hull_was_already_one_band():
    """`proposed-2color`'s 647 arm was clipped before and is clipped now; its
    emitter has one passband, so hull and band are the same interval."""
    for channel in build_channels("config/channels/proposed-2color.yaml"):
        assert channel.detection_band_nm() == channel.emission_transmission().support(0.5)


def test_l1_3_does_not_use_the_band_edge_and_must_not():
    """The reverse substitution is worse. On a path with no emission filter the
    whole grid is ONE band, so its edge is 300 nm and every dye would "overlap"
    its own excitation -- the hull bug again by a different route. L1.3 asks
    where the detected LIGHT starts (dye-weighted); L1.5 asks where the
    FILTER's band starts (the band's own edge)."""
    channels = build_channels("config/channels/demo-probe-tracer-2color.yaml")
    for channel in channels:
        band = channel.detection_band_nm()
        assert band[1] - band[0] > 180, "effectively no emission filter"
        # The band edge would put this back at -188 / -79; the dye-weighted
        # support does not.
        assert channel.stokes_headroom_nm() > 0
