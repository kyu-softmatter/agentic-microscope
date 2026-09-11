"""The gate registry itself, pinned.

Written 2026-09-09 after three threshold changes in one session broke no test
at all: G3's 5 OD -> 7 OD escalation, `ablate()`'s matching +2.0, and G5's
localization counterfactual. Two of the three were wrong for months and the
suite was green throughout, and the one test that did break turned out to be
asserting the bug rather than the behaviour.

So these tests do not check physics -- every lens's own test module does that.
They check that **the set of gates, their kinds and their thresholds cannot
change without a test changing with them.** A snapshot test is a poor way to
find a bug and a good way to make an edit deliberate, which is the property
that was missing.

Each snapshot below is a fact about the repository, not a preference. If you
are here because one failed: that is the test working. Update the snapshot in
the same commit as the change, and put the reasoning in `kb/decisions/`.

⚠ IF YOU VERIFY THESE BY MUTATION, CLEAR `__pycache__` AFTERWARDS. Swapping
`BIAS` for `SOFT` changes no byte count, so a mutate-test-restore cycle inside
one second leaves the file correct on disk and the *stale* `.pyc` still valid by
CPython's (mtime, size) check -- these tests then keep failing against source
that is already right. That happened while writing them, and `git status` is
clean the whole time, which is what makes it confusing.
"""

from __future__ import annotations

import importlib
import pathlib
import re

import pytest

#: Committee order (docs/01 §4), not alphabetical -- the order a reader expects.
LENSES = (
    "optics",
    "detection",
    "compute",
    "sample",
    "photo",
    "validity",
    "stability",
    "trapping",
)

REPO = pathlib.Path(__file__).resolve().parent.parent


def _checks(lens: str):
    return importlib.import_module(f"{lens}.checks")


# --------------------------------------------------------------- registry --

#: Every check that runs, with the kind that decides how a shortfall is
#: handled (docs/05 §2). Adding, removing or reclassifying one lands here.
EXPECTED_CHECKS: dict[str, tuple[tuple[str, str], ...]] = {
    "optics": (
        ("excitation", "hard"),
        ("blocking", "hard"),
        ("stokes", "hard"),
        ("collection", "soft"),
        ("centering", "info"),
        ("crosstalk", "bias"),
        ("port", "info"),
    ),
    "detection": (
        ("sampling", "soft"),
        ("saturation", "hard"),
        ("snr", "soft"),
        ("motion_blur", "bias"),
        ("frame_rate", "hard"),
    ),
    "compute": (
        ("data_rate", "hard"),
        ("fps_provenance", "bias"),
        ("pixel_container", "bias"),
        ("buffer", "hard"),
        ("capacity", "hard"),
        ("realtime_cpu", "hard"),
        ("ram_capacity", "hard"),
    ),
    "sample": (
        ("na_feasibility", "hard"),
        ("working_distance", "hard"),
        ("depth_in_chamber", "hard"),
        ("wall_drag", "bias"),
        # G17 became an INFO z-to-depth converter on 2026-09-10; it no longer
        # grades and no longer reaches G23's bias ledger.
        ("ri_mismatch", "info"),
        ("count_in_field", "info"),
        # Reports G16/G16b/G16c/G17's bounds as one band, and is the only
        # thing that can express an EMPTY window (2026-09-10).
        ("depth_window", "info"),
    ),
    # G10 (photobleaching) and G20 (saturation) were both removed 2026-09-09.
    # A REPORTING SECTION since 2026-09-10, not a judging lens: every check
    # is INFO, G21 and G22 joined G10 and G20 as vacant, and `photo` left
    # validity's STANDING_LENSES. tests/test_advances_rule.py holds the rest.
    "photo": (
        ("light_driving", "info"),
        ("total_dose", "info"),
        ("trap_heating", "info"),
    ),
    "validity": (
        ("committee_coverage", "hard"),
        ("bias_ledger", "hard"),
        ("pixel_calibration", "hard"),
        ("photometric_calibration", "bias"),
        ("post_processing", "hard"),
        ("statistical_power", "soft"),
    ),
    "stability": (
        ("convening", "info"),
        # THREE GATES LEFT THIS LENS ON 2026-09-10, all to the hardware /
        # analysis stage: G28 (pfs_lock), G29 (axial_drift), G30
        # (lateral_drift). G28 was reading the wrong property; G29 and G30 were
        # reading the right one at the wrong time -- a drift rate is measured
        # during a run, so it is not an input to a design.
        # kb/decisions/2026-09-10-drift-is-not-a-design-element.md
        ("sedimentation", "bias"),
        ("evaporation", "bias"),
        # Replaced the two drift gates: reports the rate the run can absorb
        # (duration and DOF are both planning inputs) instead of gating on a
        # rate nobody can supply in advance. INFO, and unnumbered.
        ("drift_budget", "info"),
        ("vibration", "info"),
    ),
    "trapping": (
        ("effective_na", "info"),
        ("confinement", "hard"),
        ("trap_depth", "hard"),
        ("sampling", "hard"),
        # Proposes the stiffness window rather than judging a power
        # (2026-09-10). Both its ends escape the uncalibrated dial scale.
        ("power_window", "info"),
    ),
}


@pytest.mark.parametrize("lens", LENSES)
def test_check_registry_is_pinned(lens: str) -> None:
    actual = tuple((c.code, c.kind) for c in _checks(lens).CHECKS)
    assert actual == EXPECTED_CHECKS[lens], (
        f"lens {lens}'s CHECKS changed. A check's KIND decides whether a "
        "shortfall stops the proposal (hard), damages the result (bias) or "
        "only costs quality (soft) -- docs/05 §2 -- so a reclassification is "
        "a decision, not a refactor."
    )


def test_every_lens_is_covered() -> None:
    """The snapshot must not silently stop covering a lens."""
    assert set(EXPECTED_CHECKS) == set(LENSES)


# -------------------------------------------------------------- thresholds --

#: Every numeric threshold any gate compares against. Three of these moved in
#: one session with no test noticing; that is what this pins.
EXPECTED_LIMITS: dict[str, dict] = {
    "optics": {
        # 5.0 in BOTH evidence tiers since 2026-09-09 -- the 7.0
        # `blocking_od_assumed` escalation was removed, see
        # kb/decisions/2026-09-09-blocking-threshold-fixed-at-5-od.md
        "blocking_od": 5.0,
        "crosstalk": 0.05,
        "excitation_ratio": 0.2,
        "filter_efficiency": 0.5,
        "spectral_collection": 0.15,
        "stokes_headroom_nm": 5.0,
    },
    "detection": {
        "adu_fraction": 0.9,
        "duty_cycle_max": 0.3,
        "full_well_fraction": 0.7,
        "nyquist_divisor": 2.0,
        "snr_target_default": 5.0,
    },
    "compute": {
        "buffer_seconds_min": 5.0,
        "disk_bandwidth_fraction": 0.7,
        # 32000 -> 128000, authorized by KH 2026-09-10. Still an
        # authorization, not a measurement of free RAM.
        "ram_capture_budget_mb": 128000.0,
    },
    "sample": {
        "aberration_depth_mismatch_um": 1.85,
        "matched_ri_tolerance": 0.005,
        "overlap_resolution_multiple": 3.0,
        "wall_drag_suppression": 0.1,
    },
    # Empty since G20 went: G21 compares against a per-sample MEASURED
    # threshold and G22 against a caller-supplied ceiling, so this lens has no
    # constant of its own. An entry appearing here is a new standing number.
    "photo": {},
    "validity": {"linearity_breaking_filters": ("despeckle",)},
    # `axial_drift_dof_fraction` (0.5) went with G29 on 2026-09-10.
    # `stability.drift_budget` replaced it and deliberately carries NO
    # threshold: it quotes the rate for one full DOF, which is a definition,
    # and halves it on the same line so a reader can pick their own fraction.
    "stability": {
        "evaporated_fraction_max": 0.05,
        "settling_dof_fraction": 1.0,
    },
}


@pytest.mark.parametrize("lens", sorted(EXPECTED_LIMITS))
def test_thresholds_are_pinned(lens: str) -> None:
    assert _checks(lens).LIMITS == EXPECTED_LIMITS[lens], (
        f"lens {lens}'s LIMITS changed. A threshold is a claim about physics "
        "or about this instrument; moving one needs a kb/decisions/ entry, "
        "not a commit message."
    )


def test_trapping_thresholds_are_pinned() -> None:
    """`trapping/checks.py` has no LIMITS dict -- its two thresholds are
    module constants, so they are pinned separately rather than left
    unprotected because of where they happen to live.
    """
    m = _checks("trapping")
    assert m.REQUIRED_TRAP_DEPTH_KT == 10.0
    assert m.REQUIRED_SAMPLING_RATIO == 10.0


def test_only_trapping_lacks_a_limits_dict() -> None:
    """If another lens loses its LIMITS dict, `test_thresholds_are_pinned`
    would start skipping it silently. Catch that instead.
    """
    missing = [L for L in LENSES if not hasattr(_checks(L), "LIMITS")]
    assert missing == ["trapping"]


# ------------------------------------------------------- gate numbering ----

#: Numbers that are VACANT and must never be reused, so that every reference
#: in the history stays unambiguous.
VACANT_GATES = ("G10", "G18", "G20", "G21", "G22", "G28", "G29", "G30")

#: Checks that carry NO gate number. Not an error -- but the set must not grow
#: without somebody noticing, because two of them are `hard` and can stop a
#: proposal from a gate that appears in no table in `docs/`.
#: Whether to number them is an open decision (KH, 2026-09-09).
UNNUMBERED_CHECKS: dict[str, tuple[str, ...]] = {
    # `stokes` gained G3b on 2026-09-10 and left this list. G1-G4 still live
    # only in docs/04 -- see test_optics_numbers_only_g3b_in_code.
    "optics": ("excitation", "blocking", "collection", "centering", "crosstalk", "port"),
    "sample": ("depth_window",),
    # All three: photo is a reporting section, and a number here would mean
    # "this can fail", which none of them can.
    "photo": ("light_driving", "total_dose", "trap_heating"),
    # `drift_budget` is unnumbered on purpose: it reports, it cannot fail, and
    # a number would advertise it as a gate. G29/G30 are vacant, not reused.
    "stability": ("convening", "vibration", "drift_budget"),
    # confinement gained G14a on 2026-09-10 and is no longer here.
    "trapping": ("effective_na", "power_window"),
}


def _docstring_gate_numbers(lens: str) -> dict[str, str]:
    """Which check claims which gate number, read from its own docstring."""
    src = (REPO / lens / "checks.py").read_text()
    out: dict[str, str] = {}
    for m in re.finditer(r'def (check_\w+)\([^)]*\)[^:]*:\s*(?:r?"""|\'\'\')\s*(G\d+[a-d]?)', src):
        out[m.group(1)] = m.group(2)
    return out


def _documented_gate_numbers() -> tuple[set[str], set[str]]:
    """(live, vacant) gate IDs from docs/04's gate table."""
    live: set[str] = set()
    vacant: set[str] = set()
    for line in (REPO / "docs" / "04-decision-engine.md").read_text().splitlines():
        m = re.match(r"\|\s*(~~)?(G\d+[a-d]?)(~~)?\s*\|", line)
        if not m:
            continue
        (vacant if (m.group(1) or "vacant" in line.lower()) else live).add(m.group(2))
    return live, vacant


def test_every_gate_number_in_code_is_documented() -> None:
    """A number a check claims must exist in docs/04's table.

    docs/04 numbers G12 and G13 as single rows covering their sub-letters, so
    `G12a` is satisfied by a `G12` row.
    """
    live, vacant = _documented_gate_numbers()
    assert live, "failed to parse docs/04's gate table at all"

    for lens in LENSES:
        for fn, gate in _docstring_gate_numbers(lens).items():
            base = re.sub(r"[a-d]$", "", gate)
            assert gate in live or base in live, (
                f"{lens}.{fn} claims {gate}, which is not a live row in "
                "docs/04's gate table"
            )
            assert gate not in vacant and base not in vacant, (
                f"{lens}.{fn} claims {gate}, which docs/04 marks VACANT"
            )


def test_vacant_numbers_are_claimed_by_nothing() -> None:
    live, vacant = _documented_gate_numbers()
    for g in VACANT_GATES:
        assert g in vacant, f"{g} should be marked vacant in docs/04's table"
        assert g not in live
        for lens in LENSES:
            claimed = set(_docstring_gate_numbers(lens).values())
            assert g not in claimed, f"{lens} claims the vacant gate {g}"


def test_optics_numbers_only_g3b_in_code() -> None:
    """Lens 1 names exactly one gate number in code, and only since
    2026-09-10.

    G1-G4 still live only in `docs/04`'s table, which is why CLAUDE.md and
    README describe them as appearing "in no Python file". The CHECKS are
    implemented and carry the documented thresholds -- see EXPECTED_LIMITS
    above, where `excitation_ratio` 0.20, `spectral_collection` 0.15,
    `blocking_od` 5.0 and `crosstalk` 0.05 are exactly G1-G4's criteria. So
    the gates are real and only the numbering is absent, and that distinction
    is pinned here rather than left to be rediscovered as a miscount.

    `stokes` is the exception: it is `hard`, it decided the 2026-09-05
    session, and it appeared in no table at all until it was given G3b.
    """
    assert _docstring_gate_numbers("optics") == {"check_stokes": "G3b"}


def test_the_set_of_unnumbered_checks_does_not_grow_silently() -> None:
    """Two of these are `hard`, so a proposal can be stopped by something that
    appears in no gate table. Numbering them is an open decision; letting more
    of them appear unnoticed is not.
    """
    for lens in LENSES:
        numbered = set(_docstring_gate_numbers(lens).values())
        codes = {c.code for c in _checks(lens).CHECKS}
        # A check is "numbered" if its module docstring maps some check_* to a
        # gate; map back by name to keep this readable.
        by_fn = _docstring_gate_numbers(lens)
        numbered_codes = {fn.removeprefix("check_") for fn in by_fn}
        unnumbered = sorted(c for c in codes if c not in numbered_codes)
        expected = sorted(UNNUMBERED_CHECKS.get(lens, ()))
        assert unnumbered == expected, (
            f"lens {lens}'s unnumbered checks changed: {unnumbered} != "
            f"{expected}. Either give the new check a gate number in its "
            "docstring, or add it here deliberately."
        )
