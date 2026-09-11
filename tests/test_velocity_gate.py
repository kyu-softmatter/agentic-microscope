"""Tests for velocity.gate.evaluate (lens 9).

Same split as the other gate tests: Phase 0 refusals are right, Phase 1/2
aggregation is right. The distinctive thing to pin here is that **this lens
FAILS on every real configuration today**, on L9.1, and that this is the
finding rather than a defect.
"""

from __future__ import annotations

import pytest

from velocity.gate import evaluate
from velocity.setup import VelocitySetup


def _setup(**overrides) -> VelocitySetup:
    """A configuration that clears everything L9.1 does not decide."""
    defaults = dict(
        commanded_velocity_um_per_s=20.0,
        driver="piezo_stage",
        step_duration_ms=60.0,
        particle_radius_um=2.5,
        viscosity_pa_s=1.0e-3,
        stiffness_pn_per_um=3.87,   # measured on this bench, 2026-09-03
        localization_sigma_nm=10.0,
        achieved_fps=520.0,
        target_relative_error=0.05,
    )
    defaults.update(overrides)
    return VelocitySetup(**defaults)


# ----------------------------------------------------------- Phase 0 -----


@pytest.mark.parametrize(
    "field,code",
    [
        ("commanded_velocity_um_per_s", "missing.commanded_velocity"),
        ("target_relative_error", "missing.target_error"),
        ("stiffness_pn_per_um", "missing.stiffness"),
        ("localization_sigma_nm", "missing.localization_sigma"),
        ("step_duration_ms", "missing.step_duration"),
    ],
)
def test_each_missing_input_blocks_by_name(field: str, code: str) -> None:
    v = evaluate(_setup(**{field: None}))
    assert v.status == "BLOCKED"
    assert any(f.code == code for f in v.findings)


def test_the_drag_needs_both_halves():
    for field in ("particle_radius_um", "viscosity_pa_s"):
        v = evaluate(_setup(**{field: None}))
        assert v.status == "BLOCKED"
        assert any(f.code == "missing.drag" for f in v.findings)


def test_the_target_error_refusal_says_why_it_cannot_be_defaulted():
    """It is not one input among several: every bound in the lens derives from
    it, so defaulting it would invent the window."""
    v = evaluate(_setup(target_relative_error=None))
    f = next(f for f in v.findings if f.code == "missing.target_error")
    assert "derived from it" in f.message
    assert "originating a physical number" in f.message


# --------------------------------------------------- L9.1 the time base ---


def test_the_lens_fails_today_and_that_is_the_finding():
    """No commanded-versus-actual velocity exists anywhere in the repository,
    L9.1 is `hard`, so a fully specified configuration still FAILS. The lens
    was built because nothing was guarding this."""
    v = evaluate(_setup())
    assert v.status == "FAIL"
    assert v.bottleneck == "velocity.time_base"
    assert v.margins["velocity.time_base"] == 0.0
    assert v.advances is False


def test_the_time_base_finding_separates_the_two_halves_of_the_scale():
    """Distance is corroborated to 0.24 % by two standards over 10 um
    (2026-09-03); time has never been checked. Saying only "no velocity scale"
    would have been both vaguer and less true."""
    f = next(f for f in evaluate(_setup()).findings if f.code == "velocity.time_base")
    assert "DISTANCE half of the scale is corroborated" in f.message
    assert "0.24" in f.message
    assert "TIME half has never been checked" in f.message
    assert "kappa = gamma*v/x_eq" in f.message


def test_the_action_refuses_the_closed_loop_argument():
    """A closed-loop controller reporting position does not settle it: the loop
    holds its own scale, which is the question."""
    f = next(f for f in evaluate(_setup()).findings if f.code == "velocity.time_base")
    assert "closed-loop controller reporting position does NOT settle this" in f.action
    assert "camera's own frame timestamps" in f.action


def test_a_measured_ratio_clears_it_and_a_bare_declaration_does_not():
    declared = evaluate(_setup(velocity_time_base_verified=True))
    assert declared.margins["velocity.time_base"] == 10.0
    f = next(
        f for f in declared.findings if f.code == "velocity.time_base"
    )
    assert "rests on the declaration and not on a number" in f.message

    measured = evaluate(
        _setup(velocity_time_base_verified=True, velocity_scale_ratio=0.998)
    )
    assert measured.status == "PASS"
    assert not any(
        "time base" in a for a in measured.assumed_inputs
    )


# ------------------------------------------- L9.2 the velocity window ----


def test_the_window_is_the_headline_and_both_ends_are_derived():
    m = evaluate(_setup()).metrics["velocity.displacement_window"]
    assert m["offset_floor_nm"] == pytest.approx(200.0)       # sigma / target
    assert m["offset_ceiling_nm"] == pytest.approx(2500.0)    # bead radius
    lo, hi = m["velocity_window_um_per_s"]
    assert lo == pytest.approx(16.42, rel=1e-2)
    assert hi == pytest.approx(205.3, rel=1e-2)


def test_too_slow_fails_and_says_what_precision_it_would_carry():
    v = evaluate(_setup(commanded_velocity_um_per_s=5.0))
    f = next(f for f in v.findings if f.code == "velocity.displacement_window")
    assert f.severity == "fail"
    # 5 um/s -> 60.9 nm offset -> 10/60.9 = 16.4%
    assert "16.4%" in f.message
    assert "Raise the velocity to at least 16.42 um/s" in f.message


def test_too_fast_fails_on_the_models_own_stated_limit():
    """Past the bead radius `trap_force` refuses, because the focus would fall
    outside the bead -- so the ceiling is quoted, not chosen."""
    v = evaluate(_setup(commanded_velocity_um_per_s=400.0))
    f = next(f for f in v.findings if f.code == "velocity.displacement_window")
    assert f.severity == "fail"
    assert "past its own 2500 nm radius" in f.message
    assert "the focus would fall outside the bead" in f.message


def test_the_window_tightens_when_the_target_tightens():
    loose = evaluate(_setup(target_relative_error=0.10))
    tight = evaluate(_setup(target_relative_error=0.02))
    lo_loose = loose.metrics["velocity.displacement_window"]["velocity_window_um_per_s"][0]
    lo_tight = tight.metrics["velocity.displacement_window"]["velocity_window_um_per_s"][0]
    assert lo_tight == pytest.approx(5 * lo_loose, rel=1e-3)


# --------------------------------------------- L9.3 the steady state -----


def test_a_short_step_fails_and_names_the_direction_of_the_bias():
    """A step shorter than the settling time reads a smaller displacement, so
    kappa = gamma*v/x_eq comes out too LARGE. The direction matters."""
    v = evaluate(_setup(step_duration_ms=10.0))
    f = next(f for f in v.findings if f.code == "velocity.steady_state")
    assert f.severity == "fail"
    assert "kappa comes out too" in f.message and "large" in f.message


def test_the_requirement_is_reported_in_frames_as_well():
    m = evaluate(_setup()).metrics["velocity.steady_state"]
    assert m["time_constants_needed"] == pytest.approx(3.0, rel=1e-2)
    assert m["step_duration_required_ms"] == pytest.approx(36.5, rel=1e-2)
    assert m["frames_required"] == 19        # at 520 fps
    assert m["relaxation_time_ms"] == pytest.approx(12.18, rel=1e-3)


def test_the_two_levers_are_named_as_pulling_against_each_other():
    """A stiffer trap shortens tau and shrinks the offset -- L9.2 and L9.3 want
    opposite things, and the action says so rather than recommending one."""
    v = evaluate(_setup(step_duration_ms=10.0))
    f = next(f for f in v.findings if f.code == "velocity.steady_state")
    assert "pull against each other" in f.action


# ------------------------------------------------- the two INFO reports --


def test_reynolds_reports_the_number_that_retires_the_gate():
    v = evaluate(_setup())
    f = next(f for f in v.findings if f.code == "velocity.reynolds")
    assert f.severity == "info"
    assert f.kind == "info"
    m = v.metrics["velocity.reynolds"]
    assert m["reynolds"] == pytest.approx(5.0e-5, rel=1e-2)
    assert m["reynolds_unity_velocity_um_per_s"] == pytest.approx(4.0e5, rel=1e-2)


def test_the_time_axis_is_attributed_to_lens_3_rather_than_re_derived():
    v = evaluate(_setup())
    f = next(f for f in v.findings if f.code == "velocity.time_axis_owner")
    assert "lens 3" in f.message and "L3.2" in f.message
    assert v.metrics["velocity.time_axis_owner"]["time_axis_owner"].startswith("lens 3")


def test_every_check_is_visible_because_ok_was_never_used():
    """Lens 9 was built after the `_ok`-hides-it defect had appeared five
    times, so its `_ok` writes severity "info" from the start and every check
    reaches `findings`."""
    v = evaluate(_setup(velocity_time_base_verified=True, velocity_scale_ratio=1.0))
    codes = {f.code for f in v.findings}
    assert codes >= {
        "velocity.time_base",
        "velocity.displacement_window",
        "velocity.steady_state",
        "velocity.reynolds",
        "velocity.time_axis_owner",
    }


# ---------------------------------------------------------- evidence -----


def test_the_near_wall_entry_cannot_be_retired_here():
    """gamma is the unbounded Stokes value. Lens 4's L4.4 bounds the near-wall
    inflation and deliberately does not correct it, so a velocity chosen from
    this window inherits the bias -- and this lens is not where it is cleared."""
    v = evaluate(_setup(velocity_time_base_verified=True, velocity_scale_ratio=1.0))
    assert any("near-wall drag" in a for a in v.assumed_inputs)
    assert v.evidence == "assumed"
    assert v.advances is False


def test_nothing_in_this_lens_has_a_threshold_of_its_own():
    """`LIMITS` empty by construction: every bound derives from the caller's
    target or from the trap model's stated limit."""
    import velocity

    assert velocity.LIMITS == {}
