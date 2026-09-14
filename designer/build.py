"""Brief -> the nine lenses' Setup objects.

This module is the designer's only contact with physical values, so it is
where rule 2 is most easily broken and where it is held hardest: **every field
is either read from the brief or left `None`.** There is no `or 0.5`, no
fallback to a catalogue value, and no "reasonable" anything. A lens that
receives `None` refuses by name, which is the correct and useful answer.

Two ways a lens can fail to run, and they are not the same:

``NotConstructible``
    Its ``Setup`` has a *required* constructor argument the brief cannot fill,
    so ``evaluate()`` is never called and the lens emits **no** ``missing.*``
    code at all. This is a blind spot no harvest-based refiner can see into
    (kb/decisions/2026-09-13-the-planning-layer.md), and naming it is the
    whole reason this type exists rather than a bare exception.

``BLOCKED``
    The gate ran and refused by name. That is the healthy path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .brief import Brief


@dataclass(frozen=True)
class NotConstructible:
    """The gate could not be called. Carries what would make it callable."""

    lens: str
    missing: tuple[str, ...]
    why: str

    @property
    def runs(self) -> bool:
        return False


def _objective(brief: Brief):
    from optics.components import Objective

    label = brief.value("lens_1_optics.objective")
    if label is None:
        return None
    na = brief.value("lens_1_optics.objective.na")
    node = brief.facts.get("lens_1_optics", {}).get("objective", {})
    return Objective(
        label=label,
        magnification=_mag_from_label(label),
        na=na,
        immersion=node.get("immersion"),
        verified_na=bool(node.get("verified_na")),
    )


def _mag_from_label(label: str) -> float | None:
    """`"4-Apo LmbdS 40x WI"` -> 40.0. Reads the label, invents nothing."""
    import re

    m = re.search(r"(\d+(?:\.\d+)?)x", label)
    return float(m.group(1)) if m else None


# --------------------------------------------------------------------------
# One builder per lens. Each returns a Setup, or NotConstructible naming the
# required arguments the brief does not carry.
# --------------------------------------------------------------------------


def build_optics(brief: Brief):
    """Lens 1 reads the channel file directly -- the brief only points at it."""
    from optics.build import build_channels

    path = brief.meta.get("channel_config")
    if not path or not Path(path).exists():
        return NotConstructible(
            "optics", ("meta.channel_config",),
            "lens 1 is specified by a channel file and the brief names none",
        )
    return build_channels(path)


def build_detection(brief: Brief):
    from detection.setup import Acquisition, Camera, DetectionSetup
    from optics.components import find_detector

    exposure = brief.value("lens_2_detection.exposure_ms")
    if exposure is None:
        return NotConstructible(
            "detection", ("exposure_ms",),
            "detection.setup.Acquisition requires exposure_ms, so the gate is "
            "never called and emits no missing.* code for it",
        )

    obj = _objective(brief)
    name = brief.value("lens_1_optics.detector.value")
    det = find_detector(name) if name else None
    if det is None:
        return NotConstructible(
            "detection", ("detector",), f"detector {name!r} is not in data/detectors.yaml",
        )

    return DetectionSetup(
        objective=obj,
        wavelength_em_nm=brief.value("lens_2_detection.wavelength_em_nm"),
        mag_objective=_mag_from_label(brief.value("lens_1_optics.objective") or ""),
        camera=Camera(
            detector=det,
            mode=brief.value("lens_2_detection.camera_mode"),
            binning=brief.value("lens_2_detection.binning") or 1,
            row_time_us=_ns_to_us(brief.value("lens_2_detection.row_time_ns")),
        ),
        acquisition=Acquisition(exposure_ms=exposure),
    )


def _ns_to_us(ns):
    return None if ns is None else ns / 1000.0


def build_compute(brief: Brief):
    from compute.setup import AcquisitionResourceSetup

    return AcquisitionResourceSetup(
        disk_bandwidth_mb_s=brief.value("lens_3_compute.disk_bandwidth_mb_s"),
        disk_bandwidth_path_confirmed=bool(
            brief.value("lens_3_compute.disk_bandwidth_path_confirmed")
        ),
        acquisition_duration_s=brief.value("environment.acquisition_duration_s"),
        free_disk_gb=brief.value("lens_3_compute.free_disk_gb"),
    )


def build_sample(brief: Brief):
    from sample.setup import SampleSetup

    obj = _objective(brief)
    if obj is None:
        return NotConstructible(
            "sample", ("objective",), "sample.setup.SampleSetup requires an objective",
        )
    return SampleSetup(
        objective=obj,
        imaging_depth_um=brief.value("lens_4_sample.imaging_depth_um"),
        chamber_height_um=brief.value("lens_4_sample.chamber_height_um"),
        particle_radius_um=_radius(brief, "probe"),
        trapped=bool(brief.value("lens_4_sample.probe.trapped")),
        concentration_per_ml=brief.value("lens_4_sample.tracer_concentration_per_ml"),
    )


def _radius(brief: Brief, which: str):
    d = brief.value(f"lens_4_sample.{which}.diameter_um")
    return None if d is None else d / 2.0


def build_photo(brief: Brief):
    from photo.setup import IlluminationSetup

    return IlluminationSetup(
        power_mw_at_sample=brief.value("lens_5_photo.power_mw_at_sample"),
        illuminated_area_um2=brief.value("lens_5_photo.illuminated_area_um2"),
        exposure_ms=brief.value("lens_2_detection.exposure_ms"),
        trap_on=bool(brief.value("lens_4_sample.probe.trapped")),
    )


def build_validity(brief: Brief, upstream: dict | None = None):
    from validity.setup import ValiditySetup

    return ValiditySetup(
        intended_quantity=brief.intended_quantity,
        upstream=upstream or {},
        pixel_size_measured=(
            (f := brief.get("lens_2_detection.pixel_size_um_per_px")) is not None
            and f.evidence == "measured"
        ),
    )


def build_stability(brief: Brief):
    from stability.setup import StabilitySetup

    secs = brief.value("environment.acquisition_duration_s")
    return StabilitySetup(
        duration_min=None if secs is None else secs / 60.0,
        objective=_objective(brief),
        particle_radius_um=_radius(brief, "tracer"),
        chamber_height_um=brief.value("lens_4_sample.chamber_height_um"),
        chamber_sealed=brief.value("lens_4_sample.chamber_sealed"),
    )


def build_trapping(brief: Brief):
    from trapping.dynamics import Bead

    radius_um = _radius(brief, "probe")
    if radius_um is None:
        return NotConstructible(
            "trapping", ("bead.radius_m",), "trapping.dynamics.Bead requires a radius",
        )
    dial = brief.value("lens_7_trapping.dial_percent")
    if dial is None:
        return NotConstructible(
            "trapping", ("dial_percent",),
            "trapping.dynamics.TrapSetup requires the trap dial; the brief "
            "carries no laser setting for this run",
        )
    return Bead  # unreachable today -- see the NotConstructible above


def build_velocity(brief: Brief):
    from velocity.setup import VelocitySetup

    v = brief.value("lens_9_velocity.commanded_velocity_um_per_s")
    if isinstance(v, list):           # the brief states a range for a random walk
        v = max(v)                    # judge the worst case, which is the fastest
    return VelocitySetup(
        commanded_velocity_um_per_s=v,
        particle_radius_um=_radius(brief, "probe"),
        target_relative_error=brief.value("lens_9_velocity.target_relative_error"),
        velocity_time_base_verified=bool(
            brief.value("lens_9_velocity.velocity_time_base_verified")
        ),
    )


BUILDERS = {
    "optics": build_optics,
    "detection": build_detection,
    "compute": build_compute,
    "sample": build_sample,
    "photo": build_photo,
    "validity": build_validity,
    "stability": build_stability,
    "trapping": build_trapping,
    "velocity": build_velocity,
}
