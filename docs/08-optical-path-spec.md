# 08 · Optics lens design

Two things, which must not be mixed.

| | What | Form | Where |
|---|---|---|---|
| **§0** | **How the optics reviewer reaches a verdict** | Logic (Python) | `optics/gate.py` |
| **§1–7** | **How the optics hardware is written down** | Data (YAML) | `kb/systems/`, `data/` |

---

## 0. The reviewer's computation structure — a check registry, not an `if` chain

> **Question**: the review runs in order, so why not just chain `if` statements?

`if` itself is right. The question is **whether the `if` goes *between* checks or
*inside* a check**.

### ❌ The bad form — if chain / early return

```python
def evaluate(ch):
    if ch.excitation_efficiency() == 0:
        return FAIL("no excitation")
    if ch.blocking_od() < 5:
        return FAIL("insufficient blocking")
    if ch.crosstalk() > 0.05:
        return FAIL("crosstalk too large")
    return PASS
```

It reads easily and looks natural, but four things break in this project.

**(1) Only the first problem gets reported.**
The experimenter fixes it → re-runs → finds another → re-runs, over and over.
What is needed is **the whole picture at once**. Walking to the microscope to
rework the light path should happen once.

**(2) The difficulty grade cannot be produced.**
The `ROUTINE`/`TIGHT`/`HARD` grades of [05 §3](05-consensus-gate.md) require
**the margin of every gate**. Return at G1 and the margins of G2–G4 are unknown.
"How hard is this experiment" cannot be answered.

**(3) Improvement proposals cannot be produced.**
A sensitivity analysis is "which gate is the bottleneck, and how much does each
intervention raise its margin". All of it has to be computed.

**(4) Adding a check means editing the function.**
Every new check makes `evaluate` longer, and testing re-runs the entire
function. A single check cannot be unit-tested.

### ✅ The right form — two phases + a flat list of checks

```
Phase 0   input sufficiency check
          ← only this depends on preconditions. If unmet, BLOCKED and nothing
            else is computed (without NA, computing collection efficiency is
            meaningless in the first place)

Phase 1   run every check independently
          ← they know nothing of each other. A failure does not stop the rest.
            Each returns its own margin.

Phase 2   aggregate
          ← hard gate veto / difficulty = worst margin / sensitivity analysis
```

**`if` is used only *inside* a check.**

```python
@dataclass
class Check:
    code: str
    kind: str                  # hard | bias | soft   ← [05 §2]
    requires: tuple[str, ...]  # inputs this check needs
    run: Callable[[Channel, list[Channel]], CheckResult]

@dataclass
class CheckResult:
    margin: float        # achieved/required. 1.0 = exactly at the limit. Feedstock for grade and sensitivity
    severity: str        # fail | warn | info | ok
    message: str
    action: str | None   # mandatory if FAIL
    numbers: dict        # every value the verdict rested on
```

A single check looks like this. Using `if` inside it is natural:

```python
def check_blocking(ch, others):
    od = ch.excitation_blocking_od()
    required = 5.0
    margin = od / required
    if margin >= 1.0:
        return CheckResult(margin, "ok", f"blocking {od:.1f} OD", None, {"od": od})
    return CheckResult(
        margin, "fail",
        f"the detection path attenuates the excitation by only {od:.1f} OD. Backscatter swamps the signal.",
        action=f"add an emission filter with sufficient blocking at {ch.source.center_nm:.0f} nm",
        numbers={"od": od, "required": required},
    )

CHECKS = [
    Check("excitation.coupling", "hard", ("dye.abs", "source", "ex_path"), check_excitation),
    Check("blocking",            "hard", ("source", "em_path", "qe"),      check_blocking),
    Check("collection",          "soft", ("dye.em", "em_path", "qe"),      check_collection),
    Check("crosstalk",           "bias", ("dye.em", "em_path", "others"),  check_crosstalk),
    ...
]
```

Aggregation is only this:

```python
def evaluate(ch, others):
    missing = [c for c in CHECKS if not inputs_available(ch, c.requires)]
    if missing:
        return Verdict(status="BLOCKED", ...)          # Phase 0

    results = {c.code: c.run(ch, others) for c in CHECKS}   # Phase 1 — run them all

    hard_veto = any(r.margin < 1 for c, r in pairs if c.kind == "hard")
    worst = min(r.margin for c, r in pairs if c.kind in ("soft", "bias"))
    return Verdict(                                     # Phase 2
        status="FAIL" if hard_veto else grade(worst),
        feasibility=grade(worst),
        margins={code: r.margin for code, r in results.items()},
        ...
    )
```

### Why it feels "sequential"

Light passes through in order, but **the verdict has no order.**

- Transmission is a product: `T = Π Tᵢ` — commutative, order-independent
- The verdict is an AND of independent conditions:
  `excitation ∧ collection ∧ blocking ∧ crosstalk`
- What looks like order is **narrative order**, not a computational dependency

There is exactly one real dependency: **input sufficiency (Phase 0)**. Two phases
are therefore enough.

### The same structure is used for the other lenses

The Detection, Compute resources, and Optical tweezers lenses all use the same
`Check` / `CheckResult` / `Verdict` schema. That is what lets the committee
aggregate lenses uniformly, and keeps the difficulty grade and the sensitivity
analysis indifferent to which lens they came from.
→ [05 §5](05-consensus-gate.md)

### Current implementation ✅

Implemented in exactly this structure.

- `optics/checks.py` — the `Check` / `CheckResult(margin)` / `CHECKS` registry,
  `available_facts()` (Phase 0), `grade()` (difficulty grade)
- `optics/gate.py` — Phase 0/1/2 aggregation only. No check logic

The margins appear directly in the output:

```
feasibility: COMFORTABLE  Normal range.
bottleneck:  blocking  (margin 1.65)

  margins (achieved / required; 1.0 = exactly at the limit)
      0.98  emission.centering         #########
      1.65  blocking                   ################
      1.95  excitation.coupling        ###################
      2.20  spectral.separation        ######################
      3.04  collection                 ##############################
     10.00  crosstalk                  ##############################
```

Two things that tripped this up during implementation:

- **Margin blowup** — when crosstalk is effectively zero, `limit/actual` comes
  out as 1e28. Clamped with `MAX_MARGIN = 10.0`
- **Scoring the same quantity twice** — `collection` (absolute) and
  `emission.centering` (the filter's contribution) measure the same physical
  quantity, and scoring both docks one weakness twice. On top of that, 49% filter
  efficiency against a 50% target dragged the whole thing down to `HARD`.
  → `centering` demoted to `INFO`. **`collection` owns the grade and `centering`
  explains the reason**

---

## 1. Why hardware must not be written as `if` statements

*(From here on it is about the hardware description format — separate from the
verdict logic)*

```python
# ❌ Do not write it like this
def throughput(wavelength, channel):
    t = 1.0
    if channel == "647":
        t *= excitation_filter_640(wavelength)
        if dichroic_installed:
            t *= dichroic_650(wavelength)
        ...
```

**(1) The code has to change every time the hardware does.**
Swap one filter and it is edit code → test → commit. Filters change often in a
lab. That does not compare to editing one line of YAML.

**(2) Ablation becomes impossible.**
The core capability of the optics lens in this project is to actually compute —
not guess — **"what happens if this element is removed"**. To drop a term from a
product, the terms have to be **elements of a list**. An `if` branch cannot be
removed.

```python
# ✅ Possible because it is a list
signal_without = channel.relative_signal(skip="FF01-692/40")
gain = signal_without / channel.relative_signal()
```

**(3) It cannot be cross-checked against the `.cfg`.**
To confirm that the Micro-Manager config file and the real light path agree, both
have to be **lists** in the same form. You cannot diff a code branch against a
`.cfg`.

**(4) No history is left.**
In a `git diff`, `- FF01-692/40` / `+ FF01-685/70` reads at a glance. A diff that
changed an `if` condition does not say what hardware changed.

**(5) Multiplication is commutative.**
Order is meaningless in a transmission calculation to begin with. `T = Π Tᵢ`.
The sequentiality of `if` statements is an illusion, not a reflection of physics.

---

## 2. Where order really does matter

Order is irrelevant to the transmission calculation, but **the following depend
on it.** So order is recorded rather than discarded — it just is not used in the
calculation.

| Item | Why order matters |
|---|---|
| **segment** | Before/after the beamsplitter divides excitation path from emission path. **This one affects the calculation directly** |
| Autofluorescence | Fluorescing elements (plastics, adhesives, some NDs) are only filtered out if they sit **before** the emission filter |
| Damage threshold | Putting the ND before or after the high-power stage decides component lifetime |
| Ghosts & etalon | Multiple reflections between two adjacent parallel optical surfaces |
| Polarization | Among polarizing elements, order changes the result |
| Physical constraint | Which slot a part can go into |

→ Hence it is written as **an ordered list per segment**. Compute with the
product, record the order.

---

## 3. The two-tier model — separate instrument from channel

This is the crux. **The instrument does not change; only the slot settings do.**

```
① instrument          what is physically installed in which slot
                      kb/systems/current.md
                      changes: once every few months

② channel             which position each settable slot is put in
                      config/channels/*.yaml
                      changes: every experiment
```

**This structure is exactly Micro-Manager's `ConfigGroup`.**

```
# structure of an MM .cfg
ConfigGroup,Channel,647-Cy5,FilterTurret1,Label,1-Quad
ConfigGroup,Channel,647-Cy5,Wheel-A,Label,2-FF01-692/40
ConfigGroup,Channel,647-Cy5,Spectra,Red_Enable,1
```

So **channel definitions can be generated automatically from the `.cfg`, and
conversely a recommendation can be exported as a `.cfg` preset.** MM2 is settled,
so this round trip is possible as planned.

---

## 4. Instrument description format

The front matter of `kb/systems/current.md`. Written **slot-first**.

```yaml
optical_slots:

  # ── excitation path (light source → sample) ───────────────
  - slot: light_engine
    segment: excitation
    order: 10
    device: Spectra            # MM device label
    kind: light_source
    fixed: true                # the position never changes
    ref: data/light_sources.yaml#Spectra

  - slot: cube.excitation
    segment: excitation
    order: 20
    device: FilterTurret1      # sits inside the cube
    kind: bandpass
    selectable: true           # changes as the turret rotates
    positions:
      1: {ref: "data/filters.yaml#<cube1 excitation filter>"}
      2: null                  # empty
    note: "Built into the cube. Not individually replaceable"

  - slot: cube.dichroic
    segment: shared            # reflects the excitation, transmits the emission
    order: 30
    device: FilterTurret1
    kind: dichroic
    selectable: true
    removable: false           # structural element
    positions:
      1: {ref: "data/filters.yaml#<cube1 dichroic>"}

  - slot: nosepiece
    segment: shared
    order: 40
    device: Nosepiece
    kind: objective
    selectable: true
    positions:
      1: {ref: "objectives#10x"}
      5: {ref: "objectives#100x-oil"}

  # ── emission path (sample → camera) ───────────────────────
  - slot: cube.emission
    segment: emission
    order: 50
    device: FilterTurret1
    kind: bandpass
    selectable: true

  - slot: wheel_A
    segment: emission
    order: 60
    device: Wheel-A
    kind: bandpass
    selectable: true
    positions:                 # ⚠ all empty in the old setup
      0: null
      1: {ref: "data/filters.yaml#..."}
      2: {ref: "data/filters.yaml#..."}
    note: "Label must be registered in the MM .cfg to survive in the metadata"

  - slot: magnifier
    segment: emission
    order: 70
    device: IntermediateMagnification
    kind: magnifier
    selectable: true
    positions: {1: 1.0, 2: 1.5}
    off_ledger: false          # false if it is registered in MM

  - slot: sideport
    segment: emission
    order: 80
    device: LightPath
    kind: beam_split
    selectable: true
    positions:
      "4-L100": {fraction: 1.00, destination: camera}
      "3-AUX":  {fraction: 0.00, destination: aux, note: "tweezers/DMD"}

  - slot: camera
    segment: emission
    order: 99
    device: Prime95B
    kind: detector
    fixed: true
    ref: data/detectors.yaml#Prime95B
```

**Key fields**

| Field | Role |
|---|---|
| `segment` | `excitation` / `emission` / `shared` — **used directly in the calculation** |
| `order` | Physical order. For judging the order-dependent items of §2 |
| `selectable` | Can it be changed automatically (turret, wheel) or must it be swapped by hand |
| `removable` | Is it an ablation candidate. Structural elements are `false` |
| `positions` | The selectable positions → what each one holds |
| `off_ledger` | Does MM fail to record the state → sidecar mandatory |
| `ref` | The real spec lives in the `data/` registry; only a reference here |

**If a slot is empty, state `null` explicitly.** Drop the entry itself and "not
checked" cannot be distinguished from "empty".

---

## 5. Channel description format

Reference the instrument and write **only the slot positions**.

```yaml
# config/channels/647-tracking.yaml
system: current                # references kb/systems/current.md

channels:
  - name: "647-Cy5"
    dye: ATTO647N
    slots:
      cube.dichroic: 1
      cube.emission: 1
      wheel_A: 2
      nosepiece: 5
      magnifier: 1
      sideport: "4-L100"
    illumination:
      device: Spectra
      line: Red
      level_percent: 10
    camera:
      exposure_ms: 80
      binning: 1
      roi: [742, 898, 160, 176]
      readout_mode: HDR-16bit
```

The optics lens merges this with the instrument description and expands it into a
`Channel` object. Nobody has to write filter names out repeatedly, and when the
instrument changes only **one place** needs editing.

> **The current implementation** still supports only the short form (filter names
> listed directly in the channel).
> → [config/channels/proposed-2color.yaml](../config/channels/proposed-2color.yaml)
> The slot-reference form is not implemented yet.

---

## 6. So where do `if` statements go

**In the verdict logic.** Not in the hardware description.

```python
# ✅ This is logic — if is correct here
if blocking_od < floor:
    verdict = "required"
elif crosstalk > limit:
    verdict = "required"
elif gain >= threshold and not spectra_measured:
    verdict = "candidate"
```

The dividing line:

| | Form | Where |
|---|---|---|
| **What is installed** | Data (YAML) | `kb/systems/`, `data/` |
| **What it is set to** | Data (YAML) | `config/channels/` |
| **Whether that is acceptable** | Logic (Python) | `optics/gate.py` |
| **The physics calculation** | Formulas (Python) | `optics/spectra.py`, `path.py` |

Start writing hardware into code and **verdict criteria get mixed up with
hardware facts**, and then "why is this filter here?" becomes unanswerable.

---

## 7. The `.cfg` round trip (possible now that MM2 is settled)

```
MM .cfg  ──parse──▶  kb/systems/current.md  (slots · positions · labels)
                               │
                               ├─ cross-check vs NIS-Elements device list
                               │      → three-way cross-check table  [02 §4]
                               ├─ cross-check vs physical inspection
                               │      → missing devices found
                               │
                               ▼
                     optics lens computation
                               │
                               ▼
               config/channels/*.yaml  (recommended slot settings)
                               │
                          ──generate──▶  MM ConfigGroup preset
                                         (Phase 2: automatic apply)
```

What to extract from the `.cfg`:

| `.cfg` line | Use |
|---|---|
| `Device,<label>,<lib>,<name>` | Device list → three-way cross-check table |
| `Label,<device>,<state>,<name>` | **Turret/wheel position names** ← the biggest gap in the old setup |
| `ConfigGroup,Channel,<preset>,...` | Existing channel definitions → initial KB |
| `ConfigGroup,System,Startup,...` | Startup state |
| `Property,<device>,<prop>,<val>` | Defaults |
| `PixelSize_um`, `ConfigPixelSize` | Pixel calibration (absent in the old setup) |

**Without `Label,` lines the filter wheel is recorded as `Filter-0` forever.**
The first thing to check on receiving a `.cfg`.
