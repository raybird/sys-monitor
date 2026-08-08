# Changelog

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
