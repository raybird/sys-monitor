#!/usr/bin/env python3
"""A lightweight local dashboard for the freeze-monitor collector."""

from __future__ import annotations

import csv
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk


APP_ID = "com.raybird.FreezeWatch"
NORMAL_ICON_NAME = f"{APP_ID}-symbolic"
WARNING_ICON_NAME = f"{APP_ID}-warning-symbolic"
SNI_INTERFACE = "org.kde.StatusNotifierItem"
DBUS_PROPERTIES = "org.freedesktop.DBus.Properties"
SNI_PATH = "/StatusNotifierItem"
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "freeze-monitor"
HWMON_ROOT = Path(os.environ.get("FREEZE_WATCH_HWMON_ROOT", "/sys/class/hwmon"))

# Kept in step with the same lists in the freeze-monitor collector.
CPU_TEMP_SENSORS = ("k10temp", "coretemp", "zenpower", "k8temp", "cpu_thermal")
GPU_TEMP_SENSORS = ("amdgpu", "radeon", "nouveau")
NVME_TEMP_SENSORS = ("nvme",)
ICON_THEME_PATH = Path(
    os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")
) / "icons"

METRICS_FIELDS = [
    "timestamp", "epoch", "uptime_s", "load1", "load5", "load15",
    "mem_available_kib", "swap_used_kib", "root_used_pct", "cpu_temp_mC",
    "gpu_temp_mC", "nvme_temp_mC", "gpu_busy_pct", "cpu_psi_avg10",
    "memory_psi_avg10", "io_psi_avg10", "docker_state",
    "docker_containers", "docker_tasks", "tracked_containers",
    "tracked_tasks", "tracked_processes", "tracked_zombies", "top_processes",
]
DOCKER_FIELDS = [
    "timestamp", "epoch", "container", "is_tracked_project", "cpu_pct",
    "memory_usage", "tasks", "processes", "zombies", "oom_killed",
    "restart_count",
]


def tail_text(path: Path, byte_limit: int = 160_000) -> str:
    """Read only the useful tail of an append-only log."""
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - byte_limit))
            data = handle.read()
        return data.decode("utf-8", errors="replace")
    except OSError:
        return ""


def newest_file(pattern: str) -> Path | None:
    files = list(STATE_DIR.glob(pattern))
    if not files:
        return None
    return max(files, key=lambda item: item.stat().st_mtime)


def read_tsv_tail(pattern: str, fields: list[str]) -> list[dict[str, str]]:
    path = newest_file(pattern)
    if path is None:
        return []

    lines = tail_text(path).splitlines()
    if not lines:
        return []

    rows = list(csv.DictReader(lines, fieldnames=fields, delimiter="\t"))
    return [row for row in rows if row.get("timestamp") and row["timestamp"] != "timestamp"]


def as_float(value: Any) -> float | None:
    try:
        if value in (None, "", "NA"):
            return None
        return float(str(value).rstrip("%"))
    except (TypeError, ValueError):
        return None


def as_int(value: Any) -> int | None:
    number = as_float(value)
    return int(number) if number is not None else None


def format_temperature(value: float | None) -> str:
    return "—" if value is None else f"{value:.0f}°C"


def format_gib(kib: int | None) -> str:
    return "—" if kib is None else f"{kib / 1024 / 1024:.1f} GiB"


def read_hwmon_temperature(*wanted_names: str) -> float | None:
    """Return the first named driver that is present, in preference order."""
    for wanted_name in wanted_names:
        for hwmon in sorted(HWMON_ROOT.glob("hwmon*")):
            try:
                if (hwmon / "name").read_text().strip() != wanted_name:
                    continue
                raw_value = (hwmon / "temp1_input").read_text().strip()
                return int(raw_value) / 1000
            except (OSError, ValueError):
                continue
    return None


def direct_temperatures() -> dict[str, float | None]:
    return {
        "cpu": read_hwmon_temperature(*CPU_TEMP_SENSORS),
        "gpu": read_hwmon_temperature(*GPU_TEMP_SENSORS),
        "nvme": read_hwmon_temperature(*NVME_TEMP_SENSORS),
    }


def temperature_level(temperatures: dict[str, float | None]) -> str:
    values = [value for value in temperatures.values() if value is not None]
    peak = max(values) if values else 0
    if peak >= 95:
        return "danger"
    if peak >= 85:
        return "hot"
    if peak >= 70:
        return "warm"
    return "safe"


def level_copy(level: str) -> tuple[str, str]:
    return {
        "danger": ("危險溫度", "請立即降低負載並檢查散熱"),
        "hot": ("高溫警戒", "已接近過熱範圍"),
        "warm": ("溫度偏高", "持續觀察負載與風扇"),
        "safe": ("穩定監測中", "溫度與資源目前正常"),
    }[level]


class StatusNotifierItem(dbus.service.Object):
    """Minimal SNI implementation, compatible with Ubuntu AppIndicators."""

    def __init__(self, on_activate):
        self.bus = dbus.SessionBus()
        super().__init__(self.bus, SNI_PATH)
        self.on_activate = on_activate
        self.label = "CPU —"
        self.title = "Freeze Watch"
        self.icon_name = NORMAL_ICON_NAME
        self.status = "Active"
        self._register()

    def _register(self) -> None:
        try:
            watcher = self.bus.get_object(
                "org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher"
            )
            watcher.RegisterStatusNotifierItem(
                SNI_PATH,
                dbus_interface="org.kde.StatusNotifierWatcher",
            )
        except dbus.DBusException:
            # The dashboard remains useful if the shell extension restarts.
            GLib.timeout_add_seconds(10, self._retry_register)

    def _retry_register(self) -> bool:
        self._register()
        return False

    def _properties(self) -> dict[str, Any]:
        return {
            "Category": dbus.String("Hardware"),
            "Id": dbus.String("freeze-watch"),
            "Title": dbus.String(self.title),
            "Status": dbus.String(self.status),
            "WindowId": dbus.Int32(0),
            "IconThemePath": dbus.String(str(ICON_THEME_PATH)),
            "Menu": dbus.ObjectPath("/NO_DBUSMENU"),
            "ItemIsMenu": dbus.Boolean(False),
            "IconName": dbus.String(self.icon_name),
            "IconPixmap": dbus.Array([], signature="(iiay)"),
            "OverlayIconName": dbus.String(""),
            "OverlayIconPixmap": dbus.Array([], signature="(iiay)"),
            "AttentionIconName": dbus.String(WARNING_ICON_NAME),
            "AttentionIconPixmap": dbus.Array([], signature="(iiay)"),
            "AttentionMovieName": dbus.String(""),
            "XAyatanaLabel": dbus.String(self.label),
            "XAyatanaLabelGuide": dbus.String("CPU 000°"),
            "IconAccessibleDesc": dbus.String(self.title),
        }

    @dbus.service.method(
        DBUS_PROPERTIES, in_signature="ss", out_signature="v"
    )
    def Get(self, interface_name: str, property_name: str):
        if interface_name != SNI_INTERFACE or property_name not in self._properties():
            raise dbus.exceptions.DBusException(
                "org.freedesktop.DBus.Error.InvalidArgs",
                f"Unknown property: {interface_name}.{property_name}",
            )
        return self._properties()[property_name]

    @dbus.service.method(
        DBUS_PROPERTIES, in_signature="s", out_signature="a{sv}"
    )
    def GetAll(self, interface_name: str):
        if interface_name != SNI_INTERFACE:
            return dbus.Dictionary({}, signature="sv")
        return dbus.Dictionary(self._properties(), signature="sv")

    @dbus.service.signal(DBUS_PROPERTIES, signature="sa{sv}as")
    def PropertiesChanged(self, interface_name, changed_properties, invalidated):
        pass

    @dbus.service.method(SNI_INTERFACE, in_signature="ii", out_signature="")
    def Activate(self, _x: int, _y: int) -> None:
        GLib.idle_add(self.on_activate)

    @dbus.service.method(SNI_INTERFACE, in_signature="ii", out_signature="")
    def SecondaryActivate(self, _x: int, _y: int) -> None:
        GLib.idle_add(self.on_activate)

    @dbus.service.method(SNI_INTERFACE, in_signature="ii", out_signature="")
    def ContextMenu(self, _x: int, _y: int) -> None:
        GLib.idle_add(self.on_activate)

    @dbus.service.method(SNI_INTERFACE, in_signature="is", out_signature="")
    def Scroll(self, _delta: int, _orientation: str) -> None:
        pass

    @dbus.service.method(SNI_INTERFACE, in_signature="s", out_signature="")
    def ProvideXdgActivationToken(self, _token: str) -> None:
        pass

    @dbus.service.method(SNI_INTERFACE, in_signature="u", out_signature="")
    def XAyatanaSecondaryActivate(self, _timestamp: int) -> None:
        GLib.idle_add(self.on_activate)

    def update(self, temperatures: dict[str, float | None], level: str) -> None:
        cpu = temperatures.get("cpu")
        self.label = f"CPU {cpu:.0f}°" if cpu is not None else "CPU —"
        self.title = (
            f"Freeze Watch — CPU {format_temperature(cpu)} · "
            f"GPU {format_temperature(temperatures.get('gpu'))} · "
            f"NVMe {format_temperature(temperatures.get('nvme'))}"
        )
        self.icon_name = (
            WARNING_ICON_NAME
            if level in ("hot", "danger")
            else NORMAL_ICON_NAME
        )
        self.PropertiesChanged(
            SNI_INTERFACE,
            dbus.Dictionary(
                {
                    "XAyatanaLabel": dbus.String(self.label),
                    "Title": dbus.String(self.title),
                    "IconName": dbus.String(self.icon_name),
                    "IconAccessibleDesc": dbus.String(self.title),
                },
                signature="sv",
            ),
            dbus.Array([], signature="s"),
        )


class ThermalRibbon(Gtk.DrawingArea):
    """Three quiet thermal lanes: CPU, GPU and NVMe over recent samples."""

    def __init__(self):
        super().__init__()
        self.history: list[dict[str, float | None]] = []
        self.set_content_height(76)
        self.set_size_request(-1, 76)
        self.set_hexpand(True)
        self.set_vexpand(False)
        self.set_valign(Gtk.Align.START)
        self.set_draw_func(self._draw)

    def set_history(self, rows: list[dict[str, str]]) -> None:
        self.history = [
            {
                "cpu": self._from_millidegree(row.get("cpu_temp_mC")),
                "gpu": self._from_millidegree(row.get("gpu_temp_mC")),
                "nvme": self._from_millidegree(row.get("nvme_temp_mC")),
            }
            for row in rows[-180:]
        ]
        self.queue_draw()

    @staticmethod
    def _from_millidegree(value: str | None) -> float | None:
        number = as_float(value)
        return number / 1000 if number is not None else None

    @staticmethod
    def _colour(value: float | None) -> tuple[float, float, float]:
        if value is None:
            return 0.18, 0.22, 0.27
        if value >= 95:
            return 0.88, 0.25, 0.20
        if value >= 85:
            return 0.94, 0.52, 0.17
        if value >= 70:
            return 0.80, 0.66, 0.20
        return 0.27, 0.70, 0.80

    def _draw(self, _area, context, width: int, height: int) -> None:
        context.set_source_rgb(0.055, 0.071, 0.09)
        context.paint()

        lanes = ("cpu", "gpu", "nvme")
        lane_height = height / len(lanes)
        for index, name in enumerate(lanes):
            y = index * lane_height
            context.set_source_rgba(0.55, 0.67, 0.75, 0.14)
            context.rectangle(0, y + lane_height - 1, width, 1)
            context.fill()
            context.set_source_rgba(0.82, 0.9, 0.94, 0.55)
            context.set_font_size(10)
            context.move_to(8, y + 14)
            context.show_text(name.upper())

        if not self.history:
            return

        step = max(width / len(self.history), 1)
        for position, sample in enumerate(self.history):
            x = position * step
            for index, name in enumerate(lanes):
                red, green, blue = self._colour(sample[name])
                context.set_source_rgb(red, green, blue)
                context.rectangle(x, index * lane_height + 2, step + 0.8, lane_height - 4)
                context.fill()


class FreezeWatch(Gtk.Application):
    def __init__(self, start_hidden: bool):
        super().__init__(application_id=APP_ID)
        self.start_hidden = start_hidden
        self.window: Gtk.ApplicationWindow | None = None
        self.tray: StatusNotifierItem | None = None
        self.ribbon: ThermalRibbon | None = None
        self.labels: dict[str, Gtk.Label] = {}
        self.temperature_cards: dict[str, tuple[Gtk.Label, Gtk.Label, Gtk.Widget]] = {}
        self.container_list: Gtk.ListBox | None = None
        self.event_list: Gtk.ListBox | None = None
        self._initial_activation = True

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.hold()
        self._install_css()
        self.tray = StatusNotifierItem(self.present_dashboard)
        GLib.timeout_add_seconds(2, self.refresh)

    def do_activate(self):
        if self.window is None:
            self._build_window()
            self.refresh()
        if not self.start_hidden or not self._initial_activation:
            self.window.present()
        self._initial_activation = False

    def _install_css(self) -> None:
        css = b"""
            window { background: #10151a; color: #dfe8ed; }
            label { color: #dfe8ed; }
            .dashboard { padding: 22px 26px 28px; }
            .hero { background: #162129; border: 1px solid #2a424e;
                    border-radius: 14px; padding: 20px 22px; }
            .eyebrow { color: #77bfce; font-size: 11px; font-weight: 700;
                       letter-spacing: 1.7px; }
            .hero-value { font-size: 42px; font-weight: 700; letter-spacing: -1px; }
            .hero-title { font-size: 19px; font-weight: 700; }
            .muted { color: #9badb7; font-size: 12px; }
            .metric-card { background: #151d23; border: 1px solid #28343c;
                           border-radius: 10px; padding: 14px 16px; }
            .metric-key { color: #91a4af; font-size: 11px; font-weight: 700;
                          letter-spacing: 1.2px; }
            .metric-value { color: #e7f0f4; font-size: 25px; font-weight: 700; }
            .section-title { color: #dcebf1; font-size: 14px; font-weight: 700; }
            .list-row { padding: 9px 4px; border-bottom: 1px solid #243038; }
            .data-list { background: #11181d; border: 1px solid #28343c;
                         border-radius: 10px; }
            .data-list row { background: #151d23; background-image: none;
                             color: #dfe8ed; }
            .data-list row:hover { background: #1b2931; background-image: none; }
            .data-list row:selected { background: #223640; background-image: none; }
            .data-list row label { color: #dfe8ed; }
            .safe { color: #79c4d3; } .warm { color: #d8c568; }
            .hot { color: #f0a046; } .danger { color: #ef6861; }
            .status-pill { font-size: 12px; font-weight: 700; }
            .button-flat { background: #1d2e37; color: #d9f0f5; border-radius: 7px; }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    @staticmethod
    def _label(text: str = "", css_class: str | None = None, xalign: float = 0) -> Gtk.Label:
        label = Gtk.Label(label=text, xalign=xalign)
        if css_class:
            label.add_css_class(css_class)
        return label

    def _metric_card(self, key: str, detail: str = "") -> Gtk.Box:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.add_css_class("metric-card")
        card.set_hexpand(True)
        card.append(self._label(key, "metric-key"))
        value = self._label("—", "metric-value")
        detail_label = self._label(detail, "muted")
        card.append(value)
        card.append(detail_label)
        self.temperature_cards[key.lower()] = (value, detail_label, card)
        return card

    def _build_window(self) -> None:
        self.window = Gtk.ApplicationWindow(application=self, title="Freeze Watch")
        self.window.set_default_size(1040, 760)
        self.window.set_size_request(720, 540)
        self.window.connect("close-request", self._hide_on_close)

        header = Gtk.HeaderBar()
        title = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        title.append(self._label("FREEZE WATCH", "eyebrow"))
        title.append(self._label("系統熱度與穩定性", "muted"))
        header.set_title_widget(title)
        refresh_button = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh_button.set_tooltip_text("立即更新")
        refresh_button.connect("clicked", lambda _button: self.refresh())
        header.pack_end(refresh_button)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.window.set_titlebar(header)
        scroll = Gtk.ScrolledWindow()
        scroll.set_hexpand(True)
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        content.add_css_class("dashboard")
        content.set_valign(Gtk.Align.START)
        content.set_vexpand(False)
        scroll.set_child(content)
        root.append(scroll)
        self.window.set_child(root)

        hero = Gtk.Box(spacing=24)
        hero.add_css_class("hero")
        hero.set_hexpand(True)
        hero.set_valign(Gtk.Align.START)
        hero.set_vexpand(False)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        left.set_hexpand(True)
        left.set_valign(Gtk.Align.START)
        left.set_vexpand(False)
        left.append(self._label("即時熱度", "eyebrow"))
        self.labels["hero_temp"] = self._label("—", "hero-value")
        self.labels["hero_status"] = self._label("讀取感測器中", "hero-title")
        self.labels["hero_detail"] = self._label("尚未取得監測資料", "muted")
        left.append(self.labels["hero_temp"])
        left.append(self.labels["hero_status"])
        left.append(self.labels["hero_detail"])
        hero.append(left)
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        right.set_valign(Gtk.Align.CENTER)
        right.set_vexpand(False)
        self.labels["hero_docker"] = self._label("Docker —", "metric-key")
        self.labels["hero_memory"] = self._label("可用記憶體 —", "muted")
        right.append(self.labels["hero_docker"])
        right.append(self.labels["hero_memory"])
        hero.append(right)
        content.append(hero)

        content.append(self._label("最近 30 分鐘熱度帶", "section-title"))
        self.ribbon = ThermalRibbon()
        content.append(self.ribbon)

        temperatures = Gtk.Grid(column_spacing=12, row_spacing=12)
        for column, (title_text, detail) in enumerate((
            ("CPU", "核心溫度"),
            ("GPU", "顯示核心"),
            ("NVME", "儲存裝置"),
        )):
            temperatures.attach(self._metric_card(title_text, detail), column, 0, 1, 1)
        content.append(temperatures)

        content.append(self._label("系統脈搏", "section-title"))
        system_grid = Gtk.Grid(column_spacing=12, row_spacing=12)
        for column, title_text in enumerate(("可用記憶體", "負載", "I/O 壓力", "根目錄")):
            card = self._metric_card(title_text)
            self.labels[f"system_{column}"] = self.temperature_cards[title_text.lower()][0]
            self.labels[f"system_detail_{column}"] = self.temperature_cards[title_text.lower()][1]
            system_grid.attach(card, column, 0, 1, 1)
        content.append(system_grid)

        split = Gtk.Grid(column_spacing=18, row_spacing=12)
        split.set_column_homogeneous(True)
        left_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        left_column.append(self._label("容器狀態", "section-title"))
        self.container_list = Gtk.ListBox()
        self.container_list.add_css_class("data-list")
        self.container_list.set_selection_mode(Gtk.SelectionMode.NONE)
        left_column.append(self.container_list)
        split.attach(left_column, 0, 0, 1, 1)

        right_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        right_column.append(self._label("最近事件", "section-title"))
        self.event_list = Gtk.ListBox()
        self.event_list.add_css_class("data-list")
        self.event_list.set_selection_mode(Gtk.SelectionMode.NONE)
        right_column.append(self.event_list)
        split.attach(right_column, 1, 0, 1, 1)
        content.append(split)

        content.append(self._label("目前最活躍程序", "section-title"))
        self.labels["top_processes"] = self._label("—", "muted")
        self.labels["top_processes"].set_wrap(True)
        self.labels["top_processes"].set_wrap_mode(2)
        content.append(self.labels["top_processes"])
    def _hide_on_close(self, _window) -> bool:
        self.window.hide()
        return True

    @staticmethod
    def _set_level_class(widget: Gtk.Widget, level: str) -> None:
        for candidate in ("safe", "warm", "hot", "danger"):
            widget.remove_css_class(candidate)
        widget.add_css_class(level)

    def _update_temperature_card(
        self, name: str, value: float | None, detail: str, level: str
    ) -> None:
        label, detail_label, card = self.temperature_cards[name.lower()]
        label.set_text(format_temperature(value))
        detail_label.set_text(detail)
        self._set_level_class(label, level)
        self._set_level_class(card, level)

    @staticmethod
    def _clear_list(list_box: Gtk.ListBox) -> None:
        while child := list_box.get_first_child():
            list_box.remove(child)

    def _append_container_row(self, row: dict[str, str]) -> None:
        if self.container_list is None:
            return
        container_row = Gtk.ListBoxRow()
        container_row.add_css_class("data-row")
        content = Gtk.Box(spacing=10)
        content.add_css_class("list-row")
        name = self._label(row.get("container", "unknown"), None)
        name.set_hexpand(True)
        cpu = row.get("cpu_pct", "—")
        memory = row.get("memory_usage", "—").split(" / ")[0]
        zombies = row.get("zombies", "—")
        detail = f"{cpu}  ·  {memory}  ·  Z {zombies}"
        content.append(name)
        content.append(self._label(detail, "muted", 1))
        container_row.set_child(content)
        self.container_list.append(container_row)

    def _append_event_row(self, event: str) -> None:
        if self.event_list is None:
            return
        row = Gtk.ListBoxRow()
        row.add_css_class("data-row")
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        content.add_css_class("list-row")
        parts = event.split("\t", 2)
        timestamp = parts[0] if parts else "—"
        message = parts[-1] if parts else event
        content.append(self._label(message, None))
        content.append(self._label(timestamp, "muted"))
        row.set_child(content)
        self.event_list.append(row)

    def _recent_events(self) -> list[str]:
        event_log = STATE_DIR / "events.log"
        lines = [line for line in tail_text(event_log, 24_000).splitlines() if line.strip()]
        meaningful = [line for line in lines if "\tWARN\t" in line or "\tROTATE\t" in line]
        return (meaningful or lines)[-6:][::-1]

    def present_dashboard(self) -> bool:
        if self.window is None:
            self._build_window()
            self.refresh()
        self.window.present()
        return False

    def refresh(self) -> bool:
        metric_rows = read_tsv_tail("metrics-*.tsv", METRICS_FIELDS)
        latest_metric = metric_rows[-1] if metric_rows else {}
        # Each reading falls back on its own. Testing them together meant one
        # readable sensor suppressed the recorded values for every other field.
        temperatures = direct_temperatures()
        for name, column in (
            ("cpu", "cpu_temp_mC"),
            ("gpu", "gpu_temp_mC"),
            ("nvme", "nvme_temp_mC"),
        ):
            if temperatures[name] is None:
                temperatures[name] = self._temperature_from_metric(latest_metric, column)
        level = temperature_level(temperatures)
        status, status_detail = level_copy(level)

        if self.tray is not None:
            self.tray.update(temperatures, level)

        if self.window is None:
            return True

        self.labels["hero_temp"].set_text(format_temperature(temperatures["cpu"]))
        self.labels["hero_status"].set_text(status)
        self.labels["hero_detail"].set_text(
            f"GPU {format_temperature(temperatures['gpu'])}  ·  "
            f"NVMe {format_temperature(temperatures['nvme'])}  ·  {status_detail}"
        )
        self._set_level_class(self.labels["hero_temp"], level)
        self._set_level_class(self.labels["hero_status"], level)

        docker_state = latest_metric.get("docker_state", "—")
        container_count = latest_metric.get("docker_containers", "—")
        self.labels["hero_docker"].set_text(f"DOCKER  {container_count} 容器 · {docker_state}")
        available_kib = as_int(latest_metric.get("mem_available_kib"))
        self.labels["hero_memory"].set_text(f"可用記憶體 {format_gib(available_kib)}")

        for name, value, detail in (
            ("cpu", temperatures["cpu"], "核心溫度"),
            ("gpu", temperatures["gpu"], "顯示核心"),
            ("nvme", temperatures["nvme"], "儲存裝置"),
        ):
            self._update_temperature_card(name, value, detail, temperature_level({name: value}))

        self.labels["system_0"].set_text(format_gib(available_kib))
        self.labels["system_detail_0"].set_text(
            f"swap {format_gib(as_int(latest_metric.get('swap_used_kib')))}"
        )
        self.labels["system_1"].set_text(
            latest_metric.get("load1", "—")
        )
        self.labels["system_detail_1"].set_text(
            f"5m {latest_metric.get('load5', '—')} · 15m {latest_metric.get('load15', '—')}"
        )
        self.labels["system_2"].set_text(
            f"{latest_metric.get('io_psi_avg10', '—')}%"
        )
        self.labels["system_detail_2"].set_text(
            f"CPU {latest_metric.get('cpu_psi_avg10', '—')}% · RAM {latest_metric.get('memory_psi_avg10', '—')}%"
        )
        self.labels["system_3"].set_text(
            f"{latest_metric.get('root_used_pct', '—')}%"
        )
        self.labels["system_detail_3"].set_text("根目錄使用率")
        self.labels["top_processes"].set_text(
            latest_metric.get("top_processes", "尚無程序資料").replace(";", "    ·    ")
        )

        if self.ribbon is not None:
            self.ribbon.set_history(metric_rows)

        docker_rows = read_tsv_tail("docker-*.tsv", DOCKER_FIELDS)
        last_timestamp = docker_rows[-1].get("timestamp") if docker_rows else None
        current_containers = [
            row for row in docker_rows if row.get("timestamp") == last_timestamp
        ]
        if self.container_list is not None:
            self._clear_list(self.container_list)
            for row in current_containers:
                self._append_container_row(row)

        if self.event_list is not None:
            self._clear_list(self.event_list)
            for event in self._recent_events():
                self._append_event_row(event)

        return True

    @staticmethod
    def _temperature_from_metric(row: dict[str, str], key: str) -> float | None:
        value = as_float(row.get(key))
        return value / 1000 if value is not None else None


def main() -> int:
    DBusGMainLoop(set_as_default=True)
    start_hidden = "--background" in sys.argv
    argv = [arg for arg in sys.argv if arg != "--background"]
    app = FreezeWatch(start_hidden=start_hidden)
    return app.run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
