# Issue #6 第三輪獨立審查報告

- 審查日期：2026-11-12
- 範圍：`origin/main` merge-base 至新提交的完整本機交付；專案不建立 PR。
- Reviewed BASE SHA：`f76a4c945d2405f66bb60284d7a75e80f7339254`
- Reviewed HEAD SHA：`6a7cb639cc6e948d8394b404cc02556af2e7dc64`
- Reviewed patch-id：`28cae937a94b1c5ad14aa9b8dbac76875257c903`
- 核准基線 SHA：`0c489cbdf3ef2fa8c40a9086016643d6cce6b4f1`，依 `git log -G` 核准來源欄位推得；README 的核准 commit 仍為「待提交」。
- 獨立 reviewer：`/root/issue6_review`，與原實作者 `/root` 分離。
- Review artifact：`docs/issues/issue-6/review-6a7cb63.md`

## 問題與風險

1. **MUST FIX｜合法但不在事故時間窗內的資料被誤報損壞。** `src/freeze_watch.py:469-470` 以 `metric_window(path, start, finish)` 的結果為空，就呼叫 `empty_sample_status(path)` 判斷資料不完整；後者 `src/freeze_watch.py:220-226` 只檢查檔案是否有非標頭列，沒有檢查該列有效性。完全合法的樣本只要落在窗口外，報告會同時說「此區間沒有可讀取的取樣」與「取樣資料不完整」。隔離實測：事件 `2026-10-05T00:00:00+00:00`，完整 36 欄樣本在 `00:20:00+00:00`（已超過事件後 5 分鐘）；`diagnostic_report` 仍輸出資料不完整。這違反 SCN-001 區分損壞與缺資料的目的。請以實際無效列作判準，並補「合法但窗口外」與「只有損壞列」的反向對照。
2. **SHOULD FIX｜GUI 新狀態缺直接整合測試。** `tests/test_freeze_watch.py` 驗證時間及損壞狀態函式，亮暗主題 GUI 測試驗證版面，但尚未對 `FreezeWatch.refresh` 的過期、恢復及歷史回顧顯示做直接斷言。這屬證據持久力建議，現有測試仍是真實通過。

## 已查核維度

- 前輪兩項 MUST FIX：`src/freeze-monitor:448-457` 現在用 `matches` 計原始命中、`recorded` 計去重與上限後寫出事件，報告不再把重複命中稱為零。前次 boot 掃描失敗只寫獨立 INFO，不把目前 boot 的 `kernel_log_state` 設為 unavailable。`scripts/check.sh` 增加重複訊息及前次 boot 失敗後目前 boot 仍掃描的真實 shell 對照；依程式與測試可判兩項修正有效。
- SCN-001：舊格式、NUL／截斷尾列與零有效列有測試；但上述合法窗口外資料被誤判，故尚未通過。SCN-002：固定時間的 60／61 秒、缺資料、恢復判準存在，歷史回顧不套用即時時鐘；沒有本輪新發現。SCN-003：成功掃描、未掃描、掃描失敗及重複命中已各有正反例，舊版缺資訊維持未知；沒有本輪新發現。
- 證據：`docs/issues/issue-6/implementation-plan.md` 記錄沙箱外 `FREEZE_WATCH_SKIP_GUI_TESTS=1 ./scripts/check.sh` 155 項（14 GUI 略過，安裝／解除安裝通過）及 Xvfb `tests.test_window_layout` 21 項通過。本 reviewer 另執行資料與報告的 13 項測試、`bash -n` 與固定 diff `--check`，均通過；這些綠燈沒有覆蓋上述窗口外合法檔案。
- 安全、架構與品質：沒有新增權限或原始日誌外洩；版本、核心原始命中及去重數的欄位分工清楚。三條 TSV 讀取路徑的有效性判準仍分散，修復時應避免以「無窗口樣本」等同「檔案損壞」。
- 豁免與待確認：核准來源涵蓋 SCN-001～003，TBD-1／TBD-2 有結論，未見此輪 MUST FIX 豁免；不將 GUI 全套在先前環境的 segfault 說成通過，單獨 Xvfb GUI 套件通過。

## 流程判定

**RETURN TO execute-task**。修正上述 MUST FIX 後須以新 HEAD 重審完整交付；本報告只對固定的 `6a7cb63` 有效。
