# 01 · Architecture

## 0. One-sentence summary

Turn past acquisition metadata into a **knowledge base normalized to physical
quantities**; when a new experimental request arrives, generate a **setting
proposal reprojected onto the current instrument**, and confirm only what passes
**unanimous consent of a per-subsystem committee**.

---

## 1. Why an ordinary chatbot will not do

Three structural constraints determine the design.

**(1) Past settings cannot be copied verbatim.**
The 2,343 archived acquisitions came from a setup that no longer exists. Device
values like `Exposure=500ms, Spectra-Red_Level=10` are meaningless once the
camera, light source, or filters change. The only transferable content is the
**physical quantities** that setting produced — photon flux at the sample,
effective pixel size, excitation/emission bands, total photon dose.

**(2) Anything computable must not be guessed.**
Optical transmission, SNR, sampling, and trap stiffness all have closed forms.
The moment an LLM answers "roughly this much should be fine," this project has
failed. Code does the computing; the LLM **gathers inputs and interprets
results**.

**(3) Optima run in opposite directions depending on the lens.**
For a light-driven active particle, the optics lens says "raise the light for
SNR" while the photo-perturbation lens says "that light is pushing the
particle." Morphology observation and particle tracking want opposite pixel
sizes. Single-lens optimization produces quietly wrong answers.

---

## 2. Layers

```
┌─ L0  Sources (read-only) ──────────────────────────────────────────────┐
│  MM metadata *_metadata.txt   MM .cfg   NIS-Elements settings          │
│  Hardware datasheets   filter/dye spectral curves   protocol documents │
│  Analysis code (D:\codes)  ← which analysis you run sets the           │
│                              setting requirements                      │
└────────────────────────────────────────────────────────────────────────┘
                                   │
┌─ L1  Ingest & normalize ───────────────────────────────────────────────┐
│  Streaming parser (headers only: Summary + first FrameKey + tail)      │
│  Handles the MM 1.4 / 2.0 dual schema                                  │
│  3-tier normalization:  raw  →  device  →  physical                    │
│  System fingerprint decides "which microscope is this" automatically   │
└────────────────────────────────────────────────────────────────────────┘
                                   │
┌─ L2  Knowledge base (persistent) ──────────────────────────────────────┐
│  kb/systems/       per-system dossier + three-way device wiring cross- │
│                    check                                               │
│  kb/calibrations/  measured hardware calibrations                      │
│  kb/decisions/     past recommendations + actual outcomes ← learning   │
│                    loop                                                │
│  kb/expertise/     expertise extracted from conversation               │
│  data/             dye / filter / light source / detector registries   │
│                    (spectra included)                                  │
└────────────────────────────────────────────────────────────────────────┘
                                   │
┌─ L3  Inference ────────────────────────────────────────────────────────┐
│  Search precedent → convert to physical quantities → reproject onto    │
│  the current instrument → solve the constraints                        │
│  (choose exposure, light level, binning, ROI under a required SNR /    │
│   time resolution / photon budget)                                     │
└────────────────────────────────────────────────────────────────────────┘
                                   │
┌─ L4  Committee ────────────────────────────────────────────────────────┐
│  Hard gates (code)  +  per-subsystem lenses 6+2                        │
│  Nothing passes unless every lens ADVANCEs. Every FAIL must carry a    │
│  concrete fix instruction.                                             │
└────────────────────────────────────────────────────────────────────────┘
                                   │
┌─ L5  Output ───────────────────────────────────────────────────────────┐
│  Setting proposal (rationale · assumptions · uncertainty · alternatives)│
│  MM Channel preset / off-ledger settings checklist                     │
│  Experiment plan                                                       │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Core design principles

### Principle 1 — Judge by computation, never by inference

The LLM does not estimate a value that can be computed. If the input is
missing, it **refuses**.

This is enforced in code. `optics.gate.Verdict` separates two axes:

| Axis | Meaning |
|---|---|
| `status` | Is it physically sound (`PASS` / `PASS_WITH_CHANGES` / `FAIL` / `BLOCKED`) |
| `evidence` | Were the values used measured (`measured`) or estimated (`assumed`) |
| `advances` | **`passed and evidence == "measured"`** — this is all the committee looks at |

If the computation ran on nominal catalog values, `advances` is `NO` even when
`status` is `PASS`. Everything that was estimated is listed in
`assumed_inputs`.

```
evidence: assumed   confidence: low   advances: NO
assumed:  ATTO647N spectra, FF01-692/40, Plan Apo 100x Oil transmission,
          Spectra.Red power at sample
```

### Principle 2 — 3-tier normalization; only physical quantities transfer

```
tier 1  raw       "Spectra-Red_Level": "10"      Verbatim. Never lost.
tier 2  device    source=Spectra, line=Red, 10%  Instrument-bound. Valid only
                                                 within the same system.
tier 3  physical  640±15 nm, ? mW/cm² @ sample   Instrument-independent. Only
                                                 this transfers across systems.
```

If tier 3 is empty (i.e. there is no measured light level), cross-system
transfer is **impossible**. That is exactly the state of the current archive.
→ [03](03-cross-system-transfer.md)

### Principle 3 — Off-ledger settings are first-class citizens

Settings that MM does not record do exist.

| Item | Status | Where it survives |
|---|---|---|
| Optical tweezers power | **Off-ledger** — power measurement pending | Folder name `OT0.005` |
| Piezo stage | **Off-ledger** — not registered in MM or NIS, separate program | Nowhere |
| Filter wheel position | Registered, **label not registered** — position info pending | Recorded only as `Filter-0` |
| 1.5x intermediate magnification | **Registered in MM** (current system) | Was missing only in archive generation C |

→ Leave an `acquisition.yaml` sidecar for every acquisition, and have the agent
explicitly ask for the off-ledger items to fill it. If it does not ask, the
information is lost forever.

> Archive generation C was recorded with no `IntermediateMagnification` device
> in the config, so the 1.5x survives only in the folder name. It shows that a
> device being registered is a separate question from **whether that config was
> the one used for the acquisition**. This is why the fingerprint includes the
> device list.

### Principle 4 — The knowledge base is text

`kb/` is markdown + SQLite. A human can open and fix it, git keeps its history,
and the agent can grep it. No vector DB and no opaque embedding store — those
make "why was this value recommended" untraceable.

### Principle 5 — Unanimous consent, but deadlocks go to the human

Only unanimous ADVANCE passes. But unanimity across six lenses deadlocks
easily, so:

- Every FAIL must carry a **concrete fix instruction** (no complaining)
- The revise → re-review loop runs **at most 3 times**
- If it does not converge within 3 rounds, **present the conflict itself to the
  human**:
  "Photo-perturbation requires ≤5% light level; detection requires ≥30% to
  reach SNR 5 at 20 Hz. These are incompatible. (a) Lower the frame rate to
  10 Hz, (b) switch to a brighter dye, or (c) accept the light-driven
  perturbation and proceed — a choice is needed."

This is **correct behavior, not failure**. Failure would be forcibly papering
over physically incompatible requirements.

---

## 4. Committee composition

The split is by subsystem. Splitting by discipline (optics / colloids / theory)
overlaps jurisdictions and yields "everyone thinks it's roughly fine" verdicts.
Splitting by subsystem makes **the settings each lens owns** unambiguous, so a
FAIL is already a fix instruction.

### Standing (6)

| # | Lens | Settings owned | Basis of verdict | Implementation |
|---|---|---|---|---|
| 1 | **Optics** | Filters, dichroics, mirrors, ND, objective, light path | Spectral integration → fully deterministic | `optics/` ✅ |
| 2 | **Detection** | Exposure, binning, ROI, readout, gain, frame interval | Photon budget, SNR, sampling → deterministic | `detection/` ✅ |
| 3 | **Compute resources** | Frame rate, buffer, storage, processing | Bandwidth and capacity arithmetic → deterministic | `compute/` ✅ |
| 4 | **Sample geometry & optics** | Objective choice, immersion, coverslip, focal depth | Refractive index, WD, aberration → semi-deterministic | `sample/` ✅ (G15–G19) + `.claude/agents/sample-optics.md` for the qualitative half |
| 5 | **Photo-perturbation** | Light level, illumination duty, total dose | Bleaching, heating, light-driving → semi-deterministic | `photo/` ✅ (G10, G20–G22) + `.claude/agents/photo-perturbation.md` for the qualitative half |
| 6 | **Measurement validity** | Whether all of the above yields the intended physical quantity without bias | Bias computation + qualitative | `.claude/agents/measurement-validity.md` (draft, no code) |

### Conditional (2)

| # | Lens | Convened when | Basis of verdict | Implementation |
|---|---|---|---|---|
| 7 | **Optical tweezers** | Tweezers in use | Trap stiffness κ, U/kT, corner frequency f_c → computed | `trapping/` ✅ (no heating check — [06 D6](06-pitfalls.md)) |
| 8 | **Mechanical & environmental** | Long experiments (>30 min) | Drift, vibration, evaporation, PFS lock | Not implemented |

### Why 4 and 5 are separate

A sample's **geometric/optical properties** and its **photoresponsiveness**
demand different expertise and lead to opposite conclusions. Bundling them into
one lens hides that conflict.

### Cross-lens constraints (what no single lens catches)

This is the real reason for having a committee.

| Constraint | Lenses | Content |
|---|---|---|
| Motion blur | 2 ↔ 6 | If particle travel during exposure exceeds the PSF, MSD is **underestimated** |
| Trap stiffness vs sampling | 7 ↔ 2 | Power-spectrum calibration needs `f_s ≳ 10·f_c`. Raising laser power raises f_c, which raises the frame-rate requirement |
| Light level vs light-driving | 1 ↔ 5 | The extra light needed for SNR drives active particles |
| ROI vs statistics | 3 ↔ 6 | Shrinking the ROI for speed reduces the particle count in the field, weakening statistical power |
| Pixel size | 2 ↔ 6 | Morphology wants Nyquist; tracking is optimal at σ_PSF ≈ pixel. **Opposite directions** |
| Immersion vs depth | 4 ↔ 1 | Refractive-index mismatch grows spherical aberration in proportion to depth. In ATPS the two phases have different RI |

---

## 5. Folder structure

```
experimentalist/
│
├── README.md                     Project overview + document map
├── requirements.txt
│
├── docs\                         ← design documents
│   ├── 01-architecture.md        (this file)
│   ├── 02-knowledge-base.md      KB schema · three-way wiring cross-check · off-ledger settings
│   ├── 03-cross-system-transfer.md   transferring settings between systems
│   ├── 04-decision-engine.md     decision order · formulas · the 14 hard gates
│   ├── 05-consensus-gate.md      committee · difficulty grades · improvement proposals
│   ├── 06-pitfalls.md            pitfall list grounded in measured evidence
│   ├── 07-roadmap.md             Phase 0–5
│   ├── 08-optical-path-spec.md   lens computation structure · hardware YAML format
│   └── 09-knowledge-capture.md   expertise capture — the real purpose of this project
│
├── .claude\agents\               ← judgment lenses as LLM subagents (draft, no code)
│   ├── sample-optics.md          lens 4
│   ├── photo-perturbation.md     lens 5
│   └── measurement-validity.md   lens 6
│
├── optics\                       ← lens 1 (optics)
│   ├── spectra.py                Spectrum type, curve loading, band approximation
│   ├── components.py             dyes · filters · dichroics · sources · objectives · detectors
│   ├── path.py                   light-path model, throughput, ablation analysis
│   ├── checks.py                 check registry · margin · difficulty grade
│   ├── gate.py                   Phase 0/1/2 aggregation + evidence separation
│   ├── build.py                  dict/YAML → Channel
│   ├── recommend.py              setting recommendation
│   └── cli.py                    `python -m optics.cli check <config>`
│
├── detection\                    ← lens 2 (detection, G5–G9)
│   ├── photometry.py             photon budget, SNR
│   ├── timing.py                 frame timing, rolling shutter
│   ├── checks.py  gate.py  setup.py  cli.py
│
├── compute\                      ← lens 3 (compute resources, G12–G13)
│   ├── resources.py              data rate, buffer, capacity
│   ├── checks.py  gate.py  setup.py  cli.py
│
├── sample\                       ← lens 4 (sample geometry & optics, G15–G19)
│   ├── aberration.py             RI mismatch, focal shift, WD budget, overlap
│   ├── checks.py  gate.py  setup.py  cli.py
│
├── photo\                        ← lens 5 (photo-perturbation, G10 · G20–G22)
│   ├── dose.py                   irradiance, bleaching, saturation, total dose
│   ├── checks.py  gate.py  setup.py  cli.py
│
├── trapping\                     ← lens 7 (optical tweezers, G14)
│   ├── laser.py                  laser and beam
│   ├── dynamics.py               trap stiffness, corner frequency
│   ├── goa.py                    generalized optical approach
│   ├── checks.py  gate.py  cli.py
│
├── calibration\                  ← Phase 0 hardware measurement scripts
│   ├── disk_bandwidth.py         sustained disk write bandwidth
│   ├── mm_live.py                camera row time, EM1/EM2 camera identification
│   ├── ram_capture.py            RAM buffer capture
│   └── cli.py
│
├── hardware\                     ← off-ledger device control
│   ├── optical_tweezers.py
│   ├── piezo_stage.py
│   └── piezo\vendor\             vendor DLL + adapter
│
├── data\                         ← registries (filled in by hand)
│   ├── fluorophores.yaml         dyes
│   ├── filters.yaml              filters · dichroics · ND · polarizers
│   ├── light_sources.yaml        source lines + measured power at sample
│   ├── detectors.yaml            cameras
│   ├── objectives.yaml           the nosepiece — NA · immersion · WD · coverslip
│   └── spectra\                  measured curves (vendor txt/csv)
│
├── config\
│   ├── channels\                 channel configuration examples
│   └── scopes\                   system profiles
│
├── kb\                           ← knowledge base
│   ├── systems\current.md        current system dossier
│   ├── calibrations\             measured calibrations
│   ├── decisions\                past recommendations + outcomes
│   └── expertise\                expertise captured from conversation
│
├── reference\
│   ├── observed-systems.md       ⚠ old-setup inventory (not the current system)
│   └── quotes\                   purchase quotes
│
├── manual\                       vendor manuals (DMD · optical tweezers · piezo stage)
└── tests\
```

---

## 6. What actually works today

The four computational lenses (1 · 2 · 3 · 7) are implemented, and they
**refuse** as intended.

```bash
python -m optics.cli check config/channels/legacy-observed.yaml
```

Feed in the old setup as-is:

```
channel: 647-Cy5 (as observed)   dye: SA647   ->  BLOCKED - insufficient information

  [FAIL] missing.filter_spec
         Element 'DA/FI/TR10Empty' has no passband on record
      -> Add it to data/filters.yaml with its part number and passband

  [FAIL] missing.filter_spec
         Element 'Wheel-A:Filter-0' has no passband on record
```

Feed in a two-channel proposal with the specs filled in and real numbers come
out; if approximations are mixed in, it is caught as `advances: NO`:

```
excitation efficiency   36.8%      spectral collection   21.1%
geometric collection    35.2%      total collection       7.4%
excitation blocking     11.5 OD    Stokes headroom       25 nm
Rayleigh resolution      281 nm    depth of field       483 nm

[WARN] emission.peak_clipped
       Detection band starts at 672 nm — past the ATTO647N emission peak
       (669 nm). You are discarding the brightest part.

element ablation
  candidate  FF01-640/14      signal +104%  based on approximate spectra, so
                                            not an instruction until confirmed
                                            on the bench
  required   FF01-692/40      signal  +43%  removing it drops blocking to 5.6 OD
  required   Di03-R405/...    signal   +0%  structural element
```

`ablation` is this lens's key capability. **It answers "what happens if I remove
this filter" by actually removing the term from the product and recomputing,
not by guessing.** If signal rises while blocking and crosstalk still hold, it
proposes removal; otherwise it explains in numbers why the element is needed.

---

## 7. What comes next

1. **Judgment lenses 4 · 5 · 6** — agent definitions are drafted in
   `.claude/agents/`; they still need to be wired into committee orchestration
2. **Lens 8 (mechanical & environmental)** — not started
3. **L1 indexer** — the 2,343 archived acquisitions → SQLite
4. **Agent layer** — `CLAUDE.md` + skills + committee orchestration

What is blocking progress is mostly **facts, not code**: the gates run but
return `BLOCKED` for want of measured inputs, illumination power above all.
→ [Phase 0](07-roadmap.md)
