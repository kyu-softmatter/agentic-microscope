"""Illumination setup: the facts lens 5's gates need."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from optics.path import Channel


@dataclass
class IlluminationSetup:
    #: Measured mW at the SAMPLE PLANE. Empty in data/light_sources.yaml for
    #: every line on every source, which is the project's top blocker -- a
    #: percent setting in the metadata is not a physical quantity. Without it
    #: every gate here is BLOCKED, by design.
    power_mw_at_sample: float | None = None
    #: Illuminated area at the sample, um^2.
    illuminated_area_um2: float | None = None
    #: Excitation wavelength (source line centre), nm.
    wavelength_nm: float | None = None

    #: Exposure per frame and how many frames the movie has.
    exposure_ms: float | None = None
    n_frames: int | None = None
    #: Wall-clock spacing between frames, for the duty cycle. Optional.
    frame_interval_ms: float | None = None

    # -- dye photophysics, from data/fluorophores.yaml ---------------------
    ext_coeff_m1cm1: float | None = None
    quantum_yield: float | None = None
    lifetime_ns: float | None = None
    #: Mean photons emitted before bleaching. Empty for every dye in the
    #: registry (docs/04 §6), so G10 blocks until one is supplied. The
    #: qualitative `photostability` grade is explicitly not a substitute.
    bleach_photons: float | None = None

    #: Rates from lens 1, if already computed. Supplying these skips the
    #: chain here; lens 1 owns it (optics.path.Channel).
    excitation_rate_per_s: float | None = None
    emitted_photons_per_s: float | None = None
    #: Transmission-weighted mean of the dye's absorption over the delivered
    #: spectrum -- lens 1's ``excitation_efficiency() / source_delivery()``.
    #: Used only by the local fallback chain below, which has no spectra of its
    #: own. 1.0 would mean the delivered line sits exactly on the absorption
    #: peak across its whole band, which is never true, so an absent value is
    #: reported as assumed rather than quietly taken as 1.
    excitation_coupling: float | None = None

    # -- sample photoresponse ---------------------------------------------
    #: Can the light itself drive the sample -- light-driven active particles,
    #: photo-crosslinking, LC photo-alignment (docs/06 D2)?
    #:
    #: Tri-state on purpose. ``None`` means **nobody has asked yet**, which is
    #: a different state from a confirmed ``False``: docs/06 D2's accident is
    #: the unasked question, not a wrong number, so the default must not be a
    #: silent "no". ``None`` warns and stops the verdict advancing without
    #: blocking the rest of the lens.
    photoresponsive: bool | None = None
    #: Irradiance above which the sample responds, W/cm^2. Sample-specific and
    #: not derivable, so a photoresponsive sample without it BLOCKs rather
    #: than being waved through.
    light_driving_threshold_w_cm2: float | None = None
    #: Optional total-dose ceiling, J/cm^2.
    dose_limit_j_cm2: float | None = None

    #: True when the 1064 nm trap is on. Lens 7 owns trap heating but does not
    #: implement it, so lens 5 refuses to let that handoff vanish silently.
    trap_on: bool = False

    @classmethod
    def from_channel(
        cls,
        channel: "Channel",
        *,
        power_mw_at_sample: float | None = None,
        illuminated_area_um2: float | None = None,
        **kwargs,
    ) -> IlluminationSetup:
        """Build from a lens 1 channel, consuming its excitation chain.

        This is the path that gets k_ex right: the channel's rate already
        carries the spectral-overlap weighting the fallback chain cannot
        compute, so ``excitation_coupling`` is not needed here.

        Anything not derivable from the channel (exposure, frame count, sample
        photoresponse) still has to be supplied.
        """
        dye = channel.dye
        return cls(
            power_mw_at_sample=power_mw_at_sample,
            illuminated_area_um2=illuminated_area_um2,
            wavelength_nm=channel.source.center_nm if channel.source else None,
            ext_coeff_m1cm1=dye.ext_coeff,
            quantum_yield=dye.quantum_yield,
            lifetime_ns=dye.lifetime_ns,
            bleach_photons=dye.bleach_photons,
            excitation_rate_per_s=channel.excitation_rate_per_s(
                power_mw_at_sample=power_mw_at_sample,
                illuminated_area_um2=illuminated_area_um2,
            ),
            emitted_photons_per_s=channel.emitted_photons_per_s(
                power_mw_at_sample=power_mw_at_sample,
                illuminated_area_um2=illuminated_area_um2,
            ),
            **kwargs,
        )

    @property
    def resolved_excitation_rate(self) -> float | None:
        """Absorption events per molecule per second.

        Uses lens 1's value when supplied, otherwise computes the chain from
        power/area/wavelength/epsilon -- the same arithmetic, for the case
        where there is no Channel to hand (a what-if, or a test).

        Not quite the same arithmetic, in fact: lens 1 weights ``sigma phi`` by
        how well the delivered spectrum overlaps the absorption band
        (``optics.path.Channel.excitation_rate_per_s``), and this fallback has
        no spectra to do that with. ``excitation_coupling`` carries that factor
        in when it is known; without it the value is an upper bound. See
        ``excitation_coupling_assumed``.
        """
        if self.excitation_rate_per_s is not None:
            return self.excitation_rate_per_s
        if (
            self.power_mw_at_sample is None
            or self.illuminated_area_um2 is None
            or self.wavelength_nm is None
            or self.ext_coeff_m1cm1 is None
        ):
            return None
        from .dose import irradiance_w_cm2, photon_flux_per_cm2_s

        flux = photon_flux_per_cm2_s(
            irradiance_w_cm2(self.power_mw_at_sample, self.illuminated_area_um2),
            self.wavelength_nm,
        )
        coupling = 1.0 if self.excitation_coupling is None else self.excitation_coupling
        return 3.82e-21 * self.ext_coeff_m1cm1 * flux * coupling

    @property
    def excitation_coupling_assumed(self) -> bool:
        """Did k_ex come from the local chain with no overlap factor at all?

        Then it is ``sigma phi`` with the spectral overlap silently set to 1 --
        the delivered line treated as if it sat on the absorption peak. Real
        couplings are well under 1: ATTO488 (abs peak 500 nm) on this lab's
        462-486 nm green band runs near a half
        (config/channels/active-microrheology-probe-tracer.yaml).

        The bias direction is worth stating, because it is not the dangerous
        one. Too large a k_ex inflates both the excited-state fraction (G20)
        and the emitted-photon count (G10), so both gates come out *stricter*
        than the instrument warrants -- false alarms, not false clears. The
        cost is a wrong instruction ("cut the light") rather than a missed
        perturbation. Either way the number is not this instrument's, so the
        verdict reports it as assumed and does not advance.
        """
        return (
            self.excitation_rate_per_s is None
            and self.excitation_coupling is None
            and self.resolved_excitation_rate is not None
        )

    @property
    def resolved_emitted_per_s(self) -> float | None:
        if self.emitted_photons_per_s is not None:
            return self.emitted_photons_per_s
        rate = self.resolved_excitation_rate
        if rate is None or self.quantum_yield is None:
            return None
        return rate * self.quantum_yield

    @property
    def resolved_irradiance(self) -> float | None:
        if self.power_mw_at_sample is None or self.illuminated_area_um2 is None:
            return None
        from .dose import irradiance_w_cm2

        return irradiance_w_cm2(self.power_mw_at_sample, self.illuminated_area_um2)
