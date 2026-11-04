# Architecture

Freeze Watch has three deliberately small processes:

1. `freeze-monitor` samples Linux metrics every 10 seconds and Docker details
   every third sample.
2. `freeze-monitor-maintain` compresses raw TSV logs after 14 days and removes
   compressed archives after 90 days.
3. `freeze_watch.py` is the GTK4 dashboard and StatusNotifierItem tray process.

The GUI reads the collector's append-only TSV files. It does not repeatedly call
Docker itself, so opening the dashboard does not add container-engine load.

It reads them twice over. Live, it shows the newest file. In review, it shows
the window before a chosen incident: a freeze names the file it was cut off
from, a stall is matched to the file whose samples span it, and the container
sample beside either is one substitution away, since both files are named from
the same stamp. The tray is left on live readings throughout, because a review
is something the reader asked for and the indicator is not.

## Data flow

```text
/proc + /sys + Docker
        |
        v
  freeze-monitor
        |
        +-- metrics-*.tsv
        +-- docker-*.tsv
        +-- events.log
                |
                v
       GTK4 dashboard + tray
```

All files live below `${XDG_STATE_HOME:-~/.local/state}/freeze-monitor`.
No daemon runs as root.

## Incidents

The collector is read after the fact, so it has to say where an incident was.

截至 2026-10-05，每個 session 以 `START`／`STOP` 區分正常停止。缺少
`STOP` 且 boot id 改變時記為 `UNCLEAN`：只能確認非正常關機，無法區分
斷電、強制重啟或當機；同 boot 則記為 `INTERRUPTED`。歷史 `FREEZE`
仍可回顧，但 UI 一律保留「疑似當機、原因未確認」的措辭。

截至 2026-10-05，前次 session 的取樣定位追蹤 `START` 後的所有 `ROTATE`，
從最新有效取樣檔向前回退，不借用其他 session 的資料。回顧以 `last_sample`
為窗口終點，涵蓋同 session 的輪替檔；沒有有效取樣時明示缺資料。

`GAP` records a sample that arrived later than three intervals. It answers a
question the metrics cannot: if samples kept arriving through a reported
freeze, the kernel was scheduling this loop and the desktop is what stopped
responding.

Samples are buffered and flushed every third one, except while any reading is
elevated, when each sample is written through. The thresholds for that sit
below the ones that raise a warning, so the evidence is already durable before
anything is worth warning about. `FLUSH` marks each transition.

## Kernel evidence

Metrics describe load; they do not say that the GPU driver reset or that a task
blocked for two minutes. `KERNEL` events carry those lines, matched against a
list confined to what explains a machine that stopped responding: hung tasks,
RCU stalls, DRM and GPU hangs, NVMe and ATA timeouts, machine checks, OOM
kills, thermal throttling, and filesystem I/O errors.

Reading goes through `journalctl` rather than `/dev/kmsg`, because it honours
group membership and can reach the boot before this one. Each scan resumes from
a cursor, so no line is reported twice, and output is capped per scan: one
failing device can emit thousands of near-identical lines, and a log that
scrolls past the freeze is no better than no log. A match also switches the
collector to write-through.

The previous boot is read only when the machine went down without shutting
down, which is the one time those lines are worth replaying.

Users outside the `adm` and `systemd-journal` groups cannot read the kernel
log. The collector says so once at startup and carries on. `/sys/fs/pstore`,
where a panic leaves its remnants, is root-only on every distribution checked,
so it is not consulted.

## Signals

Linux pressure accounting reports two figures per resource. `some` counts time
where at least one task was stalled; `full` counts time where every task was,
which is what a freeze is from the kernel's point of view. Both are recorded,
and `full` carries the lower alerting threshold of the two.

Processes in uninterruptible sleep are counted for the same reason. That state
is where a task waits on a device, so a pile-up points at storage rather than
at the CPU, and it raises the load average without consuming any CPU at all.

Several readings are cumulative counters that only mean something as a rate,
so the sample carries the change since the previous one: swap pages in and
out, major faults, and the disk's busy milliseconds. The first sample of a
session has nothing to subtract from and records those as missing.

The CPU throttle count is kept as an absolute, because what matters is whether
it moved at all. A temperature says the part was hot; the counter says the
firmware responded by taking speed away. It is absent on hardware without
Intel's `thermal_throttle` interface, which reads as missing rather than zero.

Disk figures come from the whole device holding the root filesystem, resolved
once at startup by walking from the mounted partition to its parent in sysfs.
A root on LVM or device-mapper does not resolve that way and reads as missing.

NVMe error counters are deliberately absent: reading them needs root, and the
kernel log already carries the controller timeouts and resets that matter.

## GPU 程序紀錄與安全匯出

截至 2026-11-04，設定 `FREEZE_WATCH_GPU_PROCESSES=1` 可啟用 `freeze_gpu.py`。
資料附加於 metrics TSV 最後的 `gpu_processes` JSON 欄位，預設為 `disabled`。
每列 JSON 只記有活動或活動未知的 client：`engines` 的數字是引擎占比，字串是
未量到的原因（`baseline`、`counter_regressed`）；取樣期間無活動的持有者只以名稱
列在 `idle`（已列為有活動的程式不重複列出）。沒有 client id 或引擎計數器的持有者
（例如 NVIDIA 專有驅動）依驅動以名稱列在 `unsupported`，不冒充零活動。
實機（Intel，34 個 client）每列約 0.6 KB，每日約 5 MB。
採樣讀 `/proc/PID/fd` 與 fdinfo；僅讀 comm，不讀 cmdline。依裝置與
DRM client-id 去重，使用程序啟動身份辨識 PID 重用；累積引擎 ns 轉為差值，
首次／缺計數器／計數器回退時不冒充零活動，並依引擎 capacity 換算占比。
契約依 [Linux 核心文件](https://docs.kernel.org/gpu/drm-usage-stats.html)。

截至 2026-11-04，只掃描本人的程序，PID 新的先掃，讓上限不會遮住剛啟動的程式。
成本由掃描預算 100 ms 與外層逾時 1 秒限制；512 個程序、每程序 1024 個 fd、
總計 16384 個 fd、64 個 client、每 client 4 個持有者與 8 個引擎的上限只限制
記憶體與輸出量。本人但設為不可傾印的程序（瀏覽器沙箱等）記為 `protected`，
不算採樣失敗；在讀到 fd 清單前就結束的程序直接略過，已確認持有 GPU 卻讀不到
fdinfo 時才記為 unavailable。截斷或其他讀取失敗才記 truncated／partial；
無權限或不支援的驅動不影響基本監測。
私有 gpu-counters.json 保存差值基線，收集器重新啟動時重設 session 身份。

截至 2026-10-05，診斷報告為事件前 30 分鐘／後 5 分鐘的純文字預覽，
儲存使用與預覽相同的固定文本，權限 0600。數值以允許欄位輸出，省略檔案路徑、
程序名稱與參數；核心訊息僅保留錯誤分類，原始內容仍留於本機 events.log。
非正常關機的前次核心證據可能由新 session 讀回，報告標示其讀回時間。

截至 2026-11-04，儀表板讀 TSV 尾端時丟掉被截斷的第一行，即時熱度帶依列數讀滿
30 分鐘（180 列），不受每列寬度影響；檔案中的無效位元組以替換字元讀取。

最後驗證日期：2026-11-04（GPU 程序紀錄、尾端讀取與報告窗口）。

## Compatibility

The first private deployment used `runtelenexus_*` field names. The public
schema uses `tracked_*` names at the same column positions, so the dashboard
can continue reading earlier files.

New columns are appended, never inserted, for the same reason. A file written
by an older collector simply stops short of the newest columns, and the
dashboard reads the absent ones as missing data.
