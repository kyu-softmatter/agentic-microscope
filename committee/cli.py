"""Read out what the committee can emit, and who is listening.

    python -m committee.cli emissions            # every code, every lens
    python -m committee.cli emissions --lens sample
    python -m committee.cli reconcile            # vs lens 6's bias registries
    python -m committee.cli invisible            # computed, then not printed
    python -m committee.cli parser               # what the parser could not read

``reconcile`` is the one to run after adding or removing a gate. It replaces a
hand-written snapshot that was wrong by two the first time it was counted, and
by one more the first time this layer checked it.

Exit codes: `reconcile` returns 1 when either direction is non-empty, so it can
be wired into a check later. It is **not** wired into the test suite as a
failure today: the drift is known, deliberate, and tracked
(kb/decisions/2026-09-11-the-emission-collection-layer.md).
"""

from __future__ import annotations

import argparse
import sys

from .emissions import (
    LENSES,
    collect,
    collect_all,
    invisible_computations,
    reconcile_bias_registry,
    unparsed_sites,
)


def cmd_emissions(args: argparse.Namespace) -> int:
    lenses = (args.lens,) if args.lens else LENSES
    print(f"\n{'addr':7} {'lens':10} {'emitted code':34} {'kind':5} {'sev':5} vis ledger")
    print("-" * 86)
    n = 0
    for lens in lenses:
        for s in collect(lens):
            n += 1
            print(
                f"{s.address or '--':7} {s.lens:10} {s.emitted_code:34} "
                f"{s.kind:5} {s.severity:5} "
                f"{'y' if s.visible else ' ':3} {'y' if s.reaches_bias_ledger else ''}"
            )
    print(f"\n{n} emission sites")
    print(
        "  vis    = reaches Verdict.findings (severity != 'ok'); the rest live\n"
        "           only in `metrics`, which no CLI prints\n"
        "  ledger = validity's bias ledger would collect it: BIAS by the\n"
        "           RESULT's kind, visible, and not from validity itself"
    )
    return 0


def cmd_reconcile(args: argparse.Namespace) -> int:
    r = reconcile_bias_registry()
    print("\nbias codes: emitted vs registered in validity.setup\n")
    print(r.summary())
    print(
        "\n  registered, not emitted -> a declaration naming one matches nothing;\n"
        "                             it neither clears a bias nor reads as a\n"
        "                             false claim, and nobody is told\n"
        "  emitted, not registered -> accepted, because refusing an unknown code\n"
        "                             would block work on gates the tables have\n"
        "                             not caught up with -- but it pins the\n"
        "                             verdict's `evidence` to `assumed`\n"
    )
    return 0 if r.clean else 1


def cmd_invisible(args: argparse.Namespace) -> int:
    sites = invisible_computations()
    print(f"\n{len(sites)} sites compute a result and put it where nothing prints it")
    print("(severity 'ok', which every gate.py drops from findings)\n")
    print(f"{'addr':7} {'lens':10} {'emitted code':34} kind")
    print("-" * 66)
    for s in sites:
        print(f"{s.address or '--':7} {s.lens:10} {s.emitted_code:34} {s.kind}")
    print(
        "\nNot all of these are defects. The line drawn 2026-09-11: a pass that\n"
        "rests on 'this does not apply to you' is a DECISION and must be visible;\n"
        "a pass that rests on 'you have it' is a FACT and may stay silent.\n"
        "This lists the candidates; it does not judge them.\n"
    )
    return 0


def cmd_parser(args: argparse.Namespace) -> int:
    bad = {lens: unparsed_sites(lens) for lens in LENSES}
    bad = {k: v for k, v in bad.items() if v}
    if not bad:
        print(
            f"\nevery construction site in all {len(LENSES)} lenses parsed "
            f"({len(collect_all())} emission sites).\n"
        )
        return 0
    print("\n⚠ UNPARSED SITES -- this layer is blind at these lines, which means\n"
          "it may claim a code cannot be emitted when it can:\n")
    for lens, rows in bad.items():
        for line, why in rows:
            print(f"  {lens}/checks.py:{line}  {why}")
    print()
    return 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="committee", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("emissions", help="every code every lens can emit")
    e.add_argument("--lens", choices=LENSES, default=None)
    e.set_defaults(func=cmd_emissions)

    r = sub.add_parser("reconcile", help="emitted bias codes vs lens 6's registries")
    r.set_defaults(func=cmd_reconcile)

    i = sub.add_parser("invisible", help="results computed and never printed")
    i.set_defaults(func=cmd_invisible)

    q = sub.add_parser("parser", help="construction sites the parser could not read")
    q.set_defaults(func=cmd_parser)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
