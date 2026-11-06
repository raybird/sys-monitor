# Issue 5 - 容器重啟基準補測試與 issue 2 審查的文件小修 (Small)

## 概述

issue #2 第三輪審查（[review-a7c2c36.md](../issue-2/review-a7c2c36.md)，2026-11-06 PASS）留下幾項不擋合併的建議，這個 issue 處理它們：

- 收集器端的重啟基準合併邏輯沒有自動化測試。reviewer 把它改回 f1b9bfa 的「整份取代」寫法，現有測試仍然全過，表示這段邏輯被回退時沒有測試會失敗。
- 幾處文件不精確或缺漏。

這個 issue 不改變任何可觀察行為，只補測試保護與修正文件。

## 涉及檔案

- `tests/test_container_probe.py`：用真實 shell 收集器補重啟基準的測試。
- `docs/troubleshooting.md`：修正 `unavailable:error` 的處置說明與手動執行 helper 的指令。
- `src/freeze_watch.py`：`read_tsv_before` 內 `epoch_after` 的回傳型別註記，只改註記。
- `docs/issues/issue-2/README.md`、`docs/issues/issue-2/evidence.md`：補文件清單、涉及檔案、儀表板與收集器重啟基準的邊界差異、Python 3.10 證據的命令。

`src/freeze-monitor` 原則上不修改。如果測試必須調整收集器的結構才能寫，要先回報再改。

## 驗收條件

1. **AC-1**：重啟次數 1 → 中間一輪採樣失敗 → 重啟次數 2，收集器仍寫出一筆含 `restarts=2(new)` 的 Docker anomaly 事件。要涵蓋兩種失敗：
   - partial：該容器 `restart_count=NA`、`sample_status=unavailable_or_timeout`；
   - helper 逾時：外層 timeout 以 exit 124 結束。

   檢查方式：用真實 `src/freeze-monitor` 搭配替身 helper 的自動化測試。紅燈基線：把合併基準的 awk 暫時換回 f1b9bfa 的整份取代寫法，partial 那個案例必須失敗；換回後通過。
2. **AC-2**：某容器 ID 的重啟基準超過一天沒有更新就會被刪除。容器消失超過一天後，帶著更高的重啟次數回來，不寫 `(new)` 事件；消失不到一天就回來，照常寫 `(new)`（對照組）。

   檢查方式：真實 shell 的自動化測試，用替身 `date` 跳過一天。紅燈基線：暫時拿掉一天刪除的條件，這個測試必須失敗。
3. **AC-3**：`docs/troubleshooting.md` 的不可用原因表要寫對：
   - `unavailable:error` 的處置改成檢查 `docker context inspect` 與 socket 路徑，不再寫「As above」（手動執行 helper 只會再印出 `unavailable:error`）。
   - 手動執行 helper 的指令註明：直譯器以 `~/.config/freeze-watch/env` 的 `FREEZE_WATCH_PYTHON` 為準，安裝目錄依 `XDG_DATA_HOME`。

   檢查方式：人工核對文字與 `src/container_probe.py` 的 `unavailable_reason`、`install.sh` 的安裝路徑一致；把文件中的指令照抄在本機實際執行一次，確認能跑。
4. **AC-4**：issue 2 的文件補齊：
   - 文件清單列出 `review-f1b9bfa.md`、`review-a7c2c36.md`。
   - 涉及檔案列出 `docs/troubleshooting.md`、`.github/workflows/ci.yml`。
   - 風險段寫明儀表板與收集器重啟基準的邊界差異：跨日輪替後新檔第一筆沒有比較對象；儀表板只看該 ID 最後 60 筆，收集器保留一天；以 events.log 為完整紀錄。
   - evidence.md 補上 Python 3.10 綠燈 log 實際執行的測試命令。

   檢查方式：人工核對；確認連結指向存在的檔案。
5. **AC-5**：`epoch_after` 的回傳型別註記包含 `math.inf` 這個 float 值，行為不變。

   檢查方式：看程式碼；`scripts/check.sh` 前後都全過。

- **核准日期**: 2026-11-06
- **核准來源**: 使用者 2026-11-06 回覆「合併進 main 然後照建議開後續 issue」，接受把 review-a7c2c36 的 S1、N2～N5 移到本 issue、N1 維持現狀；範圍見 GitHub [#5](https://github.com/raybird/sys-monitor/issues/5)。同日選擇「#5 補測試與文件」作為下一個 issue。AC-1～5 對應 #5 範圍的第 1～4 項。

## 不處理

審查 N1 不在這個 issue 處理：partial 輪次中，某容器單獨查詢失敗時，它持續存在的異常會再寫一次事件。這只是多餘的事件紀錄，不會漏事件，目前追蹤 7 個容器也觸發不到（要超過 8 個才會）。依 reviewer 建議與使用者 2026-11-06 的決定維持現狀；追蹤的容器接近 8 個時再評估。

## 風險與首要驗證

**風險**: Low。只補測試與修文件，不改變可觀察行為。唯一的未知是 AC-2 的替身 `date` 會不會干擾收集器其他用到時間的地方，例如檔名、跨日輪替、缺口偵測；寫 AC-2 時先確認，不行就改用其他方式控制時間，並回報。

## 實作與驗證步驟

1. ✅ **AC-1：跨失敗輪次的重啟基準測試**（相依：無）
   - 產出：`tests/test_container_probe.py` 新增 partial 與 helper 逾時兩個案例。
   - 完成判準：測試在現有程式碼上通過；突變成整份取代時，partial 案例失敗。突變只做在 scratchpad 的複本，不提交。
   - 完成證據（2026-11-06）：
     - 新增 `RestartBaselineTests`，以 `run_rounds` 驅動真實 `src/freeze-monitor`，每輪 Docker 採樣的替身 helper 回應可以指定為 ok、partial 或卡住。
     - `test_ac1_partial_round_keeps_the_restart_baseline` 與 `test_ac1_helper_timeout_round_keeps_the_restart_baseline` 在現有程式碼上通過（[artifacts/check.log](artifacts/check.log)）。
     - partial 案例的歷程：
       - 第一版 3 輪（重啟次數 1、NA、2）：只抓得到「基準被清掉」。
       - 依 [review-c315961.md](review-c315961.md) S1 改成 4 輪（1、NA、1、2）：抓得到「把 NA 存成基準」，但第 3 輪會重新建立基準，所以又抓不到「基準被清掉」（[review-efd8c16.md](review-efd8c16.md) M1）。我那次只重跑了 NA 的突變，沒有重跑整份取代的突變，所以漏掉了。
       - 現在是 5 輪（1、NA、1、NA、2），斷言只有 1 筆含 `restarts=2(new)` 的事件，兩種回歸都抓得到。
     - 突變複跑（2026-11-06，以目前的測試為準）：在 scratchpad 的三份複本各做一種突變，在各自的 tests/ 下執行 `python3 -m unittest -v test_container_probe.RestartBaselineTests test_container_probe.IntegratedReviewFollowupTests.test_m1_n1_failed_rounds_neither_drop_the_restart_baseline_nor_repeat_events`：

       | 突變 | partial | 逾時 | AC-2 | m1_n1 | log |
       |---|---|---|---|---|---|
       | 未修改（對照） | ok | ok | ok | ok | [mutation-control.log](artifacts/mutation-control.log) |
       | 合併 awk 換回 f1b9bfa 的整份取代 | FAIL | ok | FAIL | ok | [mutation-replace.log](artifacts/mutation-replace.log) |
       | 拿掉 `if (now - ce[2] <= 86400)` | ok | ok | FAIL | ok | [mutation-noprune.log](artifacts/mutation-noprune.log) |
       | 合併 awk 拿掉 `$11 ~ /^[0-9]+$/`（把 NA 存成基準） | FAIL | ok | ok | ok | [mutation-na-baseline.log](artifacts/mutation-na-baseline.log) |
     - 限制：逾時案例在這個突變下仍然通過。逾時那一輪走 `unavailable:*` 的提早 return，不經過合併邏輯，所以它保護的是「逾時後基準仍在」這個行為，不是合併 awk 本身。
2. ✅ **AC-2：一天未更新就刪除基準的測試**（相依：無）
   - 產出：同一檔案新增測試，用替身 `date` 跳過一天，並有消失兩輪、不跳時間的對照組。
   - 完成判準：測試通過；拿掉刪除條件的突變版本失敗。
   - 完成證據（2026-11-06）：
     - 收集器開頭寫死了 `PATH`，所以 PATH 上的替身 `date` 不會被用到；第一次寫的測試因此失敗，得到 1 筆事件。改用 bash 匯出函式 `BASH_FUNC_date%%` 替換 `date`，只在 `date +%s` 時加上 offset，不修改 `src/freeze-monitor`。
     - `test_ac2_baseline_older_than_a_day_is_dropped` 通過：對照組（沒有跳過時間）寫 1 筆 `(new)`，跳過一天則 0 筆。
     - 紅燈基線：在 scratchpad 複本拿掉 `if (now - ce[2] <= 86400)`，同一命令 exit 1，只有 AC-2 FAIL（[artifacts/mutation-noprune.log](artifacts/mutation-noprune.log)）。
     - 替身 `date` 生效的證據是跳時間的案例本身：沒跳成功就會寫出 `(new)` 而變紅。reviewer 另外保留實跑的狀態檔確認 epoch 跳了 90001 秒，並有 GAP 事件（[review-c315961.md](review-c315961.md) N3）。上面拿掉刪除條件的突變不論時間有沒有跳都會紅，證明不了這點。
3. ✅ **AC-3：疑難排解處置欄**（相依：無）
   - 產出：`docs/troubleshooting.md`。
   - 完成判準：AC-3 的人工核對與指令實跑結果記入下方證據。
   - 完成證據（2026-11-06）：
     - 原因碼與 `src/container_probe.py` 的 `unavailable_reason` 一致；`error` 是其他例外的去處，helper 不輸出細節。
     - 安裝路徑與 `install.sh` 的 `data_home="${XDG_DATA_HOME:-...}"`、`env_file` 一致。
     - 把文件中的手動執行指令照抄在本機跑一次，只把 `mktemp -d` 的位置改到 scratchpad：exit 0，第一行 `ok`，後面 7 列容器（[artifacts/manual-helper-run.txt](artifacts/manual-helper-run.txt)；repo 公開，只保存摘要，不保存容器名稱與 ID）。
     - 新增的 `ls -l /var/run/docker.sock` 在本機輸出 `srw-rw---- root docker`。
     - 審查後修正（[review-c315961.md](review-c315961.md) N2）：手動執行指令改成用 `sed` 讀出 `FREEZE_WATCH_PYTHON`，不再用 `.` 執行設定檔，跟程式讀這個檔的方式一致；讀不到時退回 `/usr/bin/python3`，跟收集器的預設一致。照抄實跑：讀到 `/usr/bin/python3`，exit 0，第一行 `ok`，7 列容器。
     - 依 [review-efd8c16.md](review-efd8c16.md) N1 包回子 shell，不在使用者的 shell 留下 `py` 變數。照抄實跑：exit 0，第一行 `ok`，7 列容器，執行後 `py` 為空。
4. ✅ **AC-4、AC-5：issue 2 文件與型別註記**（相依：無）
   - 產出：`docs/issues/issue-2/README.md`、`docs/issues/issue-2/evidence.md`、`src/freeze_watch.py`。
   - 完成判準：連結都指向存在的檔案；`env -u DISPLAY -u WAYLAND_DISPLAY bash scripts/check.sh` 全過、沒有跳過。
   - 完成證據（2026-11-06）：
     - issue 2 README 補了文件清單、涉及檔案，並在風險段加上「已知邊界」；evidence.md 補上 3.10 紅綠燈的命令。
     - 用腳本逐一檢查 issue 2 README、evidence.md 與本 README 的相對連結，全部存在。
     - `epoch_after` 註記改為 `tuple[int, int | float | None]`。
     - `env -u DISPLAY -u WAYLAND_DISPLAY bash scripts/check.sh`：exit 0，Ran 129 tests，OK，沒有跳過，All checks passed（[artifacts/check.log](artifacts/check.log)，審查後修正之後重跑）。129 = 126 + 3 個新測試。
     - 精煉：新測試的替身 helper 與既有 m1_n1 測試有部分重複。既有測試沒有改寫，維持手術式修改。審查後拿掉 `run_rounds` 沒用到的 `'fail'` 選項，並補上 class 之間的空行（N4）。
     - 影響分析：GitNexus 沒有登錄本 repo。用 grep 確認 `epoch_after` 只在 `read_tsv_before` 內使用；`src/freeze-monitor` 沒有修改。

## Gate 豁免紀錄

| 日期 | 豁免項目 | 使用者原話 | 殘餘風險 |
|---|---|---|---|
| 2026-11-06 | 建立 PR 與 PR 證據（改由本地獨立審查報告承載） | 「這專案可以不走 pr 再本地直接審查」（2026-11-04，記錄於 docs/agents/project.md，持續有效） | 沒有平台上的審查紀錄；分支在審查時尚未推到 origin，CI 要等合併後在 main 上執行 |

## Timeline

| 日期 | 異動 | 負責人 |
|------|------|--------|
| 2026-11-06 | 建立；範圍取自 GitHub #5 | - |
| 2026-11-06 | 本地獨立審查 c315961，判定 PASS（[review-c315961.md](review-c315961.md)） | - |
| 2026-11-06 | 使用者回覆「照建議修完之後合併」：修 S1、N2、N3、N4，不處理 N1、N6；AC-2 對照組的措辭由「只消失一輪」更正為「消失不到一天」，與測試相符，語意不變 | 使用者／開發助理 |
| 2026-11-06 | 本地獨立審查 efd8c16，判定 RETURN TO execute-task（[review-efd8c16.md](review-efd8c16.md)）：4 輪的 partial 案例抓不到整份取代的回歸。改成 5 輪並重跑全部突變；N1 一併修正 | - |

---
**建立日期**: 2026-11-06  
**分級**: Small  
**風險**: Low\
**狀態**: 待獨立審查
