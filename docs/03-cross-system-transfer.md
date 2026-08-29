# 03 · Cross-system setting transfer

> **Status: sketch.** The procedure is a settled proposal; the conversion table
> gets filled in once the current system is settled.

The reason this project exists. Past data came from a microscope that no longer
exists, and systems will keep changing.

---

## 1. The problem

```
Archive, 2,343 acquisitions             Current system
───────────────────────────             ──────────────
Prime 95B 25mm, 11 µm                   ? (undetermined)
Lumencor Spectra X                      ? + devices to be added
Nikon Ti + PFS                          ?
DA/FI/TR cube ×1                        ?
100x Oil mostly                         ?
                                        piezo (outside MM and NIS)
```

Confirmed values for the current system: `kb/systems/current.md`.

Carrying `Exposure=500ms, Spectra-Red_Level=10` over verbatim is **wrong**,
because camera QE and pixel pitch, source output and spectrum, and filter
transmission all differ.

---

## 2. What transfers and what does not

| Setting | Transfers as-is | Via physical quantity | Needs recomputation | Note |
|---|:---:|:---:|:---:|---|
| Exposure time (ms) | ❌ | ✅ | | mediated by the required photon count |
| Light level (%) | ❌ | ✅ | | via mW/cm² @sample |
| Source line | ❌ | ✅ | | via center wavelength and bandwidth |
| Filter | ❌ | ✅ | | via passband |
| Objective | ❌ | | ✅ | reselected from NA and magnification |
| binning | ❌ | | ✅ | from the effective-pixel-size target |
| ROI | ❌ | | ✅ | from the field-of-view and frame-rate targets |
| readout/gain mode | ❌ | | ✅ | from the noise and speed requirements |
| **Frame rate** | ✅ | | | the sample's timescale sets it |
| **Effective pixel size** | ✅ | | | the task sets it |
| **Required SNR** | ✅ | | | the target precision sets it |
| **Total photon dose ceiling** | ✅ | | | the sample sets it |
| **Excitation/emission bands** | ✅ | | | the dye sets it |

**The five in bold are what actually transfers.** The rest are per-instrument
means of satisfying those five.

> This table is the shift in thinking. Not "what did I use last time?" but
> **"what did I achieve last time?"**

---

## 3. Transfer procedure

```
① Precedent search
   SQL query on sample system + dye + task (imaging/tracking/frap) + timescale
   → N candidate acquisitions

② Extract physical quantities  (needs the old system profile)
   Compute the tier-3 values for each candidate
   → achieved effective pixel, excitation band, irradiance, dose,
     measured fps, (where possible) SNR

③ Fix the target physical quantities
   Take the physical quantities of whichever candidate "came out well"
   ⚠ the basis for "came out well" has to be in kb/decisions. If it is not,
     ask the human

④ Back-calculate for the current instrument  (needs the current system profile)
   target physical quantities → the setting combination that produces them on
   this instrument
   If degrees of freedom remain, narrow them with [04 §1 decision order]

⑤ Pass the gates
   14 hard gates + the committee's 6+2

⑥ State the residual uncertainty
   List every value used in the back-calculation that was assumed
```

---

## 4. Back-calculation formulas

### Exposure time

To hold the target detected photon count `N_target`:

$$t_{\exp}^{\text{new}} = t_{\exp}^{\text{old}} \times
\frac{k_{det}^{\text{old}}}{k_{det}^{\text{new}}}$$

`k_det` is the product of the whole chain in
[04 §3](04-decision-engine.md). In practice:

$$\frac{k_{det}^{\text{new}}}{k_{det}^{\text{old}}} =
\underbrace{\frac{I^{\text{new}}}{I^{\text{old}}}}_{\text{irradiance}} \times
\underbrace{\frac{\eta_{geo}^{\text{new}}}{\eta_{geo}^{\text{old}}}}_{\text{NA}} \times
\underbrace{\frac{T_{em}^{\text{new}}}{T_{em}^{\text{old}}}}_{\text{emission path}} \times
\underbrace{\frac{QE^{\text{new}}}{QE^{\text{old}}}}_{\text{camera}}$$

`optics/` already computes each factor. **Only the irradiance ratio is blocked,
for want of a measurement.**

### Holding the pixel-size target

$$M^{\text{new}} = \frac{p_{\text{sensor}}^{\text{new}} \times B^{\text{new}}}
{p_{\text{sample}}^{\text{target}}}$$

Among the available magnification combinations (objective × intermediate
magnification × binning), pick the one closest to the target. An exact match is
unusual, so **which way it misses matters** — toward `σ_PSF` for tracking,
toward Nyquist for morphology.

### Frame-rate realizability

$$f^{\text{new}} \le \frac{1}{\max\left(t_{\exp}^{\text{new}},\;
h_{ROI} \times t_{\text{row}}^{\text{new}}\right)}$$

`t_row` differs per camera. The old setup was 10.28 µs/row
([04 §5](04-decision-engine.md)). **It has to be measured again on every new
camera** — divide the metadata's `ReadoutTimeNs` by the ROI height (the current
camera's measured value: `kb/calibrations/camera-readout.yaml`).

---

## 5. ⚠ Where this procedure does not work today

| Blocker | Why | How to clear it | Cost |
|---|---|---|---|
| **No measured irradiance** | `power_at_sample_mw` is empty everywhere, on both the old and the new system | Power-meter measurement of line × objective × level | 30 min, and already impossible for the old system |
| Old system's emission path unknown | Cube and wheel parts undetermined | Physical inspection | — |
| Old system's NA unverified | No NA in the metadata | Barrel engraving | — |
| Background noise unrecorded | SNR cannot be back-calculated | Dark/background frames with every acquisition | A few seconds per acquisition |

**The old system is already gone or changed, so retroactive measurement is
impossible.** What can transfer out of the archive is therefore **not an
absolute photon budget but relative relations**:

- ✅ "tracking worked on this sample at 100x with an effective pixel of 110 nm"
  → transferable
- ✅ "the 647 channel needed a 500 ms exposure = the light level was
  insufficient" → transferable as a qualitative signal
- ✅ "at duty 28% the motion blur bias was under 10%" → transferable
- ❌ "Spectra Red 10% is the right light level" → **not transferable**

> Which is why the priority is "measure the current system's light level." Do it
> once and everything acquired from then on becomes transferable.

---

## 6. Worked example (sketch — filled in once the current system is settled)

**Request**: track 647-labeled particles in the dextran-rich phase of an ATPS,
target precision 10 nm, characteristic time 50 ms

```
① precedent:  DEX647 / tracking / ATPS  →  134 acquisitions
② physical:   p_sample 110 nm, 100x NA1.45, exposure 80 ms,
              measured fps ~11, duty 88%(!), irradiance unknown
③ target:     p_sample 100–120 nm,  f ≥ 20 Hz,  duty ≤ 30%,  N ≥ ? photons
              ⚠ the precedent's duty 88% means 29% motion blur bias — not a
                target to adopt
④ back-calc:  [needs the current system profile]
⑤ gates:      [run]
⑥ uncertain:  [list]
```

The point of ②→③ is that **the precedent was not adopted as the target**. When
the precedent is defective (duty 88% here), the physics gates catch it.
**A precedent is a starting point, not the answer.**

---

## 7. What to do when the system changes

Every time a new `.cfg` arrives:

1. Compute the fingerprint → decide whether this is a known system or a new one
2. If new, create `kb/systems/<id>.md` and mark the previous one `status: legacy`
3. **Record the diff of the two dossiers in
   `kb/systems/_transitions/<old>-to-<new>.md`**
   - What changed (camera? light source? filters? objective?)
   - Which factor of the transfer formula each change affects
   - Whether any past data needs retroactive reinterpretation
4. Run the new system's calibration checklist (the four items in §5)
5. Until calibration is done, every gate is `evidence: assumed` → `advances: NO`

That diff file is the conversion table.

---

## 8. Another lab is the same problem, one step out

This is built on the microscope in Prof. Sho Takatori's lab, Stanford Chemical
Engineering. Running it in a different lab is a considered direction, and it is
**not a new mechanism** — a lab whose instrument shares no history with this one
is, to §7's fingerprint, simply an unknown system. What changes is only how much
has to be replaced at once.

### What is portable, and what is this instrument's

| Portable — computes from physical quantities | This instrument's — must be replaced |
|---|---|
| The eight lenses and the 32 gates | [`kb/systems/current.md`](../kb/systems/current.md) — this device wiring, cross-checked three ways |
| The 3-tier normalization and the `evidence` / `advances` split ([02 §2](02-knowledge-base.md), [01 §3](01-architecture.md)) | [`kb/calibrations/`](../kb/calibrations/) — pixel size, camera row time, disk bandwidth, all measured here |
| The decision order and the formulas behind every gate ([04](04-decision-engine.md)) | [`kb/expertise/`](../kb/expertise/) — this lab's tacit priors: which coverslip is really in use, which immersion media, trapping with an oil objective in water |
| The `data/*.yaml` registries as *catalogue* data — detectors, objectives, filters, light sources, fluorophores, spectra | Which entries of those registries are actually on the bench, and every empty field a power meter has to fill |
| The knowledge-base schema: source, trust level, applicable scope, falsifier | [`hardware/`](../hardware/) — drivers bound to these vendor DLLs, this TCP surface, this NIDAQ wiring |
| The refusal discipline itself, which is the part with no lab in it | The 2,343-record archive, which is one Nikon + Photometrics combination's precedent |

### The failure mode that makes this more than a configuration exercise

A new lab's mistakes would be **silent**, not loud. The dangerous entries are not
the ones that are obviously missing — those already return `BLOCKED` and name
themselves. They are the ones this lab **settled by decision**, which then look
like properties of physics rather than choices.

Lens 4's scope fix is the example: sample-medium index settled at 1.333 and
coverslip at 170 µm ([`2026-08-19-lens-4-scope.md`](../kb/decisions/2026-08-19-lens-4-scope.md))
because that is what is on this bench and it matches every objective's design.
Hand that to a lab running 150 µm coverslips, a glycerol-based medium, or a
collar objective set differently, and **G17 and G18 compute happily and are
wrong**, with no field empty anywhere to hint at it.

So the portability work is not "make the constants configurable". It is: **every
value that was settled by decision has to know it was settled by decision**, and
revert to `BLOCKED` for a system that did not make that decision. The
[`kb/decisions/`](../kb/decisions/) entries already record which values those
are, and a `scope:` field naming the system a decision applies to is the missing
half — the same shape as the `falsifier` field, one level up.
