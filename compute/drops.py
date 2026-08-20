"""Post-hoc frame-drop detection -- the compute lens's other half.

docs/05-consensus-gate.md calls this the lens's specialty and docs/06 §C5
says why: when the buffer cannot keep up, frames are discarded and **no
error is raised**. The only trace is the ``ElapsedTime-ms`` series turning
irregular. Get the lag time wrong in an MSD and the diffusion coefficient is
wholly wrong, so an acquisition can look perfect and be worthless.

Everything else in this lens judges an acquisition before it runs. This
judges one that already ran, which makes it the only part applicable to the
2,343-acquisition archive today -- docs/07-roadmap.md lists exactly that
sweep as the first thing that pays off without new experiments.

**How it decides.** For each (channel, slice) series independently -- an
interleaved multi-channel acquisition has a bimodal interval distribution
and a pooled median would be meaningless -- take the median interval as the
cadence. The median is used rather than the mean because a drop can only
lengthen an interval, never shorten one, so the mean is dragged by exactly
the thing being detected while the median is not. An interval that clears
both ``GAP_RATIO`` times the cadence **and** the cadence plus a couple of
timestamp ticks is a gap, and it hides ``round(dt / cadence) - 1`` missing
frames. The second condition only bites on fast acquisitions, where a
single tick of rounding is already a 1.5x interval.

**What it cannot do.** It cannot tell a dropped frame from a genuine stall
in the acquisition loop (a stage move, an autofocus, a filter change). Both
look like a long interval. It reports the gap and leaves the cause to
whoever knows what the acquisition was doing -- naming the frame index is
what makes that possible.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from statistics import fmean, median

from .mm_metadata import (
    DEFAULT_GLOB,
    FrameTime,
    iter_metadata_files,
    read_frame_times,
    read_summary_hints,
)

#: An interval at least this many times the median cadence is a gap. Below
#: it, an interval is jitter. A screening threshold, not a measured
#: criterion -- 1.5 is the midpoint between "one frame period" and "two",
#: so it splits cleanly for any cadence whose jitter stays under 50%.
GAP_RATIO = 1.5

#: MAD/median above this counts as an irregular cadence even with no gap
#: big enough to name. Also screening, not measured.
JITTER_WARN_FRACTION = 0.10

#: MM writes ElapsedTime-ms at 1 ms resolution.
TIMESTAMP_RESOLUTION_MS = 1.0

#: Below this many resolution steps per interval, quantization dominates the
#: jitter estimate and the number stops meaning anything.
#:
#: Derived, not picked: MAD is quantized to whole ticks, so the smallest
#: non-zero jitter it can report is ``1 tick / cadence``. For the
#: JITTER_WARN_FRACTION test to be a measurement rather than a coin flip, that
#: threshold has to be worth at least two resolvable ticks --
#: ``2 / JITTER_WARN_FRACTION = 20``. A real 2.0.3 acquisition on this archive
#: (62.5 fps, 16 ms) has intervals alternating 15/16 ms around a true cadence
#: of 15.63; MAD comes out 0.00 ms and would otherwise be reported as perfectly
#: steady.
QUANTIZATION_GUARD_STEPS = 20.0

#: A gap also has to clear the cadence by this many resolution steps, not
#: just by GAP_RATIO. At a 2 ms cadence, one tick of rounding is already a
#: 1.5x interval -- without this floor a fast acquisition reports phantom
#: drops on every quantization step, which is worse than reporting none:
#: a sweep of the archive would come back saying the fastest sessions are
#: the most contaminated.
QUANTIZATION_GAP_MARGIN_STEPS = 2.0

#: Fewer intervals than this and a median cadence is not worth computing.
MIN_FRAMES_PER_SERIES = 3


@dataclass(frozen=True)
class Gap:
    """One interval long enough to hide missing frames."""

    after_frame: int
    channel: int
    slice: int
    interval_ms: float
    missing_frames: int


@dataclass(frozen=True)
class DropReport:
    n_frames: int
    n_series: int
    span_s: float
    median_interval_ms: float
    #: The mean over the same intervals. Worth reporting next to the median
    #: because the two disagreeing is the signature of timestamp
    #: quantization: a real 62.5 fps acquisition here splits into 15 and
    #: 16 ms bins, median 16.0, mean 15.63.
    mean_interval_ms: float
    mad_interval_ms: float
    jitter_fraction: float
    #: Total frames/s implied by the instantaneous cadence -- what the
    #: acquisition was running at between drops. This is the number to feed
    #: back as ``Stream.fps`` with ``fps_source="measured"``.
    cadence_fps: float
    #: Total frames/s actually delivered over the whole span. Below
    #: ``cadence_fps`` by exactly the fraction that was dropped.
    throughput_fps: float
    n_gaps: int
    dropped_frames: int
    dropped_fraction: float
    largest_gap_frames: int
    timestamps_quantized: bool
    #: Series too short to analyse, and FrameKeys that carried no timestamp.
    short_series: int = 0
    frames_without_timestamp: int = 0
    #: MM's Summary ``Interval_ms`` -- what was requested, for the §C4
    #: comparison. ``None`` when unknown or when "as fast as possible".
    requested_interval_ms: float | None = None
    #: MM's Summary ``Frames`` -- timepoints **planned**. An acquisition
    #: stopped early is another silent failure: MM writes a complete-looking
    #: dataset and the Summary keeps advertising the frame count nobody got.
    planned_frames: int | None = None
    source: str | None = None
    gaps: tuple[Gap, ...] = field(default_factory=tuple)

    @property
    def frames_per_series(self) -> float:
        return self.n_frames / self.n_series if self.n_series else 0.0

    @property
    def completion_fraction(self) -> float | None:
        """Delivered timepoints over planned. ``None`` when unknown."""
        if not self.planned_frames:
            return None
        return self.frames_per_series / self.planned_frames

    @property
    def truncated(self) -> bool:
        """Did the acquisition stop before its planned frame count?

        Kept separate from ``contaminated``: a short run's lag times can be
        perfectly uniform. Both are worth looking at, for different reasons.
        """
        frac = self.completion_fraction
        return frac is not None and frac < 1.0

    @property
    def requested_vs_achieved(self) -> float | None:
        """How many times slower the delivered cadence is than the requested
        one. docs/06 §C4's session comes out at 3.0."""
        if not self.requested_interval_ms:
            return None
        return self.median_interval_ms / self.requested_interval_ms

    @property
    def irregular(self) -> bool:
        return (
            not self.timestamps_quantized
            and self.jitter_fraction > JITTER_WARN_FRACTION
        )

    @property
    def contaminated(self) -> bool:
        """Is there reason to distrust this acquisition's lag times?"""
        return self.dropped_frames > 0 or self.irregular

    def to_dict(self) -> dict:
        """Serialise including the derived verdicts.

        ``dataclasses.asdict`` emits fields only, so a consumer would get the
        numbers and have to re-derive ``contaminated`` / ``truncated`` /
        ``irregular`` itself -- and the whole point of computing them here is
        that nobody else has to. Same reason ``compute.gate.Verdict`` carries
        its own ``to_dict`` rather than leaning on ``asdict``.
        """
        out = asdict(self)
        out.update(
            frames_per_series=self.frames_per_series,
            completion_fraction=self.completion_fraction,
            truncated=self.truncated,
            requested_vs_achieved=self.requested_vs_achieved,
            irregular=self.irregular,
            contaminated=self.contaminated,
        )
        return out

    def summary_line(self, root: Path | str | None = None) -> str:
        """One line per acquisition, for a directory sweep.

        The bare filename is not enough to identify anything: MM names the
        file after the acquisition prefix, and this archive reuses prefixes
        across dated folders -- three separate acquisitions are all called
        ``OT0.01_exp10_100x_1x1_MMStack_Pos0_metadata.txt``. The containing
        folder is the part that distinguishes them, so it is always shown.
        """
        name = "(series)"
        if self.source:
            p = Path(self.source)
            if root is not None:
                try:
                    name = str(p.relative_to(root))
                except ValueError:
                    name = str(p)
            else:
                name = str(Path(p.parent.name) / p.name)
        state = (
            f"{self.dropped_frames} dropped in {self.n_gaps} gaps"
            if self.dropped_frames
            else ("irregular" if self.irregular else "clean")
        )
        if self.truncated:
            state += (
                f", truncated {self.frames_per_series:.0f}/{self.planned_frames}"
            )
        return (
            f"{name}: {self.n_frames} frames, cadence "
            f"{self.cadence_fps:.1f} fps, delivered "
            f"{self.throughput_fps:.1f} fps -- {state}"
        )


class NotEnoughFrames(ValueError):
    """Fewer timestamped frames than a cadence can be estimated from."""


def _mad(values: Sequence[float], centre: float) -> float:
    return median([abs(v - centre) for v in values]) if values else 0.0


def analyse(
    frames: Sequence[FrameTime],
    *,
    requested_interval_ms: float | None = None,
    planned_frames: int | None = None,
    frames_without_timestamp: int = 0,
    source: str | None = None,
) -> DropReport:
    """Detect drops in one acquisition's frame timestamps."""
    if len(frames) < MIN_FRAMES_PER_SERIES:
        raise NotEnoughFrames(
            f"need at least {MIN_FRAMES_PER_SERIES} timestamped frames, got "
            f"{len(frames)}"
        )

    series: dict[tuple[int, int], list[FrameTime]] = {}
    for f in frames:
        series.setdefault(f.series, []).append(f)

    gaps: list[Gap] = []
    cadences: list[float] = []
    steady_intervals: list[float] = []
    dropped = 0
    short_series = 0
    analysed_series = 0

    for key, group in series.items():
        group = sorted(group, key=lambda f: f.elapsed_ms)
        if len(group) < MIN_FRAMES_PER_SERIES:
            short_series += 1
            continue
        analysed_series += 1

        intervals = [
            (group[i + 1].elapsed_ms - group[i].elapsed_ms, group[i].frame)
            for i in range(len(group) - 1)
        ]
        cadence = median([dt for dt, _ in intervals])
        cadences.append(cadence)
        gap_threshold = max(
            GAP_RATIO * cadence,
            cadence + QUANTIZATION_GAP_MARGIN_STEPS * TIMESTAMP_RESOLUTION_MS,
        )

        for dt, after in intervals:
            ratio = dt / cadence if cadence > 0 else 1.0
            if dt >= gap_threshold:
                missing = max(1, round(ratio) - 1)
                dropped += missing
                gaps.append(
                    Gap(
                        after_frame=after,
                        channel=key[0],
                        slice=key[1],
                        interval_ms=dt,
                        missing_frames=missing,
                    )
                )
            else:
                steady_intervals.append(dt)

    if not analysed_series:
        raise NotEnoughFrames(
            f"no (channel, slice) series had {MIN_FRAMES_PER_SERIES} or more "
            "timestamped frames"
        )

    cadence_ms = median(cadences)
    mad = _mad(steady_intervals, cadence_ms)
    mean_ms = fmean(steady_intervals) if steady_intervals else cadence_ms
    elapsed = [f.elapsed_ms for f in frames]
    span_s = (max(elapsed) - min(elapsed)) / 1000.0

    cadence_fps = (1000.0 / cadence_ms) * analysed_series if cadence_ms > 0 else 0.0
    throughput_fps = (
        (len(frames) - analysed_series) / span_s if span_s > 0 else 0.0
    )

    return DropReport(
        n_frames=len(frames),
        n_series=analysed_series,
        span_s=span_s,
        median_interval_ms=cadence_ms,
        mean_interval_ms=mean_ms,
        mad_interval_ms=mad,
        jitter_fraction=mad / cadence_ms if cadence_ms > 0 else 0.0,
        cadence_fps=cadence_fps,
        throughput_fps=throughput_fps,
        n_gaps=len(gaps),
        dropped_frames=dropped,
        dropped_fraction=dropped / (len(frames) + dropped) if dropped else 0.0,
        largest_gap_frames=max((g.missing_frames for g in gaps), default=0),
        timestamps_quantized=cadence_ms
        < QUANTIZATION_GUARD_STEPS * TIMESTAMP_RESOLUTION_MS,
        short_series=short_series,
        frames_without_timestamp=frames_without_timestamp,
        requested_interval_ms=requested_interval_ms or None,
        planned_frames=planned_frames,
        source=source,
        gaps=tuple(sorted(gaps, key=lambda g: -g.missing_frames)),
    )


def analyse_file(path: Path | str) -> DropReport:
    """Scan one MM metadata file and report on it."""
    scan = read_frame_times(path)
    hints = read_summary_hints(path)
    return analyse(
        scan.frames,
        requested_interval_ms=hints.interval_ms,
        planned_frames=hints.frames,
        frames_without_timestamp=scan.frames_without_timestamp,
        source=scan.path,
    )


def scan_tree(
    root: Path | str, pattern: str = DEFAULT_GLOB
) -> Iterator[tuple[Path, DropReport | None, str | None]]:
    """Sweep a directory of acquisitions.

    Yields ``(path, report, error)`` -- exactly one of the last two is set,
    so a malformed or NDTiff-only acquisition is reported as skipped rather
    than silently dropped from the tally. docs/07-roadmap.md's "enumerate
    contaminated sessions" runs on top of this.
    """
    for path in iter_metadata_files(root, pattern):
        try:
            yield path, analyse_file(path), None
        except NotEnoughFrames as exc:
            yield path, None, str(exc)
        except OSError as exc:
            yield path, None, f"unreadable: {exc}"
