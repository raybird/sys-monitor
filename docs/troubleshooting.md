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

The CPU temperature comes from the first of `k10temp`, `coretemp`, `zenpower`,
`k8temp`, or `cpu_thermal` that is present, the GPU temperature from `amdgpu`,
`radeon`, or `nouveau`, and the drive temperature from `nvme`. A generic
`acpitz` device is deliberately ignored, because it usually reports a board or
ambient sensor and a wrong CPU temperature is worse than none when the log is
read back to explain a freeze.

Integrated Intel graphics report neither a hwmon temperature nor
`gpu_busy_percent`, so `gpu_temp_mC` and `gpu_busy_pct` stay `NA` on those
machines. The CPU package sensor covers the same silicon. Unsupported hardware
still receives load, memory, pressure, filesystem, and Docker data.

## The tray icon never appears after logging in

Some sessions never activate `graphical-session.target`, which is what would
normally pull in the tray service. Chrome Remote Desktop and several
lightweight session managers start the desktop outside the systemd user
hierarchy. Check with:

```bash
systemctl --user is-active graphical-session.target
```

If that prints `inactive`, the XDG autostart entry installed at
`~/.config/autostart/com.raybird.FreezeWatch-autostart.desktop` takes over at
the next login. To start the tray in the current session without logging out:

```bash
systemctl --user start freeze-watch.service
```

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
