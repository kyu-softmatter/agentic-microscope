"""Deterministic optical-path validation.

Committee lens #1. Given a dye, a light source, a filter/dichroic chain, an
objective and a detector, compute what actually reaches the camera and return a
PASS / PASS_WITH_CHANGES / FAIL / BLOCKED verdict with the numbers attached.

    from optics import build_channel, evaluate

    ch = build_channel({
        "name": "Cy5",
        "dye": "ATTO647N",
        "objective": {"label": "100x Oil", "magnification": 100,
                      "na": 1.45, "immersion": "oil", "verified_na": True},
        "detector": "Prime95B",
        "source": ["Spectra", "Red"],
        "excitation": ["FF01-640/14"],
        "dichroic": "FF650-Di01",
        "emission": ["FF01-692/40"],
    })
    print(evaluate(ch).status)

``BLOCKED`` means the inputs were insufficient to judge — it is not a pass.
"""

from .components import (
    Detector,
    Element,
    Fluorophore,
    LightSourceLine,
    Objective,
    find_dye,
    find_filter,
    find_line,
    reset_registries,
)
from .checks import CHECKS, GRADE_NOTES, LIMITS, Check, CheckResult, grade
from .gate import THRESHOLDS, Finding, Verdict, evaluate
from .path import Ablation, Channel, ablate
from .spectra import GRID, Spectrum, overlap, product
from .build import build_channel, build_channels
from .recommend import (
    Candidate,
    Panel,
    PanelChoice,
    SourceOption,
    compare_sources,
    load_scope,
    recommend_labels,
    recommend_panel,
    screen,
)

__all__ = [
    "Ablation",
    "CHECKS",
    "Candidate",
    "Channel",
    "Check",
    "CheckResult",
    "Detector",
    "Element",
    "Finding",
    "GRADE_NOTES",
    "LIMITS",
    "Panel",
    "PanelChoice",
    "SourceOption",
    "grade",
    "Fluorophore",
    "GRID",
    "LightSourceLine",
    "Objective",
    "Spectrum",
    "THRESHOLDS",
    "Verdict",
    "ablate",
    "build_channel",
    "build_channels",
    "compare_sources",
    "evaluate",
    "find_dye",
    "find_filter",
    "find_line",
    "load_scope",
    "overlap",
    "product",
    "recommend_labels",
    "recommend_panel",
    "reset_registries",
    "screen",
]
