"""Software laser-power dial (0-100%) -> incident power per trap.

Two facts turn this from a placeholder into a real number, and neither is
known yet (see docs/02-knowledge-base.md "수령 예정": "광집게 출력 실측"):

1. dial% -> watts at the sample / objective back-aperture -- a calibration
   curve that has to be measured with a power meter at a handful of dial
   settings. Until then, ``LaserCalibration`` falls back to a flat linear
   placeholder and marks itself ``measured=False``, matching the
   ``evidence: measured|assumed`` split used by ``optics.gate.Verdict`` --
   a force number computed from an unmeasured calibration is triage, not a
   trap-stiffness verdict.
2. how a holographic pattern actually splits power across N simultaneous
   traps. The default here is an ideal equal split (P/N); real SLM/DOE
   diffraction efficiency is rarely perfectly uniform across orders, so pass
   measured ``weights`` once you have them.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LaserCalibration:
    """Maps a 0-100% software dial setting to incident power in watts.

    ``points`` are measured (dial_percent -> watts) pairs; when given,
    ``power_at`` linearly interpolates between them and ``measured`` is True.
    Without measured points, ``power_at`` falls back to a straight line from
    0 to ``placeholder_max_w`` at dial=100% -- a stand-in, not a
    measurement, so ``measured`` stays False.
    """

    placeholder_max_w: float = 1.0
    points: dict[float, float] = field(default_factory=dict)

    @property
    def measured(self) -> bool:
        return bool(self.points)

    def power_at(self, dial_percent: float) -> float:
        if not 0.0 <= dial_percent <= 100.0:
            raise ValueError(f"dial_percent must be in [0, 100], got {dial_percent}")

        if not self.points:
            return self.placeholder_max_w * dial_percent / 100.0

        xs = sorted(self.points)
        if dial_percent <= xs[0]:
            # Assume the response is linear from (0, 0) to the lowest
            # measured point -- do not extrapolate past what was measured.
            return self.points[xs[0]] * (dial_percent / xs[0]) if xs[0] > 0 else self.points[xs[0]]
        if dial_percent >= xs[-1]:
            if dial_percent > xs[-1]:
                raise ValueError(
                    f"dial_percent={dial_percent} exceeds the highest calibrated "
                    f"point ({xs[-1]}%); extrapolating past measured data would "
                    "be a guess, not a calibration."
                )
            return self.points[xs[-1]]
        for lo, hi in zip(xs, xs[1:]):
            if lo <= dial_percent <= hi:
                t = (dial_percent - lo) / (hi - lo)
                return self.points[lo] + t * (self.points[hi] - self.points[lo])
        raise AssertionError("unreachable: xs is sorted and covers dial_percent")


def power_per_trap(
    calibration: LaserCalibration,
    dial_percent: float,
    n_traps: int,
    *,
    weights: list[float] | None = None,
) -> list[float]:
    """Power reaching each of ``n_traps`` simultaneous traps, in watts.

    Splitting the beam into N traps divides the power among them -- this is
    not optional bookkeeping, it is the dominant effect of adding traps on
    each trap's stiffness (see docs/05-consensus-gate.md lens 7: "다중 덫이면
    출력 분배"). Returns a list of length ``n_traps``; with no ``weights`` it
    is an ideal equal split, ``[P(dial)/N] * N``.

    ``weights`` are per-trap fractions of the total (e.g. measured per-order
    diffraction efficiencies); they need not sum to 1 if some power is lost
    to the zero order or elsewhere, but each must be in [0, 1].
    """
    if n_traps < 1:
        raise ValueError(f"n_traps must be >= 1, got {n_traps}")
    total = calibration.power_at(dial_percent)

    if weights is None:
        return [total / n_traps] * n_traps

    if len(weights) != n_traps:
        raise ValueError(
            f"weights has {len(weights)} entries but n_traps={n_traps}"
        )
    if any(not 0.0 <= w <= 1.0 for w in weights):
        raise ValueError("each weight must be a fraction in [0, 1]")
    return [total * w for w in weights]
