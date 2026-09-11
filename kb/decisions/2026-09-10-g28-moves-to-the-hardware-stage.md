---
id: 2026-09-10-g28-moves-to-the-hardware-stage
question: "Should a planning gate assert that PFS held focus, when the property it reads reports the coverslip rather than the servo?"
date: 2026-09-10
status: current
corrects: [2026-08-19-lens-4-scope]
---

# 2026-09-10 · G28 moves to the hardware execution stage

**Decided by KH.** *"G28은 하드웨어 실행단계로 넘길거야. 지금은 관련된 사항을
전부 삭제."* The check, its two setup fields, its four CLI flags, its six tests
and every reference are gone from `stability/`. **`G28` is vacant and is not
reused.**

## Why, and it is not only a relocation

The obvious reason is shape: PFS lock is a **runtime state**, and a
planning-time gate can only assert what someone typed into it. `--pfs-on
--pfs-in-range` was a promise about an acquisition that had not happened.

The sharper reason is that **the gate was reading the wrong property.** It
gated on `PFS-FocusMaintenance` plus `PFS in Range` as though the pair meant
"the servo is holding". `hardware/focus.py::FocusAxis.pfs_state` records what
that second flag actually is:

> `PFS` is registered as an AutoFocus device, so `isContinuousFocusEnabled`
> answers this without guessing at a property name — **which matters, because
> the one PFS property this repo does name (`PFS in Range`) reports the
> *coverslip*, not the servo, and `In Range` is the normal reading for a
> focused sample.**

So `On + In Range` is not evidence that focus was held; it is evidence that the
servo was switched on and the coverslip was where PFS expects a coverslip. The
hardware stage asks `isContinuousFocusEnabled` and `isContinuousFocusLocked`
through the autofocus API, which is the servo, and it already has the guard
that matters — `require_pfs_quiet`, which refuses to sweep while PFS is
servoing, after 2026-09-07 lost a session to exactly that.

**The check moved to where the right property is read.** That is a better
outcome than keeping a gate that was confidently checking something adjacent.

## What this costs

**`docs/06 D7` no longer has a gate behind it.** That entry records real
archive sessions with `PFS-FocusMaintenance: On` and `PFS in Range: Out of
Range`, and G28's stated purpose was to catch them. Nothing in the committee
catches them now; the entry is marked to say so and to point here. Note the
irony worth keeping: D7's own observation is what makes the gate's reading
suspect — if `In Range` reports the coverslip, then `On` + `Out of Range` means
the *coverslip* was out of range, which is a real problem but a different one
from "the servo was not holding".

**Lens 8 is down to three gates that can pass and one that cannot.** G29 has
never run — no drift rate exists anywhere in `kb/calibrations/` — and G28 was
the one gate in this lens that needed no new measurement. So removing it leaves
a lens whose only currently-computable verdicts are G30/G31/G32, and the
Phase-0 short-circuit means even those do not report while G29 is blocked. That
short-circuit is the next item on lens 8's list and it is now the whole lens's
problem rather than one gate's.

Gate count 27 → 26, implemented 24 → 23.

## Falsifying condition

An acquisition where focus was not held, the hardware stage did not notice, and
nothing else did either. The hardware stage reads the servo rather than the
coverslip, so it is better placed than the gate was — but it runs at
acquisition time, which means a **plan** can no longer be refused for not
having said anything about focus maintenance. If a run is lost to unheld focus
after this, the answer is a check in the hardware sequence, not a restored
planning gate.
