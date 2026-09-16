"""Tests for `designer/emit.py` and `designer/run.py` -- the output boundary.

`run.py` had no tests at all until 2026-09-15, which is how its one claimed
handoff turned out never to have been wired. These cover the two things an
emitted plan can get wrong that nothing downstream would notice:

* **a hole written as a pass.** A lens that did not run, a channel that was
  never judged, a `missing.*` nobody carried -- each is a silence that reads
  as agreement (§3, E4).
* **a shape a skill misreads.** Held by calling `knowledge.plans.check_plan`
  on the emitted file, which is the same check `plan-check` runs.
"""

from __future__ import annotations

import textwrap

import pytest
import yaml

from designer import brief as brief_mod
from designer import emit as emit_mod
from designer import run as run_mod
from designer.emit import Identity

#: A brief lens 1 can build from, so the run gets past tier 1's first lens.
#: Deliberately the repository's own example rather than a fixture: a plan
#: emitted from a synthetic brief proves the serialiser and nothing about
#: whether the pipeline survives a real one.
BRIEF = "config/briefs/active-microrheology.yaml"

MINIMAL = """
meta: {id: minimal, date: 2026-09-15}
goal: {intended_quantity: msd, in_operator_words: "track beads"}
facts:
  lens_1_optics:
    detector: {value: Kinetix22, count: 1, source: "test", evidence: measured}
    objective: {value: "4-Apo LmbdS 40x WI", source: "test", evidence: measured}
gaps: []
"""


@pytest.fixture
def identity():
    return Identity(id="2026-09-15-t", date="2026-09-15", question="Does it?", title="T")


#: A brief whose lens 1 really does fail `hard`, for the tier-1 stop.
#:
#: `active-microrheology` used to serve this, on L1.3 at m=0.00 -- and that
#: verdict was wrong: the emission support hull of a penta-band filter read a
#: notch as a passband (2026-09-15). `demo-probe-tracer-2color` fails L1.2
#: `blocking.insufficient` at m=0.023 instead, which is a real leak: its
#: emission path transmits **0.77** at the excitation line.
STOPS_IN_TIER_1 = """
meta:
  id: stops-in-tier-1
  date: 2026-09-15
  channel_config: config/channels/demo-probe-tracer-2color.yaml
goal: {intended_quantity: msd, in_operator_words: "stop in tier 1"}
facts:
  lens_1_optics:
    detector: {value: Kinetix22, count: 1, source: "test", evidence: measured}
    objective: {value: "4-Apo LmbdS 40x WI", source: "test", evidence: measured}
gaps: []
"""


@pytest.fixture
def result():
    return run_mod.run(brief_mod.load(BRIEF))


@pytest.fixture
def stopped(tmp_path):
    path = tmp_path / "stops.yaml"
    path.write_text(textwrap.dedent(STOPS_IN_TIER_1), encoding="utf-8")
    return run_mod.run(brief_mod.load(path))


def _minimal(tmp_path):
    path = tmp_path / "minimal.yaml"
    path.write_text(textwrap.dedent(MINIMAL), encoding="utf-8")
    return run_mod.run(brief_mod.load(path))


# ------------------------------------------------- the shape plan-check wants


def test_the_emitted_md_passes_plan_check(tmp_path, result, identity):
    """The whole reason `plan.md` follows `kb/plans/_template.md`: one schema,
    already validated, rather than a second one maintained here."""
    from knowledge.plans import check_plan

    md, _ = emit_mod.write(result, identity, tmp_path / "plans")
    assert check_plan(md, root=tmp_path) == []


def test_the_sequence_table_exists_and_carries_no_steps(tmp_path, result, identity):
    """Stage 1 judges a configuration; it does not sequence a run. The table's
    header has to be there -- `plan-check` refuses a Sequence with no table at
    all -- and the rows have to not be, because a step this runner invented
    would have no observed confirmation to offer (SAFETY §0, E9)."""
    from knowledge.plans import CONFIRMATION_COLUMN, _section, _table_rows

    md, _ = emit_mod.write(result, identity, tmp_path / "plans")
    rows = _table_rows(_section(md.read_text(encoding="utf-8"), "Sequence"))

    assert len(rows) == 1
    assert CONFIRMATION_COLUMN in rows[0]


def test_writing_twice_refuses(tmp_path, result, identity):
    """A plan is written BEFORE a run and may already have been read by a
    person or acted on by a skill, so replacing one is a decision -- the same
    rule as `config/micromanager/set_pixel_size.py`."""
    emit_mod.write(result, identity, tmp_path / "plans")
    with pytest.raises(FileExistsError):
        emit_mod.write(result, identity, tmp_path / "plans")


def test_both_halves_share_the_slug(tmp_path, result, identity):
    md, plan_yaml = emit_mod.write(result, identity, tmp_path / "plans")
    assert md.stem == plan_yaml.stem == identity.id


# ----------------------------------------------- nothing silent, nothing new


def test_the_required_keys_are_present_even_when_empty(tmp_path, identity):
    """An absent key reads as a cleared one (§3), so both are keys and not
    conditional ones. The minimal brief declares no gaps at all, which is the
    case that would otherwise omit them."""
    doc = emit_mod.plan_yaml(_minimal(tmp_path), identity)
    assert "unevaluated" in doc
    assert "unresolved" in doc
    assert doc["unresolved"] == [] or all("field" in r for r in doc["unresolved"])


def test_the_four_judgment_lenses_are_written_as_holes(tmp_path, result, identity):
    """Stage 1 convenes no subagent, so 4 · 5 · 6 · 8's qualitative halves are
    absent on EVERY plan this emitter writes. A permanent absence omitted is a
    permanent silent clearance (E4)."""
    doc = emit_mod.plan_yaml(result, identity)
    assert {row["lens"] for row in doc["unevaluated_judgment"]} == {4, 5, 6, 8}

    body = emit_mod.plan_md(result, identity)
    assert "the judgment half of this lens is a subagent" in body


def test_a_lens_the_stop_cut_off_says_so_rather_than_repeating_its_seat(stopped):
    """It printed the seat's reason for being CONVENED as its reason for not
    running -- "standing lens (01 §4)" -- which reads as a lens that had
    nothing to say rather than one the tier-1 stop reached before."""
    states = {row["lens"]: row for row in stopped.unevaluated}

    assert stopped.stopped_after == "tier 1"
    assert "blocking.insufficient" in stopped.stop_reason
    assert states["validity"]["state"] == "not_reached"
    assert "hard` gate at m < 1" in states["validity"]["why"]


def test_the_table_and_the_list_agree_about_every_lens(stopped, identity):
    """One run described two ways on one page is the defect this catches: the
    table read the seat and the list read `unevaluated`, so a `not_reached`
    lens was `convened` four lines higher up."""
    body = emit_mod.plan_md(stopped, identity)
    table = [line for line in body.splitlines() if line.startswith("| 6 validity")]

    assert len(table) == 1
    assert "`not_reached`" in table[0]


def test_not_constructible_says_the_gate_emitted_nothing(result, identity):
    """The blind spot a harvest-based refiner cannot see into: no `missing.*`
    code exists to harvest, because `evaluate()` was never called."""
    body = emit_mod.plan_md(result, identity)
    assert "emitted no `missing.*` code at all" in body
    rows = {r["lens"]: r for r in result.unevaluated}
    assert rows["trapping"]["state"] == "not_constructible"
    assert rows["trapping"]["missing"]


# ------------------------------------------------- lens 1, once per channel


def test_every_channel_is_judged_not_only_the_first(result):
    """`optics.gate.evaluate` judges ONE channel against its siblings, so a
    two-colour proposal judged on channel 0 left the second arm's entire light
    path unexamined -- and an unexamined path is reported as nothing, which
    reads as a pass."""
    per_channel = result.runs["optics"].per_channel
    assert set(per_channel) == {"Tracer-DragonGreen", "Probe-ATTO647N"}
    #: And the two arms genuinely differ, so judging one is not judging both:
    #: only the red arm fails L1.4 (collection 0.871 against 1.0).
    assert per_channel["Probe-ATTO647N"].bottleneck == "collection.low"
    assert per_channel["Tracer-DragonGreen"].bottleneck == "collection"


def test_each_channel_gets_its_own_row_in_both_halves(result, identity):
    doc = emit_mod.plan_yaml(result, identity)
    subjects = {r["subject"] for r in doc["lenses"] if r["name"] == "optics"}
    assert subjects == {"Tracer-DragonGreen", "Probe-ATTO647N"}

    body = emit_mod.plan_md(result, identity)
    assert "1 optics · Probe-ATTO647N" in body


def test_a_hard_failure_in_the_second_channel_stops_the_run(tmp_path):
    """It could not be seen before: the tier-1 scan read `verdict`, which held
    channel 0's verdict alone.

    Unit-level on purpose. Both channels of the only two-colour brief in the
    repository fail, so a case where the FIRST one passes cannot be built from
    the real config files -- and a test that cannot distinguish the two
    behaviours is not a test of this one.
    """
    from optics.gate import Finding, Verdict

    clean = Verdict(status="PASS")
    dirty = Verdict(
        status="FAIL",
        findings=[
            Finding("fail", "spectral.overlap", "the second arm", kind="hard")
        ],
    )
    result = run_mod.Result(brief=brief_mod.load(BRIEF), seats={})
    result.runs["optics"] = run_mod.LensRun(
        lens="optics", verdict=clean, per_channel={"first": clean, "second": dirty}
    )

    found = run_mod._first_hard_failure(result, ("optics",))
    assert found is not None
    assert found[0] == "optics"
    assert found[1].code == "spectral.overlap"


# --------------------------------------------- the numbers came from the run


def test_the_checks_are_enumerated_from_margins_not_metrics(result, identity):
    """`margins` is `{code: margin}` in all nine gates; `metrics` is that in
    eight and a flat dict of metric NAMES in `optics`. Reading metrics gave
    lens 1 nine rows called `resolution_nm` and `depth_of_field_nm`, none of
    which is a check, and lost every real one."""
    doc = emit_mod.plan_yaml(result, identity)
    optics_rows = [r for r in doc["verdicts"] if r["lens"] == 1]

    codes = {r["check"] for r in optics_rows}
    assert "spectral.separation" in codes
    assert "resolution_nm" not in codes
    assert "depth_of_field_nm" not in codes
    assert {"L1.1", "L1.3"} <= {r["addr"] for r in optics_rows}


def test_the_addresses_come_from_committee_not_a_table_here(result, identity):
    """A hand-written code -> address map is the drift `committee/` exists to
    stop, and it would go stale on the next gate change exactly as the bias
    registries did twice."""
    from committee import collect_all

    known = {(s.lens, s.emitted_code): s.address for s in collect_all()}
    doc = emit_mod.plan_yaml(result, identity)
    names = {v: k for k, v in emit_mod.LENS_NUMBER.items()}

    for row in doc["verdicts"]:
        key = (names[row["lens"]], row["check"])
        if key in known:
            assert row["addr"] == known[key]


def test_a_blocked_lens_still_names_what_decided_it(result, identity):
    """Nothing graded, so there is no worst margin and `bottleneck` is None.
    A blank in that column reads as a lens with no opinion; the first refusal
    is the deciding fact."""
    doc = emit_mod.plan_yaml(result, identity)
    compute = next(r for r in doc["lenses"] if r["name"] == "compute")

    assert compute["status"] == "BLOCKED"
    assert compute["deciding_check"] == "missing.streams"


def test_the_brief_is_pinned_by_content(tmp_path, result, identity):
    """A plan whose brief has moved underneath it is not this plan, and a path
    alone cannot tell you that."""
    doc = emit_mod.plan_yaml(result, identity)
    assert doc["brief"]["sha256"] == emit_mod.sha256(result.brief.path)
    assert len(doc["brief"]["sha256"]) == 64


def test_the_channels_block_is_the_channel_files_own(result, identity):
    """Copied verbatim so `python -m optics.cli check` can be pointed at the
    plan rather than at a second copy of the same facts. Re-serialising lens
    1's objects would make a second definition of the light path."""
    doc = emit_mod.plan_yaml(result, identity)
    source = yaml.safe_load(
        open(result.brief.meta["channel_config"], encoding="utf-8").read()
    )
    assert doc["channels"] == source["channels"]


def test_the_rate_and_its_provenance_are_keys(result, identity):
    """`fps_source` is load-bearing (L3.2, E5) and `fps_usable_max` is the
    number lens 3 inherits, so neither may be prose. Null here, because this
    brief decides no rate -- and `undecided` is the honest source."""
    acquisition = emit_mod.plan_yaml(result, identity)["acquisition"]
    assert acquisition["fps_source"] == "undecided"
    assert acquisition["fps_usable_max"] is None


def test_the_plan_carries_no_instrument_state_key(result, identity):
    """Tier 3, and the constraint is the whole point: a device property no
    check reads would make the plan tier 2 and end its portability, and the
    interpreter cannot observe (01 §3 Principle 2, SAFETY §0)."""
    doc = emit_mod.plan_yaml(result, identity)
    assert "instrument_state" not in doc
    assert "**so if it is not written here, nobody sets it**" in emit_mod.plan_md(
        result, identity
    )


# -------------------------------------------------------------- subsystems


def test_lens_9_does_not_decide_piezo(result, identity):
    """A commanded velocity on this bench can be the stage OR the steered
    trap -- this brief's is the trap -- so convening lens 9 says a motion is
    commanded and not which device commands it. Inferring one is rule 2."""
    assert result.seats["velocity"].runs
    assert emit_mod.subsystems(result) == ["microscope", "tweezers"]


def test_the_brief_may_state_the_subsystems_itself(tmp_path, identity):
    result = _minimal(tmp_path)
    assert emit_mod.subsystems(result) == ["microscope"]

    result.brief.meta["subsystems"] = ["microscope", "piezo"]
    assert emit_mod.subsystems(result) == ["microscope", "piezo"]


# ------------------------------------------------- what the brief missed


def test_a_gap_may_name_the_code_it_answers(tmp_path):
    """Substring matching called `target_relative_error` unpredicted, because
    the code is `missing.target_error`. That count measures the BRIEF's
    quality, so a false surprise in it is a false accusation."""
    result = run_mod.run(brief_mod.load(BRIEF))
    rows = {r["field"]: r for r in result.unresolved}

    assert rows["missing.target_error"]["predicted_by_brief"] is True
    assert rows["missing.target_error"]["note"] is None


def test_an_unpredicted_code_is_marked_as_one(result):
    """The measure the planning-layer entry set for itself: a gate asking for
    something the brief did not know to ask for."""
    surprises = [r for r in result.unresolved if not r["predicted_by_brief"]]
    assert surprises
    assert all("NOT predicted by the brief" in r["note"] for r in surprises)
