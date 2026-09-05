"""Trap a particle the tracker found: px -> um, and confirm the trap by driving it.

    # 1. confirm a trap. TCP only -- touches no camera, watch it in the GUI.
    python config/tweezers/trap_from_tracking.py sine --create --amp-um 5 --freq-hz 1

    # 2. the same sine, but with the camera tracking the bead, which MEASURES
    #    the px <-> um transform instead of assuming it.
    python config/tweezers/trap_from_tracking.py calibrate --cfg CFG --amp-um 5

    # 3. once calibrated: detect isolated beads and put the trap on one.
    python config/tweezers/trap_from_tracking.py trap --cfg CFG --nearest-centre

TWO COORDINATE SYSTEMS, AND ONLY ONE OF THEM IS KNOWN
-----------------------------------------------------
The tracker works in **pixels from the top-left corner**. ``TRAP_POSITION``
takes **um**, and the user states its origin is the centre of the field of view
(2026-09-04). Those two facts are not enough to convert between them, and the
gap is the whole reason this module exists.

The Tweez GUI's *Beam Position* calibration is documented as
**LCS<->ICS: rotation + translation + scale** (manual pp.35-38,
kb/decisions/2026-08-26-tweezers-pattern-vs-direct.md). So the map from image
pixels to trap um carries an unknown **rotation** and an unknown **handedness**
on top of the scale -- eight orientations agree with "the origin is the centre",
and seven of them send the trap to a mirrored or rotated position. Nothing in
the TCP interface reads the calibration back: 52 command names were probed on
2026-08-27 and every one answered -11, so there is no query to ask. Guessing the
signs is not a shortcut, it is a coin flip taken four times.

**So the transform is measured here, by the confirmation the user already
wanted.** A trapped bead driven at 5 um and 1 Hz in x moves the bead's *pixel*
position at 1 Hz too; fitting that pixel series against the commanded drive
gives one full column of the matrix -- magnitude, sign and cross-axis term
together. Repeat in y and the matrix is complete. Untrapped neighbours have no
1 Hz component at all, which is why the same measurement doubles as the trap
confirmation: an amplitude that comes back near zero means the bead is not held,
and that is reported rather than fitted around.

The fit is checked against what the calibration is documented to be. A
rotation+translation+scale map has **equal singular values**, so a large
anisotropy means something else happened -- the bead slipped, or drifted, or the
seed picked the wrong particle. ``det < 0`` is expected rather than alarming:
image y runs downwards.

WHY TCP STREAMING HERE, AGAINST THIS REPO'S OWN DECISION
--------------------------------------------------------
``kb/decisions/2026-08-26-tweezers-pattern-vs-direct.md`` chose a generated
``.tpf`` over TCP position streaming. That decision stands for its own case and
not for this one. It was made because the force readout
``F = kappa (x_bead - x_trap)`` needs ``x_trap(t)`` known exactly, and a
host-timed stream only knows it to the host clock. **A trap confirmation reads
no force**, so the objection does not apply, and streaming avoids the two
GUI-only properties that made a correct pattern look broken on 2026-08-27:
``Repeat > Enabled`` defaults to False (the pattern traverses once and parks)
and ``Breakpoints > Enable Bits`` is ``0000`` on this system, which reduces
every breakpoint to nothing with no error anywhere.

The stream is still logged. ``x_trap(t)`` is unreadable after the fact --
nothing in this repo can recover it -- so ``--log`` writes the commanded series
with host timestamps, and that file is the only record there will be.

Timing is comfortable rather than tight: ``TRAP_POSITION`` round-trips in 1.9 ms
and ``send_command`` sleeps out a 10 ms floor before each send
(MIN_COMMAND_GAP_S), so the 50 Hz default has ~10 ms of slack per tick and the
floor caps this route near 100 Hz. At 50 Hz a 5 um 1 Hz sine steps 0.63 um at
the zero crossing, far below anything a 5 um bead resolves.

THE CAMERA IS SHARED WITH THE TWEEZ GUI, AND THE ORDER MATTERS
--------------------------------------------------------------
PVCAM hands a Kinetix to one process at a time. The Tweez GUI takes a body,
uses it, and releases it; ``sine`` needs no camera at all, so it runs while the
GUI still holds one. ``calibrate`` and ``trap`` need the camera, so the GUI must
have released it first -- and TCP trap commands keep working after the release,
which is what makes the closed loop possible at all (kb/systems/current.md >
"Kinetix cameras -- shared with the optical-tweezers GUI").

WHAT THIS NEVER DOES
--------------------
It never sends ``LASER_ON``. Arming belongs with a human at the interlocks, and
2026-08-27 recorded that as a rule rather than an accident. Laser power is
neither settable nor *readable* over TCP, so it is an acquisition parameter that
disappears unless someone writes it down -- ``--laser-note`` puts it in the log,
which is the only place it can go.

It also never clamps a position. Points outside the calibrated trapezoid are
**silently clipped by the GUI and not drawn**, so an over-large amplitude
deforms the drive with no error on either side; ``--max-offset-um`` refuses
instead.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from config.session.analyse_wall_diffusion import (  # noqa: E402
    OFFSET_ADU,
    detect,
    refine,
)

#: Where a measured transform is kept. Objective-specific by nature, so the
#: objective is inside the file and checked on load, not encoded in the name.
DEFAULT_CAL = REPO / "config" / "tweezers" / "px-to-trap-um.yaml"

#: Trap position command rate. See the module docstring for why 50 is
#: comfortable and ~100 is the ceiling.
STREAM_HZ = 50.0

#: Refuse a commanded offset past this. NOT a clamp: the GUI clips silently.
MAX_OFFSET_UM = 20.0

#: A rotation+translation+scale map has equal singular values. Past this the fit
#: is not describing that map and should not be trusted.
MAX_ANISOTROPY = 0.05

#: Bead response should be near in-phase with a stiff trap at 1 Hz. A large
#: quadrature component means it is lagging, i.e. barely held. Not zero even
#: for a perfect trap: a 33 ms exposure reports the mid-exposure position,
#: which is 6 deg at 1 Hz, and the tick that grabs the frame after sending the
#: position adds its own. So the alarm is set well clear of the instrumental
#: part rather than at zero -- and `column_from_fit` takes the lag out of the
#: amplitude, so a lag inside this bound costs accuracy nothing.
MAX_LAG_DEG = 45.0

#: How much of the response the single-common-phase model fails to explain.
#: Past this the two axes are not moving as one rigid map.
MAX_RESIDUAL = 0.20

#: An amplitude this far below the commanded one is not a trapped bead.
MIN_FOLLOW_FRAC = 0.5


# --------------------------------------------------------------------------
# the transform
# --------------------------------------------------------------------------

@dataclass
class TrapTransform:
    """Pixels <-> trap um, as measured, with what it was measured on.

    ``b`` is px per um: ``px = p0 + b @ um``. Stored in that direction because
    that is the direction it is fitted in -- the drive commands um and the
    camera answers in px -- and inverting once on load is cheaper than
    pretending the fit went the other way.
    """

    b: list          # 2x2, px per um
    p0: list         # px position of trap (0, 0)
    objective: str
    camera: str
    frame_shape: list
    nominal_um_per_px: float
    fitted_um_per_px: float
    anisotropy: float
    rotation_deg: float
    handedness: int
    lag_deg: list
    follow_frac: list
    residual: list
    amp_um: float
    freq_hz: float
    taken: str
    note: str = ""

    @property
    def matrix(self) -> np.ndarray:
        return np.asarray(self.b, dtype=float)

    def to_um(self, px) -> np.ndarray:
        """Pixel coordinates -> trap um."""
        px = np.asarray(px, dtype=float)
        return np.linalg.solve(self.matrix, (px - np.asarray(self.p0)).T).T

    def to_px(self, um) -> np.ndarray:
        """Trap um -> pixel coordinates."""
        um = np.asarray(um, dtype=float)
        return (self.matrix @ um.T).T + np.asarray(self.p0)

    @property
    def problems(self) -> tuple[str, ...]:
        out = []
        if self.anisotropy > MAX_ANISOTROPY:
            out.append(
                f"anisotropy {self.anisotropy:.1%} > {MAX_ANISOTROPY:.0%}: the "
                "GUI calibration is documented as rotation+translation+scale, "
                "which has equal singular values, so this fit is describing "
                "something else -- a slipping bead, drift, or the wrong seed")
        for ax, lag in zip("xy", self.lag_deg):
            if abs(lag) > MAX_LAG_DEG:
                out.append(f"{ax} drive lags by {lag:+.0f} deg "
                           f"(> {MAX_LAG_DEG:.0f}): bead barely held")
        for ax, frac in zip("xy", self.follow_frac):
            if frac < MIN_FOLLOW_FRAC:
                out.append(f"{ax} bead followed only {frac:.0%} of the "
                           "commanded amplitude: not trapped")
        for ax, res in zip("xy", self.residual):
            if res > MAX_RESIDUAL:
                out.append(f"{ax} response is {res:.0%} unexplained by one "
                           "common phase: the two axes are not moving as one "
                           "rigid map")
        return tuple(out)

    def report(self) -> str:
        b = self.matrix
        c = np.asarray(self.p0, dtype=float)
        lines = [
            f"px <-> trap um, measured {self.taken} on {self.objective} / "
            f"{self.camera}",
            f"  px = p0 + B @ um,  B = [[{b[0, 0]:+8.3f} {b[0, 1]:+8.3f}]",
            f"                          [{b[1, 0]:+8.3f} {b[1, 1]:+8.3f}]] px/um",
            f"  p0 (trap 0,0) = ({c[0]:.1f}, {c[1]:.1f}) px",
        ]
        if self.frame_shape:
            h, w = self.frame_shape
            off = math.hypot(c[0] - w / 2, c[1] - h / 2)
            lines.append(
                f"  frame centre  = ({w / 2:.1f}, {h / 2:.1f}) px -- the trap "
                f"origin sits {off:.1f} px "
                f"({off * self.fitted_um_per_px:.2f} um) from it")
        lines += [
            f"  scale      {self.fitted_um_per_px:.5f} um/px fitted against "
            f"{self.nominal_um_per_px:.5f} nominal "
            f"({self.fitted_um_per_px / self.nominal_um_per_px - 1:+.1%})",
            f"  rotation   {self.rotation_deg:+.1f} deg, handedness "
            f"{self.handedness:+d} "
            + ("(flipped -- expected, image y runs down)"
               if self.handedness < 0 else "(not flipped)"),
            f"  anisotropy {self.anisotropy:.2%} "
            f"(<= {MAX_ANISOTROPY:.0%} for a similarity)",
            f"  drive      {self.amp_um:.2f} um at {self.freq_hz:.3f} Hz; bead "
            f"followed {self.follow_frac[0]:.0%} (x) / "
            f"{self.follow_frac[1]:.0%} (y), lag {self.lag_deg[0]:+.0f} / "
            f"{self.lag_deg[1]:+.0f} deg",
        ]
        for p in self.problems:
            lines.append(f"  PROBLEM: {p}")
        return "\n".join(lines)


def save_transform(t: TrapTransform, path: Path) -> None:
    header = (
        "# px <-> trap um, MEASURED by driving a trapped bead. Not editable by\n"
        "# hand in any useful way: the signs and the cross terms come out of a\n"
        "# fit, and the TCP interface has no way to read the GUI calibration\n"
        "# back to check a guess against.\n"
        "#\n"
        "# Objective-specific, and BOTH Tweez calibrations are invalidated by an\n"
        "# objective change with nothing on either side reporting it. The\n"
        "# objective is recorded below and checked on load for that reason.\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + yaml.safe_dump(asdict(t), sort_keys=False),
                    encoding="utf-8")


def load_transform(path: Path) -> TrapTransform:
    if not path.exists():
        raise SystemExit(
            f"REFUSED: no measured transform at {path}.\n"
            "  Run `calibrate` first. This tool will not guess the px->um\n"
            "  signs: the Beam Position calibration is a rotation as well as a\n"
            "  scale, so eight orientations fit 'the origin is the centre' and\n"
            "  seven of them send the trap somewhere else.")
    return TrapTransform(**yaml.safe_load(path.read_text(encoding="utf-8")))


# --------------------------------------------------------------------------
# the drive
# --------------------------------------------------------------------------

def sine_schedule(amp_um, freq_hz, axis, cycles, rate_hz, centre):
    """The commanded (t, x, y) series, computed up front so it can be checked."""
    n = max(2, int(round(cycles * rate_hz / freq_hz)))
    out = []
    for i in range(n + 1):
        t = i / rate_hz
        d = amp_um * math.sin(2 * math.pi * freq_hz * t)
        x = centre[0] + (d if axis == "x" else 0.0)
        y = centre[1] + (d if axis == "y" else 0.0)
        out.append((t, x, y))
    return out


def check_offsets(schedule, max_offset_um):
    """Refuse a schedule that leaves the range. Never clamps -- see the header."""
    worst = max(math.hypot(x, y) for _, x, y in schedule)
    if worst > max_offset_um:
        raise SystemExit(
            f"REFUSED: the drive reaches {worst:.2f} um from the trap origin, "
            f"past --max-offset-um {max_offset_um:.2f}.\n"
            "  Points outside the calibrated trapezoid are silently clipped by\n"
            "  the GUI and not drawn, so this would deform the drive with no\n"
            "  error reported anywhere. Read the green trapezoid off the GUI\n"
            "  and raise the limit deliberately if the range really is larger.")
    return worst


def stream_sine(ot, name, schedule, on_tick=None):
    """Send the schedule on the host clock. Returns (t_sent, x, y) as flown.

    ``on_tick`` is called after each send with the tick just flown, so a camera
    can be sampled in the same loop rather than in a second thread -- the point
    is that the trap position and the frame share one clock.
    """
    flown = []
    t0 = time.perf_counter()
    for t_target, x, y in schedule:
        while True:
            slack = t_target - (time.perf_counter() - t0)
            if slack <= 0:
                break
            time.sleep(min(slack, 0.002))
        ot.set_trap_position(name, x, y)
        flown.append((time.perf_counter() - t0, x, y))
        if on_tick is not None:
            on_tick(flown[-1])
    return flown


def stream_report(flown, schedule):
    """How well the host clock kept the schedule. The drive's own error bar."""
    late = [f[0] - s[0] for f, s in zip(flown, schedule)]
    gaps = np.diff([f[0] for f in flown])
    return (f"{len(flown)} positions sent over {flown[-1][0]:.2f} s: tick "
            f"{gaps.mean() * 1e3:.1f} +- {gaps.std() * 1e3:.1f} ms "
            f"(max {gaps.max() * 1e3:.1f}), cumulative lateness "
            f"{late[-1] * 1e3:+.0f} ms")


# --------------------------------------------------------------------------
# fitting the bead against the drive
# --------------------------------------------------------------------------

def fit_against_drive(t, series, freq_hz):
    """Fit ``series(t)`` to a sinusoid at freq_hz plus an offset and a drift.

    Returns (in_phase, quadrature, offset, slope). The drive is a pure sine of
    phase zero, so ``in_phase`` carries the responding amplitude *with its
    sign* -- which is the whole point, since the sign is what cannot be guessed
    -- and ``quadrature`` is the lag. The linear term absorbs stage or thermal
    drift, which a periodic drive separates cleanly from the response; a step
    calibration cannot do that.
    """
    t = np.asarray(t, dtype=float)
    w = 2 * math.pi * freq_hz
    design = np.column_stack([np.sin(w * t), np.cos(w * t), np.ones_like(t), t])
    coef, *_ = np.linalg.lstsq(design, np.asarray(series, dtype=float),
                               rcond=None)
    return tuple(float(c) for c in coef)


def column_from_fit(t, px, py, amp_um, freq_hz):
    """One column of B (px per um) plus its lag, from a single-axis drive.

    The in-phase coefficients alone would under-read the column by ``cos(lag)``,
    and the lag is not zero even with a perfectly held bead: the camera
    integrates for 33 ms, so its reported position is the mid-exposure one and
    that is already 12 deg of phase at 1 Hz before any physics. So the response
    is treated as a **complex** 2-vector ``R = in_phase + i*quadrature``, a
    single common phase is taken out of it, and the column is what is left. A
    real spatial map with one scalar lag is exactly rank one in that sense, so
    whatever does not de-phase is the part the model does not explain and is
    returned as ``residual`` rather than absorbed.
    """
    ax_in, ax_q, ax_off, ax_slope = fit_against_drive(t, px, freq_hz)
    ay_in, ay_q, ay_off, ay_slope = fit_against_drive(t, py, freq_hz)
    r = np.array([ax_in + 1j * ax_q, ay_in + 1j * ay_q]) / amp_um
    # 0.5*arg(sum R^2) is the phase that makes a complex vector as real as it
    # can be. It leaves a sign ambiguity (phi and phi+pi both work), settled
    # below against the in-phase part, which is the one with physical meaning.
    phi = 0.5 * math.atan2(float(np.imag((r ** 2).sum())),
                           float(np.real((r ** 2).sum())))
    rot = r * np.exp(-1j * phi)
    col, residual = np.real(rot), np.imag(rot)
    if np.dot(col, np.array([ax_in, ay_in])) < 0:
        col, residual, phi = -col, -residual, phi + math.pi
    lag = math.degrees((phi + math.pi) % (2 * math.pi) - math.pi)
    return (col, lag, float(np.linalg.norm(residual) /
                            max(np.linalg.norm(col), 1e-12)),
            np.array([ax_off, ay_off]), np.array([ax_slope, ay_slope]))


def decompose(b):
    """Scale (um/px), anisotropy, rotation and handedness of the fitted matrix."""
    u, s, vt = np.linalg.svd(b)
    scale = float(s.mean())                      # px per um
    aniso = float(abs(s[0] - s[1]) / scale)
    handed = int(np.sign(np.linalg.det(b)))
    # Polar decomposition: the rotation part of B, with any flip taken out
    # first so the angle means what it says.
    r = u @ vt
    if handed < 0:
        r = r @ np.diag([1.0, -1.0])
    rot = math.degrees(math.atan2(r[1, 0], r[0, 0]))
    return 1.0 / scale, aniso, rot, handed


# --------------------------------------------------------------------------
# the camera side
# --------------------------------------------------------------------------

def bead_scale(um_per_px, radius_um=2.5):
    """Detector windows in px, from the bead and the pixel size.

    The offline analysis hardcodes ``mask_r=45`` and ``win=32``, which were
    right for the 60x it was written against (0.10833 um/px, a 5 um bead is
    r = 23 px). At 100x the same bead is r = 38 px, so both would be *inside*
    the bead: the mask would find the same particle several times and the
    refine window would clip its own signal. Scaled, not reused.
    """
    r_px = radius_um / um_per_px
    return dict(r_px=r_px,
                mask_r=int(round(1.9 * r_px)),
                win=int(round(1.7 * r_px)))


def open_core(cfg, exposure_ms=None):
    """Load MM and return (core, camera). Names the Tweez GUI on contention."""
    from pymmcore_plus import CMMCorePlus  # noqa: PLC0415  (slow import)

    core = CMMCorePlus()
    try:
        core.loadSystemConfiguration(str(cfg))
    except Exception as exc:
        raise SystemExit(
            f"could not load {cfg}: {exc}\n"
            "  If this names the camera: PVCAM hands a Kinetix to one process\n"
            "  at a time and the Tweez GUI may still be holding it. Release it\n"
            "  in the GUI first -- TCP trap commands keep working after the\n"
            "  release, which is what makes this tool possible.") from exc
    camera = core.getCameraDevice()
    if exposure_ms is not None:
        core.setExposure(exposure_ms)
    return core, camera


def objective_label(core):
    """The Nosepiece label, which is what both Tweez calibrations depend on."""
    try:
        return str(core.getStateLabel("Nosepiece"))
    except Exception:
        return "<unreadable>"


def pixel_size_um(core, mag_label):
    """Recorded um/px for the objective in place, cross-checked against MM."""
    from optics import components  # noqa: PLC0415

    mags = [float(m) for m in ("100", "60", "40") if m in mag_label]
    if not mags:
        raise SystemExit(
            f"REFUSED: cannot read an objective magnification out of the "
            f"Nosepiece label {mag_label!r}, so the pixel size is unknown and "
            "every px->um number below would be invented.")
    try:
        mf = float(core.getMagnificationFactor())
    except Exception as exc:
        raise SystemExit(
            "REFUSED: getMagnificationFactor() is unreadable, so the "
            "intermediate magnification is unknown. Position 0 is 1x and "
            "position 1 is 1.5x, and the two differ by 50% in um/px -- "
            "guessing would put every trap position 50% out.") from exc
    rec = components.recorded_pixel_um(mags[0], mf)
    if rec is None:
        raise SystemExit(f"REFUSED: no recorded pixel size for "
                         f"{mags[0]:g}x at intermediate {mf:g}x.")
    return float(rec[0]), str(rec[1]), mf


def track_bead_during(core, ot, name, schedule, seed, um_per_px, log_every=25):
    """Drive the sine and follow one bead in the same loop, on one clock.

    Both halves share the tick, so the trap position and the frame that follows
    it carry the same host timestamps and no cross-clock offset has to be
    reasoned about -- only the constant mid-exposure lag, which
    ``column_from_fit`` removes.

    Frames are deduplicated by identity of the buffer contents at the corner:
    ``getLastImage`` returns the newest frame, and at a 50 Hz tick against a
    30 fps camera roughly a third of the ticks see the same frame twice.
    Counting a frame twice would just double-weight it in the fit, but it also
    hides a stalled camera, so it is tracked and reported.
    """
    scale = bead_scale(um_per_px)
    win, jump = scale["win"], scale["r_px"]
    # A driven bead is fast: 5 um at 1 Hz peaks at 31 um/s, which is 16 px per
    # 33 ms frame at 100x. The analysis module's jump_px=8 would break the
    # link every frame, so the gate is the bead radius instead.
    samples: list[tuple[float, float, float]] = []
    state = {"cx": float(seed[0]), "cy": float(seed[1]), "last": None,
             "dupes": 0, "lost": 0}

    def on_tick(tick):
        t = tick[0]
        try:
            frame = core.getLastImage()
        except Exception:
            state["lost"] += 1
            return
        raw = np.asarray(frame)
        sig = (int(raw[0, 0]), int(raw[-1, -1]), int(raw[raw.shape[0] // 2,
                                                        raw.shape[1] // 2]))
        if sig == state["last"]:
            state["dupes"] += 1
            return
        state["last"] = sig
        img = raw.astype(np.float32) - OFFSET_ADU
        h, w = img.shape
        nx, ny, mass = refine(img, state["cx"], state["cy"], win, 3, h, w)
        if mass <= 0 or abs(nx - state["cx"]) > jump or abs(ny - state["cy"]) > jump:
            state["lost"] += 1
            return
        state["cx"], state["cy"] = nx, ny
        samples.append((t, nx, ny))

    flown = stream_sine(ot, name, schedule, on_tick=on_tick)
    return flown, np.array(samples, dtype=float), state


def find_seed(core, um_per_px, nearest_px=None, isolation_um=12.0):
    """Detect on one frame and choose a bead. Returns (seed, all, n_isolated)."""
    raw = np.asarray(core.getLastImage())
    img = raw.astype(np.float32) - OFFSET_ADU
    scale = bead_scale(um_per_px)
    cand = detect(img, mask_r=scale["mask_r"])
    if len(cand) == 0:
        raise SystemExit("REFUSED: no particle detected in the frame. Nothing "
                         "to trap and nothing to calibrate against.")
    h, w = img.shape
    if len(cand) > 1:
        d = np.linalg.norm(cand[:, None, :] - cand[None, :, :], axis=-1)
        np.fill_diagonal(d, np.inf)
        iso = d.min(axis=1) * um_per_px >= isolation_um
    else:
        iso = np.ones(1, dtype=bool)
    target = np.array(nearest_px if nearest_px is not None
                      else [w / 2, h / 2], dtype=float)
    # Isolated beads only: a bead with a neighbour inside the isolation cut is
    # the one case where the trap grabs the wrong particle and the fit reports
    # a healthy amplitude for a bead that is not the one being driven.
    pool = cand[iso] if iso.any() else cand
    pick = pool[np.argmin(np.linalg.norm(pool - target, axis=1))]
    return pick, cand, int(iso.sum())


# --------------------------------------------------------------------------
# the trap, over TCP
# --------------------------------------------------------------------------

def connect_trap(name, create, strength, centre, turn_on):
    """Open the GUI socket and make sure the named trap exists where we think.

    Order matters on create: position and strength are set **before** TRAP_ON,
    so the trap never appears at whatever position the GUI happened to have and
    then jump. It is the difference between placing a trap and sweeping one
    across the field.
    """
    from hardware.optical_tweezers import (  # noqa: PLC0415
        OpticalTweezers,
        find_gui_port,
    )

    port = find_gui_port()
    if port is None:
        raise SystemExit(
            "REFUSED: no Tweez GUI answered on 2070-2075. Start the GUI and "
            "check external control is enabled.")
    ot = OpticalTweezers(port=port)
    print(f"Tweez GUI on port {port}, ready={ot.is_ready()}")

    # -22 vs 0 on TRAP_STRENGTH is the only query this write-only interface
    # has (2026-08-27). It is a write, so it is sent with the strength we want
    # rather than a probe value -- asking the question and setting the answer
    # in one command.
    status = ot.send_command(f'TRAP_STRENGTH "{name}" {strength}')
    exists = status == 0
    if not exists and status != -22:
        raise SystemExit(f"REFUSED: TRAP_STRENGTH {name!r} answered {status}, "
                         "which is neither 0 (exists) nor -22 (absent). Look "
                         "at the GUI before driving anything.")
    if not exists:
        if not create:
            raise SystemExit(
                f"REFUSED: no trap named {name!r}. Make one in the GUI, or "
                "pass --create to make it over TCP (SIMPLE_TRAP_CREATE).")
        print(f"  creating trap {name!r} at ({centre[0]:g}, {centre[1]:g}) um")
        ot.create_simple_trap(name)
        ot.set_trap_position(name, centre[0], centre[1])
        ot.set_trap_strength(name, strength)
    else:
        print(f"  trap {name!r} exists; strength set to {strength:g}")
        ot.set_trap_position(name, centre[0], centre[1])
    if turn_on:
        ot.trap_on(name)
        print(f"  TRAP_ON {name!r} -- the trap is now steering 1064 nm to "
              f"({centre[0]:g}, {centre[1]:g}) um")
    return ot


def write_log(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"  log -> {path}")


# --------------------------------------------------------------------------
# modes
# --------------------------------------------------------------------------

def mode_sine(args):
    """Drive an existing trap and let a human watch. No camera involved."""
    centre = (args.centre_um[0], args.centre_um[1])
    schedule = sine_schedule(args.amp_um, args.freq_hz, args.axis,
                             args.cycles, args.rate_hz, centre)
    worst = check_offsets(schedule, args.max_offset_um)
    print(f"{args.axis} sine: {args.amp_um:g} um at {args.freq_hz:g} Hz, "
          f"{args.cycles:g} cycles about ({centre[0]:g}, {centre[1]:g}) um")
    print(f"  {len(schedule)} positions at {args.rate_hz:g} Hz "
          f"(step {2 * math.pi * args.freq_hz * args.amp_um / args.rate_hz:.2f} "
          f"um at the zero crossing), reaching {worst:.2f} um from the origin")
    print(f"  peak speed {2 * math.pi * args.freq_hz * args.amp_um:.1f} um/s")

    ot = connect_trap(args.trap_name, args.create, args.strength, centre,
                      not args.no_trap_on)
    try:
        flown = stream_sine(ot, args.trap_name, schedule)
        print("  " + stream_report(flown, schedule))
        if args.park:
            ot.set_trap_position(args.trap_name, centre[0], centre[1])
            print(f"  parked at ({centre[0]:g}, {centre[1]:g}) um")
        if args.log:
            write_log(args.log, {
                "kind": "sine", "trap": args.trap_name, "axis": args.axis,
                "amp_um": args.amp_um, "freq_hz": args.freq_hz,
                "centre_um": list(centre), "strength": args.strength,
                "laser_note": args.laser_note,
                "commanded": [[round(t, 5), x, y] for t, x, y in flown]})
    finally:
        ot.close()
    print("\nDid the bead follow? If it traced the drive, it is trapped -- and "
          "\n`calibrate` will turn that same motion into the px->um transform.")
    return 0


def mode_calibrate(args):
    """The same sine, tracked, in x then y: measures the transform."""
    centre = (args.centre_um[0], args.centre_um[1])
    core, camera = open_core(args.cfg, args.exposure_ms)
    obj = objective_label(core)
    um_per_px, provenance, mf = pixel_size_um(core, obj)
    scale = bead_scale(um_per_px)
    print(f"{camera} on {obj}, intermediate {mf:g}x")
    print(f"  pixel {um_per_px:.5f} um/px ({provenance}); a {2 * 2.5:g} um "
          f"bead is r = {scale['r_px']:.0f} px, so mask_r={scale['mask_r']} "
          f"win={scale['win']}")

    ot = connect_trap(args.trap_name, args.create, args.strength, centre,
                      not args.no_trap_on)
    core.startContinuousSequenceAcquisition(0)
    cols, lags, resids, follows, offs = [], [], [], [], []
    try:
        time.sleep(0.5)                      # let the first frames arrive
        carried = None
        for axis in ("x", "y"):
            if carried is None:
                seed, cand, n_iso = find_seed(core, um_per_px, args.seed_px,
                                              args.isolation_um)
                print(f"\n{axis} drive: seeded on ({seed[0]:.1f}, "
                      f"{seed[1]:.1f}) px out of {len(cand)} detections, "
                      f"{n_iso} isolated past {args.isolation_um:g} um")
            else:
                # Carry the bead x measured rather than re-detecting: a fresh
                # search from the frame centre can pick a different particle,
                # and then B has one column per bead and means nothing. The
                # trap parked at `centre` between the drives, so the bead is
                # back where the x fit last saw it.
                seed = carried
                print(f"\n{axis} drive: carrying the same bead from the x "
                      f"drive at ({seed[0]:.1f}, {seed[1]:.1f}) px")
                time.sleep(args.settle_s)
            schedule = sine_schedule(args.amp_um, args.freq_hz, axis,
                                     args.cycles, args.rate_hz, centre)
            check_offsets(schedule, args.max_offset_um)
            flown, samples, state = track_bead_during(
                core, ot, args.trap_name, schedule, seed, um_per_px)
            ot.set_trap_position(args.trap_name, centre[0], centre[1])
            print("  " + stream_report(flown, schedule))
            print(f"  {len(samples)} unique frames tracked "
                  f"({state['dupes']} repeats, {state['lost']} rejected)")
            if len(samples) < 20:
                raise SystemExit(
                    f"REFUSED: only {len(samples)} frames tracked, which "
                    "cannot support a 4-parameter fit per axis. The bead was "
                    "lost, or the camera is not streaming.")
            col, lag, resid, off, slope = column_from_fit(
                samples[:, 0], samples[:, 1], samples[:, 2],
                args.amp_um, args.freq_hz)
            follow = float(np.linalg.norm(col) * um_per_px)
            print(f"  response {np.linalg.norm(col) * args.amp_um:.1f} px "
                  f"= {np.linalg.norm(col) * args.amp_um * um_per_px:.2f} um "
                  f"for a {args.amp_um:g} um drive -> followed {follow:.0%}")
            print(f"  direction ({col[0] / np.linalg.norm(col):+.3f}, "
                  f"{col[1] / np.linalg.norm(col):+.3f}) in px, lag "
                  f"{lag:+.0f} deg, residual {resid:.0%}, drift "
                  f"{np.linalg.norm(slope) * um_per_px:.3f} um/s")
            cols.append(col)
            lags.append(lag)
            resids.append(resid)
            follows.append(follow)
            offs.append(off)
            carried = samples[-1, 1:3]
    finally:
        core.stopSequenceAcquisition()
        ot.close()

    b = np.column_stack(cols)                # columns are x then y drive
    fitted_um_per_px, aniso, rot, handed = decompose(b)
    # The fit gives the bead position while the trap sat at `centre`, so the
    # origin has to be walked back to trap (0, 0) rather than read off directly.
    p0 = np.mean(offs, axis=0) - b @ np.asarray(centre, dtype=float)
    h, w = core.getImageHeight(), core.getImageWidth()
    t = TrapTransform(
        b=[[float(v) for v in row] for row in b],
        p0=[float(p0[0]), float(p0[1])],
        objective=obj, camera=camera, frame_shape=[int(h), int(w)],
        nominal_um_per_px=float(um_per_px),
        fitted_um_per_px=float(fitted_um_per_px),
        anisotropy=float(aniso), rotation_deg=float(rot), handedness=handed,
        lag_deg=[float(v) for v in lags],
        follow_frac=[float(v) for v in follows],
        residual=[float(v) for v in resids],
        amp_um=float(args.amp_um), freq_hz=float(args.freq_hz),
        taken=time.strftime("%Y-%m-%d %H:%M"), note=args.laser_note or "")
    print("\n" + t.report())
    if t.problems and not args.save_anyway:
        raise SystemExit(
            "\nNOT SAVED: the fit did not pass its own checks (above). Fix the "
            "cause rather than the threshold -- a transform that fails these "
            "will send the trap to the wrong place quietly. --save-anyway "
            "overrides, and records the problems in the file.")
    save_transform(t, Path(args.out))
    print(f"\nsaved -> {args.out}")
    return 0


def mode_trap(args):
    """Detect isolated beads and put the trap on one, through the transform."""
    t = load_transform(Path(args.calibration))
    core, camera = open_core(args.cfg, args.exposure_ms)
    obj = objective_label(core)
    if obj != t.objective and not args.ignore_objective:
        raise SystemExit(
            f"REFUSED: the transform was measured on {t.objective!r} and the "
            f"Nosepiece now reads {obj!r}.\n"
            "  Both Tweez calibrations are objective-dependent and an "
            "objective change\n"
            "  invalidates them with nothing on either side reporting it. "
            "Re-run `calibrate`.\n"
            "  --ignore-objective exists only for a relabelled turret.")
    um_per_px = t.fitted_um_per_px
    core.startContinuousSequenceAcquisition(0)
    ot = None
    try:
        time.sleep(0.5)
        seed, cand, n_iso = find_seed(core, um_per_px, args.at_px,
                                      args.isolation_um)
        print(f"{camera} on {obj}: {len(cand)} detections, {n_iso} isolated "
              f"past {args.isolation_um:g} um")
        um = t.to_um(seed)
        print(f"  target ({seed[0]:.1f}, {seed[1]:.1f}) px "
              f"-> ({um[0]:+.3f}, {um[1]:+.3f}) um in trap coordinates")
        reach = math.hypot(um[0], um[1])
        if reach > args.max_offset_um:
            raise SystemExit(
                f"REFUSED: that bead is {reach:.2f} um from the trap origin, "
                f"past --max-offset-um {args.max_offset_um:g}. The GUI would "
                "clip the position silently and the trap would land somewhere "
                "else with no error. Move the stage instead, or read the "
                "trapezoid off the GUI and raise the limit deliberately.")
        ot = connect_trap(args.trap_name, args.create, args.strength,
                          (float(um[0]), float(um[1])), not args.no_trap_on)
        if args.confirm:
            print(f"\nconfirming with a {args.confirm_amp_um:g} um "
                  f"{args.freq_hz:g} Hz x sine about the target")
            schedule = sine_schedule(args.confirm_amp_um, args.freq_hz, "x",
                                     args.cycles, args.rate_hz,
                                     (float(um[0]), float(um[1])))
            check_offsets(schedule, args.max_offset_um)
            flown, samples, state = track_bead_during(
                core, ot, args.trap_name, schedule, seed, um_per_px)
            ot.set_trap_position(args.trap_name, float(um[0]), float(um[1]))
            print("  " + stream_report(flown, schedule))
            if len(samples) < 20:
                print(f"  INCONCLUSIVE: only {len(samples)} frames tracked.")
            else:
                col, lag, resid, _, _ = column_from_fit(
                    samples[:, 0], samples[:, 1], samples[:, 2],
                    args.confirm_amp_um, args.freq_hz)
                follow = float(np.linalg.norm(col) * um_per_px)
                verdict = ("TRAPPED" if follow >= MIN_FOLLOW_FRAC
                           else "NOT TRAPPED")
                print(f"  followed {follow:.0%} of the drive, lag "
                      f"{lag:+.0f} deg, residual {resid:.0%} -> {verdict}")
                # A held bead follows the *commanded* direction. If it follows
                # a different one, the transform is stale rather than the trap
                # empty, and those need different fixes.
                want = t.matrix @ np.array([1.0, 0.0])
                cos = float(np.dot(col, want) /
                            (np.linalg.norm(col) * np.linalg.norm(want)))
                if follow >= MIN_FOLLOW_FRAC and cos < 0.9:
                    print(f"  but it moved {math.degrees(math.acos(max(-1, min(1, cos)))):.0f} "
                          "deg off the direction the transform predicts -- the "
                          "transform is stale, not the trap empty. Re-run "
                          "`calibrate`.")
    finally:
        core.stopSequenceAcquisition()
        if ot is not None:
            ot.close()
    return 0


def build_parser():
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)

    def common(p, camera=True):
        p.add_argument("--trap-name", default="Trap 1",
                       help="trap name as the GUI knows it (default Trap 1)")
        p.add_argument("--create", action="store_true",
                       help="SIMPLE_TRAP_CREATE it if absent, over TCP")
        p.add_argument("--strength", type=float, default=1.0,
                       help="per-trap relative weight in [0,1]. NOT laser "
                            "power, which is GUI-only and unreadable")
        p.add_argument("--no-trap-on", action="store_true",
                       help="skip TRAP_ON: place the trap without steering "
                            "the beam to it")
        p.add_argument("--centre-um", type=float, nargs=2, default=[0.0, 0.0],
                       metavar=("X", "Y"),
                       help="trap origin to work about, um (default 0 0, "
                            "which the user reports is the field centre)")
        p.add_argument("--max-offset-um", type=float, default=MAX_OFFSET_UM,
                       help=f"refuse past this, um (default {MAX_OFFSET_UM:g}). "
                            "Refuses; never clamps -- the GUI clips silently")
        p.add_argument("--freq-hz", type=float, default=1.0)
        p.add_argument("--cycles", type=float, default=5.0)
        p.add_argument("--rate-hz", type=float, default=STREAM_HZ,
                       help=f"position commands per second (default "
                            f"{STREAM_HZ:g}; ~100 is the TCP ceiling)")
        p.add_argument("--laser-note", default=None,
                       help="laser power and anything else the GUI knows and "
                            "TCP cannot read. Goes in the log; it has nowhere "
                            "else to go")
        if camera:
            p.add_argument("--cfg", required=True,
                           help="Micro-Manager system configuration")
            p.add_argument("--exposure-ms", type=float, default=None)
            p.add_argument("--isolation-um", type=float, default=12.0,
                           help="nearest-neighbour cut for a usable bead")

    p_sine = sub.add_parser(
        "sine", help="drive a trap and watch it in the GUI. No camera.")
    common(p_sine, camera=False)
    p_sine.add_argument("--amp-um", type=float, default=5.0)
    p_sine.add_argument("--axis", choices=("x", "y"), default="x")
    p_sine.add_argument("--no-park", dest="park", action="store_false",
                        help="leave the trap wherever the sine ended. Default "
                             "is to return it to --centre-um, so a run does "
                             "not silently move the trap")
    p_sine.add_argument("--log", default=None,
                        help="write the commanded series as JSON. The only "
                             "record of x_trap(t) there will be")
    p_sine.set_defaults(func=mode_sine)

    p_cal = sub.add_parser(
        "calibrate", help="sine in x then y, tracked: measures px <-> um")
    common(p_cal)
    p_cal.add_argument("--amp-um", type=float, default=5.0)
    p_cal.add_argument("--seed-px", type=float, nargs=2, default=None,
                       metavar=("X", "Y"),
                       help="pick the bead nearest this pixel (default: the "
                            "frame centre)")
    p_cal.add_argument("--settle-s", type=float, default=2.0,
                       help="pause between the x and y drives, letting the "
                            "bead come to rest at the parked trap")
    p_cal.add_argument("--out", default=str(DEFAULT_CAL))
    p_cal.add_argument("--save-anyway", action="store_true",
                       help="save even if the fit fails its own checks")
    p_cal.set_defaults(func=mode_calibrate)

    p_trap = sub.add_parser(
        "trap", help="detect a bead and put the trap on it")
    common(p_trap)
    p_trap.add_argument("--calibration", default=str(DEFAULT_CAL))
    p_trap.add_argument("--at-px", type=float, nargs=2, default=None,
                        metavar=("X", "Y"),
                        help="trap the bead nearest this pixel (default: the "
                             "frame centre)")
    p_trap.add_argument("--nearest-centre", action="store_true",
                        help="explicit form of the default")
    p_trap.add_argument("--confirm", action="store_true",
                        help="after placing it, drive a small sine and report "
                             "whether the bead followed")
    p_trap.add_argument("--confirm-amp-um", type=float, default=2.0)
    p_trap.add_argument("--ignore-objective", action="store_true")
    p_trap.set_defaults(func=mode_trap)
    return ap


def main() -> int:
    # Line-buffer stdout. Python block-buffers it when it is a pipe rather
    # than a console, so a long-running window like this one produces NOTHING
    # readable until it exits -- which reads exactly like a hang, and did.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

