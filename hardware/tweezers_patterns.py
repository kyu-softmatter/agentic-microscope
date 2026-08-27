"""Aresis Tweez 300 trapping patterns (``.tpf``) generated from Python.

The format and geometry layer; hardware/tweezers_drive.py plans a drive on top
of it. Route decided 2026-08-26 -- patterns, not TCP position streaming, for
anything whose timing enters the result
(kb/decisions/2026-08-26-tweezers-pattern-vs-direct.md).

Written offline from the manual and **not yet run against the Tweez 300 GUI**.
Pure computation, so the file format and the timing arithmetic are tested here
(tests/test_tweezers_patterns.py); what no test can check is whether the GUI
accepts what this writes. See "TO SETTLE ON THE MICROSCOPE PC" below.

WHY PATTERNS AT ALL, GIVEN TCP WORKS
------------------------------------
hardware/optical_tweezers.py already drives traps directly
(``TRAP_POSITION <name> <x> <y>``), so a pattern file is not needed to *place*
a trap. It is needed for anything timed, because the two paths have completely
different clocks:

    direct TCP     host-timed. One socket round trip per move, through the GUI
                   and System Manager. Millisecond-scale at best, jitter
                   unbounded and unmeasured.
    pattern        hardware-timed. The AOD trap loop advances one pattern point
                   per pass at the switching rate (up to 100 kHz), so the
                   trajectory is clocked by the instrument, not by Python.

For this lab that is not a performance nicety, it is a measurement-validity
choice. ``config/channels/active-microrheology-probe-tracer.yaml`` drives a
5 um probe on a bounded random walk at 0-30 um/s and reads force as
``F = kappa * (x_bead - x_trap)``. That subtraction needs ``x_trap`` as a
function of time to be *known*, and the TCP interface has no position readout
to check it against (manual ch. Command Reference -- the command set is
write-only, there is no query of any kind). A ``.tpf`` traversed at a fixed
switching rate gives an exactly known trajectory; TCP streaming gives one
contaminated by host jitter you cannot measure after the fact.

Two more things only patterns can do: multiple points illuminated per trap (a
light potential landscape -- one trap position cannot do it), and breakpoints,
where the trap halts mid-path until released by software or a hardware trigger.

SO: use direct TCP for setup and quasi-static placement, patterns for anything
whose timing enters the result.

THE FILE FORMAT (manual ch. Patterns, p. 55-56)
-----------------------------------------------
ASCII text, extension ``.tpf``. A header line names the columns, which may be
in any order; body lines are one point each.

    colX     x relative to the trap position, um            mandatory
    colY     y relative to the trap position, um            mandatory
    colStr   relative strength, 0-1, multiplied by the
             trap's own strength                            mandatory
    colBP    breakpoint bits                                optional
    colXB colYB colStrB    second point, Multitone traps    optional, not used here
    colFocus beam focus, if the trap has focus control      optional, not used here

Vendor samples: ``%Program Files%\\Aresis\\Tweez\\Samples\\Patterns``.

WAIT STATES, AND WHY THIS MODULE DUPLICATES POINTS INSTEAD
----------------------------------------------------------
The GUI slows a pattern with per-trap "wait states": a point is held for N
extra trap-loop passes. **Wait states are not in the TCP command set** -- only
``BEAM_SET_PARAMS`` (switching rate, blanking time), which is global and
changes every trap at once. So a Python-only workflow cannot set them.

``Pattern.dwell(n)`` gets the same effect by repeating each point n times in the
file, which is per-point rather than per-trap and therefore strictly more
flexible: you can slow one arc of a path and leave the rest fast.

But cost it out before reaching for it. The loop runs at 100 kHz and the wanted
motion is 0-30 um/s, so slowdown factors are ~1e3-1e4. For a 2000-point walk at
30 um/s with two traps in the loop, the three routes are: drop the global rate to
236 Hz (reachable over TCP, but the *other* trap then refreshes at 118 Hz, near
the edge of holding anything); keep 100 kHz and ``dwell(423)`` (846,000-point
file, ~20 MB -- whether the GUI loads that is untested); or per-trap wait states
of 422, which costs nothing and is the vendor's own answer (manual p. 12 uses
4999) but **cannot be set over TCP**.

Hence the recommended split: build a project in the GUI once with the traps and
their wait states, save it, and have Python ``LOAD_PROJECT`` it and drive
everything else. Per-experiment variation stays in Python; the GUI-only
properties sit in a file that does not change between runs. dwell() then earns
its keep only for *non-uniform* slowdown -- dwelling on one arc of a path and not
the rest -- which wait states cannot express at all.
See kb/decisions/2026-08-26-tweezers-pattern-vs-direct.md.

TO SETTLE ON THE MICROSCOPE PC
------------------------------
1. **``LOAD_PATTERN`` argument order.** The manual contradicts itself. The
   command list (p. 68) says ``LOAD_PATTERN <pattern name> <pattern file>``;
   the worked example (p. 69) writes ``LOAD_PATTERN Sample.tsf "Patt 1"`` --
   file first, name second, and with the wrong extension (``.tsf``, everywhere
   else ``.tpf``) and a relative path where the same page says "File paths are
   absolute". The example looks sloppy, so ``optical_tweezers.load_pattern``
   follows the command list, with a ``file_first=True`` switch to flip it in one
   line once the log says which is right. Watch the TCP/IP Svr log for -10
   (invalid command line) or -27 (invalid parameters).
2. **The trapping range is a trapezoid, not a rectangle** (manual: the GUI
   draws a "green trapezoid"), set by the AOD calibration. Points outside it
   are silently clipped to the edge and *not shown graphically* -- so an
   oversized generated pattern deforms with no error anywhere. ``fits_within``
   here only checks a rectangular half-width, which is a necessary condition,
   not a sufficient one. Read the real calibrated extent off the GUI and record
   it in the KB.
3. **Breakpoint width depends on the serial number**: 1 bit for SN < 130, 4
   bits at SN >= 130 (with Enable Bits / Release Bits masks, bitwise AND). The
   SN is in the GUI's Connections box. ``BREAKPOINT_BITS`` here is None until
   someone reads it.
4. **Decimal separator.** The manual says floats follow the Windows locale
   ("decimal comma or point"). ``to_tpf(decimal=",")`` exists for that; confirm
   which the lab PC uses before trusting a file it parsed without complaint.
5. **Trap-loop slot count.** The timing arithmetic needs the number of traps in
   the loop, because every trap costs one switching interval per pass. Passing
   it wrong scales every time and speed linearly, so read the real trap count
   rather than assuming the pattern is alone.

REFERENCE NUMBERS (manual p. 6, Tweez 305 with 60x NA 1.0 WI)
-------------------------------------------------------------
    AOD switching rate     up to 100 kHz
    trapping range         100 x 100 um max, 20 x 20 um typical
    trapped particles      up to ~1000, typically 1-10
    trapping force         up to ~800 pN, typically 1-50 pN
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace
from pathlib import Path

#: Breakpoint field width in bits: 1 for SN < 130, 4 for SN >= 130. None until
#: the lab's serial number is read off the GUI's Connections box -- see
#: "TO SETTLE ON THE MICROSCOPE PC" (3). While None, breakpoint values are
#: written as given and not range-checked.
BREAKPOINT_BITS: int | None = None

#: Highest AOD switching rate quoted for the Tweez 305 (manual p. 6). Used only
#: to flag a timing request that needs more than the hardware has.
MAX_SWITCHING_RATE_HZ = 100_000.0

#: Accepted pattern-file suffixes -- both, because the manual contradicts
#: itself and the contradiction cannot be resolved from the document.
#:
#: The Patterns chapter says a pattern is "a text (ASCII) file with extension
#: tpf" (pp. 55-56, twice). The Projects chapter says "Project file created by
#: Tweez 300 is an XML file with extension tpf" (p. 65). Those describe
#: different formats under the same extension, so one of them is wrong, and
#: ``tpf`` expands just as readily to "Tweez Project File" as to "Tweez Pattern
#: File". The single ``.tsf`` in the whole manual is the LOAD_PATTERN example
#: (p. 69), which would fit pattern=.tsf / project=.tpf.
#:
#: Refusing the correct extension would be worse than accepting both -- the GUI
#: validates content anyway, and a wrong-format file will be rejected there. To
#: settle it in one command on the microscope PC, list the vendor's own samples:
#: ``dir "%ProgramFiles%\Aresis\Tweez\Samples\Patterns"``.
PATTERN_SUFFIXES = frozenset({".tpf", ".tsf"})

_MANDATORY_COLUMNS = ("colX", "colY", "colStr")


class PatternError(ValueError):
    """Raised for a pattern that the Tweez 300 would reject or silently clip."""


@dataclass(frozen=True)
class PatternPoint:
    """One illuminated point, positioned relative to its trap's origin."""

    x_um: float
    y_um: float
    strength: float = 1.0
    breakpoint: int = 0

    def __post_init__(self) -> None:
        if not 0.0 <= self.strength <= 1.0:
            raise PatternError(
                f"strength must be in [0, 1] (relative to the trap's own "
                f"strength), got {self.strength}"
            )
        if self.breakpoint < 0:
            raise PatternError(f"breakpoint bits cannot be negative: {self.breakpoint}")
        if BREAKPOINT_BITS is not None and self.breakpoint >= 2**BREAKPOINT_BITS:
            raise PatternError(
                f"breakpoint {self.breakpoint} does not fit in "
                f"{BREAKPOINT_BITS} bit(s) on this system"
            )


@dataclass(frozen=True)
class TrapLoop:
    """The trap loop's timing, which is what turns a point list into a speed.

    Every trap costs one switching interval per pass, and a pattern-assigned
    trap contributes exactly one illuminated point per pass -- so a pattern's
    traversal time depends on how many *other* traps share the loop. Worked
    example from the manual (p. 11), reproduced in the tests: 3 traps at
    100 kHz is 30 us per pass, so a 200-point pattern traverses in 6 ms.
    """

    switching_rate_hz: float
    n_traps: int = 1

    def __post_init__(self) -> None:
        if self.switching_rate_hz <= 0:
            raise PatternError("switching rate must be positive")
        if self.n_traps < 1:
            raise PatternError("the loop needs at least one trap")
        if self.switching_rate_hz > MAX_SWITCHING_RATE_HZ:
            raise PatternError(
                f"{self.switching_rate_hz} Hz exceeds the quoted maximum "
                f"{MAX_SWITCHING_RATE_HZ} Hz (manual p. 6)"
            )

    @property
    def pass_time_s(self) -> float:
        """One trap-loop pass: one switching interval per trap."""
        return self.n_traps / self.switching_rate_hz


@dataclass(frozen=True)
class Pattern:
    """An ordered point list, ready to be written as a ``.tpf``.

    Order matters: the trap loop advances one point per pass, so the sequence
    *is* the trajectory. Generators below return points already in traversal
    order.
    """

    points: tuple[PatternPoint, ...]
    name: str = "pattern"

    def __post_init__(self) -> None:
        if not self.points:
            raise PatternError("a pattern needs at least one point")

    def __len__(self) -> int:
        return len(self.points)

    # ---- geometry ----

    @property
    def path_length_um(self) -> float:
        """Sum of segment lengths in traversal order, closing back to the first
        point -- patterns are traversed continuously by default, so the return
        leg is part of the cycle."""
        pts = self.points
        return sum(
            math.dist((a.x_um, a.y_um), (b.x_um, b.y_um))
            for a, b in zip(pts, pts[1:] + pts[:1])
        )

    @property
    def half_extent_um(self) -> tuple[float, float]:
        """Largest |x| and |y|, i.e. the half-width the trapping range must
        accommodate once this pattern sits on a trap at the origin."""
        return (
            max(abs(p.x_um) for p in self.points),
            max(abs(p.y_um) for p in self.points),
        )

    def fits_within(self, half_width_um: float, half_height_um: float | None = None):
        """Necessary-not-sufficient range check. See "TO SETTLE" (2): the real
        range is a calibrated trapezoid, so passing this does not prove the
        pattern is unclipped, but failing it proves it is."""
        half_height_um = half_width_um if half_height_um is None else half_height_um
        dx, dy = self.half_extent_um
        return dx <= half_width_um and dy <= half_height_um

    # ---- timing ----

    def traversal_time_s(self, loop: TrapLoop) -> float:
        """Seconds for one full traversal of this pattern."""
        return len(self.points) * loop.pass_time_s

    def mean_speed_um_s(self, loop: TrapLoop) -> float:
        """Average speed of the illumination point along the path.

        Mean, not instantaneous: points spaced unevenly move at uneven speed,
        since each takes the same time. Generators here space points evenly by
        arc length, so for them the two coincide.
        """
        return self.path_length_um / self.traversal_time_s(loop)

    def switching_rate_for_speed(self, speed_um_s: float, n_traps: int = 1) -> float:
        """The switching rate that would give ``speed_um_s``. Inverse of
        mean_speed_um_s, for picking BEAM_SET_PARAMS from a target speed.

        Remember the rate is global: every pattern-driven trap in the loop
        speeds up together. Per-trap speed is what dwell() is for.
        """
        if speed_um_s <= 0:
            raise PatternError("speed must be positive")
        return len(self.points) * n_traps * speed_um_s / self.path_length_um

    # ---- transforms ----

    def dwell(self, factor: int) -> Pattern:
        """Repeat every point ``factor`` times -- a per-point stand-in for the
        GUI's wait states, which TCP cannot set. factor=1 is a no-op."""
        if factor < 1:
            raise PatternError("dwell factor must be >= 1")
        return replace(
            self, points=tuple(p for p in self.points for _ in range(factor))
        )

    def scaled(self, factor: float) -> Pattern:
        """Scale in software. Prefer ``TRAP_PATT_SCALE`` over TCP when the
        pattern is already loaded -- this is for building a file."""
        return replace(
            self,
            points=tuple(
                replace(p, x_um=p.x_um * factor, y_um=p.y_um * factor)
                for p in self.points
            ),
        )

    def with_breakpoint_at(self, index: int, bits: int = 1) -> Pattern:
        """Mark one point as a breakpoint: the trap halts there until released
        (``TRAP_PATT_RELEASE_BP``, or a hardware trigger)."""
        pts = list(self.points)
        pts[index] = replace(pts[index], breakpoint=bits)
        return replace(self, points=tuple(pts))

    # ---- output ----

    def to_tpf(self, decimal: str = ".", precision: int = 4) -> str:
        """Render the pattern-file text. ``colBP`` is emitted only if some point
        actually carries a breakpoint, keeping the common file to three
        columns."""
        if decimal not in (".", ","):
            raise PatternError("decimal separator must be '.' or ','")
        has_bp = any(p.breakpoint for p in self.points)
        columns = list(_MANDATORY_COLUMNS) + (["colBP"] if has_bp else [])

        def num(value: float) -> str:
            text = f"{value:.{precision}f}"
            if float(text) == 0.0:
                text = f"{0.0:.{precision}f}"  # never emit "-0.0000"
            return text.replace(".", decimal)

        lines = ["\t".join(columns)]
        for p in self.points:
            row = [num(p.x_um), num(p.y_um), num(p.strength)]
            if has_bp:
                row.append(str(p.breakpoint))
            lines.append("\t".join(row))
        return "\n".join(lines) + "\n"

    def write(self, path: str | Path, decimal: str = ".", precision: int = 4) -> Path:
        """Write the pattern file. Windows line endings, since the consumer is a
        Windows GUI reading an ASCII file.

        Both ``.tpf`` and ``.tsf`` are accepted, because the manual does not
        actually settle which one a pattern uses -- see PATTERN_SUFFIXES.
        """
        out = Path(path)
        if out.suffix.lower() not in PATTERN_SUFFIXES:
            raise PatternError(
                f"pattern files should end in one of "
                f"{sorted(PATTERN_SUFFIXES)}, got {out.name!r}"
            )
        out.write_text(
            self.to_tpf(decimal=decimal, precision=precision),
            encoding="ascii",
            newline="\r\n",
        )
        return out


# ---- generators, points in traversal order ----------------------------


def circle(radius_um: float, n_points: int, strength: float = 1.0) -> Pattern:
    """Closed circular path -- the manual's own example, and the usual shape
    for cyclic driving."""
    if radius_um <= 0:
        raise PatternError("radius must be positive")
    if n_points < 3:
        raise PatternError("a circle needs at least 3 points")
    step = 2 * math.pi / n_points
    return Pattern(
        tuple(
            PatternPoint(
                radius_um * math.cos(i * step),
                radius_um * math.sin(i * step),
                strength,
            )
            for i in range(n_points)
        ),
        name=f"circle_r{radius_um:g}um_n{n_points}",
    )


def oscillation(
    amplitude_um: float,
    n_points: int,
    angle_deg: float = 0.0,
    strength: float = 1.0,
) -> Pattern:
    """Straight there-and-back sweep, closed so continuous traversal gives a
    clean triangular drive -- the active-microrheology shape.

    ``n_points`` is the total, so the two legs get half each; an odd count
    raises rather than silently making the legs unequal, which would put a
    spurious asymmetry into the drive.
    """
    if amplitude_um <= 0:
        raise PatternError("amplitude must be positive")
    if n_points < 4 or n_points % 2:
        raise PatternError("n_points must be even and >= 4 (two equal legs)")
    theta = math.radians(angle_deg)
    ux, uy = math.cos(theta), math.sin(theta)
    # Forward leg runs -A..+A inclusive over k points; the return leg reuses the
    # k-2 interior ones, so neither turning point is illuminated twice in a
    # cycle. Total is 2k-2, hence k = (n+2)/2.
    per_leg = (n_points + 2) // 2
    forward = [
        -amplitude_um + 2 * amplitude_um * i / (per_leg - 1) for i in range(per_leg)
    ]
    back = list(reversed(forward))[1:-1]
    coords = forward + back
    return Pattern(
        tuple(PatternPoint(s * ux, s * uy, strength) for s in coords),
        name=f"oscillation_a{amplitude_um:g}um_n{len(coords)}",
    )


def raster(
    width_um: float,
    height_um: float,
    nx: int,
    ny: int,
    strength: float = 1.0,
    serpentine: bool = True,
) -> Pattern:
    """Rectangular grid, centred on the trap -- a light potential landscape
    when traversed fast enough to look continuous.

    ``serpentine`` reverses alternate rows so consecutive points stay adjacent;
    with it off, each row ends with a jump back across the whole width, which
    for a *moving* trap is a real retrace and for a quasi-static landscape does
    not matter.
    """
    if nx < 1 or ny < 1:
        raise PatternError("nx and ny must be >= 1")
    xs = [(-width_um / 2 + width_um * i / (nx - 1)) if nx > 1 else 0.0 for i in range(nx)]
    ys = [(-height_um / 2 + height_um * j / (ny - 1)) if ny > 1 else 0.0 for j in range(ny)]
    points: list[PatternPoint] = []
    for j, y in enumerate(ys):
        row = xs if (not serpentine or j % 2 == 0) else list(reversed(xs))
        points.extend(PatternPoint(x, y, strength) for x in row)
    return Pattern(tuple(points), name=f"raster_{nx}x{ny}")


def bounded_random_walk(
    n_points: int,
    step_um: float,
    half_width_um: float,
    seed: int,
    strength: float = 1.0,
) -> Pattern:
    """Bounded random walk, the drive in
    ``config/channels/active-microrheology-probe-tracer.yaml``.

    ``seed`` is required, not optional. The whole reason to bake the walk into a
    pattern rather than stream it over TCP is that the drive trajectory has to
    be exactly known to get ``F = kappa * (x_bead - x_trap)``; an unseeded walk
    would be unreproducible, which throws that away. Record the seed with the
    acquisition.

    Steps are fixed-length with a uniformly random direction, reflected at a
    square boundary. Reflection rather than rejection keeps the step count and
    therefore the timing exact -- with rejection the traversal time would
    depend on how often the walk hit the wall.
    """
    if n_points < 2:
        raise PatternError("a walk needs at least 2 points")
    if step_um <= 0:
        raise PatternError("step must be positive")
    if half_width_um <= step_um:
        raise PatternError("the boundary must be wider than one step")
    rng = random.Random(seed)
    x = y = 0.0
    points = [PatternPoint(x, y, strength)]
    for _ in range(n_points - 1):
        angle = rng.uniform(0, 2 * math.pi)
        x += step_um * math.cos(angle)
        y += step_um * math.sin(angle)
        # reflect back inside the box, repeatedly in case of a corner
        while not (-half_width_um <= x <= half_width_um):
            x = -2 * half_width_um - x if x < 0 else 2 * half_width_um - x
        while not (-half_width_um <= y <= half_width_um):
            y = -2 * half_width_um - y if y < 0 else 2 * half_width_um - y
        points.append(PatternPoint(x, y, strength))
    return Pattern(tuple(points), name=f"walk_n{n_points}_seed{seed}")
