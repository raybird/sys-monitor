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
2. **AC-2**：某容器 ID 的重啟基準超過一天沒有更新就會被刪除。容器消失超過一天後，帶著更高的重啟次數回來，不寫 `(new)` 事件；只消失一輪就回來，照常寫 `(new)`（對照組）。

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

1. ⏳ **AC-1：跨失敗輪次的重啟基準測試**（相依：無）
   - 產出：`tests/test_container_probe.py` 新增 partial 與 helper 逾時兩個案例。
   - 完成判準：測試在現有程式碼上通過；突變成整份取代時，partial 案例失敗。突變只做在 scratchpad 的複本，不提交。
2. ⏳ **AC-2：一天未更新就刪除基準的測試**（相依：無）
   - 產出：同一檔案新增測試，用替身 `date` 跳過一天，並有只消失一輪的對照組。
   - 完成判準：測試通過；拿掉刪除條件的突變版本失敗。
3. ⏳ **AC-3：疑難排解處置欄**（相依：無）
   - 產出：`docs/troubleshooting.md`。
   - 完成判準：AC-3 的人工核對與指令實跑結果記入下方證據。
4. ⏳ **AC-4、AC-5：issue 2 文件與型別註記**（相依：無）
   - 產出：`docs/issues/issue-2/README.md`、`docs/issues/issue-2/evidence.md`、`src/freeze_watch.py`。
   - 完成判準：連結都指向存在的檔案；`env -u DISPLAY -u WAYLAND_DISPLAY bash scripts/check.sh` 全過、沒有跳過。

## Timeline

| 日期 | 異動 | 負責人 |
|------|------|--------|
| 2026-11-06 | 建立；範圍取自 GitHub #5 | - |

---
**建立日期**: 2026-11-06  
**分級**: Small  
**風險**: Low\
**狀態**: 待實作
