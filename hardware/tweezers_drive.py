"""Trap drive spec -> pattern, timing plan, and the TCP command sequence.

The planning layer over hardware/tweezers_patterns.py (format, geometry and
trap-loop timing) and hardware/optical_tweezers.py (the socket). Route decided
2026-08-26: the drive is a generated ``.tpf``, not TCP position streaming --
``kb/decisions/2026-08-26-tweezers-pattern-vs-direct.md``.

Everything here is pure computation, so a plan can be reviewed offline before
anything reaches the instrument. ``plan()`` reports rather than decides where an
input is missing: with the trapping range unknown it returns ``BLOCKED`` for the
range check instead of passing it, matching the gate idiom used across the lens
packages (docs/05-consensus-gate.md).

The one thing a spec cannot express is per-trap **wait states**, which are the
vendor's mechanism for slow driven motion and are GUI-only. So the intended
shape is a GUI-built project template carrying the traps and their wait states,
loaded over ``LOAD_PROJECT``, with the pattern and everything else generated per
experiment from here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from hardware.tweezers_patterns import (
    MAX_SWITCHING_RATE_HZ,
    Pattern,
    PatternError,
    TrapLoop,
    bounded_random_walk,
    circle,
    oscillation,
    raster,
)

#: Slowdown mechanisms, and whether Python can set them. See the module
#: docstring and the decision note: ``wait_states`` is the vendor's answer and
#: is not in the TCP command set, which is why a project template exists.
SLOWDOWN_KINDS = ("wait_states", "dwell", "switching_rate")

_SHAPES = {
    "circle": circle,
    "oscillation": oscillation,
    "raster": raster,
    "bounded_random_walk": bounded_random_walk,
}

#: A trap has to be revisited often enough to hold a particle. The manual's own
#: slow-path example runs the loop at 50 Hz, and its semi-continuous discussion
#: puts a few-um particle's self-diffusion time at ~50 ms -- so ~20 Hz is about
#: where "held" stops being a safe assumption. Advisory only: this is read off
#: the manual's worked examples, not measured here, and the real threshold
#: depends on particle size, trap strength and medium viscosity.
MIN_TRAP_REFRESH_HZ = 20.0


@dataclass(frozen=True)
class SlowdownRoute:
    """One way to reach the target speed, and what it costs."""

    kind: str
    factor: float
    python_settable: bool
    cost: str


@dataclass(frozen=True)
class DrivePlan:
    """Everything a human needs to approve before this touches the laser."""

    name: str
    trap: str
    pattern_name: str
    project: str | None
    pattern: Pattern
    loop: TrapLoop
    target_speed_um_s: float
    routes: tuple[SlowdownRoute, ...]
    chosen: SlowdownRoute
    range_status: str  # OK | FAIL | BLOCKED
    range_note: str
    calibration: dict
    field_calibration: dict
    project_problem: str | None = None

    @property
    def native_speed_um_s(self) -> float:
        """Speed with no slowdown at all, at the spec's switching rate."""
        return self.pattern.mean_speed_um_s(self.loop)

    @property
    def slowdown_factor(self) -> float:
        return self.native_speed_um_s / self.target_speed_um_s

    @property
    def wait_states(self) -> int:
        """Wait states the project template has to carry. 0 for the routes that
        do the slowdown in the file or on the clock instead."""
        if self.chosen.kind != "wait_states":
            return 0
        return round(self.slowdown_factor) - 1

    @property
    def blockers(self) -> tuple[str, ...]:
        """Why this plan is not ready to run, if it is not."""
        out: list[str] = []
        if self.range_status != "OK":
            out.append(f"range check {self.range_status}")
        if self.project_problem:
            out.append(self.project_problem)
        field_obj = (self.field_calibration or {}).get("objective")
        cal_obj = (self.calibration or {}).get("objective")
        if cal_obj and field_obj and field_obj != cal_obj:
            out.append(
                f"the AOD trapping-field calibration was taken with "
                f"{field_obj!r} but this drive runs {cal_obj!r}. LOAD_PROJECT "
                "does not restore it -- it is System Manager state, not GUI "
                "state -- and the manual calls redoing it 'particularly "
                "important' for micro rheology"
            )
        if cal_obj and not field_obj:
            out.append(
                "field_calibration.objective not recorded. The project template "
                "restores the GUI calibration but not the AOD field response, "
                "so nothing here can tell whether it matches this objective"
            )
        if not (self.calibration or {}).get("objective"):
            out.append(
                "calibration.objective not recorded -- the um coordinates below "
                "are only meaningful for the objective the Tweez GUI was "
                "calibrated with, and neither Tweez calibration is readable "
                "over TCP"
            )
        if self.chosen.kind == "wait_states" and self.project is None:
            out.append(
                f"the wait_states route needs {self.wait_states} wait states on "
                f"trap {self.trap!r}, which TCP cannot set -- give a `project:` "
                "template built in the GUI, or pick another slowdown route"
            )
        return tuple(out)

    @property
    def advances(self) -> bool:
        """Whether this plan is fit to run.

        wait_states is a legitimate choice -- it is the vendor's own mechanism --
        but only once a GUI-built project supplies them, so it advances on
        `project:` being set rather than on being Python-settable.
        """
        return not self.blockers

    def effective_cycle_time_s(self) -> float:
        """One full pattern cycle as it will actually run, wait states included.

        dwell() duplicates points in place, so a dwelled pattern has the same
        path length and its traversal time already carries the slowdown; wait
        states do not appear in the file at all and have to be applied here.
        """
        run_loop = TrapLoop(self.switching_rate_hz(), n_traps=self.loop.n_traps)
        return self.emitted_pattern().traversal_time_s(run_loop) * (1 + self.wait_states)

    def effective_speed_um_s(self) -> float:
        return self.pattern.path_length_um / self.effective_cycle_time_s()

    def emitted_pattern(self) -> Pattern:
        """The pattern as it will be written. Only the ``dwell`` route changes
        the file; the other two leave it alone and change the clock."""
        if self.chosen.kind == "dwell":
            return self.pattern.dwell(int(round(self.slowdown_factor)))
        return self.pattern

    def switching_rate_hz(self) -> float:
        """The rate to send in ``BEAM_SET_PARAMS``."""
        if self.chosen.kind == "switching_rate":
            return self.loop.switching_rate_hz / self.slowdown_factor
        return self.loop.switching_rate_hz

    def report(self) -> str:
        p = self.pattern
        dx, dy = p.half_extent_um
        emitted = self.emitted_pattern()
        rate = self.switching_rate_hz()
        run_loop = TrapLoop(rate, n_traps=self.loop.n_traps)
        cal = self.calibration or {}
        fcal = self.field_calibration or {}
        lines = [
            f"drive plan: {self.name}",
            f"  trap {self.trap!r}  pattern {self.pattern_name!r}"
            f"  project {self.project or '<none: use what the GUI has open>'}",
            "",
            f"  pattern      {p.name}",
            f"    points     {len(p)}"
            + (f"  ->  {len(emitted)} emitted (dwell)" if len(emitted) != len(p) else ""),
            f"    path       {p.path_length_um:.2f} um per cycle (closed)",
            f"    extent     +/-{dx:.2f} x +/-{dy:.2f} um from the trap origin",
            "",
            f"  trap loop    {self.loop.n_traps} traps @ "
            f"{self.loop.switching_rate_hz:,.0f} Hz -> "
            f"{self.loop.pass_time_s * 1e6:.1f} us per pass",
            f"    native     {self.native_speed_um_s:,.1f} um/s",
            f"    target     {self.target_speed_um_s:,.1f} um/s"
            f"  -> slowdown x{self.slowdown_factor:,.0f}",
            "",
            "  slowdown routes:",
        ]
        for r in self.routes:
            mark = ">>" if r.kind == self.chosen.kind else "  "
            reach = "python" if r.python_settable else "GUI ONLY"
            lines.append(f"   {mark} {r.kind:16} x{r.factor:<12,.0f} [{reach}]  {r.cost}")
        lines += [
            "",
            "  as it will run:",
            f"    switching rate   {rate:,.0f} Hz  (BEAM_SET_PARAMS)",
            f"    file points      {len(emitted):,}",
            f"    wait states      {self.wait_states:,}"
            + ("  <- from the project template, not from here" if self.wait_states else ""),
            f"    cycle time       {self.effective_cycle_time_s():.3f} s",
            f"    mean speed       {self.effective_speed_um_s():,.2f} um/s",
            f"    other traps see  {1 / run_loop.pass_time_s:,.0f} Hz refresh",
            "",
            "  calibration (recorded, NOT verifiable from here):",
            f"    objective        {cal.get('objective') or '<UNRECORDED>'}",
            f"    tweez camera     {cal.get('camera') or '<unrecorded>'}",
            f"    um per px        {cal.get('um_per_px') or '<unrecorded>'}",
            f"    taken            {cal.get('taken') or '<unrecorded>'}",
            f"    field cal for   {fcal.get('objective') or '<UNRECORDED>'}"
            f"  (taken {fcal.get('taken') or '?'})",
            "    GUI cal (magnification + beam position) travels in the project;",
            "    the AOD field cal does NOT -- it is System Manager state, saved",
            "    and loaded from its own File menu (manual pp.28-32 vs 35-38)",
            "",
            f"  range check   {self.range_status}: {self.range_note}",
            f"  advances      {'YES' if self.advances else 'NO'}",
        ]
        for blocker in self.blockers:
            lines.append(f"    blocked by   {blocker}")
        return "\n".join(lines)


def resolve_project(spec: dict) -> tuple[str | None, str | None]:
    """Pick the project template for the objective this spec is calibrated for.

    ``project:`` may be a single path or a mapping keyed by Nosepiece label. The
    mapping is the form that answers "load the project for the magnification I
    want": one template per objective, each carrying that objective's GUI
    calibration (manual p. 65 -- a project stores "GUI settings (including the
    camera settings and calibration)").

    Returns ``(path, problem)``; ``problem`` is None when the lookup succeeded.
    """
    project = spec.get("project")
    if project is None or isinstance(project, str):
        return project, None
    if not isinstance(project, dict):
        return None, f"project: must be a path or a mapping, got {type(project).__name__}"
    objective = (spec.get("calibration") or {}).get("objective")
    if not objective:
        return None, "project: is per-objective but calibration.objective is unset"
    if objective not in project:
        return None, (
            f"no project template for objective {objective!r}; "
            f"have {sorted(project)}"
        )
    return project[objective], None


def load_spec(path: str | Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def build_pattern(spec: dict) -> Pattern:
    """Instantiate the spec's ``pattern:`` block.

    Unknown keys raise rather than being ignored -- a typo'd parameter that
    silently falls back to a generator default would change the trajectory
    without changing the spec, and the spec is the record.
    """
    block = dict(spec.get("pattern") or {})
    shape = block.pop("shape", None)
    if shape not in _SHAPES:
        raise PatternError(
            f"unknown pattern shape {shape!r}; expected one of {sorted(_SHAPES)}"
        )
    generator = _SHAPES[shape]
    allowed = generator.__code__.co_varnames[: generator.__code__.co_argcount]
    unknown = sorted(set(block) - set(allowed))
    if unknown:
        raise PatternError(
            f"{shape}: unknown parameter(s) {unknown}; accepts {list(allowed)}"
        )
    return generator(**block)


def _routes(
    native_um_s: float, target_um_s: float, loop: TrapLoop, len_points: int
) -> tuple[SlowdownRoute, ...]:
    factor = native_um_s / target_um_s
    reduced_rate = loop.switching_rate_hz / factor
    refresh_hz = reduced_rate / loop.n_traps
    return (
        SlowdownRoute(
            "wait_states",
            round(factor) - 1,
            python_settable=False,
            cost="free, and the vendor's own mechanism -- but not in the TCP "
            "command set, so it has to come from a GUI-built project",
        ),
        SlowdownRoute(
            "dwell",
            round(factor),
            python_settable=True,
            cost=f"file grows {round(factor):,}x, to "
            f"{round(factor) * len_points:,} points; whether the GUI loads one "
            "that large is untested",
        ),
        SlowdownRoute(
            "switching_rate",
            round(factor),
            python_settable=True,
            cost=f"global: rate drops to {reduced_rate:,.0f} Hz and every other "
            f"trap refreshes at only {refresh_hz:,.0f} Hz"
            + ("  <-- BELOW the advisory hold threshold" if refresh_hz < MIN_TRAP_REFRESH_HZ else ""),
        ),
    )


def plan(spec: dict) -> DrivePlan:
    """Turn a spec into a reviewable plan. Touches no hardware."""
    pattern = build_pattern(spec)
    loop_block = spec.get("loop") or {}
    loop = TrapLoop(
        switching_rate_hz=float(loop_block.get("switching_rate_hz", MAX_SWITCHING_RATE_HZ)),
        n_traps=int(loop_block.get("n_traps", 1)),
    )
    drive = spec.get("drive") or {}
    target = float(drive.get("target_speed_um_s", 0) or 0)
    if target <= 0:
        raise PatternError("drive.target_speed_um_s must be positive")
    kind = drive.get("slowdown", "wait_states")
    if kind not in SLOWDOWN_KINDS:
        raise PatternError(f"drive.slowdown must be one of {list(SLOWDOWN_KINDS)}")

    native = pattern.mean_speed_um_s(loop)
    if native < target:
        raise PatternError(
            f"the pattern already runs at {native:.2f} um/s, slower than the "
            f"{target:.2f} um/s target -- raise the switching rate or add points"
        )
    routes = _routes(native, target, loop, len(pattern))
    chosen = next(r for r in routes if r.kind == kind)

    rng = spec.get("trapping_range") or {}
    half_w, half_h = rng.get("half_width_um"), rng.get("half_height_um")
    if half_w is None or half_h is None:
        status = "BLOCKED"
        note = (
            "trapping_range not recorded. The real range is a calibrated "
            "trapezoid and depends on the objective in use; read it off the GUI"
        )
    elif pattern.fits_within(float(half_w), float(half_h)):
        dx, dy = pattern.half_extent_um
        status = "OK"
        note = (
            f"+/-{dx:.2f} x +/-{dy:.2f} um inside the recorded "
            f"+/-{float(half_w):.2f} x +/-{float(half_h):.2f} um "
            "(rectangular check only; the real edge is a trapezoid)"
        )
    else:
        dx, dy = pattern.half_extent_um
        status = "FAIL"
        note = (
            f"+/-{dx:.2f} x +/-{dy:.2f} um exceeds the recorded "
            f"+/-{float(half_w):.2f} x +/-{float(half_h):.2f} um -- points "
            "outside are silently clipped to the edge"
        )

    project_path, project_problem = resolve_project(spec)
    return DrivePlan(
        name=str(spec.get("name", "unnamed")),
        trap=str(spec.get("trap", "Trap 1")),
        pattern_name=str(spec.get("pattern_name", "Pattern 1")),
        project=project_path,
        project_problem=project_problem,
        pattern=pattern,
        loop=loop,
        target_speed_um_s=target,
        routes=routes,
        chosen=chosen,
        range_status=status,
        range_note=note,
        calibration=spec.get("calibration") or {},
        field_calibration=spec.get("field_calibration") or {},
    )


def command_sequence(plan_: DrivePlan, tpf_path: str, file_first: bool = False,
                     blanking_time_us: float = 0.0) -> tuple[str, ...]:
    """The TCP command lines this plan implies, in order.

    Returned as text so they can be read and approved before a socket is
    opened. Deliberately excludes ``LASER_ON`` -- arming a class-4 laser is not
    something a generated sequence should slip into the middle of a list.
    ``TRAP_ON`` is included: it only routes the beam to a trap that the laser
    has to already be on for.

    That is not a guarantee the sequence cannot emit light, though: a project
    file carries "the state of the laser operation and beam setting" (manual
    p. 65), so a ``LOAD_PROJECT`` at the head of this list can restore a saved
    laser-on state. Save templates with the laser off.
    """

    def q(text: str) -> str:
        return f'"{text}"' if " " in text else text

    lines: list[str] = []
    if plan_.project:
        lines.append(f"LOAD_PROJECT {q(plan_.project)}")
    rate = plan_.switching_rate_hz()
    # BEAM_SET_PARAMS carries the blanking time as well as the rate, so this one
    # line overwrites *both* of the GUI's standing values -- there is no way to
    # set the rate alone. ``blanking_time_us`` therefore defaults to 0 only
    # because that is what the interface makes us send when nobody has read the
    # GUI's own number; pass the real one whenever it is known. Observed on the
    # microscope PC 2026-08-27: rate 50 kHz, blanking 3 us.
    lines.append(f"BEAM_SET_PARAMS {rate:.0f} {blanking_time_us:g}")
    args = (
        (tpf_path, plan_.pattern_name) if file_first else (plan_.pattern_name, tpf_path)
    )
    lines += [
        f"LOAD_PATTERN {q(args[0])} {q(args[1])}",
        f"TRAP_ASSIGN_PATTERN {q(plan_.trap)} {q(plan_.pattern_name)}",
        f"TRAP_POSITION {q(plan_.trap)} 0 0",
        f"TRAP_STRENGTH {q(plan_.trap)} 1",
        f"TRAP_ON {q(plan_.trap)}",
    ]
    return tuple(lines)


def blanking_time_note(rate_hz: float, blanking_time_us: float = 0.0) -> str:
    """``BEAM_SET_PARAMS`` takes a blanking time in us alongside the rate, so
    sending it overwrites whatever the GUI held. Report what will be sent and
    flag when it is obviously wrong: blanking has to be short against the dwell
    per point, and a 0 silently discards the GUI's own value."""
    dwell_us = 1e6 / rate_hz
    if not blanking_time_us:
        verdict = (
            "sending 0, which OVERWRITES the GUI's blanking time -- read it off "
            "the GUI and pass --blanking-us to keep it"
        )
    elif blanking_time_us >= 0.5 * dwell_us:
        verdict = (
            f"sending {blanking_time_us:g} us, which is {100 * blanking_time_us / dwell_us:.0f}% "
            "of the dwell -- too long, the trap is dark most of each pass"
        )
    else:
        verdict = (
            f"sending {blanking_time_us:g} us = "
            f"{100 * blanking_time_us / dwell_us:.2f}% of the dwell"
        )
    return f"one switching interval is {dwell_us:.2f} us; {verdict}"
