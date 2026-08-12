# 09 · Expertise capture

> **Status: sketch.**

## 0. The real purpose of this project

> "Rather than explaining my expertise about my instruments and experiments to
> each junior one at a time, I want to build an agent that carries my level of
> knowledge, so it can be used more easily and more generally."

So this system is **not a settings calculator but an expertise transplant
device**. The computational gates are half of it; the other half is **knowledge
that no computation produces**.

```
What computation gives           What computation does not
─────────────────────────        ──────────────────────────────────────────────
transmission, SNR, sampling      this sample changes composition 30 min after prep
trap stiffness, data rate        this dye adsorbs non-specifically at this interface
diffraction limit,               a 647 exposure that reached 500 ms means the light
photon budget                        level was insufficient
                                 this objective is unusable past 20 µm unless the
                                     correction collar is set
                                 sample preparation is 80% of this experiment
```

Everything on the right lives only in the user's head. It is in no datasheet and
no paper. **Extracting it from conversation and storing it is the subject of this
document.**

---

## 1. The source and standing of knowledge

Every KB entry carries its source. The source sets its trustworthiness and **how
it can be refuted**.

| Source | Trust | How to refute | Example |
|---|---|---|---|
| `measurement` | highest | re-measure | measured mW from a power meter |
| `datasheet` | high | check the part number | filter transmission curve |
| `calculation` | as good as its inputs | validate the inputs | collection efficiency 0.352 |
| `expert-judgment` | valid until falsified | observe the falsifying condition | "this sample changes within 30 minutes" |
| `literature` | citation required | check the original | Savin-Doyle blur correction |
| `precedent` | weak | the physics gates | "we used 80 ms last time" |

**`precedent` is the weakest.** That it was done that way in the past does not
mean it was right.
→ [06 §E1](06-pitfalls.md)

---

## 2. Entry format

`kb/expertise/<id>.md`

```yaml
---
id: 647-exposure-500ms-means-underpowered
question: "What does it mean that the 647 channel exposure climbed to 500 ms"
source: expert-judgment
expert: KH
date: 2026-08-08
confidence: high
scope: "Lumencor Spectra X Red line, 100x oil, 647-family dyes"
applies_to_systems: [legacy-nikon-prime95b]   # state it if system-dependent
review_after: 2027-08-08
supersedes: null
---

## Judgment
That the 647 channel exposures pile up at 500 ms means this is not an optimized
value but **a value pinned against a ceiling**. Read it as a signal that the
light level was insufficient.

## Why  ← without this it does not get stored
· 764 acquisitions pile up at 500 ms with no distribution above it = a limit, not
  a human choice
· at that setting nothing faster than 2 Hz is possible, so time resolution is
  sacrificed
· the 488 channel spreads widely across 5–2000 ms = only 647 was peculiarly
  blocked

## Scope
· when exciting 647-family dyes with Spectra X Red (640 nm)
· does not carry over to other light sources or other dyes

## Falsifying condition  ← what observation would make this judgment wrong
· if a measurement shows the Red line delivering sufficient mW at the sample
  plane, the cause is not the light level but the emission path (the cube does
  not pass 647)
· → in that case retire this entry and merge it into B1 (filter unknown)

## Related
[[filter-cube-does-not-pass-647]]  [[measure-illumination-power-first]]
```

**`Why` and `Falsifying condition` are mandatory.**

- Without `Why` a junior cannot generalize.
  "Use 80 ms exposure" → applied verbatim to another sample → failure.
  "This sample bleaches fast, so duty has to stay under 30%, and at 12 Hz that is
  80 ms" → generalizes.
- Without a `Falsifying condition`, knowledge **never ages.** It survives an
  instrument change and goes on giving wrong advice.

---

## 3. Three capture paths

### (a) Opportunistic capture — during conversation

When the user states a non-obvious judgment, the agent detects it and proposes
storing it.

Detection signals:
- a causal claim that is not in the data ("because X, Y")
- a conditional rule ("when X, you have to Y")
- a prohibition ("never do X")
- an exception ("usually X, but in this case Y")
- a correction (the user fixing what the agent said) ← **the most valuable**

```
User:  Don't measure actin rheology with phalloidin. It stabilizes the filaments.

Agent: Store this in the KB?
  id:        phalloidin-stabilizes-actin
  judgment:  phalloidin labeling is unsuitable for actin rheology measurement
  why:       stabilizes F-actin → filament length distribution and dynamics
             change = the measured object itself is altered
  scope:     actin rheology. No problem for structural observation
  falsify:   ?  ← what would have to be observed for this judgment to be wrong?
```

That last question is always asked. Only the user can supply a falsifying
condition.

### (b) Gap-driven — the gates build the queue

**This is the most efficient path.**

Every time a gate returns `BLOCKED` or asks a question, that is a KB gap. When
the user answers, store the answer together with **the basis for the judgment**.

```
Gate:   BLOCKED — passband of 'DA/FI/TR10Empty' unknown
Agent:  Do you know what this cube actually is?
User:   Oh, that one is really a quad-band. The label is just old and never got
        updated.
Agent:  → update data/filters.yaml + create a kb/expertise entry
        "MM labels are sometimes not updated after a part is swapped.
         Never take a label as evidence for a part."
```

The second store is the real gain. The part information gets used once;
**the general rule "do not trust the label" keeps getting used.**

### (c) Planned interview — periodic

The agent finds the empty regions of the KB itself and asks.

```
Not yet asked:
· How do you decide chamber thickness? (empty across all of kb/samples)
· What is the useful lifetime of an ATPS sample?
· What signal makes you decide "this data has to be thrown out"?
   ← This one matters most. There is not a single failure criterion in the KB.
```

**"What tells you it failed"** is knowledge only the expert holds, and the last
thing a junior learns. Give it high priority.

---

## 4. When computation and expert judgment conflict

**Computation does not win automatically.**

```
Computation:  SNR 8.2 — sufficient
User:         No, you can't see anything at that setting.
```

The order of operations then:

1. **Suspect the computation's inputs first.** Usually a term is missing.
   In the case above, background fluorescence is not in the model — and indeed in
   the current SNR formula `N_bg` is a user input with no default
2. If the inputs are right and it still disagrees, **the model is inadequate**
3. Either way, **record the conflict itself in the KB**

```yaml
id: atps-background-fluorescence-dominates
source: expert-judgment + calculation-mismatch
---
## Observed mismatch
The photon budget predicted SNR 8.2, but in practice the particles were invisible.
## Cause (hypothesis)
Autofluorescence of the dextran phase itself enters the background. A term absent
from the current model.
## Action
· Add a measured background frame to the acquisition protocol
· Record the background level in kb/samples/atps-dextran-peg.md
· Lens 6: with no measured background, report SNR only as an "upper bound"
```

**The best knowledge comes out at the point of conflict.** So conflicts are not
hidden.

---

## 5. Teaching mode

The same answer is delivered differently depending on who is asking.

| Audience | Output |
|---|---|
| Expert (the user) | Conclusion + numbers. Basis folded away |
| Junior | Conclusion + **why** + source + what to verify |
| Junior (first experiment) | The above + failure signatures + what to ask |

```
Junior: I want to track 647 particles in ATPS — what exposure should I use?

Agent:
  Start at 80 ms. But why that value is what matters.

  ① The system's characteristic time is 50 ms → at least 20 Hz is needed
  ② Motion blur caps duty at 30% → the exposure has to be ≤ 15 ms
  ③ But by the photon budget, 15 ms only gives SNR 2.1

  ② and ③ conflict. 80 ms takes ③ and gives up ②, and that puts a systematic
  bias in the MSD → you must apply the Savin-Doyle correction.

  A better route: switching to 16-bit readout cuts noise 3.4×, so even 15 ms
  gives SNR 7. Try that first.

  Basis: calculation [photon budget detail] · characteristic time
         [kb/samples/atps] · blur correction [Savin & Doyle 2005]
         · expert judgment [[647-exposure-...]]

  Failure signatures: trajectories breaking often means an SNR problem.
                      An MSD slope that bends with lag means blur/drops.
```

**Hand over only the answer and the junior does not grow.** Showing the conflict
and the choice is the point.

---

## 6. Managing staleness

Knowledge spoils. System-dependent knowledge in particular turns dangerous the
moment the instrument changes.

- `review_after` on every entry
- an entry with `applies_to_systems` gets an **automatic re-review flag** when
  the system fingerprint changes
- keep the history through `supersedes` / `superseded_by` — nothing is deleted
  (why the thinking changed is itself knowledge)
- entries sourced from `precedent` are demoted automatically when a physics gate
  refutes them

On a system swap: while writing
`kb/systems/_transitions/<old>-to-<new>.md`, enumerate every expertise entry tied
to that system and rule on each one.
→ [03 §7](03-cross-system-transfer.md)

---

## 7. Rules the agent must follow

1. **Always show it and get confirmation before storing.** Never store an
   arbitrary summary of what the user said
2. **Do not store without a `Why`.** Ask for it
3. **Always ask for the `Falsifying condition`**
4. **Do not mix sources.** Never lump a computed result and an expert judgment
   into one entry
5. **Never put a guess in the KB.** The agent's own inference cannot be a source
   → [01 §3 Principle 1](01-architecture.md)
6. When the user **corrects** the agent, capture it first. A correction is dense
   knowledge
7. **Always link** when citing the KB. No advice without a source

---

## 8. Open questions

- [ ] How often to offer a capture — too often and the conversation breaks up
- [ ] Whether to retain the conversation logs themselves (re-extraction potential
      vs noise)
- [ ] What to do when judgments from different people conflict (the user vs
      another researcher)
- [ ] Whether to let juniors write to the KB — a review procedure seems necessary
- [ ] Whether to absorb the existing protocol documents in
      `D:\experiment method` into the KB
- [ ] How to elicit failure cases — if only successes get recorded the KB is
      biased
