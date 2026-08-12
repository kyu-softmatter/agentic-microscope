"""Tests for the labeling / laser-line recommendation loop.

Two things matter here, same split as tests/test_optics.py:

* the **ranking is not an illusion** — it has to separate a well-matched
  dye/line pairing from a poorly-matched one, not just echo registry order
  (the two flattening bugs this module's docstrings describe)
* the **regression is pinned** — the dichroic reflection/transmission swap
  and the un-weighted Stokes headroom bug this feature surfaced would, if
  reintroduced, make every laser channel look impossible again
"""

from __future__ import annotations

from pathlib import Path

import pytest

from optics.components import find_dye, find_filter
from optics.recommend import load_scope, recommend_labels, recommend_panel, screen

SCOPE = Path(__file__).resolve().parents[1] / "config" / "scopes" / "current-laser.yaml"


# ---------------------------------------------------------- regression pins --


def test_shared_notch_dichroic_transmits_broadband_and_reflects_narrow():
    """Di01-T405/488/568/647 must pass fluorescence emission and only reflect
    at the four laser lines — not the reverse. See data/filters.yaml note."""
    el = find_filter("Di01-T405/488/568/647-13x15x0.5", position="shared")
    assert el.transmission.at(670) > 0.5, "broadband emission must pass through"
    assert el.reflection.at(640) > 0.5, "the 640 nm laser line must be reflected"
    assert el.reflection.at(670) < 0.1, "emission wavelengths must not reflect"


def test_stokes_headroom_uses_the_source_line_not_the_whole_shared_dichroic():
    """A dichroic shared by four laser lines has a passive support spanning
    all four notches at once. stokes_headroom_nm must narrow that down using
    the actual line in use, or every dye looks like it overlaps its own
    excitation band (see optics/path.py Channel.stokes_headroom_nm)."""
    scope = load_scope(SCOPE)
    c = screen(scope, "AlexaFluor488", "488", "EM1-525/36")
    assert c is not None
    assert c.bottleneck != "spectral.overlap"


# ------------------------------------------------------------- single-line --


@pytest.mark.parametrize("line", ["488", "561", "640"])
def test_top_candidate_per_line_absorbs_near_that_wavelength(line):
    """The registry has an obvious right answer for three of the four lines:
    whichever dye's absorption peak sits closest to the line, not whichever
    dye happens to be registered first. Checked by spectral proximity, not a
    hardcoded name, because the dye registry keeps growing (docs/09) and a
    brighter, better-matched dye added later should be free to win."""
    by_line = recommend_labels(SCOPE, top=1)
    winner = find_dye(by_line[line][0].dye)
    assert abs(winner.absorption.peak_nm() - float(line)) < 20


def test_top_candidate_per_line_beats_every_other_dye_at_that_absorption():
    """Regression: a HARD-check margin sitting just under the (inflated,
    assumed-evidence) blocking bar must not bury a dye that is 10x+ brighter
    just because a dimmer dye happened to clear that bar by chance of which
    filter it was paired with (optics/recommend.py Candidate.hard_ok
    docstring). EGFP-class dyes on the 488 line are the concrete case that
    exposed this."""
    by_line = recommend_labels(SCOPE, top=1)
    winner = by_line["488"][0]
    assert winner.brightness > 0.05, (
        f"top 488 nm candidate ({winner.dye}) is nearly dark "
        f"(brightness={winner.brightness}) - a dim but technically-compliant "
        "channel won over a bright one"
    )


def test_405_line_has_no_well_matched_dye_in_the_registry():
    """Nothing in data/fluorophores.yaml absorbs anywhere near 405 nm — every
    candidate should still come back (never silently drop to an empty list),
    but with excitation efficiency far below the 488/561/640 lines'."""
    by_line = recommend_labels(SCOPE, top=1)
    assert by_line["405"], "must still report *something*, not go silent"
    assert (
        by_line["405"][0].excitation_efficiency
        < by_line["488"][0].excitation_efficiency
    )


def test_ranking_is_not_just_registry_order():
    """Regression for the tie-break bug: every filter in this registry shares
    the same un-curved blocking_od=6 default, so the bottleneck margin alone
    ties across nearly every candidate. Without a tie-break on excitation
    efficiency, sorting silently falls back to alphabetical dye order."""
    by_line = recommend_labels(SCOPE, top=4)
    names_488 = [c.dye for c in by_line["488"]]
    assert names_488 != sorted(names_488), (
        "ranking matches alphabetical order - the tie-break is not doing anything"
    )


def test_evidence_is_assumed_for_an_all_parametric_registry():
    """Every dye and filter here is peak+FWHM, not a loaded vendor curve, so
    the honest answer is 'assumed' — this is triage, not a cleared channel."""
    by_line = recommend_labels(SCOPE, top=1)
    for candidates in by_line.values():
        for c in candidates:
            assert c.evidence == "assumed"


def test_unknown_dye_name_does_not_crash_the_search():
    scope = load_scope(SCOPE)
    assert screen(scope, "NotADye", "488", "EM1-525/36") is None


# ------------------------------------------------------------------- panel --


def test_panel_assigns_four_distinct_well_matched_dyes():
    panel = recommend_panel(SCOPE)
    assert panel is not None
    dyes = [c.dye for c in panel.choices]
    assert len(set(dyes)) == 4, "a panel must not relabel the same dye twice"

    by_line = {c.line: find_dye(c.dye) for c in panel.choices}
    for line, dye in by_line.items():
        if line == "405":
            continue  # known registry gap, see test_405_line_has_no_well_matched_dye...
        assert abs(dye.absorption.peak_nm() - float(line)) < 20, (
            f"{dye.name} was assigned to the {line} nm line but absorbs at "
            f"{dye.absorption.peak_nm():.0f} nm"
        )


def test_panel_crosstalk_margin_is_computed_against_the_other_chosen_channels():
    panel = recommend_panel(SCOPE)
    assert panel is not None
    assert panel.worst_crosstalk_margin > 0


# --------------------------------------------------------- dual-camera split --
# Splitter = "DM A561LP" (config/scopes/current-laser.yaml): Kinetix_red gets
# the transmitted side (>561 nm), Kinetix_blue the reflected side (<561 nm).
#
# These two call screen() directly with an explicit bandpass filter, rather
# than going through recommend_labels(SCOPE)'s emission_filters list. As of
# 2026-08-11 that list holds only "EM-Open" (kb/systems/current.md >
# optical_path_nis > EM1/EM2 -- the filters previously recorded there turned
# out to be misattributed, and EM1/EM2's real filters have no fwhm data yet).
# Without any real emission filter, the 488 nm line's top recommend_labels()
# candidate correctly flips to Kinetix_red: the reflected/blue side passes
# <561 nm unfiltered, so 488 nm excitation reflects right along with the
# dye's emission and the excitation-blocking hard gate fails -- that is a
# genuine finding about the current unfiltered system, not a bug. Pinning
# the dichroic swap regression itself needs a filter that actually blocks
# the excitation line, so these use "EM1-525/36"/"EM1-705/72" as synthetic
# stand-in bandpasses -- real, registered filters, just not claimed to be
# EM1/EM2's current physical contents.


def test_candidates_below_561_land_on_the_reflected_side_camera():
    below = screen(load_scope(SCOPE), "ATTO488", "488", "EM1-525/36", camera="Kinetix_blue")
    above = screen(load_scope(SCOPE), "ATTO488", "488", "EM1-525/36", camera="Kinetix_red")
    assert below.sort_key() > above.sort_key()


def test_candidates_above_561_land_on_the_transmitted_side_camera():
    below = screen(load_scope(SCOPE), "AlexaFluor647", "640", "EM1-705/72", camera="Kinetix_blue")
    above = screen(load_scope(SCOPE), "AlexaFluor647", "640", "EM1-705/72", camera="Kinetix_red")
    assert above.sort_key() > below.sort_key()


def test_panel_choices_report_a_camera_for_a_split_scope():
    panel = recommend_panel(SCOPE)
    assert panel is not None
    assert all(c.camera in {"Kinetix_red", "Kinetix_blue"} for c in panel.choices)


def test_single_camera_scope_has_no_camera_field():
    """A scope without a `splitter` key must behave exactly as before this
    feature existed - camera stays None, nothing changes for a one-camera lab."""
    scope = load_scope(SCOPE)
    scope.pop("splitter")
    for line in scope["source"]["lines"]:
        for filt in scope["emission_filters"]:
            c = screen(scope, "AlexaFluor647", line, filt)
            if c is not None:
                assert c.camera is None
