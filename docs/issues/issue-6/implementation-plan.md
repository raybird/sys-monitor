# Issue 6 初始計畫

2026-11-12：SCN-001～003 已由使用者核准，以下步驟依序執行。

## 設計方向
沿用既有 TSV 與事件架構；有效樣本與觀測可用狀態分開呈現。新增欄位保持舊格式相容；不由未知值推論正常。風險與首要驗證見 [README](README.md)。

## 實作步驟
1. ✅ SCN-001：舊版短欄位加 NUL／無效 epoch 尾列，先見 `AssertionError: 2 != 1`，修正後 `test_scn001_damaged_tail_does_not_replace_last_valid_old_row` 通過；保留有效樣本並標記不完整。短於舊版最低欄數的列亦略過。
2. ✅ SCN-002：固定時間測試先因缺少 `sample_freshness` 失敗；修正後 `test_scn002_live_freshness_uses_current_time_not_container_age` 通過，涵蓋 60／61 秒邊界、缺資料及恢復。即時畫面顯示狀態，歷史回顧不套用時鐘。
3. ✅ SCN-003：報告測試先因缺版本資訊失敗；修正後 `test_issue6_report_distinguishes_observation_states` 通過，涵蓋 GPU 停用、核心可讀零命中、不可讀與版本。舊格式沒有狀態時保持未知。
4. ✅ SCN-001～003：`FREEZE_WATCH_SKIP_GUI_TESTS=1 ./scripts/check.sh` 於沙箱外通過（153 項，14 項無顯示器略過；安裝、解除安裝與 shell 驗證通過）；`GSK_RENDERER=cairo xvfb-run -a /usr/bin/python3 -m unittest tests.test_window_layout -v` 通過（21 項，含亮暗主題對比）；已更新使用、架構與疑難排解文件。

## 測試策略
解析單元測試與畫面／報告整合驗證分開；不以無例外代替正確資料。不得操作真實服務製造事故。核准後補測試檔案與具體執行命令，不預記通過。

## 建檔檢核
- 已保存去識別化統計與查核方式。
- 已記錄產品行為核准來源。
- 2026-11-12：首輪完整測試已通過 153 項單元測試，但新增 VERSION 檔未在解除安裝時移除，導致安裝檢查失敗；修正後重新驗證通過。另一次 GUI 全套執行在 GTK 測試時 segfault，單獨 GUI 套件於 Xvfb 通過。
- 程式碼精煉：保持核心日誌串流掃描，避免把整段訊息載入 shell 變數；移除巢狀條件運算式與修正提示文字。
- 2026-11-12 第一輪獨立審查 [review-0c489cb.md](review-0c489cb.md) 判定 RETURN TO execute-task。修正三項 MUST FIX：成功掃描有明確事件與結果，報告僅陳述截至該次掃描的零命中；只有損壞列也標資料不完整；README 核准狀態一致。新增未掃描／掃描失敗／零有效列對照測試，先紅後綠。
- 修正後 `FREEZE_WATCH_SKIP_GUI_TESTS=1 ./scripts/check.sh` 於沙箱外通過（154 項，14 項因無顯示器略過，含安裝及解除安裝）；`GSK_RENDERER=cairo xvfb-run -a /usr/bin/python3 -m unittest tests.test_window_layout -v` 通過（21 項）。
- 2026-11-12 第二輪獨立審查 [review-eaa5cc1.md](review-eaa5cc1.md) 判定 RETURN TO execute-task。補前次 boot 查詢失敗不影響目前 boot 採樣的 shell 對照、重複核心訊息的原始命中數與去重後事件數區別，以及零有效樣本在安全報告中的損壞提示；`FREEZE_WATCH_SKIP_GUI_TESTS=1 ./scripts/check.sh` 通過（155 項，14 項因無顯示器略過，含新增 shell 對照），Xvfb GUI 21 項通過。
