"""Command-line front end for the knowledge-base index.

    python -m knowledge.cli check       # what would change, and what cannot be indexed
    python -m knowledge.cli write       # regenerate kb/INDEX.md
    python -m knowledge.cli problems    # only the files the index cannot describe
    python -m knowledge.cli plan-check  # refuse a kb/plans/ entry a skill would misread
    python -m knowledge.cli plan-sidecar kb/plans/<slug>.md   # scaffold its .json half

`check` is what CI runs through `tests/test_kb_index.py`. It exits non-zero when
the committed index differs from what the frontmatter says, or when any file in
`kb/` cannot be indexed at all -- a file with no frontmatter is invisible to
every reader who starts from the index, which is the failure this whole
mechanism exists to prevent.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path

from .index import INDEX_PATH, KB_ROOT, collect, render
from .plans import check_all


def _report_problems(problems: list) -> None:
    if not problems:
        return
    print(f"{len(problems)} file(s) the index cannot describe:", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)


def cmd_check(args: argparse.Namespace) -> int:
    entries, problems = collect(Path(args.kb))
    _report_problems(problems)

    wanted = render(entries)
    index_path = Path(args.out)
    current = index_path.read_text(encoding="utf-8") if index_path.exists() else ""

    if current == wanted:
        print(f"{index_path.name} is up to date -- {len(entries)} entries")
        return 1 if problems else 0

    diff = difflib.unified_diff(
        current.splitlines(keepends=True),
        wanted.splitlines(keepends=True),
        fromfile=f"{index_path.name} (committed)",
        tofile=f"{index_path.name} (from frontmatter)",
    )
    sys.stdout.writelines(diff)
    print(f"\n{index_path.name} is stale. Run: python -m knowledge.cli write")
    return 1


def cmd_write(args: argparse.Namespace) -> int:
    entries, problems = collect(Path(args.kb))
    _report_problems(problems)

    index_path = Path(args.out)
    index_path.write_text(render(entries), encoding="utf-8")
    print(f"wrote {index_path} -- {len(entries)} entries")
    return 1 if problems else 0


def cmd_problems(args: argparse.Namespace) -> int:
    _, problems = collect(Path(args.kb))
    if not problems:
        print("every file in kb/ can be indexed")
        return 0
    _report_problems(problems)
    return 1


def cmd_plan_check(args: argparse.Namespace) -> int:
    """Refuse a hardware plan a skill would misread. See knowledge/plans.py."""
    plans_dir = Path(args.kb) / "plans"
    problems = check_all(plans_dir)
    if not problems:
        count = len([p for p in plans_dir.glob("*.md") if not p.name.startswith("_")])
        print(f"{count} plan(s) in {plans_dir}, all usable")
        return 0
    print(f"{len(problems)} problem(s):", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    return 1


def cmd_plan_sidecar(args: argparse.Namespace) -> int:
    """Scaffold the structured half of a plan. Refuses to overwrite one.

    Overwriting is refused rather than prompted for, the same way
    `config/micromanager/set_pixel_size.py` refuses a differing preset: a
    sidecar that exists has been filled in by a person, and regenerating it
    from the prose would invert which half is authoritative.
    """
    from .index import read_entry
    from .plans import split_frontmatter
    from .sidecar import scaffold, sidecar_path

    plan_path = Path(args.plan)
    if not plan_path.is_file():
        print(f"no such plan: {plan_path}", file=sys.stderr)
        return 2

    out = sidecar_path(plan_path)
    if out.exists():
        print(
            f"{out} exists -- refusing to overwrite. Edit it, or delete it "
            "deliberately first.",
            file=sys.stderr,
        )
        return 1

    entry, problems = read_entry(plan_path, root=plan_path.parent.parent)
    if entry is None:
        _report_problems(problems)
        return 1

    _, body = split_frontmatter(plan_path.read_text(encoding="utf-8"))
    out.write_text(
        json.dumps(scaffold(plan_path, entry.id, body), indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {out} -- every empty field is yours to fill; nothing was guessed")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m knowledge.cli", description=__doc__.splitlines()[0]
    )
    parser.add_argument(
        "--kb", default=str(KB_ROOT), help="knowledge-base root (default: kb/)"
    )
    parser.add_argument(
        "--out", default=str(INDEX_PATH), help="index path (default: kb/INDEX.md)"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="exit non-zero if the index is stale").set_defaults(
        func=cmd_check
    )
    sub.add_parser("write", help="regenerate the index").set_defaults(func=cmd_write)
    sub.add_parser("problems", help="list unindexable files").set_defaults(
        func=cmd_problems
    )
    sub.add_parser("plan-check", help="validate kb/plans/ entries").set_defaults(
        func=cmd_plan_check
    )
    scaffold = sub.add_parser(
        "plan-sidecar", help="write a first kb/plans/<slug>.json for a plan"
    )
    scaffold.add_argument("plan", help="path to the plan's .md")
    scaffold.set_defaults(func=cmd_plan_sidecar)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
