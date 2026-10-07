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
