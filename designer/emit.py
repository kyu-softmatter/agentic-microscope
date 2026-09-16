"""A committee run -> the two files a plan is (CLAUDE.md §2).

``run.py`` produces verdicts in memory. This module is the only thing that
writes them down, and it writes them **twice**, because the plan has two
readers with opposite needs:

``plan.md``
    the operator's. The ``kb/plans/_template.md`` shape, so
    ``python -m knowledge.cli plan-check`` validates it without a second
    schema -- including the ``Confirmed by`` column that refuses a step
    resting on a return code (E9).

``plan.yaml``
    the plan interpreter's, and any re-check's. Tier 3: **no device property
    that no check reads.** Admitting one makes the plan tier 2 and ends its
    portability (01 §3 Principle 2), and the interpreter leaves every
    parameter no check reads at its current value -- so a key here that
    nothing reads is a key nothing will honour.

Three rules this module holds, each of which is a way a plan lies:

**It originates nothing.** Every number comes from a Setup the builder filled
from the brief or from a gate's own output. There is no field this module
computes, and the one place it looks like it does -- ``channels:`` -- is a
verbatim copy of the channel file the brief names, not a re-serialisation of
lens 1's objects.

**``unevaluated`` and ``unresolved`` are written even when empty.** An absent
key reads as a cleared one and `unevaluated` != `cleared` (§3). In `plan.md`
the same rule is a section that may not be silent.

**Stage 1 writes no Sequence and no Preconditions.** All nine lenses have a
``gate.py``, so the committee's *code* half runs end to end -- but the
subagents (the qualitative half of 4 · 5 · 6 · 8) and the prose are stage 2.
An emitted plan therefore has every judgment row `unevaluated` and an empty
Sequence, and it has to **say** that rather than leave the reader to notice:
a plan whose Preconditions list is empty because nobody wrote it looks
exactly like one with nothing to check.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

from .run import CROSS_TIER, INTRA_TIER, Result

#: Lens name -> its number, for `L<lens>.<n>` and for the verdict table's
#: row labels. The numbering is CLAUDE.md §2's and is not this module's to
#: choose; it is spelled out here because nothing else maps name to number.
LENS_NUMBER = {
    "optics": 1,
    "detection": 2,
    "compute": 3,
    "sample": 4,
    "photo": 5,
    "validity": 6,
    "trapping": 7,
    "stability": 8,
    "velocity": 9,
}

#: The judgment halves stage 2 adds. Each is a row in `plan.md` that stage 1
#: must write as `unevaluated` rather than omit (E4).
JUDGMENT_LENSES = ("sample", "photo", "validity", "stability")


@dataclass(frozen=True)
class Identity:
    """What a plan is called. Not derivable from a brief, so it is asked for.

    ``id`` and ``date`` are the frontmatter's; ``question`` is what
    `knowledge.cli` indexes the entry by. The slug is the id, and the `.md`
    and `.yaml` share it deliberately: one run, one name, two readers.
    """

    id: str
    date: str
    question: str
    title: str | None = None

    @property
    def heading(self) -> str:
        return f"{self.date} · {self.title or self.id}"


def sha256(path: Path) -> str:
    """Pin the brief by content. A plan whose brief has moved underneath it is
    not this plan, and a path alone cannot tell you that."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --------------------------------------------------------------------------
# Addresses -- L<lens>.<n> for a code, from the one layer that already knows
# --------------------------------------------------------------------------


def _address_map() -> dict[tuple[str, str], tuple[str | None, str]]:
    """``(lens, emitted_code) -> (address, kind)``.

    From ``committee.collect_all()``, which parses every emission site out of
    each lens's ``checks.py``. Not a table maintained here: a hand-written map
    of codes to addresses is the drift `committee/` was built to stop, and it
    would go stale on the next gate change exactly as the bias registries did
    twice.
    """
    from committee import collect_all

    out: dict[tuple[str, str], tuple[str | None, str]] = {}
    for site in collect_all():
        out.setdefault((site.lens, site.emitted_code), (site.address, site.kind))
    return out


# --------------------------------------------------------------------------
# plan.yaml
# --------------------------------------------------------------------------


def _channels(result: Result) -> list:
    """The channel file's own `channels:` block, copied verbatim.

    The template says "`config/channels` schema VERBATIM -- so `python -m
    optics.cli check` can be pointed straight at this file rather than at a
    second copy of the same facts". Copying the source block is how that is
    literally true; re-serialising lens 1's `Channel` objects would produce a
    second definition of the light path that drifts from the first.
    """
    ref = result.brief.meta.get("channel_config")
    if not ref or not Path(ref).exists():
        return []
    raw = yaml.safe_load(Path(ref).read_text(encoding="utf-8")) or {}
    return raw.get("channels") or []


def _acquisition(result: Result) -> dict:
    """What lenses 2 and 3 were judged on, from their Setups.

    ``fps_source`` is load-bearing (L3.2, E5) and ``fps_usable_max`` is the
    number lens 3 inherits, so both are keys rather than prose. Where lens 2
    was not constructible every field is ``None`` -- which is the honest shape
    and not an empty acquisition.
    """
    det = result.runs["detection"].setup if "detection" in result.runs else None
    cmp_ = result.runs["compute"].setup if "compute" in result.runs else None
    duration = None if cmp_ is None else cmp_.acquisition_duration_s

    if det is None:
        return {
            "exposure_ms": None,
            "task_kind": None,
            "roi_width_px": None,
            "roi_height_px": None,
            "binning": None,
            "camera_mode": None,
            "fps": None,
            "fps_source": "undecided",
            "fps_usable_max": None,
            "duration_s": duration,
        }

    window = det.frame_rate_window()
    return {
        "exposure_ms": det.acquisition.exposure_ms,
        "task_kind": det.acquisition.task_kind,
        "roi_width_px": det.camera.roi_width_px,
        "roi_height_px": det.camera.roi_height_px,
        "binning": det.camera.binning,
        "camera_mode": det.camera.mode,
        "fps": det.acquisition.decided_fps,
        "fps_source": det.acquisition.fps_source,
        "fps_usable_max": window.fps_usable_max,
        "duration_s": duration,
    }


def _system(result: Result) -> dict:
    """The system under study, carried through because L2.6 reports against it
    and a re-check needs it. Read off lens 2's Setup where it ran, and off the
    brief where it did not -- the same two values either way."""
    det = result.runs["detection"].setup if "detection" in result.runs else None
    if det is not None:
        return {
            "characteristic_length_um": det.characteristic_length_um,
            "characteristic_time_s": det.characteristic_time_s,
        }
    return {
        "characteristic_length_um": result.brief.value("system.characteristic_length_um"),
        "characteristic_time_s": result.brief.value("system.characteristic_time_s"),
    }


def _subjects(run) -> dict:
    """``{subject -> verdict}`` for one lens.

    One entry for eight of the nine. Lens 1 judges a channel against its
    siblings, so a two-colour proposal is two subjects -- and reporting only
    the first left the second arm's entire light path unexamined and unnamed,
    which reads as a pass.
    """
    return run.per_channel or {None: run.verdict}


def _lens_rows(result: Result) -> list[dict]:
    """The lens-level answer, one row per lens that ran.

    Separate from the per-check rows because a BLOCKED lens has **no** check
    rows -- nothing graded -- and a plan that carried only the check rows
    would show a refusing lens as an empty one. Its refusals are in
    `unresolved` and the reason it refused is here.
    """
    addresses = _address_map()
    rows: list[dict] = []
    for lens in LENS_NUMBER:
        run = result.runs.get(lens)
        if run is None or not run.ran:
            continue
        for subject, v in _subjects(run).items():
            code = v.bottleneck or next(
                (f.code for f in v.findings if f.code.startswith("missing.")), None
            )
            rows.append({
                "lens": LENS_NUMBER[lens],
                "name": lens,
                #: Lens 1 is judged per channel, so the row needs to say which
                #: one. `null` everywhere else: the lens IS the subject.
                "subject": subject,
                "status": v.status,
                "feasibility": v.feasibility,
                "evidence": v.evidence,
                #: docs/05's criterion: feasibility >= TIGHT and evidence
                #: measured and no hard gate below 1. `assumed` computes and
                #: reports; only `measured` authorises (§3).
                "advances": v.advances,
                "deciding_check": code,
                "deciding_addr": addresses.get((lens, code), (None, None))[0] if code else None,
            })
    return rows


def _verdict_rows(result: Result) -> list[dict]:
    """One row per check that produced a result, ok ones included.

    Enumerated from ``verdict.margins``, which is ``{result.code: margin}`` in
    all nine gates. **Not from ``metrics``**: that is ``{code: numbers}`` in
    eight of them and a flat dict of metric NAMES in ``optics`` -- so reading
    metrics gave lens 1 nine rows called `resolution_nm` and
    `depth_of_field_nm`, none of which is a check, and lost every real one.
    A uniform field beats a nearly-uniform one.

    A check that passed quietly still ran, and a plan listing only findings
    would show a clean lens as an empty one -- hence `status: ok` rather than
    omission.
    """
    addresses = _address_map()
    rows: list[dict] = []
    for lens in LENS_NUMBER:
        run = result.runs.get(lens)
        if run is None or not run.ran:
            continue
        for subject, verdict in _subjects(run).items():
            severities = {f.code: f.severity for f in verdict.findings}
            for code, margin in verdict.margins.items():
                address, kind = addresses.get((lens, code), (None, None))
                rows.append({
                    "lens": LENS_NUMBER[lens],
                    "subject": subject,
                    "addr": address,
                    "check": code,
                    "kind": kind,
                    "status": severities.get(code, "ok"),
                    "m": margin,
                    #: The lens's evidence axis, which is the only one there
                    #: is: a per-check tier would be a claim no gate makes.
                    "evidence": verdict.evidence,
                })
    return rows


def _judgment_rows() -> list[dict]:
    """Stage 2's half of the committee, written as holes.

    Not a formality. E4: a lens that was not convened leaves a hole and not a
    pass, and the qualitative halves of 4 · 5 · 6 · 8 are *never* convened by
    stage 1 -- so omitting them would turn four permanent absences into four
    silent clearances on every plan this emitter writes.
    """
    return [
        {
            "lens": LENS_NUMBER[lens],
            "state": "absent",
            "why": "the judgment half of this lens is a subagent, and stage 1 "
            "runs the code half only -- no subagent was convened",
        }
        for lens in JUDGMENT_LENSES
    ]


def plan_yaml(result: Result, identity: Identity) -> dict:
    """The machine half. Every key the template declares, present."""
    brief_path = Path(result.brief.path)
    return {
        "id": identity.id,
        "date": identity.date,
        "status": "planned",
        "brief": {"ref": str(brief_path), "sha256": sha256(brief_path)},
        "channels": _channels(result),
        "acquisition": _acquisition(result),
        "system": _system(result),
        "lenses": _lens_rows(result),
        "verdicts": _verdict_rows(result),
        #: Both REQUIRED even when empty (§3). `judgment` is a second list
        #: rather than mixed into the first because the two absences have
        #: different causes: the roster decided one, and stage 1 not existing
        #: decided the other.
        "unevaluated": result.unevaluated,
        "unevaluated_judgment": _judgment_rows(),
        "unresolved": result.unresolved,
        "stopped_after": result.stopped_after,
        "stop_reason": result.stop_reason,
    }


# --------------------------------------------------------------------------
# plan.md
# --------------------------------------------------------------------------


def subsystems(result: Result) -> list[str]:
    """Which hardware skills may act on this plan.

    ``microscope`` is always in the roster. ``tweezers`` follows from lens 7
    being convened, which is a fact about the brief.

    **Lens 9 does not decide ``piezo``.** A commanded velocity on this bench
    can be the stage *or* the steered trap -- the active brief's is the trap --
    so convening lens 9 says a motion is commanded and not which device
    commands it. Inferring one would be exactly the shape of guess rule 2
    forbids, so the brief states it in ``meta.subsystems`` or it is not
    claimed.
    """
    from hardware.orchestrator import SUBSYSTEMS

    stated = result.brief.meta.get("subsystems")
    if stated:
        return [s for s in SUBSYSTEMS if s in set(stated)]

    present = {"microscope"}
    if result.seats["trapping"].runs:
        present.add("tweezers")
    return [s for s in SUBSYSTEMS if s in present]


def _lens_label(lens: str) -> str:
    return f"{LENS_NUMBER[lens]} {lens}"


def _states(result: Result) -> dict[str, str]:
    """Lens -> the state the `unevaluated` block gives it.

    Read off that block rather than off the seat, so the table and the list
    below it cannot disagree. They did: a lens the tier-1 stop cut off printed
    `convened` in the table and `not_reached` in the list, which is one run
    described two ways on one page.
    """
    return {row["lens"]: row["state"] for row in result.unevaluated}


def _committee_table(result: Result) -> list[str]:
    addresses = _address_map()
    states = _states(result)
    lines = [
        "| Lens | Verdict | Deciding check | m | Evidence |",
        "|---|---|---|---|---|",
    ]
    #: By lens NUMBER, matching the template's table and the order an operator
    #: scans -- the tiers are the run order and they are reported as handoffs
    #: above, not as row order here.
    for lens in LENS_NUMBER:
        run = result.runs.get(lens)
        if run is None or not run.ran:
            lines.append(
                f"| {_lens_label(lens)} | `{states.get(lens, 'unevaluated')}` "
                "| — | — | — |"
            )
            continue
        for subject, verdict in _subjects(run).items():
            code = verdict.bottleneck
            if code is None:
                # A BLOCKED lens has no worst margin, because nothing graded.
                # The first refusal IS the deciding fact, so name it: a blank
                # here reads as a lens with no opinion.
                code = next(
                    (f.code for f in verdict.findings if f.code.startswith("missing.")),
                    None,
                )
            addr = addresses.get((lens, code), (None, None))[0] if code else None
            deciding = f"`{addr or code}`" if code else "—"
            m = verdict.margins.get(code) if code else None
            label = _lens_label(lens) + (f" · {subject}" if subject else "")
            lines.append(
                f"| {label} | `{verdict.status}`"
                f"{' (advances)' if verdict.advances else ''} | {deciding} | "
                f"{'—' if m is None else f'{m:.2f}'} | `{verdict.evidence}` |"
            )
    return lines


def _not_evaluated(result: Result) -> list[str]:
    """The section `plan-check` refuses to let be silent."""
    lines = [
        "**Not evaluated.** `unevaluated` is not `cleared` (CLAUDE.md §3).",
        "",
        "*The code half* — a gate that did not run, and why:",
        "",
    ]
    for row in result.unevaluated:
        lens = row["lens"]
        detail = row.get("why") or ""
        if row["state"] == "not_constructible":
            detail = (
                f"{row['why']} — missing {', '.join(row['missing'])}. "
                "**The gate was never called, so it emitted no `missing.*` code "
                "at all**, which is the blind spot a harvest-based refiner "
                "cannot see into."
            )
        lines.append(f"- **{_lens_label(lens)}** — `{row['state']}`: {detail}")

    lines.append("")
    lines.append(
        "*The judgment half* — the four subagents stage 1 can never convene. "
        "A lens can appear in both lists, and that is not a duplicate: its "
        "gate and its subagent are two evaluations. Written out rather than "
        "omitted (E4), because a permanent absence omitted is a permanent "
        "silent clearance:"
    )
    lines.append("")
    for row in _judgment_rows():
        name = next(k for k, v in LENS_NUMBER.items() if v == row["lens"])
        lines.append(f"- **{_lens_label(name)}** — `unevaluated`: {row['why']}")
    return lines


def _handoffs() -> list[str]:
    lines = [
        "**The handoffs, not the nine calls.** What one lens carried to "
        "another in this run:",
        "",
        "| From | To | What crossed |",
        "|---|---|---|",
    ]
    for (src, dst), why in {**INTRA_TIER, **CROSS_TIER}.items():
        lines.append(f"| {_lens_label(src)} | {_lens_label(dst)} | {why} |")
    return lines


def plan_md(result: Result, identity: Identity) -> str:
    """The operator's half, in the `kb/plans/_template.md` shape."""
    subs = subsystems(result)
    out: list[str] = [
        "---",
        f"id: {identity.id}",
        f'question: "{identity.question}"',
        f"date: {identity.date}",
        "status: planned",
        f"subsystems: [{', '.join(subs)}]",
        "---",
        "",
        f"# {identity.heading}",
        "",
        "**Written by `python -m designer.cli`, stage 1.** The committee's "
        "code half only: all nine lenses have a `gate.py` and every one of "
        "them ran or said why it did not, but the subagents — the qualitative "
        "half of 4 · 5 · 6 · 8 — were not convened and the prose sections "
        "below were not written. Both facts are load-bearing, not caveats.",
        "",
        f"**Machine half:** `{identity.id}.yaml`, same slug — one run, one "
        "name, two readers.",
        "",
        "## Request",
        "",
        (result.brief.goal.get("in_operator_words") or "").strip()
        or "_The brief states no goal in the operator's words._",
        "",
        f"Intended quantity: `{result.brief.intended_quantity}`. "
        f"Brief: `{result.brief.path}`, sha256 "
        f"`{sha256(Path(result.brief.path))[:12]}…`.",
        "",
        "## Proposed setting + rationale",
        "",
        "⚠ **Stage 1 proposes nothing.** It judges the settings the brief "
        "already carries; choosing among them is synthesis, and synthesis is "
        "stage 2. What the lenses were judged on is in `plan.yaml`'s "
        "`acquisition` block, and every number there came from the brief with "
        "its source attached — none of it was originated here (rule 2).",
        "",
    ]
    out += _handoffs()
    out += [
        "",
        "## Committee verdict",
        "",
    ]
    out += _committee_table(result)
    out += ["", *_not_evaluated(result)]

    if result.stopped_after:
        out += [
            "",
            f"⛔ **Stopped after {result.stopped_after}.** {result.stop_reason} "
            "Every lens below that point is `unevaluated`, which is a hole and "
            "not a pass.",
        ]

    out += [
        "",
        "## Preconditions",
        "",
        "⚠ **This section is empty because nobody has written it, which is "
        "not the same as nothing to check.** Stage 1 emits no preconditions: "
        "each one is confirmed by something *observed*, and this runner "
        "observes nothing. Copy the blocks from "
        "[`kb/plans/_template.md`](_template.md) — the ~thirty instrument "
        "settings no check reads live there, and the plan interpreter leaves "
        "every one of them at its current value, **so if it is not written "
        "here, nobody sets it**.",
        "",
        "- [ ] …  — *checked by:* …",
        "",
        "## Sequence",
        "",
        "⚠ **No steps. Stage 1 judges a configuration; it does not sequence a "
        "run.** [SAFETY §8](../../SAFETY.md) is the standing setup order and "
        "is not repeated here. Every row added below confirms on something "
        "*observed* — a return code is not a confirmation (SAFETY §0, E9), "
        "and `plan-check` refuses one that is.",
        "",
        "| # | Subsystem | Action | Flag required | Confirmed by |",
        "|---:|---|---|---|---|",
        "",
        "## Stop conditions",
        "",
        "⚠ **Not written by stage 1**, and it cannot be: a stop condition "
        "names the state an abort leaves the instrument in, and that is a "
        "fact about the devices this runner never touches.",
        "",
        "- …",
        "",
    ]
    return "\n".join(out)


# --------------------------------------------------------------------------
# writing both
# --------------------------------------------------------------------------


def write(result: Result, identity: Identity, out_dir: Path) -> tuple[Path, Path]:
    """Both halves, same slug. Returns `(md, yaml)` in that order.

    Refuses to overwrite, on the same grounds as
    `config/micromanager/set_pixel_size.py`: a plan is written *before* a run
    and may already have been read by a person or acted on by a skill, so
    replacing one is a decision and never a side effect.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{identity.id}.md"
    yaml_path = out_dir / f"{identity.id}.yaml"

    existing = [p for p in (md_path, yaml_path) if p.exists()]
    if existing:
        raise FileExistsError(
            f"{', '.join(str(p) for p in existing)} already exists. A plan is "
            "written before a run and may already have been read -- replacing "
            "one is a decision, so delete it or choose another id."
        )

    md_path.write_text(plan_md(result, identity), encoding="utf-8")
    yaml_path.write_text(
        yaml.safe_dump(plan_yaml(result, identity), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return md_path, yaml_path
