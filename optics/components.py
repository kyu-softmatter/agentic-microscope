"""Optical components and the registries that describe them.

Every element in a light path is reduced to a transmission :class:`Spectrum`
plus enough metadata to reason about *why* it is there — which is what lets the
gate propose removing it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .spectra import GRID, Spectrum

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SPECTRA_DIR = DATA_DIR / "spectra"

# Refractive index of the immersion medium, for collection-efficiency maths.
IMMERSION_N = {
    "air": 1.000,
    "dry": 1.000,
    "water": 1.333,
    "glycerol": 1.470,
    "silicone": 1.406,
    "oil": 1.518,
}


# --------------------------------------------------------------------------
# Spectrum construction from a YAML description
# --------------------------------------------------------------------------


def build_spectrum(spec: dict[str, Any], label: str = "") -> Spectrum:
    """Turn a YAML component description into a transmission spectrum.

    Recognised forms, in priority order:

    ``curve: <file>``            measured two-column data (preferred)
    ``bands: [[c, w], ...]``     multiband pass
    ``center_nm`` + ``fwhm_nm``  single bandpass
    ``edge_nm`` + ``kind``       long/short pass or dichroic edge
    ``od``                       neutral density
    ``transmission``             flat value
    """
    if curve := spec.get("curve"):
        path = Path(curve)
        if not path.is_absolute():
            path = SPECTRA_DIR / curve
        return Spectrum.from_file(path, label)

    blocking_raw = spec.get("blocking_od", 6.0)
    blocking = None if blocking_raw is None else float(blocking_raw)
    peak = float(spec.get("peak_transmission", spec.get("transmission", 0.95)))

    if bands := spec.get("bands"):
        total = Spectrum(GRID * 0.0, label, measured=False)
        for band in bands:
            c, w = float(band[0]), float(band[1])
            total = Spectrum(
                total.values
                + Spectrum.band(
                    c, w, peak=peak, blocking_od=blocking, label=label
                ).values,
                label,
                measured=False,
            )
        return total.clipped(0.0, peak)

    if spec.get("center_nm") is not None:
        return Spectrum.band(
            float(spec["center_nm"]),
            float(spec["fwhm_nm"]),
            peak=peak,
            blocking_od=blocking,
            label=label,
        )

    if spec.get("edge_nm") is not None:
        kind = spec.get("kind", "longpass")
        direction = "short" if "short" in str(kind) else "long"
        return Spectrum.edge(
            float(spec["edge_nm"]),
            kind=direction,
            peak=peak,
            blocking_od=blocking,
            transition_nm=float(spec.get("transition_nm", 8.0)),
            label=label,
        )

    if (od := spec.get("od")) is not None:
        return Spectrum.constant(10.0 ** (-float(od)), label)

    return Spectrum.constant(peak, label)


# --------------------------------------------------------------------------
# Elements
# --------------------------------------------------------------------------


@dataclass
class Element:
    """One thing the light passes through (or bounces off).

    ``removable`` and ``purpose`` drive the ablation analysis: the gate tries
    taking each removable element out and reports what that would buy.
    """

    label: str
    kind: str  # bandpass | multiband | longpass | shortpass | dichroic |
    # mirror | nd | polarizer | objective | tube_lens | window | unknown
    transmission: Spectrum
    reflection: Spectrum | None = None
    removable: bool = True
    purpose: str = ""
    position: str = "emission"  # excitation | emission | shared | illumination
    vendor: str | None = None
    part_number: str | None = None
    note: str | None = None
    verified: bool = False  # True when built from a measured curve

    @classmethod
    def from_spec(
        cls, label: str, spec: dict[str, Any], *, position: str = "emission"
    ) -> "Element":
        t = build_spectrum(spec, label)
        r = None
        if refl := spec.get("reflection"):
            r = build_spectrum(refl, f"R({label})")
        elif spec.get("kind") in {"dichroic", "mirror"}:
            r = t.inverted()
        return cls(
            label=label,
            kind=spec.get("kind", "unknown"),
            transmission=t,
            reflection=r,
            removable=bool(spec.get("removable", True)),
            purpose=spec.get("purpose", ""),
            position=spec.get("position", position),
            vendor=spec.get("vendor"),
            part_number=spec.get("part_number"),
            note=spec.get("note"),
            verified=t.measured,
        )

    def as_reflected(self) -> "Element":
        """The same physical part, seen from its reflected side.

        A beamsplitting dichroic (e.g. an image splitter sending one
        wavelength half to each of two cameras) sends different light down
        each port, but every caller downstream — ``Channel.emission_chain``,
        ablation, the gate's missing-input scan — only ever reads
        ``.transmission``. Rather than teach each of those about a "which
        side" flag, swap the two spectra once here and let the port on the
        reflected side treat the result as an ordinary transmissive element.
        """
        if self.reflection is None:
            raise ValueError(
                f"'{self.label}' has no reflectance on record, so its "
                "reflected side is unknown. Add `reflection:` or set "
                "`kind: dichroic`/`mirror` on its data/filters.yaml entry."
            )
        return replace(
            self,
            label=f"{self.label} (reflected)",
            transmission=self.reflection,
            reflection=self.transmission,
        )


@dataclass
class Fluorophore:
    name: str
    absorption: Spectrum
    emission: Spectrum
    ext_coeff: float | None = None  # M^-1 cm^-1
    quantum_yield: float | None = None
    lifetime_ns: float | None = None
    photostability: str | None = None  # low | medium | high
    bleach_photons: float | None = None  # mean photons emitted before bleaching
    aliases: list[str] = field(default_factory=list)
    note: str | None = None

    @property
    def brightness(self) -> float | None:
        """ε·Φ — the standard single-number comparison between dyes."""
        if self.ext_coeff and self.quantum_yield:
            return self.ext_coeff * self.quantum_yield
        return None

    @property
    def stokes_shift_nm(self) -> float:
        return self.emission.peak_nm() - self.absorption.peak_nm()

    @property
    def verified(self) -> bool:
        return self.absorption.measured and self.emission.measured

    @classmethod
    def from_spec(cls, name: str, spec: dict[str, Any]) -> "Fluorophore":
        curves = spec.get("curves") or {}

        def band(which: str, peak_key: str, fwhm_key: str, side: str) -> Spectrum:
            if path := curves.get(which):
                p = Path(path)
                return Spectrum.from_file(
                    p if p.is_absolute() else SPECTRA_DIR / p, f"{name}.{which}"
                )
            peak = spec.get(peak_key)
            if peak is None:
                raise ValueError(
                    f"fluorophore '{name}': needs either curves.{which} or {peak_key}"
                )
            return Spectrum.fluorophore_band(
                float(peak),
                float(spec.get(fwhm_key, 40.0)),
                side=side,
                label=f"{name}.{which}",
            )

        return cls(
            name=name,
            absorption=band("absorption", "abs_peak_nm", "abs_fwhm_nm", "absorption"),
            emission=band("emission", "em_peak_nm", "em_fwhm_nm", "emission"),
            ext_coeff=spec.get("ext_coeff_M1cm1"),
            quantum_yield=spec.get("quantum_yield"),
            lifetime_ns=spec.get("lifetime_ns"),
            photostability=spec.get("photostability"),
            bleach_photons=spec.get("bleach_photons"),
            aliases=spec.get("aliases") or [],
            note=spec.get("note"),
        )


@dataclass
class LightSourceLine:
    """One excitation line, as spectral power at the source."""

    name: str
    spectrum: Spectrum
    max_power_mw: float | None = None
    #: measured mW at the sample per objective, at 100% level
    power_at_sample_mw: dict[str, float] = field(default_factory=dict)
    linear_in_level: bool = True

    @property
    def center_nm(self) -> float:
        return self.spectrum.peak_nm()

    @property
    def calibrated(self) -> bool:
        return bool(self.power_at_sample_mw)

    @classmethod
    def from_spec(cls, name: str, spec: dict[str, Any]) -> "LightSourceLine":
        # A source is an emission line, not a filter: no out-of-band pedestal.
        # With a 1e-4 floor spread over the 800 nm grid, a 24 nm LED line would
        # carry more integrated power outside the line than inside it, and the
        # gate would report excitation of dyes the source cannot reach.
        src = dict(spec)
        src.setdefault("blocking_od", None)
        src.setdefault("peak_transmission", 1.0)
        s = build_spectrum(src, name)
        return cls(
            name=name,
            spectrum=s,
            max_power_mw=spec.get("max_power_mw"),
            power_at_sample_mw=spec.get("power_at_sample_mw") or {},
            linear_in_level=bool(spec.get("linear_in_level", True)),
        )


@dataclass
class Objective:
    label: str
    magnification: float
    na: float
    immersion: str = "air"
    transmission: Spectrum | None = None
    wd_um: float | None = None
    coverslip_um: float | None = 170.0
    correction_collar: bool = False
    verified_na: bool = False

    @classmethod
    def from_spec(cls, label: str, spec: dict[str, Any]) -> Objective:
        """Build from a registry entry (data/objectives.yaml).

        ``optics.build._objective`` is the equivalent for an objective spelled
        out inline in a channel/scope file; it is kept separate because that
        path also has to accept a bare string.
        """
        transmission = None
        if t := spec.get("transmission"):
            transmission = (
                build_spectrum(t, f"{label}.T")
                if isinstance(t, dict)
                else Spectrum.constant(float(t), f"{label}.T")
            )
        return cls(
            label=spec.get("label", label),
            magnification=float(spec.get("magnification") or 0.0),
            na=float(spec.get("na") or 0.0),
            immersion=spec.get("immersion", "air"),
            transmission=transmission,
            wd_um=spec.get("wd_um"),
            coverslip_um=spec.get("coverslip_um", 170.0),
            correction_collar=bool(spec.get("correction_collar", False)),
            verified_na=bool(spec.get("verified_na", False)),
        )

    @property
    def n_medium(self) -> float:
        return IMMERSION_N.get(self.immersion, 1.0)

    def collection_efficiency(self) -> float:
        """Fraction of isotropic emission captured: ``(1 - cos θ)/2``.

        The single largest term in a fluorescence photon budget, and the one
        most often left out of back-of-envelope estimates.
        """
        ratio = min(self.na / self.n_medium, 1.0)
        theta = math.asin(ratio)
        return (1.0 - math.cos(theta)) / 2.0

    def resolution_nm(self, emission_nm: float) -> float:
        """Rayleigh lateral resolution ``0.61 λ / NA``."""
        return 0.61 * emission_nm / self.na

    def depth_of_field_nm(self, emission_nm: float) -> float:
        """Wave-optical DOF ``n λ / NA²`` (Berek term omitted)."""
        return self.n_medium * emission_nm / (self.na**2)

    def psf_sigma_nm(self, emission_nm: float) -> float:
        """Gaussian PSF standard deviation ``0.21 λ / NA`` (docs/04 §2).

        The localization-precision optimum for single-particle tracking sits
        near ``p ≈ σ_PSF``, not at the Nyquist pixel size used for morphology
        imaging -- see docs/04 §2 / docs/06-pitfalls.md §C6.
        """
        return 0.21 * emission_nm / self.na

    def throughput(self) -> Spectrum:
        if self.transmission is not None:
            return self.transmission
        # Placeholder only. Objective transmission is strongly wavelength
        # dependent (Plan Apo designs fall off hard below 400 nm and above
        # 700 nm), so this flat value is flagged unmeasured and forces the
        # verdict to "assumed".
        s = Spectrum.constant(0.90, f"{self.label}.T")
        s.measured = False
        return s


@dataclass
class DetectorMode:
    """One row of a camera's readout-mode table (docs/04 §4 §5, data/detectors.yaml).

    Bit depth, read noise and full well move together as a mode is chosen --
    they are kept in one place so a check never mixes numbers across modes.
    """

    name: str
    bit_depth: int
    read_noise_e: float | None = None
    full_well_e: float | None = None
    line_time_us: float | None = None


@dataclass
class Detector:
    label: str
    qe: Spectrum
    pixel_um: float | None = None
    read_noise_e: float | None = None
    full_well_e: float | None = None
    dark_e_per_s: float | None = None
    sensor_px: tuple[int, int] | None = None
    modes: dict[str, DetectorMode] = field(default_factory=dict)
    #: {"WxH": {"pcie": fps, "usb": fps}} -- datasheet frame-rate-by-ROI table.
    frame_rate_by_roi_fps: dict[str, dict[str, float]] = field(default_factory=dict)

    @classmethod
    def from_spec(cls, label: str, spec: dict[str, Any]) -> "Detector":
        # `qe_verified` was written into data/detectors.yaml from the start but was
        # never read here, so an inline curve typed in by hand -- every one of ours
        # was read off a datasheet *graph* by eye -- arrived as measured=True and
        # therefore never appeared in the gate's `assumed_inputs`
        # (optics/gate.py:208). An eyeballed curve was silently earning
        # `advances`, which is exactly what docs/01 Principle 1 and
        # docs/06-pitfalls.md E3 exist to prevent. An inline dict now has to say
        # `qe_verified: true` to claim measured; the default is False, because
        # silence about an unknown is how a recommender becomes dangerous.
        verified = spec.get("qe_verified")
        if curve := spec.get("qe_curve"):
            if isinstance(curve, dict):
                qe = Spectrum.from_curve(
                    [float(k) for k in curve],
                    list(curve.values()),
                    f"{label}.QE",
                    measured=bool(verified),
                )
            else:
                p = Path(curve)
                qe = Spectrum.from_file(
                    p if p.is_absolute() else SPECTRA_DIR / curve, f"{label}.QE"
                )
                # A file can be an eyeball digitization too; an explicit
                # `qe_verified: false` overrides from_file's optimism.
                if verified is False:
                    qe.measured = False
        else:
            qe = Spectrum.constant(float(spec.get("qe_peak", 0.8)), f"{label}.QE")
            qe.measured = False
        px = spec.get("sensor_px")
        modes = {
            name: DetectorMode(
                name=name,
                bit_depth=int(mode_spec["bit_depth"]),
                read_noise_e=mode_spec.get("read_noise_e"),
                full_well_e=mode_spec.get("full_well_e"),
                line_time_us=mode_spec.get("line_time_us"),
            )
            for name, mode_spec in (spec.get("modes") or {}).items()
        }
        roi_fps = {
            roi: dict(rates)
            for roi, rates in (spec.get("frame_rate_by_roi_fps") or {}).items()
            if roi != "note"
        }
        return cls(
            label=label,
            qe=qe,
            pixel_um=spec.get("pixel_um"),
            read_noise_e=spec.get("read_noise_e"),
            full_well_e=spec.get("full_well_e"),
            dark_e_per_s=spec.get("dark_e_per_s"),
            sensor_px=tuple(px) if px else None,
            modes=modes,
            frame_rate_by_roi_fps=roi_fps,
        )


# --------------------------------------------------------------------------
# Registries
# --------------------------------------------------------------------------


def _load_yaml(name: str) -> dict[str, Any]:
    path = DATA_DIR / name
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@lru_cache(maxsize=1)
def pixel_size_table() -> dict[str, Any]:
    """``data/pixel_size.yaml`` -- the recorded um/px per objective x intermediate.

    Mirrors ``kb/systems/current.md > pixel_size_calibration``, which is where
    the value lives that the Micro-Manager ``.cfg`` does not carry.
    """
    return _load_yaml("pixel_size.yaml").get("pixel_size") or {}


def recorded_pixel_um(
    mag_objective: float, mag_intermediate: float = 1.0, binning: int = 1
) -> tuple[float, str] | None:
    """um/px at the sample from the recorded table, with its evidence tier.

    Returns ``(um_per_px, evidence)`` or ``None`` when the combination is not in
    the table. **``evidence`` is ``"measured"`` for exactly one row** -- the 20x,
    the only one that departs from ``p_sensor / (M_obj * M_int)``. The rest are
    ``"nominal"`` and reproduce
    :func:`detection.photometry.effective_pixel_nm` exactly, so a caller that
    treats a ``nominal`` hit as a measurement has invented provenance rather
    than found it (``data/pixel_size.yaml`` header, and lens 6's G23-G27).
    """
    table = pixel_size_table().get("table") or {}
    row = table.get(str(int(mag_objective))) if float(mag_objective).is_integer() else None
    if row is None:
        return None
    values = row.get("values") or {}
    key = f"{mag_intermediate:g}x"
    if key not in values:
        return None
    return float(values[key]) * binning, str(row.get("evidence", "nominal"))


@lru_cache(maxsize=1)
def fluorophores() -> dict[str, Fluorophore]:
    """Dye registry, keyed by canonical name and by every alias."""
    raw = _load_yaml("fluorophores.yaml").get("fluorophores") or {}
    out: dict[str, Fluorophore] = {}
    for name, spec in raw.items():
        dye = Fluorophore.from_spec(name, spec)
        out[name.lower()] = dye
        for alias in dye.aliases:
            out[alias.lower()] = dye
    return out


def find_dye(name: str) -> Fluorophore | None:
    reg = fluorophores()
    key = name.strip().lower()
    if key in reg:
        return reg[key]
    squashed = "".join(ch for ch in key if ch.isalnum())
    for k, v in reg.items():
        if "".join(ch for ch in k if ch.isalnum()) == squashed:
            return v
    return None


@lru_cache(maxsize=1)
def filters() -> dict[str, dict[str, Any]]:
    return _load_yaml("filters.yaml").get("filters") or {}


def find_filter(name: str, *, position: str = "emission") -> Element | None:
    spec = filters().get(name)
    if spec is None:
        for k, v in filters().items():
            if k.lower() == name.lower():
                spec = v
                name = k
                break
    return Element.from_spec(name, spec, position=position) if spec else None


@lru_cache(maxsize=1)
def light_sources() -> dict[str, dict[str, Any]]:
    return _load_yaml("light_sources.yaml").get("light_sources") or {}


@lru_cache(maxsize=1)
def detectors() -> dict[str, Detector]:
    """Detector registry, keyed by canonical name and by every alias."""
    raw = _load_yaml("detectors.yaml").get("detectors") or {}
    out: dict[str, Detector] = {}
    for name, spec in raw.items():
        det = Detector.from_spec(name, spec)
        out[name.lower()] = det
        for alias in spec.get("aliases") or []:
            out[str(alias).lower()] = det
    return out


def find_detector(name: str) -> Detector | None:
    return detectors().get(name.strip().lower())


@lru_cache(maxsize=1)
def objectives() -> dict[str, Objective]:
    """Objective registry (the nosepiece), keyed by name and by label."""
    raw = _load_yaml("objectives.yaml").get("objectives") or {}
    out: dict[str, Objective] = {}
    for name, spec in raw.items():
        obj = Objective.from_spec(name, spec)
        out[str(name).lower()] = obj
        if obj.label:
            out[obj.label.lower()] = obj
    return out


def find_objective(name: str) -> Objective | None:
    return objectives().get(name.strip().lower())


@lru_cache(maxsize=1)
def objective_keys() -> tuple[str, ...]:
    """Canonical registry keys, in file order.

    ``objectives()`` is also keyed by label so lookups are forgiving; this is
    what to show a user who typed an unknown name.
    """
    return tuple(str(k) for k in (_load_yaml("objectives.yaml").get("objectives") or {}))


def find_line(source: str, line: str) -> LightSourceLine | None:
    src = light_sources().get(source) or {}
    spec = (src.get("lines") or {}).get(line)
    return LightSourceLine.from_spec(f"{source}.{line}", spec) if spec else None


def reset_registries() -> None:
    """Drop caches after editing the YAML files."""
    for fn in (fluorophores, filters, light_sources, detectors, objectives, objective_keys):
        fn.cache_clear()
