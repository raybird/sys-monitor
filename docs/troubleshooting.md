# Troubleshooting

## The installer reports missing GTK dependencies

The bindings are distribution packages, so an interpreter from pyenv, asdf,
conda, or an activated virtualenv usually cannot see them even when the
packages are installed. Compare the two:

```bash
python3 -c 'import dbus, gi'
/usr/bin/python3 -c 'import dbus, gi'
```

If only the second succeeds, the installer will normally pick it on its own.
Ask it which interpreter it resolved, or name one explicitly:

```bash
./install.sh --print-python
./install.sh --python /usr/bin/python3
```

The answer is recorded as `FREEZE_WATCH_PYTHON` in
`~/.config/freeze-watch/env`, and both the systemd units and the `freeze-watch`
launcher read it from there. Editing that line is enough to move an existing
installation to a different interpreter.

## The tray icon is missing

Confirm the service is running:

```bash
systemctl --user status freeze-watch.service
journalctl --user-unit=freeze-watch.service -n 100 --no-pager
```

GNOME requires a StatusNotifier/AppIndicator extension. Ubuntu enables one by
default. On other GNOME installations, install and enable
`gnome-shell-extension-appindicator`.

## The dashboard has no temperature values

Check available hardware-monitor devices:

```bash
for device in /sys/class/hwmon/hwmon*; do
  printf '%s: ' "$device"
  cat "$device/name"
done
```

Freeze Watch currently recognises `k10temp`, `amdgpu`, and `nvme`. Unsupported
hardware still receives load, memory, pressure, filesystem, and Docker data.

## Docker shows unavailable

Docker is optional. If installed, the current user must be allowed to query it:

```bash
docker ps
```

Do not add a user to the Docker group without understanding that it grants
root-equivalent control of the host.

## Logs

```bash
journalctl --user-unit=freeze-monitor.service -n 100 --no-pager
journalctl --user-unit=freeze-watch.service -n 100 --no-pager
tail -50 ~/.local/state/freeze-monitor/events.log
```
