"""The Stokes-drag slope fit, and the per-rung scatter it returns.

Precondition P7 of
[`kb/plans/2026-09-15-drag-calibration-stiffness-vs-size.md`](../kb/plans/2026-09-15-drag-calibration-stiffness-vs-size.md)
asks for one number: **the relative scatter on `gamma` per rung**, because the
simulation side put the ladder fit's tolerance at 4.48 % and nobody here has
measured what this instrument delivers. The whole plan's viability turns on
which side of that the answer falls.

**This module goes to the data rather than the other way round** (KH,
2026-09-16: expand P7 in the plan itself, and build it so a plan can be produced
on another computer too -- read the value from the file where it lives, then
store it in `kb`). It needs numpy and nothing else -- no Micro-Manager,
no MATLAB, no instrument -- so a clone plus `requirements.txt` runs it wherever
the tracked positions already are, and what comes back into version control is
the result with its provenance rather than a second copy of the raw data.

**What it does not do.** It does not read the existing analysis output.
`creepx` detrends the mean displacement away by design, and the mean
displacement *is* the measurand here, so what this needs is the tracked
positions **before** that step. Identifying that file is the one prerequisite
this code cannot supply.

## Before the contract: what is actually on disk

**The tracked positions do not arrive in this shape**, and the gap is the point
rather than an inconvenience. Per
[`analysis/matlab/README.md`](../analysis/matlab/README.md) the position files
are **plain text, two columns `x y` in pixels, one row per frame** -- the speed
is in the filename
(`<tag>_creepx_<speed>umps_<power>_OT<otfactor>_<rep>_5um.txt`) and **there is
no time column at all.**

So a preparation step exists, and it carries exactly the quantity that README
warns about: `frame_time` is hardcoded at `0.02` s in every MATLAB file and
never read from metadata, while on this instrument the achieved period equals
the exposure -- so an acquisition at any other exposure silently puts every
frequency axis and every diffusivity out by the ratio. Its own instruction is
to take the period **from the timestamp column, not from the setting** (G12b: a
requested rate is not evidence).

`python -m calibration.cli drag-prepare` is that step. It refuses a filename it
cannot parse rather than skipping it silently, and it requires the frame period
*and a stated source for it* -- because the one number the preparation has to
supply is the one nobody can recover afterwards.

## The input contract

A delimited text file with a header line, comma or tab separated. Refused --
never guessed -- when a required column is absent, because a guessed column is
a silent factor of something.

| column | meaning |
|---|---|
| `t_s` | time, seconds |
| `x_px` **or** `x_um` | bead position along the drive axis. `x_px` needs `--pixel-size-um` |
| `v_um_s` | the **commanded** stage velocity for the row's segment. A requested rate is not evidence (G12b), so this is the drive setting and the achieved rate is checked separately |
| `segment` | integer id. Segments at one velocity are the repeats whose spread is the answer |
| `rung` *(optional)* | integer or height id. Absent means one rung |

## What it returns, and what each number is for

- `slope` -- of `x_eq` against `v`, per rung. This is `gamma/alpha`, and it is
  the primary route.
- `intercept` -- diagnostic, not a result. Physically `x_eq(0) = 0`, so a
  non-zero intercept is the trap-centre estimate being off, and it biases
  `alpha` if it is ignored.
- `sigma_gamma_rel` -- **the number P7 exists for.** The relative spread of the
  per-segment `x_eq/v` within a rung. Dimensionless, so a common multiplicative
  constant cancels out of it exactly: the 0.73 % `px_to_um` disagreement with
  `D:\\codes` contributes identically zero here, which is why this can be run
  with either pixel size.
- `alpha_equipartition` -- `kT/var(x)` on the plateau residuals, the independent
  cross-check. **Requires a measured temperature** and is `BLOCKED` without one,
  naming P3, rather than defaulting to 293.15 K.
  ⚠ **It is reported uncorrected for localisation noise, and that is not a
  detail.** Whatever `epsilon` the tracker contributes adds in quadrature to
  the thermal spread, inflating `var` and deflating this `alpha` by the same
  fraction -- about 8 % at the assumed 10 nm. Precondition P8 measures
  `epsilon` on a coverslip-stuck bead so `var(x)` can be corrected by
  `epsilon^2`; until it is, this number is a lower bound on the stiffness and
  not an estimate of it. Subtracting an *assumed* `epsilon` here would hide
  that, so it is left in and said instead.

**Where this runs is incidental** (KH, 2026-09-16, refining the above):
producing a plan does not require being on site, so the machine and path are
recorded as *provenance* rather than as a precondition. It runs the same on a copied file as on one in
place -- which is why the tool takes a path and knows nothing about a
microscope.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

#: Boltzmann constant in the units this repository states stiffness in.
#: pN*um/K -- 1.380649e-23 J/K = 1.380649e-23 * 1e12 pN * 1e6 um / K.
K_B_PN_UM_PER_K = 1.380649e-5

#: Columns the fit cannot proceed without. `x` is either unit and is handled
#: separately.
REQUIRED = ("t_s", "v_um_s", "segment")

#: How much of each segment to drop before the plateau. A bead released into a
#: new drive velocity approaches its offset exponentially with `tau_k`, so the
#: transient has to go -- the plan discards `3.5/(2*pi*f_c)`, 56 ms at
#: a = 4.95 um. **Not defaulted**: it is a physical number and the caller
#: supplies it, because it depends on the trap and the bead.
SETTLE_S_REQUIRED = "settle_s"


@dataclass
class RungFit:
    """One rung's fit, and the scatter that is the point of it."""

    rung: str
    n_segments: int
    velocities_um_s: list[float]
    x_eq_um: list[float]
    slope_s: float
    intercept_um: float
    sigma_gamma_rel: float | None
    alpha_equipartition_pn_um: float | None
    blocked: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        out = {
            "rung": self.rung,
            "n_segments": self.n_segments,
            "velocities_um_s": [round(v, 6) for v in self.velocities_um_s],
            "x_eq_um": [round(x, 6) for x in self.x_eq_um],
            "slope_s": self.slope_s,
            "intercept_um": self.intercept_um,
            "sigma_gamma_rel_percent": (
                None if self.sigma_gamma_rel is None else 100.0 * self.sigma_gamma_rel
            ),
            "alpha_equipartition_pn_um": self.alpha_equipartition_pn_um,
        }
        if self.blocked:
            out["blocked"] = list(self.blocked)
        return out


def _split(line: str) -> list[str]:
    return [cell.strip() for cell in (line.split("\t") if "\t" in line else line.split(","))]


def read_positions(path: Path) -> dict[str, np.ndarray]:
    """Parse the input contract, or refuse and say which column is missing."""
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not lines:
        raise ValueError(f"{path} has no data rows")

    header = _split(lines[0])
    columns: dict[str, list[str]] = {name: [] for name in header}
    for n, line in enumerate(lines[1:], start=2):
        cells = _split(line)
        if len(cells) != len(header):
            raise ValueError(
                f"{path}:{n} has {len(cells)} fields against {len(header)} in the "
                "header. Refusing rather than padding -- a shifted row moves every "
                "column after it"
            )
        for name, cell in zip(header, cells):
            columns[name].append(cell)

    missing = [name for name in REQUIRED if name not in columns]
    if "x_px" not in columns and "x_um" not in columns:
        missing.append("x_px or x_um")
    if missing:
        raise ValueError(
            f"{path} is missing {', '.join(missing)}. Present: {', '.join(header)}. "
            "Refusing rather than guessing -- see the input contract in "
            "calibration/drag_slope.py"
        )

    out: dict[str, np.ndarray] = {}
    for name, cells in columns.items():
        try:
            out[name] = np.asarray([float(cell) for cell in cells])
        except ValueError:
            out[name] = np.asarray(cells, dtype=object)
    return out


def plateau_mask(t_s: np.ndarray, segment: np.ndarray, settle_s: float) -> np.ndarray:
    """True where a sample is past its segment's transient.

    The mask is per segment rather than global: segments are not the same
    length, and a fixed sample count would discard a different amount of
    physics from each.
    """
    keep = np.zeros(t_s.shape, dtype=bool)
    for value in np.unique(segment):
        rows = segment == value
        keep[rows] = t_s[rows] >= (t_s[rows].min() + settle_s)
    return keep


def fit_rung(
    t_s: np.ndarray,
    x_um: np.ndarray,
    v_um_s: np.ndarray,
    segment: np.ndarray,
    settle_s: float,
    rung: str = "0",
    temperature_c: float | None = None,
) -> RungFit:
    """One rung: per-segment plateaus, the slope through them, and the scatter."""
    keep = plateau_mask(t_s, segment, settle_s)
    if not keep.any():
        raise ValueError(
            f"rung {rung}: settle_s = {settle_s} s discards every sample. "
            "Either the segments are shorter than the transient or the times are "
            "not in seconds"
        )

    per_segment_v: list[float] = []
    per_segment_x: list[float] = []
    residuals: list[np.ndarray] = []
    for value in np.unique(segment):
        rows = (segment == value) & keep
        if not rows.any():
            continue
        v = float(np.unique(v_um_s[rows])[0])
        block = x_um[rows]
        per_segment_v.append(v)
        per_segment_x.append(float(block.mean()))
        residuals.append(block - block.mean())

    v_arr = np.asarray(per_segment_v)
    x_arr = np.asarray(per_segment_x)

    design = np.vstack([v_arr, np.ones_like(v_arr)]).T
    (slope, intercept), *_ = np.linalg.lstsq(design, x_arr, rcond=None)

    #: gamma/alpha per segment, from that segment alone. Its spread is P7's
    #: answer: it is what a single rung's gamma would scatter by. Segments at
    #: v = 0 carry no information about the ratio and are excluded rather than
    #: dividing by zero.
    moving = v_arr != 0
    ratios = (x_arr[moving] - intercept) / v_arr[moving]
    sigma = None
    if ratios.size > 1 and abs(ratios.mean()) > 0:
        sigma = float(ratios.std(ddof=1) / abs(ratios.mean()))

    blocked: list[str] = []
    alpha = None
    if temperature_c is None:
        blocked.append(
            "alpha_equipartition: no measured temperature. Precondition P3 of the "
            "plan blocks on a thermometer at the sample; kT is not defaulted to "
            "293.15 K here, because a cross-check computed from an assumed "
            "temperature is not independent of the assumption"
        )
    else:
        var = float(np.concatenate(residuals).var(ddof=1))
        if var > 0:
            alpha = K_B_PN_UM_PER_K * (temperature_c + 273.15) / var

    return RungFit(
        rung=rung,
        n_segments=int(len(per_segment_v)),
        velocities_um_s=per_segment_v,
        x_eq_um=per_segment_x,
        slope_s=float(slope),
        intercept_um=float(intercept),
        sigma_gamma_rel=sigma,
        alpha_equipartition_pn_um=alpha,
        blocked=blocked,
    )


def fit_file(
    path: Path,
    settle_s: float,
    pixel_size_um: float | None = None,
    temperature_c: float | None = None,
) -> list[RungFit]:
    """Every rung in a tracked-positions file."""
    data = read_positions(path)

    if "x_um" in data:
        x_um = data["x_um"]
    else:
        if pixel_size_um is None:
            raise ValueError(
                "the file gives x in px and no --pixel-size-um was supplied. "
                "Refusing rather than assuming 0.06453: the scatter this produces "
                "is dimensionless and unaffected, but the slope and the "
                "equipartition alpha are not"
            )
        x_um = data["x_px"] * pixel_size_um

    rungs = data.get("rung")
    if rungs is None:
        rungs = np.zeros(x_um.shape)

    out: list[RungFit] = []
    for value in np.unique(rungs):
        rows = rungs == value
        out.append(
            fit_rung(
                data["t_s"][rows],
                x_um[rows],
                data["v_um_s"][rows],
                data["segment"][rows],
                settle_s=settle_s,
                rung=str(value),
                temperature_c=temperature_c,
            )
        )
    return out


def sha256_prefix(path: Path, chars: int = 16) -> str:
    """The input's hash, so a number that decides an experiment is resolvable.

    Truncated to the same 16 hex the bridge's manifest uses, so the two records
    can be compared without a format argument.
    """
    import hashlib

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{digest[:chars]}"


def as_calibration_entry(
    path: Path,
    fits: list[RungFit],
    settle_s: float,
    pixel_size_um: float | None,
    temperature_c: float | None,
    date: str,
    machine: str,
) -> dict:
    """The `kb/calibrations/` record, in the shape `camera-readout.yaml` set.

    `evidence_class: measured` -- this is this instrument, which is what makes
    it admissible as a gate threshold where a `kb/external/` entry is not.
    `verified: false` until a person says otherwise: `confirmed_by` is human
    only, here as in the bridge protocol.
    """
    scatters = [
        fit.sigma_gamma_rel for fit in fits if fit.sigma_gamma_rel is not None
    ]
    return {
        "measurand": "sigma_gamma_rel -- relative scatter on gamma per rung, from the drag slope",
        "why": (
            "Precondition P7. The ladder fit tolerates 4.48 % per rung "
            "(kb/external/bd/trap-stiffness-recovery.r8.md, simulated, not a "
            "threshold), and no measurement of what this instrument delivers "
            "existed. This entry is that measurement."
        ),
        "source_file": str(path),
        "source_hash": sha256_prefix(path),
        "machine": machine,
        "settle_s": settle_s,
        "pixel_size_um": pixel_size_um,
        "temperature_c": temperature_c,
        "date": date,
        "measured_by": "agent (Claude Code), from tracked positions -- not from a live instrument",
        "evidence_class": "measured",
        "verified": False,
        "rungs": [fit.to_dict() for fit in fits],
        "sigma_gamma_rel_percent_max": (
            None if not scatters else 100.0 * max(scatters)
        ),
        "note": (
            "The scatter is dimensionless, so a common multiplicative constant "
            "cancels out of it exactly -- the 0.73 % px_to_um disagreement with "
            "D:\\codes contributes identically zero to this number. It does reach "
            "the slope (-0.72 %) and the equipartition alpha (-1.44 %, since var "
            "scales as px^2). Derived in the plan's Analysis section, not imported."
        ),
    }


def summarise(fits: list[RungFit]) -> str:
    """One line per rung, for a person reading the terminal."""
    lines = [
        f"{'rung':>8}  {'n':>3}  {'slope [s]':>12}  {'intercept [um]':>15}  "
        f"{'sigma_gamma':>12}  {'alpha_eq [pN/um]':>17}"
    ]
    for fit in fits:
        sigma = (
            "blocked" if fit.sigma_gamma_rel is None else f"{100 * fit.sigma_gamma_rel:.2f} %"
        )
        alpha = (
            "BLOCKED"
            if fit.alpha_equipartition_pn_um is None
            else f"{fit.alpha_equipartition_pn_um:.4g}"
        )
        lines.append(
            f"{fit.rung:>8}  {fit.n_segments:>3}  {fit.slope_s:>12.6g}  "
            f"{fit.intercept_um:>15.6g}  {sigma:>12}  {alpha:>17}"
        )
    worst = [f.sigma_gamma_rel for f in fits if f.sigma_gamma_rel is not None]
    if worst:
        value = 100 * max(worst)
        verdict = "under" if value <= 4.48 else "OVER"
        lines.append(
            f"\nworst rung: {value:.2f} % -- {verdict} the 4.48 % the ladder fit "
            "tolerates (simulated, r8; a target and not a gate threshold)"
        )
    if any(fit.blocked for fit in fits):
        lines.append("")
        for fit in fits:
            for reason in fit.blocked:
                lines.append(f"BLOCKED rung {fit.rung}: {reason}")
    return "\n".join(lines)


#: The MATLAB parsers' own filename convention, and the reason this is strict:
#: their README says "a file that does not match is skipped, sometimes
#: silently", and a silently skipped velocity is a missing point in a slope fit.
_CREEPX = re.compile(r"_creepx_(?P<speed>[0-9.]+)umps_", re.IGNORECASE)
_PASSIVE = re.compile(r"_passive_", re.IGNORECASE)

#: The value `analysis/matlab/README.md` warns about: hardcoded in every MATLAB
#: file and never read from metadata. Equalling it is not an error -- the
#: standing exposure really is 20.0 ms -- so it earns a warning and not a
#: refusal.
HARDCODED_FRAME_PERIOD_MS = 20.0


def speed_from_filename(name: str) -> float:
    """The commanded stage speed, in um/s, from the MATLAB filename convention.

    `passive` means the trap was held with no drive, so the speed is zero --
    those files carry `var(x)` for the equipartition route and no slope point.
    Anything else is refused by name: a file silently skipped is a velocity
    missing from the fit, and the fit will not say so.
    """
    hit = _CREEPX.search(name)
    if hit:
        return float(hit.group("speed"))
    if _PASSIVE.search(name):
        return 0.0
    raise ValueError(
        f"{name!r} matches neither <tag>_creepx_<speed>umps_... nor "
        "<tag>_passive_... Refusing rather than skipping it: the MATLAB parsers "
        "skip a non-matching file 'sometimes silently' (analysis/matlab/README.md), "
        "and a skipped velocity is a missing point in a slope fit"
    )


def prepare_rows(
    paths: list[Path],
    frame_period_ms: float,
    rung: str = "0",
) -> list[str]:
    """Turn the two-column position files into the input contract.

    One segment per file, numbered in the order given. `t_s` is **constructed**
    from the frame period, which is why the caller has to say where that period
    came from -- this function cannot tell a measured period from a setting, and
    neither can anything downstream once the column exists.
    """
    out = ["t_s,x_px,v_um_s,segment,rung"]
    t = 0.0
    dt = frame_period_ms / 1000.0
    for segment, path in enumerate(paths):
        speed = speed_from_filename(path.name)
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            fields = stripped.replace(",", " ").split()
            try:
                x = float(fields[0])
            except (IndexError, ValueError):
                raise ValueError(
                    f"{path}:{n} does not start with a number. The contract for "
                    "these files is two columns `x y` in pixels, one row per "
                    "frame -- a header or a four-column two-bead file needs a "
                    "different reader, not a guess"
                ) from None
            if len(fields) < 2:
                raise ValueError(
                    f"{path}:{n} has one column; the position files are `x y`"
                )
            t += dt
            out.append(f"{t:.6f},{x:.6f},{speed},{segment},{rung}")
    return out


def faxen_gamma_pn_s_um(
    radius_um: float, height_um: float, viscosity_pa_s: float
) -> float:
    """`gamma = 6*pi*eta*a / (1 - 9a/(16h))`, in pN*s/um.

    Here only so a slope can be turned into an `alpha` without importing the
    trapping lens, which pulls in the gate machinery. It is the same first-order
    parallel correction `sample.aberration.wall_drag_suppression` reports, and
    it refuses `h <= a` the same way rather than returning a number.
    """
    if height_um <= radius_um:
        raise ValueError(
            f"h = {height_um} um is not above a = {radius_um} um; the 9a/(16h) "
            "expansion has no meaning there"
        )
    bulk = 6.0 * math.pi * viscosity_pa_s * (radius_um * 1e-6)  # N*s/m
    bulk_pn_s_um = bulk * 1e12 / 1e6
    return bulk_pn_s_um / (1.0 - 9.0 * radius_um / (16.0 * height_um))
