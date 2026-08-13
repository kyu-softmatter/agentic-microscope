"""Tests for validity.gate.evaluate (lens 6).

This lens reviews other lenses' verdicts, so the tests build real verdicts from
the real lenses where that is cheap, and structural stand-ins where it is not.
"""

from __future__ import annotations

import pytest

from validity.gate import evaluate
from validity.setup import STANDING_LENSES, ValiditySetup


class _V:
    """Structural VerdictLike stand-in for an upstream lens."""

    def __init__(self, status="PASS", evidence="measured", findings=(), metrics=None):
        self.status = status
        self.evidence = evidence
        self.margins = {}
        self.findings = list(findings)
        self.metrics = metrics or {}


class _F:
    """Structural FindingLike stand-in."""

    def __init__(self, code, lens, kind="bias", severity="warn", margin=0.5):
        self.code = code
        self.lens = lens
        self.kind = kind
        self.severity = severity
        self.margin = margin
        self.message = f"{code} from {lens}"


def _all_present(**overrides):
    up = {name: _V() for name in STANDING_LENSES}
    up.update(overrides)
    return up


def _setup(**overrides) -> ValiditySetup:
    defaults = dict(
        intended_quantity="diffusion",
        target_relative_error=0.05,
        upstream=_all_present(),
        n_particles=200.0,
        n_frames=2000,
        pixel_size_measured=True,
        analysis_script="D:/codes/track_msd.m",
    )
    defaults.update(overrides)
    return ValiditySetup(**defaults)


# ----------------------------------------------------------- Phase 0 -----


def test_blocked_without_any_upstream_verdict():
    """The lens has to run last; with nothing to review it refuses."""
    v = evaluate(_setup(upstream={}))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.upstream_verdicts" for f in v.findings)


def test_blocked_without_an_intended_quantity():
    v = evaluate(_setup(intended_quantity=None))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.intended_quantity" for f in v.findings)


def test_blocked_for_an_unknown_quantity():
    """Guessing which calibrations matter would mean certifying validity
    against the wrong criteria."""
    v = evaluate(_setup(intended_quantity="vibes"))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.quantity_requirements" for f in v.findings)


def test_blocked_without_a_target_error():
    v = evaluate(_setup(target_relative_error=None))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.target_error" for f in v.findings)


def test_blocked_without_a_sample_size():
    v = evaluate(_setup(n_particles=None, n_frames=None))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.sample_size" for f in v.findings)


# ------------------------------------------- G27 committee coverage ------


def test_missing_standing_lens_fails():
    """Nothing else in the codebase notices that a lens never ran -- there is
    no orchestrator, so each lens is invoked separately."""
    up = _all_present()
    del up["photo"]
    v = evaluate(_setup(upstream=up))
    assert v.status == "FAIL"
    assert v.metrics["validity.committee_coverage"]["missing_standing"] == ["photo"]


def test_blocked_upstream_lens_fails_coverage():
    """BLOCKED means 'no basis to decide'; validity cannot sit on top of that."""
    v = evaluate(_setup(upstream=_all_present(photo=_V(status="BLOCKED"))))
    assert v.status == "FAIL"
    assert v.metrics["validity.committee_coverage"]["blocked"] == ["photo"]


def test_failed_upstream_lens_fails_coverage():
    v = evaluate(_setup(upstream=_all_present(optics=_V(status="FAIL"))))
    assert v.status == "FAIL"
    assert v.metrics["validity.committee_coverage"]["failed"] == ["optics"]


def test_full_committee_passes_coverage():
    v = evaluate(_setup())
    assert v.margins["validity.committee_coverage"] == 10.0


def test_extra_conditional_lens_is_allowed():
    v = evaluate(_setup(upstream=_all_present(trapping=_V())))
    assert v.margins["validity.committee_coverage"] == 10.0


# ------------------------------------------------- G23 bias ledger ------


def test_no_upstream_bias_findings_passes():
    v = evaluate(_setup())
    assert v.metrics["validity.bias_ledger"]["bias_findings"] == 0


def test_uncorrected_upstream_bias_fails():
    up = _all_present(sample=_V(findings=[_F("geometry.ri_mismatch", "sample")]))
    v = evaluate(_setup(upstream=up))
    assert v.status == "FAIL"
    assert "geometry.ri_mismatch" in v.metrics["validity.bias_ledger"]["uncorrected_codes"]


def test_declaring_the_correction_clears_the_bias():
    up = _all_present(sample=_V(findings=[_F("geometry.ri_mismatch", "sample")]))
    v = evaluate(
        _setup(upstream=up, corrections_applied=frozenset({"geometry.ri_mismatch"}))
    )
    assert v.metrics["validity.bias_ledger"]["uncorrected"] == 0
    assert v.status != "FAIL"


def test_bias_ledger_margin_is_the_worst_uncorrected_upstream_margin():
    """The committee's worst unhandled problem stays visible instead of being
    averaged away."""
    up = _all_present(
        sample=_V(findings=[_F("geometry.ri_mismatch", "sample", margin=0.33)]),
        photo=_V(findings=[_F("perturbation.photobleaching", "photo", margin=0.8)]),
    )
    v = evaluate(_setup(upstream=up))
    assert v.margins["validity.bias_ledger"] == pytest.approx(0.33)


def test_only_bias_kind_findings_enter_the_ledger():
    """A hard failure is the owning lens's business; this ledger is for biases."""
    up = _all_present(
        detection=_V(findings=[_F("timing.frame_rate", "detection", kind="hard", severity="fail")])
    )
    v = evaluate(_setup(upstream=up))
    assert v.metrics["validity.bias_ledger"]["bias_findings"] == 0


def test_ok_severity_bias_findings_are_not_counted():
    up = _all_present(
        sample=_V(findings=[_F("geometry.coverslip", "sample", severity="info")])
    )
    v = evaluate(_setup(upstream=up))
    assert v.metrics["validity.bias_ledger"]["bias_findings"] == 0


# --------------------------------------------- G24 pixel calibration ----


def test_geometric_quantity_without_measured_pixel_size_fails():
    """docs/06 A1: every distance would be wrong by an unknown constant, and
    the numbers would still look reasonable."""
    v = evaluate(_setup(pixel_size_measured=False))
    assert v.status == "FAIL"
    assert v.bottleneck == "validity.pixel_calibration"


def test_intensity_quantity_does_not_need_pixel_size():
    v = evaluate(
        _setup(
            intended_quantity="stoichiometry",
            pixel_size_measured=False,
            background_measured=True,
            dark_current_measured=True,
            flat_field_measured=True,
        )
    )
    assert v.margins["validity.pixel_calibration"] == 10.0


# --------------------------------------- G25 photometric calibration ----


def test_intensity_quantity_needs_photometric_calibration():
    v = evaluate(_setup(intended_quantity="concentration"))
    assert any(
        f.code == "validity.photometric_calibration" and f.severity == "warn"
        for f in v.findings
    )


def test_geometric_quantity_does_not_need_photometric_calibration():
    v = evaluate(_setup())
    assert v.margins["validity.photometric_calibration"] == 10.0


def test_photometric_margin_reflects_how_many_calibrations_are_missing():
    partial = evaluate(
        _setup(
            intended_quantity="concentration",
            background_measured=True,
            dark_current_measured=True,
        )
    )
    none = evaluate(_setup(intended_quantity="concentration"))
    assert (
        partial.margins["validity.photometric_calibration"]
        > none.margins["validity.photometric_calibration"]
    )


# ------------------------------------------- G26 post-processing --------


def test_despeckle_fails_an_intensity_quantity():
    """docs/06 C1: linearity and noise independence are both broken."""
    v = evaluate(
        _setup(
            intended_quantity="intensity",
            despeckle_enabled=True,
            background_measured=True,
            dark_current_measured=True,
            flat_field_measured=True,
        )
    )
    assert v.status == "FAIL"
    assert any(
        f.code == "validity.post_processing" and f.severity == "fail" for f in v.findings
    )


def test_despeckle_still_warns_for_a_geometric_quantity():
    """Localization precision degrades even where linearity is not required:
    the filter changes the noise structure the estimator assumes."""
    v = evaluate(_setup(despeckle_enabled=True))
    f = next(f for f in v.findings if f.code == "validity.post_processing")
    assert f.severity == "info"
    assert v.status != "FAIL"


def test_clean_acquisition_passes_post_processing():
    v = evaluate(_setup())
    assert v.margins["validity.post_processing"] == 10.0


def test_post_processing_action_says_it_cannot_be_undone():
    v = evaluate(
        _setup(
            intended_quantity="intensity",
            despeckle_enabled=True,
            background_measured=True,
            dark_current_measured=True,
            flat_field_measured=True,
        )
    )
    f = next(f for f in v.findings if f.code == "validity.post_processing")
    assert "cannot be undone" in f.action


# ------------------------------------------ G11 statistical power -------


def test_adequate_sample_size_passes():
    v = evaluate(_setup())
    assert v.margins["validity.statistical_power"] >= 1.0


def test_thin_sample_size_warns():
    v = evaluate(_setup(n_particles=5.0, n_frames=20))
    assert any(
        f.code == "validity.statistical_power" and f.severity == "warn"
        for f in v.findings
    )


def test_statistical_power_reports_what_would_be_needed():
    v = evaluate(_setup(n_particles=5.0, n_frames=20))
    m = v.metrics["validity.statistical_power"]
    assert m["required_particles_at_this_frame_count"] == pytest.approx(20.0)


def test_particle_count_is_taken_from_lens_4_when_not_given():
    """Cross-lens consumption: lens 4's G19 feeds lens 6's G11, which is the
    'ROI vs statistics' constraint docs/01 §4 lists as 3 <-> 6."""
    up = _all_present(
        sample=_V(
            metrics={
                "geometry.count_in_field": {"evaluated": True, "expected_count": 250.0}
            }
        )
    )
    v = evaluate(_setup(upstream=up, n_particles=None))
    assert v.metrics["validity.statistical_power"]["n_particles"] == 250.0


def test_unevaluated_lens_4_count_does_not_leak_through():
    up = _all_present(
        sample=_V(metrics={"geometry.count_in_field": {"evaluated": False}})
    )
    v = evaluate(_setup(upstream=up, n_particles=None))
    assert v.status == "BLOCKED"
    assert any(f.code == "missing.sample_size" for f in v.findings)


# ---------------------------------------------------------- evidence ------


def test_undeclared_analysis_script_downgrades_evidence():
    """docs/05: which script processes the data changes the setting
    requirements, and this lens does not read D:\\codes itself."""
    v = evaluate(_setup(analysis_script=None))
    assert v.evidence == "assumed"
    assert v.advances is False


def test_particle_count_from_lens_4_downgrades_evidence():
    up = _all_present(
        sample=_V(
            metrics={
                "geometry.count_in_field": {"evaluated": True, "expected_count": 250.0}
            }
        )
    )
    v = evaluate(_setup(upstream=up, n_particles=None))
    assert v.evidence == "assumed"
    assert any("particle count" in a for a in v.assumed_inputs)


def test_fully_specified_setup_advances():
    v = evaluate(_setup())
    assert v.evidence == "measured"
    assert v.status == "PASS"
    assert v.advances is True


def test_verdict_serializes_with_the_lens_name():
    d = evaluate(_setup()).to_dict()
    assert d["lens"] == "validity"
    assert d["feasibility_note"]


# ------------------------------------ interop with the real lens types ----


def test_reviews_a_real_sample_lens_verdict():
    """The structural protocol has to work on the actual Verdict classes, not
    just the stand-ins -- each lens defines its own copy."""
    from optics.components import find_objective
    from sample.gate import evaluate as sample_evaluate
    from sample.setup import SampleSetup

    sample_verdict = sample_evaluate(
        SampleSetup(
            objective=find_objective("100x-Oil"),
            imaging_depth_um=30.0,  # 0.185 mismatch at 30 um -> a bias finding
            n_sample=1.333,
            coverslip_actual_um=170.0,
        )
    )
    assert sample_verdict.status == "PASS_WITH_CHANGES"

    v = evaluate(_setup(upstream=_all_present(sample=sample_verdict)))
    assert "geometry.ri_mismatch" in v.metrics["validity.bias_ledger"]["uncorrected_codes"]


def test_reviews_a_real_trapping_verdict_despite_its_missing_feasibility_field():
    """trapping.gate.Verdict has no `feasibility` field while the other five
    do. Lens 6 must tolerate that rather than crash."""
    from trapping.gate import Verdict as TrappingVerdict

    tv = TrappingVerdict(status="PASS", evidence="measured")
    assert not hasattr(tv, "feasibility")
    v = evaluate(_setup(upstream=_all_present(trapping=tv)))
    assert v.status == "PASS"
