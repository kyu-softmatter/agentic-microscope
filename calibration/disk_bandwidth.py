"""Sustained sequential write bandwidth of an acquisition disk.

Feeds the G12 hard gate (docs/04-decision-engine.md §9: camera data rate
must stay under 0.7x measured disk bandwidth) and the "디스크 지속쓰기
대역폭" line item in docs/07-roadmap.md Phase 0. Point it at the actual
folder Micro-Manager streams multi-page TIFFs into -- bandwidth to a
work-PC scratch disk says nothing about the acquisition disk.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DiskBandwidthResult:
    directory: str
    bytes_written: int
    seconds: float

    @property
    def mb_per_s(self) -> float:
        return self.bytes_written / self.seconds / 1e6


def measure_write_bandwidth(
    directory: Path,
    *,
    total_bytes: int,
    chunk_bytes: int = 64 * 1024 * 1024,
) -> DiskBandwidthResult:
    """Write ``total_bytes`` of random data into a throwaway file in
    ``directory`` and time it, including an ``fsync`` so the OS write-behind
    cache can't hide behind buffering and overstate the disk's real
    bandwidth. The probe file is removed afterward, success or not.

    Random bytes (not zeros) so filesystems/SSDs that special-case runs of
    zeros (sparse-file detection, some inline compression) don't overstate
    the result. The chunk is generated once, before timing starts, and
    reused for every write -- regenerating it per chunk would time random
    number generation, not disk I/O.
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise FileNotFoundError(f"not a directory: {directory}")
    if total_bytes <= 0:
        raise ValueError(f"total_bytes must be positive, got {total_bytes}")

    chunk = os.urandom(min(chunk_bytes, total_bytes))
    target = directory / f".bandwidth_probe_{uuid.uuid4().hex}.tmp"
    written = 0
    try:
        start = time.perf_counter()
        with open(target, "wb") as f:
            while written < total_bytes:
                n = f.write(chunk[: total_bytes - written])
                written += n
            f.flush()
            os.fsync(f.fileno())
        elapsed = time.perf_counter() - start
    finally:
        target.unlink(missing_ok=True)

    return DiskBandwidthResult(
        directory=str(directory), bytes_written=written, seconds=elapsed
    )
