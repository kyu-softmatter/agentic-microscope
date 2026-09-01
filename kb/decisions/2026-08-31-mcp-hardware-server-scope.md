# 2026-08-31 · An MCP server over the hardware paths, and what it deliberately does not expose

> **Decided by the user**: hardware first, tweezers and piezo only — *"두개가
> 되면 나머지도 다 될거니까"* (get these two and the rest all follow). The
> recommendation on the table was the opposite: expose the eight committee lenses
> read-only and no hardware at all, on the grounds that
> [07 Phase 5](../../docs/07-roadmap.md#phase-5--automating-microscope-operation)
> says not to start automating operation before Phases 0–3 are finished. That
> recommendation was made once and overruled; this note records the decision and
> what was done to make it defensible rather than re-arguing it.
>
> Built the same day: `mcp_server/`, 9 tools, 30 tests.

## Request

Build a minimal MCP server. Hardware side, two subsystems: the Aresis Tweez 300
optical tweezers and the Prior/Queensgate NPC-D piezo stage.

## Why those two are the right two

Not because they are the easiest — they are the hardest, and that is the reason.

Every device registered in Micro-Manager already has an abstraction:
pymmcore-plus, and `hardware/microscope.py` on top of it with `allow_write` /
`allow_motion` / `allow_laser` already in place. The tweezers and the piezo are
the two subsystems with no abstraction at all — a 28-command TCP surface and a
vendor DLL, one bespoke translator each. If an MCP tool surface can be put over
those two honestly, the Micro-Manager path is a smaller version of the same job.

It also happens to be the direction
[`docs/mhs-integration.md`](../../docs/mhs-integration.md) reasons about. MHS
reaches devices over MCP, so a working MCP surface here is the same work whether
or not that standard is ever adopted. The gates are unaffected either way; they
sit above any transport.

## What was built

`mcp_server/`, 9 tools in three tiers, and every tool declares its tier in its
MCP annotations rather than in prose only.

| Tier | Tools | Touches |
|---|---|---|
| plan | `tweezers_plan` · `tweezers_command_sequence` · `piezo_waveform_preview` · `piezo_reference_commands` | nothing |
| write | `tweezers_write_tpf` | a file |
| read | `tweezers_probe` · `piezo_read_state` | the device, reads only |
| move | `tweezers_run` · `piezo_move` | the laser, the stage |

Nothing in the plan tier recomputes anything. Each calls
`hardware.tweezers_drive.plan`, `hardware.tweezers_patterns` or
`hardware.piezo_waveform` — the same entry points `config/tweezers/run_pattern.py`
and `config/piezo/verify_piezo_commands.py` call — and returns what they
returned. A tool and a script that disagree is therefore a bug, and
`tests/test_mcp_server.py` compares them field by field.

## The three findings worth keeping

### 1. `hardware/optical_tweezers.py` has no safety switch, and the other two drivers do

`hardware/microscope.py` gates writes behind three switches, all default off, and
`hardware/piezo_stage.py` gates motion behind `allow_motion`. The tweezers driver
gates nothing: its constructor opens the socket and all 28 commands, `laser_on()`
included, are directly callable. First light armed the laser on a typed
confirmation *in the calling script*, which is why the gap never showed.

Under an MCP server the caller is a language model, so `mcp_server/switches.py`
is the only brake in the tweezers path today. It checks **both**
`allow_motion` and `allow_laser` before a drive, and a test asserts the driver is
never even constructed while either is off.

**This is worth closing in the driver instead**, which is where MHS puts device
safety limits and where the other two drivers already put them. It was not done
here because it changes six call sites (`config/tweezers/run_pattern.py`,
`config/session/measure_latency.py`, `config/session/run_parallel.py`,
`gated_oscillations.py`, `try_hardware.py`, and the driver's own
`find_gui_port`), and that is a change to make deliberately rather than as a side
effect of adding a server. Open item, not an oversight.

### 2. A refusal has to be a value, not an exception

This is the one design decision in the server that is not inherited from the
drivers. An MCP tool that raises reads to the calling model as *this tool is
broken*, and a model that believes a tool is broken routes around it — which is
precisely the failure this repository exists to prevent. So:

- `advances: false` with `blockers` — the plan is not ready. The shipped spec
  `config/tweezers/active-microrheology-drive.yaml` returns three blockers, and
  the tool descriptions say in as many words that this is a valid result.
- `check: REFUSED` with the driver's own reason — a waveform the controller would
  clip.
- `refused: true` with `switch` and `how_to_enable` — a safety switch is off.
- `available: false` — the vendor DLL is not installed on this machine.

Every refusal carries **what would have happened**: the exact TCP command lines,
or the exact target position. A refusal that does not say what it refused is a
dead end, which is the same rule the gates follow.

### 3. Two brakes, and they are about different things

`tweezers_run` refuses twice, and the order matters. The switches are about
*permission* — is this machine allowed to move things at all. `advances` is about
*the plan* — is this particular drive ready. Passing the first does not bypass
the second, and a test asserts that with both switches on and a plan that does
not advance, the driver is still never constructed.

## What is deliberately not exposed

**The eight committee lenses.** The other half of an MCP surface for this
repository, and a larger job: each lens's CLI would have to grow a `--json` — two
of eight have one — and hand its `argparse` parser over as the tool schema so the
two cannot drift. Worth doing; not this.

**Two of the tweezers' three control surfaces.** First light
(`2026-08-27-tweezers-first-light-measured-limits.md`) established that TCP is
one of three, and that `Breakpoints > Enable Bits`, `Repeat > Enabled` and laser
power live only on the GUI surfaces. So a plan `tweezers_run` accepts is still
not a drive that runs unattended, and the server does not imply otherwise.

**Anything that could raise the piezo's security level.** `piezo_read_state`
constructs the stage with `allow_motion=False` regardless of this server's
switches, and a test asserts that.

## Verified, and how far

Nine tools exercised through the MCP layer on the working PC, which is not the
microscope PC:

- `tweezers_plan` on the shipped spec returns the same numbers
  `config/tweezers/run_pattern.py --plan` prints — 2,000 points, 12,695.5 µm/s
  native against a 30 µm/s target, `wait_states` chosen, range `BLOCKED`,
  `advances: NO` with three blockers.
- `tweezers_command_sequence` returns the six TCP lines verbatim; `tweezers_run`
  refuses on `allow_motion` and keeps all six.
- `piezo_waveform_preview` passes a ±5 µm sine and refuses a ±5000 µm one with
  the driver's own message.
- `piezo_reference_commands` reads all 414 recorded names.
- `piezo_read_state` returns `available: false` with the DLL's absence explained,
  which is the correct answer here.

**Not verified**: no tool has reached a device. The vendor DLL is not on this
machine and the Tweez GUI is not listening on it, so the two read tools and the
two move tools have been exercised only along their refusal and unavailable
paths. `sim:/NPC6330` — the DLL's own simulator — is the way to close half of
that without a stage under the objective, and it needs the DLL, so it needs the
microscope PC.

## Falsification conditions

1. Run `piezo_read_state` on the microscope PC against `sim:/NPC6330` and then
   against COM4. If the returned identity, channels and travel do not match what
   `config/piezo/verify_piezo_commands.py` prints, the tool is not the thin
   wrapper it claims to be.
2. Run `tweezers_probe` on the microscope PC with the GUI live. `reachable: true`
   with a status is the whole claim.
3. Set `AGENTIC_MICROSCOPE_ALLOW_MOTION=1` with the piezo on `sim:` and confirm
   `piezo_move` moves the simulated axis and reads it back. That exercises the
   only path with no test coverage, on a device that cannot be damaged.
