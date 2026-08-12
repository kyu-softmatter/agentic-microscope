"""Build :class:`Channel` objects from plain dicts / YAML.

Keeps the registry lookups and the "what if it isn't in the registry" handling
in one place, so callers never have to construct components by hand.

Unknown names do **not** raise. They become elements of kind ``unknown``, which
the gate then reports as ``BLOCKED`` with a specific instruction about what to
add. Failing loudly at the gate is more useful than failing at import time,
because the gate can say exactly which fact is missing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .components import (
    DATA_DIR,
    Detector,
    Element,
    Fluorophore,
    LightSourceLine,
    Objective,
    build_spectrum,
    find_dye,
    find_filter,
    find_line,
)
from .path import Channel
from .spectra import Spectrum


def _unknown_element(label: str, position: str) -> Element:
    return Element(
        label=label,
        kind="unknown",
        transmission=Spectrum.constant(1.0, label),
        removable=False,
        position=position,
        note="not found in data/filters.yaml",
        verified=False,
    )


def _element(ref: Any, position: str) -> Element:
    """Accept a registry name, an inline dict describing the element, or
    ``{"ref": <registry name>, "side": "reflect"}`` to pick the far side of a
    beamsplitting element — e.g. the camera on the reflected port of a dual-
    camera image splitter. ``side`` defaults to ``"transmit"``, the ordinary
    in-line case."""
    if isinstance(ref, dict) and "ref" in ref:
        el = find_filter(str(ref["ref"]), position=position)
        if el is None:
            return _unknown_element(str(ref["ref"]), position)
        side = ref.get("side", "transmit")
        if side == "reflect":
            return el.as_reflected()
        if side != "transmit":
            raise ValueError(
                f"unknown side '{side}' for '{ref['ref']}' "
                "(use 'transmit' or 'reflect')"
            )
        return el
    if isinstance(ref, dict):
        label = ref.get("label") or ref.get("name") or "inline"
        return Element.from_spec(label, ref, position=position)
    el = find_filter(str(ref), position=position)
    return el or _unknown_element(str(ref), position)


def _detector(ref: Any) -> Detector:
    if isinstance(ref, dict):
        return Detector.from_spec(ref.get("label", "detector"), ref)

    path = DATA_DIR / "detectors.yaml"
    registry = (
        (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("detectors") or {}
        if path.exists()
        else {}
    )
    name = str(ref)
    spec = registry.get(name)
    if spec is None:
        for key, value in registry.items():
            if key.lower() == name.lower() or name in (value.get("aliases") or []):
                spec, name = value, key
                break
    if spec is None:
        # Unknown detector. A placeholder QE is supplied only so the spectral
        # arithmetic does not crash; it is flagged unmeasured and every noise
        # figure is left None, so the gate reports BLOCKED rather than
        # producing a number that looks authoritative.
        qe = Spectrum.constant(0.8, f"{name}.QE")
        qe.measured = False
        return Detector(label=name, qe=qe)
    return Detector.from_spec(name, spec)


def _objective(ref: Any) -> Objective:
    if isinstance(ref, str):
        return Objective(label=ref, magnification=0.0, na=0.0)
    spec = dict(ref)
    transmission = None
    if t := spec.get("transmission"):
        transmission = (
            build_spectrum(t, f"{spec.get('label', 'obj')}.T")
            if isinstance(t, dict)
            else Spectrum.constant(float(t), "obj.T")
        )
    return Objective(
        label=spec.get("label", "objective"),
        magnification=float(spec.get("magnification") or 0.0),
        na=float(spec.get("na") or 0.0),
        immersion=spec.get("immersion", "air"),
        transmission=transmission,
        wd_um=spec.get("wd_um"),
        coverslip_um=spec.get("coverslip_um", 170.0),
        correction_collar=bool(spec.get("correction_collar", False)),
        verified_na=bool(spec.get("verified_na", False)),
    )


def _source(ref: Any) -> LightSourceLine | None:
    if ref is None:
        return None
    if isinstance(ref, dict):
        return LightSourceLine.from_spec(ref.get("name", "source"), ref)
    if isinstance(ref, (list, tuple)) and len(ref) == 2:
        return find_line(str(ref[0]), str(ref[1]))
    if isinstance(ref, str) and "." in ref:
        device, _, line = ref.partition(".")
        return find_line(device, line)
    return None


def build_channel(spec: dict[str, Any]) -> Channel:
    """Construct a channel from a dict. See :mod:`optics` for the shape."""
    dye_ref = spec.get("dye")
    if isinstance(dye_ref, dict):
        dye = Fluorophore.from_spec(dye_ref.get("name", "dye"), dye_ref)
    else:
        dye = find_dye(str(dye_ref)) if dye_ref else None
    if dye is None:
        raise KeyError(
            f"fluorophore '{dye_ref}' is not in data/fluorophores.yaml. "
            "Add it (peaks + epsilon + QY at minimum) before evaluating."
        )

    dichroic_ref = spec.get("dichroic")
    return Channel(
        name=spec.get("name", dye.name),
        dye=dye,
        objective=_objective(spec.get("objective", {})),
        detector=_detector(spec.get("detector", "unknown")),
        source=_source(spec.get("source")),
        excitation=[_element(r, "excitation") for r in (spec.get("excitation") or [])],
        dichroic=_element(dichroic_ref, "shared") if dichroic_ref else None,
        emission=[_element(r, "emission") for r in (spec.get("emission") or [])],
        port_fraction=float(spec.get("port_fraction", 1.0)),
    )


def build_channels(spec: dict[str, Any] | str | Path) -> list[Channel]:
    """Build every channel in a config, so crosstalk can be evaluated."""
    if isinstance(spec, (str, Path)):
        spec = yaml.safe_load(Path(spec).read_text(encoding="utf-8")) or {}

    if "channels" in spec:
        shared = {k: v for k, v in spec.items() if k != "channels"}
        return [build_channel({**shared, **c}) for c in spec["channels"]]
    if "channel" in spec:
        return [build_channel(spec["channel"])]
    return [build_channel(spec)]
