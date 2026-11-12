# Issue #6 第四輪獨立審查報告

- 審查日期：2026-11-12
- 範圍：`origin/main` merge-base 至新提交的完整本機交付；專案不建立 PR。
- Reviewed BASE SHA：`f76a4c945d2405f66bb60284d7a75e80f7339254`
- Reviewed HEAD SHA：`ddf7d2de2bbc1f4562416923c33f9c06bb8b2cd8`
- Reviewed patch-id：`e5539d3ae7a2c883b9224c43011e95f2ec5ced7d`
- 核准基線 SHA：`0c489cbdf3ef2fa8c40a9086016643d6cce6b4f1`，依 `git log -G` 核准來源欄位推得；README 的核准 commit 仍為「待提交」。
- 獨立 reviewer：`/root/issue6_review`，與原實作者 `/root` 分離。
- Review artifact：`docs/issues/issue-6/review-ddf7d2d.md`

## 問題與風險

1. **MUST FIX｜歷史回顧仍把合法但在事故窗外的資料誤判為損壞。** 第三輪修正令 `metric_window` 回傳 `(rows, incomplete)`，`diagnostic_report` 已採用真實無效列旗標；但 `src/freeze_watch.py:1867-1871` 在 `incident_rows` 為空時仍以 `empty_sample_status(source)` 判損壞。該函式 `src/freeze_watch.py:220-226` 只看是否有非標頭列，合法的窗口外樣本也會回傳「資料不完整」。隔離重現：事件 `2026-10-05T00:00:00+00:00`、同檔完整樣本 `00:20:00+00:00`，`incident_rows(incident) == []`、`empty_sample_status(path)` 回「資料不完整；沒有有效採樣」，故 `refresh` 會誤標歷史回顧。這直接違反 SCN-001「即時或事故回顧」區分資料損壞與缺資料。請讓 UI 的零有效列路徑也依真實無效列判定，並以合法窗口外資料及只有損壞列作反向對照。
2. **SHOULD FIX｜GUI 顯示仍缺直接回歸測試。** SCN-002 的 60／61 秒及 SCN-001 的資料狀態有函式層級測試，Xvfb GUI 套件檢查版面與主題；尚未直接斷言 `FreezeWatch.refresh` 對過期、恢復和歷史回顧的狀態文字。這是整合覆蓋與證據持久力建議，現有測試不是假綠燈。

## 已查核維度

- 前輪 MUST FIX：第三輪指出的診斷報告誤報已修正，`metric_window` 的兩個呼叫處已更新，報告採真實 `incomplete` 旗標。前兩輪的核心掃描失敗隔離、原始命中數／去重事件數、README 核准狀態仍維持修正；未見此輪新回歸。
- SCN-001：NUL 尾列、舊格式與只有損壞列有對照；診斷報告新增合法窗口外資料的反向測試，但歷史回顧仍有上述缺口，故未通過。SCN-002：固定時間門檻與恢復路徑存在。SCN-003：成功掃描、未掃描、失敗、重複命中與舊資料未知狀態有對照，沒有本輪新發現。
- 測試證據：`docs/issues/issue-6/implementation-plan.md` 記本輪資料／報告 58 項及 Xvfb GUI 21 項通過；shell、安裝與其他模組未改，沿用上一輪沙箱外完整檢查 155 項（14 GUI 略過）可接受。本 reviewer 另執行同 58 項測試，結果通過，`git diff BASE..HEAD --check` 通過；新增反向測試只驗證報告，沒有覆蓋 UI 的零樣本分支。
- 安全與架構：沒有新增權限或原始日誌輸出；`metric_window` 回傳型別變更已更新兩個呼叫點。資料完整性判準在 UI 與報告分歧，這是本輪的實際風險；修復時宜共用同一真實有效性判準。
- 豁免與待確認：SCN-001～003 核准來源可追溯，TBD-1／TBD-2 有結論；沒有此輪 MUST FIX 的豁免。GUI 曾在全套環境 segfault、單獨 Xvfb 套件通過，限制已揭露。

## 流程判定

**RETURN TO execute-task**。修正上述 MUST FIX 並提交後，須對新的完整 HEAD 重新獨立審查；本報告只對固定的 `ddf7d2d` 有效。
