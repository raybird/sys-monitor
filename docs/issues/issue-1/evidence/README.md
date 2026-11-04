# Issue 1 驗證證據

查核日期：2026-10-07。提交前工作區以 [pre-rebase-source.json](pre-rebase-source.json) 的 SHA-256 定位；原始 main 為 849e6aa，核准規格為 05e4d2c。

## 紅燈與綠燈

2026-10-07 以 `git archive 849e6aa` 建立隔離副本，複製當前 tests 的五份回歸測試，執行 `xvfb-run -a /usr/bin/python3 -m unittest discover -s tests -v`。
exit 1，55 項測試中有 9 個斷言失敗與 14 個錯誤，見 [baseline-red.log](baseline-red.log)。失敗涵蓋錯讀輪替檔、FREEZE 不確定性、事件回顧與報告資料定位、亮色對比，以及尚不存在的 GPU／報告功能。缺少新 API 屬目標功能缺漏，沒有把環境錯誤當成紅燈。

2026-10-07 在交付工作區執行 `xvfb-run -a bash scripts/check.sh`：exit 0，55 項測試全部通過，Bash／Python 語法、ShellCheck、systemd 與隔離安裝／移除均通過。完整輸出：[pre-rebase-check.log](pre-rebase-check.log)。

| 驗收 | 主要證據 |
|---|---|
| SCN-001 | GTK 真實合成背景與文字顏色，亮暗主題的正常／hover／selected 對比均至少 4.5；原版亮色約 1.14–1.24。圖像：[亮色](dropdown-light.png)、[暗色](dropdown-dark.png)，擷取與人工檢視日期為 2026-10-05。 |
| SCN-002 | test_previous_session 的多次輪替、最後取樣與 silent_for；test_freeze_watch 的 last_sample 窗口、跨輪替回顧。 |
| SCN-003 | 真實 Bash 收集器 subprocess：空／缺失／無效檔回退、全無取樣、STOP、不借用其他 session。 |
| SCN-004 | 不同 boot 為 UNCLEAN 並記 cause=unknown，同 boot 為 INTERRUPTED；歷史 FREEZE 與 UNCLEAN 的 UI 標籤保留疑似措辭。 |
| SCN-005 | fdinfo 差值、閒置、共享／重複 fd、PID 重用、計數器回退、capacity、缺計數器、退出、權限不足與掃描預算；真實收集器及安裝後 GPU 欄位整合。 |
| SCN-006 | 敏感資料移除、前後窗口與 session 邊界、舊事件在檔案增長後仍可匯出、前次核心錯誤、檔案權限與內容、GTK 唯讀預覽／取消；[預覽圖像](report-preview.png) 於 2026-10-05 擷取與檢視。 |

2026-10-07 隱私負向對照使用含假敏感路徑與假參數的 fixture，故意改成原文輸出，確認同一測試拒絕洩漏，見 [privacy-negative.log](privacy-negative.log)。探針本身 exit 0，因預期的斷言失敗正好被捕捉；這份紀錄不冒充產品測試綠燈。

## 層級與精煉

2026-10-07：Task 1.1 的 subprocess 直接覆蓋 Bash 外部事件契約，因此外／內迴圈合併；Task 1.2 另有 Python 消費端查核。GPU 的核心 fixture 與 Bash／安裝整合保留雙層。報告的資料／隱私及寫檔與 GTK 預覽分別查核。

2026-10-07 依 code-simplify 將 GPU client 狀態的巢狀條件式改為明確分支；精煉前後均以同組 55 項測試驗證。另修正秒數測試的跨秒競態，以收集器執行區間驗證實際秒數。這項自我檢查不是獨立 review。

## 成本、限制與流程基線

2026-10-07 以真實收集器各取 3 次單筆樣本，比較 `FREEZE_WATCH_GPU_PROCESSES=0`／`1`；其他設定為 MAX_SAMPLES=1、PYTHON=/usr/bin/python3、JOURNALCTL=/bin/false、COMPOSE_PROJECT 空值，每次使用獨立暫存 XDG_STATE_HOME。數據：[sampling-cost.json](sampling-cost.json)。

關閉／啟用的 wall 中位數為 76.583／123.938 ms，CPU 為 86.988／135.115 ms。新增 CPU 約 48 ms，以預設 10 秒週期計約占單核心 0.48%。本機可見 GPU client 為 0，這不是 AMD／Intel 活動的實機證據；引擎契約依官方 DRM 文件與 fixture 驗證，不支援的驅動明示限制。滿載 GPU 的記錄量仍需在有可用硬體的環境觀察。

2026-10-07 `git diff --check` 通過。上游 kit 已更新，`init-project.py --check` 對 AGENTS、acceptance、review-evidence 報版本差異；本次不更新流程核心。逐一 SHA-256 核對 docs/.dev-rules-kit.json：10 份已部署核心／範本均與原基線相符，專案契約 2.0 仍符合所用技能的最低需求。

2026-10-07：尚未完成獨立審查，也未部署到真實使用者服務。

## Rebase 整合紀錄

2026-10-07：已整合 origin/main d8748d6；CSS 衝突採用上游下拉選單樣式。核准文件由 05e4d2c 映射至 c62159c，兩個提交中的文件逐字相同；工作區另有台灣用字修正，驗收語意不變。GitNexus detect_changes 已執行，但 MCP 未註冊本專案，無法取得圖譜結果；不記為通過。

2026-10-07：rebase 後完整 `xvfb-run -a bash scripts/check.sh` 為 exit 0；55 項測試、亮／暗主題實際對比、語法與隔離安裝／移除均通過。輸出見 [post-rebase-check.log](post-rebase-check.log)，程式與測試定位見 [post-rebase-source.json](post-rebase-source.json)。目前尚未 push、建立 PR 或執行獨立審查。

## 2026-11-04 審查修正（review-9f5712f.md 的 RETURN TO execute-task）

2026-11-04：依使用者決策 rebase 到 origin/main 6d6066e。`src/freeze_watch.py` 三處衝突沿用上游的程序清單版面，GPU 區塊另以可見標籤接在其後；上游事故摘要與標題把 FREEZE 寫成「系統凍結」，與 SCN-004 抵觸，改為「非正常關機／疑似當機，原因未確認」並涵蓋 UNCLEAN，`tests/test_freeze_watch.py` 補上措辭斷言。核准文件由 c62159c 映射至 5524b0e，`## Gherkin 驗收劇本` 區塊逐字相同。解衝突後 `check.sh` exit 0（62 項）。

紅燈：以 `git archive a3e841c`（修正前、rebase 後）的 src 與 uninstall.sh，搭配修正後的 tests 與 scripts/check.sh 執行，unittest 71 項中 10 個失敗、3 個錯誤，`check.sh` exit 1，見 [review-fix-red.log](review-fix-red.log)：

| 審查項目 | 紅燈測試 | 修正前的結果 |
|---|---|---|
| MF-1 尾端截在列中間 | `test_review_survives_a_tail_cut_inside_a_row`（測試先確認截點不在行首） | 回顧 0 列，應為 181 列 |
| MF-2a 寬列的即時熱度帶 | `test_live_tail_keeps_half_an_hour_of_wide_rows` | 只讀回 35 列，應至少 180 列 |
| MF-2b 精簡 GPU JSON | `test_scn005_*` 四項、`test_scn005_opt_in_*`、`GpuSummaryTests` | 舊格式每個引擎都是物件，閒置持有者也逐一完整列出 |
| SF-1 非 UTF-8 程序名稱 | `test_scn005_non_utf8_process_name_does_not_fail_the_sample` | UnicodeDecodeError |
| SF-2 掃描順序與不完整訊號 | `test_scn005_other_users_*`、`test_scn005_newest_*`、`test_scn005_protected_*` | 其他使用者與受保護程序都算 unavailable，狀態變成 partial；有上限時只掃到舊程序 |
| SF-3 無效位元組 | `test_invalid_bytes_do_not_stop_the_review` | 事件找不到它的 metrics 檔 |
| SF-4 移除後殘留 | `check.sh` 新增 `test ! -e ~/.local/share/freeze-watch` | exit 1 |

SF-5：舊的 `test_scn003_does_not_borrow_a_previous_session_rotation` 改壞實作也會通過。新增的 `test_scn003_session_without_samples_does_not_borrow_an_earlier_session` 在 mutation（`src/freeze-monitor:564` 不在 START／STOP 重設檔案清單）下會失敗，舊測試照樣通過，見 [review-fix-mutation.log](review-fix-mutation.log)；這項是補強證據，未修改的實作原本就通過。SCN-001 對比測試加上固定 Adwaita，並量測勾選圖示；在 Xvfb 下主機佈景為 GTK 的 `Default`，探針確認每種佈景／模式／狀態都量到 label 與 image 兩個部件。這項同樣是補強，修正前也通過。截圖在目前程式上重拍並目視：[亮色](dropdown-light.png)、[暗色](dropdown-dark.png)、[報告預覽](report-preview.png)；擷取時要設 `GDK_BACKEND=x11`，否則主機有 wayland socket 時會截到全黑。

綠燈：2026-11-04 執行 `GDK_BACKEND=x11 GSK_RENDERER=cairo xvfb-run -a bash scripts/check.sh`，exit 0，71 項測試、語法、ShellCheck、systemd 與隔離安裝／移除均通過，見 [review-fix-check.log](review-fix-check.log)；`git diff --check`（src、tests、scripts、uninstall.sh）通過。程式與測試以 [review-fix-source.json](review-fix-source.json) 的 SHA-256 定位。

GPU 實機成本：2026-11-04 在本機真實 `/proc`（約 630 個程序，Intel i915）比較修正前後的 `freeze_gpu.py`，每 10 秒一次、各 6 次，見 [review-fix-gpu-cost.json](review-fix-gpu-cost.json)（不保存程序名稱與 PID）：

| | 修正前 | 修正後 |
|---|---|---|
| 狀態 | 每次 partial、truncated，unavailable 280 | ok，無截斷，unavailable 0，protected 36 |
| 看到的 client | 13 | 34 |
| 每列 JSON | 約 4.4 KB | 約 0.6 KB（首次基線約 7 KB） |
| 每日增量（8640 列） | 約 37.8 MB | 約 5.2 MB |
| 單次 CPU | 約 62 ms | 79～126 ms，中位數約 95 ms |

本機 2026-11-03 的 metrics 檔為 2.5 MB，啟用 GPU 紀錄後每日總量約為原本的 3 倍，屬同一量級。修正後 CPU 較高，是因為完整掃描本人的程序（約 13 500 個 fd），修正前的版本在 2048 個 fd 處就截斷；以 10 秒週期計約佔單核心 0.8～1.3%，量測時系統 load average 約 2.4～3.4。

精煉：2026-11-04 依 code-simplify 移除重複註解，受保護判斷改用回傳值，PID 只解析一次；精煉後以同組 71 項測試驗證。這項自我檢查不是獨立 review。

限制：引擎占比仍只在 Intel i915 的實機上看過，AMD 只有 fixture。GitNexus MCP 沒有本專案的索引，impact／detect_changes 無法執行，呼叫端改用 grep 確認。尚未部署到真實使用者服務。

## 2026-11-04 第二輪審查修正（review-6c972c3.md 的 RETURN TO execute-task）

紅燈：以 `git archive 61a93c3`（第二輪修正前）的 src，搭配修正後的 tests 執行，74 項中有 5 個失敗，見 [review2-fix-red.log](review2-fix-red.log)：

| 審查項目 | 紅燈測試 | 修正前的結果 |
|---|---|---|
| MUST FIX：UNCLEAN 事件沒有嚴重度顏色 | `test_unclean_event_is_marked_as_danger` | UNCLEAN 事件內文只有 `muted`，FREEZE 有 `danger` |
| SF-1：沒有 client id 的驅動 | `test_scn005_driver_without_client_ids_is_listed_by_name`、`test_scn005_missing_counters_exited_fd_and_capacity`、`GpuSummaryTests` | 6 個程序、各 12 個 `/dev/nvidia0` fd 變成 64 個 client 並截斷 |
| SF-2：名稱同時列為有活動與閒置 | `test_scn005_active_name_is_not_also_listed_idle` | 同一程序的閒置 client 讓名稱出現在 `idle` |

修正：事件清單把 UNCLEAN 與 FREEZE、KERNEL 同列為 danger。沒有 client id 或引擎計數器的持有者，依驅動以名稱列在 `unsupported`，不占 client 上限，畫面顯示「〈驅動〉 計數器不支援，僅確認持有裝置：名稱」；沒有 `drm-driver` 欄位的 `/dev/nvidia*` 記為 nvidia。閒置名單排除已列為有活動的名稱。這個 fixture 的輸出在 200 bytes 以內；沒有 NVIDIA 實機可量。

綠燈：2026-11-04 執行 `GDK_BACKEND=x11 GSK_RENDERER=cairo xvfb-run -a bash scripts/check.sh`，exit 0，74 項測試與其他檢查均通過，見 [review2-fix-check.log](review2-fix-check.log)；`git diff --check`（src、tests、scripts、uninstall.sh、docs/architecture.md）通過。

GPU 實機成本：2026-11-04 在本機真實 `/proc`（648 個程序，Intel i915）執行第二輪修正後的 `freeze_gpu.py`，每 10 秒一次、6 次，見 [review2-fix-gpu-cost.json](review2-fix-gpu-cost.json)：每次都是 ok、沒有截斷；穩定後每列 461～588 bytes，每日約 5.1 MB；CPU 中位數約 81 ms。
