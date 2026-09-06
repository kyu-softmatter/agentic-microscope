r"""Sort the two bead species into two spatial groups with the optical trap.

    python config/session/sort_two_species.py --plan
    python config/session/sort_two_species.py --run --laser-on --per-species 3

    Abvigen red   (Kinetix_red,  GREEN line) -> slots at x = -SLOT_X um
    Dragon Green  (Kinetix_blue, CYAN  line) -> slots at x = +SLOT_X um

N SIMULTANEOUS TRAPS, MOVED IN LOCKSTEP
---------------------------------------
The AOD time-shares one beam, so N traps get about 1/N of the power each --
173.5 pN/um at n_traps=1 against 43.4 at n_traps=4 on this repo's model. That
matters when the trap is marginal, and it was: 8.27 pN/um measured at dial 30
against 104 modelled. The operator raised the power and states it is now more
than enough for N traps (2026-09-06), so the beads are transported TOGETHER.

That buys speed and costs a new failure mode. With one trap at a time the only
collision risk is the static corridor; with N in flight, two beads can be
perfectly clear of every obstacle and still run into each other EN ROUTE. So
the check below is not "is the path clear" but "do any two cargo beads come
within a contact distance of one another at any instant during the move", which
is a different question with a different answer.

Every command still returns 0 regardless (SAFETY.md §0), so each bead's arrival
is verified individually from the images afterwards -- N traps makes the
transport parallel, not the verification.

WHERE THE SPECIES LABELS COME FROM
----------------------------------
The lines are STROBED, never both on at once. Measured 2026-09-06:

    GREEN only -> Kinetix_red 33 beads, Kinetix_blue 0
    CYAN  only -> Kinetix_red 56 beads, Kinetix_blue 29

CYAN alone puts MORE on the red camera than GREEN does, and CYAN excites the
Abvigen dye more weakly than GREEN, so the excess cannot be red beads -- Dragon
Green is bright enough (~29x more signal per per-mille) that its emission tail
past 561 nm gets through the splitter and FF01-595/31. With both lines lit the
red camera sees 33 + 29 ~ 58 objects and "seen on red" stops meaning "red
bead". Strobed, the assignment is clean: 34 red, 28 green, 0 ambiguous.

Blue detections are mapped into RED-camera coordinates, which is the frame the
trap transform lives in, using the registration measured the same day from that
very leak (Dragon Green visible on both cameras is the registration target):

    vertical flip, then dx = -1.21 px, dy = +1.32 px
    scale red/blue = 0.99932 +- 0.00482, i.e. 1.000

THREE COLLISION CONSTRAINTS, NOT ONE
------------------------------------
"Sorting considering particle collision" is three separate things and each one
costs a bead if skipped:

  1. PICK separation   two beads chosen as cargo must start far enough apart
                       that neither grab disturbs the other.
  2. SLOT separation   destinations are pitched at --slot-pitch-um. Two 5 um
                       spheres touch centre-to-centre at 5 um, and each sits in
                       its well with an excursion, so slots closer than ~8 um
                       will end up in contact.
  3. TRANSIT collision THE ONE THAT ONLY EXISTS WITH N TRAPS. All traps
                       advance along their straight lines at the same
                       normalised rate, so each pair's separation is a
                       quadratic in normalised time and its minimum has a
                       closed form. Two beads that start 40 um apart and end
                       40 um apart can still pass within 2 um of each other in
                       the middle. Pairs that would collide are dropped from
                       the batch rather than launched and hoped for.
  4. PATH clearance    Dragging a bead in a
                       straight line to its slot sweeps a live trap across the
                       field, and anything it passes within a bead radius of
                       may be picked up, knocked, or swapped for the cargo.
                       Most of the beads in this sample are stuck to the glass
                       (population median excursion 114.9 nm against a 259 nm
                       free expectation), so obstacles do not move out of the
                       way. Each route is checked against every detected
                       object and the move is SKIPPED rather than attempted if
                       the corridor is not clear.

WHAT IT WILL NOT DO
-------------------
  · no LASER_ON unless --laser-on is passed (SAFETY.md §1: arm at the GUI).
  · no LASER_OFF at exit. TRAP_OFF is sent to RELEASE cargo at its slot, which
    is the operation, not tidying up -- SAFETY.md §1 forbids the latter.
  · it does not write ZDrive, the Nosepiece, or any COLLISION_DEVICE.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

DEFAULT_CFG = REPO / "config" / "micromanager" / "dualcam_twocolour.cfg"
LINES = ["UV", "CYAN", "GREEN", "RED", "NIR"]
TRAP_HALF_RANGE_UM = 40.0

#: Blue -> red, after a vertical flip, in px. Measured 2026-09-06 from Dragon
#: Green visible on both cameras under CYAN: 24 of 27 objects matched within
#: 8 px, translation -1.21 +- 2.05 and +1.32 +- 1.07 px, scale 0.99932.
#: Zero within its own scatter, kept as the measured value rather than rounded
#: to zero so a later re-measurement has something to disagree with.
BLUE_TO_RED_PX = (-1.21, 1.32)

SPECIES = [
    # key, camera, line, label, destination sign in x
    ("red", "Kinetix_red", "GREEN", "abvigen-red", -1.0),
    ("green", "Kinetix_blue", "CYAN", "bangs-dragongreen", +1.0),
]


def _trap_sequence():
    src = REPO / "config" / "tweezers" / "trap_sequence.py"
    spec = importlib.util.spec_from_file_location("_trap_sequence", src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_trap_sequence"] = mod
    spec.loader.exec_module(mod)
    return mod


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


def px_to_trap_um(px, p0, um_per_px):
    return ((px[0] - p0[0]) * um_per_px, -(px[1] - p0[1]) * um_per_px)


def trap_um_to_px(um, p0, um_per_px):
    return (p0[0] + um[0] / um_per_px, p0[1] - um[1] / um_per_px)


def path_is_clear(a_px, b_px, obstacles, clear_px, ignore_px=6.0):
    """Is the straight corridor from a to b free of obstacles?

    Point-to-segment distance for every detected object. Objects within
    `ignore_px` of either endpoint are skipped -- the cargo itself is at one
    end, and whatever sits at the destination is the caller's business.
    """
    ax, ay = a_px
    bx, by = b_px
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
    if worst is None:
        return True, None
    return worst >= clear_px, worst


def min_separation_during_move(a_from, a_to, b_from, b_to):
    """Closest approach of two beads moved in lockstep, and when it happens.

    Both traps advance along their straight lines at the same NORMALISED rate,
    so at normalised time s in [0, 1] the separation vector is
    ``d(s) = (a_from - b_from) + s * ((a_to - a_from) - (b_to - b_from))``,
    i.e. linear in s -- and |d(s)|^2 is a quadratic with a closed-form minimum
    at ``s* = -(d0 . dv) / (dv . dv)``, clamped to the interval.

    Worth being exact about rather than sampling, because the dangerous case is
    narrow: two beads can start far apart and finish far apart and still pass
    within a bead diameter halfway through, and a sampled check with a coarse
    step walks straight past it.
    """
    d0 = (a_from[0] - b_from[0], a_from[1] - b_from[1])
    dv = ((a_to[0] - a_from[0]) - (b_to[0] - b_from[0]),
          (a_to[1] - a_from[1]) - (b_to[1] - b_from[1]))
    denom = dv[0] * dv[0] + dv[1] * dv[1]
    if denom <= 1e-12:                     # parallel, equal-length moves
        return math.hypot(*d0), 0.0
    s = -(d0[0] * dv[0] + d0[1] * dv[1]) / denom
    s = max(0.0, min(1.0, s))
    return math.hypot(d0[0] + s * dv[0], d0[1] + s * dv[1]), s


def rms_nm(track, um_per_px):
    a = np.array(track)
    return float(np.sqrt(((a - a.mean(axis=0)) ** 2).sum(axis=1).mean())
                 * um_per_px * 1000.0)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--plan", action="store_true", help="pick and plan, send nothing")
    p.add_argument("--run", action="store_true")
    p.add_argument("--cfg", default=str(DEFAULT_CFG))
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--trap", default="sorter")
    p.add_argument("--strength", type=float, default=1.0)
    p.add_argument("--laser-on", action="store_true")
    p.add_argument("--per-species", type=int, default=3)
    p.add_argument("--slot-x-um", type=float, default=25.0,
                   help="|x| of the two destination columns")
    p.add_argument("--slot-pitch-um", type=float, default=10.0,
                   help="spacing between slots in a column; two 5 um beads touch at 5")
    p.add_argument("--collision-um", type=float, default=8.0)
    p.add_argument("--isolation-um", type=float, default=12.0)
    p.add_argument("--path-clear-um", type=float, default=6.0,
                   help="required clearance from the drag corridor to any other object")
    p.add_argument("--area-tol", type=float, default=1.5)
    p.add_argument("--bead-um", type=float, default=5.0)
    p.add_argument("--step-um", type=float, default=0.5)
    p.add_argument("--settle-s", type=float, default=0.12)
    p.add_argument("--cyan", type=int, default=3)
    p.add_argument("--green", type=int, default=45)
    p.add_argument("--exposure-ms", type=float, default=10.0)
    p.add_argument("--binning", default="2x2")
    p.add_argument("--out", default=None)
    args = p.parse_args(argv)
    if not (args.plan or args.run):
        p.error("pass --plan (safe) or --run")

    from pymmcore_plus import CMMCorePlus

    TS = _trap_sequence()
    settle_grab = float(TS.GRAB_SETTLE_S)
    held_nm = float(TS.HELD_ENTER_NM)
    origin_off = tuple(TS.TRAP_ORIGIN_OFFSET_UM)

    core = CMMCorePlus()
    core.loadSystemConfiguration(args.cfg)
    core.setConfig("TwoColour", "GreenRed-Widefield")
    core.waitForConfig("TwoColour", "GreenRed-Widefield")
    core.setAutoShutter(False)
    for _k, cam, _l, _lab, _s in SPECIES:
        core.setCameraDevice(cam)
        core.setProperty(cam, "Binning", args.binning)
        core.clearROI()
        core.setExposure(args.exposure_ms)
    um = core.getPixelSizeUm()
    w, h = core.getImageWidth(), core.getImageHeight()
    p0 = (w / 2.0 + origin_off[0] / um, h / 2.0 + origin_off[1] / um)
    r = 0.5 * args.bead_um / um
    area_px = (max(2, int(0.25 * math.pi * r * r)), int(4.0 * math.pi * r * r))
    print(f"objective {core.getStateLabel('Nosepiece')}, {um:.4f} um/px, frame {w}x{h}",
          flush=True)
    print(f"trap (0,0) at px ({p0[0]:.1f}, {p0[1]:.1f}); square +-{TRAP_HALF_RANGE_UM:g} um",
          flush=True)

    def light(cyan, green):
        for line in LINES:
            core.setProperty("Aura", line, "0")
            core.setProperty("Aura", f"{line}_Intensity", "0")
        for line, pm in (("CYAN", cyan), ("GREEN", green)):
            if pm > 0:
                core.setProperty("Aura", f"{line}_Intensity", str(int(pm)))
                core.setProperty("Aura", line, "1")
        core.setProperty("Aura", "State", "1" if (cyan or green) else "0")
        core.waitForDevice("Aura")

    def frames_of(cam, n=6):
        core.setCameraDevice(cam)
        out = []
        for _ in range(n):
            core.snapImage()
            out.append(np.asarray(core.getImage()))
        return out

    def survey():
        """Strobed: each species under its own line, in red-camera coordinates."""
        found = {}
        for key, cam, line, label, sign in SPECIES:
            light(args.cyan if line == "CYAN" else 0,
                  args.green if line == "GREEN" else 0)
            time.sleep(0.25)
            ds = detect(frames_of(cam)[-1], area_px)
            if key == "green":
                ds = [{**d, **dict(zip(("x", "y"),
                                       blue_to_red((d["x"], d["y"]), (h, w))))}
                      for d in ds]
            for d in ds:
                d["species"] = key
                d["label"] = label
                d["sign"] = sign
            found[key] = ds
        return found

    report = {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "um_per_px": um, "p0_px": list(p0),
              "registration_blue_to_red_px": list(BLUE_TO_RED_PX)}

    try:
        found = survey()
        every = found["red"] + found["green"]
        print(f"\nstrobed survey: {len(found['red'])} red, {len(found['green'])} green "
              f"({len(every)} objects total)", flush=True)

        # ── pick cargo, per species ─────────────────────────────────────────
        areas = np.array([d["area"] for d in every], float)
        med = float(np.median(areas))
        lo_a, hi_a = med / args.area_tol, med * args.area_tol
        iso_px = args.isolation_um / um
        coll_px = args.collision_um / um
        # A POOL, not a final pick. Route clearance depends on WHICH slot a
        # bead is sent to, and the slots depend on how many beads are chosen --
        # so committing to the flux-brightest N up front and checking the
        # corridors afterwards means living with whatever routes they happen to
        # have. On this sample that lost 4 of 5: the field carries ~91 objects
        # in 156 um and a 6 um exclusion is not negotiable (6 um centre-to-
        # centre between 5 um spheres is a 1 um surface gap).
        #
        # There are 39 red and 52 green candidates, so the abundance is the
        # answer: gather a pool several times larger than needed, then let the
        # SLOTS choose their cargo from it by route clearance. Routing around
        # obstacles would be the alternative, and it is the wrong trade here --
        # a detour sweeps a longer corridor through the same crowded field.
        pool = {}
        for key, _cam, _line, label, sign in SPECIES:
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
                cand.append({**d, "trap_um": u, "species": key, "label": label,
                             "sign": sign})
                if len(cand) >= max(6, 6 * args.per_species):
                    break
            pool[key] = cand
        print(f"  candidate pool: " + ", ".join(
            f"{len(pool[k])} {k}" for k in pool), flush=True)
        cargo = [c for k in pool for c in pool[k][:args.per_species]]
        if not cargo:
            print("  no cargo qualifies. Nothing to sort.", flush=True)
            report["verdict"] = "no cargo"
            return 1

        # ── destination slots, two columns ──────────────────────────────────
        #
        # WHICH SPECIES GETS WHICH SIDE IS ARBITRARY, SO CHOOSE IT. Sorting
        # only requires the two groups end up separated; nothing requires red
        # to go left. Fixing the polarity in advance can force every bead to
        # cross the whole field: on the first run 3 of 4 corridors came out
        # blocked because the red beads happened to sit on the right and were
        # being sent left, through 83 detected objects. Picking the polarity
        # with the smaller total travel is free and removes most of those
        # crossings -- shorter routes sweep past fewer obstacles, and the
        # obstacles here are mostly stuck to the glass and will not move aside.
        counts = {k: sum(1 for c in cargo if c["species"] == k) for k, *_ in SPECIES}

        def columns(flip):
            out = {}
            for key, _cam, _line, _label, sign in SPECIES:
                n = counts[key]
                ys = [(i - (n - 1) / 2.0) * args.slot_pitch_um for i in range(n)]
                out[key] = [((-sign if flip else sign) * args.slot_x_um, y)
                            for y in ys]
            return out

        def total_travel(cols):
            tot = 0.0
            for key in counts:
                grp = sorted((c for c in cargo if c["species"] == key),
                             key=lambda c: c["trap_um"][1])
                for c, s in zip(grp, sorted(cols[key], key=lambda s: s[1])):
                    tot += math.hypot(s[0] - c["trap_um"][0], s[1] - c["trap_um"][1])
            return tot

        cand = {flip: columns(flip) for flip in (False, True)}
        cost = {flip: total_travel(cand[flip]) for flip in cand}
        flip = min(cost, key=cost.get)
        slots = cand[flip]
        sides = {k: ("+x" if slots[k][0][0] > 0 else "-x") for k in slots}
        print(f"\nassignment: red -> {sides['red']}, green -> {sides['green']}   "
              f"total travel {cost[flip]:.1f} um "
              f"(the other polarity would be {cost[not flip]:.1f})", flush=True)
        report["assignment"] = {"red_side": sides["red"], "green_side": sides["green"],
                                "total_travel_um": cost[flip],
                                "alternative_um": cost[not flip]}
        used = {k: 0 for k in slots}
        for c in cargo:
            c["slot_um"] = slots[c["species"]][used[c["species"]]]
            used[c["species"]] += 1
            c["slot_px"] = trap_um_to_px(c["slot_um"], p0, um)
            c["travel_um"] = math.hypot(c["slot_um"][0] - c["trap_um"][0],
                                        c["slot_um"][1] - c["trap_um"][1])

        # Assign slots in y ORDER within each species. A monotone assignment
        # cannot produce a crossing inside a column: if bead A starts above
        # bead B and is also sent to a slot above B's, their paths do not swap
        # sides. Assigning by flux rank instead is what creates the crossings
        # that the transit check then has to reject.
        # Each slot picks its own cargo from the pool, preferring a CLEAR route
        # and then the shortest one. Slots are filled in y order and cargo is
        # constrained to keep the y ordering monotone, which is what prevents
        # two routes inside a column from crossing.
        cargo = []
        n_no_route = 0
        for key in ("red", "green"):
            col = sorted(slots[key], key=lambda s: s[1])
            avail = list(pool[key])
            taken = []
            for s in col:
                s_px = trap_um_to_px(s, p0, um)
                scored = []
                for d in avail:
                    if any(math.hypot(d["x"] - q["x"], d["y"] - q["y"]) < coll_px
                           for q in taken + cargo):
                        continue
                    # keep the assignment monotone in y within the column
                    if taken and d["trap_um"][1] < taken[-1]["trap_um"][1]:
                        continue
                    clear, worst = path_is_clear((d["x"], d["y"]), s_px, every,
                                                 args.path_clear_um / um)
                    trav = math.hypot(s[0] - d["trap_um"][0], s[1] - d["trap_um"][1])
                    scored.append((not clear, trav, worst, d))
                if not scored:
                    continue
                scored.sort(key=lambda r: (r[0], r[1]))
                blocked, trav, worst, d = scored[0]
                if blocked:
                    n_no_route += 1
                d = {**d, "slot_um": s, "slot_px": s_px, "travel_um": trav,
                     "path_clear": not blocked,
                     "path_worst_um": (worst * um) if worst is not None else None}
                taken.append(d)
                cargo.append(d)
                avail = [a for a in avail if a is not scored[0][3]]
        if n_no_route:
            print(f"  {n_no_route} slot(s) had no candidate with a clear route -- "
                  f"filled with the best available and flagged", flush=True)

        # ── transit collisions, pairwise, exact ─────────────────────────────
        # All traps advance together, so drop the LATER-ranked bead of any pair
        # that would come within collision_um of each other en route.
        dropped_transit = []
        keep = []
        for c in cargo:
            bad = None
            for q in keep:
                sep, when = min_separation_during_move(
                    c["trap_um"], c["slot_um"], q["trap_um"], q["slot_um"])
                if sep < args.collision_um:
                    bad = (q, sep, when)
                    break
            if bad is None:
                keep.append(c)
            else:
                q, sep, when = bad
                c["dropped_because"] = (
                    f"would pass {sep:.1f} um from {q['label']} at {when:.0%} of the "
                    f"move (needs {args.collision_um:g})")
                dropped_transit.append(c)
        cargo = keep

        print(f"\nplan -- {len(cargo)} beads, slots pitched {args.slot_pitch_um:g} um "
              f"at x = +-{args.slot_x_um:g} um:", flush=True)
        for i, c in enumerate(cargo, start=1):
            # c["path_clear"], not a bare `clear` -- that name leaks from the
            # assignment loop above and held its LAST iteration's value, so
            # every row got flagged from one unrelated bead's route.
            flag = "" if c["path_clear"] else "   <-- CORRIDOR BLOCKED, will skip"
            wtxt = f"{c['path_worst_um']:.1f}" if worst is not None else "inf"
            print(f"  {i}. {c['label']:18s} trap ({c['trap_um'][0]:+6.1f},"
                  f"{c['trap_um'][1]:+6.1f}) -> ({c['slot_um'][0]:+6.1f},"
                  f"{c['slot_um'][1]:+6.1f}) um   travel {c['travel_um']:5.1f} um   "
                  f"corridor clearance {wtxt} um{flag}", flush=True)
        report["plan"] = [{"label": c["label"], "species": c["species"],
                           "from_um": list(c["trap_um"]), "to_um": list(c["slot_um"]),
                           "travel_um": c["travel_um"],
                           "path_clear": c["path_clear"],
                           "path_worst_um": c["path_worst_um"]} for c in cargo]
        n_block = sum(1 for c in cargo if not c["path_clear"])
        if n_block:
            print(f"\n  {n_block} of {len(cargo)} corridors are blocked -- a live trap "
                  f"dragged along them would\n  pass within {args.path_clear_um:g} um of "
                  f"another object and could pick it up or knock it.\n  Most beads here "
                  f"are stuck to the glass, so obstacles do not move aside.",
                  flush=True)

        if not args.run:
            print("\n--plan: nothing sent.", flush=True)
            return 0

        # ── execute: N traps, moved in lockstep ─────────────────────────────
        from hardware.optical_tweezers import OpticalTweezers, find_gui_port

        port = args.port or find_gui_port(host=args.host)
        if port is None:
            print("No Tweez GUI answered.", file=sys.stderr)
            return 1
        batch = [c for c in cargo if c["path_clear"]]
        if not batch:
            print("\nevery corridor is blocked. Nothing to move.", flush=True)
            report["verdict"] = "all corridors blocked"
            return 1
        moved, lost = [], []
        with OpticalTweezers(host=args.host, port=port) as t:
            if not t.is_ready():
                print("Tweez GUI not ready.", file=sys.stderr)
                return 1
            if args.laser_on:
                t.laser_on()
                print("\nLASER_ON sent (class-4 1064 nm, on operator instruction)",
                      flush=True)

            names = [f"{args.trap}-{i}" for i in range(1, len(batch) + 1)]
            for c, nm in zip(batch, names):
                c["trap_name"] = nm
                # Traps accumulate and the GUI has a ceiling -- delete then
                # create, which is idempotent because TRAP_DELETE on an absent
                # name is harmless. Deleting a trap this script owns is not the
                # "TRAP_OFF to tidy up" SAFETY.md §1 forbids.
                try:
                    t.delete_trap(nm)
                except Exception:
                    pass
                try:
                    t.create_simple_trap(nm)
                except Exception as exc:
                    print(f"  ! SIMPLE_TRAP_CREATE {nm!r}: {exc}", file=sys.stderr)
                t.set_trap_strength(nm, args.strength)
                fx, fy = c["trap_um"]
                # POSITION before ON, per trap: turning on first sweeps a live
                # beam from wherever the trap was to the target.
                t.trap_off(nm)
                t.set_trap_position(nm, round(fx, 4), round(fy, 4))
                t.trap_on(nm)
                print(f"  grabbed {nm!r} {c['label']:18s} at ({fx:+6.1f},{fy:+6.1f}) um",
                      flush=True)
            print(f"\n{len(batch)} traps on, sharing one beam "
                  f"(~1/{len(batch)} of the power each)", flush=True)
            time.sleep(settle_grab)

            # ── lockstep transport ──────────────────────────────────────────
            # One normalised clock for every trap, so the pairwise separations
            # follow the quadratics the transit check already cleared. Steps
            # are sized by the LONGEST journey so no trap ever jumps more than
            # --step-um and leaves its bead outside the capture range.
            longest = max(c["travel_um"] for c in batch)
            n_steps = max(1, int(math.ceil(longest / args.step_um)))
            print(f"  transporting: {n_steps} steps of <= {args.step_um:g} um "
                  f"(longest journey {longest:.1f} um)", flush=True)
            for k in range(1, n_steps + 1):
                s = k / n_steps
                for c in batch:
                    fx, fy = c["trap_um"]
                    sx, sy = c["slot_um"]
                    t.set_trap_position(c["trap_name"],
                                        round(fx + (sx - fx) * s, 4),
                                        round(fy + (sy - fy) * s, 4))
                time.sleep(args.settle_s)
            time.sleep(settle_grab)

            # ── verify each arrival separately ──────────────────────────────
            print(f"\nverifying arrivals:", flush=True)
            for key, cam, line, _label, _sign in SPECIES:
                grp = [c for c in batch if c["species"] == key]
                if not grp:
                    continue
                light(args.cyan if line == "CYAN" else 0,
                      args.green if line == "GREEN" else 0)
                time.sleep(0.25)
                ds = detect(frames_of(cam, 8)[-1], area_px)
                if key == "green":
                    ds = [{**d, **dict(zip(("x", "y"),
                           blue_to_red((d["x"], d["y"]), (h, w))))} for d in ds]
                for c in grp:
                    sp = c["slot_px"]
                    start_px = trap_um_to_px(c["trap_um"], p0, um)
                    arrived = min((math.hypot(d["x"] - sp[0], d["y"] - sp[1])
                                   for d in ds), default=1e9) * um
                    left = min((math.hypot(d["x"] - start_px[0], d["y"] - start_px[1])
                                for d in ds), default=1e9) * um
                    ok = (arrived < max(1.5, 0.1 * c["travel_um"])
                          and left > max(2.0, 0.15 * c["travel_um"]))
                    tag = "MOVED" if ok else "NOT MOVED"
                    print(f"    {c['trap_name']!r} {c['label']:18s} -> "
                          f"({c['slot_um'][0]:+6.1f},{c['slot_um'][1]:+6.1f}) um   "
                          f"arrived {arrived:5.2f} um   start now clear by "
                          f"{left:5.1f} um   {tag}", flush=True)
                    rec = {"trap": c["trap_name"], "label": c["label"],
                           "species": c["species"], "to_um": list(c["slot_um"]),
                           "travel_um": c["travel_um"], "arrived_um": arrived,
                           "left_behind_um": left}
                    if ok:
                        moved.append(rec)
                    else:
                        lost.append(rec)

            # release the ones that made it, where they are
            for c in batch:
                if any(m["trap"] == c["trap_name"] for m in moved):
                    t.trap_off(c["trap_name"])
            print(f"\nreleased {len(moved)} beads at their slots with TRAP_OFF; "
                  f"{len(lost)} traps left on", flush=True)

        report["moved"], report["lost"] = moved, lost
        print(f"\n{'=' * 70}", flush=True)
        print(f"SORTED {len(moved)} of {len(batch)} transported "
              f"({len(cargo)} planned, {len(dropped_transit)} dropped on transit "
              f"collision)", flush=True)
        for m in moved:
            print(f"  {m['label']:18s} -> ({m['to_um'][0]:+6.1f},{m['to_um'][1]:+6.1f})"
                  f" um   travelled {m['travel_um']:5.1f} um, arrived within "
                  f"{m['arrived_um']:.2f} um", flush=True)
        if lost:
            print(f"\nnot moved -- dropped en route, or stuck and never picked up:",
                  flush=True)
            for m in lost:
                print(f"    {m['label']:18s} arrived {m['arrived_um']:.2f} um from the "
                      f"slot, start still occupied within {m['left_behind_um']:.1f} um",
                      flush=True)
    finally:
        light(0, 0)
        print("\nillumination OFF. Laser LEFT ON (SAFETY.md §1).", flush=True)

    if args.out:
        outdir = Path(args.out)
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "sort.json").write_text(json.dumps(report, indent=2, default=str),
                                          encoding="utf-8")
        print(f"report: {outdir / 'sort.json'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
