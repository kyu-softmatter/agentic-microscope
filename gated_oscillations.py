"""Three breakpoint-gated oscillations: hold 2 s at +10 um, release, repeat.

Open-loop by necessity. The Tweez TCP interface has no readback of any kind --
measured this session, ``TRAP_PATT_RELEASE_BP`` answers 0 whether or not the
trap was actually waiting -- so nothing here can *observe* the trap reach the
breakpoint. What makes that acceptable is the asymmetry between the two clocks
involved:

  travel   hardware-timed by the AOD trap loop. 50,000 points at 50 kHz is
           1.000 s per cycle and 0.250 s to the breakpoint at index 12,500,
           and those are exact, not nominal.
  release  host-timed, and the only loose end. Each send costs a few ms of
           round trip, so a hold lands within roughly +/-20 ms of 2.000 s.

The breakpoint also absorbs the error that matters most: the trap *waits* there
indefinitely, so being late is a slightly longer hold, not a missed release.
Being early is the failure mode -- a release sent before the trap arrives is,
as of this writing, of unknown effect (remembered or discarded is untested), so
every wait here is computed from the hardware clock rather than guessed.

REQUIRES, and cannot check:
  - the trap's ``Breakpoints > Enable Bits`` covers colBP=1 (0001, not 0000)
  - ``Repeat > Enabled`` is True, with a Count allowing at least 4 passes --
    the 4th is what parks the trap back at +10 um at the end
Both are GUI-only over TCP. Neither is readable from here.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO = Path(r"C:\Users\Takatori lab\Box\Takatori Group\Kyu_Hwan\experimentalist")
sys.path.insert(0, str(REPO))

from hardware.optical_tweezers import (  # noqa: E402
    OpticalTweezers,
    _RETURN_CODES,
)

TRAP = "Trap 1"
PATTERN = "Sine 1Hz BP max"

#: Hardware-timed, from the drive plan: 50,000 points at 50 kHz.
CYCLE_S = 50_000 / 50_000.0
#: Breakpoint sits at index 12,500 -- a quarter of the way round.
TO_BREAKPOINT_S = 12_500 / 50_000.0

HOLD_S = 2.000
N_OSCILLATIONS = 3

#: Busy-wait tail. time.sleep() on Windows resolves to about a millisecond,
#: which is 0.05% of a hold but worth spinning out of the release timing.
_SPIN_S = 0.002


def wait_until(target: float) -> None:
    """Sleep to just short of ``target`` (a time.monotonic() value), then spin."""
    while True:
        remaining = target - time.monotonic()
        if remaining <= 0:
            return
        if remaining > _SPIN_S:
            time.sleep(remaining - _SPIN_S)


def code(status) -> str:
    return f"{status} ({_RETURN_CODES.get(status, 'unknown/unlisted')})"


def main() -> int:
    print(f"  pattern        {PATTERN!r} on trap {TRAP!r}")
    print(f"  cycle          {CYCLE_S:.3f} s   breakpoint at {TO_BREAKPOINT_S:.3f} s")
    print(f"  hold           {HOLD_S:.3f} s x {N_OSCILLATIONS} oscillations\n")

    with OpticalTweezers(host="127.0.0.1", port=2070) as tweez:
        # Re-assigning restarts the traversal, which is what defines t0. If the
        # trap were left halted at the breakpoint from an earlier run, starting
        # from a release instead would make t0 unknowable.
        st = tweez.send_command(f'TRAP_ASSIGN_PATTERN "{TRAP}" "{PATTERN}"')
        t0 = time.monotonic()
        print(f"  t=0.000  assign -> {code(st)}")
        if st != 0:
            print("  ABORT: pattern not assigned, so nothing below would mean "
                  "anything", file=sys.stderr)
            return 1

        for i in range(N_OSCILLATIONS):
            arrive_at = t0 + TO_BREAKPOINT_S + i * (HOLD_S + CYCLE_S)
            release_at = arrive_at + HOLD_S
            wait_until(release_at)

            sent = time.monotonic()
            st = tweez.send_command(f'TRAP_PATT_RELEASE_BP "{TRAP}"')
            done = time.monotonic()

            held = sent - arrive_at
            print(
                f"  t={sent - t0:6.3f}  release #{i + 1} -> {code(st)}"
                f"   held {held:.3f} s (target {HOLD_S:.3f}, "
                f"err {1e3 * (held - HOLD_S):+.1f} ms)"
                f"   round trip {1e3 * (done - sent):.1f} ms"
            )
            if st != 0:
                print(f"  release #{i + 1} was refused -- the run is no longer "
                      "the protocol described above", file=sys.stderr)
                return 1

        park_at = t0 + TO_BREAKPOINT_S + N_OSCILLATIONS * (HOLD_S + CYCLE_S)
        print(f"\n  {N_OSCILLATIONS} oscillations issued. If Repeat allows a "
              f"{N_OSCILLATIONS + 1}th pass the trap parks")
        print(f"  back at +10 um about t={park_at - t0:.3f} s and holds there, "
              "released by nothing.")
        print("  No readback exists: confirm the hold count and the final "
              "position at the GUI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
