"""Real-time plumbing shared by the acquisition and control scripts.

Three pieces, all of them adapted from the Takatori-lab bacteria stack
(``bacteria3``), which has run them on the DMD rig. They are here rather than
inlined into ``config/tweezers/`` and ``config/micromanager/`` because each
one was already about to exist in two places.

:mod:`runtime.frames`
    :class:`~runtime.frames.Latest` -- one-slot frame ring.
    :class:`~runtime.frames.FrameSource` -- a thread that drains
    Micro-Manager's circular buffer and publishes only the newest frame, with
    an honest count of what it dropped. Replaces polling ``getLastImage()``
    and de-duplicating by pixel comparison.

:mod:`runtime.ticker`
    :func:`~runtime.ticker.sleep_until` and
    :class:`~runtime.ticker.Ticker` -- a fixed-period loop clock that sleeps
    then spins to each deadline, schedules from the tick index so it cannot
    drift, and makes the missed-period policy (``catch_up``) an explicit
    choice rather than an accident.

:mod:`runtime.shmview`
    :class:`~runtime.shmview.ShmPublisher` /
    :class:`~runtime.shmview.ShmSubscriber` -- a rate-capped shared-memory
    frame channel, so a live view can run in a second process instead of
    stealing the control loop's interpreter. Display only; nothing measurable
    comes out of it.

HOW THE THREE FIT TOGETHER
--------------------------
One process owns the camera and the trap. Inside it, a thread drains frames
and the main loop runs on a Ticker; a second process draws::

    #  acquiring process
    core.startContinuousSequenceAcquisition(0)
    with FrameSource(core) as source, ShmPublisher("kinetix_red") as view:
        source.wait(timeout=2.0)                  # first frame, or raise
        last = -1
        for tick in Ticker(dt=0.02, duration=10.0, warmup_k=5):
            frame = source.fresh(last)
            if frame is None:
                continue                          # no new frame this tick
            last = frame.seq
            ...                                   # track, control, record
            view.try_publish(frame.data, frame.t)
        print(ticker.report(), source.stats().report())

    #  viewing process, any time, no claim on the camera
    with ShmSubscriber("kinetix_red") as sub:
        while True:
            got = sub.poll()
            ...

Nothing here imports cv2, pymmcore or matplotlib, so the test suite that CI
runs on ``requirements.txt`` alone collects all of it.

STATUS: none of this has run against the instrument yet. The tests drive fake
cores and injected clocks, and each module's docstring lists what that leaves
unverified.
"""

from runtime.frames import Frame, FrameSource, FrameStats, Latest
from runtime.shmview import ShmPublisher, ShmSubscriber
from runtime.ticker import Tick, Ticker, sleep_until

__all__ = [
    "Frame",
    "FrameSource",
    "FrameStats",
    "Latest",
    "ShmPublisher",
    "ShmSubscriber",
    "Tick",
    "Ticker",
    "sleep_until",
]
