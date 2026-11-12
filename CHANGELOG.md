# Changelog

## 0.10.0 - 2026-11-12

- 事故回顧與即時畫面略過損壞或截斷的 TSV 資料列，保留最後有效樣本，
  並在受影響的事故時間範圍標示證據不完整；舊版完整短欄位仍可讀取。
- 即時主機樣本超過 60 秒未更新時顯示資料過期與最後採樣時間，
  恢復採樣後解除提示，歷史回顧不套用即時過期判準。
- 記錄 collector 版本與核心日誌掃描狀態，於事故畫面及安全診斷匯出
  區分 GPU 採樣停用、核心掃描成功但零命中、掃描失敗與舊紀錄未知。

限制：既有事故資料缺少版本與觀測狀態時維持未知；本次沒有變更 GPU
採樣開關或核心日誌存取權限，也無法據此判定過往非正常結束的原因。

## 0.9.0 - 2026-11-08

- 排除採樣用的 `ps` 自己，避免 CPU／記憶體前五名被監測程序佔據；
  其他真正高負載的 `ps` 仍會顯示。
- 同時深度觀測多個 Compose project，新增容器記憶體上限、health、
  block I/O bytes 與速率，以及 CPU／記憶體／D 狀態的前列程序。
- 容器程序改依兩次採樣間的 CPU 使用率排序，並保留生命週期平均值；
  缺少基準、無法讀取主機程序或超過採樣預算時，明示退回排序的原因。
- 保存容器歷史樣本，事故回顧可對照當時的主機溫度與記憶體／I/O 壓力；
  過期、缺口與未知資料會明確標示。
- 容器警示僅針對追蹤專案，重啟依新增次數判定；採樣失敗不清除有效基準，
  並補強跨失敗輪次與基準到期的回歸測試。
- 修正跨日輪替後的最後樣本定位與事故回顧，非正常關機保留原因未確認的語意；
  改善亮暗主題下的選單及異常列辨識。
- 新增預設關閉的 GPU 程序與引擎活動紀錄，以及可預覽的純文字診斷報告匯出；
  報告預設省略敏感路徑、程序名稱與參數。
- 發版測試環境補上 GTK cairo binding，與一般 CI 的依賴一致。

限制：GPU 程序紀錄取決於驅動與存取權限；追蹤超過 8 個執行容器時，
深度採樣輪替會減少可計算區間 CPU 的容器，達 16 個時全部退回生命週期平均。
真實高負載的容器採樣成本仍依 issue 2 的外部驗收窗觀察。

## 0.8.0 - 2026-10-23

- Colour the system pulse cards (`available memory`, `load`, `I/O pressure`, and
  `root filesystem`) by severity alongside the temperature cards, so a saturated
  disk, elevated PSI full pressure, uninterruptible sleep pile-up, or swap
  thrashing stands out immediately.
- Add hover inspection and time anchors to the 30-minute thermal ribbon, showing
  exact sample timestamps, sensor readings, and stall warnings under the cursor.
- Add explanatory tooltips for technical shorthand (`swap-in`, `D` state, PSI
  `full`, disk `in-flight`, and `Z` zombies) across metric cards and container
  rows.
- Render the top CPU and memory processes as side-by-side structured lists with
  explicit `CPU %` and `RAM %` figures instead of raw semicolon-separated text.
- Highlight active incident reviews with a dedicated banner style, human-readable
  incident summaries, event-severity colours, and a one-click button to return
  to live monitoring.
- Style the incident dropdown popover in dark mode so GTK themes do not render
  light text on a white popover background.

## 0.7.1 - 2026-08-09

- Stop the dashboard dragging the view back up the page. Emptying a list to
  refill it shrinks the scrolled content, which clamps the scroll position, and
  refilling does not put it back, so every two-second refresh walked the page
  upwards for anyone who had scrolled down. Lists are now rebuilt only when
  their contents actually changed, and the position is restored once the new
  contents have been laid out.

## 0.7.0 - 2026-08-09

- Record the CPU throttle count. A temperature says the part was hot; this says
  the firmware took speed away, which is what the machine actually feels. Any
  increase raises a warning, because throttling is not a threshold to cross.
- Record swap traffic and major faults as the change since the previous sample.
  A swap total says how much was ever paged out; the rate says whether the
  machine is thrashing right now.
- Record the queue depth and busy time of the disk holding the root filesystem.
  A device saturated for whole seconds at a time looks exactly like a freeze.
- Rank processes by memory as well as by CPU. The process that exhausted the
  machine is rarely the one burning CPU at the moment it gives up.
- Show all of it in the dashboard: throttling beside the temperature that
  caused it, swap-in beside the memory figure, disk queue and busy share beside
  the filesystem.

NVMe error counters are not included. They need root, and the kernel log
already carries the controller timeouts that matter.

## 0.6.0 - 2026-08-09

- Record the `full` pressure figures alongside `some`. "Some" means at least
  one task was stalled; "full" means every task was, which is what a freeze
  is, and only the weaker of the two was being kept.
- Count processes in uninterruptible sleep. A pile-up is the signature of a
  machine stopped on storage rather than on the CPU, and it explains a load
  average that climbs while nothing uses any CPU. The dashboard shows the
  count beside the load average for that reason.
- Warn on sustained full pressure or a pile-up of uninterruptible sleepers,
  and treat either as grounds for writing every sample through.
- Read files written before these columns existed as missing data rather than
  as the literal text `None`. Columns are appended, never inserted.

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
