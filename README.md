# Freeze Watch

A lightweight Linux freeze-diagnostics collector with a native GTK4 dashboard,
Docker process monitoring, and a live CPU-temperature tray label.

Freeze Watch was built to investigate hard desktop freezes where keyboard and
mouse input stop responding. It keeps low-overhead, disk-backed evidence across
the period immediately before a forced reboot.

## Features

- freeze, stall, and unclean-shutdown markers naming the last sample recorded
- kernel evidence for GPU hangs, hung tasks, RCU stalls, and device timeouts
- CPU, GPU, and NVMe temperatures on AMD, Intel, and ARM hardware
- load averages, memory, swap, filesystem usage, and Linux PSI pressure,
  including the `full` figures and processes in uninterruptible sleep
- GPU busy percentage, and top processes by CPU and by memory
- CPU throttling, swap traffic, major faults, and disk queue depth
- Docker CPU, memory, task counts, OOM state, restarts, and zombie detection
- optional deep monitoring of one Docker Compose project
- live `CPU 58°` StatusNotifier/AppIndicator label
- dedicated full-colour launcher icon and symbolic tray icons
- GTK4 dashboard with a 30-minute thermal ribbon and stall markers
- incident review showing the half hour before any recorded freeze or stall
- warns when live samples are over 60 seconds old or saved rows are damaged;
  diagnostic reports identify available evidence
- daily log rotation, compression after 14 days, expiration after 90 days
- user-level systemd services; no root daemon

## Requirements

- Linux with systemd user services
- Python 3, PyGObject/GTK4, and dbus-python
- Bash and standard GNU/Linux utilities
- Docker is optional
- a StatusNotifier/AppIndicator host for the tray item

| Distribution | Packages |
| --- | --- |
| Debian, Ubuntu | `python3 python3-gi python3-dbus gir1.2-gtk-4.0` |
| Fedora, RHEL | `python3 python3-gobject python3-dbus gtk4` |
| Arch | `python python-gobject python-dbus gtk4` |
| openSUSE | `python3-gobject python3-gobject-Gdk python3-dbus-python typelib-1_0-Gtk-4_0` |
| Alpine | `python3 py3-gobject3 py3-dbus gtk4.0` |
| Void | `python3-gobject python3-dbus gtk4` |

The installer prints the command for the detected package manager if anything
is missing. For GNOME outside Ubuntu, the tray may also need
`gnome-shell-extension-appindicator`.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/raybird/sys-monitor/main/install.sh | bash
```

The installer downloads the latest release, installs below `$HOME`, and never
needs root. To pass options through the pipe:

```bash
curl -fsSL https://raw.githubusercontent.com/raybird/sys-monitor/main/install.sh |
  bash -s -- --compose-project runtelenexus
```

From a checkout it behaves the same and installs the working tree:

```bash
git clone https://github.com/raybird/sys-monitor.git
cd sys-monitor
./install.sh
```

The installer is safe to rerun. It updates program files and units without
removing existing history.

### Options

| Option | Purpose |
| --- | --- |
| `--compose-project NAME` | Deep-monitor one Docker Compose project |
| `--python PATH` | Use a specific interpreter instead of probing |
| `--ref REF` | Install a given tag, branch, or commit |
| `--repo OWNER/NAME` | Install from a fork |
| `--source DIR` | Install from an extracted source tree |
| `--no-start` | Install files without enabling services |
| `--print-python` | Print the resolved interpreter and exit |

Each option also has a `FREEZE_WATCH_`-prefixed environment variable, which is
easier to use through a pipe:

```bash
curl -fsSL https://raw.githubusercontent.com/raybird/sys-monitor/main/install.sh |
  FREEZE_WATCH_REF=v0.2.0 bash
```

### Python interpreter

Freeze Watch needs the GTK 4 and dbus bindings that ship with the distribution
interpreter. Version managers such as pyenv, asdf, and conda, and activated
virtualenvs, normally lack them even when they own `python3` on `PATH`, so the
installer probes candidates, records the one that works in
`~/.config/freeze-watch/env`, and the dashboard reads it from there. Override
the choice with `--python /path/to/python3`.

## Use

The collector and retention timer start immediately. The dashboard starts in
the active graphical session and returns automatically on the next login,
including in sessions that never activate `graphical-session.target`, where an
XDG autostart entry starts it instead.

```bash
freeze-watch
systemctl --user status freeze-monitor.service
systemctl --user status freeze-watch.service
```

Click the tray item to open the dashboard. Closing the window hides it while
the tray process remains active. The dashboard is also available as
**Freeze Watch** in the desktop application launcher.

When the collector has recorded a freeze or a stall, a selector appears at the
top of the dashboard. Choosing an entry replaces the live readings with the
half hour that led up to it, so the temperatures, pressure, load, and running
containers shown are the ones recorded at the time. The tray keeps reporting
the machine as it is now. Select **即時監測** to return.

Configuration is stored in:

```text
~/.config/freeze-watch/env
```

Collected data is stored in:

```text
~/.local/state/freeze-monitor/
```

## GPU 程序紀錄與診斷匯出

截至 2026-10-05，GPU 程序紀錄預設關閉。需要時在
`~/.config/freeze-watch/env` 設定 `FREEZE_WATCH_GPU_PROCESSES=1`，再執行
`systemctl --user restart freeze-monitor.service`；安裝器升級會保留此設定。
此功能讀取 Linux DRM fdinfo（例如 AMD／Intel），其他驅動或無權限時明確
顯示資料不完整或計數器不支援。持有裝置不等於正在使用 GPU，首次採樣活動未知。
截至 2026-11-04，只檢查本人的程序，受保護的程序（例如瀏覽器沙箱）另列數量；
啟用後 metrics 檔每日約增加 5 MB（實機 34 個 GPU client）。

截至 2026-10-05，選取事件後可按「預覽診斷報告」，確認內容後再匯出文字檔。
報告涵蓋事件前 30 分鐘／後 5 分鐘，省略路徑、程序名稱與參數，核心訊息僅列
錯誤分類；缺資料會明示。缺少正常停止紀錄僅代表非正常關機／疑似當機，不能
單憑此條件確認硬體或 GPU 故障。

最後驗證日期：2026-11-12（GPU 程序紀錄與資料狀態）。

## Uninstall

The installer leaves a copy of the uninstaller behind, so no checkout or
network access is needed:

```bash
~/.local/share/freeze-watch/uninstall.sh
```

Add `--purge-data` to also delete configuration and collected history. The
uninstaller is self-contained and can equally be run from a checkout or piped:

```bash
curl -fsSL https://raw.githubusercontent.com/raybird/sys-monitor/main/uninstall.sh | bash
```

## Development

```bash
./scripts/check.sh
```

The check suite validates Bash and Python syntax, unit tests, systemd units,
ShellCheck when available, and a full install/uninstall inside an isolated
temporary HOME.

To publish a release, update `VERSION` and `CHANGELOG.md`, then push a matching
tag. CI verifies that the tag, `VERSION`, and the changelog agree, runs the
checks, and publishes the archive and its checksum.

```bash
git tag v0.2.0
git push origin v0.2.0
```

See [architecture](docs/architecture.md) and
[troubleshooting](docs/troubleshooting.md).

## Security

Freeze Watch runs entirely as the logged-in user. Docker access is never
configured by the installer. Be aware that membership in the Docker group is
effectively root-equivalent.

## License

MIT

## Container evidence

To inspect both projects without changing their containers:

```bash
./install.sh --compose-project runwukong,runtelenexus
```

The existing single-project option still works. Expand a container in the
dashboard to see raw block I/O byte counters and rates, OOM/restarts/health,
and up to 15 CPU, memory, or D-state processes. Selected projects retain exited
containers and their OOM/restart state; stopped CPU/I/O values are unknown. Select a saved timestamp to
compare that sample with host temperature and PSI; incident review reads the
same saved evidence after a reboot. Expanded rows and timestamp choices survive
live refreshes. Unknown and stale samples are labelled rather than treated as
healthy; rows without a complete live sample are shown in italic lilac, and an
unavailable Docker states why (socket permission, missing socket, timeout and
so on). Incident review locates the 2 MB of container records that end at the
incident, so an incident early in a day's file still finds them. Only tracked projects raise warnings: OOM, unhealthy healthcheck,
zombies, a restart since the previous sample, or at least 4 D-state processes
(8 for event log entries, matching the host thresholds). An old restart count
alone is not a warning. The top 5 CPU processes are ranked by their CPU between
two deep samples, read from the host's `/proc` (100% is one core), so a
long-lived process that just spiked ranks first; the ps lifetime average is
shown alongside; a process younger than one second shows an unknown interval.
A container's first deep sample, or one with more than 1024 processes, a
`/proc` read over 0.2 s, an unreadable `/proc` or plain ASCII process names in
`/proc` that differ from Docker top's (as with Docker running in a VM), falls back to
the lifetime ranking and says why. These are diagnostic clues, not proof of a
freeze.

Each container row takes roughly 0.4 KB: eight containers every 30 seconds add
about 10 MB a day before compression, about 130 MB over the 14 raw days.

The collector queries a local Docker Unix socket through the selected Docker
context (or `DOCKER_HOST`). TCP/SSH daemons are reported unavailable: host PID
and RAM attribution would otherwise refer to a different machine. No new
permissions, container agent, `docker exec`, or container changes are required.
Existing access to the daemon is still necessary. Cached file reads may not
appear as block I/O, and kernels without accounting produce unknown counters.
See [architecture](docs/architecture.md#container-samples) for limits and units.
