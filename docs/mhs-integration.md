# MHS — a note, not a plan

> Anthropic previewed the **Model Hardware Standard** on 2026-08-27, after this
> project's hardware layer was written. It is kept out of the README on purpose.
> The scientific-validity layer here is the part that should stay useful
> whichever hardware abstraction wins, and rewriting the project's identity
> around a standard announced two days ago would be positioning rather than
> engineering. Independent convergence is the more interesting observation, and
> recording it here is enough. If an integration actually happens, this file is
> where it gets designed.

**What this file is for, stated plainly.** Not a case for adopting MHS and not a
claim to have solved what it addresses. It is a description of **one bench,
written against the standard's own stated problems**, on the assumption that a
specification is tested better by a hard instrument than by a cooperative one.
Where this bench answers a problem, the answer carries a file, a date or a
measurement. Where it does not, that is said. Two of the most useful entries
below are a failure and an absence: a test this repository built and then
falsified ([§2.4](#24-verification-may-have-to-be-an-action-not-an-observation)),
and a device that was on the bench for two months while nothing in the
repository knew it existed ([§1.5](#15-the-tier-no-enumeration-reaches)).

## What MHS is, and where it would touch this

**[Model Hardware Standard](https://www.anthropic.com/news/model-hardware-standard-research-preview),
research preview, announced 2026-08-27.** A shared specification for agents to
operate physical devices: `read` / `write` primitives, **devices discoverable
in a standard format** so that agents and instruments find each other *"without
needing a bespoke 'translator' program"*, **device-level safety limits enforced
in the driver**, model-agnostic and reachable over MCP.

It lands on three things here at once. This repository *is* three bespoke
translators — pymmcore-plus, a 28-command TCP surface, a vendor DLL — plus
[`hardware/orchestrator.py`](../hardware/orchestrator.py) gluing them onto one
clock, which is item 1. Standard-format discovery would put a self-describing
device on **rung 1** of the discovery ladder and retire the
`strings`-over-a-DLL rung for anything that adopts it
([scope](../kb/decisions/2026-08-29-device-discovery-scope.md)). And safety
limits declared *in the driver* are item 3's reviewer expressed one layer
down — complementary rather than redundant: MHS would enforce *this axis
cannot exceed this travel*, while the reviewer still decides *this script
should not be run at all*.

---

## 0 · Where the seam falls

Three layers, and naming them is most of the analysis. The README's
architecture diagram marks the middle one directly above
[`hardware/`](../hardware/).

```text
   MCP            how an agent reaches tools and context at all.
                  Present here: mcp_server/, 9 tools in 4 tiers.

   ---------------------------------------------------------------
   MHS            how one device is described, read and written,
                  with its physical limits enforced in the driver.
                  ABSENT here. This is the layer with no incumbent.
   ---------------------------------------------------------------

   hardware/      three hand-written translators + one clock.
                  What occupies the MHS layer today, per vendor.

   24 gates       whether the setting is a good idea at all.
                  Above any transport, unaffected either way.
```

**The unusual thing about this bench is not the bottom layer, it is that the
top and bottom are both already built and the middle is the gap.** Most of what
a hardware standard has to argue for — that an agent should reach instruments,
that device knowledge should be machine-readable, that safety belongs in the
driver — is already assumed here and implemented per-vendor. So this repository
cannot say much about whether the layer is worth having. It can say, in detail,
**what the layer would have to survive**, which is the rest of this file.

One consequence worth stating because it cuts against adopting MHS eagerly:
**the 24 gates are indifferent to it.** They consume physical quantities —
irradiance at the sample, effective pixel size, τ_c, κ — and no transport
produces those. A standard that made every device on this bench reachable
tomorrow would not move a single gate from `BLOCKED` to `PASS`, because what
blocks them is measurements nobody has taken. That is not an argument against
the standard; it is the boundary of what it can be credited with.

---

## 1 · The device problems

The reachability table in the [README](../README.md#agentic-microscope) is the
data for this section and is not repeated. Headline: **28 devices, 6
Micro-Manager adapters, 8 manufacturers — and 8 tiers of how far code can
actually get.** Of the seven non-baseline tiers, **three would collapse into
the first** if the relevant vendor adopted a standard (a readable vendor DLL, a
turret that named its own positions, a version-locked package). **Four would
not.** Those four are §§1.1–1.5.

### 1.1 A success byte that means nothing

*Standard's problem: "장비 상태와 데이터가 서로 다른 프로그램에 갇혀 있어 실시간
공유가 어렵다" — device state and data locked in separate programs.*

The sharper form here is not that the state is locked in another program. It is
that **for one subsystem the state does not exist to be shared.** The Aresis
Tweez 300 answers over TCP with a return code and has **no readback of any
kind**: six distinct wrong states and a success are the same byte
([`SAFETY.md`](../SAFETY.md) §0).

Measured, 2026-09-04: `SIMPLE_TRAP_CREATE`, `TRAP_POSITION` and `TRAP_ON`
**all returned `0` with the laser unarmed**, while the GUI showed the trap's
`Active` = false and nothing was trapped. Six commands that would report or set
that state answer `-11, unknown command`.

And a second instance that cost more, because it was believed for weeks:
`TRAP_PATT_RELEASE_BP` returns `0` unconditionally, because
`Breakpoints > Enable Bits` is `0000` and is **GUI-only**. Every
release-round-trip latency figure measured before 2026-09-03 is precision on a
command with no effect.

**Why this is a constraint on the standard rather than a complaint about a
vendor.** A device-state abstraction — any shared dictionary, any `read`
primitive — has to have a defined answer for *a device that cannot be read*.
Three candidate answers and their costs, from this bench:

- **Omit the device.** Then the trap is invisible to exactly the agent that is
  steering a class-4 laser with it.
- **Report the commanded value.** This is what the host clock already does here,
  and [`orchestrator.py`](../hardware/orchestrator.py) says in its own docstring
  why it is not enough. A commanded position reported as state is a value that
  is *confidently wrong* precisely when a command silently failed — the failure
  mode above.
- **Report `unknown` and make callers handle it.** Correct, and it means every
  consumer needs a third branch. This repository took this route
  (`current_position: null` on the `Splitter`, `evidence: stated` vs `measured`,
  `advances: NO`) and it is more invasive than it sounds: the tri-state has to
  reach the gates, not stop at the driver.

The third is the only honest one, and a standard that makes it *easy* rather
than merely *possible* would be doing real work. Note that this is the same
distinction the MCP surface here already had to make for a different reason:
`refused: true` is a **value, not an exception**, because a tool that raises
reads to a calling model as broken, and a model that believes a tool is broken
routes around it. Unreadable state has the same shape.

### 1.2 A protocol the manufacturer does not document

*Standard's problem: "오래된 장비는 COM·ActiveX, 감시 폴더, GUI처럼 현대적이지
않은 인터페이스만 제공하기도 한다" — legacy interfaces only.*

This bench has all of that: GUI-only (tweezers, and three properties that are
GUI-only even there), a vendor DLL (piezo), an MM adapter locked to interface
**v71** against a v75 core (Mightex Polygon1000 DMD, which is what blocks FRAP).

But the case a standard cannot reach is the confocal laser. The **Nikon
LUN-F-XL** is the only laser on this instrument and was reachable only through
NIS-Elements. It is now driven from Python over an FTDI FT4222 SPI link with NIS
not running — wavelength selection and on/off per line, blanking polarity
**measured** as active-HIGH where Nikon documents nothing, and the DAC confirmed
**writable** (a 32-frame probe extinguished 561 while 640 kept emitting, so
writes are channel-selective; nine candidate framings alternating full-scale
against zero made 561 flicker, so arbitrary levels write)
→ [`2026-09-02`](../kb/decisions/2026-09-02-lunf-first-light-measured-limits.md).

**And it is still not commandable.** The DAC word format is one of nine
candidate framings, so levels write but you cannot ask for 50 %.
[`hardware/lunf_power.py`](../hardware/lunf_power.py) is complete as transport
and **refuses to transmit** without `PROTOCOL` set, which is the right default
for a byte going into a laser driver.

Two things closed negatively, and they are worth as much: the AO route is dead
(the PCIe-6323's four AO channels against the LUN-F's four lines was suggestive
and wrong — tested per channel and at rate, no flicker), and **nothing about the
LUN-F can be read back at all**, which puts it with the tweezers rather than the
piezo.

**A standard makes an integration cheap. It does not document an undocumented
protocol.** No specification recovers a DAC word format that the manufacturer
has not published, and this is the single largest hardware blocker on the bench:
until it is named, per-line laser power is not a quantity this repository can
command, which means the illumination half of every confocal channel stays
`assumed`.

### 1.3 A unified interface is not a unified clock

*Standard's problem, second half: 실시간 공유 — real-time sharing.*

This is the finding least likely to be anticipated by an interface
specification, because it survives the interface being fixed. **The three
subsystems here do run on one timeline** — done 2026-09-03,
[`run_trap_stage_sine.py`](../config/session/run_trap_stage_sine.py) put both
zeros on the camera's clock with per-frame timestamps through
[`timestamped_capture.py`](../calibration/timestamped_capture.py). The
microscope is always on the roster because its per-frame `ElapsedTime-ms` is the
series everything else is aligned onto.

**And the trap still has no timestamp of its own.** All three candidate routes
are unbuilt, and each fails differently:

| Route | Why it is not free |
|---|---|
| The probe's own `.Data` series (`TimOrg, PrbOrgX, TrpOrgX…`) | samples accumulate only while the Tweez GUI is tracking, so it does not escape the camera-ownership conflict; and it means reaching an undocumented embedded node tree — 0 of 51 paths readable at GUI startup |
| The hardware trigger | gives a *computed* position from a hardware-clocked pattern, not a read one — and `TRAP_PATT_RELEASE_BP` answers `0` whether the trap waited at the breakpoint or the pattern had already finished, so nothing on this route confirms a pass happened (§1.1) |
| An out-of-band sensor on the trap beam, on the camera's NIDAQ clock | the only route yielding an **independent** time base. Nothing like it exists here |

None can be replaced by timing the drive from the host.
[`orchestrator.py`](../hardware/orchestrator.py) states it in its own docstring:
**the host clock is not the experiment clock**, and mapping host stamps onto
MM's series afterwards is a correlation, not a synchronisation.

Underneath it is an exclusion a standard does not dissolve: **while the Tweez
GUI owns the camera there is trap-position readback and no imaging from
pymmcore-plus, and while Micro-Manager owns it, the reverse.** Active
microrheology needs bead *and* trap position at the same instant, and only one
owner can see both. A 2026-09-04 session did run with MM owning `Kinetix_red`
while TCP drove the trap, so the conflict is now *demonstrated rather than
argued* — but the case it was raised for is untouched, because the trap position
on that route is commanded rather than read.

**So: two devices reachable through one specification would still not be
simultaneous.** Shared memory gives a shared address space, not a shared time
base. If the standard has an opinion about time — a device-supplied timestamp on
every `read`, monotonic and comparable across devices — that would be a larger
contribution to this bench than uniform access, and it is not obviously in
scope.

### 1.4 Adding hardware, and what the cost actually is

*Standard's problem: "장비를 추가할 때마다 일회성 연결 코드와 전문 인력이
필요하다" — one-off glue and a specialist per device.*

There are additions planned for this bench, including hand-built apparatus (a
rotating stage), which is the case a standard serves least well: **nothing
hand-built has a vendor to adopt a specification.** For those, the interface is
whatever the builder wrote, and the useful target is not standard discovery but
the discovery *ladder* — get the device onto rung 1 (what it says about itself),
then produce a **stub, not an answer**
([scope](../kb/decisions/2026-08-29-device-discovery-scope.md)).

Where this repository agrees with the problem statement is narrower and, from
the evidence here, more important than the glue: **the recurring cost is not
writing the driver, it is that the device's facts do not stay in one place.**
Measured instances, all from the last three days:

- A pixel-size value that Micro-Manager answered as `0.0` — not an error, a
  plausible-looking zero — in 3 of 6 configs, including the parent of the other
  four.
- One physical branch mirror whose two label strings were **swapped** in the
  `.cfg`, which made a correct record look falsified for two days and would have
  flipped every name-based preset to the blocking state the moment the labels
  were fixed.
- One trap half-extent, operator-verified for the 100× objective, hardcoded as a
  bare literal in **four** session scripts and applied whatever objective was in
  place.

Each is a *bespoke translator problem* only in the loosest sense. What each
actually is: a physical fact with more than one home and no single reader. This
repository's answer is the mirror pattern — `kb/systems/current.md` is the
dossier, `data/*.yaml` is the machine-readable copy, one reader function per
quantity, and it **returns `None` rather than a default** when the fact is
unrecorded (`optics.components.trapping_range_um`,
`optics.components.recorded_pixel_um`). A device standard would supply that for
values the *device* knows. It supplies nothing for the ones it does not — which
on this bench includes the coverslip thickness, the polarizer angle, the
condenser position's meaning, and the sample's own extent.

### 1.5 The tier no enumeration reaches

*Standard's problem: "AI 에이전트가 장비를 제어할 공통 방식과 물리적 안전 정보를
전달받을 방법이 부족하다" — no common way to receive physical safety
information.*

On 2026-09-06 the operator listed the bench's hardware and it included a
**temperature-controlled stage**. Before that sentence this repository contained
**zero mentions** of one, in any file. `stability/` — lens 8, which owns the
mechanical and environmental axis — still has no temperature input of any kind.

It was not missed by a bad scan. It is in no `.cfg`, loads no adapter, and no
script has ever addressed it, so **nothing enumerable would have surfaced it**,
including a standard-format discovery scan. Only the operator saying so did.

**And it controls the quantity that dominates the only real measurement here.**
The 2026-09-04 wall-diffusion result (`D‖ = 0.03951 ± 0.00039 µm²/s`, 9 fields,
SEM 1.1 %) is explicitly *not* a measurement of the wall effect, and the first
of the three reasons is *sample temperature at the coverslip — 3–8 %, one-sided,
unmeasured.* The companion simulation project independently calls `T = 300 K`
its most damaging soft spot, worth −4 % to −14 % on every timescale it computes
because water's viscosity is 2.06 %/K sensitive, and concludes: **"a thermometer
reading ends that."** A stage that *controls* the quantity was on the bench for
the whole period in which that error budget was written around not having one.

The stub is now in
[`kb/systems/current.md`](../kb/systems/current.md) with everything but
existence `null`, and the second `TODO(human)` is the one that matters: *was it
powered, and at what setpoint, during the 2026-09-04 grid?* That answer decides
whether the 3–8 % can be narrowed retrospectively or is permanently lost.

**The generalisation, and it is the strongest single thing this bench has to say
to a hardware standard: physical safety and physical context arrive by human
statement, and the transport layer is not where they enter.** The evidence is
not one anecdote. Six records were falsified in a single 2026-09-04 session and
**five of the six were corrected by the operator supplying a fact the repository
had wrong or did not hold** — the Lapp branch, the Z retract direction, the
`IntermediateMagnification` device class, the `Splitter`'s readability, the Faxén
term's claimed boundedness. A seventh was the temperature stage. One of them was
a *correction that was itself wrong* — the mirror labels — which is the case that
should worry a specification most, because two independent measurements agreed
with each other while both were read through the same mislabelled enum.

This repository's answer is [`docs/09`](09-knowledge-capture.md), capturing
judgment out of conversation into a durable note with a **falsifier** attached,
and it is called the real purpose of the project for this reason rather than as
a flourish.

---

## 2 · The sample problems

Sections 1.1–1.5 are about devices. The standard's last two problems are not,
and answering them with a device inventory would miss them.

### 2.1 Why "experiments vary" is the wrong answer

*Standard's problem: "실험은 상황에 따라 바뀌기 때문에 고정된 공장 자동화 방식으로
처리하기 어렵다" — experiments change with circumstances, so fixed
factory-automation approaches do not fit.*

Every lab can claim varied experiments, which makes the claim unfalsifiable and
therefore not evidence. The specific and checkable version, for this bench:
**the specimen changes on the timescale of the control loop, and the measurement
tool is itself a perturbation.** That is a physical reason a fixed pipeline is
wrong rather than an inconvenience, and it is the case in which agentic control
is not a convenience either.

### 2.2 The instrument is the perturbation

For a light-responsive sample — light-driven active colloids, photo-crosslinking,
liquid-crystal photo-alignment, FRAP — *"raise the light for SNR"* is correct in
purely optical terms and changes the thing being measured. Lens 1 and lens 2 say
raise it; lens 5 is the only lens that can answer *that ruins the experiment*.
`01 §4` files this as a cross-lens constraint, and it is not a tradeoff to
balance: when the illumination is an experimental variable, SNR and dose are not
two costs on one axis.

The mechanism is [`photo/checks.py`](../photo/checks.py) G21,
`check_light_driving`, and the part worth reading is that **it has three answers
rather than two**:

- `photoresponsive is None` → **warns and does not pass.** The code states the
  reason: *"a default of 'no' would make the gate silent in exactly the case
  docs/06 D2 is about."* The recorded finding says the same:
  *"Nobody has said whether this sample responds to light, so 6.2 W/cm² is
  unevaluated, not cleared. … The margin below is not a judgement — there is
  nothing yet to judge."* The margin prints `10.00` and the verdict still
  refuses to advance, because it is computed against a threshold nobody supplied.
- `False` → clears the check.
- `True` with no measured `light_driving_threshold_w_cm2` → **`BLOCKED`**, not
  compared against a guess.

*Unevaluated* and *cleared* being different states is the whole design, and this
sample class is why the distinction had to exist.

### 2.3 The sample's own timescale sets the settings, and it moves

τ_c drives the frame rate (G9), the motion-blur ceiling (G8) and the target
precision (G11). For an active sample τ_c is a function of activity, which is a
function of illumination, fuel and crowding — so it can change **during** the
run. This is the physical argument for real-time analysis (roadmap item 5): not
efficiency, but that the correct settings are a function of a state that moves.

And the bias it interacts with is already written down: a measured MSD carries
`−2D·t_exp/3` from blur and `+2ε²` from static localization error, which at
short lags **cancel into a plausible straight line with the wrong slope**
([04 §5](04-decision-engine.md)). A fixed pipeline that chose its exposure once,
against a τ_c that has since moved, produces exactly that line — and the line
looks like data.

### 2.4 Verification may have to be an action, not an observation

The most useful result this bench has for an agentic-hardware specification is a
**negative** one, and it was this repository's own test that failed.

To decide whether a bead was held, the live loop scored its RMS excursion over
1.5 s. Measured 2026-09-04: **wrong in five cycles out of five** — four held
beads called free, one unheld bead called held. The cause is physical and no
threshold fixes it: *a bead stuck to the coverslip sits as still as a trapped
one*, and *a bead just trapped is still travelling into the well*. The statistic
does not separate the populations.

What separates them is **moving the trap and seeing whether the bead comes**:
98.6–99.8 % follow against 2.9 %, nothing in between.

Read as a constraint on the standard: **on a device with no readback,
verification is an action, and an action is a `write`.** A `read`/`write` split
in which verification lives on the `read` side cannot express this. The safety
consequence is the uncomfortable half — the only way to confirm the trap is
holding is to *move a class-4 laser*, so "verify before you act" and "do not act
until verified" are not simultaneously satisfiable here. Any approval model has
to have an answer for that, and this repository's answer is currently a human
keypress.

### 2.5 The gap on this side, stated

`photoresponsive` is a **command-line flag** (`--not-photoresponsive`). It is
not a field in [`data/particles.yaml`](../data/particles.yaml), which is 725
lines and has no slot for it or for `light_driving_threshold_w_cm2`; the
particle-sheet to-do in the README does not list them either. So **the lens
built for active samples exists, and the particle registry has nowhere to record
the answer it consumes** — every run re-asserts it, or leaves it unanswered and
takes the warning.

Every registered particle today is passive polystyrene. The machinery is ready
for the sample class and the records are not.

---

## 3 · Safety, against the standard's own six points

Mostly this section reports that the mechanism exists, with the file. Where the
mechanism exists and is *unenforced*, that is said, because an unenforced rule
is the one this repository has been burned by.

**1 · Physical limits recorded in the driver and enforced independently of the
model's judgement.** Present. `COLLISION_DEVICES = (Nosepiece, ZDrive,
PFSOffset)`; two **sign-free** guards in
`Microscope._require_clear_of_sample` that refuse a write without consulting the
Z direction at all; `Z_RETRACT_DIRECTION = -1` measured 2026-09-05; and since
2026-09-06 the same fact declared to Micro-Manager as `FocusDirection,ZDrive,1`
in all six configs, where it had been `0` = *unknown*.
[`hardware/lunf_power.py`](../hardware/lunf_power.py) refuses to transmit; the
`.cfg` refuses `NIDAQAO-Dev1/ao2`; `optics.components.trapping_range_um` returns
`None` rather than a default for five of six objectives.

**Two honest exceptions.** `PFSOffset` is in `COLLISION_DEVICES` and its sign
convention has **never been measured** — the one unmeasured direction left on a
collision device. And
[`hardware/optical_tweezers.py`](../hardware/optical_tweezers.py) **has no
safety switch of its own**, unlike the other two drivers: its constructor opens
the socket and all 28 commands including `laser_on()` are directly callable.
Today `mcp_server/switches.py` is the only brake in that path. The switch
belongs in the driver — which is exactly where the standard would put it.

**2 · A human approval point for high-risk decisions.** Present, and currently
*too* present: `allow_write` · `allow_motion` · `allow_laser` all default off,
`.mcp.json` ships both move-tier switches `"0"` so every move-tier call on a
fresh session answers `refused: true`, the trap laser is armed by hand, and the
live sorting loop advances **on a keypress at every stage**. Operator-side
interlocks exist on the instrument in addition to these software gates.

**3 · A pre-experiment state check.** Present.
[`dualcam_hardware_config.py`](../config/session/dualcam_hardware_config.py)
asserts a full device state in application order and generates the matching
`.cfg` preset from the same list, so a script and a config that disagree is a
bug. `setup_dualcam_run.py --verify-splitter` identifies an unreadable element
*by measurement* — one excitation line at a time, both cameras, four numbers the
other two positions cannot fake. `focus_monitor.py` reports focus without ever
writing `ZDrive`. And **G27 is the only thing that notices the committee never
convened**, which is the state-check failure that matters most.

**4 · Agents for exploration; verified procedures fixed in deterministic code.**
This is the repository's central split, and it is a table in the README rather
than an aspiration: physical calculations, hardware limits, evidence and
provenance, and hard gates are **deterministic code**; the LLM supplies
qualitative judgment with no closed form and **originates no numerical value**
and cannot override a failed gate. 24 gates, none of which need the
instrument.

**5 · Operation logs and reproducible evaluation for auditing.** Partly.
Per-frame timestamps are recorded through
[`timestamped_capture.py`](../calibration/timestamped_capture.py) with
`requested_interval_ms` kept separate from the achieved `Interval_ms`;
`kb/decisions/` holds what was decided and why, including effects left *ungated
by decision* rather than by omission; 2,343 prior acquisitions are normalized
into physical quantities. **What is missing is the live half**: the closed loop
advances on a keypress and **no per-frame record of its decisions exists**, and
the repository's own rule for item 5 says that record has to be written *before*
the first loop closes, or lens 6's bias ledger (G23) is judging a session that
no longer exists.

**6 · A physical-safety assessment and misuse roadmap developed with partners
during the preview.** Anthropic's, not this bench's. The corresponding local
fact is that [`SAFETY.md`](../SAFETY.md) is a **first draft and not yet
operator-reviewed** — the current best account of the hazards, not a cleared
procedure — while every roadmap item that moves hardware is gated on it. None of
this instrument's vendors (Nikon, Photometrics, Yokogawa, Lumencor, Aresis,
Prior/Queensgate, Mightex, National Instruments) is among the announced
partners.

---

## 4 · The standard's stated limitations, from here

Three of these this bench can speak to. One it cannot, and saying so is what
makes the other three worth reading.

**"Claude's spatial and physical reasoning needs expert supervision."** Agreed,
and the evidence here is unambiguous rather than diplomatic: the first
end-to-end run was **operator-guided**, and five of its six falsified records
were corrected by the operator supplying a fact the repository had wrong. The
repository's structural response is not better reasoning but a smaller claim —
`advances: NO` on every lens, and *commissioning run* as a verdict distinct from
*successful measurement*.

**"May not distinguish real-world causes — bubbles, fluid behaviour, physical
failure — from software problems."** This is the limitation this bench is
positioned to work on, because **fluid behaviour is the lab's own subject**.
Active and dynamic samples are the hardest instance of it: *"the particles
started moving differently"* has candidate causes spanning a real change in
activity, focus drift, laser-power drift and a bug, and they are not separable
from the images alone. The answer implemented here is not that the model will
tell them apart — it is lens 6's bias ledger (G23) carrying every effect that
damages the specific quantity being measured, a **falsifier** on every stored
prior, and a refusal when the ledger cannot be closed. The 2026-09-04 result is
that mechanism working: a number was extracted, and the verdict was *report no
hindrance ratio from it*.

**"Long tasks can stall while the agent waits for human approval."** Confirmed
here in its strongest form — the live loop advances on a keypress at *every*
stage, so an unattended run is currently impossible by construction rather than
by policy. The concrete proposal is an **asynchronous approval channel** (Slack
or equivalent) so that a run blocks on a *notification* rather than on someone
being at the bench. That is a small piece of engineering with a real precondition
attached: the approval request has to carry the physical consequence of the
action, not just its name, or a remote *yes* is worse than a local one.

**"Needs a lot of context about the instrument and the goal."** This is what
`kb/` is: system dossier cross-checked three ways, measured calibrations, tacit
expertise notes each with its own falsifier, decisions, and 2,343 acquisitions
normalized into transferable physical quantities. The cost is real and is
mostly *human statement* — see §1.5.

**"Whether the compute cost of long-running real-time inference beats the
researcher time saved."** The axis this bench would add is not the one stated.
Researcher-hours saved is the wrong numerator for a shared high-end instrument;
the binding cost is the **training barrier**. On this microscope that is
concretely: a theorist cannot currently run their own experiment, a new student
needs months before their data is trustworthy, and a specialist operator is a
prerequisite for the instrument being used at all. A system that refuses
correctly is worth more against that cost than against wall-clock, because the
expensive failure is not slow work — it is a student's six months of data with an
unrecorded thermal state.

**What this bench cannot speak to: diagnosing a device's physical failure.** No
capability here addresses it, and the repository is worse-placed than the
limitation implies, because its own inventory of *what software cannot see* is
unbuilt — the per-configuration manual-steps checklist is proposal 4 in the
maintenance section and does not exist. The Splitter episode is the shape of the
problem: an unreadable element became the prime suspect precisely because it
could not defend itself, and the actual cause was a mislabelled device that
could.

---

## 5 · What this bench has not done

Stated so that nothing above implies otherwise.

- **No MCP tool has reached a device.** Verified end to end over stdio —
  handshake, tool list, a plan matching what the script prints, a refused
  move — and that is all.
- **No experiment has been executed end to end by the agent.** The first
  end-to-end run was operator-guided at every stage.
- **There is no dashboard and no one-click start.** Beginning a session is
  still a sequence of scripts.
- **Adding a device is not a minutes-long job here.** The piezo took a vendor
  DLL, a unit discovery (picometres, and a waveform generator that does *not*
  read its samples in the unit its position setter takes), and a first-light
  session.
- **The live loop is not a measurement path.** It samples the newest frame and
  drops the rest by design, so nothing it produces can become an MSD; it serves
  selection, not measurement.
- **`SAFETY.md` is a first draft, not operator-reviewed.**

---

## 6 · The decision criterion

Unchanged, and the sections above are the reason to keep it narrow.

Evaluate when the preview is reachable or the standard is open-sourced **and**
at least one device on this bench has a driver. Otherwise writing MHS drivers for
three instruments ourselves is the same integration work with an extra
specification to satisfy — and none of the vendors here is among the announced
partners, though Danaher and MBF Bioscience are, which is microscopy-adjacent.

**The zero-cost move meanwhile is to keep the swap cheap**, and the shape is
already right: one driver per file, an orchestrator that opens no device, a
read/write split whose write side is gated by `allow_write` · `allow_motion` ·
`allow_laser`, and — since 2026-09-06 — physical facts behind single readers that
return `None` rather than a default.

**What it would not fix, restated because it is most of what is blocking today.**
Not one named blocker disappears: Nikon still does not document the LUN-F's DAC
word format, the Tweez GUI still owns the camera exclusively and its TCP set
still has no camera command, the DMD's vendor package is still pinned to MM
interface v71, `power_at_sample_mw` still needs a power meter, and no standard
tells anyone that a temperature stage is sitting on the bench. **A standard makes
an integration cheap; it does not document an undocumented protocol, and it does
not perform a measurement.** It also moves only *how* a device is reached, never
*whether the setting is a good idea* — the 24 gates sit above any transport and
are unaffected either way.

---
