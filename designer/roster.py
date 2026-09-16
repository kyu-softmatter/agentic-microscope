"""Who is convened, and -- the part that needed a third answer -- who cannot
be decided either way.

CLAUDE.md §2 E4 says a conditional lens that was not convened leaves a hole
and not a pass. That assumes convening is decidable. It is not always: lens 8
convenes past ~30 minutes, and if the brief does not carry a duration then
the lens is neither convened nor absent, and **recording it as absent would
be a guess with the same shape as the one E4 exists to stop**.

So a lens is `convened`, `absent` (with a reason that is a fact), or
`undecided` (with the input that would settle it). `undecided` is the new one,
and it came out of running the first real brief -- nothing in the design
predicted it.
"""

from __future__ import annotations

from dataclasses import dataclass

from stability.setup import CONVENE_DURATION_MIN

from .brief import Brief

#: CLAUDE.md §2. Tier 1 is code and runs first so that no later lens
#: deliberates over a physically impossible proposal; tier 3 reviews tiers 1
#: and 2, which is why it is alone (E2).
TIER_1 = ("optics", "detection", "compute", "trapping", "velocity")
TIER_2 = ("sample", "photo", "stability")
TIER_3 = ("validity",)

#: The six that always sit, and the three convened on a condition (01 §4).
STANDING = ("optics", "detection", "compute", "sample", "photo", "validity")
CONDITIONAL = ("trapping", "stability", "velocity")

#: Past this, lens 8 is convened (01 §4).
#:
#: IMPORTED, NOT RESTATED. It was a second `30.0` here until 2026-09-14, and
#: the two copies had already drifted in the way a duplicated constant always
#: does first -- not in value but in the comparison around it: `StabilitySetup
#: .convenes` is `> 30`, and this module was `>= 30`, so a 30-minute
#: acquisition convened lens 8 here and did not convene it there. One
#: definition, one file (CLAUDE.md §7).
STABILITY_THRESHOLD_MIN = CONVENE_DURATION_MIN


@dataclass(frozen=True)
class Seat:
    lens: str
    state: str  # convened | absent | undecided
    why: str
    #: For an `undecided` seat: the brief field that would settle it.
    #:
    #: Carried rather than re-derived. `designer/questions.py` first recovered
    #: it by string-matching this `why` sentence and got it wrong -- the field
    #: is `acquisition_duration_s` and the prose says "no acquisition
    #: duration", so no substitution of underscores for spaces reaches it.
    #: `convene` below already knows which gap it consulted, so it says so.
    decided_by: str | None = None

    @property
    def runs(self) -> bool:
        return self.state == "convened"


def convene(brief: Brief) -> dict[str, Seat]:
    """Decide the roster from the brief, and never from a default."""
    seats: dict[str, Seat] = {
        lens: Seat(lens, "convened", "standing lens (01 §4)") for lens in STANDING
    }

    # --- lens 7, the trap -------------------------------------------------
    trapped = brief.value("lens_4_sample.probe.trapped")
    if trapped is None:
        trapped = "lens_7_trapping" in brief.facts or None
    if trapped:
        seats["trapping"] = Seat("trapping", "convened", "the probe is trapped")
    elif trapped is None:
        seats["trapping"] = Seat(
            "trapping", "undecided",
            "the brief does not say whether anything is trapped",
            decided_by="lens_4_sample.probe.trapped",
        )
    else:
        seats["trapping"] = Seat("trapping", "absent", "nothing is trapped")

    # --- lens 9, commanded motion ----------------------------------------
    v = brief.value("lens_9_velocity.commanded_velocity_um_per_s")
    if v is not None:
        seats["velocity"] = Seat("velocity", "convened", f"a motion is commanded ({v} um/s)")
    else:
        seats["velocity"] = Seat("velocity", "absent", "nothing commands a motion")

    # --- lens 8, duration -------------------------------------------------
    # The case the design did not have an answer for. `acquisition_duration_s`
    # is R1 in the first real brief, so this is not hypothetical.
    minutes = brief.value("environment.acquisition_duration_s")
    if minutes is None:
        gap = brief.gap("acquisition_duration_s")
        seats["stability"] = Seat(
            "stability",
            "undecided",
            "no acquisition duration, so the ~30 min threshold cannot be applied"
            + (f" -- {gap.rank}, the operator's to answer" if gap else ""),
            decided_by="acquisition_duration_s",
        )
    elif float(minutes) / 60.0 > STABILITY_THRESHOLD_MIN:
        seats["stability"] = Seat(
            "stability", "convened",
            f"{float(minutes) / 60:.0f} min > {STABILITY_THRESHOLD_MIN:.0f}",
        )
    else:
        seats["stability"] = Seat(
            "stability", "absent",
            f"{float(minutes) / 60:.0f} min <= {STABILITY_THRESHOLD_MIN:.0f}",
        )

    return seats


def order(seats: dict[str, Seat]) -> tuple[tuple[str, ...], ...]:
    """The three tiers, filtered to who actually runs.

    An `undecided` lens does NOT run. It is not skipped either -- the caller
    carries it into the plan's `unevaluated` block with its reason, which is
    the whole point of distinguishing it from `absent`.
    """
    return tuple(
        tuple(lens for lens in tier if seats[lens].runs)
        for tier in (TIER_1, TIER_2, TIER_3)
    )
