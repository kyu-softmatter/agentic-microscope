---
# frontmatter added 2026-09-09 for kb/INDEX.md. `question` restates this
# file's own title and Request/Context; the link fields read its own
# supersession notes. A retrieval aid, not evidence -- see knowledge/index.py.
id: sessions-index
question: "What happened on each working day, and where does each running thread stand?"
date: 2026-09-07
living: true
status: index
---

# Session log — daily learnings and project progress

One file per working day, `YYYY-MM-DD.md`. This index is the thing to read
first: the table says what happened, the **projects** section says where each
running thread actually stands.

Started 2026-09-07 at the user's request. Earlier work is recorded in
`kb/decisions/` (dated decision records) and `kb/systems/current.md` (measured
instrument state) — those conventions continue; this adds the narrative layer
they do not have.

---

## How to write one

A session log is a lab notebook entry, not a changelog. It answers:

1. **What was the intent**, in one line.
2. **What actually happened** — including, especially, failures. A session that
   established a thing does not work is worth more than one that ran a script.
3. **What was learned that no code records** — the operational grit, the
   "this reads like a serial fault and is not one" facts.
4. **What state the instrument was left in.** The next person's first question.
5. **What to do next, in order.**

Two rules that keep these useful:

- **Numbers, not adjectives.** "RMS excursion 183 nm, ramp left the bead 1.03 µm
  from the start" — not "the catch seemed weak".
- **A failed session gets a *longer* entry, not a shorter one.** The reasoning
  that turned out wrong is the expensive part to reconstruct.

Do not duplicate what the repo already records. If a session produced a
measured constant it belongs in `data/` or `kb/calibrations/`; if it produced a
design choice it belongs in `kb/decisions/`; if it produced durable
expert judgment it belongs in `kb/expertise/`. Link to those from here.

---

## Sessions

| Date | Headline | Outcome |
|---|---|---|
| [2026-09-07](2026-09-07.md) | Microrheology attempt on a 5 µm bead, 100x Oil, 1×1 | **Abandoned, no data.** Beads stuck to the coverslip (2/2 failed the ramp test). Light path fixed; MATLAB pipeline captured; real-time GUI scoped; no valid 1×1 trap calibration yet. |

---

## Projects in flight

### Microrheology in water — trap stiffness three ways
**Status: blocked on a catchable bead.**
Design is settled: κ from (1) equipartition, (2) full passive-PSD Oldroyd-B fit,
(3) Stokes drag at known stage velocity — (1) and (2) share their biases, (3) is
the independent check.
- (1) and (2) **already implemented** in `analysis/matlab/`.
- (3) **not implemented anywhere** — the flow pipeline detrends away exactly the
  mean displacement it needs. This is the code to write.
- Blockers, in order: a bead that is not stuck → a 1×1 px→trap-µm calibration
  that passes its own checks → a measured sample temperature.
- Conditions: [`kb/expertise/microrheology-standard-conditions.md`](../expertise/microrheology-standard-conditions.md)

### Real-time particle-tracking GUI
**Status: scoped, not built.** → [`kb/decisions/2026-09-07-realtime-tracking-gui-scope.md`](../decisions/2026-09-07-realtime-tracking-gui-scope.md)
Show live: brightness, Brownian statistics, diffusivity.
- Display half largely exists: `config/micromanager/live_view.py`, including the
  `--publish`/`--attach` shared-memory path that lets a viewer watch without a
  second camera claim.
- **The architectural constraint:** statistics cannot be computed from the
  display stream. It drops frames by design, and MSD lag is indexed by row
  offset, so a dropped frame relabels every subsequent lag. Stats belong in the
  acquiring process, which sees every frame with its timestamp.
- Motivating evidence: on 2026-09-07 a live MSD panel would have identified two
  stuck beads in seconds instead of two full catch cycles.

### Bead sticking to the coverslip
**Status: the dominant practical obstacle for `abvigen-red-5um-cooh`; no fix yet.**
2026-09-06 (21 beads, most stuck) and 2026-09-07 (2/2 stuck) agree. The
excursion statistic cannot distinguish stuck from held — only moving the trap
can. No passivation or sample-prep change has been tried in this record.
