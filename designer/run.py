"""Running the committee in CLAUDE.md §2's order.

One thing this module found by trying to obey §2 literally, recorded here
because the code is the evidence: **tier 1 is not parallel.** §2 draws
`1 · 2 · 3` as one block, but L3.2 is judged against lens 2's
`fps_usable_max` and refuses by name without it (`compute/checks.py`), so
lens 3 cannot start until lens 2 has finished. The tier has an edge inside
it. That is the same shape as E2 -- a lens drawn beside its own input -- and
it is reported in the plan rather than silently reordered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import build as _build
from .brief import Brief, Gap
from .roster import Seat, convene, order

#: Inside tier 1, who must finish before whom, and why. Empty for every pair
#: not listed -- those really are parallel.
INTRA_TIER = {("detection", "compute"): "L3.2 is judged against lens 2's fps_usable_max"}

#: Handoffs that cross a tier boundary. The tiers already sequence these, so
#: unlike INTRA_TIER this table changes no order -- it records WHAT is carried,
#: which is the part that was invisible. A lens not listed here receives
#: nothing but the brief.
CROSS_TIER = {
    ("detection", "sample"): "L4.6's particle count needs the field, which is "
    "lens 2's ROI times lens 2's pixel",
    ("sample", "validity"): "L6.5 counts the particles L4.6 and L4.8 bound",
    ("detection", "validity"): "L6.5 needs the decided rate to turn a "
    "correlation time into a correlation length in frames",
    ("velocity", "validity"): "L6.5's correlation time is lens 7's tau = "
    "gamma/kappa, which lens 9 already computes",
}


@dataclass
class LensRun:
    lens: str
    verdict: Any | None = None
    #: The Setup the gate was called on. Kept because a later lens sometimes
    #: needs a number this one computed -- see CROSS_TIER.
    setup: Any | None = None
    not_constructible: _build.NotConstructible | None = None
    seat: Seat | None = None

    @property
    def ran(self) -> bool:
        return self.verdict is not None


@dataclass
class Result:
    brief: Brief
    seats: dict[str, Seat]
    runs: dict[str, LensRun] = field(default_factory=dict)
    stopped_after: str | None = None
    stop_reason: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def unevaluated(self) -> list[dict]:
        """Every lens that produced no verdict, and why. Never silent (§3)."""
        out = []
        for lens, seat in self.seats.items():
            run = self.runs.get(lens)
            if run is not None and run.ran:
                continue
            if run is not None and run.not_constructible is not None:
                nc = run.not_constructible
                out.append({
                    "lens": lens, "state": "not_constructible",
                    "missing": list(nc.missing), "why": nc.why,
                })
            else:
                out.append({"lens": lens, "state": seat.state, "why": seat.why})
        return out

    @property
    def unresolved(self) -> list[dict]:
        """The brief's own gaps, plus anything a gate asked for that it did not
        predict. The second list is a direct measure of the brief's quality."""
        out = [
            {"field": g.field, "rank": g.rank, "consumed_by": list(g.consumed_by),
             "action": g.action}
            for g in self.brief.gaps
        ]
        for lens, run in self.runs.items():
            if not run.ran:
                continue
            for f in run.verdict.findings:
                if f.code.startswith("missing."):
                    out.append({
                        "field": f.code, "rank": "unranked", "lens": lens,
                        "action": getattr(f, "action", None),
                        "note": "emitted by the gate and NOT predicted by the brief"
                        if not _brief_predicted(self.brief, f.code) else None,
                    })
        return out


def _brief_predicted(brief: Brief, code: str) -> bool:
    tail = code.split(".", 1)[-1]
    return any(tail in g.field or g.field in tail for g in brief.gaps)


def _hard_failures(verdict) -> list:
    """Level 1 of §2's precedence: a `hard` gate at m < 1 stops everything."""
    return [
        f for f in verdict.findings
        if getattr(f, "kind", None) == "hard" and f.severity == "fail"
    ]


def run(brief: Brief) -> Result:
    seats = convene(brief)
    tiers = order(seats)
    result = Result(brief=brief, seats=seats)

    for lens in seats:
        result.runs[lens] = LensRun(lens=lens, seat=seats[lens])

    for index, tier in enumerate(tiers, start=1):
        for lens in _sequence(tier):
            if lens == "validity":
                built = _build.build_validity(
                    brief, upstream=_upstream(result), setups=_setups(result)
                )
            elif lens == "sample":
                built = _build.build_sample(brief, detection=_setup_of(result, "detection"))
            else:
                built = _build.BUILDERS[lens](brief)
            if isinstance(built, _build.NotConstructible):
                result.runs[lens].not_constructible = built
                continue
            result.runs[lens].setup = built
            result.runs[lens].verdict = _evaluate(lens, built)

        if index == 1:
            stop = _first_hard_failure(result, tier)
            if stop is not None:
                lens, finding = stop
                result.stopped_after = "tier 1"
                result.stop_reason = (
                    f"{lens} {finding.code}: a `hard` gate at m < 1 stops the "
                    "run and returns a revision (§2 precedence level 1)"
                )
                return result

    return result


def _sequence(tier: tuple[str, ...]) -> list[str]:
    """Order a tier so that every INTRA_TIER edge is respected."""
    seq = list(tier)
    for (first, second), _ in INTRA_TIER.items():
        if first in seq and second in seq and seq.index(first) > seq.index(second):
            seq.remove(first)
            seq.insert(seq.index(second), first)
    return seq


def _evaluate(lens: str, setup):
    import importlib

    gate = importlib.import_module(f"{lens}.gate")
    if lens == "optics":
        # Lens 1 judges a channel against its siblings, for crosstalk.
        channels = setup
        return gate.evaluate(channels[0], others=channels[1:])
    return gate.evaluate(setup)


def _setups(result: Result) -> dict:
    """Every Setup built so far, for a lens that needs another's numbers."""
    return {lens: run.setup for lens, run in result.runs.items() if run.setup is not None}


def _setup_of(result: Result, lens: str):
    """The Setup a lens ran on, or None if it never ran.

    None is the honest answer and the receiving builder has to handle it:
    lens 2 being unbuildable must not make lens 4 unbuildable too, it must
    make lens 4's field-dependent check say it did not evaluate.
    """
    run = result.runs.get(lens)
    return None if run is None else run.setup


def _upstream(result: Result) -> dict:
    return {
        lens: run.verdict
        for lens, run in result.runs.items()
        if run.ran and lens != "validity"
    }


def _first_hard_failure(result: Result, tier: tuple[str, ...]):
    for lens in tier:
        run = result.runs.get(lens)
        if run is None or not run.ran:
            continue
        fails = _hard_failures(run.verdict)
        if fails:
            return lens, fails[0]
    return None
