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
#:
#: ⚠ AN ORDER IS NOT A HANDOFF. This table said "L3.2 is judged against lens
#: 2's fps_usable_max" from the day it was written and nothing passed the
#: number, so lens 3 ran second and received nothing: L3.2 refused with
#: `missing.usable_fps_ceiling` on every brief, which reads from outside like
#: a gate waiting on a calibration rather than a wire that was never run
#: (2026-09-15, the fourth of these). The carry is `build_compute`'s
#: `detection=` argument. It is NOT in CROSS_TIER, which is for edges that
#: cross a tier boundary; this one is inside tier 1, which is why the order
#: alone looked sufficient.
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
    #: Lens 1 only, and it is not a convenience. `optics.gate.evaluate` judges
    #: ONE channel against its siblings, so a two-colour proposal used to be
    #: judged on channel 0 alone -- the second arm's whole light path went
    #: unexamined and reported as nothing at all, which reads as a pass. Each
    #: channel is now its own subject, keyed by name. `verdict` stays channel
    #: 0's so no ordering is invented over the rest.
    per_channel: dict[str, Any] = field(default_factory=dict)
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
            elif seat.runs:
                # CONVENED AND NEVER REACHED, which is a fourth state and not
                # `absent`. It printed the seat's reason for being convened --
                # "standing lens (01 §4)" -- as its reason for not running,
                # which reads as a lens that had nothing to say rather than
                # one the tier-1 stop cut off before it could speak.
                out.append({
                    "lens": lens, "state": "not_reached",
                    "why": self.stop_reason
                    or "convened, and the run ended before its tier",
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
             "action": g.action, "predicted_by_brief": True}
            for g in self.brief.gaps
        ]
        for lens, run in self.runs.items():
            if not run.ran:
                continue
            for verdict in (run.per_channel or {None: run.verdict}).values():
                for f in verdict.findings:
                    if not f.code.startswith("missing."):
                        continue
                    predicted = _brief_predicted(self.brief, f.code)
                    out.append({
                        "field": f.code, "rank": "unranked", "lens": lens,
                        "action": getattr(f, "action", None),
                        #: A boolean, because this is the measure the
                        #: planning-layer entry set for itself and a machine
                        #: reader counts it. The prose beside it is for the
                        #: person reading `plan.md`.
                        "predicted_by_brief": predicted,
                        "note": None if predicted else
                        "emitted by the gate and NOT predicted by the brief",
                    })
        return out


def _brief_predicted(brief: Brief, code: str) -> bool:
    """Did the brief know to ask for what this code asks for?

    An explicit `answers:` first, because it is the gap's own claim. The
    substring fallback is a heuristic and is kept only for the gaps that make
    no claim -- it is wrong in both directions, and the direction that matters
    is the false surprise: this count is reported as a measure of the brief's
    quality.
    """
    if any(code in g.answers for g in brief.gaps):
        return True
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
            elif lens == "compute":
                built = _build.build_compute(brief, detection=_setup_of(result, "detection"))
            else:
                built = _build.BUILDERS[lens](brief)
            if isinstance(built, _build.NotConstructible):
                result.runs[lens].not_constructible = built
                continue
            result.runs[lens].setup = built
            if lens == "optics":
                result.runs[lens].per_channel = _evaluate_channels(built)
                result.runs[lens].verdict = next(iter(result.runs[lens].per_channel.values()))
            else:
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

    return importlib.import_module(f"{lens}.gate").evaluate(setup)


def _evaluate_channels(channels) -> dict:
    """Lens 1, once per channel, each judged against its siblings.

    Crosstalk is why `evaluate` takes `others`: a channel is judged in the
    company it keeps. Judging only the first channel therefore does not even
    get the crosstalk right in one direction -- it asks whether channel 0
    leaks into the rest and never whether the rest leak into it.
    """
    from optics import gate

    return {
        channel.name: gate.evaluate(
            channel, others=[c for c in channels if c is not channel]
        )
        for channel in channels
    }


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
        #: Every channel, not only the one in `verdict`. A hard failure in the
        #: second arm of a two-colour proposal stops the run exactly as the
        #: first arm's does; it had no way to be seen.
        for verdict in (run.per_channel or {"": run.verdict}).values():
            fails = _hard_failures(verdict)
            if fails:
                return lens, fails[0]
    return None
