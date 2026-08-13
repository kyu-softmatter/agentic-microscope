"""Light-path model: source -> sample -> detector, and what survives the trip.

A :class:`Channel` is one complete imaging configuration for one fluorophore.
Everything the optical lens needs to judge it is computed here; the verdict
itself lives in :mod:`optics.gate`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .components import Detector, Element, Fluorophore, LightSourceLine, Objective
from .spectra import GRID, Spectrum, product

# Physical constants
_H = 6.62607015e-34  # J*s
_C = 2.99792458e8  # m/s
#: Absorption cross-section per unit molar extinction coefficient, cm^2.
_SIGMA_PER_EPSILON = 3.82e-21


@dataclass
class Channel:
    """One fluorophore imaged through one specific optical configuration."""

    name: str
    dye: Fluorophore
    objective: Objective
    detector: Detector
    source: LightSourceLine | None = None
    #: source -> sample, in order. Excitation filter, ND, shutter window, ...
    excitation: list[Element] = field(default_factory=list)
    #: the beamsplitter. Reflects excitation, transmits emission (epi geometry).
    dichroic: Element | None = None
    #: sample -> detector, in order. Emission filter, wheel position, mirrors.
    emission: list[Element] = field(default_factory=list)
    #: fraction of collected light sent to this camera port (e.g. L100 -> 1.0)
    port_fraction: float = 1.0

    # -- transmission chains ------------------------------------------------

    def excitation_chain(self) -> list[Element]:
        chain = list(self.excitation)
        if self.dichroic is not None:
            chain.append(self.dichroic)
        return chain

    def emission_chain(self) -> list[Element]:
        chain: list[Element] = []
        if self.dichroic is not None:
            chain.append(self.dichroic)
        chain.extend(self.emission)
        return chain

    def excitation_transmission(self, *, skip: str | None = None) -> Spectrum:
        """Source -> sample. The dichroic contributes its *reflection*."""
        parts: list[Spectrum] = []
        for el in self.excitation:
            if el.label != skip:
                parts.append(el.transmission)
        if self.dichroic is not None and self.dichroic.label != skip:
            refl = self.dichroic.reflection or self.dichroic.transmission.inverted()
            parts.append(refl)
        parts.append(self.objective.throughput())
        return product(*parts)

    def emission_transmission(self, *, skip: str | None = None) -> Spectrum:
        """Sample -> detector, excluding QE. The dichroic transmits here."""
        parts: list[Spectrum] = [self.objective.throughput()]
        if self.dichroic is not None and self.dichroic.label != skip:
            parts.append(self.dichroic.transmission)
        for el in self.emission:
            if el.label != skip:
                parts.append(el.transmission)
        return product(*parts) * self.port_fraction

    # -- scalar figures of merit ---------------------------------------------

    def excitation_efficiency(self, *, skip: str | None = None) -> float:
        """Fraction of source power that both reaches the sample *and* lands
        where the dye absorbs.

        ``∫ S(λ)·T_ex(λ)·A(λ) dλ / ∫ S(λ) dλ`` with ``A`` the dye absorption
        normalized to unit peak. Zero means the line cannot excite this dye.
        """
        if self.source is None:
            return float("nan")
        t = self.excitation_transmission(skip=skip)
        src = self.source.spectrum
        num = np.trapezoid(src.values * t.values * self.dye.absorption.values, GRID)
        den = np.trapezoid(src.values, GRID)
        return float(num / den) if den > 0 else 0.0

    def source_delivery(self, *, skip: str | None = None) -> float:
        """Fraction of source power reaching the sample, regardless of the dye."""
        if self.source is None:
            return float("nan")
        t = self.excitation_transmission(skip=skip)
        num = np.trapezoid(self.source.spectrum.values * t.values, GRID)
        den = np.trapezoid(self.source.spectrum.values, GRID)
        return float(num / den) if den > 0 else 0.0

    def spectral_collection(self, *, skip: str | None = None) -> float:
        """Electrons per photon *emitted into the collected solid angle*.

        ``∫ E(λ)·T_em(λ)·QE(λ) dλ`` with ``E`` the emission spectrum normalized
        to unit area. Combines filter transmission and detector QE.
        """
        t = self.emission_transmission(skip=skip)
        e = self.dye.emission.area_normalized()
        return float(np.trapezoid(e.values * t.values * self.detector.qe.values, GRID))

    def total_collection(self, *, skip: str | None = None) -> float:
        """Electrons per photon emitted by a molecule, over 4π."""
        return self.objective.collection_efficiency() * self.spectral_collection(
            skip=skip
        )

    def relative_signal(self, *, skip: str | None = None) -> float:
        """Excitation × collection. The quantity ablation compares."""
        ex = self.excitation_efficiency(skip=skip)
        if math.isnan(ex):
            ex = 1.0  # no source defined: judge the emission side alone
        return ex * self.total_collection(skip=skip)

    def excitation_blocking_od(self, *, skip: str | None = None) -> float:
        """How hard the emission path attenuates the excitation light.

        Backscattered and reflected excitation is the dominant background in
        epifluorescence. Anything below ~5 OD shows up as a bright haze that no
        amount of exposure tuning fixes.
        """
        if self.source is None:
            return float("inf")
        at_sample = self.source.spectrum * self.excitation_transmission()
        em_t = self.emission_transmission(skip=skip)
        leaked = np.trapezoid(at_sample.values * em_t.values * self.detector.qe.values, GRID)
        incident = np.trapezoid(at_sample.values * self.detector.qe.values, GRID)
        if incident <= 0:
            return float("inf")
        ratio = leaked / incident
        return float(-math.log10(ratio)) if ratio > 0 else float("inf")

    def crosstalk_from(self, other: "Channel") -> float:
        """Fraction of ``other``'s per-molecule signal that leaks into this
        channel, counting both cross-excitation and emission bleed-through."""
        em_leak = float(
            np.trapezoid(
                other.dye.emission.area_normalized().values
                * self.emission_transmission().values
                * self.detector.qe.values,
                GRID,
            )
        )
        if self.source is not None:
            src = self.source.spectrum
            t = self.excitation_transmission()
            cross_ex = float(
                np.trapezoid(src.values * t.values * other.dye.absorption.values, GRID)
            ) / float(np.trapezoid(src.values, GRID))
        else:
            cross_ex = 1.0

        own = other.relative_signal()
        leak = cross_ex * other.objective.collection_efficiency() * em_leak
        return float(leak / own) if own > 0 else 0.0

    def stokes_headroom_nm(self) -> float:
        """Gap between the excitation band edge and the emission band edge.

        Negative means the excitation and detection bands overlap, which no
        filter can fix — the dye/filter pairing itself is wrong.

        Must be weighted by the source spectrum, not just the passive path.
        A single narrow excitation filter makes the two nearly the same, which
        is why this went unnoticed: but a dichroic shared by several laser
        lines (one multiband element reflecting at all of them) has a passive
        support spanning every line at once. Without the source line to pick
        out which reflection notch is actually lit, the "excitation band"
        looks hundreds of nm wide and falsely overlaps every dye's emission.
        Same pattern as :meth:`excitation_blocking_od`.
        """
        path = self.excitation_transmission()
        delivered = self.source.spectrum * path if self.source is not None else path
        ex = delivered.support(0.5)
        em = self.emission_transmission().support(0.5)
        if not ex or not em:
            return float("nan")
        return em[0] - ex[1]

    # -- absolute photon budget ------------------------------------------------

    def excitation_rate_per_s(
        self,
        *,
        power_mw_at_sample: float | None = None,
        illuminated_area_um2: float | None = None,
    ) -> float | None:
        """Absorption events per second per molecule (docs/04 §5's chain).

        ``P -> I = P/A -> phi = I lambda/(hc) -> sigma phi``. Returns ``None``
        when the illumination has never been power-calibrated, rather than
        inventing a number.

        This is the quantity the photo-perturbation lens (5) needs: dose is
        about what the molecule absorbs, not what the camera detects. Lens 1
        owns this chain, so lens 5 consumes it rather than recomputing it.
        """
        if (
            power_mw_at_sample is None
            or illuminated_area_um2 is None
            or self.dye.ext_coeff is None
            or self.source is None
        ):
            return None

        lam_m = self.source.center_nm * 1e-9
        photon_energy_j = _H * _C / lam_m
        power_w = power_mw_at_sample * 1e-3
        area_cm2 = illuminated_area_um2 * 1e-8
        flux = power_w / photon_energy_j / area_cm2  # photons cm^-2 s^-1

        sigma = _SIGMA_PER_EPSILON * self.dye.ext_coeff  # cm^2
        # Weight by how well the delivered spectrum overlaps the absorption.
        coupling = self.excitation_efficiency() / max(self.source_delivery(), 1e-12)

        return float(sigma * flux * coupling)

    def emitted_photons_per_s(
        self,
        *,
        power_mw_at_sample: float | None = None,
        illuminated_area_um2: float | None = None,
    ) -> float | None:
        """Photons emitted per second per molecule — ``k_em`` in docs/04 §6.

        The input to the photobleaching budget (G10), which counts emitted
        photons against the dye's ``bleach_photons``, not detected ones.
        """
        rate = self.excitation_rate_per_s(
            power_mw_at_sample=power_mw_at_sample,
            illuminated_area_um2=illuminated_area_um2,
        )
        if rate is None or self.dye.quantum_yield is None:
            return None
        return float(rate * self.dye.quantum_yield)

    def detected_e_per_s(
        self,
        *,
        power_mw_at_sample: float | None = None,
        illuminated_area_um2: float | None = None,
    ) -> float | None:
        """Detected electrons per second per molecule.

        Returns ``None`` when the illumination has never been power-calibrated,
        rather than inventing a number. Without ``mW at the sample`` there is no
        absolute photon budget — only relative comparisons are meaningful.

        Saturation and triplet shelving are not modelled; at high irradiance
        this overestimates. Lens 5's G20 is what checks whether that regime has
        been reached.
        """
        emitted = self.emitted_photons_per_s(
            power_mw_at_sample=power_mw_at_sample,
            illuminated_area_um2=illuminated_area_um2,
        )
        if emitted is None:
            return None
        return float(emitted * self.total_collection())


# --------------------------------------------------------------------------
# Ablation: which elements are earning their place?
# --------------------------------------------------------------------------


#: Elements that spectrally select rather than merely attenuate. The emission
#: path must retain at least one of these; a bare dichroic is not a detection
#: filter.
SELECTIVE_KINDS = {"bandpass", "multiband", "longpass", "shortpass"}


@dataclass
class Ablation:
    """What happens to the channel if one element is taken out."""

    element: str
    kind: str
    signal_gain: float  # multiplicative, 1.0 = no change
    blocking_od_after: float
    worst_crosstalk_after: float
    verdict: str  # remove | candidate | keep | required | no-effect
    reason: str


def ablate(
    channel: Channel,
    others: list[Channel] | None = None,
    *,
    min_blocking_od: float = 5.0,
    max_crosstalk: float = 0.05,
    gain_threshold: float = 1.10,
    spectra_measured: bool = True,
) -> list[Ablation]:
    """Try removing each removable element and report what it costs or buys.

    This is the concrete mechanism behind "suggest removing a filter": rather
    than guessing, take the element out of the product, recompute, and check
    whether the constraints still hold.

    ``spectra_measured=False`` (parametric band shapes) makes the analysis
    deliberately timid. A parametric filter has an idealized flat blocking
    floor and infinitely clean wings, so removing it looks far safer on paper
    than it is in glass. Under approximation the blocking requirement is
    raised and every removal is downgraded to ``candidate`` — something to
    test on the bench, not an instruction to follow.
    """
    others = others or []
    base_signal = channel.relative_signal()
    results: list[Ablation] = []

    # Approximated curves understate out-of-band leakage; demand more margin.
    blocking_floor = min_blocking_od + (0.0 if spectra_measured else 2.0)
    emission_selective = [
        el for el in channel.emission_chain() if el.kind in SELECTIVE_KINDS
    ]

    candidates = [el for el in channel.excitation_chain() + channel.emission_chain()]
    seen: set[str] = set()

    for el in candidates:
        if el.label in seen:
            continue
        seen.add(el.label)

        if not el.removable:
            results.append(
                Ablation(
                    element=el.label,
                    kind=el.kind,
                    signal_gain=1.0,
                    blocking_od_after=channel.excitation_blocking_od(),
                    worst_crosstalk_after=0.0,
                    verdict="required",
                    reason="marked non-removable (structural element)",
                )
            )
            continue

        signal_after = channel.relative_signal(skip=el.label)
        gain = signal_after / base_signal if base_signal > 0 else float("inf")
        blocking = channel.excitation_blocking_od(skip=el.label)

        worst_xt = 0.0
        if others:
            saved_em = list(channel.emission)
            saved_dic = channel.dichroic
            channel.emission = [e for e in channel.emission if e.label != el.label]
            if channel.dichroic is not None and channel.dichroic.label == el.label:
                channel.dichroic = None
            try:
                worst_xt = max(channel.crosstalk_from(o) for o in others)
            finally:
                channel.emission = saved_em
                channel.dichroic = saved_dic

        # Would the emission path still be spectrally selective without it?
        last_selective = (
            el.kind in SELECTIVE_KINDS
            and el in emission_selective
            and len(emission_selective) == 1
        )

        if last_selective:
            verdict = "required"
            reason = (
                "it is the only spectrally selective element in the detection "
                "path; without it the dichroic alone decides what reaches the "
                "camera, which is not a detection filter"
            )
        elif blocking < blocking_floor:
            verdict = "required"
            reason = (
                f"removing it drops excitation blocking to {blocking:.1f} OD "
                f"(need >= {blocking_floor:.0f}); backscattered excitation "
                f"would swamp the signal"
            )
        elif worst_xt > max_crosstalk:
            verdict = "required"
            reason = (
                f"removing it raises crosstalk to {worst_xt * 100:.1f}% "
                f"(limit {max_crosstalk * 100:.0f}%)"
            )
        elif gain >= gain_threshold and not spectra_measured:
            verdict = "candidate"
            reason = (
                f"signal would rise {(gain - 1) * 100:.0f}% on paper, but this "
                f"rests on approximated spectra whose wings and blocking floor "
                f"are optimistic. Load measured curves before acting; if the "
                f"element is a source-cleanup or blocking filter, assume it is "
                f"needed until proven otherwise"
            )
        elif gain >= gain_threshold:
            verdict = "remove"
            reason = (
                f"signal would rise {(gain - 1) * 100:.0f}% with blocking still "
                f"{blocking:.1f} OD and crosstalk {worst_xt * 100:.1f}% - "
                f"this element costs more than it contributes"
            )
        elif gain <= 1.001:
            verdict = "no-effect"
            reason = "no measurable effect on signal, blocking or crosstalk"
        else:
            verdict = "keep"
            reason = f"only {(gain - 1) * 100:.1f}% to gain; not worth changing"

        results.append(
            Ablation(
                element=el.label,
                kind=el.kind,
                signal_gain=gain,
                blocking_od_after=blocking,
                worst_crosstalk_after=worst_xt,
                verdict=verdict,
                reason=reason,
            )
        )

    results.sort(key=lambda a: -a.signal_gain)
    return results
