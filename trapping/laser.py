"""Software laser-power dial (0-100%) -> incident power per trap.

Two facts turn this from a placeholder into a real number, and neither is
known yet (see docs/02-knowledge-base.md "Pending": "Optical tweezers power
measurement"):

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


#: The trap laser's MEASURED dial% -> power-at-the-sample curve, in watts.
#:
#: SOURCE: **kb/calibrations/illumination-power.yaml**, the `optical_tweezers`
#: row (`sheet_line: 1064`, `path: all_in`, `by_level_20x`). Measured by KH
#: 2026-09-09 at the sample plane through the **20x** objective with a
#: PM100A + S121C head. That file is the record; this is a transcription, and
#: it is the only place in this package carrying these numbers.
#:
#: Three limits, all from that file and all worth knowing before using this:
#:
#: 1. **It stops at 80 %.** 100 % over-ranged the meter, so that file's
#:    `at_100pct_extrapolated_mw: 1275` is `assumed`, and it is deliberately
#:    NOT included here -- `power_at` refuses to extrapolate past the highest
#:    measured point, which is exactly the wanted behaviour.
#: 2. **It is the 20x.** Every 1064 figure for another objective is an
#:    estimate off a vendor transmittance plot read by eye, and those plots
#:    stop at 1000 nm; the 100x Oil estimate is ~0.95 of the 20x. That file's
#:    `at_20pct_RETRACTED` row records what a 1064 reading at another
#:    objective cost last time it was attempted.
#: 3. **The absolute scale is the least reliable number in that file** -- the
#:    S121C is silicon and 1064 nm sits near its band edge. What is *not*
#:    affected is the linearity, because a single scale factor cancels: that
#:    file records 1.00 / 0.99 / 0.99 / 0.99 over 5-80 %.
MEASURED_1064_20X_W: dict[float, float] = {
    0.0: 0.0,
    5.0: 0.064,
    10.0: 0.126,
    30.0: 0.380,
    50.0: 0.633,
    80.0: 1.020,
}


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
    each trap's stiffness (see docs/05-consensus-gate.md lens 7:
    "Power splitting for multiple traps"). Returns a list of length
    ``n_traps``; with no ``weights`` it
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
