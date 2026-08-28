# RUN FIRST — NPC-D piezo: ask it for its whole command set, at super-user

> **Written 2026-08-27 for the session at the microscope PC on 2026-08-28.**
> Self-contained: everything needed is on this page. Budget **~20 min** for steps
> 1–5, plus 5 min for step 6.
>
> **Nothing moves.** Every script here constructs `PiezoStage` without
> `allow_motion`, so the position setters and `function_start()` raise. No command
> is executed at all beyond reading the level, raising it, and reading firmware.
> Safe with a sample in place and in focus.
>
> Sibling of [`PyTool-RUN-FIRST.md`](PyTool-RUN-FIRST.md), which does the same job
> for the tweezers' embedded Python. Same design rule: one run answers "what else
> is there", so a second trip is not needed.

## Why this

The security level decides what *exists* on this controller, and the repo has only
ever reached **User**. At the base level it reports 188 commands; at User, 414. The
level is the single biggest lever on this interface and there is one more notch on
it that has never been tried.

`piezo_stage.ACCESS_CODES` carries `super-user = 0xB01DFACE`, read out of the
vendor GUI's own config file (`C:/Program Files (x86)/NanoBench 6000/data/config.ini`,
section `[SecurityLevels]`). **It has never been sent.** So:

- What super-user exposes is unknown.
- And one claim this repo states as fact may be wrong because of it.
  [`reference/npcd-command-set.md`](../../reference/npcd-command-set.md) says
  `fpga.*`, `peek.*`, `system.*`, `stage.command.digital.scaling.*` and
  `identity.software.fpga.version.get` "answer *Invalid command name* on this
  controller. They belong to other models, or to a service interface." But **a
  gated command answers exactly the same way** — that is the whole lesson of §2
  of [`kb/decisions/2026-08-27-piezo-first-light-measured-limits.md`](../decisions/2026-08-27-piezo-first-light-measured-limits.md),
  where `stage.position.command.set` was *invisible* rather than absent and read
  like "this controller cannot command a position". If those names appear at
  super-user, they were gated, and the reference file needs correcting.

Second reason, independent of the level: **the descriptions exist nowhere else.**
The vendor's command-set manual is not in this repo. The DLL will report a
description, a parameter list and a result list per command, and nothing has ever
captured all 414.

## What we already know (do not re-derive)

- **Link string** is the bare port: `COM4`. Not `com:/COM4`, not `COM4:`.
  `list_devices()` answers `[]` — the port is named, never discovered.
- **The port is exclusive.** With the NanoBench 6000 GUI holding a session,
  `connect()` fails with "could not open comms link to 'COM4'" — the same message
  a bad link string gives. Close its session first.
- **The `0x` prefix is required.** `DEC0DED` → "Not enough parameters for
  command"; `0xDEC0DED` → `security = User`.
- **The level outlives the session.** It is controller-side state and the vendor
  GUI leaves it raised, so an unlock reporting "nothing new became visible" may
  mean *already unlocked*, not *code rejected*. Both scripts here restore the
  level they found on the way out.
- **The DLL's four unit getters access-violate** (buffer length dereferenced as a
  pointer). `with_units=False` throughout; units are not obtainable from this API
  in either failure mode. Positions are picometres, established by arithmetic:
  `calibrated-range.maximum` = 6.0e8 on a stage part-numbered SP-XYZ-600.
- Travel **0–600 µm on all three axes**; command grid **32 pm**; servo **20 µs**.
- Channels are 1-based: **1=x, 2=y, 3=z**.

## Step 1 — close the vendor GUI, confirm the port  (2 min)

```powershell
Get-CimInstance Win32_SerialPort | Select-Object DeviceID, Description
```

Expect `COM4`. If the NanoBench 6000 GUI is open, close its session (or the whole
app). Note whether it was open — that predicts the level found in step 3.

## Step 2 — dry run against the DLL simulator first  (2 min)

Proves the script and the DLL load before anything touches the real controller.

```bash
python config/piezo/dump_command_set.py --link "sim:/NPC6330" --no-describe
```

The simulator reports its own reduced command set and its own level; the point is
that the script completes and writes a file, not what it says.

## Step 3 — the real sweep  (5 min)

```bash
python config/piezo/dump_command_set.py --link COM4
```

That is the whole run: it climbs **as-found → user → super-user**, keeps the diff
at each step, re-asks the claimed-absent names at every level, dumps every
description and signature at the highest level reached, diffs the result against
`reference/npcd-command-set.md`, and restores the level it found. Output lands in
`data/piezo/npcd_command_set_<timestamp>.txt` (falls back to `%USERPROFILE%`).

Sections, in the order the file prints them:

| § | what it holds | read it for |
|---|---|---|
| 0 | DLL version, devices, channels, firmware, level on entry | was the GUI holding the level up? |
| 1 | what the reference file expects | the baseline being tested |
| 2 | **the level climb, with per-family diffs** | **what super-user exposes** |
| 3 | every description + parameter/result names | the manual we do not have |
| 4 | the claimed-absent names, asked at every level | gated vs genuinely absent |
| 5 | diff against `reference/npcd-command-set.md` | what to add to the file |
| 6 | what to do with the file | — |

If `0xB01DFACE` is refused, §2 records the controller's exact words and the climb
continues rather than aborting. That is a result, not a failed run.

## Step 4 — read §2 and §4 first, in this order  (5 min)

1. **Did the level actually rise?** §2 prints the level before and after each
   code. `IDENTICAL to the previous level` means the code changed nothing —
   check §0's level-on-entry before blaming the code, because the GUI leaves it
   raised and "already in force" is the common case.
2. **Did anything in §4 flip from `absent/gated` to `PRESENT`?** If yes, the
   reference file's "names that do not exist here" paragraph is wrong and the
   repo has been treating a permission problem as a hardware fact. This is the
   finding with the longest reach — it is the same mistake as the one already on
   record for `stage.position.command.set`.
3. **What kind of commands appeared?** A `peek.*`/`fpga.*` family is a service
   interface — reads into controller memory. Anything named `.set` at that level
   deserves reading before it is ever called; a service-level setter can change
   calibration, and `stage.calibration.preset.*` is how this stage knows what
   600 µm means.
4. **Did anything DISAPPEAR?** §2 reports that separately. No reading of the
   security model predicts it; record it verbatim if it happens.

## Step 5 — the interactive follow-up, if §2 found something  (5 min)

`dump_command_set.py` is the sweep. For chasing one family by hand:

```bash
python config/piezo/verify_piezo_commands.py --link COM4 --unlock super-user --describe all --out piezo-superuser.txt
```

`--unlock` takes a level name (`user`, `super-user`) or a raw code. `--describe`
takes a family or `all`. It restores the level on exit too, unless
`--leave-unlocked`.

## Step 6 — while you are there  (5 min, nothing moves)

```bash
python config/piezo/verify_piezo_commands.py --link COM4 --hazard
```

Re-reads the analogue-vs-digital command path. Answered 2026-08-27 —
`digital-command 1`, `analogue-command 0` on all three channels — but the mode
word is writable at User level (`stage.mode-mask.set`, `stage.mode-only.set`), so
it is worth confirming it has not moved. **Keep `NIDAQAO-Dev1/ao2` out of every
Micro-Manager configuration regardless:** MM writes 0 V on initialize, and 0 V is
0 µm on a path that is inert only as long as the mode says so.

---

## If it goes wrong

| symptom | meaning | do this |
|---|---|---|
| `could not open 'COM4'` | the GUI holds the port, **or** the link string is wrong — same message | close the NanoBench session; verify with `--link "sim:/NPC6330"`, which works even when the port is held |
| `FAILED to load the controller DLL` | wrong machine, or a 32/64-bit mismatch | this path is Windows-only; `hardware/piezo_stage.py` picks the DLL by `ctypes.sizeof(c_voidp)` |
| unlock answers "Not enough parameters for command" | the `0x` prefix was dropped | send `0xB01DFACE`, not `B01DFACE` |
| `OSError: access violation` mid-sweep | the DLL's string getters | expected and contained: every probe is wrapped, the failure is printed in place and the sweep continues |
| the level is left raised | the run died before its `finally` | `python -c "from hardware.piezo_stage import PiezoStage; s=PiezoStage(); s.connect('COM4'); s.lock(); print(s.security_level()); s.disconnect(); s.close()"` |

## Bring back

- `data/piezo/npcd_command_set_*.txt` — **paste it in whole.** 400+ descriptions
  are the deliverable; a summary is not.
- the level reported in §0 (was the GUI holding it up?)
- whether the GUI had been open before the run, which decides how §2 reads

## What this run will NOT answer

Two things need a *drive*, not a description, so they are out of scope here and
neither is blocked by the other:

1. **`piezo_stage.WAVEFORM_DATA_UNITS`.** The generator does not read its samples
   in picometres — a ±5 µm sine uploaded as picometres swung the axis 314 µm.
   `config/piezo/settle_waveform_units.py` is the bounded experiment (a constant
   waveform, lateral axis only, channel 3 refused outright). **That one moves the
   stage, and by an amount that is the unknown being measured.** Do not fold it
   into this session without reading its SAFETY block.
2. **The trigger plumbing** — `function.trigger-inputs.*`,
   `function.trigger-output.*`, `controller.synchronisation.master`/`slave`. All
   present in the command set; none exercised. This is what would start the piezo
   and the camera off one edge, and §3 will finally give their signatures — which
   is the input to designing that, not the test of it.
