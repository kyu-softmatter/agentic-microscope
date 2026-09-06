r"""The two-species sort, as a function, so it can run from inside a live view.

`sort_two_species.py` is the command-line front end and `live_dualcam_view.py`
calls `sort_once()` on the space bar. The logic lives here so there is one
copy: a live view that holds both cameras cannot shell out to the CLI, because
PVCAM hands a Kinetix to one process at a time, so the alternative to sharing
this module is duplicating it.

Everything here is measured on this instrument on 2026-09-06 unless it says
otherwise. The reasoning behind each constant is in `sort_two_species.py`'s
docstring; the short version:

  species labels   the two lines are STROBED, never simultaneous. Dragon Green
                   is bright enough that its emission tail past 561 nm reaches
                   the red camera, so with both lines lit the red camera sees
                   BOTH species (33 + 29 ~ 58 objects) and the assignment
                   collapses. Strobed: 34 red, 28 green, 0 ambiguous.
  blue -> red      vertical flip, then (-1.21, +1.32) px. Measured from that
                   same leak: Dragon Green on both cameras is the registration
                   target. Scale red/blue 0.99932 +- 0.00482.
  trap transform   px = p0 + diag([1,-1])/um_per_px @ um, no fitted parameter:
                   the addressable square is centred on the field, the OT
                   commands micrometres AT THE SAMPLE, and TRAP_ORIGIN_OFFSET_UM
                   pins the origin to ~1 um over five holds.
  collisions       four separate constraints -- pick separation, slot pitch,
                   exact pairwise transit minima, and static corridor
                   clearance. 6 um centre-to-centre between 5 um spheres is a
                   1 um surface gap, so the corridor bar does not move.
"""

from __future__ import annotations

import importlib.util
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]

TRAP_HALF_RANGE_UM = 40.0
LINES = ["UV", "CYAN", "GREEN", "RED", "NIR"]
BLUE_TO_RED_PX = (-1.21, 1.32)

SPECIES = [
    # key, camera, line, label, default destination sign in x
    ("red", "Kinetix_red", "GREEN", "abvigen-red", -1.0),
    ("green", "Kinetix_blue", "CYAN", "bangs-dragongreen", +1.0),
]


@dataclass
class SortOpts:
    per_species: int = 3
    slot_x_um: float = 18.0
    slot_pitch_um: float = 10.0
    collision_um: float = 8.0
    isolation_um: float = 8.0
    path_clear_um: float = 6.0
    area_tol: float = 1.5
    bead_um: float = 5.0
    step_um: float = 0.5
    settle_s: float = 0.12
    strength: float = 1.0
    trap_prefix: str = "sorter"
    cyan: int = 3
    green: int = 45
    laser_on: bool = False
    log: object = field(default=None)   # callable(str); defaults to print
    on_frame: object = field(default=None)  # callable(cam, frame, phase)
    taken: object = field(default=None)     # {species: set(slot y um)} filled
    flip: object = field(default=None)      # None = choose polarity, bool = forced


def _say(opts, msg):
    (opts.log or print)(msg)


def _emit(opts, cam, frame, phase):
    """Hand a frame to the viewer, if one asked for them.

    Wrapped because a drawing failure must never abort a sort that already
    has traps on and beads in transit.
    """
    cb = getattr(opts, "on_frame", None)
    if cb is None:
        return
    try:
        cb(cam, frame, phase)
    except Exception as exc:      # noqa: BLE001
        _say(opts, f"  (view frame dropped: {exc})")


def trap_sequence_consts():
    src = REPO / "config" / "tweezers" / "trap_sequence.py"
    spec = importlib.util.spec_from_file_location("_trap_sequence", src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_trap_sequence"] = mod
    spec.loader.exec_module(mod)
    return (float(mod.GRAB_SETTLE_S), float(mod.HELD_ENTER_NM),
            tuple(mod.TRAP_ORIGIN_OFFSET_UM))


def detect(frame, area_px, n_sigma=8.0):
    import cv2

    f32 = frame.astype(np.float32)
    residual = f32 - cv2.GaussianBlur(f32, (0, 0), 15)
    scale = float(np.median(np.abs(residual - np.median(residual)))) * 1.4826 or 1.0
    n, labels, stats, cent = cv2.connectedComponentsWithStats(
        (residual > n_sigma * scale).astype(np.uint8), 8)
    lo, hi = area_px
    out = []
    for i in range(1, n):
        area = int(stats[i, 4])
        if not (lo <= area <= hi):
            continue
        sel = labels == i
        out.append({"x": float(cent[i][0]), "y": float(cent[i][1]), "area": area,
                    "flux": float(residual[sel].sum())})
    out.sort(key=lambda d: -d["flux"])
    return out


def blue_to_red(pt, shape, offset=BLUE_TO_RED_PX):
    h, _w = shape
    return (pt[0] + offset[0], (h - 1) - pt[1] + offset[1])


def px_to_trap_um(px, p0, um):
    return ((px[0] - p0[0]) * um, -(px[1] - p0[1]) * um)


def trap_um_to_px(u, p0, um):
    return (p0[0] + u[0] / um, p0[1] - u[1] / um)


def path_is_clear(a, b, obstacles, clear_px, ignore_px=6.0):
    ax, ay = a
    bx, by = b
    vx, vy = bx - ax, by - ay
    seg2 = vx * vx + vy * vy
    if seg2 <= 0:
        return True, None
    worst = None
    for o in obstacles:
        if (math.hypot(o["x"] - ax, o["y"] - ay) < ignore_px
                or math.hypot(o["x"] - bx, o["y"] - by) < ignore_px):
            continue
        tt = max(0.0, min(1.0, ((o["x"] - ax) * vx + (o["y"] - ay) * vy) / seg2))
        d = math.hypot(o["x"] - (ax + tt * vx), o["y"] - (ay + tt * vy))
        if worst is None or d < worst:
            worst = d
    return (True, None) if worst is None else (worst >= clear_px, worst)


def min_separation_during_move(a_from, a_to, b_from, b_to):
    """Closest approach of two beads advanced in lockstep, exactly.

    Both traps move along their lines at the same NORMALISED rate, so the
    separation is linear in s and |d(s)|^2 is a quadratic with a closed-form
    minimum. Sampled coarsely instead, the dangerous case is missed: two beads
    can start and finish far apart and still pass within a diameter halfway.
    """
    d0 = (a_from[0] - b_from[0], a_from[1] - b_from[1])
    dv = ((a_to[0] - a_from[0]) - (b_to[0] - b_from[0]),
          (a_to[1] - a_from[1]) - (b_to[1] - b_from[1]))
    den = dv[0] ** 2 + dv[1] ** 2
    if den <= 1e-12:
        return math.hypot(*d0), 0.0
    s = max(0.0, min(1.0, -(d0[0] * dv[0] + d0[1] * dv[1]) / den))
    return math.hypot(d0[0] + s * dv[0], d0[1] + s * dv[1]), s


def geometry(core, binning_um=None):
    """p0, um/px and the bead-area window for the frame as currently set."""
    _s, _h, origin_off = trap_sequence_consts()
    um = binning_um if binning_um else core.getPixelSizeUm()
    w, h = core.getImageWidth(), core.getImageHeight()
    p0 = (w / 2.0 + origin_off[0] / um, h / 2.0 + origin_off[1] / um)
    return p0, um, (w, h)


def area_window(um, bead_um):
    r = 0.5 * bead_um / um
    return (max(2, int(0.25 * math.pi * r * r)), int(4.0 * math.pi * r * r))


def set_lines(core, cyan, green):
    for line in LINES:
        core.setProperty("Aura", line, "0")
        core.setProperty("Aura", f"{line}_Intensity", "0")
    for line, pm in (("CYAN", cyan), ("GREEN", green)):
        if pm > 0:
            core.setProperty("Aura", f"{line}_Intensity", str(int(pm)))
            core.setProperty("Aura", line, "1")
    core.setProperty("Aura", "State", "1" if (cyan or green) else "0")
    core.waitForDevice("Aura")


def flush_frame(core, n, tries=3):
    """Newest frame after discarding n-1 stale ones.

    Each snap is paired with its getImage: the camera hands a frame back for
    every snapImage, and leaving those unretrieved is what produced the
    intermittent `Unknown error in the device (1)` on a strobe switch. The
    discard count is unchanged -- it is there to clear frames exposed under
    the previous line -- and a device error is retried rather than aborting
    a sort mid-field.
    """
    last = None
    for attempt in range(tries):
        try:
            for _ in range(n):
                core.snapImage()
                last = core.getImage()
            return last
        except RuntimeError:
            if attempt == tries - 1:
                raise
            time.sleep(0.2)
    return last


def survey(core, opts, area_px, shape):
    """Both species, each under its own line only, in RED-camera coordinates."""
    w, h = shape
    found = {}
    for key, cam, line, label, sign in SPECIES:
        set_lines(core, opts.cyan if line == "CYAN" else 0,
                  opts.green if line == "GREEN" else 0)
        time.sleep(0.25)
        core.setCameraDevice(cam)
        img = np.asarray(flush_frame(core, 6))
        _emit(opts, cam, img, f"survey {label}")
        ds = detect(img, area_px)
        if key == "green":
            ds = [{**d, **dict(zip(("x", "y"), blue_to_red((d["x"], d["y"]), (h, w))))}
                  for d in ds]
        for d in ds:
            d.update(species=key, label=label, sign=sign)
        found[key] = ds
    return found


def slot_ys(opts):
    """Slot y positions, centre outward, inside the addressable range.

    A column cannot run past TRAP_HALF_RANGE_UM, so it holds
    2*floor(range/pitch)+1 slots -- 9 at the 10 um default. That is the ceiling
    on how many of a species can ever be parked, whatever the trap count
    allows: the GUI took 160 traps without complaint (measured 2026-09-05), so
    destinations, not traps, are what runs out. Centre outward keeps the early
    rounds' journeys short.
    """
    n = int(TRAP_HALF_RANGE_UM // opts.slot_pitch_um)
    return sorted((i * opts.slot_pitch_um for i in range(-n, n + 1)),
                  key=lambda y: (abs(y), y))


def plan(found, p0, um, opts):
    """Cargo, destinations and routes. Pure geometry -- touches no hardware."""
    every = found["red"] + found["green"]
    if not every:
        return [], [], every, "nothing detected"
    areas = np.array([d["area"] for d in every], float)
    med = float(np.median(areas))
    lo_a, hi_a = med / opts.area_tol, med * opts.area_tol
    iso_px, coll_px = opts.isolation_um / um, opts.collision_um / um

    # Where earlier rounds already parked beads. A parked bead is bright,
    # isolated and sits closest to the next free slot, so without excluding it
    # the pool prefers it and the round shuffles sorted beads down the column
    # instead of fetching new ones. Only knowable once polarity is locked,
    # which is exactly when `taken` is non-empty.
    parked = {}
    held = opts.taken or {}
    if opts.flip is not None:
        for key, _c, _l, _lab, sign in SPECIES:
            sx = (-sign if opts.flip else sign) * opts.slot_x_um
            parked[key] = [(sx, y) for y in held.get(key, ())]

    pool = {}
    for key, _c, _l, label, sign in SPECIES:
        cand = []
        for d in found[key]:
            if not (lo_a <= d["area"] <= hi_a):
                continue
            u = px_to_trap_um((d["x"], d["y"]), p0, um)
            if abs(u[0]) > TRAP_HALF_RANGE_UM or abs(u[1]) > TRAP_HALF_RANGE_UM:
                continue
            if min((math.hypot(d["x"] - o["x"], d["y"] - o["y"])
                    for o in every if o is not d), default=1e9) < iso_px:
                continue
            if any(math.hypot(u[0] - sx, u[1] - sy) < opts.collision_um
                   for sx, sy in parked.get(key, ())):
                continue          # already parked in this column; leave it be
            cand.append({**d, "trap_um": u})
            if len(cand) >= max(6, 6 * opts.per_species):
                break
        pool[key] = cand

    # Slots filled by earlier rounds are off the table. Without this every
    # round re-targets the centre and drives new beads onto parked ones.
    free = {k: [y for y in slot_ys(opts) if y not in held.get(k, ())]
            for k in pool}
    counts = {k: min(opts.per_species, len(pool[k]), len(free[k])) for k in pool}

    def columns(flip):
        out = {}
        for key, _c, _l, _lab, sign in SPECIES:
            out[key] = [((-sign if flip else sign) * opts.slot_x_um, y)
                        for y in free[key][:counts[key]]]
        return out

    def cost(cols):
        tot = 0.0
        for key in counts:
            grp = sorted(pool[key][:counts[key]], key=lambda c: c["trap_um"][1])
            for c, s in zip(grp, sorted(cols[key], key=lambda s: s[1])):
                tot += math.hypot(s[0] - c["trap_um"][0], s[1] - c["trap_um"][1])
        return tot

    cand_cols = {f: columns(f) for f in (False, True)}
    costs = {f: cost(cand_cols[f]) for f in cand_cols}
    if opts.flip is None:
        flip = min(costs, key=costs.get)
    else:
        # Locked after round 1. Re-choosing polarity mid-run would send one
        # species into the column the other is already parked in.
        flip = bool(opts.flip)
    slots = cand_cols[flip]

    # Each slot chooses its cargo from the pool: clear route first, then
    # shortest. Committing to the flux-brightest and checking routes afterwards
    # gave 1 of 5 usable on a 91-object field; this gave 5 of 6.
    cargo = []
    for key in ("red", "green"):
        avail = list(pool[key])
        taken = []
        for s in sorted(slots[key], key=lambda s: s[1]):
            s_px = trap_um_to_px(s, p0, um)
            scored = []
            for d in avail:
                if any(math.hypot(d["x"] - q["x"], d["y"] - q["y"]) < coll_px
                       for q in taken + cargo):
                    continue
                if taken and d["trap_um"][1] < taken[-1]["trap_um"][1]:
                    continue          # monotone in y: no crossings in a column
                ok, worst = path_is_clear((d["x"], d["y"]), s_px, every,
                                          opts.path_clear_um / um)
                scored.append((not ok, math.hypot(s[0] - d["trap_um"][0],
                                                  s[1] - d["trap_um"][1]), worst, d))
            if not scored:
                continue
            scored.sort(key=lambda r: (r[0], r[1]))
            blocked, trav, worst, d = scored[0]
            c = {**d, "slot_um": s, "slot_px": s_px, "travel_um": trav,
                 "path_clear": not blocked,
                 "path_worst_um": (worst * um) if worst is not None else None}
            taken.append(c)
            cargo.append(c)
            avail = [a for a in avail if a is not d]

    # exact pairwise transit minima
    keep, dropped = [], []
    for c in cargo:
        bad = next(((q, *min_separation_during_move(
            c["trap_um"], c["slot_um"], q["trap_um"], q["slot_um"]))
            for q in keep
            if min_separation_during_move(c["trap_um"], c["slot_um"],
                                          q["trap_um"], q["slot_um"])[0]
            < opts.collision_um), None)
        if bad is None:
            keep.append(c)
        else:
            q, sep, when = bad
            c["dropped_because"] = (f"would pass {sep:.1f} um from {q['label']} at "
                                    f"{when:.0%} of the move")
            dropped.append(c)
    sides = {k: ("+x" if slots[k][0][0] > 0 else "-x") for k in slots} if counts else {}
    why = (f"pool {', '.join(f'{len(pool[k])} {k}' for k in pool)}; "
           f"red -> {sides.get('red', '?')}, green -> {sides.get('green', '?')}; "
           f"travel {costs[flip]:.0f} um (other polarity {costs[not flip]:.0f})")
    return keep, dropped, every, why, flip


def sort_once(core, ot, opts: SortOpts | None = None) -> dict:
    """Survey, plan and transport. Uses an EXISTING core and tweezers link."""
    opts = opts or SortOpts()
    grab_settle, held_nm, _off = trap_sequence_consts()
    p0, um, shape = geometry(core)
    area_px = area_window(um, opts.bead_um)

    found = survey(core, opts, area_px, shape)
    cargo, dropped, every, why, flip = plan(found, p0, um, opts)
    _say(opts, f"survey: {len(found['red'])} red, {len(found['green'])} green")
    _say(opts, f"plan: {why}")
    if dropped:
        _say(opts, f"  {len(dropped)} dropped on transit collision")
    if not cargo:
        _say(opts, "  no cargo. Nothing to sort.")
        return {"moved": [], "lost": [], "why": why, "flip": flip}

    batch = [c for c in cargo if c["path_clear"]]
    blocked = len(cargo) - len(batch)
    if blocked:
        _say(opts, f"  {blocked} corridor(s) blocked -- skipped")
    if not batch:
        return {"moved": [], "lost": [], "why": "all corridors blocked",
                "flip": flip}

    if opts.laser_on:
        ot.laser_on()
        _say(opts, "  LASER_ON sent (class-4 1064 nm)")

    names = [f"{opts.trap_prefix}-{i}" for i in range(1, len(batch) + 1)]
    for c, nm in zip(batch, names):
        c["trap_name"] = nm
        # Delete-then-create is idempotent: TRAP_DELETE on an absent name
        # answers -22 and is harmless.
        #
        # This comment used to say the GUI has a trap-COUNT ceiling, from a -20
        # "requested resource not supported". That is wrong and was used to
        # argue against trapping more particles: on 2026-09-05, 160 named traps
        # were created and deleted cleanly in one go. Whatever produced that
        # -20, it was not running out of trap slots. What actually limits this
        # sort is destinations -- TRAP_HALF_RANGE_UM with slot_pitch_um gives
        # slot_ys(), 9 per species -- and in practice the candidate pool runs
        # dry before even those fill.
        for call in (lambda: ot.delete_trap(nm), lambda: ot.create_simple_trap(nm)):
            try:
                call()
            except Exception:
                pass
        ot.set_trap_strength(nm, opts.strength)
        fx, fy = c["trap_um"]
        ot.trap_off(nm)                 # POSITION before ON, always
        ot.set_trap_position(nm, round(fx, 4), round(fy, 4))
        ot.trap_on(nm)
    _say(opts, f"  {len(batch)} traps on, ~1/{len(batch)} of the beam each")
    time.sleep(grab_settle)

    longest = max(c["travel_um"] for c in batch)
    n_steps = max(1, int(math.ceil(longest / opts.step_um)))
    _say(opts, f"  transporting: {n_steps} steps, longest journey {longest:.1f} um")
    watch = getattr(opts, "on_frame", None) is not None
    if watch:
        # CYAN and GREEN together for the whole transport. With both lines
        # on, each camera sees its own species in its own band and no line
        # switch is needed between steps -- so none of the 0.25 s Aura
        # settles that make the survey slow. survey() leaves CYAN only,
        # which would show the green species and leave red beads dark.
        # The cost is real and it is the red beads': ~n_steps * settle_s of
        # 589-610 nm excitation they do not get when nobody is watching.
        set_lines(core, opts.cyan, opts.green)
        _say(opts, f"  watching: both lines on for ~"
                   f"{n_steps * opts.settle_s:.1f} s of transport")
    for k in range(1, n_steps + 1):
        s = k / n_steps
        for c in batch:
            fx, fy = c["trap_um"]
            sx, sy = c["slot_um"]
            ot.set_trap_position(c["trap_name"], round(fx + (sx - fx) * s, 4),
                                 round(fy + (sy - fy) * s, 4))
        time.sleep(opts.settle_s)
        if watch:
            # Alternate bodies so both species keep updating. One paired
            # snap each step, ~20 ms of readout, no extra settle.
            _k, _cam = SPECIES[k % len(SPECIES)][0], SPECIES[k % len(SPECIES)][1]
            try:
                core.setCameraDevice(_cam)
                _emit(opts, _cam, np.asarray(flush_frame(core, 1)),
                      f"transport {k}/{n_steps}")
            except RuntimeError as exc:
                _say(opts, f"  watch frame skipped: {exc}")
    time.sleep(grab_settle)

    w, h = shape
    moved, lost = [], []
    for key, cam, line, _label, _sign in SPECIES:
        grp = [c for c in batch if c["species"] == key]
        if not grp:
            continue
        set_lines(core, opts.cyan if line == "CYAN" else 0,
                  opts.green if line == "GREEN" else 0)
        time.sleep(0.25)
        core.setCameraDevice(cam)
        img = np.asarray(flush_frame(core, 8))
        _emit(opts, cam, img, f"arrival {key}")
        ds = detect(img, area_px)
        if key == "green":
            ds = [{**d, **dict(zip(("x", "y"), blue_to_red((d["x"], d["y"]), (h, w))))}
                  for d in ds]
        for c in grp:
            sp, st = c["slot_px"], trap_um_to_px(c["trap_um"], p0, um)
            arrived = min((math.hypot(d["x"] - sp[0], d["y"] - sp[1]) for d in ds),
                          default=1e9) * um
            left = min((math.hypot(d["x"] - st[0], d["y"] - st[1]) for d in ds),
                       default=1e9) * um
            ok = (arrived < max(1.5, 0.1 * c["travel_um"])
                  and left > max(2.0, 0.15 * c["travel_um"]))
            rec = {"trap": c["trap_name"], "label": c["label"], "species": key,
                   "to_um": list(c["slot_um"]), "travel_um": c["travel_um"],
                   "arrived_um": arrived, "left_behind_um": left}
            (moved if ok else lost).append(rec)
            _say(opts, f"    {c['label']:18s} -> ({c['slot_um'][0]:+6.1f},"
                       f"{c['slot_um'][1]:+6.1f}) um  arrived {arrived:5.2f} um  "
                       f"{'MOVED' if ok else 'NOT MOVED'}")

    for c in batch:                      # release only what actually arrived
        if any(m["trap"] == c["trap_name"] for m in moved):
            ot.trap_off(c["trap_name"])
    _say(opts, f"  sorted {len(moved)} of {len(batch)}; released them at their slots")
    return {"moved": moved, "lost": lost, "why": why, "flip": flip,
            "blocked": blocked, "dropped_transit": len(dropped)}


def sort_until_full(core, ot, opts: SortOpts | None = None,
                    max_rounds: int = 12, stall_rounds: int = 2) -> dict:
    """Round after round until both columns are full, or nothing is moving.

    Three independent stops, because "sort every particle" is not reachable:
    a column holds len(slot_ys(opts)) per species, so a crowded field always
    outnumbers its destinations. Stops on columns full, on an empty pool, or on
    stall_rounds consecutive rounds that moved nothing -- the last matters on a
    sticky sample, where retrying forever only adds dose.

    A slot counts as filled only when a bead ARRIVED, so one lost to adhesion
    leaves its slot open for a later round.
    """
    opts = opts or SortOpts()
    cap = len(slot_ys(opts))
    taken = {key: set() for key, *_rest in SPECIES}
    flip, rounds, stalls = None, [], 0
    for r in range(1, max_rounds + 1):
        opts.taken = {k: set(v) for k, v in taken.items()}
        opts.flip = flip
        done = sum(len(v) for v in taken.values())
        _say(opts, f"--- round {r}: {done}/{cap * len(SPECIES)} slots filled ---")
        res = sort_once(core, ot, opts)
        rounds.append(res)
        if res.get("flip") is not None:
            flip = res["flip"]
        gained = 0
        for m in res["moved"]:
            taken[m["species"]].add(m["to_um"][1])
            gained += 1
        if all(len(taken[k]) >= cap for k in taken):
            _say(opts, "  both columns full -- stopping")
            break
        if not res["moved"] and not res["lost"]:
            _say(opts, "  nothing left to pick up -- stopping")
            break
        stalls = 0 if gained else stalls + 1
        if stalls >= stall_rounds:
            _say(opts, f"  {stalls} rounds moved nothing -- stopping")
            break
    filled = sum(len(v) for v in taken.values())
    _say(opts, f"=== {filled}/{cap * len(SPECIES)} slots filled in "
               f"{len(rounds)} round(s) ===")
    return {"rounds": rounds, "filled": {k: sorted(v) for k, v in taken.items()},
            "cap_per_species": cap}
