"""Name the LUN-F DAC word format: which of the nine candidate framings is real.

`config/lunf/probe_lunf.py spi-modulate` established that at least one of nine
framings addressing DAC index 2 actually drives 561 -- the line flickered 5 V to
0 V with its blanking held open. This narrows nine to one.

HOW A ROUND WORKS
-----------------
The data = 0 burst is a free reset: it puts 561 at zero on demand, with no NIS
restart between rounds. So each round is

    1. all nine candidates at DATA = 0        -> 561 dark
    2. the selected subset at DATA = --high   -> lit, if the real one is in it
    3. blink 561 and look                     <- the test
    4. all nine at DATA = --high              -> must be lit
    5. blink 561 and look                     <- the CONTROL

Step 4-5 is the part worth insisting on. Without it a dark result at step 3 is
ambiguous: it could mean "the real framing is not in this subset", or it could
mean the fiber shutter closed, or NIS took the FT4222 back, or the laser is off.
Those failures are silent and they would make every round read as a clean
negative. If the control is dark the round is void, and the script says so.

FOUR ROUNDS, BINARY-CODED
-------------------------
Rather than halving, each round tests the indices with one bit set. The pattern
of lit/dark across four rounds spells the answer in binary:

    round 0 -> bit 0    indices 1 3 5 7
    round 1 -> bit 1    indices 2 3 6 7
    round 2 -> bit 2    indices 4 5 6 7
    round 3 -> bit 3    index   8

Then confirm the winner alone with --only, because these rounds send several
frames at once and a frame meant for one chip can be partial nonsense to
another.

    python config/lunf/bisect_dac.py --round 0
    python config/lunf/bisect_dac.py --only 3        # confirm a single candidate
    python config/lunf/bisect_dac.py --list
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_lunf import (  # noqa: E402
    WL, OPEN, CLOSED, FULL_SCALE_V, Daq, Spi, builders,
)

NM = "561"
ADDR = WL[NM][1]
LINE = WL[NM][0]


def blink(daq: Daq, n: int, period: float, label: str) -> None:
    print(f"    {label}: blinking {n}x", flush=True)
    for _ in range(n):
        daq.write_line(LINE, OPEN)
        time.sleep(period)
        daq.write_line(LINE, CLOSED)
        time.sleep(period)


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--round", type=int, choices=(0, 1, 2, 3),
                   help="binary-coded round; the bit it resolves")
    g.add_argument("--only", type=str, help="comma-separated candidate indices")
    g.add_argument("--list", action="store_true", help="print the candidates and exit")
    ap.add_argument("--high", type=float, default=5.0)
    ap.add_argument("--blinks", type=int, default=3)
    ap.add_argument("--period", type=float, default=0.5)
    a = ap.parse_args()

    cands = builders(ADDR)
    if a.list:
        for i, (lbl, b) in enumerate(cands):
            print(f"  [{i}] {lbl:22} 0V={b(0.0).hex(' '):14} 5V={b(1.0).hex(' ')}")
        return 0

    if a.only:
        sel = sorted({int(x) for x in a.only.split(",")})
        what = f"--only {a.only}"
    else:
        sel = [i for i in range(len(cands)) if i >> a.round & 1]
        what = f"round {a.round} (bit {a.round})"
    bad = [i for i in sel if i >= len(cands)]
    if bad:
        print(f"!! no such candidate index: {bad} (have 0..{len(cands)-1})")
        return 2

    f_hi = a.high / FULL_SCALE_V
    print(f"{what}  ->  candidates {sel}")
    for i in sel:
        print(f"    [{i}] {cands[i][0]:22} {cands[i][1](f_hi).hex(' ')}")
    print()

    daq = Daq()
    try:
        with Spi() as spi:
            print("  reset: all nine at DATA = 0")
            for _, b in cands:
                spi.write(b(0.0))
            time.sleep(0.3)

            print(f"  TEST: raising {sel} to {a.high} V")
            for i in sel:
                spi.write(cands[i][1](f_hi))
            time.sleep(0.3)
            blink(daq, a.blinks, a.period, "TEST")

            print("\n  --- 3 s dark gap: everything after this is the CONTROL ---",
                  flush=True)
            for _, b in cands:
                spi.write(b(0.0))
            time.sleep(3.0)

            print(f"  CONTROL: all nine at {a.high} V (this one MUST be lit)")
            for _, b in cands:
                spi.write(b(f_hi))
            time.sleep(0.3)
            blink(daq, a.blinks, a.period, "CONTROL")

            for _, b in cands:
                spi.write(b(0.0))
    finally:
        daq.close_all()
        print("\n  DAC left at 0 V, all blanking CLOSED")

    print(f"""
Two answers, in order:

  CONTROL dark  -> the round is VOID. The shutter closed, or NIS took the
                   FT4222 back, or the laser is off. Fix that and re-run;
                   do not read anything into the TEST result.
  CONTROL lit   -> the round counts. Then:
                     TEST lit   -> the real framing IS in {sel}
                     TEST dark  -> it is NOT
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
