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

Configuration is stored in:

```text
~/.config/freeze-watch/env
```

Collected data is stored in:

```text
~/.local/state/freeze-monitor/
```

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
