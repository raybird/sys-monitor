# Changelog

## 0.5.0 - 2026-08-09

- Review a past incident from the dashboard. A selector lists recorded freezes
  and stalls, and choosing one shows the thirty minutes leading up to it:
  temperatures, pressure, load, and the containers as they were recorded, not
  as they are now. The ribbon is titled with the moment it ends at.
- Put the incident summary above the live readings. The dashboard is opened
  after something went wrong far more often than to watch a healthy machine,
  and that panel used to be below the fold.
- Mark stalls on the thermal ribbon, derived from the sample intervals
  themselves, so a hesitation is visible in both live and review views.
- Wrap event messages instead of truncating them. The end of a freeze entry
  carries the last sample and the file it was cut off from, which was exactly
  the part being cut off.
- Keep twelve events rather than six.
- Leave the tray on live readings during a review, because the indicator was
  not what the reader asked to change.

## 0.4.1 - 2026-08-09

- Match the kernel messages AMD and NVIDIA actually emit. Vendor spellings
  differ: AMD announces `GPU reset begin!` with no drm tag, Intel wraps errors
  in `[drm:function]` rather than a bare `[drm]`, and the NVIDIA blob reports
  an `Xid`. Only the Intel `GPU HANG` shape was recognised, which left the
  hardware this tool was written on the least well covered.
- Also match soft lockups, kernel panics, page-fault oopses, and general
  protection faults, which are among the most common causes of a machine that
  stops responding.
- Check the pattern against recorded message shapes in
  `tests/kernel-samples.tsv`, including boot chatter it must ignore, and check
  the AMD sensor path against a synthetic k10temp and amdgpu machine.

## 0.4.0 - 2026-08-09

- Record `KERNEL` events for the messages that explain a machine which stopped
  responding: hung tasks, RCU stalls, DRM and GPU hangs, NVMe and ATA timeouts,
  machine checks, OOM kills, thermal throttling, and filesystem I/O errors.
  Metrics describe load and never said that the GPU driver had reset.
- Read the previous boot's kernel log after an unclean shutdown, which is the
  one time those lines are worth replaying.
- Switch to write-through when a kernel message matches, on the assumption that
  more is about to go wrong.
- Say so once and carry on when the kernel log cannot be read, which is the
  normal case for a user outside the `adm` and `systemd-journal` groups.

## 0.3.0 - 2026-08-09

- Report how the previous session ended. A session that never wrote `STOP` was
  cut off: a new boot id records a `FREEZE` naming the last sample and how long
  the log had been silent, the same boot id records an `INTERRUPTED` because
  only the collector died while the machine kept running. Until now nothing in
  the logs said where an incident happened.
- Record a `GAP` when a sample arrives later than three intervals. Whether
  sampling continued through a reported freeze separates a stalled kernel from
  a desktop that stopped responding, which are different investigations.
- Write every sample straight to disk while conditions are elevated, well
  before anything is warning-worthy. Buffered writes could lose the last 30
  seconds before a power cut, which is the evidence the collector exists to
  keep. The switch is logged once per transition.
- Surface the new events in the dashboard ahead of routine entries.
- Stop reporting an I/O pressure warning on every sample on kernels built
  without pressure accounting. The reading is `NA` there, and awk compared it
  as a string, where `"NA"` sorts above `"20.0"`.

## 0.2.4 - 2026-08-09

- Stop the dashboard from opening wider than the screen. Event and container
  rows carry arbitrary strings, and a label that can neither wrap nor ellipsize
  reports its whole text width as its minimum, which the horizontal scroll
  policy passed straight to the window. A single event line naming an absolute
  path forced a 2624px window onto an 1854px screen.
- Clamp the initial window size to the monitor, leaving room for panels.
- Measure widget widths in the test suite, under Xvfb when headless, so the
  overflow cannot come back unnoticed.

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
