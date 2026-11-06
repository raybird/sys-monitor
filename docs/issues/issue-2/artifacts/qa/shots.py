import os, sys
sys.path.insert(0, '/home/kevin/Documents/RCodes/sys-monitor/src')
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Graphene
import freeze_watch as fw
out = sys.argv[1]

def pump(n=40):
    ctx = GLib.MainContext.default()
    for _ in range(n):
        while ctx.pending():
            ctx.iteration(False)
        GLib.usleep(20000)

def descendants(w):
    yield w
    c = w.get_first_child()
    while c:
        yield from descendants(c)
        c = c.get_next_sibling()

def shot(widget, path):
    w, h = widget.get_width(), widget.get_height()
    paintable = Gtk.WidgetPaintable.new(widget)
    snap = Gtk.Snapshot()
    paintable.snapshot(snap, w, h)
    node = snap.to_node()
    tex = widget.get_native().get_renderer().render_texture(node, Graphene.Rect().init(0, 0, w, h))
    tex.save_to_png(path)
    print('saved', path, w, h)

Gtk.init()
settings = Gtk.Settings.get_default()
app = fw.FreezeWatch(start_hidden=False)
app._install_css()
app._build_window()
app.window.set_default_size(1040, 1400)
app.window.present()
app.refresh(); pump()
print('incidents', [i.label for i in app.incidents])
for mode in ('live', 'review'):
    if mode == 'review':
        app.incident_dropdown.set_selected(1); pump(); app.refresh(); pump()
    for ex in [w for w in descendants(app.container_list) if isinstance(w, Gtk.Expander)][:1]:
        ex.set_expanded(True)
    pump()
    labels = [w.get_text() for w in descendants(app.container_list) if isinstance(w, Gtk.Label)]
    print(mode, 'labels:', [l for l in labels if l][:40])
    print(mode, 'warm rows:', [w.get_text() for w in descendants(app.container_list) if isinstance(w, Gtk.Label) and w.has_css_class('warm')]); print(mode, 'unknown rows:', [w.get_text() for w in descendants(app.container_list) if isinstance(w, Gtk.Label) and w.has_css_class('unknown')])
    print(mode, 'hero_docker:', app.labels['hero_docker'].get_text() if 'hero_docker' in app.labels else None)
    for theme, dark in (('Adwaita', False), ('Adwaita', True)):
        settings.set_property('gtk-theme-name', theme)
        settings.set_property('gtk-application-prefer-dark-theme', dark)
        pump()
        tag = 'dark' if dark else 'light'
        shot(app.window, f'{out}/{mode}-{tag}-window.png')
        shot(app.container_list, f'{out}/{mode}-{tag}-containers.png')
