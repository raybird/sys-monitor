# 驗證證據

核准與範圍以 [README.md](README.md) 為準。日期一律為 2026-11-06。

## 紅燈

- 命令（在 tests/ 下）：`python3 -m unittest test_container_probe.ProcessCpuIntervalTests test_container_probe.CounterTests test_freeze_watch.ProcessCpuIntervalDetailTests`
- 結果：exit 1，5 個 failure、8 個 error（[artifacts/red.log](artifacts/red.log)）。
  - helper 端 7 個新測試都是 `AttributeError: ... does not have the attribute 'PROC_ROOT'`，功能還不存在。
  - 既有的 `test_bounded_processes_preserve_dstate_and_never_argv` 出現 `not enough values to unpack (expected 5, got 4)`，因為測試已改成新的回傳值。
  - 儀表板 3 個新測試失敗：沒有「CPU 區間」，也沒有排序說明。
- 紅燈 log 裡有一個是測試本身寫錯：`test_scn005_old_rows_keep_the_old_wording` 斷言沒有「區間」，但容器 CPU 那一行原本就有「區間使用率」。改成斷言沒有「CPU 區間」。
- 實作過程中又修了兩個測試寫錯的地方，都不是實作的問題：
  - SCN-001 的程序列期望值照 Gherkin 預覽寫成 `）· RAM`，實作沿用既有的 ` · ` 分隔，改測試。
  - `assertNotIn('ps 生命週期平均；')` 和區間模式的說明「括號內為 ps 生命週期平均；」衝突。這個斷言要確認的是舊說明沒有出現，改成斷言沒有「程序 CPU 為 ps 生命週期平均」。

## 被修改的既有測試

- `CounterTests.test_bounded_processes_preserve_dstate_and_never_argv`：
  - `process_sample` 多回傳一個 snapshot，解包改成 5 個值。
  - 程序的欄位集合加上 `cpu_interval`、`cpu_fallback`。
  - 這兩處都是 SCN-001 核准的行為變更，其餘斷言不變。

## 綠燈與完整檢查

- `env -u DISPLAY -u WAYLAND_DISPLAY bash scripts/check.sh`：exit 0，Ran 139 tests，OK，沒有跳過，All checks passed（[artifacts/check.log](artifacts/check.log)）。
- 139 = 129 + 10 個新測試（helper 7 個、儀表板 3 個）。

## 突變驗證

在 scratchpad 的複本各做一種突變，在各自的 tests/ 下執行 `python3 -m unittest -v test_container_probe.ProcessCpuIntervalTests`；未修改的版本全過。

| 突變（`src/container_probe.py`） | 失敗的測試 | log |
|---|---|---|
| 拿掉 starttime 比對 `old[0] == start and` | PID 重用 | [mutation-nostart.log](artifacts/mutation-nostart.log) |
| 時間分母多加 1 秒 | 4 個，包括 SCN-001、SCN-005 | [mutation-denominator.log](artifacts/mutation-denominator.log) |
| 排序改回生命週期平均 | SCN-001 會飆高的長壽程序 | [mutation-rank.log](artifacts/mutation-rank.log) |

第一次做 starttime 突變之前，我先把 PID 重用測試裡舊程序的 tick 從 1000 改成 100。原本舊 tick 比新的大，就算拿掉 starttime 比對，也會因為「tick 不能倒退」碰巧得到同樣的結果，測試抓不到。

## 真實對照組（主機，TBD-2）

- 腳本：[artifacts/host_control.py](artifacts/host_control.py)。在主機上啟動自己的程序，先閒置 10 秒，再忙迴圈 15 秒。用 `ps -o pid,stat,pcpu,pmem,comm` 的輸出當作 Docker top 的資料，走完整的 `process_sample`，讀真實的 `/proc`。
- 命令：`python3 -I host_control.py <repo>`。
- 結果（[artifacts/host-control.txt](artifacts/host-control.txt)）：
  - 第 12 秒第一次採樣：`cpu_interval` 為 null，`cpu_fallback` 為 `no_previous`，ps 平均 16.7%。
  - 第 17 秒第二次採樣：`cpu_interval` 為 **100.0**，ps 平均 41.3%，約等於忙 7 秒除以活了 17 秒。
  - 結論：tick 換算（`SC_CLK_TCK`=100）與時間分母在真實環境下正確，生命週期平均確實會低估剛飆高的程序。
- 限制：主機對照組沒有經過 Docker top。這段由假 `/proc` 的單元測試，加上下面的真實唯讀採樣涵蓋。

## 真實 Docker 唯讀採樣

- 命令：`/usr/bin/python3 -I src/container_probe.py now <epoch> runwukong,runtelenexus <scratchpad 暫存目錄>`，跑兩輪，間隔約 10 秒。
- 結果（[artifacts/real-docker-summary.txt](artifacts/real-docker-summary.txt)，repo 公開，只保存摘要）：
  - 兩輪都是 exit 0、state ok，各約 0.1 秒。
  - 第一輪追蹤容器的 15 個程序都標示 `no_previous`，第二輪 15 個都有區間值。
  - cache 保存 6 個執行中追蹤容器的 15 個程序。

## 驗收對照

| Scenario | 證據 | 判定 |
|---|---|---|
| SCN-001 | `test_scn001_spiking_long_lived_process_ranks_first_by_interval`、`test_scn001_interval_and_lifetime_are_both_shown`、突變（排序、分母）、主機對照組 | 通過 |
| SCN-002 | `test_scn002_without_previous_ranks_by_lifetime_and_says_why`、時鐘沒前進的測試、儀表板退回標示、真實採樣第一輪 | 通過 |
| SCN-003 | `test_scn003_pid_reuse_new_and_exited_processes`、程序在讀取前結束的測試、starttime 突變 | 通過 |
| SCN-004 | `test_scn004_over_count_over_time_or_unreadable_falls_back_for_the_whole_container`、儀表板退回標示；helper 既有的預算與硬上限測試仍通過 | 通過 |
| SCN-005 | `test_scn005_collect_keeps_readings_of_live_deep_processes_only`、`test_scn005_old_rows_keep_the_old_wording`；既有的 TSV 欄位測試仍通過 | 通過 |

## 其他

- 精煉：新增的函式只有 `boot_seconds`、`read_proc_times`、`interval_cpu`。`boot_seconds` 是為了讓測試能固定時間；沒有新增設定項。no-op。
- 影響分析：GitNexus 沒有登錄本 repo。用 grep 確認 `process_sample` 只在 `collect` 和測試中呼叫；`container_detail` 只在儀表板與測試中使用；`process_status` 的值沒有改變。
