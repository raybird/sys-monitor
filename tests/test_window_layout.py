"""Layout width checks.

GTK 4 segfaults when a widget is constructed without a display, so the widget
tests run only when one is present. scripts/check.sh supplies one through Xvfb.
"""

from __future__ import annotations

import importlib.util
import os
import tempfile
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

    def test_process_rows_stay_shrinkable(self) -> None:
        self.app.cpu_process_list = Gtk.ListBox()
        self.app._populate_process_list(
            self.app.cpu_process_list,
            "an-unreasonably-long-process-command-name-that-would-overflow 98.5 14.2",
        )
        self.assertLess(
            self.minimum_width(self.app.cpu_process_list), self.BOUNDED_WIDTH
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


@unittest.skipUnless(HAS_DISPLAY, "no display available")
class DropdownContrastTests(unittest.TestCase):
    def test_scn001_light_dark_normal_hover_selected_contrast(self):
        import cairo
        from gi.repository import GLib

        def descendants(widget):
            yield widget
            child = widget.get_first_child()
            while child:
                yield from descendants(child)
                child = child.get_next_sibling()

        def luminance(channels):
            linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels]
            return sum(v * weight for v, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

        Gtk.init()
        settings = Gtk.Settings.get_default()
        old_dark = settings.get_property("gtk-application-prefer-dark-theme")
        old_theme = settings.get_property("gtk-theme-name")
        old_animations = settings.get_property("gtk-enable-animations")
        settings.set_property("gtk-enable-animations", False)
        app = freeze_watch.FreezeWatch(True)
        app._install_css()
        try:
            # The host theme and a fixed Adwaita, so the result does not
            # depend only on whatever theme the test machine happens to use.
            for theme, dark in [(name, dark) for name in dict.fromkeys((old_theme, "Adwaita"))
                                for dark in (False, True)]:
                settings.set_property("gtk-theme-name", theme)
                settings.set_property("gtk-application-prefer-dark-theme", dark)
                window = Gtk.Window()
                dropdown = Gtk.DropDown.new_from_strings(["即時監測", "非正常關機／疑似當機"])
                window.set_child(dropdown)
                window.present()
                while GLib.MainContext.default().pending():
                    GLib.MainContext.default().iteration(False)
                rows = [widget for widget in descendants(dropdown)
                        if widget.get_css_name() == "row" and widget.get_parent().get_css_name() == "listview"]
                self.assertEqual(len(rows), 2)
                for state in (Gtk.StateFlags.NORMAL, Gtk.StateFlags.PRELIGHT, Gtk.StateFlags.SELECTED):
                    row = rows[1]
                    row.unset_state_flags(Gtk.StateFlags.PRELIGHT | Gtk.StateFlags.SELECTED)
                    row.set_state_flags(state, False)
                    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 20, 20)
                    ancestors = []
                    ancestor = row
                    while ancestor:
                        ancestors.append(ancestor)
                        ancestor = ancestor.get_parent()
                    for ancestor in reversed(ancestors):
                        Gtk.render_background(ancestor.get_style_context(), cairo.Context(surface), 0, 0, 20, 20)
                    blue, green, red, alpha = surface.get_data()[:4]
                    self.assertEqual(alpha, 255)
                    bg = luminance([red / 255, green / 255, blue / 255])
                    # The label and the selection check mark both have to read.
                    marks = [widget for widget in descendants(row)
                             if widget.get_css_name() in ("label", "image")]
                    self.assertTrue(any(widget.get_css_name() == "label" for widget in marks))
                    for widget in marks:
                        foreground = widget.get_style_context().get_color()
                        fg = luminance([foreground.red, foreground.green, foreground.blue])
                        ratio = (max(bg, fg) + 0.05) / (min(bg, fg) + 0.05)
                        with self.subTest(theme=theme, dark=dark, state=state, part=widget.get_css_name()):
                            self.assertGreaterEqual(ratio, 4.5)
                window.destroy()
        finally:
            settings.set_property("gtk-application-prefer-dark-theme", old_dark)
            settings.set_property("gtk-theme-name", old_theme)
            settings.set_property("gtk-enable-animations", old_animations)


@unittest.skipUnless(HAS_DISPLAY, "no display available")
class ReportPreviewTests(unittest.TestCase):
    def test_scn006_preview_does_not_write_and_cancel_keeps_it_readonly(self):
        Gtk.init()
        app = freeze_watch.FreezeWatch(True)
        app.window = Gtk.Window()
        app.selected_incident = freeze_watch.Incident("2026-10-05T00:00:00+00:00", "UNCLEAN", "", None)
        old = freeze_watch.STATE_DIR
        with tempfile.TemporaryDirectory() as directory:
            freeze_watch.STATE_DIR = Path(directory)
            try:
                preview = app._preview_report(None)
                self.assertIsNotNone(preview)
                box = preview.get_child()
                view = box.get_first_child().get_child()
                buffer = view.get_buffer()
                text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
                self.assertIn("原因未確認", text)
                self.assertFalse(view.get_editable())
                self.assertEqual(list(Path(directory).iterdir()), [])
                status = box.get_first_child().get_next_sibling()
                chooser = app._save_report(preview, text, status)
                chooser.emit("response", Gtk.ResponseType.CANCEL)
                self.assertEqual(list(Path(directory).iterdir()), [])
                preview.destroy()
            finally:
                freeze_watch.STATE_DIR = old
                app.window.destroy()


if __name__ == "__main__":
    unittest.main()
