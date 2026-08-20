"""The one thing drop detection needs out of a Micro-Manager metadata file:
the per-frame ``ElapsedTime-ms`` series.

This is **not** the L1 indexer of docs/02-knowledge-base.md -- that one reads
headers only (Summary + first FrameKey + tail) and builds a SQLite envelope
across all 2,343 acquisitions. Drop detection needs every frame's timestamp,
so this scans the whole file, but line by line with a regex rather than
``json.load`` so a multi-hundred-MB metadata file does not have to be
materialised as a dict.

Both MM generations write the same two tokens -- ``"FrameKey-t-c-z"`` and
``"ElapsedTime-ms"`` -- so the dual schema of docs/06 §A2 does not need
branching here. What it does need is tolerance: MM 1.4 sometimes quotes the
number, and neither generation guarantees pretty-printing, so the scan
matches tokens within a line rather than assuming one token per line.

Not covered: MM 2.0's NDTiff format, which has no ``metadata.txt`` at all.
An NDTiff dataset scans as zero frames, and the caller is told so rather
than being handed an empty series that looks like a clean acquisition.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

#: One pass over the text, matching either token. Order matters: a FrameKey
#: opens a block, the next ElapsedTime-ms closes it.
TOKEN_RE = re.compile(
    r'"FrameKey-(?P<t>\d+)-(?P<c>\d+)-(?P<z>\d+)"\s*:'
    r'|"ElapsedTime-ms"\s*:\s*"?(?P<ms>-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)"?'
)

_SUMMARY_NUMBER_RE = {
    "interval_ms": re.compile(r'"Interval_ms"\s*:\s*"?(-?\d+(?:\.\d+)?)"?'),
    "frames": re.compile(r'"Frames"\s*:\s*"?(\d+)"?'),
    "width": re.compile(r'"Width"\s*:\s*"?(\d+)"?'),
    "height": re.compile(r'"Height"\s*:\s*"?(\d+)"?'),
    "bit_depth": re.compile(r'"BitDepth"\s*:\s*"?(\d+)"?'),
}

DEFAULT_GLOB = "*metadata.txt"


@dataclass(frozen=True)
class FrameTime:
    """One frame's position in the acquisition and when it arrived."""

    frame: int
    channel: int
    slice: int
    elapsed_ms: float

    @property
    def series(self) -> tuple[int, int]:
        """The (channel, slice) series this frame belongs to.

        A multi-channel or z-stack acquisition interleaves several series
        into one ElapsedTime sequence, giving it a bimodal interval
        distribution -- tiny gaps within a timepoint, a long one between
        them. Drop detection has to run per series or the median cadence is
        meaningless.
        """
        return (self.channel, self.slice)


@dataclass(frozen=True)
class MetadataScan:
    path: str
    frames: tuple[FrameTime, ...]
    #: FrameKey blocks seen, including any that carried no ElapsedTime-ms.
    frame_keys_seen: int

    @property
    def frames_without_timestamp(self) -> int:
        return self.frame_keys_seen - len(self.frames)


@dataclass(frozen=True)
class SummaryHints:
    """The few Summary fields worth having next to a drop report.

    ``interval_ms`` is the **requested** frame interval -- the number
    docs/06 §C4 found to be 3x off the delivered one. Everything here is
    what MM was told, not what happened.
    """

    interval_ms: float | None = None
    frames: int | None = None
    width: int | None = None
    height: int | None = None
    bit_depth: int | None = None


def read_frame_times(path: Path | str) -> MetadataScan:
    """Scan a metadata file for its ``(FrameKey, ElapsedTime-ms)`` pairs."""
    path = Path(path)
    frames: list[FrameTime] = []
    pending: tuple[int, int, int] | None = None
    seen = 0

    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            for m in TOKEN_RE.finditer(line):
                if m.group("t") is not None:
                    pending = (int(m.group("t")), int(m.group("c")), int(m.group("z")))
                    seen += 1
                elif pending is not None:
                    t, c, z = pending
                    frames.append(FrameTime(t, c, z, float(m.group("ms"))))
                    pending = None

    return MetadataScan(path=str(path), frames=tuple(frames), frame_keys_seen=seen)


def read_summary_hints(path: Path | str) -> SummaryHints:
    """Pull the Summary block's requested settings, stopping at frame 1.

    Streams only as far as the first FrameKey, so this stays cheap enough to
    call on every file in a directory sweep.
    """
    path = Path(path)
    found: dict[str, float] = {}

    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            for name, pattern in _SUMMARY_NUMBER_RE.items():
                if name not in found and (m := pattern.search(line)):
                    found[name] = float(m.group(1))
            if '"FrameKey-' in line:
                break

    def _int(name: str) -> int | None:
        return int(found[name]) if name in found else None

    return SummaryHints(
        interval_ms=found.get("interval_ms"),
        frames=_int("frames"),
        width=_int("width"),
        height=_int("height"),
        bit_depth=_int("bit_depth"),
    )


def iter_metadata_files(root: Path | str, pattern: str = DEFAULT_GLOB) -> Iterator[Path]:
    """Every metadata file under ``root``, sorted so a sweep is reproducible."""
    yield from sorted(Path(root).rglob(pattern))
