#!/usr/bin/env python3
"""A lightweight local dashboard for the freeze-monitor collector."""

from __future__ import annotations

import csv
import json
import math
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, NamedTuple

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango


APP_ID = "com.raybird.FreezeWatch"
NORMAL_ICON_NAME = f"{APP_ID}-symbolic"
WARNING_ICON_NAME = f"{APP_ID}-warning-symbolic"
SNI_INTERFACE = "org.kde.StatusNotifierItem"
DBUS_PROPERTIES = "org.freedesktop.DBus.Properties"
SNI_PATH = "/StatusNotifierItem"
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "freeze-monitor"
HWMON_ROOT = Path(os.environ.get("FREEZE_WATCH_HWMON_ROOT", "/sys/class/hwmon"))
# FREEZE and GAP are the reason the collector exists, so they outrank the
# routine housekeeping entries when the dashboard picks what to show.
NOTEWORTHY_EVENTS = ("UNCLEAN", "FREEZE", "KERNEL", "INTERRUPTED", "GAP", "WARN", "ROTATE")

# Events worth going back to look at, as opposed to merely worth reading.
INCIDENT_KINDS = ("UNCLEAN", "FREEZE", "GAP")
INCIDENT_LIMIT = 8
INCIDENT_WINDOW_SECONDS = 30 * 60
# The ribbon shows the last half hour of 10 s samples.
HISTORY_ROWS = 180
EVENT_HISTORY_LIMIT = 12
# Matches the collector's default. Only used to turn busy milliseconds into a
# share of the interval, so a mismatch misreads that one figure and nothing else.
SAMPLE_INTERVAL_SECONDS = 10
STALE_AFTER_SECONDS = 60
WINDOW_MIN_WIDTH = 720
WINDOW_MIN_HEIGHT = 540
WINDOW_PREFERRED_WIDTH = 1040
WINDOW_PREFERRED_HEIGHT = 760
WINDOW_SCREEN_MARGIN = 80

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
    # Appended, never inserted: these files are read by position, and one
    # written before this release simply stops short of them.
    "cpu_psi_full_avg10", "memory_psi_full_avg10", "io_psi_full_avg10",
    "dstate_count", "cpu_throttle_count", "swapin_pages", "swapout_pages",
    "majfault_count", "disk_in_flight", "disk_busy_ms", "top_memory_processes", "gpu_processes",
]
DOCKER_FIELDS = [
    "timestamp", "epoch", "container", "is_tracked_project", "cpu_pct",
    "memory_usage", "tasks", "processes", "zombies", "oom_killed",
    "restart_count", "container_id", "project", "service", "health",
    "read_bytes", "write_bytes", "read_bps", "write_bps", "dstate",
    "process_sample", "sample_status", "process_status", "container_state",
]


def tail_text(path: Path, byte_limit: int = 160_000) -> str:
    """Read only the useful tail of an append-only log."""
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            start = max(0, size - byte_limit)
            # Start one byte early so a cut that lands on a line boundary keeps
            # that line, then drop the partial line in front of it.
            handle.seek(max(0, start - 1))
            data = handle.read()
            if start > 0:
                newline = data.find(b"\n")
                data = data[newline + 1:] if newline >= 0 else b""
        return data.decode("utf-8", errors="replace")
    except OSError:
        return ""


def newest_file(pattern: str) -> Path | None:
    files = list(STATE_DIR.glob(pattern))
    if not files:
        return None
    return max(files, key=lambda item: item.stat().st_mtime)


def read_tsv_path(path: Path | None, fields: list[str], byte_limit: int = 160_000,
                  min_rows: int = 0) -> list[dict[str, str]]:
    if path is None:
        return []

    while True:
        lines = tail_text(path, byte_limit).splitlines()
        # restval keeps a row written before a column existed reading as missing
        # data rather than as None, which every caller here would render literally.
        rows = []
        incomplete = False
        minimum = 24 if fields is METRICS_FIELDS else 11
        for line in lines:
            if line.startswith("timestamp\t"):
                continue
            parts = line.split("\t")
            if (len(parts) < minimum or "\x00" in line or
                    not parts[1].isdigit() or not parts[0]):
                incomplete = True
                continue
            rows.append(dict(zip(fields, parts + ["NA"] * (len(fields) - len(parts)))))
        if incomplete and rows:
            rows[-1]["_incomplete"] = "yes"
        # Row width varies (GPU JSON), so a fixed byte window can hold far
        # fewer rows than the view needs; widen until it does or the file ends.
        try:
            whole_file = path.stat().st_size <= byte_limit
        except OSError:
            whole_file = True
        if len(rows) >= min_rows or whole_file:
            return rows
        byte_limit *= 4


def read_tsv_before(path: Path | None, fields: list[str], end_epoch: int,
                    byte_limit: int = 2_000_000) -> list[dict[str, str]]:
    """Rows at or before end_epoch, wherever in the file they are.

    An incident early in a day's file sits far from the tail, so reading the
    last bytes and filtering would find nothing although the rows are on disk.
    Rows are appended in epoch order, so the cut point can be searched for.
    """
    if path is None:
        return []
    try:
        with path.open("rb") as handle:
            size = handle.seek(0, os.SEEK_END)

            def epoch_after(offset: int) -> tuple[int, int | float | None]:
                """The first whole line starting after offset and its epoch."""
                handle.seek(offset)
                if offset:
                    handle.readline()
                start = handle.tell()
                line = handle.readline()
                parts = line.split(b"\t", 2)
                try:
                    return start, int(parts[1])
                except (IndexError, ValueError):
                    # The header, or the end of the file.
                    return start, None if line else math.inf

            low, high = 0, size
            while low < high:
                middle = (low + high) // 2
                _, epoch = epoch_after(middle)
                if epoch is not None and epoch > end_epoch:
                    high = middle
                else:
                    low = middle + 1
            cut, _ = epoch_after(low)
            handle.seek(max(0, cut - byte_limit))
            data = handle.read(cut - max(0, cut - byte_limit))
            if cut > byte_limit:
                data = data[data.find(b"\n") + 1:]
    except OSError:
        return []
    lines = data.decode("utf-8", errors="replace").splitlines()
    rows = []
    minimum = 24 if fields is METRICS_FIELDS else 11
    for line in lines:
        parts = line.split("\t")
        if (len(parts) < minimum or "\x00" in line or not parts[1].isdigit()
                or int(parts[1]) > end_epoch):
            continue
        rows.append(dict(zip(fields, parts + ["NA"] * (len(fields) - len(parts)))))
    return rows


def read_tsv_tail(pattern: str, fields: list[str]) -> list[dict[str, str]]:
    return read_tsv_path(newest_file(pattern), fields, min_rows=HISTORY_ROWS)


def sample_freshness(row: dict[str, str], now: float) -> str:
    epoch = as_int(row.get("epoch"))
    if epoch is None:
        if row.get("_incomplete") == "yes":
            return "資料不完整；沒有有效採樣"
        return "資料缺失；尚無有效採樣"
    details = []
    if now - epoch > STALE_AFTER_SECONDS:
        details.append(f"資料過期；最後採樣 {row.get('timestamp', '未知')}")
    if row.get("_incomplete") == "yes":
        details.append("資料不完整；已略過損壞列")
    return " · ".join(details)


def empty_sample_status(path: Path | None) -> str:
    if path is None:
        return ""
    lines = tail_text(path).splitlines()
    return "資料不完整；沒有有效採樣" if any(
        line and not line.startswith("timestamp\t") for line in lines
    ) else ""


class Incident(NamedTuple):
    """Something the collector recorded that is worth going back to look at."""

    timestamp: str
    kind: str
    message: str
    metrics_path: Path | None

    @property
    def label(self) -> str:
        moment = self.timestamp.replace("T", " ")[:16]
        kind = "非正常關機／疑似當機" if self.kind in ("FREEZE", "UNCLEAN") else "取樣停擺"
        return f"{moment} · {kind}"


def parse_event_line(line: str) -> tuple[str, str, str] | None:
    parts = line.split("\t", 2)
    if len(parts) < 3:
        return None
    return parts[0], parts[1], parts[2]


def read_incidents(limit: int = INCIDENT_LIMIT) -> list[Incident]:
    """The most recent incidents, newest first."""
    incidents: list[Incident] = []
    for line in tail_text(STATE_DIR / "events.log").splitlines():
        parsed = parse_event_line(line)
        if parsed is None:
            continue
        timestamp, kind, message = parsed
        if kind not in INCIDENT_KINDS:
            continue

        metrics_path = None
        # A freeze names the file it was cut off from. A stall happened mid
        # session, so the file has to be found by the time it covers.
        marker = "metrics="
        if marker in message:
            metrics_path = Path(message.split(marker, 1)[1].split(" ", 1)[0])
        else:
            metrics_path = metrics_file_covering(timestamp)
        incidents.append(Incident(timestamp, kind, message, metrics_path))

    return incidents[-limit:][::-1]


def metrics_file_covering(timestamp: str) -> Path | None:
    """The metrics file whose samples span the given moment."""
    target = epoch_of(timestamp)
    if target is None:
        return None

    for path in sorted(STATE_DIR.glob("metrics-*.tsv"), reverse=True):
        rows = read_tsv_path(path, METRICS_FIELDS)
        if not rows:
            continue
        try:
            with path.open(errors="replace") as handle:
                first_row = next(csv.DictReader(handle, delimiter="\t"), {})
        except OSError:
            continue
        first = as_int(first_row.get("epoch"))
        last = next((epoch for row in reversed(rows)
                     if (epoch := as_int(row.get("epoch"))) is not None), None)
        if first is not None and last is not None and first <= target <= last:
            return path
    return None


def docker_path_for(metrics_path: Path | None) -> Path | None:
    if metrics_path is None or not metrics_path.name.startswith("metrics-"):
        return None
    return metrics_path.with_name("docker-" + metrics_path.name[len("metrics-"):])


def epoch_of(timestamp: str) -> int | None:
    try:
        return int(datetime.fromisoformat(timestamp).timestamp())
    except ValueError:
        return None


def incident_end(incident: Incident) -> int | None:
    for part in incident.message.split():
        if part.startswith("last_sample="):
            stamp = part.split("=", 1)[1]
            if stamp != "unknown":
                return epoch_of(stamp)
    return epoch_of(incident.timestamp)


def incident_paths(incident: Incident, include_after: bool = False) -> list[Path]:
    paths: list[Path] = []
    found = False
    for line in tail_text(STATE_DIR / "events.log", 2_000_000).splitlines():
        parsed = parse_event_line(line)
        if parsed is None:
            continue
        timestamp, kind, message = parsed
        if kind in ("START", "STOP"):
            if found:
                break
            paths = []
        if kind in ("START", "ROTATE") and "metrics=" in message:
            paths.append(Path(message.split("metrics=", 1)[1].split(" ", 1)[0]))
        if timestamp == incident.timestamp and kind == incident.kind and message == incident.message:
            found = True
            if not include_after:
                break
    if incident.metrics_path in paths:
        return paths if include_after else paths[:paths.index(incident.metrics_path) + 1]
    return [incident.metrics_path] if incident.metrics_path is not None else []


def metric_window(path: Path, start: int, finish: int) -> tuple[list[dict[str, str]], bool]:
    rows = []
    incomplete = False
    try:
        with path.open(errors="replace") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                epoch = as_int(row.get("epoch"))
                if (epoch is None or sum(value is not None for value in row.values()) < 24
                        or "\x00" in "".join(str(value) for value in row.values())):
                    incomplete = True
                    continue
                if start <= epoch <= finish:
                    rows.append(row)
    except OSError:
        pass
    if incomplete and rows:
        rows[-1]["_incomplete"] = "yes"
    return rows, incomplete


def incident_rows(incident: Incident) -> list[dict[str, str]]:
    end = incident_end(incident)
    rows: list[dict[str, str]] = []
    for path in reversed(incident_paths(incident)):
        samples = read_tsv_path(path, METRICS_FIELDS, 4_000_000)
        if end is not None and samples and (as_int(samples[0].get("epoch")) or 0) > end - INCIDENT_WINDOW_SECONDS:
            samples, _ = metric_window(path, end - INCIDENT_WINDOW_SECONDS, end)
        rows = samples + rows
        if samples and end is not None and (as_int(samples[0].get("epoch")) or 0) < end - INCIDENT_WINDOW_SECONDS:
            break
    if end is None:
        return rows[-HISTORY_ROWS:]
    return [row for row in rows if end - INCIDENT_WINDOW_SECONDS <= (as_int(row.get("epoch")) or 0) <= end]


def gpu_summary(value: str | None) -> str:
    if value in (None, "NA", "disabled"):
        return "GPU 程序紀錄未啟用"
    try:
        report = json.loads(value)
    except (TypeError, ValueError):
        report = None
    if not isinstance(report, dict):
        return "GPU 程序資料無法讀取"
    lines = []
    if report.get("status") != "ok":
        lines.append("GPU 資料不完整：權限不足、掃描受限或採樣失敗")
    if report.get("truncated"):
        lines.append("已達掃描上限，僅列出部分程序")
    for client in report.get("clients", []):
        owners = ", ".join(f"{pid} {name}" for pid, name in zip(client["pids"], client["names"]))
        # A number is a measured percentage; a string names why it is unmeasured.
        activity = [
            f"{engine} {reading:.2f}%" if isinstance(reading, (int, float)) else f"{engine} 活動未知"
            for engine, reading in client.get("engines", {}).items()
        ]
        lines.append(f"{owners} · {client['driver']} · " + (", ".join(activity) or "活動未知"))
    for driver, names in (report.get("unsupported") or {}).items():
        lines.append(f"{driver} 計數器不支援，僅確認持有裝置：" + ", ".join(names))
    if report.get("idle"):
        lines.append("持有裝置、取樣期間無活動：" + ", ".join(report["idle"]))
    if report.get("protected"):
        lines.append(f"{report['protected']} 個受保護的程序無法檢查（例如瀏覽器沙箱）")
    return "\n".join(lines) or "未找到可見的 GPU 裝置持有者；不代表沒有 GPU 活動"


REPORT_FIELDS = [
    "cpu_temp_mC", "gpu_temp_mC", "nvme_temp_mC", "load1",
    "mem_available_kib", "swap_used_kib", "cpu_psi_avg10", "cpu_psi_full_avg10",
    "memory_psi_avg10", "memory_psi_full_avg10", "io_psi_avg10", "io_psi_full_avg10",
    "disk_in_flight", "disk_busy_ms", "dstate_count",
]
KERNEL_REPORT_PATTERN = re.compile(
    r"GPU HANG|GPU hang|GPU reset|NVRM: Xid|ring [a-z0-9_.]+ timeout|"
    r"hung_task|blocked for more than [0-9]+ seconds|rcu|soft lockup|hard LOCKUP|"
    r"Kernel panic|BUG: unable to handle|general protection fault|"
    r"Hardware Error|Machine check|Out of memory|oom-kill|cpu clock throttled|"
    r"EXT4-fs error|Buffer I/O error|nvme[^ ]*.*?(?:timeout|controller is down|resetting)|"
    r"ata[0-9]+\.[0-9]+: failed command"
)


def diagnostic_report(incident: Incident) -> str:
    end = incident_end(incident)
    if end is None:
        return "Freeze Watch 診斷報告\n事件時間無效，無法定位資料。\n"
    start, finish = end - INCIDENT_WINDOW_SECONDS, end + 300
    moment = datetime.fromtimestamp(end).astimezone().isoformat()
    kind = "非正常關機／疑似當機，原因未確認" if incident.kind in ("UNCLEAN", "FREEZE") else "取樣停擺"
    lines = ["Freeze Watch 診斷報告", f"事件：{kind}", f"基準時間：{moment}",
             "範圍：前 30 分鐘／後 5 分鐘；未記錄的區間不推測。",
             "隱私：只列數值與核心錯誤分類，省略檔案路徑、程序名稱與參數。", "",
             "取樣（溫度 m°C、記憶體 KiB、PSI %、磁碟忙碌 ms）", "timestamp\t" + "\t".join(REPORT_FIELDS)]
    event_lines = tail_text(STATE_DIR / "events.log", 2_000_000).splitlines()
    version = "未知（舊紀錄未保存）"
    kernel_state = "未知（舊紀錄未保存）"
    kernel_scan_stamp = ""
    kernel_scan_matches = 0
    for event_line in event_lines:
        parsed = parse_event_line(event_line)
        if parsed is None:
            continue
        event_stamp, event_kind, message = parsed
        if event_stamp == incident.timestamp and event_kind == incident.kind and message == incident.message:
            break
        if event_kind == "START":
            version_match = re.search(r"(?:^| )version=([0-9A-Za-z._-]+)", message)
            kernel_match = re.search(r"(?:^| )kernel=(ok|unavailable)", message)
            version = version_match.group(1) if version_match else "未知（舊紀錄未保存）"
            kernel_state = "初始可讀；掃描未知" if kernel_match and kernel_match.group(1) == "ok" else (
                "unavailable" if kernel_match else "未知（舊紀錄未保存）")
            kernel_scan_stamp = ""
            kernel_scan_matches = 0
        elif event_kind == "KERNEL_SCAN" and message.startswith("status=ok"):
            kernel_state = "ok"
            kernel_scan_stamp = event_stamp
            match = re.search(r"\bmatches=(\d+)\b", message)
            kernel_scan_matches = int(match.group(1)) if match else 0
        elif event_kind == "INFO" and "kernel log scan unavailable" in message:
            kernel_state = "unavailable"
            kernel_scan_stamp = ""
    count = 0
    after = 0
    gpu_states = set()
    incomplete = False
    for path in incident_paths(incident, include_after=True):
        samples, path_incomplete = metric_window(path, start, finish)
        incomplete |= path_incomplete
        for row in samples:
            epoch = as_int(row["epoch"])
            gpu_states.add(row.get("gpu_processes", "NA"))
            incomplete |= row.get("_incomplete") == "yes"
            values = []
            for field in REPORT_FIELDS:
                value = row.get(field, "NA")
                try:
                    number = float(value)
                    values.append(str(number) if math.isfinite(number) else "NA")
                except (TypeError, ValueError):
                    values.append("NA")
            stamp = datetime.fromtimestamp(epoch).astimezone().isoformat()
            lines.append(stamp + "\t" + "\t".join(values))
            count += 1
            after += epoch > end
    if not count:
        lines.append("此區間沒有可讀取的取樣。")
    if not after:
        lines.append("事件後沒有可讀取的取樣。")
    if gpu_states == {"disabled"}:
        gpu_state = "未啟用"
    elif not gpu_states or gpu_states == {"NA"}:
        gpu_state = "未知"
    else:
        gpu_state = "已記錄；詳情留於本機"
    lines.extend([f"收集器版本：{version}", f"GPU 程序採樣：{gpu_state}"])
    if incomplete:
        lines.append("取樣資料不完整；已略過損壞列。")
    lines.extend(["", "相關核心錯誤（分類保留，原始訊息未匯出）"])
    errors = 0
    for line in event_lines:
        parsed = parse_event_line(line)
        if parsed is None:
            continue
        timestamp, event_kind, message = parsed
        epoch = epoch_of(timestamp)
        previous_boot = "previous boot:" in message and timestamp == incident.timestamp
        if event_kind != "KERNEL" or epoch is None or not (start <= epoch <= finish or previous_boot):
            continue
        match = KERNEL_REPORT_PATTERN.search(message)
        category = match.group() if match is not None else "核心錯誤（詳細資訊省略）"
        if category.startswith("nvme"):
            category = "NVMe timeout/reset"
        lines.append(f"{datetime.fromtimestamp(epoch).astimezone().isoformat()} · {category}")
        errors += 1
    if not errors:
        if kernel_state == "ok" and kernel_scan_matches:
            lines.append("核心掃描有命中，但本區間沒有新事件紀錄；可能已去重。")
        else:
            lines.append("此區間沒有可讀取的核心錯誤紀錄；不代表沒有核心錯誤。")
    if kernel_state == "unavailable":
        kernel_summary = "不可讀"
    elif kernel_state == "ok":
        result = "有命中" if kernel_scan_matches or errors else "零命中"
        kernel_summary = f"截至 {kernel_scan_stamp} 掃描成功，{result}；其後未知"
    else:
        kernel_summary = kernel_state
    lines.append(f"核心紀錄：{kernel_summary}")
    return "\n".join(lines) + "\n"


def write_diagnostic_report(path: Path, report: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(report)


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


def format_busy(busy_ms: Any, interval_seconds: int) -> str:
    """Disk busy time as a share of the sampling interval."""
    milliseconds = as_float(busy_ms)
    if milliseconds is None or interval_seconds <= 0:
        return "—"
    share = milliseconds / (interval_seconds * 1000) * 100
    return f"{min(share, 100):.0f}%"


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


def clamp_window_size(screen_width: int, screen_height: int) -> tuple[int, int]:
    """Fit the preferred size onto the screen without going below the minimum."""
    return (
        max(WINDOW_MIN_WIDTH, min(WINDOW_PREFERRED_WIDTH, screen_width - WINDOW_SCREEN_MARGIN)),
        max(
            WINDOW_MIN_HEIGHT,
            min(WINDOW_PREFERRED_HEIGHT, screen_height - WINDOW_SCREEN_MARGIN),
        ),
    )


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


LEVEL_SEVERITY = {"safe": 0, "warm": 1, "hot": 2, "danger": 3}

CARD_TOOLTIPS = {
    "cpu": (
        "處理器封裝溫度與硬體熱節流（Thermal Throttle）累計次數。\n"
        "若節流次數增加，代表溫度過高導致韌體強制降頻。"
    ),
    "gpu": "顯示核心溫度（支援 AMD、Intel 與 Nouveau 感測器）。",
    "nvme": "NVMe 固態硬碟感測器溫度。",
    "可用記憶體": (
        "立即可供應用程式分配的記憶體（MemAvailable）。\n"
        "• swap：目前已使用的交換空間\n"
        "• 換入（swap-in）：最近一輪從磁碟讀回記憶體的頁數；"
        "數值飆高代表系統正因記憶體不足而劇烈抖動（Thrashing）。"
    ),
    "負載": (
        "1 / 5 / 15 分鐘系統平均負載（Load Average）。\n"
        "• D（Uninterruptible Sleep）：正在等待磁碟或硬體 I/O 回應、無法中斷的程序數。"
        "若 D 持續偏高，通常是儲存裝置或驅動卡死的前兆。"
    ),
    "i/o 壓力": (
        "Linux PSI（Pressure Stall Information）過去 10 秒受阻時間比例。\n"
        "• 全停（full）：所有非閒置程序同時因等待資源而停擺的比例，直接對應畫面卡死體感\n"
        "• CPU / RAM：處理器與記憶體受阻比例（some）"
    ),
    "根目錄": (
        "根目錄（/）磁碟空間使用率與底層裝置繁忙程度。\n"
        "• 佇列（in-flight）：目前正在排隊等待磁碟處理的 I/O 請求數\n"
        "• 忙碌（busy）：採樣區間內磁碟實際處於讀寫忙碌的時間佔比"
    ),
}


def worst_level(*levels: str) -> str:
    return max(levels, key=lambda item: LEVEL_SEVERITY.get(item, 0), default="safe")


def memory_level(available_kib: int | None, swapin_pages: int | None = None) -> str:
    level = "safe"
    if available_kib is not None:
        if available_kib < 512 * 1024:
            level = "danger"
        elif available_kib < 1024 * 1024:
            level = "hot"
        elif available_kib < 2 * 1024 * 1024:
            level = "warm"
    if swapin_pages is not None:
        if swapin_pages >= 10000:
            level = worst_level(level, "danger")
        elif swapin_pages >= 3000:
            level = worst_level(level, "hot")
        elif swapin_pages >= 1000:
            level = worst_level(level, "warm")
    return level


def load_level(
    load1: float | None,
    dstate_count: int | None = None,
    cpu_count: int | None = None,
) -> str:
    level = "safe"
    if dstate_count is not None:
        if dstate_count >= 8:
            level = "danger"
        elif dstate_count >= 4:
            level = "hot"
        elif dstate_count >= 1:
            level = "warm"
    if load1 is not None:
        cores = max(cpu_count or os.cpu_count() or 4, 1)
        if load1 >= cores * 2.5:
            level = worst_level(level, "danger")
        elif load1 >= cores * 1.5:
            level = worst_level(level, "hot")
        elif load1 >= cores:
            level = worst_level(level, "warm")
    return level


def pressure_level(
    io_some: float | None,
    io_full: float | None = None,
    mem_full: float | None = None,
    cpu_some: float | None = None,
    mem_some: float | None = None,
) -> str:
    full_peak = max((v for v in (io_full, mem_full) if v is not None), default=0.0)
    some_peak = max((v for v in (io_some, mem_some) if v is not None), default=0.0)
    if full_peak >= 10.0 or some_peak >= 40.0:
        return "danger"
    if full_peak >= 3.0 or some_peak >= 20.0:
        return "hot"
    if full_peak >= 1.0 or some_peak >= 5.0 or (cpu_some or 0.0) >= 25.0:
        return "warm"
    return "safe"


def disk_level(
    used_pct: float | None,
    in_flight: int | None = None,
    busy_ms: float | None = None,
    interval_seconds: int = SAMPLE_INTERVAL_SECONDS,
) -> str:
    busy_pct = (
        busy_ms / (interval_seconds * 1000) * 100
        if busy_ms is not None and interval_seconds > 0
        else 0.0
    )
    if (used_pct or 0.0) >= 95.0 or busy_pct >= 90.0 or (in_flight or 0) >= 32:
        return "danger"
    if (used_pct or 0.0) >= 90.0 or busy_pct >= 75.0 or (in_flight or 0) >= 16:
        return "hot"
    if (used_pct or 0.0) >= 85.0 or busy_pct >= 50.0 or (in_flight or 0) >= 4:
        return "warm"
    return "safe"


def parse_process_entries(raw: str | None) -> list[tuple[str, str, str]]:
    """Parse semicolon-delimited 'comm %cpu %mem' entries from the collector."""
    if not raw or raw in ("NA", "—", "尚無程序資料"):
        return []
    entries: list[tuple[str, str, str]] = []
    for item in raw.split(";"):
        text = item.strip()
        if not text:
            continue
        parts = text.rsplit(None, 2)
        if len(parts) == 3 and as_float(parts[1]) is not None and as_float(parts[2]) is not None:
            entries.append((parts[0], f"{parts[1].rstrip('%')}%", f"{parts[2].rstrip('%')}%"))
        else:
            entries.append((text, "—", "—"))
    return entries


def format_process_listing(raw: str | None) -> str:
    entries = parse_process_entries(raw)
    if not entries:
        return "尚無程序資料"
    formatted = []
    for name, cpu, mem in entries:
        if cpu == "—" and mem == "—":
            formatted.append(name)
        else:
            formatted.append(f"{name} (CPU {cpu} · RAM {mem})")
    return "    ·    ".join(formatted)


def format_incident_summary(incident: Incident) -> str:
    """Turn a raw collector incident message into a concise human summary."""
    message = incident.message
    if incident.kind in ("FREEZE", "UNCLEAN"):
        last_sample = ""
        silent_for = ""
        for token in message.split():
            if token.startswith("last_sample="):
                last_sample = token.split("=", 1)[1].replace("T", " ")[:19]
            elif token.startswith("silent_for="):
                silent_for = token.split("=", 1)[1]
        details = []
        if last_sample:
            details.append(f"最後取樣 {last_sample}")
        if silent_for:
            details.append(f"中斷 {silent_for}")
        summary = "非正常關機／疑似當機，原因未確認"
        if details:
            return f"{summary}（{' · '.join(details)}）"
        return f"{summary}（可能為斷電、強制重啟或當機）"
    if incident.kind == "GAP" and "sampling stalled for" in message:
        return message.replace("sampling stalled for ", "取樣停擺 ").replace(
            ", expected ", "（預期 "
        ) + "）"
    return message


def ribbon_sample_tooltip(sample: dict[str, Any], stalled: bool = False) -> str:
    raw_ts = str(sample.get("timestamp") or "")
    moment = raw_ts.replace("T", " ")[:19] if raw_ts else "未知時間"
    header = f"{moment} · ⚠ 採樣停擺（排程延遲）" if stalled else moment
    return (
        f"{header}\n"
        f"CPU {format_temperature(sample.get('cpu'))}  ·  "
        f"GPU {format_temperature(sample.get('gpu'))}  ·  "
        f"NVMe {format_temperature(sample.get('nvme'))}"
    )


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


def latest_containers(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    stamp = rows[-1].get('timestamp') if rows else None
    return [row for row in rows if row.get('timestamp') == stamp and row.get('container')]


def container_detail(row: dict[str, str], metrics: list[dict[str, str]]) -> str:
    def value(key: str) -> str:
        result = row.get(key)
        return '未知' if result in (None, '', 'NA') else str(result)

    def rate(key: str) -> str:
        number = as_float(row.get(key))
        return '未知' if number is None else f'{number / 1024:.1f} KiB/s'

    cpu_text = value('cpu_pct').rstrip('%')
    cpu_text = cpu_text if cpu_text == '未知' else f"{cpu_text}%"
    health = {'not_configured': '未設定 healthcheck', 'healthy': '健康',
              'unhealthy': '不健康', 'starting': '啟動中'}.get(value('health'), value('health'))
    lines = [f"採樣：{value('timestamp')} · 狀態 {value('sample_status')}",
             f"ID：{value('container_id')} · 容器狀態 {value('container_state')}", f"Project／service：{value('project')}／{value('service')}",
             f"CPU：{cpu_text}（區間使用率，100% 為一個核心）",
             f"記憶體／上限：{value('memory_usage')}",
             f"Tasks {value('tasks')} · 程序 {value('processes')} · D {value('dstate')} · Z {value('zombies')}",
             f"OOM {value('oom_killed')} · 重啟 {value('restart_count')} · Health {health}",
             f"累計 block I/O：讀 {value('read_bytes')} B · 寫 {value('write_bytes')} B",
             f"讀取 {rate('read_bps')} · 寫入 {rate('write_bps')}",
             'Block I/O 不含快取命中的所有檔案讀取；未知可能是首次採樣、計數器重置或核心未提供。']
    epoch = as_float(row.get('epoch'))
    host = next((m for m in reversed(metrics) if epoch is not None and as_float(m.get('epoch')) is not None
                 and 0 <= epoch - as_float(m.get('epoch')) <= 45), None)
    if host:
        temperature = as_float(host.get('cpu_temp_mC'))
        lines.append(f"主機 @{host.get('timestamp', host.get('epoch'))}：CPU {format_temperature(temperature / 1000 if temperature is not None else None)} · "
                     f"I/O PSI {host.get('io_psi_avg10', '未知')}% · RAM PSI {host.get('memory_psi_avg10', '未知')}%")
    else:
        lines.append('主機資料缺口：沒有此前 45 秒內的對照樣本')
    status = value('process_status')
    descriptions = {'stopped': '容器已停止，無即時負載／程序', 'not_tracked': '未選取此 Compose project', 'budget_or_limit': '本輪預算／容器數上限，等待輪替',
                    'unavailable_or_timeout': '權限、容器消失、格式不支援或查詢逾時', 'NA': '舊紀錄未提供'}
    try:
        processes = json.loads(row.get('process_sample', 'NA'))
        if not isinstance(processes, list):
            raise ValueError('not a list')
        process_lines = []
        for process in processes[:15]:
            cpu = f"CPU {process['cpu']}%"
            if 'cpu_interval' in process:
                interval = '未知' if process['cpu_interval'] is None else f"{process['cpu_interval']}%"
                cpu = f"CPU 區間 {interval}（平均 {process['cpu']}%）"
            process_lines.append(f"PID {process['pid']} · {process['state']} · {cpu} · RAM {process['memory']}% · {process['name']}")
        if not processes:
            process_lines.append('此樣本無程序')
    except (ValueError, TypeError, KeyError, AttributeError):
        processes, process_lines = [], [f"程序：未知（{descriptions.get(status, status)}）"]
    # Rows before issue 4 carry no cpu_interval and were ranked by the ps lifetime average.
    fallback = next((p['cpu_fallback'] for p in processes if isinstance(p, dict) and isinstance(p.get('cpu_fallback'), str)), None)
    if fallback:
        reason = {'no_previous': '尚無前一筆可算區間值', 'over_budget': '超過讀取預算', 'proc_unreadable': '無法讀取 /proc'}.get(fallback, fallback)
        ranking = f'程序依生命週期平均排序（{reason}）'
    elif any(isinstance(p, dict) and 'cpu_interval' in p for p in processes):
        ranking = '程序依兩次採樣之間的區間 CPU 排序（100% 為一個核心），括號內為 ps 生命週期平均'
    else:
        ranking = '程序 CPU 為 ps 生命週期平均'
    lines.append(f'{ranking}；記憶體 % 以主機 RAM 為分母；PID 為主機 PID。')
    lines.extend(process_lines)
    lines.append('高負載與事故時間重疊僅是線索，不代表因果。')
    return '\n'.join(lines)


def previous_restart_sample(history: list[dict[str, str]]) -> dict[str, str] | None:
    """The latest sample with a restart count, the baseline the collector also keeps."""
    return next((row for row in reversed(history) if as_int(row.get('restart_count')) is not None), None)


def container_warning(row: dict[str, str], previous: dict[str, str] | None = None) -> bool:
    """Known anomalies of a tracked container; previous is its prior sample.

    A restart counts only as an increase over that sample, so a container that
    restarted once long ago is not flagged forever. D uses the host's elevated
    threshold.
    """
    if row.get('is_tracked_project') != '1':
        return False
    restarts = as_int(row.get('restart_count'))
    before = as_int((previous or {}).get('restart_count'))
    restarted = restarts is not None and before is not None and restarts > before
    return (row.get('oom_killed') == 'true' or row.get('health') == 'unhealthy' or restarted
            or (as_int(row.get('zombies')) or 0) > 0 or (as_int(row.get('dstate')) or 0) >= 4)


DOCKER_UNAVAILABLE_REASONS = {
    "permission": "Docker socket 權限不足",
    "no_socket": "找不到 Docker socket",
    "no_daemon": "Docker 未執行",
    "nonlocal": "非本機 Docker endpoint",
    "timeout": "查詢逾時",
    "helper_failed": "採樣程式失敗",
    "error": "查詢失敗",
}


def docker_state_label(state: str) -> str:
    """The collector's Docker state with the recorded reason spelled out."""
    if state != "unavailable" and not state.startswith("unavailable:"):
        return state
    reason = state.partition(":")[2]
    if not reason:
        return "不可用（原因未記錄）"
    return f"不可用（{DOCKER_UNAVAILABLE_REASONS.get(reason, reason)}）"


CONTAINER_SAMPLE_GAPS = {
    "unavailable_or_timeout": "查詢逾時或失敗",
    "stopped": "已停止，無即時負載",
    "unavailable": "Docker 不可用",
}


def container_summary(row: dict[str, str], previous: dict[str, str] | None = None) -> tuple[str, str]:
    """The one-line text and style of a container in the list.

    Missing figures must not look like a healthy container, so a row without
    a complete live sample gets its own style; a known anomaly still wins.
    """
    state = row.get("container_state") or "未知"
    status = row.get("sample_status")
    cpu = as_float(row.get("cpu_pct"))
    memory = (row.get("memory_usage") or "NA").split(" / ")[0]
    if status in CONTAINER_SAMPLE_GAPS:
        text = f"{state} · 未知（{CONTAINER_SAMPLE_GAPS[status]}）"
    else:
        cpu_text = "CPU 未知" if cpu is None else f"{cpu:.1f}%"
        memory_text = "記憶體未知" if memory in ("", "NA") else memory
        text = f"{state} · {cpu_text} · {memory_text}"
    complete = status == "ok" and cpu is not None and memory not in ("", "NA")
    if container_warning(row, previous):
        return text, "warm"
    return text, "muted" if complete else "unknown"


def container_signature(rows: list[dict[str, str]]) -> tuple:
    """Everything a container row renders, and nothing else.

    Emptying a list shrinks the scrolled content, which clamps the scroll
    position, and refilling it does not put the position back. Comparing this
    against the previous refresh is what keeps an unchanged list untouched.
    """
    return tuple(
        (
            row.get("container"),
            row.get("cpu_pct"),
            row.get("memory_usage"),
            row.get("zombies"),
            row.get("evidence_detail"),
            row.get("history_signature"),
        )
        for row in rows
    )


def stall_positions(rows: list[dict[str, str]], factor: int = 3) -> list[int]:
    """Indices where sampling fell behind, derived from the samples themselves.

    A ribbon that only draws temperature hides the most telling thing in the
    window: the moment the machine stopped scheduling the collector.
    """
    intervals: list[int] = []
    epochs = [as_int(row.get("epoch")) for row in rows]
    for previous, current in zip(epochs, epochs[1:]):
        if previous is not None and current is not None:
            intervals.append(current - previous)

    usual = min((gap for gap in intervals if gap > 0), default=0)
    if usual <= 0:
        return []

    positions = []
    for index, gap in enumerate(intervals, start=1):
        if gap >= usual * factor:
            positions.append(index)
    return positions


class ThermalRibbon(Gtk.DrawingArea):
    """Three quiet thermal lanes: CPU, GPU and NVMe over recent samples."""

    def __init__(self):
        super().__init__()
        self.history: list[dict[str, Any]] = []
        self.stalls: list[int] = []
        self.hover_index: int | None = None
        self.set_content_height(76)
        self.set_size_request(-1, 76)
        self.set_hexpand(True)
        self.set_vexpand(False)
        self.set_valign(Gtk.Align.START)
        self.set_tooltip_text("滑鼠懸停可查看各時間點的感測器溫度與停擺紀錄")
        self.set_draw_func(self._draw)

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_motion)
        motion.connect("leave", self._on_leave)
        self.add_controller(motion)

    def set_history(self, rows: list[dict[str, str]]) -> None:
        visible = rows[-HISTORY_ROWS:]
        self.history = [
            {
                "timestamp": row.get("timestamp", ""),
                "cpu": self._from_millidegree(row.get("cpu_temp_mC")),
                "gpu": self._from_millidegree(row.get("gpu_temp_mC")),
                "nvme": self._from_millidegree(row.get("nvme_temp_mC")),
            }
            for row in visible
        ]
        self.stalls = stall_positions(visible)
        if self.hover_index is not None:
            if 0 <= self.hover_index < len(self.history):
                self._update_hover_tooltip(self.hover_index)
            else:
                self.hover_index = None
        self.queue_draw()

    def _on_motion(self, _controller, x: float, _y: float) -> None:
        width = self.get_width()
        if not self.history or width <= 0:
            return
        step = max(width / len(self.history), 1)
        index = max(0, min(int(x / step), len(self.history) - 1))
        if index != self.hover_index:
            self.hover_index = index
            self._update_hover_tooltip(index)
            self.queue_draw()

    def _on_leave(self, _controller) -> None:
        if self.hover_index is not None:
            self.hover_index = None
            self.set_tooltip_text("滑鼠懸停可查看各時間點的感測器溫度與停擺紀錄")
            self.queue_draw()

    def _update_hover_tooltip(self, index: int) -> None:
        sample = self.history[index]
        self.set_tooltip_text(ribbon_sample_tooltip(sample, index in self.stalls))

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

    @staticmethod
    def _short_time(timestamp: Any) -> str:
        text = str(timestamp or "")
        if "T" in text:
            return text.split("T", 1)[1][:8]
        return text[:8]

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

        for position in self.stalls:
            x = position * step
            context.set_source_rgb(0.95, 0.35, 0.32)
            context.rectangle(max(0, x - 1), 0, 2, height)
            context.fill()

        if self.hover_index is not None and 0 <= self.hover_index < len(self.history):
            hx = self.hover_index * step
            context.set_source_rgba(0.92, 0.97, 1.0, 0.85)
            context.rectangle(max(0, hx), 0, max(step, 2), height)
            context.fill()

        # Subtle start and end timestamps anchor the 30-minute window.
        start_time = self._short_time(self.history[0].get("timestamp"))
        end_time = self._short_time(self.history[-1].get("timestamp"))
        if start_time and end_time and width >= 180:
            context.set_font_size(9.5)
            context.set_source_rgba(0.86, 0.93, 0.96, 0.72)
            context.move_to(48, height - 6)
            context.show_text(start_time)
            context.move_to(max(110, width - 54), height - 6)
            context.show_text(end_time)


class FreezeWatch(Gtk.Application):
    def __init__(self, start_hidden: bool):
        super().__init__(application_id=APP_ID)
        self.start_hidden = start_hidden
        self.window: Gtk.ApplicationWindow | None = None
        self.incident_bar: Gtk.Box | None = None
        self.incident_dropdown: Gtk.DropDown | None = None
        self.live_button: Gtk.Button | None = None
        self.scroll: Gtk.ScrolledWindow | None = None
        self.container_signature: tuple | None = None
        self.event_signature: tuple | None = None
        self.process_signature: tuple | None = None
        self.incidents: list[Incident] = []
        self.incident_signature: tuple[str, ...] = ()
        self.selected_incident: Incident | None = None
        self.tray: StatusNotifierItem | None = None
        self.ribbon: ThermalRibbon | None = None
        self.labels: dict[str, Gtk.Label] = {}
        self.export_button: Gtk.Button | None = None
        self.temperature_cards: dict[str, tuple[Gtk.Label, Gtk.Label, Gtk.Widget]] = {}
        self.container_list: Gtk.ListBox | None = None
        self.event_list: Gtk.ListBox | None = None
        self.cpu_process_list: Gtk.ListBox | None = None
        self.memory_process_list: Gtk.ListBox | None = None
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
            .hero.reviewing { background: #1f1916; border-color: #8a5628; }
            .eyebrow { color: #77bfce; font-size: 11px; font-weight: 700;
                       letter-spacing: 1.7px; }
            dropdown > button { background: #1b262d; color: #e6eef2;
                                border: 1px solid #33434d; border-radius: 8px;
                                padding: 6px 10px; min-width: 190px; }
            dropdown > button:hover { background: #23313a; }
            dropdown > button label { color: #e6eef2; }
            dropdown popover contents { background: #151d23;
                                        background-image: none; color: #e6eef2; }
            dropdown popover listview { background: #151d23; color: #e6eef2; }
            dropdown popover row { background: #151d23; background-image: none;
                                   color: #e6eef2; }
            dropdown popover row:hover { background: #263b47; }
            dropdown popover row:selected { background: #304d5c; }
            dropdown popover row label,
            dropdown popover row image { color: #e6eef2; }
            .hero-value { font-size: 42px; font-weight: 700; letter-spacing: -1px; }
            .hero-title { font-size: 19px; font-weight: 700; }
            .muted { color: #9badb7; font-size: 12px; }
            .metric-card { background: #151d23; border: 1px solid #28343c;
                           border-radius: 10px; padding: 14px 16px; }
            .metric-card.warm { border-color: #6b5f35; }
            .metric-card.hot { border-color: #8a5628; background: #1c1a17; }
            .metric-card.danger { border-color: #8c3835; background: #1f1618; }
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
            .data-list row label.safe { color: #79c4d3; }
            .data-list row label.warm { color: #d8c568; }
            .data-list row label.hot { color: #f0a046; }
            .data-list row label.danger { color: #ef6861; }
            .data-list row label.unknown { color: #b4a7e0; font-style: italic; }
            .safe { color: #79c4d3; } .warm { color: #d8c568; }
            .hot { color: #f0a046; } .danger { color: #ef6861; }
            .status-pill { font-size: 12px; font-weight: 700; }
            .button-flat { background: #1d2e37; color: #d9f0f5;
                           border: 1px solid #33505e; border-radius: 8px;
                           padding: 6px 12px; font-weight: 700; }
            .button-flat:hover { background: #263d49; }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    @staticmethod
    def _label(
        text: str = "",
        css_class: str | None = None,
        xalign: float = 0,
        ellipsize: bool = False,
    ) -> Gtk.Label:
        label = Gtk.Label(label=text, xalign=xalign)
        if ellipsize:
            # A label that can neither wrap nor ellipsize reports the width of
            # its whole text as its minimum. The horizontal scroll policy hands
            # that minimum straight to the window, so any row carrying an
            # arbitrary string has to be able to shorten itself. Fixed captions
            # are left alone: making them shrinkable only lets the layout
            # squeeze them below their natural width.
            label.set_ellipsize(Pango.EllipsizeMode.END)
        if css_class:
            label.add_css_class(css_class)
        return label

    def _metric_card(self, key: str, detail: str = "") -> Gtk.Box:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.add_css_class("metric-card")
        card.set_hexpand(True)
        tooltip = CARD_TOOLTIPS.get(key.lower())
        if tooltip:
            card.set_tooltip_text(tooltip)
        card.append(self._label(key, "metric-key"))
        value = self._label("—", "metric-value")
        detail_label = self._label(detail, "muted")
        card.append(value)
        card.append(detail_label)
        self.temperature_cards[key.lower()] = (value, detail_label, card)
        return card

    def _build_window(self) -> None:
        self.window = Gtk.ApplicationWindow(application=self, title="Freeze Watch")
        self.window.set_default_size(*self._default_window_size())
        self.window.set_size_request(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
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
        self.export_button = Gtk.Button(label="預覽診斷報告")
        self.export_button.set_sensitive(False)
        self.export_button.connect("clicked", self._preview_report)
        header.pack_end(self.export_button)

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
        self.scroll = scroll
        root.append(scroll)
        self.window.set_child(root)

        # Incidents sit above the live readings. The dashboard is opened after
        # something went wrong far more often than to watch a healthy machine,
        # and the panel that answers that question used to be below the fold.
        self.incident_bar = Gtk.Box(spacing=12)
        self.incident_bar.add_css_class("hero")
        self.incident_bar.set_visible(False)
        incident_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        incident_text.set_hexpand(True)
        self.labels["incident_eyebrow"] = self._label("事故回顧", "eyebrow")
        incident_text.append(self.labels["incident_eyebrow"])
        self.labels["incident_summary"] = self._label("", "muted", ellipsize=True)
        incident_text.append(self.labels["incident_summary"])
        self.incident_bar.append(incident_text)
        self.live_button = Gtk.Button(label="返回即時監測")
        self.live_button.add_css_class("button-flat")
        self.live_button.set_valign(Gtk.Align.CENTER)
        self.live_button.set_tooltip_text("結束歷史事故檢視，切回目前即時感測器讀數")
        self.live_button.set_visible(False)
        self.live_button.connect("clicked", self._return_to_live)
        self.incident_bar.append(self.live_button)
        self.incident_dropdown = Gtk.DropDown.new_from_strings(["即時監測"])
        self.incident_dropdown.set_valign(Gtk.Align.CENTER)
        self.incident_dropdown.set_tooltip_text("選擇過去記錄到的凍結或停擺事件，檢視事發前 30 分鐘的系統狀態")
        self.incident_dropdown.connect("notify::selected", self._on_incident_selected)
        self.incident_bar.append(self.incident_dropdown)
        content.append(self.incident_bar)

        hero = Gtk.Box(spacing=24)
        hero.add_css_class("hero")
        hero.set_hexpand(True)
        hero.set_valign(Gtk.Align.START)
        hero.set_vexpand(False)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        left.set_hexpand(True)
        left.set_valign(Gtk.Align.START)
        left.set_vexpand(False)
        self.labels["hero_eyebrow"] = self._label("即時熱度", "eyebrow")
        left.append(self.labels["hero_eyebrow"])
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

        ribbon_header = Gtk.Box(spacing=8)
        self.labels["ribbon_title"] = self._label("最近 30 分鐘熱度帶", "section-title")
        self.labels["ribbon_title"].set_hexpand(True)
        ribbon_header.append(self.labels["ribbon_title"])
        ribbon_hint = self._label("懸停可查看時間點數值 · 紅線為取樣停擺", "muted")
        ribbon_header.append(ribbon_hint)
        content.append(ribbon_header)
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

        process_split = Gtk.Grid(column_spacing=18, row_spacing=12)
        process_split.set_column_homogeneous(True)
        cpu_proc_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        cpu_proc_column.append(self._label("目前最活躍程序（CPU）", "section-title"))
        self.cpu_process_list = Gtk.ListBox()
        self.cpu_process_list.add_css_class("data-list")
        self.cpu_process_list.set_selection_mode(Gtk.SelectionMode.NONE)
        cpu_proc_column.append(self.cpu_process_list)
        process_split.attach(cpu_proc_column, 0, 0, 1, 1)

        mem_proc_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        mem_proc_column.append(self._label("佔用記憶體最多的程序（RAM）", "section-title"))
        self.memory_process_list = Gtk.ListBox()
        self.memory_process_list.add_css_class("data-list")
        self.memory_process_list.set_selection_mode(Gtk.SelectionMode.NONE)
        mem_proc_column.append(self.memory_process_list)
        process_split.attach(mem_proc_column, 1, 0, 1, 1)
        content.append(process_split)

        for key in ("top_processes", "top_memory_processes"):
            self.labels[key] = self._label("—", "muted")
            self.labels[key].set_wrap(True)
            self.labels[key].set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            self.labels[key].set_max_width_chars(40)
            self.labels[key].set_visible(False)
            content.append(self.labels[key])

        content.append(self._label("GPU 裝置持有者與引擎活動", "section-title"))
        self.labels["gpu_processes"] = self._label("—", "muted")
        self.labels["gpu_processes"].set_wrap(True)
        self.labels["gpu_processes"].set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.labels["gpu_processes"].set_max_width_chars(40)
        content.append(self.labels["gpu_processes"])

    @staticmethod
    def _default_window_size() -> tuple[int, int]:
        """Open no larger than the monitor, leaving room for panels."""
        display = Gdk.Display.get_default()
        monitors = display.get_monitors() if display is not None else None
        monitor = (
            monitors.get_item(0)
            if monitors is not None and monitors.get_n_items()
            else None
        )
        if monitor is None:
            return WINDOW_PREFERRED_WIDTH, WINDOW_PREFERRED_HEIGHT

        area = monitor.get_geometry()
        return clamp_window_size(area.width, area.height)

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

    def _update_system_card(
        self, index: int, key: str, value_text: str, detail_text: str, level: str
    ) -> None:
        self.labels[f"system_{index}"].set_text(value_text)
        self.labels[f"system_detail_{index}"].set_text(detail_text)
        card_entry = self.temperature_cards.get(key.lower())
        if card_entry is not None:
            label, _detail_label, card = card_entry
            self._set_level_class(label, level)
            self._set_level_class(card, level)

    @staticmethod
    def _clear_list(list_box: Gtk.ListBox) -> None:
        while child := list_box.get_first_child():
            list_box.remove(child)

    def _container_popup_open(self) -> bool:
        def descendants(widget):
            child = widget.get_first_child()
            while child:
                yield child
                yield from descendants(child)
                child = child.get_next_sibling()

        return self.container_list is not None and any(
            isinstance(widget, Gtk.Popover) and widget.get_mapped()
            for widget in descendants(self.container_list)
        )

    def _append_container_row(self, row: dict[str, str], history=None, metrics=None, expanded=False) -> None:
        if self.container_list is None:
            return
        history = history or [row]
        metrics = metrics or []
        container_row = Gtk.ListBoxRow()
        container_row.add_css_class("data-row")
        expander = Gtk.Expander()
        expander.set_name(row.get("container_id", row.get("container", "unknown")))
        expander.set_expanded(expanded)
        content = Gtk.Box(spacing=10)
        name = self._label(row.get("container", "unknown"), None, ellipsize=True)
        name.set_hexpand(True)
        summary, style = container_summary(row, previous_restart_sample(history[:-1]))
        detail_label = self._label(summary, style, 1, ellipsize=True)
        content.append(name)
        content.append(detail_label)
        expander.set_label_widget(content)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        choices = history[-60:][::-1]
        dropdown = Gtk.DropDown.new_from_strings([r.get("timestamp", "未知") for r in choices])
        dropdown.set_tooltip_text("選擇已保存的容器樣本，同時顯示此前 45 秒內主機溫度與 PSI。最多 60 筆。")
        box.append(dropdown)
        detail = self._label("", "muted", ellipsize=False)
        detail.set_wrap(True)
        detail.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        detail.set_max_width_chars(35)
        detail.set_selectable(True)
        box.append(detail)
        key = expander.get_name()
        selections = getattr(self, "container_selections", {})
        self.container_selections = selections
        selected = next((i for i, r in enumerate(choices) if r.get("epoch") == selections.get(key)), 0)
        dropdown.set_selected(selected)
        detail.set_text(container_detail(choices[selected], metrics))

        def select_sample(widget, _parameter):
            index = widget.get_selected()
            if index < len(choices):
                selections[key] = choices[index].get("epoch")
                detail.set_text(container_detail(choices[index], metrics))

        dropdown.connect("notify::selected", select_sample)
        expander.set_child(box)
        container_row.set_tooltip_text("警示條件（僅追蹤中的專案）：OOM、不健康、較前一次採樣新增重啟、Z 大於 0，或 D 達 4。未知不視為正常，資料不完整的列以紫色斜體顯示；展開查看採樣時間與原因。")
        container_row.set_child(expander)
        self.container_list.append(container_row)

    def _append_process_row(
        self, list_box: Gtk.ListBox | None, name_text: str, cpu_text: str, mem_text: str
    ) -> None:
        if list_box is None:
            return
        row = Gtk.ListBoxRow()
        row.add_css_class("data-row")
        content = Gtk.Box(spacing=10)
        content.add_css_class("list-row")
        name = self._label(name_text, None, ellipsize=True)
        name.set_hexpand(True)
        content.append(name)
        if cpu_text != "—" or mem_text != "—":
            cpu_val = as_float(cpu_text) or 0.0
            mem_val = as_float(mem_text) or 0.0
            detail_class = (
                "hot"
                if cpu_val >= 90.0 or mem_val >= 25.0
                else ("warm" if cpu_val >= 50.0 or mem_val >= 12.0 else "muted")
            )
            detail = f"CPU {cpu_text}  ·  RAM {mem_text}"
            content.append(self._label(detail, detail_class, 1, ellipsize=True))
        row.set_child(content)
        list_box.append(row)

    def _populate_process_list(
        self, list_box: Gtk.ListBox | None, raw: str | None
    ) -> None:
        if list_box is None:
            return
        self._clear_list(list_box)
        entries = parse_process_entries(raw)
        if not entries:
            self._append_process_row(list_box, "尚無程序資料", "—", "—")
            return
        for name, cpu, mem in entries:
            self._append_process_row(list_box, name, cpu, mem)

    def _append_event_row(self, event: str) -> None:
        if self.event_list is None:
            return
        row = Gtk.ListBoxRow()
        row.add_css_class("data-row")
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        content.add_css_class("list-row")
        parts = event.split("\t", 2)
        timestamp = parts[0] if parts else "—"
        kind = parts[1] if len(parts) > 2 else ""
        message = parts[-1] if parts else event

        # Wrapped rather than ellipsized: the end of a freeze message carries
        # the sample timestamp and the file it was cut off from, which is the
        # part worth reading. Wrapping on word or character boundaries keeps
        # the minimum width small, which an ellipsized label also does but a
        # plain one does not.
        body_class = (
            "danger"
            if kind in ("UNCLEAN", "FREEZE", "KERNEL")
            else ("warm" if kind in ("GAP", "INTERRUPTED", "WARN") else None)
        )
        body = self._label(message, body_class)
        body.set_wrap(True)
        body.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        body.set_max_width_chars(48)
        content.append(body)
        meta_text = f"{timestamp.replace('T', ' ')[:19]} · {kind}" if kind else timestamp
        content.append(self._label(meta_text, "muted", ellipsize=True))
        row.set_child(content)
        self.event_list.append(row)

    def _return_to_live(self, _button=None) -> None:
        if self.incident_dropdown is not None:
            self.incident_dropdown.set_selected(0)

    def _on_incident_selected(self, dropdown, _parameter) -> None:
        index = dropdown.get_selected()
        self.selected_incident = (
            self.incidents[index - 1] if 0 < index <= len(self.incidents) else None
        )
        self.refresh()

    def _preview_report(self, _button) -> Gtk.Window | None:
        if self.selected_incident is None:
            return None
        report = diagnostic_report(self.selected_incident)
        preview = Gtk.Window(title="診斷報告預覽", transient_for=self.window, modal=True)
        preview.set_default_size(760, 540)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        preview.set_child(box)
        view = Gtk.TextView(editable=False, monospace=True)
        view.get_buffer().set_text(report)
        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scroll.set_child(view)
        box.append(scroll)
        status = self._label("已省略路徑、程序名稱與參數；確認內容後再儲存。", "muted")
        status.set_wrap(True)
        box.append(status)
        save = Gtk.Button(label="匯出文字檔")
        save.connect("clicked", lambda _button: self._save_report(preview, report, status))
        box.append(save)
        preview.present()
        return preview

    def _save_report(self, preview: Gtk.Window, report: str, status: Gtk.Label):
        chooser = Gtk.FileChooserNative.new("匯出診斷報告", preview, Gtk.FileChooserAction.SAVE, "儲存", "取消")
        chooser.set_current_name("freeze-watch-report.txt")

        def response(dialog, result):
            if result == Gtk.ResponseType.ACCEPT:
                file = dialog.get_file()
                path = file.get_path() if file is not None else None
                if path is None:
                    status.set_text("請選擇本機檔案位置。")
                else:
                    try:
                        write_diagnostic_report(Path(path), report)
                        status.set_text("診斷報告已儲存。")
                    except OSError as error:
                        status.set_text(f"無法儲存：{error.strerror}")
            dialog.destroy()
            preview.report_chooser = None

        chooser.connect("response", response)
        preview.report_chooser = chooser
        chooser.show()
        return chooser

    def _sync_incidents(self) -> None:
        """Keep the selector in step with the log without losing the choice."""
        if self.incident_dropdown is None or self.incident_bar is None:
            return

        self.incidents = read_incidents()
        signature = tuple(incident.timestamp for incident in self.incidents)
        self.incident_bar.set_visible(bool(self.incidents))
        if signature == self.incident_signature:
            return
        self.incident_signature = signature

        chosen = self.selected_incident
        model = Gtk.StringList.new(
            ["即時監測"] + [incident.label for incident in self.incidents]
        )
        self.incident_dropdown.set_model(model)

        position = 0
        if chosen is not None:
            for index, incident in enumerate(self.incidents, start=1):
                if incident.timestamp == chosen.timestamp:
                    position = index
                    break
        self.selected_incident = self.incidents[position - 1] if position else None
        self.incident_dropdown.set_selected(position)

    def _recent_events(self) -> list[str]:
        event_log = STATE_DIR / "events.log"
        lines = [line for line in tail_text(event_log, 24_000).splitlines() if line.strip()]
        meaningful = [
            line
            for line in lines
            if any(f"\t{kind}\t" in line for kind in NOTEWORTHY_EVENTS)
        ]
        return (meaningful or lines)[-EVENT_HISTORY_LIMIT:][::-1]

    def present_dashboard(self) -> bool:
        if self.window is None:
            self._build_window()
            self.refresh()
        self.window.present()
        return False

    def refresh(self) -> bool:
        self._sync_incidents()
        reviewing = self.selected_incident is not None

        if reviewing:
            metric_rows = incident_rows(self.selected_incident)
        else:
            metric_rows = read_tsv_tail("metrics-*.tsv", METRICS_FIELDS)
        latest_metric = metric_rows[-1] if metric_rows else {}
        if not metric_rows:
            source = self.selected_incident.metrics_path if reviewing else newest_file("metrics-*.tsv")
            if empty_sample_status(source):
                latest_metric = {"_incomplete": "yes"}

        if reviewing:
            # Reviewing means showing what was recorded, never what the sensors
            # say now, or the page would mix an old freeze with a healthy present.
            temperatures = {
                name: self._temperature_from_metric(latest_metric, column)
                for name, column in (
                    ("cpu", "cpu_temp_mC"),
                    ("gpu", "gpu_temp_mC"),
                    ("nvme", "nvme_temp_mC"),
                )
            }
        else:
            # Each reading falls back on its own. Testing them together meant one
            # readable sensor suppressed the recorded values for every other field.
            temperatures = direct_temperatures()
            for name, column in (
                ("cpu", "cpu_temp_mC"),
                ("gpu", "gpu_temp_mC"),
                ("nvme", "nvme_temp_mC"),
            ):
                if temperatures[name] is None:
                    temperatures[name] = self._temperature_from_metric(
                        latest_metric, column
                    )
        level = temperature_level(temperatures)
        status, status_detail = level_copy(level)
        freshness = "" if reviewing else sample_freshness(latest_metric, time.time())
        if freshness:
            status = "監測資料需注意"
            status_detail = freshness
        elif reviewing and latest_metric.get("_incomplete") == "yes":
            status = "監測資料需注意"
            status_detail += " · 資料不完整；已略過損壞列"

        # The tray always shows the machine as it is now. A review is something
        # the reader asked for; the indicator is not.
        if self.tray is not None and not reviewing:
            self.tray.update(temperatures, level)

        if self.window is None:
            return True
        if self.export_button is not None:
            self.export_button.set_sensitive(reviewing)

        if self.incident_bar is not None:
            if reviewing:
                self.incident_bar.add_css_class("reviewing")
            else:
                self.incident_bar.remove_css_class("reviewing")
        if self.live_button is not None:
            self.live_button.set_visible(reviewing)

        if reviewing:
            incident = self.selected_incident
            if "incident_eyebrow" in self.labels:
                self.labels["incident_eyebrow"].set_text(
                    f"正在檢視歷史事故 · {'非正常關機／疑似當機' if incident.kind in ('FREEZE', 'UNCLEAN') else '取樣停擺'}"
                )
            self.labels["incident_summary"].set_text(format_incident_summary(incident))
            self.labels["incident_summary"].set_tooltip_text(incident.message)
            self.labels["hero_eyebrow"].set_text("事故當下熱度")
            self.labels["ribbon_title"].set_text(
                f"事故前 30 分鐘熱度帶 · {incident.timestamp.replace('T', ' ')[:19]}"
            )
        else:
            if "incident_eyebrow" in self.labels:
                self.labels["incident_eyebrow"].set_text("事故回顧")
            self.labels["hero_eyebrow"].set_text("即時熱度")
            self.labels["ribbon_title"].set_text("最近 30 分鐘熱度帶")
            if self.incidents:
                self.labels["incident_summary"].set_text(
                    f"記錄到 {len(self.incidents)} 次事故，最近一次 "
                    f"{self.incidents[0].timestamp.replace('T', ' ')[:16]}"
                )
                self.labels["incident_summary"].set_tooltip_text(
                    self.incidents[0].message
                )

        self.labels["hero_temp"].set_text(format_temperature(temperatures["cpu"]))
        self.labels["hero_status"].set_text(status)
        self.labels["hero_detail"].set_text(
            f"GPU {format_temperature(temperatures['gpu'])}  ·  "
            f"NVMe {format_temperature(temperatures['nvme'])}  ·  {status_detail}"
        )
        self._set_level_class(self.labels["hero_temp"], level)
        self._set_level_class(self.labels["hero_status"], level)

        docker_state = docker_state_label(latest_metric.get("docker_state", "—"))
        container_count = latest_metric.get("docker_containers", "—")
        available_kib = as_int(latest_metric.get("mem_available_kib"))
        self.labels["hero_memory"].set_text(f"可用記憶體 {format_gib(available_kib)}")

        # Throttling belongs beside the temperature that caused it.
        throttles = latest_metric.get("cpu_throttle_count", "—")
        cpu_detail = "核心溫度"
        if throttles not in ("—", "NA", None):
            cpu_detail = f"核心溫度 · 節流 {throttles} 次"

        for name, value, detail in (
            ("cpu", temperatures["cpu"], cpu_detail),
            ("gpu", temperatures["gpu"], "顯示核心"),
            ("nvme", temperatures["nvme"], "儲存裝置"),
        ):
            self._update_temperature_card(name, value, detail, temperature_level({name: value}))

        swapin_pages = as_int(latest_metric.get("swapin_pages"))
        mem_lvl = memory_level(available_kib, swapin_pages)
        # Swap read back is the one that hurts: it is memory the machine had
        # already given away and now has to wait for.
        self._update_system_card(
            0,
            "可用記憶體",
            format_gib(available_kib),
            (
                f"swap {format_gib(as_int(latest_metric.get('swap_used_kib')))} · "
                f"換入 {latest_metric.get('swapin_pages', '—')} 頁"
            ),
            mem_lvl,
        )

        load1_val = as_float(latest_metric.get("load1"))
        dstate_val = as_int(latest_metric.get("dstate_count"))
        load_lvl = load_level(load1_val, dstate_val)
        # Uninterruptible sleepers sit beside the load average because they are
        # what makes it climb while nothing is using the CPU.
        self._update_system_card(
            1,
            "負載",
            latest_metric.get("load1", "—"),
            (
                f"5m {latest_metric.get('load5', '—')} · "
                f"15m {latest_metric.get('load15', '—')} · "
                f"D {latest_metric.get('dstate_count', '—')}"
            ),
            load_lvl,
        )

        psi_lvl = pressure_level(
            as_float(latest_metric.get("io_psi_avg10")),
            as_float(latest_metric.get("io_psi_full_avg10")),
            as_float(latest_metric.get("memory_psi_full_avg10")),
            as_float(latest_metric.get("cpu_psi_avg10")),
            as_float(latest_metric.get("memory_psi_avg10")),
        )
        self._update_system_card(
            2,
            "I/O 壓力",
            f"{latest_metric.get('io_psi_avg10', '—')}%",
            (
                f"全停 {latest_metric.get('io_psi_full_avg10', '—')}% · "
                f"CPU {latest_metric.get('cpu_psi_avg10', '—')}% · "
                f"RAM {latest_metric.get('memory_psi_avg10', '—')}%"
            ),
            psi_lvl,
        )

        disk_lvl = disk_level(
            as_float(latest_metric.get("root_used_pct")),
            as_int(latest_metric.get("disk_in_flight")),
            as_float(latest_metric.get("disk_busy_ms")),
            SAMPLE_INTERVAL_SECONDS,
        )
        self._update_system_card(
            3,
            "根目錄",
            f"{latest_metric.get('root_used_pct', '—')}%",
            (
                f"根目錄 · 佇列 {latest_metric.get('disk_in_flight', '—')} · "
                f"忙碌 {format_busy(latest_metric.get('disk_busy_ms'), SAMPLE_INTERVAL_SECONDS)}"
            ),
            disk_lvl,
        )

        for key in ("top_processes", "top_memory_processes"):
            listing = latest_metric.get(key)
            self.labels[key].set_text(format_process_listing(listing))
        self.labels["gpu_processes"].set_text(gpu_summary(latest_metric.get("gpu_processes")))

        if self.ribbon is not None:
            self.ribbon.set_history(metric_rows)

        if reviewing:
            # The collector names both files from the same stamp, so the
            # container sample beside an incident is one substitution away.
            docker_path = docker_path_for(self.selected_incident.metrics_path)
            end = incident_end(self.selected_incident)
            docker_rows = (
                read_tsv_path(docker_path, DOCKER_FIELDS, 2_000_000) if end is None
                else read_tsv_before(docker_path, DOCKER_FIELDS, end)
            )
        else:
            docker_rows = read_tsv_path(newest_file("docker-*.tsv"), DOCKER_FIELDS, 2_000_000)
        current_containers = latest_containers(docker_rows)
        histories = {}
        for row in current_containers:
            identity = row.get("container_id")
            history = [r for r in docker_rows if (
                r.get("container_id") == identity if identity not in (None, "NA", "")
                else r.get("container") == row.get("container")
            ) and r.get("container")][-60:]
            histories[row.get("container")] = history
            row["evidence_detail"] = container_detail(row, metric_rows)
            row["history_signature"] = str([(r.get("epoch"), r.get("process_status")) for r in history])
        if "hero_docker" in self.labels:
            last = docker_rows[-1] if docker_rows else {}
            stamp = last.get("timestamp", "未知")
            age = (as_float(latest_metric.get("epoch")) or 0) - (as_float(last.get("epoch")) or 0)
            freshness = " · 資料過期／缺口" if age > 60 else ""
            self.labels["hero_docker"].set_text(f"DOCKER {container_count} · {docker_state} · 最後採樣 {stamp}{freshness}")
        # Emptying a list shrinks the content, which clamps the scroll position
        # to the smaller extent; refilling it does not put the position back.
        # Refreshing every two seconds therefore walked the view up the page
        # whenever anyone scrolled down. Rebuild only on a real change, and put
        # the position back once the new contents have been laid out.
        events = self._recent_events()
        containers = container_signature(current_containers)
        event_signature = tuple(events)
        processes_sig = (
            latest_metric.get("top_processes", ""),
            latest_metric.get("top_memory_processes", ""),
        )

        # Rebuilding destroys an open history menu under the pointer; the
        # signature stays stale, so the rebuild happens once the menu closes.
        rebuild_containers = (
            self.container_list is not None
            and containers != self.container_signature
            and not self._container_popup_open()
        )
        rebuild_events = (
            self.event_list is not None and event_signature != self.event_signature
        )
        rebuild_processes = (
            (self.cpu_process_list is not None or self.memory_process_list is not None)
            and processes_sig != self.process_signature
        )

        if rebuild_containers or rebuild_events or rebuild_processes:
            adjustment = self.scroll.get_vadjustment() if self.scroll else None
            position = adjustment.get_value() if adjustment is not None else 0.0

            if rebuild_containers:
                self.container_signature = containers
                expanded = set()
                child = self.container_list.get_first_child()
                while child:
                    expander = child.get_child()
                    if isinstance(expander, Gtk.Expander) and expander.get_expanded():
                        expanded.add(expander.get_name())
                    child = child.get_next_sibling()
                self._clear_list(self.container_list)
                for row in current_containers:
                    key = row.get("container_id", row.get("container", "unknown"))
                    self._append_container_row(row, histories.get(row.get("container")), metric_rows, key in expanded)

            if rebuild_events:
                self.event_signature = event_signature
                self._clear_list(self.event_list)
                for event in events:
                    self._append_event_row(event)

            if rebuild_processes:
                self.process_signature = processes_sig
                self._populate_process_list(
                    self.cpu_process_list, latest_metric.get("top_processes")
                )
                self._populate_process_list(
                    self.memory_process_list, latest_metric.get("top_memory_processes")
                )

            if adjustment is not None and position > 0:
                GLib.idle_add(self._restore_scroll, adjustment, position)

        return True

    @staticmethod
    def _restore_scroll(adjustment: Gtk.Adjustment, position: float) -> bool:
        # Runs from the idle queue, after the rebuilt contents have been laid
        # out. Setting the value any earlier would clamp it against the extent
        # of the emptied list, which is the very thing being undone.
        # Gtk.Adjustment clamps to the valid range itself.
        adjustment.set_value(position)
        return False

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
