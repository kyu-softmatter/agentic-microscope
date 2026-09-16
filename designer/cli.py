"""The designer's command line: a brief in, a verdict or two plan files out.

    python -m designer.cli run     config/briefs/active-microrheology.yaml
    python -m designer.cli packets config/briefs/x.yaml --out <dir>
    python -m designer.cli emit    config/briefs/x.yaml --id <slug> \\
        --question "..." --out <dir> [--judgment <verdict.yaml> ...]

`run` prints and writes nothing. `emit` writes both halves of the plan and
then **validates the `.md` it just wrote with `knowledge.plans.check_plan`** --
the same check `python -m knowledge.cli plan-check` runs, called on the output
rather than trusted to be run later. A shape a hardware skill would misread is
caught here, in the process that produced it.

There is no default output directory, and `kb/plans/` is not one. `kb/` is
indexed: writing there also means running `python -m knowledge.cli write` and
reviewing the entry, which is a decision and not a side effect of a CLI
invocation (§6).

STAGE 2 IS TWO COMMANDS AND A CONVERSATION IN BETWEEN. `packets` writes what
each judgment lens is to be handed; the **main agent** convenes the four
agents in `.claude/agents/`, because nothing in this process can; `emit
--judgment` reads their verdicts back, refuses the ones that are not reviews,
and fills in the rows a stage-1 plan leaves as holes. The middle step is not
automatable from here, and the seam is shaped so that nothing has to pretend
otherwise.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import brief as brief_mod
from . import emit as emit_mod
from . import run as run_mod
from .emit import LENS_NUMBER


def _print_result(result: run_mod.Result) -> None:
    print(f"brief: {result.brief.path}")
    print(f"goal:  {result.brief.intended_quantity}")
    print()
    #: The same state the plan's `unevaluated` block gives each lens, so this
    #: printout and the emitted file cannot disagree about one run.
    states = {row["lens"]: row["state"] for row in result.unevaluated}
    print(f"{'lens':12} {'state':18} {'status':12} {'evid':9} deciding")
    print("-" * 72)
    for lens in LENS_NUMBER:
        run = result.runs.get(lens)
        if run is not None and run.ran:
            v = run.verdict
            print(
                f"{lens:12} {result.seats[lens].state:18} {v.status:12} "
                f"{v.evidence:9} {v.bottleneck or '--'}"
            )
        elif run is not None and run.not_constructible is not None:
            nc = run.not_constructible
            print(
                f"{lens:12} {'not_constructible':18} {'--':12} {'--':9} "
                f"needs {', '.join(nc.missing)}"
            )
        else:
            print(
                f"{lens:12} {states.get(lens, 'unevaluated'):18} {'--':12} "
                f"{'--':9} {result.seats[lens].why}"
            )

    if result.stopped_after:
        print()
        print(f"STOPPED after {result.stopped_after}: {result.stop_reason}")

    print()
    print(f"unevaluated ({len(result.unevaluated)}) -- a hole, not a pass:")
    for row in result.unevaluated:
        print(f"  {row['lens']:12} {row['state']:18} {row['why']}")

    unresolved = result.unresolved
    surprises = [r for r in unresolved if not r["predicted_by_brief"]]
    print()
    print(f"unresolved ({len(unresolved)}), of which {len(surprises)} the brief "
          "did not predict:")
    for row in unresolved:
        mark = " " if row["predicted_by_brief"] else "!"
        print(f" {mark} {row['rank']:9} {row['field']:44} {row.get('action') or ''}")


def cmd_run(args: argparse.Namespace) -> int:
    _print_result(run_mod.run(brief_mod.load(args.brief)))
    return 0


def cmd_packets(args: argparse.Namespace) -> int:
    from . import judgment as judgment_mod

    result = run_mod.run(brief_mod.load(args.brief))
    written = judgment_mod.write_packets(result, Path(args.out))

    if not written:
        print("no packets: no judgment lens produced a verdict for an agent to "
              "interpret.")
        for row in result.unevaluated:
            if row["lens"] in judgment_mod.JUDGMENT_LENSES:
                print(f"  {row['lens']:12} {row['state']:18} {row['why']}")
        #: Not an error. A run that stops in tier 1 has nothing for stage 2,
        #: and saying so is the answer -- §2 precedence level 1 stops the run
        #: and returns a revision.
        return 0

    packets = judgment_mod.build_packets(result)
    for path in written:
        packet = packets[path.stem.split("-", 2)[2]]
        print(f"wrote {path}")
        print(f"  agent {packet.agent}  ·  {len(packet.must_rule_on)} to rule "
              f"on  ·  {len(packet.assumed_inputs)} assumed input(s)")
    print()
    print("Convene each agent with its packet, then pass the verdicts back:")
    print("  python -m designer.cli emit <brief> ... " +
          " ".join(f"--judgment <{p.stem}-verdict.yaml>" for p in written))
    return 0


def _load_judgments(paths, result) -> tuple[dict, int]:
    """Read every returned verdict and refuse the ones that are not reviews.

    ⚠ THE PACKET ROSTER IS REBUILT AFTER EVERY ACCEPTED VERDICT, because E2
    makes it grow: lens 6 has no packet until lenses 4 · 5 · 8 have returned,
    so a roster built once before the loop has no lens-6 entry and refuses a
    lens-6 verdict with "no packet in this run". That is what it did the first
    time a real lens-6 verdict was handed to it -- the library half enforced
    E2 correctly and this half built the roster once and never looked again.
    """
    from . import judgment as judgment_mod

    accepted: dict = {}
    refused = 0
    for path in paths or ():
        packets = judgment_mod.build_packets(result, judgments=accepted)
        parsed = judgment_mod.read_judgment(path)
        lens = parsed.lens if isinstance(parsed.lens, str) else next(
            (name for name, pk in packets.items() if pk.number == parsed.lens), None
        )
        packet = packets.get(lens)
        if packet is None:
            print(f"REFUSED {path}: lens {parsed.lens!r} has no packet in this "
                  "run, so there was nothing for it to review")
            refused += 1
            continue
        problems = judgment_mod.check_judgment(parsed, packet, others=accepted)
        if problems:
            print(f"REFUSED {path} ({len(problems)}):")
            for r in problems:
                print(f"  [{r.rule}] {r.why}")
                print(f"      -> {r.action}")
            refused += 1
            continue
        print(f"accepted {path}: lens {packet.number} {lens}, {parsed.status}, "
              f"{len(parsed.rulings)} ruling(s)")
        accepted[lens] = parsed
    return accepted, refused


def cmd_emit(args: argparse.Namespace) -> int:
    from knowledge.plans import check_plan

    from . import judgment as judgment_mod

    result = run_mod.run(brief_mod.load(args.brief))
    identity = emit_mod.Identity(
        id=args.id, date=args.date, question=args.question, title=args.title
    )

    rows = None
    if args.judgment:
        accepted, refused = _load_judgments(args.judgment, result)
        if refused:
            print()
            print("nothing written. A refused judgment is not a missing one -- "
                  "writing the plan without it would record a review that did "
                  "not happen.")
            return 1
        packets = judgment_mod.build_packets(result, judgments=accepted)
        rows = judgment_mod.judgment_rows(packets, accepted, result)
        print()

    md, plan_yaml = emit_mod.write(result, identity, Path(args.out), rows)
    print(f"wrote {md}")
    print(f"wrote {plan_yaml}")

    problems = check_plan(md, root=Path(args.out).parent)
    if problems:
        print()
        print(f"plan-check REFUSES the file just written ({len(problems)}):")
        for p in problems:
            print(f"  {p}")
        return 1
    print("plan-check: ok")

    print()
    _print_result(result)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m designer.cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run the committee and print the verdicts")
    run_p.add_argument("brief", help="path to a config/briefs/*.yaml")
    run_p.set_defaults(func=cmd_run)

    emit_p = sub.add_parser("emit", help="run the committee and write plan.md + plan.yaml")
    emit_p.add_argument("brief")
    emit_p.add_argument("--id", required=True, help="YYYY-MM-DD-slug; both files share it")
    emit_p.add_argument("--date", required=True, help="YYYY-MM-DD")
    emit_p.add_argument(
        "--question", required=True,
        help="what this run is for, as a question -- what knowledge.cli indexes it by",
    )
    emit_p.add_argument("--title", default=None)
    emit_p.add_argument(
        "--out", required=True,
        help="output directory. No default, and kb/plans/ is not one -- writing "
             "there is a decision (§9), not a side effect",
    )
    emit_p.add_argument(
        "--judgment", action="append", default=[],
        help="a judgment lens's returned verdict. Repeatable. Each is checked "
             "before it is believed, and one refusal writes nothing",
    )
    emit_p.set_defaults(func=cmd_emit)

    packets_p = sub.add_parser(
        "packets", help="write what each judgment lens is to be handed (stage 2)"
    )
    packets_p.add_argument("brief")
    packets_p.add_argument("--out", required=True)
    packets_p.set_defaults(func=cmd_packets)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
