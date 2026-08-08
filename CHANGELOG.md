# Changelog

## 0.2.3 - 2026-08-08

- Restart running units when reinstalling. `enable --now` does nothing to a
  unit that is already active, so an upgrade kept executing the previous
  program until the next reboot.
- Restart the tray when it is already running even if
  `graphical-session.target` is inactive, which is the state Chrome Remote
  Desktop and similar sessions leave it in.

## 0.2.2 - 2026-08-08

- Apply the widened temperature-sensor list to the dashboard as well. It kept
  its own copy that still named only `k10temp` and `amdgpu`, so 0.2.1 fixed the
  recorded data while the tray label stayed `CPU —` on Intel and ARM machines.
- Fall back to the collector's recorded temperature per reading instead of only
  when every direct sensor read fails. One readable sensor, typically `nvme`,
  used to suppress the recorded values for every other field.
- Test that the two sensor lists stay identical, so the pair cannot drift apart
  again.

## 0.2.1 - 2026-08-08

- Read the CPU temperature from `coretemp`, `zenpower`, `k8temp`, or
  `cpu_thermal` when `k10temp` is absent, and the GPU temperature from `radeon`
  or `nouveau` when `amdgpu` is absent. Intel and ARM machines previously
  recorded `NA` for every sample, which left the tray label empty.
- Match temperature sources in preference order rather than in hwmon numbering
  order.
- Start the tray from an XDG autostart entry in sessions that never activate
  `graphical-session.target`, such as Chrome Remote Desktop and several
  lightweight session managers.

## 0.2.0 - 2026-08-08

- Install without cloning: the installer downloads its own source when run
  from a pipe, and accepts `--ref`, `--repo`, and `--source`.
- Probe for a Python interpreter that actually provides the GTK 4 and dbus
  bindings instead of trusting `python3` on `PATH`, so pyenv, asdf, conda, and
  virtualenv shims no longer break installation or the dashboard. The result is
  recorded as `FREEZE_WATCH_PYTHON` and can be overridden with `--python`.
- Print dependency instructions for apt, dnf, pacman, zypper, apk, and xbps
  rather than Ubuntu and Fedora only.
- Preserve the configured Compose project when reinstalling without
  `--compose-project`.
- Leave a copy of the uninstaller in `~/.local/share/freeze-watch` so removal
  needs neither a checkout nor network access.
- Publish tagged releases with an archive and a SHA-256 checksum.
- Verify systemd units against the isolated test home, where the installed
  programs the units reference actually exist.

## 0.1.1 - 2026-08-08

- Add a dedicated Freeze Watch launcher icon and compact symbolic tray icons.
- Use a distinct warning tray icon when hardware enters a hot or danger state.

## 0.1.0 - 2026-08-08

- Initial public repository.
- Persistent temperature, pressure, memory, disk, and process collection.
- Docker and optional Compose-project process diagnostics.
- GTK4 dashboard and live temperature StatusNotifierItem.
- Daily rotation with 14-day compression and 90-day expiration.
- User-level installer, uninstaller, tests, and CI.
