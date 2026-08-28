# RUN FIRST — Tweez 300 embedded Python: ask it what its API is

> **Written 2026-08-27 for the next session at the microscope PC.** Self-contained:
> everything needed is on this page. Budget **~25 min** for steps 1-5, plus 5 min
> for step 6 (worth doing regardless of the outcome).
>
> Laser stays **OFF** the whole time. No camera needed. Nothing is written to the
> instrument — every call in `PyTool_ApiDump` is Python introspection or `ReadNode`
> on the tool's own `Report`/`Output` node.

## Why this, before anything else

The Tweez 300 GUI hosts a real CPython 3.9.5 in a separate process,
`Tweez300GUIPython.exe`, and that interpreter can reach the whole Properties panel
— including the three GUI-only properties that gate every pattern drive
(`Breakpoints > Enable Bits`, `Repeat > Enabled`, `Pattern > Wait States`) and
possibly the camera and laser power, neither of which TCP can touch at all.

**There is no document listing that API.** The manual never mentions the `\Python`
folder. Compare: the TCP surface has a vendor-published list of exactly 28
commands (User Manual pp.66-68), and 52 further names were probed and all answered
-11, so TCP is closed and measured. The node API is the opposite — wide open and
completely unmapped.

The last session tried to map it by *guessing 51 node paths* and read **0 of 51**,
including `System.Version`, which cannot be absent. Diagnosis: the node tree is
not up yet when the GUI's init script runs.

**But that failure was about reading node VALUES. It says nothing about the API.**
`dir()` and `inspect` work on the module object, which exists the moment the import
succeeds — and we know the import succeeds, because `PyTool_NodeDump`'s
`from PyToTw300Comm import Tw300Nodes` is a top-level statement, so a failed import
would have killed that script before it wrote anything, and it wrote a dump.

So `Tw300Nodes` is a live object in that process that has never been asked what it
can do. That question needs no waiting, no menu, no reverse engineering. It is the
cheapest unmapped thing left, which is why it goes first.

## What we already know (do not re-derive)

- **TCP, port 2070**: 28 commands, complete and measured. Write-only — the only
  query is `TRAP_STRENGTH "<name>" 1` → `0` exists / `-22` does not.
- **Node paths evidenced by vendor code** — the entire confirmed set, 7 entries:
  `System.Version` · `Traps.Number` · `Traps.Assign Pattern` ·
  `Traps.Remove Pattern` · `Traps.<Trap>.Pattern.Wait States` · `<probe>.Data`
  → `(Time, PrbX, PrbY, TrpX, TrpY)` · `<PyTool>.Report.Add` / `.Report.Show`
- Everything else about the node tree is inference.

Background: [`kb/decisions/2026-08-27-tweezers-first-light-measured-limits.md`](../decisions/2026-08-27-tweezers-first-light-measured-limits.md) §7.

## Paths on that PC

| what | where |
|---|---|
| vendor original (**do not modify** — timestamps still 2022) | `C:\Program Files\Aresis\Tweez300\Python` |
| our redirected copy (this is what the GUI runs from) | `%LOCALAPPDATA%\Aresis\Tweez300\PyPath`<br>= `C:\Users\Takatori lab\AppData\Local\Aresis\Tweez300\PyPath` |
| the env var that points there (**User** scope, no admin needed) | `TW300PYPATH` |
| dump output | `C:\Tweez\`, falling back to `%USERPROFILE%\` |

---

## Step 0 — send the vendor email  (2 min, do it before you sit down)

[`aresis-support-email-draft.md`](aresis-support-email-draft.md) is ready to send to
support@aresis.com. It asks for the node-API documentation directly, which would
make most of what follows unnecessary. Two blanks to fill first: the system serial
(System Manager → Connections box — which also settles our own `SN >= 130`
inference) and the software version from the About dialog.

Independent of everything below, so send it and carry on. A reply days later still
cross-checks whatever the dump finds.

## Step 1 — confirm the redirect is still live  (2 min)

A User-scope env var survives reboots but not a Tweez reinstall, and someone may
have reverted it. Check before assuming.

```powershell
$env:TW300PYPATH
Get-ChildItem $env:TW300PYPATH | Select-Object Name, LastWriteTime
```

Expect the path to be the `AppData\Local` copy, ~14 files, and **fresh `.pyc`
timestamps** (the vendor folder's newest is 2022 — that contrast is the proof the
GUI runs from the copy).

If it points at `C:\Program Files\...`, re-apply the redirect:

```powershell
[Environment]::SetEnvironmentVariable('TW300PYPATH', "$env:LOCALAPPDATA\Aresis\Tweez300\PyPath", 'User')
```

then open a new shell and restart the GUI.

## Step 2 — copy the tool in, dropping the `.reference` suffix  (2 min)

It is stored as `.reference` in the repo so nothing on the Mac tries to import or
collect it. On the PC it must be a real module name.

```powershell
Copy-Item "<repo>\kb\systems\PyTool_ApiDump.py.reference" "$env:TW300PYPATH\PyTool_ApiDump.py"
```

## Step 3 — hook it into the init script  (3 min)

Edit **`$env:TW300PYPATH\ArTw300GUIPythonInit.py`** (the copy, never the vendor
original). `PyTool_NodeDump` is already called there. Add ApiDump **before** it:

```python
from PyTool_ApiDump import ApiDump
ApiDump(None, tag="init", caller_globals=globals())
```

`caller_globals=globals()` matters: the host may inject names straight into the
init script's namespace rather than through a module, and nothing else in the
survey would see those.

**Leave the existing NodeDump call in place.** It is now a control: if ApiDump
succeeds while NodeDump still reads 0/51, that confirms the diagnosis — import
fine, node tree not up — and rules out a broken PyPath.

## Step 4 — restart the GUI, collect the dump  (3 min)

Close the Tweez 300 GUI completely (and System Manager if it stays up), reopen it.
**Laser OFF. No traps, no patterns needed** — introspection does not care.

```powershell
Get-ChildItem C:\Tweez\tw300_apidump_*.txt, "$env:USERPROFILE\tw300_apidump_*.txt" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 3
```

## Step 5 — read it, in this order  (10 min)

The dump has five sections and repeats this order in its own header. It does not
just report — **section 2 probes for an enumerator and section 3 walks the tree
automatically if one answers**, so a successful run gives the node-path list
without a second trip.

| § | what it holds | read it for |
|---|---|---|
| 0 | `sys.modules` split into injected vs stdlib, `sys.path`, builtins/globals diff | a module §7 never named; any module with `__file__` |
| 1 | `Tw300Nodes` in full — `dir()`, per-attribute arity, `pydoc` incl. inherited | **the command list** |
| 2 | read-only call probe, with what was skipped and why | a **CANDIDATE ENUMERATOR** line |
| 3 | breadth-first tree walk, if §2 found one | the real node paths |
| 4 | every other injected module, same treatment | `PyTw300PattGen`, `PyTw300DataManager` |

Priority, because the first can make the rest unnecessary:

1. **Did an enumerator answer (§2 → §3)?** If yes, **`PyTool_NodeDump`'s 51 guessed
   paths are obsolete** — the tree lists itself. Check §3's last line for
   `CAP HIT`: the walk stops at 2000 nodes / depth 6, and a capped walk is *not*
   a complete tree.
2. **Does any injected module report `__file__` (§0)?** §7's "not on disk" was
   inferred from a folder listing; `__file__` is the interpreter's own answer. If
   present, just read the source. If absent, `__loader__` distinguishes frozen
   (source may be recoverable) from built into the host binary (not).
3. **Any call reaching the CAMERA or LASER POWER (§1, §4)?** TCP reaches neither,
   so this API is the only remaining candidate. Camera ownership gates the whole
   Micro-Manager handoff; laser power is currently an acquisition parameter that
   vanishes unless a human writes it down.
4. **An injected module §7 did not name (§0)?** That detection can over-report but
   not under-report. `PyTw300PattGen` deserves its own look — generating patterns
   in-process would remove the write-`.tpf`-then-`LOAD_PATTERN` round trip.

**On arities**: for C-implemented methods `inspect.signature` may raise
`ValueError`, and **that failure is itself informative** — it means a C
implementation without argument-clinic metadata. The tool prints three sources
(`signature`, `__text_signature__`, and `__doc__`, whose first line conventionally
*is* the signature for C extensions), so at least one usually lands.

**What §2 will and will not call.** Allowlisting is per CamelCase *token*, not
substring: some token must be in `SAFE_TOKENS` and none in `DANGER_TOKENS`, with
`laser`/`shutter`/`power`/`beam`/`trap` blocked anywhere in the name. So
`GetChildren`, `NodeList`, `Version`, `GetSettings` are called; `SetNode`,
`WriteNode`, `LaserOn`, `EnableBits`, `BeamSetParams` are not. Token matching is
the point — a substring blocklist rejects `Version` (contains "on") and
`GetSettings` (contains "set"), which is how you fail to find the enumerator.
Everything skipped is listed with its reason, so scan that list too: if the
enumerator was refused, call it by hand.

## Step 6 — snapshot the 14 vendor files while you are there  (5 min, zero risk)

Do this regardless of how step 5 goes. That folder is 168 KB and is the **only
extant documentation of this control surface**; right now the repo has just the two
`PyTool_*.reference` files we wrote ourselves.

```powershell
robocopy "$env:TW300PYPATH" "$env:USERPROFILE\Desktop\tw300-python-snapshot" /E
```

The two `.xml` files matter most: `ArTw300ROIPythonTools.xml` defines the PyTool
contract (menu placement, `DataSource Name="Probe"`, the `Output`/`Report` node
declarations) — which is the answer to the open question of why our tool never
appeared under a right-click, and how to attach one to a tracking ROI.

---

## If it goes wrong

| symptom | meaning | do this |
|---|---|---|
| no dump file anywhere | the init hook never ran, or the GUI swallowed an error before it | check the import line spelling in `ArTw300GUIPythonInit.py`; the tool writes to `%USERPROFILE%` when `C:\Tweez` is not writable |
| dump says `from PyToTw300Comm import Tw300Nodes` **FAILED** | contradicts NodeDump having produced output — suspect the run context, not the module | keep the traceback, it is the finding |
| **GUI will not start at all** | the init script edit broke startup | revert (below), restart, then re-add the two lines one at a time |

**Full revert — one line, then restart the GUI. Nothing else needs undoing:**

```powershell
[Environment]::SetEnvironmentVariable('TW300PYPATH', 'C:\Program Files\Aresis\Tweez300\Python', 'User')
```

## Bring back

- the `tw300_apidump_*.txt` file (paste it in whole — arities and dunders matter)
- the `tw300_nodedump_*.txt` from the same startup, as the control
- the `tw300-python-snapshot` folder from step 6

## If step 5 question 1 comes up empty

Then the API has no enumerator and node path *names* are still unknown. Two
fallbacks, in order:

1. **Deferred NodeDump.** The tree-not-up problem is a *scheduling* problem, and
   §7 wrongly ruled out retrying ("holding the init would hold GUI startup") —
   true of blocking retry only. A daemon thread does not hold startup: poll
   `System.Version` every 2 s until it reads, then dump. ~10 lines added to
   `PyTool_NodeDump`. **Untested risk: the node API may not be thread-safe.** First
   attempt with laser off and no pattern in flight.
2. **`strings` on the binaries**, using the 5 vendor-evidenced names above as the
   oracle that locates the right string table:

   ```powershell
   Get-ChildItem "$env:TW300PYPATH\..\*.exe","$env:TW300PYPATH\..\*.dll" | ForEach-Object { $_.FullName; strings.exe -n 6 $_.FullName | Select-String "Wait States|Assign Pattern|Enable Bits|Release Bits|Data Format" }
   ```

   Heed the NPC-D precedent in [`reference/npcd-command-set.md`](../../reference/npcd-command-set.md): that extraction pulled 178 names
   and was wrong in **both** directions — its regexp could not match a hyphen, so
   whole command families were invisible. **Node paths contain spaces**
   (`Traps.Trap 1.Breakpoints.Enable Bits`), so any narrowed character class will
   shred them exactly the same way. Extraction is a hypothesis generator; confirm
   every name against a live read.
