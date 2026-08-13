"""Statistical power: the one quantity lens 6 computes itself.

Pure functions, no gate logic -- mirrors compute/resources.py,
sample/aberration.py, photo/dose.py. docs/04-decision-engine.md §7.

Everything else in this lens reviews other lenses' verdicts rather than
calculating; this module is the exception.
"""

from __future__ import annotations

import math


def relative_error(n_particles: float, n_frames: float) -> float:
    """Relative error of an ensemble average, ``1/sqrt(N_p x N_f)``.

    docs/04 §7 gives this as the microrheology ensemble error and calls it
    "roughly", which it is. The assumptions worth stating:

    - particles are independent, so N_p x N_f counts independent samples. In a
      crowded or hydrodynamically coupled suspension they are not, and this is
      optimistic.
    - the whole movie contributes. For an MSD at a long lag only a fraction of
      the frames contribute to that lag, so the error at the longest lag is
      worse than this.

    Both caveats push the same way: real error >= this. It is a floor.
    """
    product = n_particles * n_frames
    if product <= 0:
        return float("inf")
    return 1.0 / math.sqrt(product)


def required_sample_product(target_relative_error: float) -> float:
    """``N_p x N_f`` needed to reach a target relative error. docs/04 §7's
    "back out the required N_particles x N_frames"."""
    if target_relative_error <= 0:
        raise ValueError("target_relative_error must be positive")
    return 1.0 / (target_relative_error**2)


def required_particles(target_relative_error: float, n_frames: float) -> float:
    """Particles needed in the field at a given frame count.

    The actionable form: it answers "how much must I dilute less" or "how much
    longer must the movie be", which a bare product does not.
    """
    if n_frames <= 0:
        raise ValueError("n_frames must be positive")
    return required_sample_product(target_relative_error) / n_frames


def required_frames(target_relative_error: float, n_particles: float) -> float:
    if n_particles <= 0:
        raise ValueError("n_particles must be positive")
    return required_sample_product(target_relative_error) / n_particles


def roi_speed_tradeoff(area_factor: float, frame_rate_gain: float) -> float:
    """Net statistical gain from shrinking the ROI. docs/04 §7.

    Shrinking the area by ``area_factor`` (0.25 for a quarter-area ROI) cuts
    the particle count by the same factor while buying ``frame_rate_gain`` in
    frames. Since the error goes as ``1/sqrt(N_p x N_f)``, the net factor on
    the sample product is simply the product of the two -- so quartering the
    area for 4x the frame rate is a **wash**, which is the trap docs/04 §7
    warns about. Returns the factor on ``N_p x N_f``: > 1 is a real gain.
    """
    return area_factor * frame_rate_gain
