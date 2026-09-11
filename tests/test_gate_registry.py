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
    "velocity",
)

#: The same nine in COMMITTEE order, which is what the `L<lens>.<n>` addresses
#: are numbered from. `LENSES` above is the import order this file has always
#: used and puts stability before trapping; the address scheme follows docs/01
#: §4's lens numbers, where trapping is 7, stability is 8 and velocity is 9.
#: Two orderings for one set is worth the explicitness -- deriving the lens
#: number from `LENSES` would have silently numbered every trapping check L8.x.
LENSES_IN_COMMITTEE_ORDER = (
    "optics",
    "detection",
    "compute",
    "sample",
    "photo",
    "validity",
    "trapping",
    "stability",
    "velocity",
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
    # TWO CHECKS LEFT ON 2026-09-11 and neither number is reused. G11
    # (statistical_power) was this lens's only computation and
    # `1/sqrt(N_p x N_f)` counts independent samples -- 3.5x optimistic for one
    # trapped bead at 520 fps, where 6.3 consecutive frames fall inside one
    # relaxation time. G26 (post_processing) gated on an unverified
    # `despeckle_enabled` boolean that `detection/recommend.py` already refuses
    # on, where it destroys something computable.
    # kb/decisions/2026-09-11-g11-and-g26-removed.md
    #
    # `soft` survives elsewhere -- optics.collection, detection.sampling and
    # detection.snr -- so §1's rank order still has a level-3 tie-break to
    # decide. G11 was this lens's only one.
    "validity": (
        ("committee_coverage", "hard"),
        ("bias_ledger", "hard"),
        ("pixel_calibration", "hard"),
        ("photometric_calibration", "bias"),
    ),
    # A REPORTING SECTION SINCE 2026-09-10, like photo above: every check INFO.
    # G31 and G32 became reports (a trapped bead does not settle, and the free
    # case is lens 4's G19; sealing is declarable but an evaporation rate is
    # not), and `vibration` was deleted outright -- every part of the
    # microscope sits on one isolation table, so camera and sample move
    # together and an image shows only their relative motion.
    # kb/decisions/2026-09-10-lens-8-becomes-a-reporting-section.md
    # Lens 9, new 2026-09-11: the system's velocity. Three `hard` and two
    # `info`, and `LIMITS` empty -- every bound is derived from the caller's
    # `target_relative_error` or from a limit the trap model states about
    # itself. kb/decisions/2026-09-11-the-velocity-lens.md
    "velocity": (
        ("time_base", "hard"),
        ("displacement_window", "hard"),
        ("steady_state", "hard"),
        ("reynolds", "info"),
        ("time_axis_owner", "info"),
    ),
    "stability": (
        ("convening", "info"),
        # THREE GATES LEFT THIS LENS ON 2026-09-10, all to the hardware /
        # analysis stage: G28 (pfs_lock), G29 (axial_drift), G30
        # (lateral_drift). G28 was reading the wrong property; G29 and G30 were
        # reading the right one at the wrong time -- a drift rate is measured
        # during a run, so it is not an input to a design.
        # kb/decisions/2026-09-10-drift-is-not-a-design-element.md
        ("sedimentation", "info"),
        ("evaporation", "info"),
        # Replaced the two drift gates: reports the rate the run can absorb
        # (duration and DOF are both planning inputs) instead of gating on a
        # rate nobody can supply in advance. INFO, and unnumbered.
        ("drift_budget", "info"),
    ),
    "trapping": (
        ("effective_na", "info"),
        ("confinement", "hard"),
        ("trap_depth", "hard"),
        ("sampling", "hard"),
        # Proposes the stiffness window rather than judging a power
        # (2026-09-10). Both its ends escape the uncalibrated dial scale.
        ("power_window", "info"),
        # Reports that the 20 C is the LAB SETPOINT and not a sample
        # measurement (2026-09-11). It replaced an `assumed_inputs` entry that
        # blocked `advances` on every trapping verdict -- the gap between room
        # and focus IS trap heating, which is ungated by decision (E3), so
        # blocking on it charged twice for one decision.
        ("temperature_basis", "info"),
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
    # Empty since G26 went on 2026-09-11 -- `linearity_breaking_filters`
    # (`("despeckle",)`) was this lens's only numeric constant, and every check
    # left compares a declaration or another lens's verdict rather than a
    # threshold. The third lens with no constant of its own, after photo and
    # stability, and for a third reason: this one never computed much to begin
    # with.
    "validity": {},
    # Empty BY CONSTRUCTION, which is different from the other three empties:
    # photo and stability lost their constants when they became reporting
    # sections and validity never had many, but lens 9 was designed so that
    # every bound derives from the experiment's stated precision target. An
    # entry here means somebody introduced a threshold that does not.
    "velocity": {},
    # Empty since lens 8 became a reporting section on 2026-09-10 -- the
    # second lens to have no constant of its own, for a different reason than
    # photo's. `axial_drift_dof_fraction` (0.5) went with G29;
    # `settling_dof_fraction` (1.0) had nothing left to compare once G31
    # reported a velocity instead of a distance; `evaporated_fraction_max`
    # (0.05) was a threshold on a quantity the plan cannot supply.
    # `drift_budget` deliberately carries none: one full DOF is a definition,
    # and the half is printed beside it so a reader picks their own fraction.
    "stability": {},
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


# ---------------------------------------------------- check addressing ----
#
# RENUMBERED 2026-09-11 (KH): flat gate numbers G1-G32 became per-lens
# addresses `L<lens>.<n>`. The reason was structural, not cosmetic -- a flat
# number space made a gate number a GLOBAL resource, so removing lens 5's
# gates punched holes that lenses 6 and 8 then had to document, and by the end
# of that review ten of thirty-two numbers were vacant and five gates carried
# letter suffixes (G12a-c, G13a-d, G16b/c, G14a-c, G3b). Per-lens addressing
# makes a removal local and absorbs the letters into ordinary numbers.
#
# Two consequences worth stating because they are easy to get wrong:
#
#   * **Every check has an address, `info` ones included.** An address is a
#     LOCATION, not a claim that something can fail; the `kind` printed beside
#     it is what says that. That is what resolved the standing tension over the
#     eleven previously unnumbered checks -- numbering them used to imply
#     gatehood, and `L8.4 info` cannot.
#   * **The address lives in the check's docstring, not in its list position.**
#     So inserting or reordering a check does not renumber its neighbours: a
#     new check takes the next free number in its lens. The map below is what
#     holds that.
#
# kb/decisions/2026-09-11-per-lens-check-addresses.md

#: Every check's address, keyed by lens, in address order. The authoritative
#: map -- docs/04's table and the agent briefs are derived from it, not the
#: other way round.
EXPECTED_ADDRESSES: dict[str, tuple[tuple[str, str], ...]] = {
    "optics": (
        ("L1.1", "excitation"),
        ("L1.2", "blocking"),
        ("L1.3", "stokes"),
        ("L1.4", "collection"),
        ("L1.5", "centering"),
        ("L1.6", "crosstalk"),
        ("L1.7", "port"),
    ),
    "detection": (
        ("L2.1", "sampling"),
        ("L2.2", "saturation"),
        ("L2.3", "snr"),
        ("L2.4", "motion_blur"),
        ("L2.5", "frame_rate"),
    ),
    "compute": (
        ("L3.1", "data_rate"),
        ("L3.2", "fps_provenance"),
        ("L3.3", "pixel_container"),
        ("L3.4", "buffer"),
        ("L3.5", "capacity"),
        ("L3.6", "realtime_cpu"),
        ("L3.7", "ram_capacity"),
    ),
    "sample": (
        ("L4.1", "na_feasibility"),
        ("L4.2", "working_distance"),
        ("L4.3", "depth_in_chamber"),
        ("L4.4", "wall_drag"),
        ("L4.5", "ri_mismatch"),
        ("L4.6", "count_in_field"),
        ("L4.7", "depth_window"),
    ),
    "photo": (
        ("L5.1", "light_driving"),
        ("L5.2", "total_dose"),
        ("L5.3", "trap_heating"),
    ),
    "validity": (
        ("L6.1", "committee_coverage"),
        ("L6.2", "bias_ledger"),
        ("L6.3", "pixel_calibration"),
        ("L6.4", "photometric_calibration"),
    ),
    "trapping": (
        ("L7.1", "effective_na"),
        ("L7.2", "confinement"),
        ("L7.3", "trap_depth"),
        ("L7.4", "sampling"),
        ("L7.5", "power_window"),
        ("L7.6", "temperature_basis"),
    ),
    "velocity": (
        ("L9.1", "time_base"),
        ("L9.2", "displacement_window"),
        ("L9.3", "steady_state"),
        ("L9.4", "reynolds"),
        ("L9.5", "time_axis_owner"),
    ),
    "stability": (
        ("L8.1", "convening"),
        ("L8.2", "sedimentation"),
        ("L8.3", "evaporation"),
        ("L8.4", "drift_budget"),
    ),
}

#: Old flat number -> new address, for every G-number that named a live check
#: on 2026-09-11. Docs carry this table; **`kb/` is left alone**, because its
#: entries are dated records and rewriting them would falsify the history they
#: exist to hold.
GATE_TO_ADDRESS: dict[str, str] = {
    "G1": "L1.1", "G3": "L1.2", "G3b": "L1.3", "G2": "L1.4", "G4": "L1.6",
    "G5": "L2.1", "G6": "L2.2", "G7": "L2.3", "G8": "L2.4", "G9": "L2.5",
    "G12a": "L3.1", "G12b": "L3.2", "G12c": "L3.3",
    "G13a": "L3.4", "G13b": "L3.5", "G13c": "L3.6", "G13d": "L3.7",
    "G15": "L4.1", "G16": "L4.2", "G16b": "L4.3", "G16c": "L4.4",
    "G17": "L4.5", "G19": "L4.6",
    "G23": "L6.2", "G24": "L6.3", "G25": "L6.4", "G27": "L6.1",
    "G14a": "L7.2", "G14b": "L7.3", "G14c": "L7.4",
    "G31": "L8.2", "G32": "L8.3",
}

#: G-numbers that named a gate and now name nothing. They are NOT reused and
#: they are NOT translated: a reference to one of these in `kb/` points at
#: something that was removed, and the reason is the useful part.
RETIRED_GATES: dict[str, str] = {
    "G10": "photobleaching, removed 2026-09-09",
    "G11": "statistical power, removed 2026-09-11",
    "G18": "coverslip thickness, removed 2026-09-10",
    "G20": "saturation / triplet shelving, removed 2026-09-09",
    "G21": "light-driving, became the L5.1 report 2026-09-10",
    "G22": "total dose, became the L5.2 report 2026-09-10",
    "G26": "post-processing, removed 2026-09-11",
    "G28": "PFS lock, moved to the hardware stage 2026-09-10",
    "G29": "axial drift, moved to the hardware stage 2026-09-10",
    "G30": "lateral drift, moved to the hardware stage 2026-09-10",
}


def _docstring_addresses(lens: str) -> dict[str, str]:
    """Which check claims which address, read from its own docstring."""
    src = (REPO / lens / "checks.py").read_text()
    out: dict[str, str] = {}
    for m in re.finditer(
        r'def (check_\w+)\([^)]*\)[^:]*:\s*(?:r?"""|\'\'\')(L\d+\.\d+)', src
    ):
        out[m.group(1)] = m.group(2)
    return out


@pytest.mark.parametrize("lens", LENSES)
def test_every_check_has_the_address_it_is_supposed_to(lens: str) -> None:
    """An address is part of a check's identity. If this fails, either a check
    moved lens, or somebody renumbered rather than taking the next free number.
    """
    by_fn = _docstring_addresses(lens)
    codes = {c.run.__name__: c.code for c in _checks(lens).CHECKS}
    actual = tuple(
        sorted(
            ((addr, codes[fn]) for fn, addr in by_fn.items()),
            key=lambda t: int(t[0].split(".")[1]),
        )
    )
    assert actual == EXPECTED_ADDRESSES[lens]


def test_every_check_in_every_lens_is_addressed() -> None:
    """The eleven previously unnumbered checks included two `hard` ones that
    appeared in no table anywhere. Nothing is unaddressed now, and this is what
    keeps it that way."""
    for lens in LENSES:
        addressed = {
            codes for codes in (c.code for c in _checks(lens).CHECKS)
        }
        mapped = {code for _, code in EXPECTED_ADDRESSES[lens]}
        assert addressed == mapped, f"lens {lens}: {addressed ^ mapped} unaddressed"
    # 43 before lens 9 arrived on 2026-09-11, 48 after.
    assert sum(len(v) for v in EXPECTED_ADDRESSES.values()) == 48


def test_addresses_are_dense_and_lens_numbered() -> None:
    """`L<lens>.<n>` with n from 1, no gaps -- that density is the whole point
    of moving off the flat space, which ended with ten holes in thirty-two."""
    order = {name: i + 1 for i, name in enumerate(LENSES_IN_COMMITTEE_ORDER)}
    for lens, rows in EXPECTED_ADDRESSES.items():
        want = [f"L{order[lens]}.{i}" for i in range(1, len(rows) + 1)]
        assert [a for a, _ in rows] == want


def test_no_retired_gate_number_is_reused_or_translated() -> None:
    """A retired number must not reappear as an address's alias, and must not
    be silently mapped to a live check -- a `kb/` reference to G20 points at
    something that was removed, and that is the information."""
    assert not (set(RETIRED_GATES) & set(GATE_TO_ADDRESS))
    assert len(RETIRED_GATES) == 10
    src = "".join(
        (REPO / lens / "checks.py").read_text() for lens in LENSES
    )
    for gate in RETIRED_GATES:
        assert f"(was {gate})" not in src, f"{gate} is retired, not renamed"


def test_the_old_numbers_are_still_recoverable_from_the_code() -> None:
    """Each carried-forward address says which gate it was, so a reader coming
    from `kb/` or from a commit message can land in the right place."""
    found = {}
    for lens in LENSES:
        src = (REPO / lens / "checks.py").read_text()
        for m in re.finditer(r"(L\d+\.\d+) \(was (G\d+[a-d]?)\)", src):
            found[m.group(2)] = m.group(1)
    assert found == GATE_TO_ADDRESS


# ---------------- three numbering tests retired 2026-09-11 -------------------
#
# `test_every_gate_number_in_code_is_documented`,
# `test_vacant_numbers_are_claimed_by_nothing` and
# `test_optics_numbers_only_g3b_in_code` all existed to police the flat gate
# space: that a claimed number appeared in docs/04, that a vacant one was
# claimed by nothing, and that lens 1 had exactly one number in code while
# G1-G4 lived only in the document. The address scheme dissolves all three --
# every check is addressed, addresses are dense per lens, and there is no
# vacancy to guard. What replaced them is above:
# `test_every_check_has_the_address_it_is_supposed_to`,
# `test_every_check_in_every_lens_is_addressed`,
# `test_addresses_are_dense_and_lens_numbered` and
# `test_no_retired_gate_number_is_reused_or_translated`.
#
# `test_the_set_of_unnumbered_checks_does_not_grow_silently` went too: there
# are no unnumbered checks.


# ----------------------------------------------------- bias registry drift --
#
# MOVED 2026-09-11 to `committee/`, and the move corrected it.
#
# Two hand-written snapshots lived here -- the registered-with-no-emitter set
# and the emitted-with-no-registry set -- with a regex that derived the second
# from the source. Both were wrong:
#
#   * the first count missed `geometry.count_in_field.{crowded,jammed}` and
#     `geometry.depth_window.empty`, because it scanned only checks whose
#     `Check` registration was BIAS, and `bias_findings` filters on the
#     RESULT's kind. Fixed here 2026-09-11 by widening the scan.
#   * it then asserted that `sampling.wrong_direction` could not reach the
#     ledger. It can: it is BIAS at severity "fail". The regex had read the
#     `ok` branch of `"sampling" if ok else "sampling.wrong_direction"` and
#     not the `fail` branch, so the code was invisible to it. **Eight
#     unregistered emitters, not seven.**
#
# `committee.emissions` parses with `ast` instead, which handles the
# conditional and pairs a shared condition rather than multiplying it, and
# `committee.unparsed_sites` makes a parse miss detectable instead of silent.
# The reconciliation and its snapshot now live in
# `tests/test_committee_emissions.py`; run `python -m committee.cli reconcile`
# after adding or removing a gate.
# kb/decisions/2026-09-11-the-emission-collection-layer.md


def test_the_bias_registry_reconciliation_lives_in_the_committee_layer() -> None:
    """Left as a pointer rather than deleted, because this is where somebody
    adding a gate will look."""
    from committee import reconcile_bias_registry

    r = reconcile_bias_registry()
    assert not r.clean
    assert len(r.emitted_without_registry) == 8
    assert len(r.registered_without_emitter) == 7


