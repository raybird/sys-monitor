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

- 首次交付（02eda4b）：`env -u DISPLAY -u WAYLAND_DISPLAY bash scripts/check.sh`，exit 0，Ran 139 tests，OK，沒有跳過。139 = 129 + 10 個新測試（helper 7 個、儀表板 3 個）。
- 第一輪審查修正後（ef3c759）：同一命令 exit 0，Ran 147 tests，OK，沒有跳過。147 = 139 + 8 個新測試（helper 7 個、儀表板 1 個），見下方「審查修正」。
- 第二輪審查修正後：同一命令 exit 0，Ran 149 tests，OK，沒有跳過，All checks passed（[artifacts/check.log](artifacts/check.log)）。149 = 147 + 2 個新測試，見下方「第二輪審查修正」。

## 突變驗證

在 scratchpad 的複本各做一種突變，在各自的 tests/ 下執行 `python3 -m unittest -v test_container_probe.ProcessCpuIntervalTests`；未修改的版本全過。

| 突變（`src/container_probe.py`） | 失敗的測試 | log |
|---|---|---|
| 拿掉 starttime 比對 `old[0] == start and` | PID 重用 | [mutation-nostart.log](artifacts/mutation-nostart.log) |
| 時間分母多加 1 秒 | 4 個，包括 SCN-001、SCN-005 | [mutation-denominator.log](artifacts/mutation-denominator.log) |
| 排序改回生命週期平均 | SCN-001 會飆高的長壽程序 | [mutation-rank.log](artifacts/mutation-rank.log) |

第一次做 starttime 突變之前，我先把 PID 重用測試裡舊程序的 tick 從 1000 改成 100。原本舊 tick 比新的大，就算拿掉 starttime 比對，也會因為「tick 不能倒退」碰巧得到同樣的結果，測試抓不到。

## 審查修正（review-02eda4b）

[review-02eda4b.md](review-02eda4b.md) 判定 RETURN。2026-11-06 使用者決定 S3 比對程序名稱、N2 新程序存活不到 1 秒記為未知（SCN-003、SCN-004 修訂後重新核准），並要求一併處理 N1、N3、N4、N5。

| 發現 | 修正 | 紅燈 |
|---|---|---|
| M1 退回模式的排序是假綠燈 | SCN-002 與 SCN-004 測試改成低生命週期平均的程序排在前面輸入，只有依生命週期平均排序才會讓 10 排第一 | 不改程式；以突變驗證，見下表 `lifetimekey` |
| S1 `cpu_fallback` 不是字串時儀表板拋 TypeError | 只取字串的 `cpu_fallback` | `test_damaged_fallback_value_does_not_break_the_detail`：list、dict 兩個 subTest 拋 `TypeError: cannot use 'list' as a dict key`（[artifacts/red-review-s1.log](artifacts/red-review-s1.log)） |
| S2 輪替限制描述不正確 | architecture.md 與 TBD-3 改為「每輪 8 個裡只有 max(0, 16−N) 個有區間值，16 個以上全都沒有」 | 文件；數字取自 reviewer 實測 |
| S3 PID namespace 沒有交叉核對 | `/proc/<pid>/stat` 括號內的 comm 不是 Docker top 名稱的前綴時，整個容器記為 `proc_unreadable` | `test_scn004_name_mismatch_means_another_pid_namespace`：`KeyError: 'cpu_fallback'`（[artifacts/red-review-fix.log](artifacts/red-review-fix.log)，下同） |
| N1 PID 防護與 1024 邊界 | PID 須是 ASCII 數字 | `test_pid_must_be_ascii_digits_and_1024_is_within_budget`：阿拉伯數字 PID `KeyError` |
| N2 短命新程序顯示 100% | 新程序存活至少 1 秒才計算，否則記為未知 | `test_scn003_new_process_needs_one_second_of_life`：`{'40': 100.0, …} != {'40': None, …}` |
| N3 同分時依 Docker top 輸出順序 | 排序鍵加上生命週期平均；退回時區間值全部未知，同一個鍵即依生命週期平均排序，所以拿掉了退回模式另外的排序分支 | `test_equal_interval_ranks_by_lifetime_average`：`['10', '20', '30', '40'] != ['20', '10', '40', '30']` |
| N4 cache 損壞讓整個容器變成查詢失敗 | 舊 tick 不是整數時只讓該程序未知；`at` 不是有限數時退回 `no_previous` | `test_damaged_cache_only_loses_the_damaged_entries`：`TypeError: '>=' not supported` |
| N5 邊界沒有測試 | 補「剛好在上次讀取時啟動」與「tick 倒退」的測試 | 守衛原本就在，是刻畫測試；以突變驗證 |

其他已綠的新測試：`test_kernel_comm_is_a_prefix_of_the_top_name`（名稱比對不會誤判 15 字元截斷與 ` <defunct>`）、`test_ticks_going_backwards_are_unknown`。既有測試的假 `/proc` 程序名稱原本與 Docker top 的名稱不同，加上名稱比對後會全部退回，所以 `stat()` 改為必須傳入名稱，並讓每個測試兩邊的名稱一致；期望值沒有改變。

修正後重跑全部突變，包括首次交付的三個（[artifacts/mutations-review-fix.txt](artifacts/mutations-review-fix.txt)）。執行 `test_container_probe.ProcessCpuIntervalTests`、`CounterTests` 與 `test_freeze_watch.ProcessCpuIntervalDetailTests`，未修改的版本全過，13 個突變都有測試失敗：

| 突變 | 失敗的測試 |
|---|---|
| `nostart` 拿掉 starttime 比對 | PID 重用 |
| `denominator` 時間分母多 1 秒 | 6 個 |
| `rank` 排序改回只看生命週期平均 | SCN-001、同分 |
| `lifetimekey` 第二排序鍵改成常數（M1 的退回排序） | SCN-002 三個 subTest、SCN-004 兩個、同分 |
| `namecheck` 拿掉名稱比對 | 名稱不一致 |
| `isascii` 只檢查 `isdigit()` | 阿拉伯數字 PID |
| `count` `>` 改 `>=` | 剛好 1024 個 |
| `onesecond` 拿掉 1 秒門檻 | 新程序存活時間 |
| `borneq` `<=` 改 `<` | 新程序存活時間（剛好在上次讀取時啟動） |
| `tickback` 拿掉 tick 不可倒退 | tick 倒退 |
| `intcheck` 拿掉舊 tick 的整數檢查 | cache 損壞 |
| `isfinite` 拿掉 `at` 的有限數檢查 | cache 損壞（NaN） |
| `dashstr` 儀表板不檢查字串 | 儀表板異常值兩個 subTest |

首次交付時的 `rankfallback`（退回時仍用區間值排序）在加上第二排序鍵後與正確程式等價，不再是突變；它保護的行為改由 `lifetimekey` 驗證。

## 第二輪審查修正（review-ef3c759）

[review-ef3c759.md](review-ef3c759.md) 判定 PASS，S1 需決策。2026-11-06 使用者選「只比對單純 ASCII 名稱」（TBD-4，SCN-004 第二次修訂）。

| 發現 | 修正 | 紅燈（[artifacts/red-review2-fix.log](artifacts/red-review2-fix.log)） |
|---|---|---|
| S1 ps 改寫顯示名稱造成固定誤判 | 核心 comm 是可列印 ASCII、沒有開頭、結尾或連續空白時才比對 | `test_names_ps_rewrites_are_not_compared`：6 個 subTest 都因為出現 `cpu_fallback` 失敗。輸入取自 reviewer 以 procps-ng 4.0.4 實測的 ps 輸出 |
| N1 名稱測試只分得出首字元 | 補首字元相同的不一致（top `node`、核心 `nginx`） | 刻畫測試，原本就綠；以 `firstchar` 突變驗證 |
| N2 cache 的 `at` 是極大整數時 helper 失敗 | `at` 必須是 float（JSON 讀回的時間一律是 float） | `test_damaged_cache_only_loses_the_damaged_entries` 的 `10**400` subTest：`OverflowError` |
| N3 文件沒寫未知值的位置 | architecture.md 補上「未知排在所有已知值之後」 | 文件 |
| N4 VM 情境下 PID 全都不存在 | 不修；數字不會錯，只是每個程序都是未知，reviewer 列為參考 | — |

architecture.md 也改寫名稱不一致的解讀：「可能是另一個 PID namespace」，並說明哪些名稱不比對。README 雙語版本改成「單純 ASCII 程序名稱不一致」。

重跑全部 16 個突變（[artifacts/mutations-review2-fix.txt](artifacts/mutations-review2-fix.txt)）：未修改的版本全過，每個突變都有測試失敗。新增的 3 個：

| 突變 | 失敗的測試 |
|---|---|
| `plainskip` 拿掉「只比對單純名稱」 | ps 改寫的 6 個 subTest |
| `firstchar` 名稱只比首字元 | 首字元相同的不一致 |
| `floatonly` `at` 也接受整數 | cache 損壞（`10**400`） |

修正後再對真實 Docker 唯讀跑兩輪：第一輪 15 個程序都是 `no_previous`，第二輪 15 個都有區間值。

## 真實對照組（主機，TBD-2）

- 腳本：[artifacts/host_control.py](artifacts/host_control.py)。在主機上啟動自己的程序，先閒置 10 秒，再忙迴圈 15 秒。用 `ps -o pid,stat,pcpu,pmem,comm` 的輸出當作 Docker top 的資料，走完整的 `process_sample`，讀真實的 `/proc`。
- 命令：`python3 -I host_control.py <repo>`。
- 結果（[artifacts/host-control.txt](artifacts/host-control.txt)，審查修正後重跑，數值相同）：
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
  - 審查修正後重跑兩輪：結果相同，第二輪 15 個程序都有區間值，名稱比對沒有誤判。

## 驗收對照

| Scenario | 證據 | 判定 |
|---|---|---|
| SCN-001 | `test_scn001_spiking_long_lived_process_ranks_first_by_interval`、`test_scn001_interval_and_lifetime_are_both_shown`、突變（排序、分母）、主機對照組 | 通過 |
| SCN-002 | `test_scn002_without_previous_ranks_by_lifetime_and_says_why`（輸入順序已改，`lifetimekey` 突變）、時鐘沒前進的測試、儀表板退回標示、真實採樣第一輪 | 通過 |
| SCN-003（修訂） | `test_scn003_pid_reuse_new_and_exited_processes`、`test_scn003_new_process_needs_one_second_of_life`、程序在讀取前結束的測試、`nostart`／`onesecond`／`borneq` 突變 | 通過 |
| SCN-004（第二次修訂） | `test_scn004_over_count_over_time_or_unreadable_falls_back_for_the_whole_container`、`test_scn004_name_mismatch_means_another_pid_namespace`、`test_mismatch_sharing_the_first_letter_still_falls_back`、`test_names_ps_rewrites_are_not_compared`、儀表板退回標示、`namecheck`／`plainskip`／`firstchar`／`lifetimekey` 突變；helper 既有的預算與硬上限測試仍通過 | 通過 |
| SCN-005 | `test_scn005_collect_keeps_readings_of_live_deep_processes_only`、`test_scn005_old_rows_keep_the_old_wording`；既有的 TSV 欄位測試仍通過 | 通過 |

## 其他

- 精煉：新增的函式只有 `boot_seconds`、`read_proc_times`、`interval_cpu`。`boot_seconds` 是為了讓測試能固定時間；沒有新增設定項。審查修正時把兩種模式的排序合成一個排序鍵（見上方 N3）。
- 影響分析：GitNexus 沒有登錄本 repo。用 grep 確認 `process_sample` 只在 `collect` 和測試中呼叫；`container_detail` 只在儀表板與測試中使用；`process_status` 的值沒有改變。
