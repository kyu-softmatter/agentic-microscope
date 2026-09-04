"""Tests for config/micromanager/set_pixel_size.py.

The tool writes into a file that gets loaded against real hardware, so what is
pinned here is mostly what it *declines* to write. Every test runs on a copy in
tmp_path -- nothing here touches the repository's own .cfg.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CFG = REPO / "config" / "micromanager" / "single_cam_red_noDMD.cfg"

_spec = importlib.util.spec_from_file_location(
    "set_pixel_size", REPO / "config" / "micromanager" / "set_pixel_size.py"
)
sps = importlib.util.module_from_spec(_spec)
sys.modules["set_pixel_size"] = sps
_spec.loader.exec_module(sps)


@pytest.fixture
def bare(tmp_path: Path) -> Path:
    """A copy of the lab config with its pixel-size presets stripped.

    Split with the module's own `read_cfg`, not on a hardcoded CRLF. This
    fixture used to split on CRLF, which is what `core.autocrlf` gives a
    Windows working copy and is not what macOS and Linux get. Against an LF
    checkout that split returns the entire file as one "line", no line matches
    either prefix, nothing is stripped, and every test taking this fixture is
    handed a verbatim copy with all six presets still in it -- so the tool was
    asked to add a preset that was already there and reported "already covers"
    instead. Green on Windows, three failures on the other two, and the tool
    itself was never at fault. See
    `test_the_lab_config_line_endings_are_consistent` for the same hazard
    stated as a property.
    """
    lines, eol = sps.read_cfg(CFG)
    kept = [
        line
        for line in lines
        if not line.startswith(("ConfigPixelSize,", "PixelSize_um,"))
    ]
    out = tmp_path / "bare.cfg"
    out.write_bytes(eol.join(kept).encode("utf-8"))
    return out


# ---- the repository's own config ---------------------------------------


def test_the_lab_config_is_fully_covered():
    """Every nosepiece position has a preset that matches the table."""
    assert sps.audit(CFG, 1.0) == 0


def test_the_lab_config_line_endings_are_consistent():
    """One ending throughout, whichever one this checkout produced.

    Not "is CRLF": `core.autocrlf` gives Windows a CRLF working copy and macOS
    and Linux an LF one, and CI runs all three. What must hold on every one of
    them is that the file does not mix -- appending LF lines to a CRLF checkout
    is easy to do from a POSIX shell and it happened here on 2026-09-04.
    """
    raw = CFG.read_bytes()
    crlf, lf_total = raw.count(b"\r\n"), raw.count(b"\n")
    assert crlf in (0, lf_total), f"mixed: {crlf} CRLF among {lf_total} lines"


def test_reader_survives_a_mixed_file(bare: Path, tmp_path: Path):
    """The parser must not trust the file to be clean -- see read_cfg.

    The odd line is swapped to *the other* ending, whichever this checkout
    produced, so the file is genuinely mixed on all three platforms. Written
    as a fixed CRLF-to-LF swap, this was a no-op against an LF checkout: the
    substring did not occur, `mixed` was a clean copy, and the assertion below
    passed without a mixed file ever existing. It is the one test here that
    stayed green on macOS and Linux while testing nothing.
    """
    additions, _ = sps.plan(bare, 40, 1.0)
    sps.apply(bare, additions)

    _, eol = sps.read_cfg(bare)
    other = "\n" if eol == "\r\n" else "\r\n"
    target = f"{eol}ConfigPixelSize,40x-1x"
    raw = bare.read_bytes()
    assert target.encode("utf-8") in raw, "fixture did not write the 40x preset"

    mixed = tmp_path / "mixed.cfg"
    mixed.write_bytes(
        raw.replace(target.encode("utf-8"), f"{other}ConfigPixelSize,40x-1x".encode("utf-8"), 1)
    )
    blob = mixed.read_bytes()
    crlf, lf_total = blob.count(b"\r\n"), blob.count(b"\n")
    assert 0 < crlf < lf_total, f"not mixed: {crlf} CRLF among {lf_total} lines"

    lines, _ = sps.read_cfg(mixed)
    assert sps.existing_presets(lines)["40x-1x"] == ("4-Apo LmbdS 40x WI", 0.1625)


# ---- writing -----------------------------------------------------------


def test_dry_run_writes_nothing(bare: Path):
    before = bare.read_bytes()
    additions, problems = sps.plan(bare, 40, 1.0)
    assert additions and not problems
    assert bare.read_bytes() == before


def test_write_then_the_preset_is_there_and_matches(bare: Path):
    additions, problems = sps.plan(bare, 40, 1.0)
    assert not problems
    sps.apply(bare, additions)

    lines, _ = sps.read_cfg(bare)
    presets = sps.existing_presets(lines)
    assert presets["40x-1x"] == ("4-Apo LmbdS 40x WI", 0.1625)


def test_write_preserves_the_files_own_line_ending(bare: Path):
    """`apply` keeps whichever ending it was given, and does not mix.

    Was `test_write_preserves_crlf`, asserting every newline is CRLF. That is
    only true where `core.autocrlf` produced a CRLF working copy, so it failed
    on macOS and Linux for a reason that had nothing to do with `apply`. What
    `apply` actually promises is the property `read_cfg` documents: write back
    the ending the file already had, and never leave a mixed file behind.
    """
    _, eol_before = sps.read_cfg(bare)
    additions, _ = sps.plan(bare, 40, 1.0)
    sps.apply(bare, additions)

    raw = bare.read_bytes()
    crlf, lf_total = raw.count(b"\r\n"), raw.count(b"\n")
    assert crlf in (0, lf_total), f"mixed: {crlf} CRLF among {lf_total} lines"
    assert sps.read_cfg(bare)[1] == eol_before


def test_running_twice_is_not_a_duplicate(bare: Path):
    additions, _ = sps.plan(bare, 40, 1.0)
    sps.apply(bare, additions)
    again, problems = sps.plan(bare, 40, 1.0)
    assert again == []
    assert any("already covers" in p for p in problems)


# ---- the three refusals ------------------------------------------------


def test_refuses_an_objective_with_no_row_in_the_table(bare: Path):
    """It will not fall back to p_sensor/M and call the result a calibration."""
    additions, problems = sps.plan(bare, 25, 1.0)
    assert additions == []
    assert any("no row for" in p for p in problems)


def test_refuses_a_magnification_the_nosepiece_does_not_have(bare: Path, tmp_path: Path):
    """A preset keyed on a label no position carries can never match."""
    lines, eol = sps.read_cfg(bare)
    without_60 = [line for line in lines if "60x Oil" not in line]
    trimmed = tmp_path / "no60.cfg"
    trimmed.write_bytes(eol.join(without_60).encode())

    additions, problems = sps.plan(trimmed, 60, 1.0)
    assert additions == []
    assert any("no 60x position" in p for p in problems)


def test_refuses_to_overwrite_a_preset_that_disagrees(bare: Path):
    """One of the two is wrong and the tool cannot tell which."""
    additions, _ = sps.plan(bare, 40, 1.0)
    sps.apply(bare, additions)
    bare.write_bytes(
        bare.read_bytes().replace(b"PixelSize_um,40x-1x,0.1625", b"PixelSize_um,40x-1x,0.17")
    )

    again, problems = sps.plan(bare, 40, 1.0)
    assert again == []
    assert any("Not overwriting" in p for p in problems)
    # and the wrong value is still there -- it refused, it did not repair
    assert b"0.17" in bare.read_bytes()


def test_audit_flags_a_disagreement_rather_than_passing_it(bare: Path):
    additions, _ = sps.plan(bare, 40, 1.0)
    sps.apply(bare, additions)
    bare.write_bytes(
        bare.read_bytes().replace(b"PixelSize_um,40x-1x,0.1625", b"PixelSize_um,40x-1x,0.17")
    )
    assert sps.audit(bare, 1.0) == 1


# ---- it never opens a device -------------------------------------------


def test_the_module_does_not_import_pymmcore():
    """File-only by construction: the half that turns a turret is not here."""
    source = (REPO / "config" / "micromanager" / "set_pixel_size.py").read_text(
        encoding="utf-8"
    )
    for banned in ("pymmcore", "CMMCorePlus", "setState", "setProperty"):
        assert banned not in source, banned
