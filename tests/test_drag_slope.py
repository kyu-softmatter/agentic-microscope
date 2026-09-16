"""The Stokes-drag slope fit, and the one number precondition P7 exists for.

The ladder fit tolerates 4.48 % of per-rung scatter on `gamma`
(`kb/external/bd/trap-stiffness-recovery.r8.md` -- simulated, and therefore a
target rather than a gate threshold). Nobody had measured what this instrument
delivers, and the plan's whole viability turns on which side of that the answer
falls. This module is how that gets measured, and it runs **where the data
already is**: numpy only, no instrument, no Micro-Manager, no edit to the
analysis PC's own code.

Every test names the failure it stands for, and more of them are about refusals
than about results. That is the shape of the problem: what is on disk is **two
columns `x y` in pixels with no time column** and the speed in the filename
(`analysis/matlab/README.md`), so the time axis has to be *constructed* from a
frame period that the MATLAB scripts hardcode at 0.02 s and never read from
metadata. Every number that cannot be recovered afterwards is refused here
rather than defaulted.

The one thing this code still cannot supply is **which** file holds the tracked
positions *before* `creepx` detrends the mean displacement away.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from calibration.drag_slope import (
    HARDCODED_FRAME_PERIOD_MS,
    as_calibration_entry,
    fit_file,
    prepare_rows,
    read_positions,
    sha256_prefix,
    speed_from_filename,
)

#: gamma/alpha for the synthetic bead, in seconds. The slope the fit has to find.
SLOPE_S = 0.02

#: The plan's four velocity fractions of 23.0 um/s at the reference rung.
VELOCITIES = (5.75, 11.5, 17.25, 23.0)


def synthetic(
    path: Path,
    *,
    noise_um: float = 0.02,
    in_px: bool = False,
    pixel_size_um: float = 0.06453,
    seed: int = 7,
    n_per_segment: int = 500,
    fps: float = 520.0,
    tau_s: float = 0.016,
) -> Path:
    """A tracked-positions file with a known slope and an exponential transient.

    The transient is the point of `--settle-s`: a bead released into a new drive
    velocity approaches its offset with `tau_k`, and averaging that in would
    pull every `x_eq` toward zero by a different amount per segment.
    """
    rng = np.random.default_rng(seed)
    unit = "x_px" if in_px else "x_um"
    rows = [f"t_s,{unit},v_um_s,segment,rung"]
    t = 0.0
    segment = 0
    for v in VELOCITIES:
        for _ in range(3):
            x_eq = SLOPE_S * v
            for i in range(n_per_segment):
                t += 1.0 / fps
                x = x_eq * (1.0 - math.exp(-(i / fps) / tau_s)) + rng.normal(0, noise_um)
                rows.append(
                    f"{t:.6f},{x / pixel_size_um if in_px else x:.6f},{v},{segment},0"
                )
            segment += 1
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# the result
# --------------------------------------------------------------------------


def test_it_recovers_a_known_slope(tmp_path):
    (fit,) = fit_file(synthetic(tmp_path / "p.csv"), settle_s=0.056)
    assert fit.slope_s == pytest.approx(SLOPE_S, rel=0.02)
    assert fit.intercept_um == pytest.approx(0.0, abs=0.01)
    assert fit.n_segments == 12


def test_the_transient_is_what_settle_s_is_for(tmp_path):
    """Keeping it biases every x_eq toward zero, by a different amount per segment.

    So this is not a tidiness parameter: it is the difference between a slope
    and a slope that is wrong in a way no scatter reveals.
    """
    path = synthetic(tmp_path / "p.csv", noise_um=0.0)
    (kept,) = fit_file(path, settle_s=0.0)
    (dropped,) = fit_file(path, settle_s=0.056)
    assert kept.slope_s < dropped.slope_s
    assert dropped.slope_s == pytest.approx(SLOPE_S, rel=0.005)


def test_the_scatter_is_exactly_invariant_to_the_pixel_size(tmp_path):
    """The cancellation the plan's Analysis section derives, held as a test.

    `sigma(c*x)/mean(c*x) = sigma(x)/mean(x)`, so the 0.73 % disagreement
    between `D:\\codes`'s hardcoded 0.065 and the recorded 0.06453 contributes
    **identically zero** to the number that gets compared against 4.48 %. That
    is why this can be run with either value, and why the operator's ruling
    that it is not an error here holds for this quantity by arithmetic rather
    than by tolerance.
    """
    px = synthetic(tmp_path / "px.csv", in_px=True)

    (recorded,) = fit_file(px, settle_s=0.056, pixel_size_um=0.06453)
    (hardcoded,) = fit_file(px, settle_s=0.056, pixel_size_um=0.065)

    #: the same bytes, two pixel sizes: identical to floating point
    assert hardcoded.sigma_gamma_rel == pytest.approx(recorded.sigma_gamma_rel, rel=1e-12)
    #: and it does reach the slope, by exactly the 0.73 % the plan states
    assert hardcoded.slope_s / recorded.slope_s == pytest.approx(0.065 / 0.06453, rel=1e-9)

    #: ⚠ Against a file exported in um instead, the agreement is only ~1e-3 --
    #: and that is not the cancellation failing. It is the exported file's own
    #: rounding: six decimals in px is a different quantisation from six
    #: decimals in um. The cancellation is exact for one dataset read two ways;
    #: re-exporting is a second, non-cancelling effect, and confusing the two is
    #: what this comment exists to stop.
    (from_um,) = fit_file(synthetic(tmp_path / "um.csv"), settle_s=0.056)
    assert recorded.sigma_gamma_rel == pytest.approx(from_um.sigma_gamma_rel, rel=1e-3)


def test_more_noise_is_more_scatter(tmp_path):
    (quiet,) = fit_file(synthetic(tmp_path / "a.csv", noise_um=0.01), settle_s=0.056)
    (loud,) = fit_file(synthetic(tmp_path / "b.csv", noise_um=0.08), settle_s=0.056)
    assert loud.sigma_gamma_rel > quiet.sigma_gamma_rel


# --------------------------------------------------------------------------
# the refusals
# --------------------------------------------------------------------------


def test_a_missing_column_is_refused_and_named(tmp_path):
    path = tmp_path / "p.csv"
    path.write_text("t_s,x_um,segment\n0.1,0.2,0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="v_um_s"):
        fit_file(path, settle_s=0.0)


def test_a_ragged_row_is_refused_rather_than_padded(tmp_path):
    """A shifted row moves every column after it, silently."""
    path = tmp_path / "p.csv"
    path.write_text("t_s,x_um,v_um_s,segment\n0.1,0.2,5.0,0\n0.2,0.3,5.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="fields against"):
        fit_file(path, settle_s=0.0)


def test_pixels_without_a_pixel_size_are_refused(tmp_path):
    """Never originate a physical number -- not even one recorded elsewhere."""
    with pytest.raises(ValueError, match="pixel-size-um"):
        fit_file(synthetic(tmp_path / "p.csv", in_px=True), settle_s=0.056)


def test_a_settle_that_discards_everything_is_refused(tmp_path):
    with pytest.raises(ValueError, match="discards every sample"):
        fit_file(synthetic(tmp_path / "p.csv"), settle_s=60.0)


def test_the_equipartition_crosscheck_is_blocked_without_a_temperature(tmp_path):
    """P3 blocks on a thermometer, and BLOCKED is a valid result.

    Computing `kT/var(x)` from an assumed 293.15 K would produce a cross-check
    that is not independent of the assumption it is meant to test.
    """
    (fit,) = fit_file(synthetic(tmp_path / "p.csv"), settle_s=0.056)
    assert fit.alpha_equipartition_pn_um is None
    assert any("P3" in reason for reason in fit.blocked)


def test_the_equipartition_crosscheck_runs_with_a_measured_temperature(tmp_path):
    """`kT/var`: 0.02 um of spread is var = 4e-4 um^2, and kT(293.15 K) is
    4.048e-3 pN*um, so alpha comes out near 10.1 pN/um.

    ⚠ And that number is **not** this bead's trap stiffness. The synthetic
    spread here is pure measurement noise, so what `kT/var` returns is what the
    real measurement returns when `epsilon` is left in: var is inflated and
    alpha is deflated by the same fraction. Correcting `var(x)` by `epsilon^2`
    -- precondition P8 -- is not a refinement of this cross-check, it is the
    difference between it meaning something and not.
    """
    (fit,) = fit_file(synthetic(tmp_path / "p.csv"), settle_s=0.056, temperature_c=20.0)
    assert not fit.blocked
    assert fit.alpha_equipartition_pn_um == pytest.approx(10.1, rel=0.05)


# --------------------------------------------------------------------------
# the record it leaves
# --------------------------------------------------------------------------


def test_the_entry_hashes_its_input(tmp_path):
    """A number that decides an experiment's viability resolves to its bytes."""
    path = synthetic(tmp_path / "p.csv")
    fits = fit_file(path, settle_s=0.056)
    entry = as_calibration_entry(
        path, fits, settle_s=0.056, pixel_size_um=None, temperature_c=None,
        date="2026-09-16", machine="test",
    )
    assert entry["source_hash"] == sha256_prefix(path)
    assert entry["source_hash"].startswith("sha256:")


def test_the_entry_is_measured_and_unverified(tmp_path):
    """`measured` is what makes it admissible as a threshold where an import is not.

    And `verified: false` until a person reads it: `confirmed_by` is human-only
    here as in the bridge protocol, so no agent may sign this off.
    """
    path = synthetic(tmp_path / "p.csv")
    entry = as_calibration_entry(
        path, fit_file(path, settle_s=0.056), settle_s=0.056, pixel_size_um=None,
        temperature_c=None, date="2026-09-16", machine="test",
    )
    assert entry["evidence_class"] == "measured"
    assert entry["verified"] is False
    assert "4.48" in entry["why"]


def test_comments_and_blank_lines_are_skipped(tmp_path):
    path = tmp_path / "p.csv"
    path.write_text(
        "# exported from the tracker, 2026-09-03\n\nt_s,x_um,v_um_s,segment\n"
        "0.0,0.1,5.0,0\n0.1,0.11,5.0,0\n",
        encoding="utf-8",
    )
    data = read_positions(path)
    assert data["t_s"].size == 2


# --------------------------------------------------------------------------
# the step between disk and the contract
# --------------------------------------------------------------------------


def two_column(path: Path, speed: float, n: int = 500, seed: int = 3) -> Path:
    """What is actually on disk: two columns `x y` in pixels, no header, no time.

    Per `analysis/matlab/README.md`. The speed lives in the filename, which is
    why the name matters as much as the contents.
    """
    rng = np.random.default_rng(seed)
    x_eq_px = SLOPE_S * speed / 0.06453
    rows = []
    for i in range(n):
        settling = x_eq_px * (1.0 - math.exp(-(i / 520.0) / 0.016))
        rows.append(f"{settling + rng.normal(0, 0.3):.4f}  {rng.normal(0, 0.3):.4f}")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def test_the_speed_comes_from_the_filename(tmp_path):
    assert speed_from_filename("bead_creepx_17.25umps_80_OT1_1_5um.txt") == 17.25
    assert speed_from_filename("bead_passive_80_OT1_1_5um.txt") == 0.0


def test_an_unparseable_filename_is_refused_not_skipped(tmp_path):
    """The MATLAB parsers skip a non-matching file "sometimes silently".

    A skipped velocity is a missing point in a slope fit, and the fit does not
    announce that it fitted three points instead of four.
    """
    with pytest.raises(ValueError, match="Refusing rather than skipping"):
        speed_from_filename("bead_run3.txt")


def test_prepare_round_trips_into_the_fit(tmp_path):
    """Disk shape in, slope out -- the whole of P7 steps 2 and 3."""
    paths = [
        two_column(tmp_path / f"bead_creepx_{v}umps_80_OT1_1_5um.txt", v, seed=i)
        for i, v in enumerate(VELOCITIES)
    ]
    prepared = tmp_path / "prepared.csv"
    prepared.write_text(
        "\n".join(prepare_rows(paths, frame_period_ms=1.923)) + "\n", encoding="utf-8"
    )

    (fit,) = fit_file(prepared, settle_s=0.056, pixel_size_um=0.06453)
    assert fit.slope_s == pytest.approx(SLOPE_S, rel=0.02)
    assert fit.n_segments == len(VELOCITIES)


def test_a_two_bead_file_is_refused_rather_than_read_as_one(tmp_path):
    """Those files are four columns WITH a header -- a different reader, not a guess."""
    path = tmp_path / "bead_creepx_5.75umps_80_OT1_1_5um.txt"
    path.write_text("Left_x Left_y Right_x Right_y\n1.0 2.0 3.0 4.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not start with a number"):
        prepare_rows([path], frame_period_ms=1.923)


def test_a_single_column_row_is_refused(tmp_path):
    path = tmp_path / "bead_creepx_5.75umps_80_OT1_1_5um.txt"
    path.write_text("1.0 2.0\n3.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="one column"):
        prepare_rows([path], frame_period_ms=1.923)


def test_the_cli_refuses_a_blank_frame_period_source(tmp_path, capsys):
    """`t_s` is constructed, so its provenance is the one thing nothing recovers.

    The frame period is hardcoded at 0.02 s in every MATLAB file and never read
    from metadata (analysis/matlab/README.md), while the achieved period equals
    the exposure on this camera -- so a blank source is exactly the state in
    which a setting gets used as a measurement.
    """
    from calibration.cli import main

    path = two_column(tmp_path / "bead_creepx_5.75umps_80_OT1_1_5um.txt", 5.75)
    code = main(
        [
            "drag-prepare", str(path),
            "--frame-period-ms", "1.923",
            "--frame-period-source", "   ",
        ]
    )
    assert code == 1
    assert "cannot be told from one measured" in capsys.readouterr().err


def test_the_cli_warns_when_the_period_is_the_hardcoded_one(tmp_path, capsys):
    """20.0 ms is not an error -- the standing exposure is 20.0 ms -- so it warns."""
    from calibration.cli import main

    path = two_column(tmp_path / "bead_creepx_5.75umps_80_OT1_1_5um.txt", 5.75)
    code = main(
        [
            "drag-prepare", str(path),
            "--frame-period-ms", str(HARDCODED_FRAME_PERIOD_MS),
            "--frame-period-source", "the exposure setting",
            "--out", str(tmp_path / "out.csv"),
        ]
    )
    assert code == 0
    assert "G12b" in capsys.readouterr().err
