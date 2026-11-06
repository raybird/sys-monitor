"""以虛擬顯示器擷取 issue 1 選單與報告預覽。"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("capture_watch", ROOT / "src/freeze_watch.py")
watch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watch)
output = Path(sys.argv[1])
output.mkdir(parents=True, exist_ok=True)


def descendants(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from descendants(child)
        child = child.get_next_sibling()


def capture(name):
    loop = GLib.MainLoop()

    def save():
        subprocess.run(["import", "-window", "root", "-crop", "1000x650+0+0", str(output / name)], check=True)
        loop.quit()
        return False

    GLib.timeout_add(500, save)
    loop.run()


Gtk.init()
settings = Gtk.Settings.get_default()
settings.set_property("gtk-enable-animations", False)
app = watch.FreezeWatch(True)
app._install_css()
for dark in (False, True):
    settings.set_property("gtk-application-prefer-dark-theme", dark)
    window = Gtk.Window(title="Freeze Watch 選單驗證")
    window.set_default_size(680, 220)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
    box.set_margin_top(20)
    box.set_margin_start(20)
    window.set_child(box)
    box.append(Gtk.Label(label="selected／hover／正常：三種狀態"))
    dropdown = Gtk.DropDown.new_from_strings(["選取：非正常關機／疑似當機", "滑鼠停留：取樣停擺", "正常：即時監測"])
    box.append(dropdown)
    window.present()
    popover = next(w for w in descendants(dropdown) if w.get_css_name() == "popover")
    popover.popup()
    rows = [w for w in descendants(popover) if w.get_css_name() == "row"]
    rows[1].set_state_flags(Gtk.StateFlags.PRELIGHT, False)
    capture("dropdown-dark.png" if dark else "dropdown-light.png")
    window.destroy()

app.window = Gtk.Window()
app.selected_incident = watch.Incident("2026-10-05T00:00:00+08:00", "UNCLEAN", "last_sample=unknown", None)
preview = app._preview_report(None)
capture("report-preview.png")
preview.destroy()
app.window.destroy()
