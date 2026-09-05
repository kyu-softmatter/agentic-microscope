"""Ensemble MSD and D from a grid of wall-diffusion fields.

    python config/session/analyse_wall_diffusion.py \
        --day "D:\\Kyu Hwan Choi\\agentic_microscope\\2026-09-04" \
        --runs wall-diffusion-004..012 --out msd_grid

Two things this does differently from the first pass on 2026-09-04, and both
were forced by what that pass got wrong.

THREE-PASS REFINE, NOT ONE
--------------------------
Localization is an intensity-weighted centroid in a window, and the window has
to be placed somewhere. Placing it on the *previous frame's* centre and taking
one pass makes the estimate lag: the centroid is pulled back toward where the
bead was, which is an explicit frame-to-frame anti-correlation and it
suppresses exactly the shortest lags.

Measured 2026-09-04 on run 003: starting from the previous frame's centre, the
first pass still moves the centroid a median of 0.403 px = 43.7 nm, and the
second moves it 0.000. The per-frame diffusive step is 57.5 nm -- so the
one-pass residual was 76% of the signal, and the symptom was unmistakable in
hindsight: apparent D *rose* with lag (0.0323 at lag 1 to 0.0362 at lag 16)
and the fitted intercept came out NEGATIVE, which is unphysical. Static
localization noise does the opposite; it inflates short lags. Iterating to
convergence removes the dependence on where the window started.

WHOLE-TRAJECTORY ISOLATION, NOT A CUT AT t=0
--------------------------------------------
The isolation cut is not a hydrodynamic nicety, it is set by the localization
geometry: a bead's disk is ~27 px in radius at the working threshold, so a
window big enough to hold it cannot exclude a neighbour closer than about
twice that. At nn = 45 px there is no window that works at all.

And nn is not constant. Two beads' separation random-walks with 2x the
single-bead diffusivity, so over a 30 s block pair separations move 3.5 um,
and over 180 s they move 8.5 um. A bead that starts at nn = 12 um can end a
30 s block at 8.5 um (still clear of the ~6 um hard limit) but ends a 180 s
block at 3.5 um (badly contaminated). So the cut has to hold for the whole
trajectory, which is why the bookkeeping below tracks *every* detection --
including ones that are never measured -- and takes the minimum of nn over
frames.

Cheap tracking for the bookkeeping, expensive tracking for the measurement:
one refine pass is ample for deciding whether a neighbour is 12 um away, and
would be ruinous for the MSD.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

PX_UM_DEFAULT = 0.10833
OFFSET_ADU = 102.0
T_EXP_MS = 33.33          # exposure == frame period in free-run
BLUR_S = T_EXP_MS / 3.0 / 1000.0   # Savin-Doyle x-axis offset
D_BULK = 0.0857           # Stokes-Einstein at 20.0 C, a = 2.5 um
A_UM = 2.5


def detect(img, thr_frac=0.30, mask_r=45, max_n=800):
    """Rough centres, brightest-pixel-then-mask. Integer-ish, refine after."""
    a = img.copy()
    bg = np.percentile(a, 20)
    thr = bg + thr_frac * (np.percentile(a, 99.9) - bg)
    H, W = a.shape
    yy, xx = np.mgrid[0:H, 0:W]
    out = []
    for _ in range(max_n):
        i = int(np.argmax(a))
        py, px = divmod(i, W)
        if a[py, px] < thr:
            break
        out.append((float(px), float(py)))
        a[(yy - py) ** 2 + (xx - px) ** 2 < mask_r ** 2] = bg
    return np.array(out, dtype=float).reshape(-1, 2)


def refine(img, cx, cy, win, npass, H, W):
    """Threshold-free centroid in a window, iterated to convergence.

    Threshold-free because a fixed absolute threshold on a fading disk crosses
    at a smaller apparent radius and walks the centroid -- a bias, not a
    variance. Subtracting the window's own 10th percentile makes the estimate
    invariant to an overall intensity scale, which is the property lens 5 asked
    for and the property the x0.8 acceptance test checks.
    """
    for _ in range(npass):
        x0, x1 = int(max(0, cx - win)), int(min(W, cx + win + 1))
        y0, y1 = int(max(0, cy - win)), int(min(H, cy + win + 1))
        w = img[y0:y1, x0:x1]
        w = np.clip(w - np.percentile(w, 10), 0, None)
        t = w.sum()
        if t <= 0:
            return cx, cy, 0.0
        nx = (w * np.arange(x0, x1)[None, :]).sum() / t
        ny = (w * np.arange(y0, y1)[:, None]).sum() / t
        if abs(nx - cx) < 0.01 and abs(ny - cy) < 0.01:
            cx, cy = nx, ny
            break
        cx, cy = nx, ny
    return cx, cy, float(t)


def track(stack, seed, npass, win=32, jump_px=8.0):
    """Follow every seed through every frame. Returns (frames, beads, 2) in px."""
    NF, H, W = stack.shape
    cur = seed.copy()
    out = np.full((NF, len(seed), 2), np.nan)
    for fi in range(NF):
        img = np.asarray(stack[fi], dtype=np.float32) - OFFSET_ADU
        for k in range(len(cur)):
            nx, ny, mass = refine(img, cur[k, 0], cur[k, 1], win, npass, H, W)
            if mass > 0 and abs(nx - cur[k, 0]) < jump_px and abs(ny - cur[k, 1]) < jump_px:
                cur[k] = (nx, ny)
            out[fi, k] = cur[k]
    return out


def track_once(stack, seed, cand, npass_book=1, npass_meas=3, win=32,
               jump_px=8.0):
    """One read of the stack, two trackers on it.

    The first version of this analysis read the whole stack twice: once at one
    refine pass over every detection, to work out which beads stay isolated,
    and again at three passes over the survivors, to measure them. On the
    2026-09-04 grid that was **two passes over 93 GB** -- about 8 minutes of
    I/O against 2.8 minutes of compute, i.e. the disk was the wall and half of
    the reading was avoidable.

    Merging is not simply "do three passes on everything". Measured: one pass
    over 274 beads costs 21 ms a frame and three passes cost 61 ms, so
    refining everything three times would push compute from 2.8 to 8.2 minutes
    and lose more than the 4 minutes of I/O it saves. What works is doing both
    jobs on the frame while it is in memory: cheap tracking for the whole
    population, expensive tracking only for the candidates.

    ``cand`` is chosen at frame 0 with a margin over the isolation cut. Pair
    separations random-walk at twice the single-bead diffusivity, so over a
    30 s block they move 3.5 um; a bead starting at nn >= cut + 3.5 um is
    guaranteed to clear the cut for the whole block. That is conservative -- it
    rejects beads that would in fact have stayed clear -- and it is the right
    direction, because it can never admit a contaminated one. The bookkeeping
    still runs over every frame, so the guarantee is **verified afterwards**
    rather than trusted.
    """
    NF, H, W = stack.shape
    cur_b = seed.copy()
    cur_m = seed[cand].copy()
    book = np.full((NF, len(seed), 2), np.nan)
    meas = np.full((NF, len(cand), 2), np.nan)
    for fi in range(NF):
        img = np.asarray(stack[fi], dtype=np.float32) - OFFSET_ADU
        for k in range(len(cur_b)):
            nx, ny, mass = refine(img, cur_b[k, 0], cur_b[k, 1], win,
                                  npass_book, H, W)
            if mass > 0 and abs(nx - cur_b[k, 0]) < jump_px \
                    and abs(ny - cur_b[k, 1]) < jump_px:
                cur_b[k] = (nx, ny)
            book[fi, k] = cur_b[k]
        for j in range(len(cur_m)):
            nx, ny, mass = refine(img, cur_m[j, 0], cur_m[j, 1], win,
                                  npass_meas, H, W)
            if mass > 0 and abs(nx - cur_m[j, 0]) < jump_px \
                    and abs(ny - cur_m[j, 1]) < jump_px:
                cur_m[j] = (nx, ny)
            meas[fi, j] = cur_m[j]
    return book, meas


def min_nn_um(all_tracks, sub_idx, px_um, stride=10):
    """Minimum over frames of each subject's nearest-neighbour distance, um.

    Measured against EVERY tracked object, not just the subjects: a neighbour
    that is never measured contaminates a centroid exactly as much as one that
    is. Strided in time because nn changes on the seconds timescale, not the
    frame timescale.
    """
    NF = all_tracks.shape[0]
    worst = np.full(len(sub_idx), np.inf)
    for fi in range(0, NF, stride):
        p = all_tracks[fi]
        q = p[sub_idx]
        d = np.linalg.norm(q[:, None, :] - p[None, :, :], axis=-1)
        for j, gi in enumerate(sub_idx):
            d[j, gi] = np.inf
        worst = np.minimum(worst, d.min(axis=1))
    return worst * px_um


def msd_axis(x, lags):
    return np.array([np.nanmean((x[k:] - x[:-k]) ** 2) for k in lags])


def fit_D(m, tau, sel):
    """MSD = 2 D (tau - t_exp/3) + 2 sigma^2. Returns (D, intercept)."""
    te = tau[sel] - BLUR_S
    A = np.vstack([2 * te, np.ones(te.size)]).T
    (D, c), *_ = np.linalg.lstsq(A, m[sel], rcond=None)
    return float(D), float(c)


def faxen_ratio(delta_um):
    x = A_UM / (A_UM + delta_um)
    return 1 - 9/16*x + 1/8*x**3 - 45/256*x**4 - 1/16*x**5


def invert_gap(ratio):
    lo, hi = 0.005, 5.0
    for _ in range(90):
        mid = (lo + hi) / 2
        if faxen_ratio(mid) < ratio:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def expand(spec):
    if ".." not in spec:
        return [s.strip() for s in spec.split(",") if s.strip()]
    a, b = spec.split("..")
    stem = a.rsplit("-", 1)[0]
    return [f"{stem}-{n:03d}" for n in range(int(a.rsplit("-", 1)[1]), int(b) + 1)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--day", required=True)
    ap.add_argument("--runs", required=True,
                    help="wall-diffusion-004..012, or a comma list")
    ap.add_argument("--out", default="msd_grid")
    ap.add_argument("--isolation-um", type=float, default=12.0)
    ap.add_argument("--refine-passes", type=int, default=3)
    ap.add_argument("--lag-lo", type=int, default=2)
    ap.add_argument("--lag-hi", type=int, default=15)
    ap.add_argument("--slope-tol", type=float, default=0.15,
                    help="reject a bead whose MSD log-slope is more than this "
                         "far from 1. Drift and sticking both push it toward 2, "
                         "and sticking biases D DOWN -- which looks like "
                         "stronger wall hindrance, i.e. like the answer")
    ap.add_argument("--pair-drift-um", type=float, default=0.0, metavar="UM",
                    help="margin added to the frame-0 cut when choosing which "
                         "beads to refine expensively. **Zero is correct and "
                         "the default.** The frame-0 cut is already a superset "
                         "of the verified whole-trajectory cut -- a bead whose "
                         "MINIMUM nn clears 12 um necessarily cleared it at "
                         "frame 0 -- so any margin only discards beads that "
                         "would have survived. A first version set this to "
                         "3.5 um (the 30 s pair drift) and cut the usable "
                         "population from 37 to about 12 per field, trading "
                         "statistics for I/O, which is the wrong trade. Raise "
                         "it only to deliberately measure a more isolated "
                         "sub-population")
    ap.add_argument("--px-um", type=float, default=None)
    args = ap.parse_args(argv)

    day = Path(args.day)
    runs = expand(args.runs)
    print(f"{len(runs)} runs, isolation cut {args.isolation_um:.1f} um over the "
          f"WHOLE trajectory, {args.refine_passes}-pass refine\n")

    fields = []
    for name in runs:
        npy = day / name / f"{name}.npy"
        if not npy.exists():
            print(f"{name}: no .npy, skipped")
            continue
        # The pixel size is a calibration, not a property of the run, so it
        # comes from --px-um or from the recorded table's value for 60x at
        # intermediate 1.0x. Worth knowing where it does NOT come from: the
        # `_settings.json` that timestamped_capture writes beside each stack
        # carries Frames/Width/Height/BitDepth/ROI/ExposureMs/AchievedFPS and
        # **no pixel size** -- it cannot, the capture module never sees one. So
        # a run folder on its own does not carry the number that scales D by
        # its square. run_wall_diffusion.py puts it in `_run.json`; the grid
        # script puts it in the grid summary one level up. Neither is read
        # here, deliberately: silently picking up a pixel size from whichever
        # sidecar happens to exist is how a calibration gets applied without
        # anyone choosing it.
        px_um = args.px_um if args.px_um is not None else PX_UM_DEFAULT
        stack = np.load(npy, mmap_mode="r")
        NF = stack.shape[0]
        dt = T_EXP_MS / 1000.0
        tsv = day / name / f"{name}_timestamps.csv"
        if tsv.exists():
            import csv
            t = []
            with open(tsv, newline="") as fh:
                for row in csv.DictReader(fh):
                    for k in row:
                        if "elapsed" in k.lower():
                            try: t.append(float(row[k]))
                            except (TypeError, ValueError): pass
                            break
            if len(t) > 1:
                dt = (t[-1] - t[0]) / (len(t) - 1) / 1000.0

        f0 = np.asarray(stack[0], dtype=np.float32) - OFFSET_ADU
        seed = detect(f0)
        print(f"{name}: {NF} frames, dt {dt*1e3:.4f} ms, {len(seed)} detections")
        if len(seed) < 3:
            print("   too few detections, skipped")
            continue

        # Candidates from frame 0, with the pair-drift margin that makes the
        # whole-trajectory cut provable rather than hoped for.
        H, W = stack.shape[1:]
        margin = args.pair_drift_um
        d0 = np.linalg.norm(seed[:, None] - seed[None, :], axis=-1)
        np.fill_diagonal(d0, np.inf)
        nn0 = d0.min(axis=1) * px_um
        interior0 = ((seed[:, 0] >= 32) & (seed[:, 0] <= W - 32)
                     & (seed[:, 1] >= 32) & (seed[:, 1] <= H - 32))
        # A superset of the verified cut: min-over-frames >= cut implies
        # frame-0 >= cut. So refining these three-pass wastes effort only on
        # beads that later dip below, which is cheap and harmless.
        cand = np.where(interior0 & (nn0 >= args.isolation_um + margin))[0]
        print(f"   interior {int(interior0.sum())}, candidates at frame 0 with "
              f"nn >= {args.isolation_um + margin:.1f} um: {len(cand)}")
        if len(cand) < 3:
            print("   too few candidates, skipped")
            continue

        # ONE read: cheap tracking for every detection, expensive only for the
        # candidates.
        book, meas = track_once(stack, seed, cand,
                                npass_book=1, npass_meas=args.refine_passes)

        # verify the guarantee instead of trusting it
        nn = min_nn_um(book, cand, px_um)
        ok = nn >= args.isolation_um
        if not ok.all():
            print(f"   {int((~ok).sum())} of {len(cand)} candidate(s) dipped below "
                  f"{args.isolation_um:.0f} um somewhere in the block -- dropped")
        keep = cand[ok]
        if len(keep) < 3:
            print("   too few survive the verified cut, skipped")
            continue
        tr = meas[:, ok] * px_um
        lags = np.unique(np.round(np.logspace(0, np.log10(NF // 4), 24)).astype(int))
        tau = lags * dt
        sel = (lags >= args.lag_lo) & (lags <= args.lag_hi)

        slopes, drop = [], []
        s2 = (lags >= args.lag_lo) & (lags <= min(60, NF // 4))
        for b in range(tr.shape[1]):
            m = msd_axis(tr[:, b, 0], lags) + msd_axis(tr[:, b, 1], lags)
            sl = np.polyfit(np.log(tau[s2]), np.log(m[s2]), 1)[0]
            slopes.append(sl)
            if abs(sl - 1.0) > args.slope_tol:
                drop.append(b)
        good = np.array([b for b in range(tr.shape[1]) if b not in drop])
        print(f"   log-slope median {np.median(slopes):.3f}; "
              f"rejected {len(drop)} of {tr.shape[1]} outside 1 +- {args.slope_tol}")
        if len(good) < 3:
            print("   too few beads survive the slope test, skipped")
            continue

        mx = msd_axis(tr[:, good, 0], lags)
        my = msd_axis(tr[:, good, 1], lags)
        Dx, cxi = fit_D(mx, tau, sel)
        Dy, cyi = fit_D(my, tau, sel)
        Dm = (Dx + Dy) / 2
        sig = np.sqrt(max((cxi + cyi) / 4, 0)) * 1e3
        print(f"   D_x {Dx:.5f}  D_y {Dy:.5f}  mean {Dm:.5f} um2/s   "
              f"x-y {abs(Dx-Dy)/Dm:.1%}")
        print(f"   intercept 2s^2: x {cxi:+.2e}  y {cyi:+.2e} um2"
              + (f"  -> sigma {sig:.1f} nm" if cxi > 0 and cyi > 0
                 else "   *** still negative ***"))
        fields.append({
            "name": name, "n_frames": NF, "dt_ms": dt * 1e3,
            "n_detected": int(len(seed)), "n_interior": int(interior0.sum()),
            "n_candidates": int(len(cand)), "n_isolated": int(len(keep)), "n_used": int(len(good)),
            "log_slope_median": float(np.median(slopes)),
            "D_x": Dx, "D_y": Dy, "D_mean": Dm,
            "intercept_x": cxi, "intercept_y": cyi,
            "tau_s": tau.tolist(), "msd_x": mx.tolist(), "msd_y": my.tolist(),
            "lag_lo": args.lag_lo, "lag_hi": args.lag_hi,
        })

    if not fields:
        print("\nno field yielded a fit.", file=sys.stderr)
        return 1

    Ds = np.array([f["D_mean"] for f in fields])
    n = len(Ds)
    mean, sd = Ds.mean(), Ds.std(ddof=1) if n > 1 else 0.0
    sem = sd / np.sqrt(n) if n > 1 else float("nan")
    print(f"\n{'=' * 66}")
    print(f"{n} fields:  D = {mean:.5f} +- {sem:.5f} um2/s  "
          f"(field-to-field SD {sd:.5f})")
    print(f"  D/D_bulk = {mean/D_BULK:.4f}  ->  inverted mean gap "
          f"{invert_gap(mean/D_BULK)*1e3:.0f} nm, h/a "
          f"{(A_UM + invert_gap(mean/D_BULK))/A_UM:.3f}")
    print(f"  the SEM carries {1/np.sqrt(2*(n-1)):.0%} uncertainty on itself "
          f"at {n} fields")
    print(f"  beads used: {sum(f['n_used'] for f in fields)} "
          f"of {sum(f['n_isolated'] for f in fields)} isolated, "
          f"{sum(f['n_detected'] for f in fields)} detected")

    out = day / f"{args.out}.json"
    out.write_text(json.dumps({
        "isolation_um": args.isolation_um,
        "refine_passes": args.refine_passes,
        "lag_window": [args.lag_lo, args.lag_hi],
        "slope_tol": args.slope_tol,
        "t_exp_ms": T_EXP_MS, "blur_offset_s": BLUR_S,
        "D_bulk": D_BULK,
        "D_mean": float(mean), "D_sd": float(sd), "D_sem": float(sem),
        "n_fields": n, "fields": fields,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
