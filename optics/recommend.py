"""Dye-labeling / laser-line recommendation loop.

Given a fixed set of installed excitation lines and emission filters (a
*scope*, see :mod:`config/scopes`), search the fluorophore registry for which
dye pairs well with which line and which filter, and — for a simultaneous
multi-colour panel — which combination keeps every pairwise crosstalk under
the same limit :mod:`optics.gate` enforces.

This is deliberately **not** a wrapper around :func:`optics.gate.evaluate`.
That gate's Phase 0 vetoes the whole verdict on a missing objective NA or an
incomplete detector spec (docs/08 §0) — correct for "is this channel ready to
shoot", wrong for "which dye should I even consider". None of the four checks
used here (:func:`optics.checks.check_excitation`,
:func:`optics.checks.check_stokes`, :func:`optics.checks.check_blocking`,
:func:`optics.checks.check_collection`) read NA or pixel/read-noise/full-well,
so they can run today even though this lab's current objective and camera are
still unconfirmed (kb/systems/current.md). Reusing them directly — rather than
recomputing similar arithmetic — is what keeps these numbers identical to
whatever ``optics.cli check`` would report once a full channel config exists.

This screens; it does not clear. A candidate that ranks first here still needs
``optics.cli check`` against a real objective/camera config before an
experiment is booked on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product as _iproduct
from pathlib import Path
from typing import Any

import yaml

from .build import build_channel
from .checks import (
    GRADES,
    HARD,
    check_blocking,
    check_collection,
    check_crosstalk,
    check_excitation,
    check_stokes,
    grade,
)
from .components import fluorophores
from .gate import _assumed_inputs  # same evidence bookkeeping as the full gate
from .path import Channel

SCOPES_DIR = Path(__file__).resolve().parents[1] / "config" / "scopes"

#: The single-channel checks a recommendation is built from. Crosstalk is
#: deliberately excluded here — it only means something once a full panel has
#: been chosen, see :func:`recommend_panel`.
_SINGLE_CHECKS = (check_excitation, check_stokes, check_blocking, check_collection)

#: Margin below which optics.checks.grade() calls it INFEASIBLE (docs/05
#: §3). GRADES is sorted descending with INFEASIBLE last at threshold 0.0,
#: so this is the threshold of the entry just above it (MARGINAL).
_INFEASIBLE_BELOW = GRADES[-2][0]


@dataclass
class Candidate:
    """One (line, filter, dye) combination and how it scores."""

    line: str
    filter: str
    dye: str
    bottleneck: str
    margin: float
    grade: str
    evidence: str  # measured | assumed
    #: which camera this candidate was scored on, or None for a single-camera
    #: scope. See :func:`_cameras` — a scope with a ``splitter`` is scored on
    #: every camera and the winner is kept, since which port a dye's emission
    #: actually lands on is a property of its own spectrum, not a hardware
    #: setting to choose in advance.
    camera: str | None = None
    #: no HARD-kind check (excitation/Stokes/blocking) is in INFEASIBLE
    #: territory (margin < 0.2, the same cutoff optics.checks.grade uses,
    #: docs/05 §3). Deliberately *not* gated at margin >= 1.0: the project's
    #: own grading treats HARD (0.5-1.0) as "runs, just difficult" rather
    #: than broken, and every candidate here is `evidence: assumed`, which
    #: already inflates the blocking requirement from 5 OD to 7 (checks.py
    #: LIMITS) as a safety margin against uncurved filter wings. A 0.87
    #: (~6.1 OD) sitting just under that inflated bar is not the same thing
    #: as zero excitation or overlapping bands, and must not be treated as
    #: equally disqualifying. See :meth:`sort_key`.
    hard_ok: bool = False
    #: excitation_efficiency x spectral_collection - a relative brightness
    #: figure that needs no power calibration (the geometric/NA factor that
    #: would turn this into an absolute photon rate is identical for every
    #: candidate on this scope, so it cancels out of the *ranking* even
    #: though it is missing from the *value*). See :meth:`sort_key`.
    brightness: float = 0.0
    #: raw source-power fraction landing in the dye's absorption, unnormalized
    #: by hardware losses. Kept for reporting even though `brightness`, not
    #: this alone, drives the ranking.
    excitation_efficiency: float = 0.0
    margins: dict[str, float] = field(default_factory=dict)
    assumed: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def sort_key(self) -> tuple[bool, float, float, float]:
        """Structurally sound first, then by how bright it would actually be.

        Two flattening effects make ranking on check margins alone
        meaningless — this data set has no vendor curves loaded, and the
        margins themselves do not track absolute brightness:

        1. Every filter in this registry shares the same un-curved
           ``blocking_od: 6`` default (docs/06), so ``blocking`` margins
           differ mainly by how far the filter sits from the excitation
           line — a dye barely excited at all, if paired with a distant
           filter, can rack up a huge blocking margin (extra rejection it
           does not need) that a well-excited dye with a closer filter never
           gets a chance at. Sorting on margin first let a near-dark channel
           beat a bright one.
        2. :func:`optics.checks.check_excitation` grades *coupling
           efficiency given whatever the dye absorbs at that wavelength* —
           it does not penalise a dye that barely absorbs there at all.

        So: first, does this clear every HARD gate at all (``hard_ok`` —
        genuinely broken configurations, e.g. zero excitation or overlapping
        bands, still sink no matter how the rest reads)? Among those that do,
        rank by ``brightness`` — the thing an experimenter actually cares
        about. The bottleneck margin only breaks remaining ties.
        """
        return (self.hard_ok, self.brightness, self.margin, self.excitation_efficiency)


@dataclass
class PanelChoice:
    line: str
    dye: str
    filter: str
    single_margin: float
    excitation_efficiency: float = 0.0
    brightness: float = 0.0
    camera: str | None = None


@dataclass
class Panel:
    """A simultaneous multi-colour assignment: one dye + filter per line."""

    choices: list[PanelChoice]
    worst_single_margin: float
    worst_crosstalk_margin: float
    grade: str

    @property
    def worst_margin(self) -> float:
        return min(self.worst_single_margin, self.worst_crosstalk_margin)

    @property
    def hard_ok(self) -> bool:
        """Same relaxed bar as :attr:`Candidate.hard_ok` for the per-channel
        margin (see its docstring — HARD-grade is "runs, just difficult", not
        broken). Crosstalk is graded ``bias`` (docs/05 §2: wrong-looking-right
        data, not merely hard), and this loop has no unmixing step to fall
        back on, so that one is kept at the stricter 1.0."""
        return (
            self.worst_single_margin >= _INFEASIBLE_BELOW
            and self.worst_crosstalk_margin >= 1.0
        )

    def sort_key(self) -> tuple[bool, float, float]:
        """Same rationale as :meth:`Candidate.sort_key`: a dim-but-technically
        -clean channel must not out-rank a bright one just because check
        margins do not track brightness. Gate on every gate actually holding
        (single-channel *and* crosstalk), then sum brightness across the
        panel — total signal is what a simultaneous acquisition is for."""
        total_brightness = sum(c.brightness for c in self.choices)
        return (self.hard_ok, total_brightness, self.worst_margin)


def load_scope(path: str | Path) -> dict[str, Any]:
    """Read a ``config/scopes/*.yaml`` profile. See that folder for examples."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return data.get("scope", data)


def _cameras(scope: dict[str, Any]) -> list[str | None]:
    """Which cameras a candidate must be scored on.

    A scope with no ``splitter`` has one detector and nothing to choose
    between — ``[None]`` so every caller can loop over this uniformly. A
    scope with a ``splitter`` (e.g. a dual-camera image splitter) names each
    camera and which side of the split it sits on; every candidate is scored
    on all of them.
    """
    splitter = scope.get("splitter")
    if not splitter:
        return [None]
    return list(splitter["cameras"].keys())


def _trial_channel(
    scope: dict[str, Any],
    dye_name: str,
    line: str,
    filt: str,
    *,
    camera: str | None = None,
    name: str | None = None,
) -> Channel:
    # Fixed elements every channel in this scope carries (e.g. a cube's own
    # multiband emitter, ahead of the selectable EM1/EM2 filter downstream)
    # come first, in physical order, then the selectable filter, then the
    # splitter side if this scope has one.
    emission = list(scope.get("emission_fixed") or []) + [filt]
    splitter = scope.get("splitter")
    if splitter and camera is not None:
        side = splitter["cameras"][camera]
        emission.append({"ref": splitter["registry"], "side": side})
    spec = {
        "name": name or f"{dye_name}@{line}/{filt}" + (f"/{camera}" if camera else ""),
        "dye": dye_name,
        "objective": scope.get("objective")
        or {"label": "(objective TBD)", "magnification": 0, "na": 0},
        "detector": scope["detector"],
        "source": [scope["source"]["device"], line],
        "excitation": scope.get("excitation") or [],
        "dichroic": scope["dichroic"],
        "emission": emission,
        "port_fraction": scope.get("port_fraction", 1.0),
    }
    return build_channel(spec)


def screen(
    scope: dict[str, Any], dye_name: str, line: str, filt: str, *, camera: str | None = None
) -> Candidate | None:
    """Score one (dye, line, filter) combination, on one camera.

    Returns ``None`` only when the combination cannot even be constructed
    (unknown dye/line name) — a combination that scores badly still comes
    back with a low margin, not ``None``, so the caller sees the whole
    picture rather than a silently shortened list.
    """
    try:
        ch = _trial_channel(scope, dye_name, line, filt, camera=camera)
    except KeyError:
        return None
    if ch.source is None:
        return None

    results = [c(ch, []) for c in _SINGLE_CHECKS]
    worst = min(results, key=lambda r: r.margin)
    hard_ok = all(r.margin >= _INFEASIBLE_BELOW for r in results if r.kind == HARD)
    assumed = _assumed_inputs(ch)
    ex_eff = ch.excitation_efficiency()
    return Candidate(
        line=line,
        filter=filt,
        dye=dye_name,
        camera=camera,
        hard_ok=hard_ok,
        brightness=ex_eff * ch.spectral_collection(),
        bottleneck=worst.code,
        margin=round(worst.margin, 3),
        grade=grade(worst.margin),
        evidence="measured" if not assumed else "assumed",
        excitation_efficiency=ex_eff,
        margins={r.code: round(r.margin, 3) for r in results},
        assumed=assumed,
        notes=[r.message for r in results if r.severity != "ok"],
    )


def recommend_labels(
    scope_path: str | Path,
    dye_names: list[str] | None = None,
    *,
    top: int = 5,
) -> dict[str, list[Candidate]]:
    """For every excitation line in the scope, rank dye x filter combinations.

    ``dye_names`` defaults to the whole registry (deduplicated by canonical
    name — the registry indexes every alias too, and scoring an alias twice
    would just pad the ranking with itself).
    """
    scope = load_scope(scope_path)
    dyes = dye_names or sorted({d.name for d in fluorophores().values()})
    lines = scope["source"]["lines"]
    filters = scope["emission_filters"]
    cameras = _cameras(scope)

    out: dict[str, list[Candidate]] = {}
    for line in lines:
        scored: list[Candidate] = []
        for dye in dyes:
            for filt in filters:
                # A dye's emission lands on whichever side of a splitter its
                # spectrum favours - that is not a setting to guess in
                # advance, so score every camera and keep the one it wins.
                per_camera = [
                    c
                    for cam in cameras
                    if (c := screen(scope, dye, line, filt, camera=cam)) is not None
                ]
                if per_camera:
                    scored.append(max(per_camera, key=lambda c: c.sort_key()))
        scored.sort(key=lambda c: c.sort_key(), reverse=True)
        out[line] = scored[:top]
    return out


def recommend_panel(
    scope_path: str | Path,
    lines: list[str] | None = None,
    dye_names: list[str] | None = None,
    *,
    candidates_per_line: int = 4,
) -> Panel | None:
    """Best simultaneous multi-colour labeling scheme for this scope.

    Exhaustive over the top-``candidates_per_line`` single-channel candidates
    per line, not over the full dye x filter grid: doing a full search would
    be ``(dyes x filters) ** n_lines`` crosstalk evaluations, which grows fast
    for no real benefit — a dye that is not even in the top handful for its
    own line is not going to win a panel once crosstalk is added on top.
    Raise ``candidates_per_line`` for a wider (slower) search.

    Returns ``None`` if any line has zero candidates (e.g. the registry has
    nothing this scope's filters can pass at all).
    """
    scope = load_scope(scope_path)
    lines = lines or scope["source"]["lines"]
    per_line = recommend_labels(scope_path, dye_names, top=candidates_per_line)
    pools = [per_line.get(line, []) for line in lines]
    if any(not p for p in pools):
        return None

    best: Panel | None = None
    for combo in _iproduct(*pools):
        if len({c.dye for c in combo}) != len(combo):
            continue  # the same dye cannot label two lines in one panel

        channels = [
            _trial_channel(
                scope, c.dye, c.line, c.filter, camera=c.camera, name=f"{c.line}:{c.dye}"
            )
            for c in combo
        ]
        worst_single = min(c.margin for c in combo)
        worst_xt_margin = min(
            check_crosstalk(ch, [o for j, o in enumerate(channels) if j != i]).margin
            for i, ch in enumerate(channels)
        )

        panel = Panel(
            choices=[
                PanelChoice(
                    c.line, c.dye, c.filter, c.margin,
                    c.excitation_efficiency, c.brightness, c.camera,
                )
                for c in combo
            ],
            worst_single_margin=worst_single,
            worst_crosstalk_margin=worst_xt_margin,
            grade=grade(min(worst_single, worst_xt_margin)),
        )
        if best is None or panel.sort_key() > best.sort_key():
            best = panel
    return best


@dataclass
class SourceOption:
    """One light source's best answer to the same labeling question."""

    scope_path: str
    scope_name: str
    panel: Panel | None
    error: str | None = None


def compare_sources(
    scope_paths: list[str | Path],
    lines: list[str] | None = None,
    dye_names: list[str] | None = None,
    *,
    candidates_per_line: int = 4,
) -> list[SourceOption]:
    """Run the same labeling question against several light sources.

    Each scope is one light source (docs/08 §6 - a scope names exactly one
    ``source.device``), so this never mixes two light engines into one
    panel; a lab that prefers a single light source per experiment gets that
    for free just by keeping scopes single-source. This function does not
    pick a winner - it hands back every source's best panel, sorted best
    first, so a person chooses. Which light source suits the biology (optical
    sectioning vs. photon budget vs. what else is already booked on it) is
    exactly the kind of judgment this project does not want a script making
    silently (docs/01 principle 5).

    ``lines`` means "these excitation lines, however each scope names them" -
    pass the wavelengths every candidate scope actually has (e.g. ``["488",
    "640"]``); a scope missing one just returns no panel, reported as such
    rather than silently dropped.
    """
    options: list[SourceOption] = []
    for path in scope_paths:
        path = Path(path)
        try:
            scope = load_scope(path)
        except Exception as exc:  # noqa: BLE001 - report, do not crash the comparison
            options.append(SourceOption(str(path), path.stem, None, str(exc)))
            continue
        try:
            panel = recommend_panel(
                path, lines=lines, dye_names=dye_names,
                candidates_per_line=candidates_per_line,
            )
        except Exception as exc:  # noqa: BLE001
            options.append(SourceOption(str(path), scope.get("name", path.stem), None, str(exc)))
            continue
        options.append(SourceOption(str(path), scope.get("name", path.stem), panel))

    def key(opt: SourceOption) -> tuple[bool, bool, float]:
        if opt.panel is None:
            return (False, False, 0.0)
        return (True, opt.panel.hard_ok, sum(c.brightness for c in opt.panel.choices))

    options.sort(key=key, reverse=True)
    return options
