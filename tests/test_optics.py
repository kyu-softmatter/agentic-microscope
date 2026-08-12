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
    them for G7 (quantization noise) and G9 (row time)."""
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
