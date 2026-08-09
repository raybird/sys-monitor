"""Layout width checks.

GTK 4 segfaults when a widget is constructed without a display, so the widget
tests run only when one is present. scripts/check.sh supplies one through Xvfb.
"""

from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HAS_DISPLAY = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))

SPEC = importlib.util.spec_from_file_location(
    "freeze_watch_layout", REPO_ROOT / "src" / "freeze_watch.py"
)
assert SPEC and SPEC.loader
freeze_watch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(freeze_watch)

if HAS_DISPLAY:
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk

# Long enough that an unbounded label would demand far more than a laptop
# screen offers, which is exactly the shape of a real collector event line.
LONG_EVENT = (
    "2026-08-09T00:00:04+08:00\tSTART\tboot=0b987bd8 "
    "metrics=/home/someone/.local/state/freeze-monitor/"
    "metrics-2026-08-09T00-00-04+08-00-0b987bd8.tsv interval=10s flush=30s"
)


@unittest.skipUnless(HAS_DISPLAY, "no display available")
class LabelWidthTests(unittest.TestCase):
    """A label reports its full text width as its minimum unless told otherwise.

    The dashboard puts its content in a scrolled window whose horizontal policy
    is NEVER, which passes that minimum straight through to the window, and the
    two bottom columns are homogeneous so the widest one is applied twice. One
    long event line was enough to force a 2624px window onto an 1854px screen.
    """

    BOUNDED_WIDTH = 400

    def setUp(self) -> None:
        Gtk.init()

    @staticmethod
    def minimum_width(widget) -> int:
        return widget.measure(Gtk.Orientation.HORIZONTAL, -1)[0]

    def test_a_plain_label_demands_its_whole_text(self) -> None:
        label = freeze_watch.FreezeWatch._label(LONG_EVENT)
        self.assertGreater(self.minimum_width(label), self.BOUNDED_WIDTH)

    def test_an_ellipsized_label_can_shrink(self) -> None:
        label = freeze_watch.FreezeWatch._label(LONG_EVENT, ellipsize=True)
        self.assertLess(self.minimum_width(label), self.BOUNDED_WIDTH)


@unittest.skipUnless(HAS_DISPLAY, "no display available")
class RowWidthTests(unittest.TestCase):
    """The rows built from collector output must stay shrinkable."""

    BOUNDED_WIDTH = 400

    def setUp(self) -> None:
        Gtk.init()
        self.app = freeze_watch.FreezeWatch(start_hidden=True)

    @staticmethod
    def minimum_width(widget) -> int:
        return widget.measure(Gtk.Orientation.HORIZONTAL, -1)[0]

    def test_event_rows_stay_shrinkable(self) -> None:
        self.app.event_list = Gtk.ListBox()
        self.app._append_event_row(LONG_EVENT)
        self.assertLess(
            self.minimum_width(self.app.event_list), self.BOUNDED_WIDTH
        )

    def test_container_rows_stay_shrinkable(self) -> None:
        self.app.container_list = Gtk.ListBox()
        self.app._append_container_row(
            {
                "container": "a-deployment-with-an-unreasonably-long-container-name",
                "cpu_pct": "0.00%",
                "memory_usage": "696KiB / 31GiB",
                "zombies": "0",
            }
        )
        self.assertLess(
            self.minimum_width(self.app.container_list), self.BOUNDED_WIDTH
        )


@unittest.skipUnless(HAS_DISPLAY, "no display available")
class ScrollRestoreTests(unittest.TestCase):
    """Refreshing must not walk the view back up the page.

    Emptying a list shrinks the scrolled content, which clamps the scroll
    position to the smaller extent, and refilling it does not put the position
    back. Refreshing every two seconds therefore dragged the view upwards
    whenever anyone had scrolled down.
    """

    def setUp(self) -> None:
        Gtk.init()

    @staticmethod
    def adjustment(value: float, upper: float, page: float):
        return Gtk.Adjustment(
            value=value, lower=0, upper=upper, page_size=page
        )

    def test_puts_the_position_back(self) -> None:
        adjustment = self.adjustment(200, 1000, 400)
        freeze_watch.FreezeWatch._restore_scroll(adjustment, 500)
        self.assertEqual(adjustment.get_value(), 500)

    def test_stops_running_after_one_pass(self) -> None:
        adjustment = self.adjustment(0, 1000, 400)
        self.assertIs(
            freeze_watch.FreezeWatch._restore_scroll(adjustment, 100), False
        )


class ContainerSignatureTests(unittest.TestCase):
    """Deciding whether a rebuild is needed at all needs no display."""

    @staticmethod
    def row(name: str, cpu: str = "0.00%", memory: str = "1MiB") -> dict[str, str]:
        return {
            "container": name,
            "cpu_pct": cpu,
            "memory_usage": memory,
            "zombies": "0",
            "timestamp": "ignored",
        }

    def test_identical_rows_compare_equal(self) -> None:
        self.assertEqual(
            freeze_watch.container_signature([self.row("a"), self.row("b")]),
            freeze_watch.container_signature([self.row("a"), self.row("b")]),
        )

    def test_a_changed_reading_differs(self) -> None:
        self.assertNotEqual(
            freeze_watch.container_signature([self.row("a")]),
            freeze_watch.container_signature([self.row("a", cpu="9.90%")]),
        )

    def test_order_matters(self) -> None:
        self.assertNotEqual(
            freeze_watch.container_signature([self.row("a"), self.row("b")]),
            freeze_watch.container_signature([self.row("b"), self.row("a")]),
        )

    def test_a_field_that_is_not_rendered_is_ignored(self) -> None:
        noisy = self.row("a")
        noisy["timestamp"] = "changes every sample"
        self.assertEqual(
            freeze_watch.container_signature([self.row("a")]),
            freeze_watch.container_signature([noisy]),
        )


class ClampTests(unittest.TestCase):
    """Pure sizing arithmetic, so it needs no display."""

    def test_keeps_the_preferred_size_on_a_large_screen(self) -> None:
        self.assertEqual(freeze_watch.clamp_window_size(2560, 1440), (1040, 760))

    def test_shrinks_to_fit_a_small_screen(self) -> None:
        self.assertEqual(freeze_watch.clamp_window_size(1366, 768), (1040, 688))

    def test_never_goes_below_the_minimum(self) -> None:
        self.assertEqual(freeze_watch.clamp_window_size(640, 480), (720, 540))


if __name__ == "__main__":
    unittest.main()
