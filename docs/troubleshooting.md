# Troubleshooting

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
