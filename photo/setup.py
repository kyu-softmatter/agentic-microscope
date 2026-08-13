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

    # -- sample photoresponse ---------------------------------------------
    #: True when the light itself can drive the sample: light-driven active
    #: particles, photo-crosslinking, LC photo-alignment (docs/06 D2).
    photoresponsive: bool = False
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
        return 3.82e-21 * self.ext_coeff_m1cm1 * flux

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
