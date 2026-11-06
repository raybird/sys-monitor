# 驗證證據

最後更新：2026-11-06。原始實作的證據由前次 session 取得（基線 `6d6066e`，提交 `1e33e63`）；整合 main 與 S3 修訂的證據在 2026-11-06 本次取得。

## 範圍與環境

- 分支：`issue-2-container-inspection`。原始提交 `1e33e63`，整合 main（`bd56e94`）的合併提交 `23ca87c`。
- 環境：Linux，`/usr/bin/python3` 3.14.4。GUI 測試在 xvfb 下執行（`GDK_BACKEND=x11 GSK_RENDERER=cairo`）。
- 未啟停容器、未部署服務、未修改主機設定。安裝與移除測試只操作臨時 HOME。

## 原始實作（1e33e63，前次 session）

紅燈：

- 新增的 Counter／Sampling 測試第一次執行時，因為 `container_probe.py` 還不存在而失敗。
- UI 資料層新增的 4 個測試，因為 `latest_containers`／`container_detail` 還不存在而失敗。
- 第一輪審查的回歸測試先得到 6 個失敗斷言（含 CPU 的三個 subtest），修正後同一組測試通過：[artifacts/recovery-red.log](artifacts/recovery-red.log)、[artifacts/recovery-green.log](artifacts/recovery-green.log)。
- R4 輪替公平性：64 個混合狀態容器跑 20 輪，修正前失敗：[artifacts/rotation-red.log](artifacts/rotation-red.log)。

綠燈：

- 前次 session 跑 `FREEZE_WATCH_SKIP_GUI_TESTS=1 FREEZE_WATCH_SKIP_SYSTEMD_VERIFY=1 bash scripts/check.sh`，exit 0，68 個測試中 60 個通過、8 個 GUI 測試明確跳過：[artifacts/check-portable.log](artifacts/check-portable.log)。
- 當時的執行環境建立 Gtk.Label 就 segfault，所以 GUI 測試是跳過，不是通過。
- GitHub Actions run 42153168060（headSha `1e33e63`，xvfb）：68 個測試全部 OK，沒有跳過，GUI widget 測試有實際執行。
- 獨立 reviewer 在 `1e33e63` 執行 `env -u DISPLAY -u WAYLAND_DISPLAY bash scripts/check.sh`：exit 0，68 個測試 OK，0 個跳過（[review-1e33e63.md](review-1e33e63.md)）。

## 真實 Docker 量測（獨立 reviewer，2026-11-06）

- 以唯讀方式執行 `python3 -I src/container_probe.py <ts> <epoch> runwukong,runtelenexus <暫存目錄>` 兩次，間隔約 20 秒。
- 結果：
  - 耗時 0.26 秒與 0.21 秒，RSS 約 26 MB，每輪約 3.3 KB。
  - 輸出 8 列，其中 7 個是追蹤中的容器（含 1 個已退出），每列 24 欄。
  - 第二輪算出了速率；cache 權限是 0600。
- 這是閒置狀態的量測。高負載成本依 Gate 豁免紀錄留到合併後觀察。

## 整合 main（23ca87c）

- 有 5 個檔案衝突：
  - `install.sh`、`uninstall.sh`、`scripts/check.sh`：兩邊新增的檔案取聯集（`container_probe.py` 與 `freeze_gpu.py`）。
  - `src/freeze-monitor`：metrics 表頭用 main 的版本（含 `gpu_processes`），docker 表頭用本分支的 24 欄。
  - `src/freeze_watch.py`：`read_tsv_path` 用 main 的版本。它已經包含本分支需要的 `byte_limit` 參數，另外多了 `min_rows`。
- 驗證命令：`env -u DISPLAY -u WAYLAND_DISPLAY DOCKER_HOST=unix:///nonexistent bash scripts/check.sh`
  - 結果：exit 0，107 個測試 OK，0 個跳過，All checks passed。
  - 測試數核對：main 有 76 個測試定義，1e33e63 有 66 個，共同基線有 37 個，合併後是 105 個定義，沒有遺失。執行數比定義數多 2，是 `HardTimeoutTest` 繼承父類別造成的重複執行。

## S3 警示判準修訂（SCN-006、SCN-007）

- 規格來源：使用者 2026-11-06 回覆「照你的建議處理 D1、M3、S3、S7」。
- 測試契約變更：`test_known_anomalies_only_are_flagged` 原本斷言 `dstate=1` 與 `restart_count=2` 會警示。核准的行為已經改變，所以改成追蹤中的容器加上 `dstate=4`，並移除只看累計重啟次數的斷言。
- 新增測試：
  - `ContainerAlertTests.test_events_follow_tracked_restart_increase_and_dstate_threshold`：用真實 shell 收集器跑 3 次容器採樣，替身 helper 會輸出 4 個容器。
  - `test_dstate_uses_host_elevated_threshold`、`test_untracked_containers_are_never_flagged`、`test_restart_flags_only_an_increase_over_previous_sample`。
- 紅燈，命令是 `cd tests && /usr/bin/python3 -m unittest test_container_probe.ContainerAlertTests test_freeze_watch.ContainerBackwardCompatibilityTests`，exit 1（[artifacts/alert-red.log](artifacts/alert-red.log)）：
  - shell 端寫了 3 筆事件，預期 2 筆：D 數一變就重寫事件、未追蹤的 portainer 被警示、第一次採樣就因重啟次數 1 而警示。
  - UI 端 3 個失敗加 1 個錯誤：`container_warning` 不接受前一次樣本參數；`dstate=3` 與只有累計重啟次數時仍然警示。
  - 第一次執行時替身 helper 有錯（關鍵字參數重複），helper 回報 unavailable，事件數是 0。這是測試裝置的錯，不是目標行為的紅燈；修正替身後才取得上述紅燈。
- 最小實作後全綠：同一個命令 exit 0，6 個測試 OK（[artifacts/alert-green.log](artifacts/alert-green.log)）。
- 完整檢查：`env -u DISPLAY -u WAYLAND_DISPLAY DOCKER_HOST=unix:///nonexistent bash scripts/check.sh`，exit 0，111 個測試 OK，0 個跳過，All checks passed（[artifacts/check-integrated.log](artifacts/check-integrated.log)）。
- 重構：no-op。改動是一個判斷函式與一段 awk，沒有可抽取的重複；最小實作後的綠燈同時代表最終狀態。
- 影響分析：GitNexus 索引沒有註冊 sys-monitor，`impact` 回報 repository not found，無法使用。改用 grep 確認 `container_warning` 只有 `src/freeze_watch.py` 的 `_append_container_row` 一處呼叫與測試；shell 端的 awk 只在 `record_docker_sample` 內。

## 視覺 QA 與跨重啟回看（M3，2026-11-06）

重現腳本：[artifacts/qa/fake_probe.py](artifacts/qa/fake_probe.py)（替身 helper）、[artifacts/qa/shots.py](artifacts/qa/shots.py)（截圖）。兩個腳本內含本機 repo 的絕對路徑。

步驟：

1. 以 `XDG_STATE_HOME=<暫存目錄> FREEZE_WATCH_CONTAINER_PROBE=fake_probe.py FREEZE_WATCH_INTERVAL_SECONDS=1` 啟動真實的 `src/freeze-monitor`，約 8 秒後 `kill -9`，所以沒有寫 STOP。
2. 把 events.log 中前一次 START 的 `boot=` 改成另一個 id，模擬跨開機。這與 `scripts/check.sh` 的 UNCLEAN 測試做法相同。
3. 以 `FREEZE_WATCH_MAX_SAMPLES=4` 再跑一次收集器。
4. 在 xvfb 下開儀表板，分別以 Adwaita 亮色與暗色主題截圖，即時與回顧模式都截。

結果：

- 事件紀錄（[artifacts/qa/cross-restart-events.log](artifacts/qa/cross-restart-events.log)）：
  - 第一次 session 的第二次容器採樣，因重啟次數由 1 增加到 2，寫了一筆 `Docker anomaly: runwukong-schedulerd-1:...restarts=2(new)...`。
  - 未追蹤的 portainer 一直是 OOM 而且重啟 7 次，但沒有被警示。
  - 重啟後記錄 `UNCLEAN`；新 session 的第一次採樣沒有基線，所以不警示。
- 跨重啟回看（[artifacts/qa/review-light-window.png](artifacts/qa/review-light-window.png)、[artifacts/qa/review-dark-window.png](artifacts/qa/review-dark-window.png)、[artifacts/qa/review-containers.png](artifacts/qa/review-containers.png)）：
  - 選擇事故後，hero 顯示「DOCKER 4 · ok · 最後採樣 12:06:47」，這是中斷前最後一次容器採樣，不是新 session 的 12:06:54。
  - 詳情對齊「主機 @12:06:47：CPU 47°C · I/O PSI 0.02% · RAM PSI 0.01%」。
- 警示樣式（[artifacts/qa/warning-containers.png](artifacts/qa/warning-containers.png)）：把最新一次樣本中 memoria 的 D 改成 5 後，該列以醒目的黃色顯示，文字清楚可讀；portainer 維持一般色。
- 亮暗主題：
  - 容器清單的截圖在兩種主題下逐位元組相同（md5 一致），因為儀表板用固定的深色調色盤。
  - 整窗截圖不同，差在標題列。兩種主題下容器清單、詳情與下拉選單都清楚可讀。
- 檢視者：本 session 的 agent 看 xvfb 截圖，不是使用者在實體桌面上操作。
- 限制：
  - 跨重啟是收集器重啟加上改寫 boot id 的模擬，沒有真的重開機。
  - 「未知%」與正常列同色（審查 S5，TBD-6）在截圖中可以看到，本次未修。
- 範圍外觀察：亮色主題下，標題列「預覽診斷報告」按鈕的字對比偏低（review-light-window.png）。這個元件不在本 issue 的改動範圍內，只記錄不修。

## 驗收對照

| Scenario | 證據 | 結論 |
|---|---|---|
| SCN-001 | check.sh 雙 project 設定與單 project 升級保留；fixture；真實 helper 輸出兩組專案都有 ID、project、service | 通過 |
| SCN-002 | fixture、RecoveryRegressionTests；真實 health 有 healthy 與 not_configured；GUI 測試；QA 截圖 | 通過；未知呈現的改善屬於 TBD-6 |
| SCN-003 | CounterTests、RecoveryRegressionTests；真實第二輪有速率 | 通過；速率分母口徑屬於 TBD-6（S2） |
| SCN-004 | `process_sample` 上限與欄位測試；真實 top 解析；文件標明生命週期平均的限制 | 通過；差分改善追蹤 #4 |
| SCN-005 | 不讀未來樣本與缺口標示的測試；跨重啟 QA | 通過；2 MB 尾端的回看範圍屬於 TBD-6（S6） |
| SCN-006 | `test_dstate_uses_host_elevated_threshold`、`test_known_anomalies_only_are_flagged`、shell 事件測試；警示截圖 | 通過 |
| SCN-007 | `test_untracked_containers_are_never_flagged`、`test_restart_flags_only_an_increase_over_previous_sample`、shell 事件測試（3 次採樣只寫 2 筆）；QA 事件紀錄 | 通過 |
| SCN-008 | 卡住 60 秒的 helper 在 11 秒內終止，主機樣本照常落盤；不可用時明確寫空快照；遠端 endpoint 被拒；真實失效注入很快回 unavailable | 通過；內部預算不是硬上限（S8），高負載成本已豁免 |
| SCN-009 | 舊 11 欄檔案測試；沿用 docker-*.tsv 輪替；uninstall 會刪 probe；程序只用 comm | 通過；磁碟增量屬於 TBD-6（S6） |
