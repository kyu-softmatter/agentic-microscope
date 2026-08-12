"""Spectral primitives.

Everything optical in this project reduces to multiplying spectra together and
integrating. A dye's excitation efficiency is
``∫ source(λ)·T_exfilter(λ)·R_dichroic(λ)·abs_dye(λ) dλ``; its detected signal is
``∫ em_dye(λ)·T_dichroic(λ)·T_emfilter(λ)·QE_cam(λ) dλ``. So one `Spectrum` type
on one fixed grid, and the rest is arithmetic.

Two ways to get a spectrum:

* **measured curve** - a vendor text file (Semrock/Chroma/FPbase export).
  Use this whenever it exists.
* **parametric band** - peak + FWHM. A convenience for triage only.

The parametric path is deliberately marked lower-confidence. Real dye spectra
are asymmetric with vibronic structure, and filter edges are far steeper than
any analytic band; a pass/fail decision on blocking or crosstalk taken from a
parametric approximation can easily be wrong by orders of magnitude.
See :attr:`Spectrum.measured`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Fixed 1 nm grid. Wide enough for NIR trapping lasers (1064 nm) so their
# leakage into the detection path can be checked too.
WL_MIN, WL_MAX, WL_STEP = 300.0, 1100.0, 1.0
GRID: np.ndarray = np.arange(WL_MIN, WL_MAX + WL_STEP, WL_STEP)

# Typical vibronic progression spacing, used by the parametric band shape.
_VIBRONIC_CM1 = 1300.0
_VIBRONIC_AMP = 0.28


def _nm_to_cm1(nm: np.ndarray | float) -> np.ndarray | float:
    return 1.0e7 / np.asarray(nm, dtype=float)


@dataclass
class Spectrum:
    """A quantity sampled on :data:`GRID`.

    ``values`` are transmission (0-1), normalized absorption/emission (0-1),
    quantum efficiency (0-1), or spectral power (arbitrary units) depending on
    context. The class does not police units; the callers do.
    """

    values: np.ndarray
    label: str = ""
    #: False when the curve came from a parametric approximation rather than a
    #: measured dataset. Any verdict resting on an approximated curve is
    #: reported as low-confidence.
    measured: bool = True

    def __post_init__(self) -> None:
        self.values = np.asarray(self.values, dtype=float)
        if self.values.shape != GRID.shape:
            raise ValueError(
                f"spectrum '{self.label}' has {self.values.shape} samples, "
                f"expected {GRID.shape} (use Spectrum.from_curve to resample)"
            )

    # -- construction ------------------------------------------------------

    @classmethod
    def constant(cls, value: float, label: str = "") -> "Spectrum":
        return cls(np.full_like(GRID, float(value)), label)

    @classmethod
    def from_curve(
        cls,
        wavelengths_nm,
        values,
        label: str = "",
        *,
        fill: float = 0.0,
        measured: bool = True,
    ) -> "Spectrum":
        """Resample an arbitrary (λ, value) curve onto the grid."""
        wl = np.asarray(wavelengths_nm, dtype=float)
        v = np.asarray(values, dtype=float)
        order = np.argsort(wl)
        wl, v = wl[order], v[order]
        out = np.interp(GRID, wl, v, left=fill, right=fill)
        return cls(out, label, measured)

    @classmethod
    def from_file(cls, path: str | Path, label: str = "", **kw) -> "Spectrum":
        """Load a two-column text/CSV curve (λ_nm, value).

        Handles the usual vendor exports: comment lines, tab/comma/space
        separators, and percent-scaled transmission (auto-detected: any value
        above 1.5 means the column is in percent).
        """
        path = Path(path)
        rows: list[tuple[float, float]] = []
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line[0] in "#;/%":
                continue
            parts = [p for p in line.replace(",", " ").replace("\t", " ").split() if p]
            if len(parts) < 2:
                continue
            try:
                rows.append((float(parts[0]), float(parts[1])))
            except ValueError:
                continue  # header row
        if not rows:
            raise ValueError(f"no numeric (wavelength, value) rows found in {path}")

        wl = np.array([r[0] for r in rows])
        v = np.array([r[1] for r in rows])
        if v.max() > 1.5:
            v = v / 100.0
        return cls.from_curve(wl, v, label or path.stem, **kw)

    @classmethod
    def band(
        cls,
        center_nm: float,
        fwhm_nm: float,
        *,
        peak: float = 1.0,
        blocking_od: float | None = 6.0,
        edge_steepness: float = 0.02,
        label: str = "",
    ) -> "Spectrum":
        """A bandpass: flat top, steep edges, finite out-of-band leak.

        ``edge_steepness`` is the transition width as a fraction of the
        bandwidth (2% ≈ a modern hard-coated filter). ``blocking_od`` sets the
        out-of-band floor, which is what actually decides bleed-through
        verdicts — a real filter's blocking is wavelength dependent and this
        flat floor is optimistic in the far wings.

        ``blocking_od=None`` gives a true zero floor. Use it for **emission
        lines**, not filters: a 24 nm-wide LED line modelled with a 1e-4 floor
        spread over the whole 800 nm grid carries as much integrated power in
        its fictitious pedestal as in the line itself, which silently invents
        excitation at wavelengths the source does not emit.
        """
        half = fwhm_nm / 2.0
        width = max(fwhm_nm * edge_steepness, 0.5)
        rise = 0.5 * (1 + np.tanh((GRID - (center_nm - half)) / width))
        fall = 0.5 * (1 - np.tanh((GRID - (center_nm + half)) / width))
        shape = rise * fall
        # Renormalize so the flat top reaches `peak` even for narrow bands,
        # where the two tanh edges start to overlap.
        top = shape.max()
        if top > 0:
            shape = shape / top
        floor = 0.0 if blocking_od is None else 10.0 ** (-blocking_od)
        return cls(floor + (peak - floor) * shape, label, measured=False)

    @classmethod
    def edge(
        cls,
        edge_nm: float,
        *,
        kind: str = "long",
        peak: float = 1.0,
        blocking_od: float | None = 6.0,
        transition_nm: float = 8.0,
        label: str = "",
    ) -> "Spectrum":
        """A long-pass (``kind="long"``) or short-pass dichroic/filter."""
        s = 0.5 * (1 + np.tanh((GRID - edge_nm) / max(transition_nm / 2.0, 0.5)))
        if kind == "short":
            s = 1.0 - s
        floor = 0.0 if blocking_od is None else 10.0 ** (-blocking_od)
        return cls(floor + (peak - floor) * s, label, measured=False)

    @classmethod
    def fluorophore_band(
        cls,
        peak_nm: float,
        fwhm_nm: float,
        *,
        side: str = "emission",
        label: str = "",
    ) -> "Spectrum":
        """Approximate a dye absorption or emission band.

        Modelled as a Gaussian in **wavenumber** (which reproduces the
        characteristic wavelength-space asymmetry) plus one vibronic shoulder:
        blue-side for absorption, red-side for emission.

        This is a triage shape, not a measurement. Peak positions are right;
        the wings — which is where crosstalk and bleed-through live — are not.
        """
        nu0 = _nm_to_cm1(peak_nm)
        # Convert FWHM from nm to cm^-1 at the peak.
        fwhm_cm1 = abs(_nm_to_cm1(peak_nm - fwhm_nm / 2) - _nm_to_cm1(peak_nm + fwhm_nm / 2))
        sigma = fwhm_cm1 / (2.0 * np.sqrt(2.0 * np.log(2.0)))

        nu = _nm_to_cm1(GRID)
        main = np.exp(-((nu - nu0) ** 2) / (2 * sigma**2))
        shift = _VIBRONIC_CM1 if side == "absorption" else -_VIBRONIC_CM1
        shoulder = _VIBRONIC_AMP * np.exp(
            -((nu - (nu0 + shift)) ** 2) / (2 * sigma**2)
        )
        v = main + shoulder
        v /= v.max()
        return cls(v, label, measured=False)

    # -- arithmetic ---------------------------------------------------------

    def __mul__(self, other: "Spectrum | float") -> "Spectrum":
        if isinstance(other, Spectrum):
            return Spectrum(
                self.values * other.values,
                f"{self.label}*{other.label}".strip("*"),
                self.measured and other.measured,
            )
        return Spectrum(self.values * float(other), self.label, self.measured)

    __rmul__ = __mul__

    def clipped(self, lo: float = 0.0, hi: float = 1.0) -> "Spectrum":
        return Spectrum(np.clip(self.values, lo, hi), self.label, self.measured)

    def inverted(self) -> "Spectrum":
        """``1 - T``. Reflection of an ideal lossless dichroic."""
        return Spectrum(
            np.clip(1.0 - self.values, 0.0, 1.0), f"R({self.label})", self.measured
        )

    # -- reductions ---------------------------------------------------------

    def integrate(self, lo: float = WL_MIN, hi: float = WL_MAX) -> float:
        m = (GRID >= lo) & (GRID <= hi)
        return float(np.trapezoid(self.values[m], GRID[m]))

    def area_normalized(self) -> "Spectrum":
        """Scale to unit area — the right form for an emission probability."""
        a = self.integrate()
        if a <= 0:
            return Spectrum(np.zeros_like(GRID), self.label, self.measured)
        return Spectrum(self.values / a, self.label, self.measured)

    def peak_nm(self) -> float:
        """Wavelength of the maximum.

        Uses the centre of the maximal plateau rather than ``argmax`` — a
        flat-top bandpass has hundreds of tied samples and ``argmax`` would
        report its blue edge as the "peak".
        """
        peak = self.values.max()
        if peak <= 0:
            return float(GRID[0])
        idx = np.nonzero(self.values >= peak * (1 - 1e-9))[0]
        return float((GRID[idx[0]] + GRID[idx[-1]]) / 2.0)

    def at(self, nm: float) -> float:
        return float(np.interp(nm, GRID, self.values))

    def mean_over(self, other: "Spectrum") -> float:
        """Weighted mean of this spectrum under ``other`` as the weight.

        e.g. mean camera QE over a dye's emission band.
        """
        w = other.area_normalized()
        return float(np.trapezoid(self.values * w.values, GRID))

    def support(self, threshold: float = 0.5) -> tuple[float, float] | None:
        """(λ_low, λ_high) where the curve exceeds ``threshold`` of its peak."""
        peak = self.values.max()
        if peak <= 0:
            return None
        idx = np.nonzero(self.values >= threshold * peak)[0]
        if idx.size == 0:
            return None
        return float(GRID[idx[0]]), float(GRID[idx[-1]])


def overlap(a: Spectrum, b: Spectrum) -> float:
    """``∫ a·b dλ`` with ``b`` area-normalized: the fraction of ``b`` that ``a``
    lets through. Bounded in [0, 1] when ``a`` is a transmission."""
    return float(np.trapezoid(a.values * b.area_normalized().values, GRID))


def product(*spectra: Spectrum) -> Spectrum:
    """Multiply a chain of optical elements together."""
    out = Spectrum.constant(1.0, "unity")
    for s in spectra:
        out = out * s
    return out
