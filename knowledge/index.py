"""Build `kb/INDEX.md` from the frontmatter each knowledge file already carries.

The index is **pointers only** -- id, date, the one-line question the file
answers, and which other entries supersede or correct it. No measured value, no
conclusion and no quotation goes in it, because CLAUDE.md §6 says not to
duplicate what the repository already records, and an index that carries
content is a fourth place a fact lives.

It is generated, not written. `tests/test_kb_index.py` regenerates it and fails
on any difference, so the committed file cannot drift away from the frontmatter
the way a hand-maintained list would.

    python -m knowledge.cli check     # print what would change; exit 1 if any
    python -m knowledge.cli write     # regenerate kb/INDEX.md

What the frontmatter is, and is not: the `question:` line is a restatement of
the file's own title and its Request/Context section, and the link fields are
readings of the supersession notes those files already carry in prose. It is a
retrieval aid derived from each file. It is **not** evidence and it is not a
source -- docs/09 §7, "the agent's own inference is not a source". Cite the
entry, never the index line.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

#: Repository root, from this file's location.
REPO_ROOT = Path(__file__).resolve().parent.parent

#: Where the knowledge base lives, and where the index is written.
KB_ROOT = REPO_ROOT / "kb"
INDEX_PATH = KB_ROOT / "INDEX.md"

#: Every indexed file carries these. `id` addresses it, `question` says what it
#: answers.
REQUIRED_KEYS = ("id", "question")

#: And a `date`, saying when that was true -- except for an entry that declares
#: `living: true`. A dossier revised on every trip to the instrument has no one
#: date at which it was true, and stamping one on it would be a claim the file
#: cannot support. The opt-in is a key of its own so it cannot happen by
#: forgetting to write the date.
LIVING_KEY = "living"

#: Fields naming other entries. A value here that matches no `id` is a bug --
#: it means a supersession note points at a file that moved or never existed.
LINK_KEYS = ("supersedes", "superseded_by", "corrects", "corrected_by")

#: Directory order in the rendered index: what the instrument is, then durable
#: judgment, then dated choices, then outside numbers, then the daily record.
SECTIONS: tuple[tuple[str, str], ...] = (
    ("systems", "What this instrument is, as measured"),
    ("expertise", "Durable expert judgment. Each carries a `Why` and a falsifier"),
    ("decisions", "Dated design and scope choices, in the order they were made"),
    ("plans", "One hardware run each, before it happens — 05 §6 stage 5"),
    ("literature", "Published values nobody here has measured"),
    ("sessions", "The day's narrative"),
)

#: Templates and the index itself are not entries.
EXCLUDED_NAMES = frozenset({"INDEX.md", "_template.md"})

#: The one status that renders no marker, because it is the default. Every
#: other value is shown verbatim rather than matched against a whitelist -- a
#: whitelist is how a status nobody thought of disappears from the index while
#: still being true of the file.
DEFAULT_STATUS = "current"


@dataclass(frozen=True)
class Entry:
    """One indexed knowledge file."""

    path: Path
    """Absolute path on disk."""

    meta: dict
    """The parsed frontmatter, verbatim."""

    root: Path = KB_ROOT
    """The knowledge-base root this entry was collected under.

    Carried on the entry rather than read off the module, so `collect()` over
    some other directory -- a test's `tmp_path`, a second knowledge base -- is
    not silently resolved against `kb/`.
    """

    @property
    def rel(self) -> str:
        """Path relative to the root, forward-slashed, for a link in INDEX.md."""
        return self.path.relative_to(self.root).as_posix()

    @property
    def section(self) -> str:
        """The subdirectory of the root this entry sits in."""
        return self.path.relative_to(self.root).parts[0]

    @property
    def id(self) -> str:
        return str(self.meta["id"])

    @property
    def question(self) -> str:
        """The frontmatter question, unwrapped to one line."""
        return " ".join(str(self.meta["question"]).split())

    @property
    def date(self) -> str:
        """The date the entry records, or `""` for a living one that omits it."""
        raw = self.meta.get("date")
        return "" if raw is None else str(raw)

    @property
    def living(self) -> bool:
        """True when the entry is revised continuously and has no single date."""
        return bool(self.meta.get(LIVING_KEY))

    @property
    def when(self) -> str:
        """What renders where the date goes."""
        if not self.living:
            return self.date
        return f"living, since {self.date}" if self.date else "living"

    @property
    def status(self) -> str:
        return str(self.meta.get("status", "current"))

    def links(self, key: str) -> tuple[str, ...]:
        """The ids named by one link field, as a tuple. Absent field -> empty."""
        raw = self.meta.get(key)
        if raw is None:
            return ()
        if isinstance(raw, str):
            return (raw,)
        return tuple(str(item) for item in raw)


@dataclass(frozen=True)
class Problem:
    """Something wrong with a file's frontmatter. Reported, never guessed around."""

    path: Path
    what: str

    def __str__(self) -> str:
        try:
            where = self.path.relative_to(REPO_ROOT).as_posix()
        except ValueError:  # pragma: no cover -- a path outside the repository
            where = str(self.path)
        return f"{where}: {self.what}"


def split_frontmatter(text: str) -> tuple[str | None, str]:
    """Return `(frontmatter_text, body)`. `None` when the file has no frontmatter.

    A frontmatter block is a `---` on the very first line, closed by the next
    `---` alone on a line.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None, text
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "".join(lines[1:i]), "".join(lines[i + 1 :])
    return None, text


def read_entry(path: Path, root: Path = KB_ROOT) -> tuple[Entry | None, list[Problem]]:
    """Parse one file. Returns `(None, problems)` when it cannot be indexed."""
    text = path.read_text(encoding="utf-8")
    raw, _ = split_frontmatter(text)
    if raw is None:
        return None, [Problem(path, "no YAML frontmatter -- cannot be indexed")]
    try:
        meta = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        first = str(exc).splitlines()[0]
        return None, [Problem(path, f"frontmatter is not valid YAML: {first}")]
    if not isinstance(meta, dict):
        return None, [Problem(path, "frontmatter is not a mapping")]
    missing = [key for key in REQUIRED_KEYS if not meta.get(key)]
    if not meta.get("date") and not meta.get(LIVING_KEY):
        missing.append("date (or living: true)")
    if missing:
        return None, [Problem(path, f"frontmatter is missing {', '.join(missing)}")]
    return Entry(path=path, meta=meta, root=root), []


def collect(kb_root: Path = KB_ROOT) -> tuple[list[Entry], list[Problem]]:
    """Every indexable `kb/**/*.md`, plus what could not be indexed and why."""
    entries: list[Entry] = []
    problems: list[Problem] = []
    for path in sorted(kb_root.rglob("*.md")):
        if path.name in EXCLUDED_NAMES:
            continue
        entry, trouble = read_entry(path, root=kb_root)
        problems.extend(trouble)
        if entry is not None:
            entries.append(entry)
    problems.extend(_duplicate_ids(entries))
    problems.extend(_dangling_links(entries))
    problems.extend(_unknown_sections(entries))
    return entries, problems


def _duplicate_ids(entries: list[Entry]) -> list[Problem]:
    """An id addresses exactly one file, or it addresses nothing."""
    seen: dict[str, Entry] = {}
    problems: list[Problem] = []
    for entry in entries:
        first = seen.get(entry.id)
        if first is None:
            seen[entry.id] = entry
        else:
            problems.append(
                Problem(entry.path, f"id {entry.id!r} is already used by {first.rel}")
            )
    return problems


def _dangling_links(entries: list[Entry]) -> list[Problem]:
    """A supersession pointing at nothing is worse than none: it reads as safe."""
    known = {entry.id for entry in entries}
    problems: list[Problem] = []
    for entry in entries:
        for key in LINK_KEYS:
            for target in entry.links(key):
                if target not in known:
                    problems.append(
                        Problem(entry.path, f"{key}: {target!r} matches no entry id")
                    )
    return problems


def _unknown_sections(entries: list[Entry]) -> list[Problem]:
    """A new `kb/` subdirectory has to be given a place in the index by hand."""
    named = {name for name, _ in SECTIONS}
    return [
        Problem(entry.path, f"in kb/{entry.section}/, which SECTIONS does not list")
        for entry in entries
        if entry.section not in named
    ]


def _marker(entry: Entry, by_id: dict[str, Entry]) -> str:
    """What follows the date: the status, and who superseded or corrected this."""

    def refs(key: str) -> str:
        return ", ".join(
            f"[{target}]({by_id[target].rel})" for target in entry.links(key)
        )

    label = "" if entry.status == DEFAULT_STATUS else entry.status.replace("-", " ")
    superseded_by, corrected_by = refs("superseded_by"), refs("corrected_by")

    parts: list[str] = []
    if label and superseded_by:
        parts.append(f"{label} by {superseded_by}")
    elif label:
        parts.append(label)
    elif superseded_by:
        parts.append(f"superseded by {superseded_by}")
    if corrected_by:
        parts.append(f"corrected by {corrected_by}")
    return " · ".join(parts)


def render(entries: list[Entry]) -> str:
    """The whole of `kb/INDEX.md`, deterministic for a given set of entries."""
    by_id = {entry.id: entry for entry in entries}
    out: list[str] = [
        "# kb/INDEX.md",
        "",
        "**Generated. Do not edit by hand.**",
        "`python -m knowledge.cli write` rebuilds it from each file's",
        "frontmatter; `tests/test_kb_index.py` fails when the two disagree.",
        "",
        "Pointers only -- id, date, the question the entry answers, and what has",
        "superseded or corrected it since. **No value, conclusion or quotation is",
        "repeated here**, so a line in this file is never a citation: open the",
        "entry and cite that (docs/09 §7). The `question` lines are restatements",
        "of each file's own title and Request/Context section, not new claims.",
        "",
    ]

    for name, blurb in SECTIONS:
        section = sorted(
            (entry for entry in entries if entry.section == name),
            key=lambda entry: (not entry.living, entry.date, entry.id),
        )
        if not section:
            continue
        out.append(f"## `kb/{name}/` — {len(section)} entries")
        out.append("")
        out.append(f"{blurb}.")
        out.append("")
        for entry in section:
            marker = _marker(entry, by_id)
            suffix = f" · {marker}" if marker else ""
            out.append(f"- **[{entry.id}]({entry.rel})** · {entry.when}{suffix}")
            out.append(f"  {entry.question}")
        out.append("")

    out.extend(
        [
            "## `kb/calibrations/` — not indexed here",
            "",
            "Measured constants, as `.yaml` and one `.txt` rather than prose, so",
            "they carry no frontmatter to generate a line from. Each one opens with",
            "a header comment naming the command that produced it and the gate that",
            "consumes it, which is the same information a line here would carry --",
            "so listing them would be the duplication this file exists to avoid.",
            "",
        ]
    )
    return "\n".join(out).rstrip("\n") + "\n"
