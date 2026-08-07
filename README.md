# Freeze Watch

A lightweight Linux freeze-diagnostics collector with a native GTK4 dashboard,
Docker process monitoring, and a live CPU-temperature tray label.

Freeze Watch was built to investigate hard desktop freezes where keyboard and
mouse input stop responding. It keeps low-overhead, disk-backed evidence across
the period immediately before a forced reboot.

## Features

- CPU, GPU, and NVMe temperatures
- load averages, memory, swap, filesystem usage, and Linux PSI pressure
- GPU busy percentage and top CPU processes
- Docker CPU, memory, task counts, OOM state, restarts, and zombie detection
- optional deep monitoring of one Docker Compose project
- live `CPU 58°` StatusNotifier/AppIndicator label
- dedicated full-colour launcher icon and symbolic tray icons
- GTK4 dashboard with a 30-minute thermal ribbon
- daily log rotation, compression after 14 days, expiration after 90 days
- user-level systemd services; no root daemon

## Requirements

- Linux with systemd user services
- Python 3, PyGObject/GTK4, and dbus-python
- Bash and standard GNU/Linux utilities
- Docker is optional
- a StatusNotifier/AppIndicator host for the tray item

Ubuntu 24.04:

```bash
sudo apt install python3 python3-gi python3-dbus gir1.2-gtk-4.0
```

For GNOME outside Ubuntu, the tray may also need:

```bash
sudo apt install gnome-shell-extension-appindicator
```

## Install

```bash
git clone https://github.com/raybird/sys-monitor.git
cd sys-monitor
./install.sh
```

To deep-monitor a Compose project:

```bash
./install.sh --compose-project runtelenexus
```

The installer is safe to rerun. It updates program files and units without
removing existing history.

## Use

The collector and retention timer start immediately. The dashboard starts in
the active graphical session and returns automatically on the next login.

```bash
freeze-watch
systemctl --user status freeze-monitor.service
systemctl --user status freeze-watch.service
```

Click the tray item to open the dashboard. Closing the window hides it while
the tray process remains active. The dashboard is also available as
**Freeze Watch** in the desktop application launcher.

Configuration is stored in:

```text
~/.config/freeze-watch/env
```

Collected data is stored in:

```text
~/.local/state/freeze-monitor/
```

## Uninstall

Preserve configuration and collected history:

```bash
./uninstall.sh
```

Also delete configuration and history:

```bash
./uninstall.sh --purge-data
```

## Development

```bash
./scripts/check.sh
```

The check suite validates Bash and Python syntax, unit tests, systemd units,
ShellCheck when available, and a full install/uninstall inside an isolated
temporary HOME.

See [architecture](docs/architecture.md) and
[troubleshooting](docs/troubleshooting.md).

## Security

Freeze Watch runs entirely as the logged-in user. Docker access is never
configured by the installer. Be aware that membership in the Docker group is
effectively root-equivalent.

## License

MIT
