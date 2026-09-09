"""`kb/INDEX.md` is generated, and this is what stops it from becoming a lie.

`kb/` is 48 files and roughly 710 KB of prose. `kb/systems/current.md` alone is
1634 lines. Nobody -- person or agent -- opens the right one of those by
grepping, so the index is what makes the knowledge base reachable at all, and an
index that has drifted is worse than none: it is a list that reads as complete
while omitting the entry that would have changed the answer.

So the index is not maintained. It is rendered from frontmatter that lives next
to the content it describes, and these tests fail on every way that can come
apart:

- a file in `kb/` that carries no frontmatter is **invisible to the index**, and
  therefore invisible to every reader who starts from it
- a committed `INDEX.md` that no longer matches the frontmatter
- two files claiming one `id`
- a `superseded_by` / `corrects` pointing at an id that does not exist -- which
  is the dangerous one, because a supersession that resolves to nothing reads
  exactly like an entry nobody has had to correct

Only `knowledge/index.py` is under test here. What the entries *say* is not
checkable by a test; that is what `Why` and the falsifier in docs/09 §2 are for.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from knowledge.index import (
    EXCLUDED_NAMES,
    INDEX_PATH,
    KB_ROOT,
    LINK_KEYS,
    SECTIONS,
    Entry,
    collect,
    read_entry,
    render,
    split_frontmatter,
)


#: How long a `question:` line may get before it has stopped being a pointer.
MAX_QUESTION_CHARS = 200


@pytest.fixture(scope="module")
def collected() -> tuple[list[Entry], list]:
    """The real `kb/`, collected once -- rglob over 48 files is not free."""
    return collect()


# --------------------------------------------------------------------------
# the repository's own kb/
# --------------------------------------------------------------------------


def test_every_kb_file_can_be_indexed(collected):
    """A file with no frontmatter is invisible to anyone starting at the index."""
    _, problems = collected
    assert not problems, "\n".join(str(problem) for problem in problems)


def test_committed_index_matches_the_frontmatter(collected):
    """The whole point: `INDEX.md` cannot drift away from what it describes."""
    entries, _ = collected
    assert INDEX_PATH.exists(), "kb/INDEX.md is missing -- python -m knowledge.cli write"
    assert INDEX_PATH.read_text(encoding="utf-8") == render(entries), (
        "kb/INDEX.md is stale. Run: python -m knowledge.cli write"
    )


def test_the_index_covers_every_markdown_file(collected):
    """Counted independently of `collect`, so a filter bug cannot hide a file."""
    entries, _ = collected
    on_disk = {
        path for path in KB_ROOT.rglob("*.md") if path.name not in EXCLUDED_NAMES
    }
    assert {entry.path for entry in entries} == on_disk


def test_a_question_stays_one_line(collected):
    """The observable symptom of content leaking into the index is length.

    No test can judge whether a `question` has quietly become a finding -- that
    is what review is for. What it can hold is the shape: one line, and short
    enough that answering it in place was never an option. A `question` that has
    grown into a paragraph is the state in which somebody has started pasting
    the conclusion in so the reader does not have to open the entry.

    The bound is a limit on this file's format, not a measurement of anything.
    The longest question in `kb/` is 163 characters (2026-09-09,
    `current-laser-green-band-single-slot`), so 200 leaves room for one more
    clause and refuses a second sentence.
    """
    entries, _ = collected
    too_long = {
        entry.id: len(entry.question)
        for entry in entries
        if len(entry.question) > MAX_QUESTION_CHARS
    }
    assert not too_long, f"over {MAX_QUESTION_CHARS} chars: {too_long}"


def test_every_section_on_disk_has_a_place_in_the_index():
    """A new `kb/` subdirectory must be given a heading, not silently dropped."""
    named = {name for name, _ in SECTIONS}
    on_disk = {
        path.relative_to(KB_ROOT).parts[0]
        for path in KB_ROOT.rglob("*.md")
        if path.name not in EXCLUDED_NAMES
    }
    assert on_disk <= named, f"unplaced: {sorted(on_disk - named)}"


def test_rendering_is_deterministic(collected):
    """Two runs over the same entries agree, or `check` would be noise."""
    entries, _ = collected
    assert render(entries) == render(list(reversed(entries)))


# --------------------------------------------------------------------------
# the mechanism, on files built for the purpose
# --------------------------------------------------------------------------


def write(tmp_path: Path, rel: str, text: str) -> Path:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


GOOD = """---
id: an-entry
question: "Does this parse"
date: 2026-09-09
---

body
"""


def test_split_frontmatter_finds_the_block():
    raw, body = split_frontmatter(GOOD)
    assert raw is not None and "id: an-entry" in raw
    assert body.strip() == "body"


def test_split_frontmatter_needs_the_marker_on_line_one():
    """A `---` further down is a horizontal rule, not frontmatter."""
    raw, _ = split_frontmatter("# title\n\n---\nid: x\n---\n")
    assert raw is None


def test_split_frontmatter_needs_the_block_closed():
    raw, _ = split_frontmatter("---\nid: x\nnever closed\n")
    assert raw is None


@pytest.mark.parametrize(
    "text, expected",
    [
        ("# no frontmatter\n", "no YAML frontmatter"),
        ("---\nid: x\nquestion: y\n---\n", "missing date"),
        ("---\nquestion: y\ndate: 2026-09-09\n---\n", "missing id"),
        ("---\nid: x\ndate: 2026-09-09\n---\n", "missing question"),
        ("---\n- a list\n---\n", "not a mapping"),
        ("---\nid: x\n  bad: indent\n---\n", "not valid YAML"),
    ],
)
def test_a_file_the_index_cannot_describe_is_reported_not_guessed(
    tmp_path, text, expected
):
    """Every one of these is a `Problem`, never a silently skipped file."""
    path = write(tmp_path, "systems/broken.md", text)
    entry, problems = read_entry(path)
    assert entry is None
    assert expected in str(problems[0])


def test_living_replaces_the_date_and_only_when_declared(tmp_path):
    """A continuously revised dossier has no one date; it has to say so."""
    living = write(
        tmp_path,
        "systems/dossier.md",
        '---\nid: dossier\nquestion: "What is here"\nliving: true\n---\n',
    )
    entry, problems = read_entry(living)
    assert not problems
    assert entry.living and entry.when == "living"

    entry, problems = read_entry(
        write(
            tmp_path,
            "systems/forgot.md",
            '---\nid: forgot\nquestion: "What is here"\n---\n',
        )
    )
    assert entry is None
    assert "date (or living: true)" in str(problems[0])


def test_living_with_a_date_says_since_when(tmp_path):
    entry, _ = read_entry(
        write(
            tmp_path,
            "sessions/README.md",
            '---\nid: i\nquestion: "What happened"\ndate: 2026-09-07\nliving: true\n---\n',
        )
    )
    assert entry.when == "living, since 2026-09-07"


def test_two_files_cannot_claim_one_id(tmp_path):
    for name in ("one.md", "two.md"):
        write(
            tmp_path,
            f"decisions/{name}",
            '---\nid: same\nquestion: "Which one"\ndate: 2026-09-09\n---\n',
        )
    _, problems = collect(tmp_path)
    assert any("already used by" in str(problem) for problem in problems)


@pytest.mark.parametrize("key", LINK_KEYS)
def test_a_link_to_a_missing_entry_is_a_problem(tmp_path, key):
    """A supersession that resolves to nothing reads like one nobody had to make."""
    write(
        tmp_path,
        "decisions/a.md",
        f'---\nid: a\nquestion: "Q"\ndate: 2026-09-09\n{key}: [gone]\n---\n',
    )
    _, problems = collect(tmp_path)
    assert any("matches no entry id" in str(problem) for problem in problems)


def test_a_status_nobody_anticipated_still_renders(tmp_path):
    """No whitelist: an unknown status shows, rather than vanishing quietly."""
    write(
        tmp_path,
        "decisions/a.md",
        '---\nid: a\nquestion: "Q"\ndate: 2026-09-09\nstatus: withdrawn-by-operator\n---\n',
    )
    entries, problems = collect(tmp_path)
    assert not problems
    assert "withdrawn by operator" in render(entries)


def test_a_new_subdirectory_is_reported_rather_than_dropped(tmp_path):
    write(
        tmp_path,
        "protocols/a.md",
        '---\nid: a\nquestion: "Q"\ndate: 2026-09-09\n---\n',
    )
    _, problems = collect(tmp_path)
    assert any("SECTIONS does not list" in str(problem) for problem in problems)
