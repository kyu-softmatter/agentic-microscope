"""Tests for `designer/judgment.py` -- stage 2's seam.

The seam exists because **code cannot convene a subagent**, so the thing worth
testing is not the convening. It is the two checkable halves either side of it:
what a judgment lens is handed, and whether what came back is a review.

Every test below is one way a judgment verdict can look like a review and not
be one. That list is the module's whole content; the serialisation is
incidental.
"""

from __future__ import annotations

import textwrap

import pytest
import yaml

from designer import brief as brief_mod
from designer import emit as emit_mod
from designer import judgment as judgment_mod
from designer import run as run_mod
from designer.emit import Identity
from designer.judgment import Judgment, Ruling

#: A brief that reaches tier 2 and tier 3, built to drive the seam's edge
#: cases -- lens 8 `absent` under the 30-minute threshold, lens 6 `awaiting`,
#: lenses 4 and 5 with verdicts. The REAL brief reaches stage 2 too, as of the
#: L1.3 repair (kb/decisions/2026-09-15-l1-3-read-a-notch-as-an-overlap.md),
#: and `test_the_real_brief_reaches_stage_2` below is what says so -- this
#: fixture is here for the states that brief does not happen to produce.
REACHES_TIER_2 = """
meta: {id: reaches-tier-2, date: 2026-09-15}
goal: {intended_quantity: msd, in_operator_words: "reach tier 2"}
facts:
  lens_1_optics:
    detector: {value: Kinetix22, count: 1, source: "test", evidence: measured}
    objective: {value: "4-Apo LmbdS 40x WI", source: "test", evidence: measured}
  lens_2_detection:
    exposure_ms: {value: 10.0, source: "test"}
    task_kind: {value: tracking, source: "test"}
    camera_mode: {value: "Sensitivity", source: "test"}
    wavelength_em_nm: {value: 520.0, source: "test"}
    roi_width_px: {value: 512, source: "test"}
    roi_height_px: {value: 512, source: "test"}
    row_time_ns: {value: 3531.2, source: "test"}
    achieved_fps: {value: 100.0, source: "timestamps"}
  lens_4_sample:
    probe: {diameter_um: 0.5, source: "test"}
    imaging_depth_um: {value: 8.0, source: "test"}
    chamber_height_um: {value: 100.0, source: "test"}
    tracer_concentration_per_ml: {value: 10000000.0, source: "test"}
  lens_9_velocity:
    target_relative_error: {value: 0.05, source: "test"}
  environment:
    acquisition_duration_s: {value: 60.0, source: "test"}
gaps: []
"""


@pytest.fixture
def result(tmp_path):
    path = tmp_path / "tier2.yaml"
    path.write_text(textwrap.dedent(REACHES_TIER_2), encoding="utf-8")
    return run_mod.run(brief_mod.load(path))


@pytest.fixture
def packets(result):
    return judgment_mod.build_packets(result)


@pytest.fixture
def real():
    """The repository's own brief, which reaches stage 2 as of the L1.3 repair.

    Used where the assertion is about a REAL two-colour light path -- lens 1
    with two arms, lens 8 undecided for want of a duration. The synthetic
    fixture cannot stand in: it names no channel file, so its lens 1 is
    `not_constructible`.
    """
    return run_mod.run(brief_mod.load("config/briefs/active-microrheology.yaml"))


def _judgment(packet, *, rulings=None, status="PASS", unevaluated=(), lens=None):
    """A verdict that answers a packet completely, unless a test spoils it.

    `upheld` for a `hard` finding below 1 and `overruled` otherwise -- not a
    convenience: OVERRULING one is refused by `cleared-a-stop`, so a fixture
    that overruled everything would trip that rule in every test rather than
    in the one testing it.
    """
    if rulings is None:
        rulings = [
            Ruling(
                code=s.code,
                ruling="upheld" if s.kind == "hard" and (s.m or 0) < 1.0 else "overruled",
                basis="fixture",
                source="kb/x.md",
            )
            for s in packet.must_rule_on
        ]
    return Judgment(
        lens=packet.lens if lens is None else lens,
        agent=packet.agent,
        status=status,
        rulings=tuple(rulings),
        unevaluated=tuple(unevaluated),
    )


# ----------------------------------------------- the real brief, end to end


def test_the_real_brief_reaches_stage_2():
    """It did not until the L1.3 repair on 2026-09-15.

    Both channels FAILed `spectral.overlap` at m=0.00 and precedence level 1
    stopped the run in tier 1, so this file's only subject was a synthetic
    fixture. The falsifier that entry set for itself is partly retired here:
    a real proposal now produces real packets.
    """
    result = run_mod.run(brief_mod.load("config/briefs/active-microrheology.yaml"))
    assert result.stopped_after is None

    packets = judgment_mod.build_packets(result)
    assert packets, "a real brief must reach at least one judgment lens"
    for packet in packets.values():
        assert packet.must_rule_on
        assert packet.verdict is not None


# ------------------------------------------------------- what is handed over


def test_a_lens_whose_gate_did_not_run_gets_no_packet(result, packets):
    """There is no verdict for its agent to interpret, so convening it would
    be asking for an opinion with no subject. The plan still carries its row
    as a hole (E4)."""
    assert result.seats["stability"].state == "absent"
    assert "stability" not in packets


def test_lens_6_is_refused_a_packet_until_the_others_return(result, packets):
    """E2. It reviews the other lenses' verdicts, so a packet built before
    those exist hands it the gate results and silently drops the judgment half
    of exactly what it is convened to review."""
    assert result.runs["validity"].ran
    assert "validity" not in packets

    returned = {
        lens: _judgment(packet) for lens, packet in packets.items()
    }
    later = judgment_mod.build_packets(result, judgments=returned)
    assert "validity" in later


def test_the_packet_carries_the_gates_verdict_to_interpret(packets):
    """The gate is authoritative over the agent file -- every one of the four
    says so in its own header -- so the verdict is the thing being read, not
    recomputed."""
    packet = packets["sample"]
    assert packet.verdict["lens"] == "sample"
    assert packet.verdict["status"]
    assert packet.agent_file == ".claude/agents/sample-optics.md"


def test_the_packet_carries_who_handed_it_what(packets):
    """A judgment lens never generates the number it is judging (§2), so the
    provenance of each number it will cite arrives with it."""
    carried = packets["sample"].carried
    assert any(row["from"] == "detection" for row in carried)


def test_the_packet_lists_every_finding_and_not_just_the_failures(result, packets):
    """An agent handed only the failures would be reading a filtered gate, and
    the filter would be this module's opinion about what matters."""
    emitted = {f.code for f in result.runs["sample"].verdict.findings}
    assert {s.code for s in packets["sample"].must_rule_on} >= emitted


def test_the_packet_carries_the_lens_01_4_pairs_it_with(real):
    """E6 in the packet. `sample-optics` says in its own description that it
    "must be invoked together with optics (Lens 1)" and the packet carried no
    lens 1 at all until 2026-09-15 -- found by convening it for real."""
    packets = judgment_mod.build_packets(real)
    sample = {row["name"] for row in packets["sample"].cross_lens}
    photo = {row["name"] for row in packets["photo"].cross_lens}

    assert "optics" in sample, "immersion vs depth, 4 <-> 1"
    assert "optics" in photo, "light level vs light-driving, 1 <-> 5"


def test_a_cross_lens_row_names_the_constraint_neither_lens_owns(real):
    """`carried` is a NUMBER crossing; this is a constraint with no owner,
    which is why both verdicts have to be read side by side and why one of
    them cannot simply compute it."""
    rows = judgment_mod.build_packets(real)["sample"].cross_lens
    immersion = next(r for r in rows if r["constraint"] == "Immersion vs depth")

    assert immersion["lens"] == 1
    assert immersion["verdict"]["status"]
    assert "Refractive-index mismatch" in immersion["content"]


def test_lens_1s_two_arms_both_reach_the_partner(real):
    """A two-colour proposal's arms differ -- on this brief the red arm fails
    L1.4 and the green does not -- so handing over `verdict` alone would hand
    over one arm and call it the lens."""
    rows = judgment_mod.build_packets(real)["photo"].cross_lens
    optics = next(r for r in rows if r["name"] == "optics")

    assert set(optics["per_channel"]) == {"Tracer-DragonGreen", "Probe-ATTO647N"}
    assert optics["per_channel"]["Probe-ATTO647N"]["bottleneck"] == "collection.low"


def test_a_partner_that_did_not_run_is_a_row_with_its_reason(real):
    """A constraint whose other half is unevaluated is `unevaluated`, not
    cleared (§3). Lens 8 is `undecided` on this brief -- no duration -- and
    lens 4 shares two constraints with it."""
    rows = judgment_mod.build_packets(real)["sample"].cross_lens
    eight = [r for r in rows if r["lens"] == 8]

    assert len(eight) == 2, "Chamber and Particle count"
    for row in eight:
        assert row["verdict"] is None
        assert "undecided" in row["why_absent"]


def _validity_setup_with(*codes):
    """A ValiditySetup carrying real upstream bias findings.

    Unit-level, because which biases a synthetic brief happens to raise is not
    the thing under test -- whether the ledger's three lists reach the packet
    is. Built from `optics.gate.Finding` so `bias_findings` sees the same
    shape a real lens hands over.
    """
    from optics.gate import Finding, Verdict
    from validity.setup import ValiditySetup

    findings = [
        Finding("warn", code, "upstream bias", kind="bias") for code in codes
    ]
    return ValiditySetup(
        intended_quantity="msd",
        upstream={"sample": Verdict(status="PASS_WITH_CHANGES", findings=findings)},
    )


def test_lens_6s_list_comes_from_validitys_own_ledger():
    """Not from a checklist here. `uncorrected` · `falsely_corrected` ·
    `unverified` are three states the setup already computes, and the middle
    one is why this is not merely "the uncorrected biases": a bias declared
    corrected for which no correction exists would have read clean."""
    from dataclasses import replace

    setup = _validity_setup_with("geometry.ri_mismatch", "motion_blur.biased")
    subjects = {s.code: s for s in judgment_mod._ledger_subjects(setup)}

    assert {"geometry.ri_mismatch", "motion_blur.biased"} <= set(subjects)
    assert all(
        s.because.startswith("an applicable bias") for s in subjects.values()
    )

    # Now declare a correction for the one that has none. It must get LOUDER,
    # not quieter: the ledger would otherwise have read clean.
    declared = replace(setup, corrections_applied=frozenset({"geometry.ri_mismatch"}))
    after = {s.code: s for s in judgment_mod._ledger_subjects(declared)}
    assert "NO correction exists" in after["geometry.ri_mismatch"].because


def test_an_unaudited_correction_reaches_the_list_too():
    """Accepted -- refusing an unknown gate's correction would block work on
    gates the tables have not caught up with -- but it pins the verdict's
    evidence to `assumed`, so a reviewer has to see it."""
    from dataclasses import replace

    setup = replace(
        _validity_setup_with("motion_blur.biased"),
        corrections_applied=frozenset({"motion_blur.biased"}),
    )
    # Declared and registered, so it clears and leaves the list.
    assert judgment_mod._ledger_subjects(setup) == []

    unaudited = replace(
        _validity_setup_with("fps_provenance.unrealizable"),
        corrections_applied=frozenset({"fps_provenance.unrealizable"}),
    )
    subjects = judgment_mod._ledger_subjects(unaudited)
    assert [s.code for s in subjects] == ["fps_provenance.unrealizable"]
    assert "neither registry" in subjects[0].because


def test_a_bias_subject_carries_whether_a_correction_exists():
    """§2 precedence level 2: proceed only where a correction formula exists,
    stop where none does. The reviewer cannot apply that rule without knowing
    which side of it each bias is on, and the answer is in `validity.setup`'s
    two registries -- not in a judgment this module makes."""
    from validity.setup import CORRECTIONS, UNCORRECTABLE

    setup = _validity_setup_with("geometry.ri_mismatch", "motion_blur.biased")
    subjects = {s.code: s for s in judgment_mod._ledger_subjects(setup)}

    assert subjects["motion_blur.biased"].correction == CORRECTIONS["motion_blur.biased"]
    assert (
        subjects["geometry.ri_mismatch"].correction
        == UNCORRECTABLE["geometry.ri_mismatch"]
    )


def test_the_return_schema_travels_with_the_request(packets):
    """So the contract is not only in a docstring on the reading side."""
    doc = packets["sample"].to_dict()
    assert doc["returns"]["unevaluated"].startswith("REQUIRED KEY EVEN WHEN EMPTY")
    assert doc["returns"]["status"] == list(judgment_mod.JUDGMENT_STATUSES)


def test_packets_are_files(tmp_path, result):
    """The planning-layer entry §3's argument, applied once more: a boundary
    only a function call crosses cannot be re-run from either side."""
    written = judgment_mod.write_packets(result, tmp_path / "packets")
    assert written
    for path in written:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert loaded["agent_file"].startswith(".claude/agents/")


# --------------------------------------------------- what may come back


def test_a_complete_verdict_is_accepted(packets):
    assert judgment_mod.check_judgment(_judgment(packets["sample"]), packets["sample"]) == []


def test_a_missing_unevaluated_key_is_refused_at_parse_time(tmp_path):
    """Refused in `read_judgment` rather than in `check_judgment`, because a
    Judgment with an invented empty list has already lost the distinction."""
    path = tmp_path / "v.yaml"
    path.write_text("lens: sample\nstatus: PASS\nrulings: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unevaluated"):
        judgment_mod.read_judgment(path)


def test_a_ruling_with_no_basis_is_refused(packets):
    """A judgment with no Why is not storable (§6) and not reviewable."""
    packet = packets["sample"]
    spoiled = _judgment(packet, rulings=[
        Ruling(code=s.code, ruling="upheld", basis="") for s in packet.must_rule_on
    ])
    refusals = judgment_mod.check_judgment(spoiled, packet)
    assert {r.rule for r in refusals} == {"no-basis"}


def test_a_subject_the_packet_did_not_ask_about_is_refused(packets):
    """A subject this lens introduced is a finding it generated, and a
    judgment lens never generates the number it is judging (§2)."""
    packet = packets["sample"]
    spoiled = _judgment(packet, rulings=list(_judgment(packet).rulings) + [
        Ruling(code="my.own.concern", ruling="overruled", basis="I thought of it")
    ])
    refusals = judgment_mod.check_judgment(spoiled, packet)
    assert [r.rule for r in refusals] == ["invented-subject"]


def test_silence_on_a_subject_is_refused(packets):
    """Omitting it reads as a pass (§3). `unevaluated` is the honest answer."""
    packet = packets["sample"]
    full = list(_judgment(packet).rulings)
    spoiled = _judgment(packet, rulings=full[:-1])
    refusals = judgment_mod.check_judgment(spoiled, packet)

    assert [r.rule for r in refusals] == ["silence"]
    assert full[-1].code in refusals[0].why


def test_naming_it_unevaluated_instead_of_ruling_is_accepted(packets):
    """A reviewer who cannot rule must be able to say so, or the only way to
    return a verdict is to pretend."""
    packet = packets["sample"]
    full = list(_judgment(packet).rulings)
    honest = _judgment(
        packet,
        rulings=full[:-1],
        unevaluated=[{"code": full[-1].code, "why": "no measurement exists"}],
    )
    assert judgment_mod.check_judgment(honest, packet) == []


def test_it_may_not_clear_what_a_hard_gate_stopped(packets):
    """§2 precedence level 4: this lens may refuse to advance what 1-3
    cleared; it may not clear what they stopped."""
    packet = packets["sample"]
    stopped = judgment_mod.Packet(
        lens=packet.lens, number=packet.number, agent=packet.agent,
        agent_file=packet.agent_file, verdict=packet.verdict,
        must_rule_on=[judgment_mod.Subject(
            code="geometry.na_feasibility", kind="hard", severity="fail",
            m=0.42, because="this lens's own gate emitted it",
        )],
    )
    overruled = _judgment(stopped, rulings=[
        Ruling(code="geometry.na_feasibility", ruling="overruled", basis="looks fine")
    ])
    refusals = judgment_mod.check_judgment(overruled, stopped)
    assert [r.rule for r in refusals] == ["cleared-a-stop"]

    upheld = _judgment(stopped, rulings=[
        Ruling(code="geometry.na_feasibility", ruling="upheld", basis="it stands")
    ])
    assert judgment_mod.check_judgment(upheld, stopped) == []


def test_the_withdrawn_words_are_refused_and_not_translated(packets):
    """`accept` and `refuse` were withdrawn 2026-09-15 because the two agents
    convened on the first real proposal used them in OPPOSITE senses for the
    same act -- lens 4 ruled `accept` writing "the gate's refusal stands",
    lens 5 ruled `refuse` writing "the finding stands".

    Refused rather than translated. Reading an ambiguous verdict by picking
    whichever sense happens to pass is the defect itself, applied once more.
    """
    packet = packets["sample"]
    for word in ("accept", "refuse"):
        spoiled = _judgment(packet, rulings=[
            Ruling(code=s.code, ruling=word, basis="b") for s in packet.must_rule_on
        ])
        refusals = judgment_mod.check_judgment(spoiled, packet)
        assert {r.rule for r in refusals} == {"ambiguous-ruling"}, word
        assert "2026-09-15" in refusals[0].why


def test_upholding_a_hard_stop_is_always_allowed(packets):
    """The asymmetry falls out of the rule, not the word: `upheld` is agreeing
    with the gate and can never be the act §2 precedence level 4 forbids."""
    packet = packets["sample"]
    upheld = _judgment(packet, rulings=[
        Ruling(code=s.code, ruling="upheld", basis="the gate is right")
        for s in packet.must_rule_on
    ])
    assert judgment_mod.check_judgment(upheld, packet) == []


# ----------------------------------------- the checks that did not run


def test_a_blocked_lens_lists_only_the_checks_that_REALLY_could_not_run(real):
    """Retargeted 2026-09-15 when Phase 0b landed, and the retarget is the
    point.

    Both agents reported that a Phase-0 block discarded checks needing nothing
    missing -- lens 5 of `trap_heating`, lens 4 of `depth_window`. Those now
    RUN under the block, so they are no longer skipped: they arrive as
    reported findings instead. What is left in the skipped list is exactly one
    check per lens, and in both cases it is the check the block is actually
    about.

    Before Phase 0b this asserted `{light_driving, total_dose, trap_heating}`
    were all skipped in lens 5 and eight checks in lens 4. Now two are.
    """
    packets = judgment_mod.build_packets(real)

    def by_severity(lens):
        subjects = packets[lens].must_rule_on
        return ({s.code for s in subjects if s.severity == "skipped"},
                {s.code for s in subjects if s.severity != "skipped"})

    photo_skipped, photo_reported = by_severity("photo")
    sample_skipped, sample_reported = by_severity("sample")

    #: `light_driving` requires `irradiance`, which is what lens 5 is blocked
    #: on -- so it alone genuinely cannot run.
    assert photo_skipped == {"light_driving"}
    assert {"perturbation.total_dose", "perturbation.trap_heating_unowned"} <= photo_reported

    #: `working_distance` requires the imaging depth, which is what lens 4 is
    #: blocked on. Everything else ran.
    assert sample_skipped == {"working_distance"}
    assert {"geometry.depth_window", "geometry.ri_mismatch"} <= sample_reported


def test_a_skipped_check_carries_its_registration_and_no_margin(real):
    """A reviewer cannot rule on a number that does not exist; what it can do
    is say whether the silence is acceptable, which is why it is on the list.
    """
    photo = {s.code: s for s in judgment_mod.build_packets(real)["photo"].must_rule_on}
    skipped = photo["light_driving"]

    assert skipped.severity == "skipped"
    assert skipped.m is None
    assert skipped.kind == "info", "the REGISTRATION's kind, lens 5 being a report"
    assert "not a pass" in skipped.because


def test_a_lens_that_reached_phase_1_lists_no_skipped_checks(tmp_path):
    """Derived from `verdict.margins` against the registry, so it is empty by
    construction wherever every check ran -- not by a special case."""
    path = tmp_path / "tier2.yaml"
    path.write_text(textwrap.dedent(REACHES_TIER_2), encoding="utf-8")
    result = run_mod.run(brief_mod.load(path))

    sample = judgment_mod.build_packets(result)["sample"]
    assert result.runs["sample"].verdict.status != "BLOCKED"
    assert not [s for s in sample.must_rule_on if s.severity == "skipped"]


def test_an_unknown_ruling_word_is_refused(packets):
    packet = packets["sample"]
    spoiled = _judgment(packet, rulings=[
        Ruling(code=s.code, ruling="probably fine", basis="hmm")
        for s in packet.must_rule_on
    ])
    assert {r.rule for r in judgment_mod.check_judgment(spoiled, packet)} == {
        "unknown-ruling"
    }


def test_an_unknown_status_is_refused(packets):
    packet = packets["sample"]
    spoiled = _judgment(packet, status="LOOKS_OK")
    assert [r.rule for r in judgment_mod.check_judgment(spoiled, packet)] == [
        "unknown-status"
    ]


def test_a_verdict_answering_the_wrong_packet_is_refused(packets):
    packet = packets["sample"]
    spoiled = _judgment(packet, lens="photo")
    assert "wrong-lens" in {r.rule for r in judgment_mod.check_judgment(spoiled, packet)}


def test_a_lens_number_instead_of_a_name_is_accepted(packets):
    """The packet carries both, and `1..9` is what `plan.yaml` uses."""
    packet = packets["sample"]
    numbered = _judgment(packet, lens=packet.number)
    assert judgment_mod.check_judgment(numbered, packet) == []


def test_lens_6_returning_before_the_others_is_refused(result):
    """E2 again, from the reading side: convene it alone and last."""
    returned = {
        lens: _judgment(p) for lens, p in judgment_mod.build_packets(result).items()
    }
    packet = judgment_mod.build_packets(result, judgments=returned)["validity"]

    early = judgment_mod.check_judgment(_judgment(packet), packet, others={})
    assert [r.rule for r in early] == ["out-of-order"]

    late = judgment_mod.check_judgment(_judgment(packet), packet, others=returned)
    assert late == []


# --------------------------------------------- the CLI's own E2 obligation


def test_the_cli_rebuilds_the_roster_as_verdicts_arrive(tmp_path, real):
    """Found by handing it a real lens-6 verdict for the first time.

    E2 makes the packet roster GROW: lens 6 has no packet until the others
    have returned. `cmd_emit` built the roster ONCE before its loop, so a
    lens-6 verdict was refused with "no packet in this run" -- the library
    half enforced E2 correctly and this half built the roster once and never
    looked again. Ordering the arguments differently cannot fix it; the
    rebuild has to happen per verdict.
    """
    import yaml

    from designer.cli import _load_judgments

    packets = judgment_mod.build_packets(real)
    paths = []
    for lens, packet in packets.items():
        path = tmp_path / f"{lens}.yaml"
        j = _judgment(packet)
        path.write_text(yaml.safe_dump({
            "lens": packet.number, "agent": packet.agent, "status": "BLOCKED",
            "rulings": [{"code": r.code, "ruling": r.ruling, "basis": r.basis}
                        for r in j.rulings],
            "unevaluated": [],
        }), encoding="utf-8")
        paths.append(path)

    # Lens 6's packet does not exist yet, so its verdict has to be written
    # against the roster the first two produce.
    later = judgment_mod.build_packets(
        real, judgments={lens: _judgment(p) for lens, p in packets.items()}
    )
    six = later["validity"]
    six_path = tmp_path / "validity.yaml"
    six_path.write_text(yaml.safe_dump({
        "lens": 6, "agent": six.agent, "status": "FAIL",
        "rulings": [{"code": s.code,
                     "ruling": "upheld" if s.kind == "hard" and (s.m or 0) < 1.0
                     else "overruled",
                     "basis": "fixture"} for s in six.must_rule_on],
        "unevaluated": [],
    }), encoding="utf-8")

    accepted, refused = _load_judgments([*paths, six_path], real)
    assert refused == 0, "lens 6 must be accepted once the others are in hand"
    assert set(accepted) == {"sample", "photo", "validity"}


def test_the_cli_still_refuses_lens_6_arriving_first(tmp_path, real):
    """The rebuild must not become a way past E2: submitted first, lens 6 has
    no packet at all, and that refusal is the rule doing its job."""
    import yaml

    from designer.cli import _load_judgments

    later = judgment_mod.build_packets(
        real,
        judgments={
            lens: _judgment(p)
            for lens, p in judgment_mod.build_packets(real).items()
        },
    )
    six = later["validity"]
    path = tmp_path / "validity.yaml"
    path.write_text(yaml.safe_dump({
        "lens": 6, "agent": six.agent, "status": "FAIL",
        "rulings": [], "unevaluated": [],
    }), encoding="utf-8")

    accepted, refused = _load_judgments([path], real)
    assert refused == 1
    assert accepted == {}


# ------------------------------------------------- what the plan then says


def test_four_states_and_each_has_its_own_reason(result):
    """A hole has four causes and they are not one fact. Collapsing
    `awaiting` into `absent` was the first version and it was wrong in the
    worst available direction: lens 6's gate had returned, and the row said
    its gate produced no verdict."""
    rows = {
        row["name"]: row
        for row in judgment_mod.judgment_rows(
            judgment_mod.build_packets(result), {}, result
        )
    }
    assert rows["sample"]["state"] == "convened"
    assert rows["validity"]["state"] == "awaiting"
    assert "E2" in rows["validity"]["why"]
    assert rows["stability"]["state"] == "absent"
    assert "the gate is `absent`" in rows["stability"]["why"]


def test_a_judged_lens_stops_being_a_hole(result):
    packets = judgment_mod.build_packets(result)
    returned = {lens: _judgment(p) for lens, p in packets.items()}
    rows = {
        row["name"]: row
        for row in judgment_mod.judgment_rows(packets, returned, result)
    }

    assert rows["sample"]["state"] == "judged"
    assert rows["sample"]["rulings"]
    assert all("basis" in r for r in rows["sample"]["rulings"])


def test_the_plan_says_which_stages_produced_it(tmp_path, result):
    """A plan that does not say how much of the committee ran is a plan whose
    holes a reader has to find."""
    identity = Identity(id="t", date="2026-09-15", question="Does it?")

    stage_1 = emit_mod.plan_md(result, identity)
    assert "stage 1.**" in stage_1

    packets = judgment_mod.build_packets(result)
    returned = {lens: _judgment(p) for lens, p in packets.items()}
    rows = judgment_mod.judgment_rows(packets, returned, result)
    stage_2 = emit_mod.plan_md(result, identity, rows)

    assert "stages 1 and 2.**" in stage_2
    assert "4 sample" in stage_2


def test_a_stage_2_plan_still_passes_plan_check(tmp_path, result):
    """The rulings go into the section `plan-check` refuses to let be silent,
    so the added prose must not break its shape."""
    from knowledge.plans import check_plan

    packets = judgment_mod.build_packets(result)
    returned = {lens: _judgment(p) for lens, p in packets.items()}
    rows = judgment_mod.judgment_rows(packets, returned, result)

    identity = Identity(id="2026-09-15-t", date="2026-09-15", question="Does it?")
    md, _ = emit_mod.write(result, identity, tmp_path / "plans", rows)
    assert check_plan(md, root=tmp_path) == []


def test_an_unjudged_lens_is_still_named_in_the_plan(tmp_path, result):
    """Three of the four states are still holes, and E4 is about all three."""
    identity = Identity(id="t", date="2026-09-15", question="Does it?")
    rows = judgment_mod.judgment_rows(judgment_mod.build_packets(result), {}, result)
    body = emit_mod.plan_md(result, identity, rows)

    assert "`awaiting`" in body
    assert "`absent`" in body
    assert "`convened`" in body
