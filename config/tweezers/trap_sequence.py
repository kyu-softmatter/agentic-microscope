"""One window, four stages, advanced by the space bar: look, detect, trap, drive.

    python config/tweezers/trap_sequence.py --cfg config/micromanager/single_cam_red_noDMD.cfg \
        --roi 1200 --line GREEN --intensity 20 --gpu

    SPACE  advance     H  hold at (0,0)     D  drive again     ESC  stop
    stage 0  LIVE       frames only, no detection
    stage 1  DETECT     isolated particles circled, green isolated / red crowded
    stage 2  TRAP       the isolated particle nearest the field centre
    stage 3  OSCILLATE  5 um, 1 Hz in x -- confirms the trap AND measures px->um
    stage 4  DONE       the fit on screen
    stage 5  HOLD       bring the held bead to (0,0) and keep it there

HOLD NEEDS NO CALIBRATION, WHICH IS WHY IT IS WORTH HAVING SEPARATELY
---------------------------------------------------------------------
Moving a bead you already hold to the field centre needs only the origin:
command the trap to (0, 0) and the bead comes with it, because the origin *is*
the centre. No rotation, handedness or scale enters. The transform is needed to
choose *which* bead to grab, never to move one already held.

That also makes HOLD a way to catch a bead with no transform at all -- park at
the origin and wait for one to diffuse in. The catch is observable rather than
assumed: a held bead stops diffusing, and when its excursion collapses its
pixel position **is** p0. So the stage that needs no calibration is also the
one that hands you a third of it.

WHY THE STAGES ARE IN THIS ORDER AND NOT A BETTER ONE
-----------------------------------------------------
Stage 2 needs something stage 3 produces. Putting the trap on a *chosen*
particle means converting its pixel position into trap um, and that conversion
carries an unknown rotation and an unknown handedness -- the Tweez *Beam
Position* calibration is rotation+translation+scale and nothing in the TCP
interface reads it back (52 command names probed 2026-08-27, all -11). Eight
orientations agree with "the origin is the field centre" and seven of them send
the trap to a mirrored or rotated position.

So on a **first** run stage 2 is a labelled guess: the nominal pixel size, no
rotation, and a y flip because image y runs downwards. It is drawn on screen as
PROVISIONAL and it is checked immediately rather than trusted -- a held bead
stops diffusing, so the target bead's excursion over the next second
discriminates sharply (a free 5 um bead near the wall covers ~350 nm RMS in
1.5 s at the D measured on 2026-09-04; a held one covers tens of nm).

Stage 3 then *measures* the transform from the oscillation the operator wanted
anyway, and saves it. From the second run onwards stage 2 is not a guess, and
the window says which it is. If the provisional guess was wrong, stage 3 says
by how many degrees -- the failure is legible instead of just being a bead that
never got caught.

THE DRIVE RUNS ON THE DISPLAY TICK
----------------------------------
``trap_from_tracking.stream_sine`` blocks, which would freeze the window for
the length of the drive. Here the sine is a function of the tick clock instead:
every tick sends one position and grabs one frame, so the two share a
timestamp and the pairing the fit needs is exact rather than interpolated. The
cost is the command rate -- the display tick rather than 50 Hz, so ~25 points
per cycle and a ~1.3 um step at the zero crossing. That is still far below
anything a 5 um bead resolves, and it buys a window that stays alive.

WHAT IT LEAVES BEHIND
---------------------
The trap is **parked, never switched off**. Closing this window must not be
able to drop a bead, which is the same rule the turret shutters follow in
``live_view`` (Turret 2 is the 1064 path). The light engine *is* taken down,
because leaving excitation on bleaches the sample and nothing depends on it.

⚠ The illumination block duplicates ``live_view.main``'s. The two have to stay
in step and nothing enforces that; unifying them means refactoring live_view's
exit path, which was not worth doing while an operator was mid-session with a
live trap.
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _load(relative: str, name: str):
    """config/ is not a package, so its modules load by path."""
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module          # @dataclass needs it registered
    spec.loader.exec_module(module)
    return module


LV = _load("config/micromanager/live_view.py", "_live_view")
TFT = _load("config/tweezers/trap_from_tracking.py", "_trap_from_tracking")

STAGES = ("LIVE", "DETECT", "TRAP", "OSCILLATE", "DONE", "HOLD")

#: Rolling window HOLD judges the excursion over, seconds.
HOLD_WINDOW_S = 2.0

#: Ti2-E turret shutters, in series with the image. Left open on exit.
_TURRET_SHUTTERS = ("Turret1Shutter", "Turret2Shutter")

#: How long stage 2 watches the target before judging whether it is held.
GRAB_WATCH_S = 1.5

#: A free 5 um bead near the coverslip covers sqrt(2 D t) ~ 350 nm in 1.5 s at
#: the D measured on 2026-09-04 (0.0395 um^2/s). A held one covers tens of nm
#: -- two windows that stayed on one bead read 55 and 61 nm the same day.
#: Halfway between, in nm, on the RMS excursion.
HELD_EXCURSION_NM = 150.0

#: Hysteresis on the held verdict. One cut at 150 nm flipped on noise alone:
#: measured 55, 152, 61, 155, 143, 151, 149 nm in sequence. Entering "held"
#: and leaving it are deliberately different numbers.
HELD_ENTER_NM = 110.0
HELD_LEAVE_NM = 220.0


def provisional_transform(um_per_px, frame_shape, objective, camera):
    """The guess, clearly labelled as one. See the module docstring."""
    h, w = frame_shape
    b = (1.0 / um_per_px) * np.diag([1.0, -1.0])
    return TFT.TrapTransform(
        b=b.tolist(), p0=[w / 2.0, h / 2.0], objective=objective,
        camera=camera, frame_shape=[int(h), int(w)],
        nominal_um_per_px=float(um_per_px),
        fitted_um_per_px=float(um_per_px), anisotropy=0.0, rotation_deg=0.0,
        handedness=-1, lag_deg=[0.0, 0.0], follow_frac=[0.0, 0.0],
        residual=[0.0, 0.0], amp_um=0.0, freq_hz=0.0, taken="PROVISIONAL",
        note="never measured: nominal scale, no rotation, y flipped because "
             "image y runs down. One of eight orientations.")


def usable_transform(path, frame_shape, objective, um_per_px, camera):
    """A saved transform if it fits this frame and objective, else the guess."""
    path = Path(path)
    if not path.exists():
        return provisional_transform(um_per_px, frame_shape, objective,
                                     camera), "no saved transform"
    t = TFT.load_transform(path)
    if list(t.frame_shape) != [int(frame_shape[0]), int(frame_shape[1])]:
        # p0 is in ROI-relative pixels, so a different ROI moves the origin
        # by half the size difference -- 600 px, 39 um of trap position.
        return provisional_transform(um_per_px, frame_shape, objective,
                                     camera), (
            f"saved transform was taken at {t.frame_shape[1]}x"
            f"{t.frame_shape[0]}, this is {frame_shape[1]}x{frame_shape[0]}")
    if t.objective != objective:
        return provisional_transform(um_per_px, frame_shape, objective,
                                     camera), (
            f"saved transform was taken on {t.objective!r}, now {objective!r}")
    if t.problems:
        return provisional_transform(um_per_px, frame_shape, objective,
                                     camera), (
            f"saved transform has unresolved problems: {t.problems[0]}")
    return t, None


class Sequence:
    """The state machine. One tick per display frame, one stage per space bar."""

    def __init__(self, core, camera, ot, tracker, transform, provisional_why,
                 args, um_per_px):
        self.core, self.camera, self.ot = core, camera, ot
        self.tracker, self.transform = tracker, transform
        self.provisional_why = provisional_why
        self.args, self.um_per_px = args, um_per_px
        self.stage = 0
        self.circles = np.empty((0, 3))
        self.target_px = None          # the bead we are after, in ROI pixels
        self.target_um = None          # where the trap was sent, in trap um
        self.trap_home = (float(args.centre_um[0]), float(args.centre_um[1]))
        self.scale = TFT.bead_scale(um_per_px)
        self.watch: list[tuple[float, float, float]] = []
        self.drive: list[tuple[float, float, float]] = []
        self.t_stage = time.perf_counter()
        self.message = "SPACE to start detecting"
        self.result = None
        self.judged = False
        # The first run produced 21 samples in a 5 s drive where stage 2's
        # watch produced 54 in 1.5 s. TRAP_POSITION is only 15.6 ms of that
        # (measured: 1.3 ms round trip under a 10 ms enforced gap), so the
        # gap is unexplained -- and the way to stop guessing is to count.
        self.hold_hist: list[tuple[float, float, float]] = []
        self.hold_state = None
        self.hold_lock = None
        self.hold_lost = 0
        self.ramping = False
        self.ramp_from = np.zeros(2)
        self.ramp_dist = 0.0
        self.ramp_px0 = None
        self.reject = {"ok": 0, "mass": 0, "jump": 0}
        self.stage_ticks: dict[int, list[float]] = {}
        self.t_tick = None
        self.last_sig = None
        self.frames = 0

    # -- stage transitions ------------------------------------------------

    def advance(self):
        if self.stage == 0:
            self.stage = 1
            self.message = "SPACE to trap the one nearest the centre"
        elif self.stage == 1:
            if not self._pick_target():
                return
            self.stage = 2
            self.watch = []
        elif self.stage == 2:
            if not self.judged:
                self.message = "still watching -- wait for the verdict"
                return
            if not self.start_drive():
                return
        elif self.stage == 3:
            pass                       # the drive ends itself
        elif self.stage == 4:
            self.enter_hold()
            return
        self.t_stage = time.perf_counter()

    def enter_hold(self):
        """Ramp the trap to (0, 0) on a straight line, then keep it there.

        THIS NEEDS NO TRANSFORM, which is the whole reason it is a separate
        stage. Once a bead is held at trap position T, commanding T -> (0, 0)
        carries it to the field centre *by definition* -- the origin is the
        centre, so no rotation, handedness or scale enters. The transform is
        needed to decide *which* bead to grab, never to move one already held.

        **It is a ramp and not a jump**, for a reason that is physics rather
        than taste. Dragging the bead costs Stokes drag, roughly doubled this
        close to the coverslip, and a single ``TRAP_POSITION`` to the origin
        asks for that displacement in one 15 ms command -- an implied speed of
        a thousand um/s over a 16 um trip, far past anything a trap holds. The
        bead is simply left behind and the trap arrives empty. So the position
        is interpolated at ``--speed-um-s``.

        The speed that is *known* to work is the one already demonstrated: a
        5 um 1 Hz sine peaks at 31 um/s, so if stage 3 reported TRAPPED then
        the trap drags at least that fast and the default 10 um/s is inside a
        measured bound rather than a guessed one.

        Parking at the origin is also a way to catch a bead with no transform
        at all -- wait for one to diffuse in. The catch is observable rather
        than assumed: a held bead stops diffusing, and when its excursion
        collapses its pixel position **is** p0. So the stage that needs no
        calibration also hands you a third of it.
        """
        start = (self.target_um if self.target_um is not None
                 else np.zeros(2, dtype=float))
        self.ramp_from = np.asarray(start, dtype=float)
        self.ramp_dist = float(np.linalg.norm(self.ramp_from))
        self.ramp_px0 = (None if self.target_px is None
                         else np.array(self.target_px, dtype=float))
        self.stage = 5
        self.hold_hist = []
        self.hold_state = None
        self.hold_lock = None
        self.hold_lost = 0
        self.ramping = self.ramp_dist > 1e-6
        self.t_stage = time.perf_counter()
        if not self.ramping:
            self.ot.set_trap_position(self.args.trap_name, 0.0, 0.0)
            self.message = "trap at (0,0) -- waiting for a bead to stop diffusing"
            print("\nHOLD: trap already at (0, 0) um, the field centre.")
        else:
            secs = self.ramp_dist / self.args.speed_um_s
            self.message = (f"ramping {self.ramp_dist:.1f} um to (0,0) at "
                            f"{self.args.speed_um_s:g} um/s")
            print(f"\nHOLD: ramping the trap from ({self.ramp_from[0]:+.3f}, "
                  f"{self.ramp_from[1]:+.3f}) to (0, 0) um -- "
                  f"{self.ramp_dist:.2f} um at {self.args.speed_um_s:g} um/s, "
                  f"{secs:.2f} s.")
            print("  A straight line, not a jump: one command to the origin "
                  "would ask for ~1000 um/s and leave the bead behind.")
        print("  No transform is used here -- moving a held bead to the "
              "origin needs only the origin.")
        print(f"  then watching the detection nearest the centre over a "
              f"{HOLD_WINDOW_S:.1f} s window; held is < "
              f"{HELD_EXCURSION_NM:.0f} nm RMS")

    def _ramp_tick(self, img, t):
        """One step of the straight-line move, tracking the bead as it goes."""
        f = min(1.0, (t - self.t_stage) * self.args.speed_um_s /
                max(self.ramp_dist, 1e-9))
        pos = self.ramp_from * (1.0 - f)
        self.ot.set_trap_position(self.args.trap_name, float(pos[0]),
                                  float(pos[1]))
        p = self._refine_target(img)
        self.message = (f"ramping to (0,0): {f:.0%}, trap at "
                        f"({pos[0]:+.2f}, {pos[1]:+.2f}) um")
        if f < 1.0:
            return
        self.ramping = False
        self.t_stage = t
        print(f"  arrived at (0, 0) um in {f * self.ramp_dist:.2f} um of travel")
        if p is not None and self.ramp_px0 is not None:
            # The bead should have moved by the same distance the trap did.
            # Short means it slipped, which is the one failure a ramp can
            # still have and the one a jump has silently.
            moved = float(np.linalg.norm(p - self.ramp_px0)) * self.um_per_px
            print(f"  the bead moved {moved:.2f} um while the trap moved "
                  f"{self.ramp_dist:.2f} um ({moved / self.ramp_dist:.0%})")
            if moved < 0.5 * self.ramp_dist:
                print(f"  it did not come with the trap -- either it was "
                      f"never held, or {self.args.speed_um_s:g} um/s is past "
                      "what this trap drags. Lower --speed-um-s.")

    def _hold_tick(self, img, t):
        """Follow ONE bead and judge whether it is held.

        The first version re-picked the detection nearest the centre on every
        tick, which is wrong whenever two beads compete for "nearest": the
        target hops between them, the excursion history mixes two positions,
        and the RMS it reports is the distance between the beads rather than
        the motion of either. Measured 2026-09-04, that produced a verdict
        chattering at the 150 nm cut -- 55, 152, 61, 155, 143, 151, 149 nm --
        while the reported position jumped 300 px across the field. None of
        that was physics.

        So the bead is chosen once and then *followed*, and re-picking clears
        the history rather than extending it. The verdict also has hysteresis
        now, because a single cut on a noisy statistic is a coin toss at the
        boundary by construction.
        """
        if len(self.circles) == 0:
            self.message = "nothing detected at the centre"
            return
        h, w = img.shape
        centre = np.array([w / 2.0, h / 2.0])
        if self.hold_lock is None:
            near = self.circles[np.argmin(
                np.linalg.norm(self.circles[:, :2] - centre, axis=1))]
            self.hold_lock = np.array(near[:2], dtype=float)
            self.target_px = self.hold_lock.copy()
            self.hold_hist = []
            print(f"  locked onto the bead at ({self.hold_lock[0]:.1f}, "
                  f"{self.hold_lock[1]:.1f}) px, "
                  f"{np.linalg.norm(self.hold_lock - centre) * self.um_per_px:.2f}"
                  " um from the centre")
        p = self._refine_target(img)
        if p is None:
            self.hold_lost += 1
            if self.hold_lost > 10:
                print("  lost the locked bead; re-picking")
                self.hold_lock, self.hold_lost = None, 0
                self.hold_hist, self.hold_state = [], None
            return
        self.hold_lost = 0
        self.hold_hist.append((t, p[0], p[1]))
        self.hold_hist = [r for r in self.hold_hist if t - r[0] <= HOLD_WINDOW_S]
        if len(self.hold_hist) < 8:
            return
        span = self.hold_hist[-1][0] - self.hold_hist[0][0]
        if span < 0.8 * HOLD_WINDOW_S:
            return                     # judge on a full window or not at all
        a = np.array(self.hold_hist, dtype=float)[:, 1:3]
        rms = float(np.sqrt(((a - a.mean(axis=0)) ** 2).sum(axis=1).mean()))
        nm = rms * self.um_per_px * 1000.0
        off = float(np.linalg.norm(a.mean(axis=0) - centre))
        # Hysteresis, not one cut. A single threshold on a noisy statistic
        # flips on noise alone at the boundary, which is what produced the
        # 150 nm chatter -- so entering "held" and leaving it are different
        # numbers and the state persists between them.
        if self.hold_state is None:
            held = nm < HELD_ENTER_NM
        elif self.hold_state:
            held = nm < HELD_LEAVE_NM
        else:
            held = nm < HELD_ENTER_NM
        self.message = (f"locked bead: {nm:.0f} nm RMS over {span:.1f} s, "
                        f"{off:.0f} px from the cross -> "
                        f"{'HELD' if held else 'free'}")
        if held != self.hold_state:
            self.hold_state = held
            if held:
                print(f"  CAUGHT: bead held at ({a[:, 0].mean():.1f}, "
                      f"{a[:, 1].mean():.1f}) px, {nm:.0f} nm RMS over "
                      f"{span:.1f} s, {off:.0f} px "
                      f"({off * self.um_per_px:.2f} um) from the frame centre.")
                print("    if the trap is what is holding it, that pixel "
                      "position is p0. A bead stuck to the coverslip reads "
                      "the same, so press D to drive it -- only a trapped "
                      "bead follows.")
            else:
                print(f"  released or lost: {nm:.0f} nm RMS over {span:.1f} s")

    def _pick_target(self):
        if len(self.circles) == 0:
            self.message = "nothing detected -- cannot trap"
            return False
        h, w = self.core.getImageHeight(), self.core.getImageWidth()
        centre = np.array([w / 2.0, h / 2.0])
        iso = getattr(self.tracker, "iso_mask", np.zeros(0, dtype=bool))
        pool = (self.circles[iso] if len(iso) == len(self.circles) and iso.any()
                else self.circles)
        pick = pool[np.argmin(np.linalg.norm(pool[:, :2] - centre, axis=1))]
        self.target_px = np.array(pick[:2], dtype=float)
        um = np.asarray(self.transform.to_um(self.target_px), dtype=float)
        reach = float(math.hypot(um[0], um[1]))
        if reach > self.args.max_offset_um:
            self.message = (f"nearest bead is {reach:.1f} um out, past "
                            f"--max-offset-um {self.args.max_offset_um:g}")
            self.target_px = None
            return False
        self.target_um = um
        self.ot.set_trap_position(self.args.trap_name, float(um[0]),
                                  float(um[1]))
        tag = "PROVISIONAL" if self.provisional_why else "measured"
        print(f"\nTRAP -> ({um[0]:+.3f}, {um[1]:+.3f}) um  for bead at "
              f"({self.target_px[0]:.1f}, {self.target_px[1]:.1f}) px "
              f"[{tag} transform]")
        self.message = f"watching {GRAB_WATCH_S:.1f} s: is it held?"
        return True

    # -- per-tick work ----------------------------------------------------

    def _refine_target(self, img):
        h, w = img.shape
        nx, ny, mass = TFT.refine(img, self.target_px[0], self.target_px[1],
                                  self.scale["win"], 3, h, w)
        if mass <= 0:
            self.reject["mass"] += 1
            return None
        if math.hypot(nx - self.target_px[0],
                      ny - self.target_px[1]) > self.scale["r_px"]:
            self.reject["jump"] += 1
            return None
        self.reject["ok"] += 1
        self.target_px = np.array([nx, ny])
        return self.target_px

    def rate_report(self):
        out = []
        for st in sorted(self.stage_ticks):
            g = np.array(self.stage_ticks[st])
            if len(g) < 2:
                continue
            out.append(f"    {STAGES[st]:9s} {len(g):5d} ticks, "
                       f"{g.mean() * 1e3:6.1f} ms mean "
                       f"({1.0 / g.mean():5.1f} Hz), "
                       f"p90 {np.percentile(g, 90) * 1e3:6.1f} ms")
        r = self.reject
        tot = sum(r.values())
        if tot:
            out.append(f"    target refine: {r['ok']} kept, "
                       f"{r['mass']} empty window, {r['jump']} jumped past "
                       f"{self.scale['r_px']:.0f} px "
                       f"({r['ok'] / tot:.0%} kept)")
        return "\n".join(out)

    def tick(self, raw, img, frame8, step, t):
        """One frame. Returns nothing; mutates state and sets self.message.

        The two trackers have different signatures and different units:
        ``GpuTracker`` takes the raw full-resolution frame and answers in
        sensor pixels, ``Tracker`` takes the frame the display already
        decimated and answers in decimated ones. Everything downstream --
        targeting, refine, the transform -- works in ROI pixels, so the
        decimated answer is scaled back here rather than at each use.
        """
        if self.t_tick is not None:
            self.stage_ticks.setdefault(self.stage, []).append(t - self.t_tick)
        self.t_tick = t
        # Detection is for CHOOSING a bead, and by stage 3 one is chosen. The
        # drive needs only the target refine, so the detector -- the most
        # expensive thing in the tick -- is skipped once it has done its job.
        # The last circles stay on screen so the display does not change
        # character mid-run.
        if 1 <= self.stage <= 2 or self.stage == 5:
            if getattr(self.tracker, "full_frame", False):
                self.circles = self.tracker.update(raw)
            else:
                c = self.tracker.update(frame8, step)
                self.circles = (np.asarray(c, dtype=float) * float(step)
                                if len(c) else np.empty((0, 3)))
        if self.stage == 2 and self.target_px is not None:
            p = self._refine_target(img)
            if p is not None:
                self.watch.append((t, p[0], p[1]))
            if (not self.judged and t - self.t_stage > GRAB_WATCH_S
                    and len(self.watch) > 5):
                self._judge_grab()
        elif self.stage == 3 and self.target_px is not None:
            self._drive_tick(img, t)
        elif self.stage == 5:
            if self.ramping:
                self._ramp_tick(img, t)
            else:
                self._hold_tick(img, t)

    def _judge_grab(self):
        w = np.array(self.watch, dtype=float)[:, 1:3]
        rms = float(np.sqrt(((w - w.mean(axis=0)) ** 2).sum(axis=1).mean()))
        nm = rms * self.um_per_px * 1000.0
        held = nm < HELD_EXCURSION_NM
        self.message = (f"excursion {nm:.0f} nm over {GRAB_WATCH_S:.1f} s -> "
                        f"{'looks HELD' if held else 'looks FREE'}; "
                        "SPACE to oscillate")
        print(f"  {len(self.watch)} frames, RMS excursion {nm:.0f} nm "
              f"(cut {HELD_EXCURSION_NM:.0f}) -> "
              f"{'HELD' if held else 'STILL DIFFUSING'}")
        if not held:
            print("  a free bead here means the trap is not where the "
                  "transform says. The oscillation settles it either way.")
        self.judged = True                     # waiting for space

    def start_drive(self):
        """Check the whole sine before the first command, not per tick.

        The first version checked each commanded point as it went and stopped
        the drive when one left the limit. Measured 2026-09-04: the target
        bead sat 17.5 um from the origin, +5 um of x drive put the peak at
        22.4 um, and the run aborted after 4 tracked frames -- a fit that
        needs 20. The operator paid a full stage transition to learn
        something computable in advance.

        The fix that matters is not the check, it is what the refusal says.
        A bead near the edge of the range cannot be driven *there*, but it can
        be **brought to the origin first** and driven from there, where +-5 um
        is nowhere near any limit. That is what HOLD is for, and it is now the
        advice rather than a dead end.
        """
        centre = np.asarray(self.target_um, dtype=float)
        sched = TFT.sine_schedule(self.args.amp_um, self.args.freq_hz, "x",
                                  self.args.cycles, 50.0,
                                  (float(centre[0]), float(centre[1])))
        worst = max(math.hypot(x, y) for _, x, y in sched)
        if worst > self.args.max_offset_um:
            self.message = (f"drive would reach {worst:.1f} um > "
                            f"{self.args.max_offset_um:g} -- press H to bring "
                            "it to (0,0) first, then D")
            print(f"\n  REFUSED: the bead sits {np.linalg.norm(centre):.1f} um "
                  f"from the origin, so a {self.args.amp_um:g} um sine about "
                  f"it reaches {worst:.1f} um, past --max-offset-um "
                  f"{self.args.max_offset_um:g}.")
            print("    Press H to ramp it to (0,0) first and then D to drive "
                  "it there -- the same sine about the origin reaches only "
                  f"{self.args.amp_um:g} um.")
            print("    Or read the green trapping trapezoid off the GUI and "
                  "raise --max-offset-um deliberately. Points outside it are "
                  "clipped silently, which is why this refuses.")
            return False
        self.stage = 3
        self.drive = []
        return True

    def _drive_tick(self, img, t):
        el = t - self.t_stage
        d = self.args.amp_um * math.sin(2 * math.pi * self.args.freq_hz * el)
        x = float(self.target_um[0] + d)
        y = float(self.target_um[1])
        if math.hypot(x, y) > self.args.max_offset_um:
            self.message = "drive would leave --max-offset-um; stopped"
            self._finish_drive()
            return
        self.ot.set_trap_position(self.args.trap_name, x, y)
        p = self._refine_target(img)
        if p is not None:
            self.drive.append((el, p[0], p[1]))
        done = el >= self.args.cycles / self.args.freq_hz
        self.message = (f"driving {self.args.amp_um:g} um at "
                        f"{self.args.freq_hz:g} Hz -- "
                        f"{el * self.args.freq_hz:.1f} / "
                        f"{self.args.cycles:g} cycles")
        if done:
            self._finish_drive()

    def _finish_drive(self):
        self.ot.set_trap_position(self.args.trap_name,
                                  float(self.target_um[0]),
                                  float(self.target_um[1]))
        self.stage = 4
        self.t_stage = time.perf_counter()
        if len(self.drive) < 20:
            self.message = (f"only {len(self.drive)} frames tracked -- "
                            "inconclusive. SPACE to drive again")
            print(f"  INCONCLUSIVE: {len(self.drive)} frames is too few for a "
                  "4-parameter fit per axis. Why:")
            print(self.rate_report())
            return
        a = np.array(self.drive, dtype=float)
        col, lag, resid, off, slope = TFT.column_from_fit(
            a[:, 0], a[:, 1], a[:, 2], self.args.amp_um, self.args.freq_hz)
        follow = float(np.linalg.norm(col) * self.um_per_px)
        held = follow >= TFT.MIN_FOLLOW_FRAC
        ang = math.degrees(math.atan2(col[1], col[0]))
        self.result = dict(follow=follow, lag=lag, resid=resid, angle=ang,
                           col=col, drift=float(np.linalg.norm(slope) *
                                                self.um_per_px))
        self.message = (f"followed {follow:.0%} of the drive -> "
                        f"{'TRAPPED' if held else 'NOT TRAPPED'}")
        print(f"\n  {len(self.drive)} frames: response "
              f"{np.linalg.norm(col) * self.args.amp_um * self.um_per_px:.2f} um "
              f"for a {self.args.amp_um:g} um drive -> followed {follow:.0%}")
        print(f"  x drive moves the bead along ({col[0] / np.linalg.norm(col):+.3f},"
              f" {col[1] / np.linalg.norm(col):+.3f}) in px, i.e. {ang:+.1f} deg "
              f"from the +x pixel axis")
        print(f"  lag {lag:+.0f} deg, residual {resid:.0%}, drift "
              f"{self.result['drift']:.3f} um/s")
        print(f"  {'TRAPPED' if held else 'NOT TRAPPED'}")
        if held and self.provisional_why:
            want = math.degrees(math.atan2(self.transform.matrix[1, 0],
                                           self.transform.matrix[0, 0]))
            print(f"  the PROVISIONAL transform predicted {want:+.1f} deg, so "
                  f"it was off by {(ang - want + 180) % 360 - 180:+.1f} deg. "
                  "Run `trap_from_tracking.py calibrate` for the full matrix "
                  "-- one axis cannot give it.")


def draw(cv2, frame8, seq, step, tick_ms):
    bgr = cv2.cvtColor(frame8, cv2.COLOR_GRAY2BGR)
    s = 1.0 / step
    if seq.stage >= 1:
        iso = getattr(seq.tracker, "iso_mask", np.zeros(0, dtype=bool))
        if len(iso) != len(seq.circles):
            iso = np.zeros(len(seq.circles), dtype=bool)
        for (cx, cy, r), ok in zip(seq.circles, iso):
            cv2.circle(bgr, (int(round(cx * s)), int(round(cy * s))),
                       max(2, int(round(r * s))),
                       (90, 220, 90) if ok else (80, 80, 235), 1, cv2.LINE_AA)
    if seq.target_px is not None:
        tx, ty = int(round(seq.target_px[0] * s)), int(round(seq.target_px[1] * s))
        rr = max(4, int(round(seq.scale["r_px"] * s * 1.5)))
        cv2.circle(bgr, (tx, ty), rr, (255, 220, 60), 2, cv2.LINE_AA)
        cv2.line(bgr, (tx - rr - 6, ty), (tx - rr, ty), (255, 220, 60), 1)
        cv2.line(bgr, (tx + rr, ty), (tx + rr + 6, ty), (255, 220, 60), 1)
    h, w = bgr.shape[:2]
    cv2.drawMarker(bgr, (w // 2, h // 2), (200, 200, 200), cv2.MARKER_CROSS,
                   14, 1)
    name = STAGES[seq.stage]
    head = f"[{int(seq.stage)}] {name}   {seq.message}"
    cv2.putText(bgr, head, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (255, 255, 255), 1, cv2.LINE_AA)
    if seq.stage >= 1:
        iso_n = int(getattr(seq.tracker, "iso_mask",
                            np.zeros(0, dtype=bool)).sum())
        cv2.putText(bgr, f"{len(seq.circles)} objects, {iso_n} isolated past "
                         f"{seq.args.isolation_um:g} um", (6, 36),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 255, 200), 1,
                    cv2.LINE_AA)
    if seq.provisional_why:
        cv2.putText(bgr, f"PROVISIONAL transform: {seq.provisional_why}",
                    (6, 54), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (80, 200, 255), 1,
                    cv2.LINE_AA)
    if seq.result:
        r = seq.result
        cv2.putText(bgr, f"followed {r['follow']:.0%}  lag {r['lag']:+.0f} deg"
                         f"  axis {r['angle']:+.1f} deg  resid {r['resid']:.0%}",
                    (6, h - 26), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                    (255, 220, 60), 1, cv2.LINE_AA)
    cv2.putText(bgr, f"{w}x{h} (1/{step})  tick {tick_ms:.0f} ms  "
                     f"SPACE advance  ESC stop", (6, h - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
    return bgr


def build_parser():
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cfg", required=True)
    ap.add_argument("--roi", type=int, default=1200,
                    help="centred square ROI, px (default 1200). Centred "
                         "matters: the trap origin is the field centre, so an "
                         "off-centre ROI moves it")
    ap.add_argument("--display", type=int, default=900)
    ap.add_argument("--exposure-ms", type=float, default=None)
    ap.add_argument("--line", default=None)
    ap.add_argument("--intensity", type=float, default=None,
                    help="per-mille of full scale (0-1000), so 20 is 2%%")
    ap.add_argument("--light-device", default="Aura")
    ap.add_argument("--gpu", action="store_true",
                    help="detect on the full ROI frame via CuPy instead of "
                         "HoughCircles on the decimated one")
    ap.add_argument("--isolation-um", type=float, default=12.0)
    ap.add_argument("--trap-name", default="Trap 1")
    ap.add_argument("--create", action="store_true")
    ap.add_argument("--strength", type=float, default=1.0)
    ap.add_argument("--no-trap-on", action="store_true")
    ap.add_argument("--centre-um", type=float, nargs=2, default=[0.0, 0.0],
                    metavar=("X", "Y"))
    ap.add_argument("--max-offset-um", type=float, default=TFT.MAX_OFFSET_UM)
    ap.add_argument("--amp-um", type=float, default=5.0)
    ap.add_argument("--freq-hz", type=float, default=1.0)
    ap.add_argument("--cycles", type=float, default=5.0)
    ap.add_argument("--speed-um-s", type=float, default=10.0,
                    help="trap speed on the straight-line move to (0,0), um/s "
                         "(default 10). A 5 um 1 Hz sine peaks at 31 um/s, so "
                         "a stage-3 TRAPPED verdict is a measured upper bound "
                         "on what this trap drags")
    ap.add_argument("--calibration", default=str(TFT.DEFAULT_CAL))
    ap.add_argument("--laser-note", default=None)
    return ap


def main() -> int:
    # Line-buffer stdout. Python block-buffers it when it is a pipe rather
    # than a console, so a long-running window like this one produces NOTHING
    # readable until it exits -- which reads exactly like a hang, and did.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    ap = build_parser()
    args = ap.parse_args()
    if (args.line is None) != (args.intensity is None):
        ap.error("--line and --intensity go together: both, or neither")

    import cv2  # noqa: PLC0415

    core, camera = TFT.open_core(args.cfg, args.exposure_ms)
    if args.roi:
        core.setROI(*LV.centre_roi(core, args.roi))
    obj = TFT.objective_label(core)
    um_per_px, provenance, mf = TFT.pixel_size_um(core, obj)
    h, w = core.getImageHeight(), core.getImageWidth()
    print(f"{camera} {w}x{h} on {obj}, intermediate {mf:g}x, "
          f"pixel {um_per_px:.5f} um/px ({provenance}) -> field "
          f"{w * um_per_px:.1f} x {h * um_per_px:.1f} um")

    transform, why = usable_transform(args.calibration, (h, w), obj,
                                      um_per_px, camera)
    if why:
        print(f"PROVISIONAL px->um transform ({why}).")
        print("  Nominal scale, no rotation, y flipped. One of eight "
              "orientations -- stage 3 measures the real one.")
    else:
        print("measured px->um transform loaded:")
        print("  " + transform.report().replace("\n", "\n  "))

    shutter = core.getShutterDevice()
    lit, before = False, {}
    ot = None
    try:
        # --- illumination. Mirrors live_view.main; see the module header. ---
        core.setAutoShutter(False)
        core.setShutterOpen(False)
        if args.line is not None:
            engine = args.light_device
            if args.line not in core.getDevicePropertyNames(engine):
                lines = sorted(p for p in core.getDevicePropertyNames(engine)
                               if p.isupper())
                ap.error(f"{engine} has no line {args.line!r}. It has: "
                         f"{', '.join(lines) or '(none)'}")
            core.setProperty(engine, f"{args.line}_Intensity", args.intensity)
            core.setProperty(engine, args.line, 1)
            core.setShutterDevice(engine)
            core.setShutterOpen(True)
            lit = True
            for label in _TURRET_SHUTTERS:
                try:
                    before[label] = core.getShutterOpen(label)
                    core.setShutterOpen(label, True)
                except Exception as exc:
                    print(f"  {label}: could not open ({exc})")
            print(f"LIGHT ON: {engine}.{args.line} at {args.intensity:.0f}/1000 "
                  f"({args.intensity / 10:.1f}%).")
        else:
            print("Light off (no --line) -- expect a dark field.")

        tracker = (LV.GpuTracker(um_per_px, args.isolation_um, 100)
                   if args.gpu else LV.Tracker(um_per_px, args.isolation_um,
                                               100))
        if args.gpu:
            print(f"GPU detection on the full {w}x{h} ROI via "
                  f"{tracker.device}")
        ot = TFT.connect_trap(args.trap_name, args.create, args.strength,
                              (args.centre_um[0], args.centre_um[1]),
                              not args.no_trap_on)
        seq = Sequence(core, camera, ot, tracker, transform, why, args,
                       um_per_px)

        core.startContinuousSequenceAcquisition(0)
        win = f"{camera} - trap sequence"
        cv2.namedWindow(win, cv2.WINDOW_AUTOSIZE)
        print("\nSPACE advances a stage.  H = hold at (0,0).  "
              "D = drive again.  ESC stops.")
        tick_ms, t_prev = 0.0, None
        while True:
            try:
                frame = core.getLastImage()
            except Exception:
                if cv2.waitKey(20) == 27:
                    break
                continue
            now = time.perf_counter()
            if t_prev is not None:
                tick_ms = 0.8 * tick_ms + 0.2 * (now - t_prev) * 1e3
            t_prev = now
            raw = np.asarray(frame)
            sig = (int(raw[0, 0]), int(raw[-1, -1]))
            fresh = sig != seq.last_sig
            seq.last_sig = sig
            small, step = LV.decimate(raw, args.display)
            frame8, _ = LV.autoscale(small)
            if fresh:
                seq.frames += 1
                seq.tick(raw, raw.astype(np.float32) - TFT.OFFSET_ADU,
                         frame8, step, now)
            cv2.imshow(win, draw(cv2, frame8, seq, step, tick_ms))
            key = cv2.waitKey(1) & 0xFF
            if key == 27:
                break
            if key == 32:
                seq.advance()
            elif key in (ord("h"), ord("H")):
                seq.enter_hold()
            elif key in (ord("d"), ord("D")) and seq.target_um is not None:
                # After HOLD the bead is at the origin, so target_um has to
                # follow it there or the drive would be planned about where
                # the bead used to be.
                if seq.stage == 5 and not seq.ramping:
                    seq.target_um = np.zeros(2, dtype=float)
                if seq.start_drive():
                    seq.t_stage = time.perf_counter()
            try:
                if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                    break
            except cv2.error:
                break
        cv2.destroyAllWindows()
        cv2.waitKey(1)
        print(f"\n{seq.frames} frames, stage {seq.stage} "
              f"({STAGES[seq.stage]}) at exit")
        print("  measured, per stage:")
        print(seq.rate_report())
    finally:
        try:
            core.stopSequenceAcquisition()
        except Exception:
            pass
        if ot is not None:
            # Parked, NOT switched off: closing a window must not drop a bead.
            try:
                ot.set_trap_position(args.trap_name, args.centre_um[0],
                                     args.centre_um[1])
                print(f"trap parked at ({args.centre_um[0]:g}, "
                      f"{args.centre_um[1]:g}) um and left ON")
            except Exception as exc:
                print(f"could not park the trap: {exc}")
            ot.close()
        if lit:
            try:
                core.setProperty(args.light_device, args.line, 0)
                core.setShutterOpen(False)
                if shutter:
                    core.setShutterDevice(shutter)
            except Exception as exc:
                print(f"could not take the light down: {exc}")
        if before:
            print("  left open: " + ", ".join(before)
                  + " (closing Turret2Shutter would drop a live trap)")
        print("[dark, camera released]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
