---
id: microrheology-standard-conditions
question: "What conditions does a microrheology run on this instrument default to, and which of them are choices rather than constants"
source: expert-judgment
expert: KH
date: 2026-09-07
confidence: high
scope: "optical-trap microrheology, 5 um PS probe, water and viscoelastic media, Aresis Tweez 300 + Nikon Ti2 + Kinetix"
applies_to_systems: [current]
review_after: 2027-09-07
supersedes: null
---

## Judgment

A microrheology run here is specified by a set of conditions that the user
supplies from habit rather than from calculation. They were reconstructed on
2026-09-07 from the analysis pipeline (`analysis/matlab/`) and from the session
that day. Writing them down is the point: an agent that has to ask for all of
them every time is not carrying the expertise.

| Condition | Standing value | Standing? |
|---|---|---|
| Probe | 5 µm carboxylate PS, red (`abvigen-red-5um-cooh`) | usual, not fixed |
| Objective | **100x Oil** (`6-Plan Apo LmbdD0.13 100x Oil`) | strong preference — "I want higher magnification for these" |
| Binning | **1×1**, 0.065 µm/px | deliberate — "need high resolution on particle to track it better" |
| Frame rate | **20.0 ms exposure ⇒ ~50 fps** | matches the hardcoded `frame_time = 0.02` in every analysis script |
| Excitation | Aura **GREEN**, ~80/1000, widefield epi (no DMD, disk bypassed) | |
| Camera | Kinetix_red, 16-bit `Dynamic Range` port | |
| ROI | frame 2–3× the particle, *not* the full chip, for the measurement | "just want to watch a single particle" |
| Temperature | **20 °C lab setpoint** (`kT = 4.045e-3` pN·µm) | sourced for the ROOM (KH, 2026-09-11); the **sample** is still unmeasured — see below |
| Medium | water for calibration; viscoelastic (λ-DNA, glycerol-water) for the science | |

## Why

**The objective and binning are a considered trade, not defaults.** 100x Oil in
water clips to effective NA 1.333 and caps usable depth near 10 µm
([`oil-objective-trapping-in-water.md`](oil-objective-trapping-in-water.md)), so
at the ~8 µm working depth a run actually uses, Faxén wall drag inflates the
drag by ~17.6 % and suppresses an inferred D by the same bound. The user chose
it anyway on 2026-09-07 with that bound stated. **Report the bias; do not
silently correct it and do not re-litigate the objective.**

Unbinned follows from what the measurement is: single-particle localisation,
where a Mortensen-style variance argument favours 65 nm pixels over 130 nm ones
once background is scaled per pixel area. It is *not* the SNR-optimal choice and
should not be "corrected" to 2×2 on SNR grounds.

**20 ms is not a free parameter.** Every script in `analysis/matlab/` hardcodes
`frame_time`. The camera here ignores a requested interval and takes the
exposure as the period, so exposure *is* the frame rate, and 20.0 ms is the only
value that lands on the assumption the analysis already makes.

**Temperature: the room is sourced, the sample is not.** The 20 °C is **the
lab's air-conditioning setpoint**, which KH keeps there (2026-09-11). That
retires half of what this entry used to call "the standing hole" — 293 K is no
longer an unsourced assumption, and asking for the room temperature every
session was asking for a constant.

What remains is the half that matters more, and it is **not** a missing
measurement so much as a named residual: the physics wants the sample
temperature **at the focus**, and with a 1064 nm trap on and an oil objective in
contact with the coverslip that is not the room's. `dD/D = 2.74 %/K`, so a few
K between room and focus is a few percent on any D, viscosity or κ inferred
through `kT` or `η` — and the direction is known, since the trap only heats.

**That gap is trap heating, which is ungated by decision** (`CLAUDE.md` E3,
`docs/06` D6, `kb/decisions/2026-08-19-lens-7-scope.md`). So it is reported,
not gated: `trapping.temperature_basis` says so as INFO on every run, and
`temperature_measured` stays `False` on the setpoint alone (KH, 2026-09-11:
*"인포에서 주의를 주는정도면 충분할 듯"*). Setting it `True` is a claim about a
measurement **of the sample**, not of the room.

Two things this does not fix. The acquisition scripts and `kT_um` in the MATLAB
still hardcode 293 K, which is now right for the room and still silent about the
focus. And `StabilitySetup` has no temperature field at all, so lens 8 cannot
see it.

## The three trap stiffnesses, and which are already implemented

The 2026-09-07 design was to obtain κ three independent ways from overlapping
data and compare them. Two already exist in the pipeline:

1. **Equipartition** — `kappa = kT/var(x)` on a held bead.
   `estimate_kappa_from_component(..., 'none', 0)`. Also the MSD-plateau form
   `kappa = 2kT/MSD_inf` in the 2-particle script.
2. **Full passive PSD shape** — `k_fit` from the Oldroyd-B `lsqnonlin` in
   `fit_comprehensive_microrheology_v4.m`, fitted jointly with the medium.
3. **Stokes drag** — `kappa = gamma·v/x_eq` from the mean displacement under a
   known stage velocity. **Not implemented anywhere.** The `creepx` pipeline
   detrends that mean away to isolate fluctuations, so the drag information is
   discarded by design. This is the piece to write.

(1) and (2) are both biased by the same two things in opposite directions —
localisation noise inflates the variance, motion blur deflates it — which is
why (3) being independent is worth the work.

## Falsifier

Somebody measures the sample temperature near the focus and it differs from
20 °C by more than ~2 K. That would confirm this entry's scope limit — room ≠
sample — and at the same time put every stored κ and D out by that much: the fix
is **not a re-run but a rescale**. At 24 °C the error is ~11 %.

⚠ Note which way the falsifier cuts. It does not threaten the 20 °C, which is
the setpoint and is sourced; it threatens the *silent equation of the setpoint
with the sample*, which is what every script and every `kT_um` currently does.
A measurement that came back at 20.0 °C would be the more surprising result,
because the trap only heats.

Equally: if the achieved frame period is ever measured and found *not* to equal
the exposure setting, the `frame_time` reasoning above collapses and every
frequency axis needs re-deriving from timestamps instead.
