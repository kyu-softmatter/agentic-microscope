"""Tests for the --publish / --attach pair added to live_view.py.

Only the parts that need no camera and no window: argument validation, and
the branch where no publisher is running. The display loop itself needs
highgui and a real segment, so it is not covered here -- what is covered is
that ``--attach`` cannot reach the Micro-Manager import at all, which is the
property that makes it safe to run beside an acquisition.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def live_view():
    """Import live_view.py by path -- config/ has no package __init__.

    ``live_view`` imports tkinter at module scope for its default display
    path, so a Python built without ``_tkinter`` cannot import it at all.
    Skipping is right rather than failing: none of the tests here exercise Tk,
    and the badge workflow runs on ubuntu/macos/windows runners whose tkinter
    availability is the runner image's business, not this repository's.
    """
    pytest.importorskip("tkinter",
                        reason="live_view imports tkinter at module scope")
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    path = REPO_ROOT / "config" / "micromanager" / "live_view.py"
    spec = importlib.util.spec_from_file_location("live_view_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_main(live_view, argv, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["live_view.py", *argv])
    return live_view.main()


# --------------------------------------------------------------------------
# argument validation
# --------------------------------------------------------------------------


def test_neither_cfg_nor_attach_is_refused(live_view, monkeypatch):
    with pytest.raises(SystemExit) as exc:
        run_main(live_view, [], monkeypatch)
    assert exc.value.code == 2


def test_attach_with_cfg_is_refused(live_view, monkeypatch, capsys):
    """The two halves are mutually exclusive: --attach opens no camera, so a
    system configuration has nothing to act on. Accepting both silently would
    invite exactly the second device claim this is meant to avoid."""
    with pytest.raises(SystemExit) as exc:
        run_main(live_view, ["--attach", "seg", "--cfg", "some.cfg"], monkeypatch)
    assert exc.value.code == 2
    assert "opens no camera" in capsys.readouterr().err


@pytest.mark.parametrize(
    "flag, value",
    [("--line", "GREEN"), ("--roi", "512"), ("--binning", "2x2"),
     ("--exposure-ms", "5")],
)
def test_attach_refuses_flags_that_touch_hardware(live_view, monkeypatch,
                                                  capsys, flag, value):
    args = ["--attach", "seg", flag, value]
    if flag == "--line":
        args += ["--intensity", "100"]   # --line and --intensity go together
    with pytest.raises(SystemExit) as exc:
        run_main(live_view, args, monkeypatch)
    assert exc.value.code == 2
    assert "acquires" in capsys.readouterr().err


def test_line_without_intensity_is_still_refused(live_view, monkeypatch):
    """The pre-existing pairing rule, unchanged by this addition."""
    with pytest.raises(SystemExit) as exc:
        run_main(live_view, ["--cfg", "x.cfg", "--line", "GREEN"], monkeypatch)
    assert exc.value.code == 2


# --------------------------------------------------------------------------
# the attach branch
# --------------------------------------------------------------------------


def test_attach_returns_before_importing_micro_manager(live_view, monkeypatch):
    """The safety property: a viewer must not be able to load a device even
    by accident. Poisoning the import proves the branch returns first."""
    monkeypatch.setitem(sys.modules, "pymmcore_plus", None)  # import -> error
    called = {}

    def fake_attach(segment, display_px, *a, **k):
        called["segment"] = segment
        called["display_px"] = display_px
        return 0

    monkeypatch.setattr(live_view, "attach_loop", fake_attach)
    assert run_main(live_view, ["--attach", "seg", "--display", "300"],
                    monkeypatch) == 0
    assert called == {"segment": "seg", "display_px": 300}


def test_attach_with_no_publisher_exits_two_with_a_diagnostic(live_view, capsys):
    """A viewer pointed at a name nobody publishes fails loudly rather than
    showing a blank window forever. And it does so without needing cv2 --
    "nobody is publishing" must not be reported as a missing dependency."""
    monkeypatch_free_name = "amtest_no_publisher_ever_12345"
    assert live_view.attach_loop(monkeypatch_free_name, 400,
                                 timeout_s=0.3) == 2
    assert "publisher" in capsys.readouterr().err


def test_attach_loop_needs_no_cv2_to_report_a_missing_publisher(live_view,
                                                                monkeypatch):
    """Pins the import order inside attach_loop: the subscriber is tried
    first, so the cv2 import is never reached on this path."""
    monkeypatch.setitem(sys.modules, "cv2", None)  # any use -> error
    assert live_view.attach_loop("amtest_no_publisher_ever_67890", 400,
                                 timeout_s=0.3) == 2


# --------------------------------------------------------------------------
# the display loop, with cv2 stubbed out
# --------------------------------------------------------------------------


class StubCv2:
    """Enough of cv2 for attach_loop, recording what it was asked to draw.

    ``waitKey`` returns ESC after ``esc_after`` calls, which is how the loop
    is made to terminate. Drawing is recorded rather than performed, so no
    window is opened and the test runs headless.
    """

    WINDOW_AUTOSIZE = 1
    COLOR_GRAY2BGR = 8
    FONT_HERSHEY_SIMPLEX = 0
    LINE_AA = 16
    WND_PROP_VISIBLE = 4

    class error(Exception):
        pass

    def __init__(self, esc_after: int = 3):
        self.esc_after = esc_after
        self.waits = 0
        self.shown = []
        self.texts = []
        self.destroyed = False

    def namedWindow(self, *a, **k):  # noqa: N802 - cv2 spelling
        pass

    def cvtColor(self, img, _code):  # noqa: N802
        import numpy as np
        return np.dstack([img, img, img])

    def putText(self, _img, text, *a, **k):  # noqa: N802
        self.texts.append(text)

    def imshow(self, _win, img):
        self.shown.append(img.shape)

    def waitKey(self, _ms):  # noqa: N802
        self.waits += 1
        return 27 if self.waits >= self.esc_after else -1

    def getWindowProperty(self, *a, **k):  # noqa: N802
        return 1.0

    def destroyAllWindows(self):  # noqa: N802
        self.destroyed = True


@pytest.fixture
def segment_name():
    import os
    from itertools import count
    if not hasattr(segment_name, "_c"):
        segment_name._c = count()
    return f"amtest_lv_{os.getpid()}_{next(segment_name._c)}"


def test_attach_loop_displays_a_published_frame(live_view, monkeypatch,
                                                segment_name, capsys):
    """The display path, end to end, without a window: a real segment in,
    a recorded imshow out."""
    import numpy as np

    from runtime.shmview import ShmPublisher

    stub = StubCv2(esc_after=3)
    monkeypatch.setitem(sys.modules, "cv2", stub)

    with ShmPublisher(segment_name, max_w=64) as pub:
        pub.try_publish(np.full((256, 256), 0x4000, np.uint16), ts=1.5)
        assert live_view.attach_loop(segment_name, 400, timeout_s=2.0) == 0

    assert stub.shown, "nothing was handed to imshow"
    assert stub.shown[0] == (64, 64, 3), "the published 64x64, in colour"
    assert stub.destroyed, "the window was not cleaned up"
    overlay = " ".join(stub.texts)
    assert "256x256 sensor" in overlay, "the sensor shape has to be on screen"
    assert "published 1/4" in overlay
    assert "t=1.50" in overlay
    assert "1 frames shown" in capsys.readouterr().out


def test_attach_loop_marks_a_frozen_feed_as_stale(live_view, monkeypatch,
                                                  segment_name):
    """A publisher that exited leaves a valid but frozen mapping on Windows,
    which is indistinguishable from an idle one at the poll. The viewer has to
    say so rather than present a stale frame as live."""
    import numpy as np

    from runtime.shmview import ShmPublisher, ShmSubscriber

    stub = StubCv2(esc_after=6)
    monkeypatch.setitem(sys.modules, "cv2", stub)

    # A clock that runs 2 s per call, so `age` crosses the 3 s threshold a
    # couple of iterations after the one frame arrives -- which is the real
    # sequence, sped up. A *constant* clock would leave age at 0 forever and
    # the test would pass for the wrong reason.
    ticking_counter = iter(range(0, 1000, 2))
    real_init = ShmSubscriber.__init__

    def patched(self, name, **kwargs):
        kwargs["now"] = lambda: float(next(ticking_counter))
        real_init(self, name, **kwargs)

    monkeypatch.setattr(ShmSubscriber, "__init__", patched)

    with ShmPublisher(segment_name, max_w=32) as pub:
        pub.try_publish(np.zeros((32, 32), np.uint16), ts=0.0)
        assert live_view.attach_loop(segment_name, 400, timeout_s=2.0) == 0

    assert any(t.startswith("STALE") for t in stub.texts), \
        f"no staleness warning drawn; texts were {stub.texts}"
    assert any("publisher idle or gone" in t for t in stub.texts), \
        "the banner has to say what stale means"


def test_attach_loop_draws_the_stale_banner_only_once_per_transition(
        live_view, monkeypatch, segment_name):
    """Redrawing every iteration would burn a core showing an unchanging
    frame, so the redraw is gated on a new frame or a change of stale state."""
    import numpy as np

    from runtime.shmview import ShmPublisher, ShmSubscriber

    stub = StubCv2(esc_after=40)
    monkeypatch.setitem(sys.modules, "cv2", stub)

    counter = iter(range(0, 10_000, 2))
    real_init = ShmSubscriber.__init__

    def patched(self, name, **kwargs):
        kwargs["now"] = lambda: float(next(counter))
        real_init(self, name, **kwargs)

    monkeypatch.setattr(ShmSubscriber, "__init__", patched)

    with ShmPublisher(segment_name, max_w=32) as pub:
        pub.try_publish(np.zeros((32, 32), np.uint16), ts=0.0)
        live_view.attach_loop(segment_name, 400, timeout_s=2.0)

    stale_banners = [t for t in stub.texts if t.startswith("STALE")]
    assert len(stale_banners) == 1, (
        f"expected one banner for one transition, got {len(stale_banners)} "
        f"over {stub.waits} iterations")


def test_attach_loop_exits_cleanly_when_the_window_is_closed(live_view,
                                                             monkeypatch,
                                                             segment_name):
    import numpy as np

    from runtime.shmview import ShmPublisher

    stub = StubCv2(esc_after=1000)          # never returns ESC
    monkeypatch.setattr(stub, "getWindowProperty",
                        lambda *a, **k: 0.0)  # window closed
    monkeypatch.setitem(sys.modules, "cv2", stub)

    with ShmPublisher(segment_name, max_w=32) as pub:
        pub.try_publish(np.zeros((32, 32), np.uint16), ts=0.0)
        assert live_view.attach_loop(segment_name, 400, timeout_s=2.0) == 0
    assert stub.destroyed


# --------------------------------------------------------------------------
# --publish implies --cv2-window
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def help_text(live_view) -> str:
    """``--help`` output. argparse writes it and exits, so capture both."""
    import contextlib
    import io

    buf = io.StringIO()
    saved = sys.argv
    try:
        sys.argv = ["live_view.py", "--help"]
        with contextlib.redirect_stdout(buf), pytest.raises(SystemExit):
            live_view.main()
    finally:
        sys.argv = saved
    return buf.getvalue()


def test_publish_is_documented_as_display_only(help_text):
    """The warning has to be on the flag itself, not only in a module
    docstring nobody reads at the command line."""
    assert "--publish" in help_text
    assert "DISPLAY ONLY" in help_text
    assert "10 fps" in help_text


def test_attach_help_names_the_other_half(help_text):
    assert "--attach" in help_text
    assert "--publish" in help_text


def test_cfg_help_says_it_is_optional_only_with_attach(help_text):
    assert "Required unless --attach" in help_text
