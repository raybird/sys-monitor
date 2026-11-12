# Issue #6 第五輪獨立審查報告

- 審查日期：2026-11-12
- 範圍：`origin/main` merge-base 至固定 HEAD 的完整本機交付；專案不建立 PR。
- Reviewed BASE SHA：`f76a4c945d2405f66bb60284d7a75e80f7339254`
- Reviewed HEAD SHA：`50a93763f260eb31450ae0e74bcd5512cc68313b`
- Reviewed patch-id：`7d2780857913c75e0f7c5fa766fe9297d77d551f`
- 核准基線 SHA：`0c489cbdf3ef2fa8c40a9086016643d6cce6b4f1`，依 `git log -G '核准來源'` 推得；README 的核准 commit 仍為「待提交」。
- 獨立 reviewer：`/root/issue6_review`，與原實作者 `/root` 分離。
- Review artifact：`docs/issues/issue-6/review-50a9376.md`

## 問題與風險

1. **MUST FIX｜事故窗外的損壞列仍誤標事故窗口不完整。** `src/freeze_watch.py:349-365` 的 `metric_window` 掃完整檔案，對所有無效列設定 `incomplete=True`，未在可解析 epoch 時先排除事故窗外資料；`diagnostic_report` 於 `src/freeze_watch.py:473-480` 把此旗標寫入前 30 分鐘／後 5 分鐘的報告。`read_tsv_path` 於 `src/freeze_watch.py:131-142` 也把整個讀取尾段的無效列旗標掛到最後有效列，`incident_rows` 回傳該列後，歷史 GUI 於 `src/freeze_watch.py:1904-1910` 誤標不完整。隔離實測：00:00 事故及完整 36 欄樣本，另有明確 epoch 為 00:20 的截斷列；事故報告只至 00:05，卻輸出「取樣資料不完整」，`incident_rows` 的 00:00 樣本也帶 `_incomplete=yes`。這與 `docs/architecture.md` 的「讀取窗口內出現損壞列才標示」及 SCN-001 對事故回顧的證據完整性要求不符。請將可定位的無效列依事故窗口判定，並以窗內損壞、窗外損壞及合法窗外樣本作反向測試；無法定位時間的損壞列須避免誤稱已知發生於事故窗口。
2. **SHOULD FIX｜歷史與即時狀態缺直接 GUI 斷言。** 目前 SCN-001／002 以資料函式測試為主，Xvfb GUI 套件驗證版面與亮暗主題；尚未直接斷言 `FreezeWatch.refresh` 對損壞、過期、恢復與歷史回顧顯示的狀態文字。這是證據持久力建議，現有測試不屬假綠燈。

## 已查核維度

- 前輪 MUST FIX：第五輪 `empty_sample_status` 已共用 `parsed_tsv_row` 的有效列判準；完整合法、但位於事故窗口外的樣本不再被 `empty_sample_status` 當作損壞。新反向測試驗證此判準。前兩輪核心掃描成功／失敗、原始命中與去重寫入數、零有效列報告、README 核准狀態等修正仍在固定完整 diff 中，未見新回歸。
- SCN-001：舊版 24 欄、NUL／截斷尾列、無有效列及合法窗外列均有測試；上述可定位的窗外截斷列仍會污染事故窗口狀態，故未通過。SCN-002：60／61 秒及恢復的固定時間測試存在，歷史回顧未套即時時鐘。SCN-003：成功掃描零命中、未掃描、失敗、重複命中與舊紀錄未知可區分；安全報告不輸出原始路徑、程序資訊與 journal。
- 證據：`docs/issues/issue-6/implementation-plan.md` 記錄固定版本後沙箱外 `FREEZE_WATCH_SKIP_GUI_TESTS=1 ./scripts/check.sh` 155 項通過（14 GUI skipped，含 shell、安裝與解除安裝）及 Xvfb `tests.test_window_layout` 21 項通過；完整 diff 的 `--check` 通過，patch-id 與固定輸入一致。Reviewer 另以隔離臨時目錄重現上述窗外截斷列問題。共享工作樹隨後已有實作者未提交的反向測試；Reviewer 當時執行 58 項得 1 項紅燈，該結果是新反向測試的重現，**不是固定 HEAD 原測試失敗或通過的證據**。
- 重要失敗面：有效舊欄位加損壞尾列應保留樣本並提示；只有損壞列應提示不完整，空檔應提示缺資料；事故窗外合法樣本不可標損壞（此輪已修）；事故窗外有可定位截斷列時，事故窗口不應標損壞（此輪仍失敗）；核心查詢成功零命中與查詢失敗不可混同，重複命中不可算零命中。其他既有對照測試與程式分支已覆核。
- 需求、架構、安全與品質：沒有新增 root 權限、GPU 採樣開關或原始 journal 匯出；版本檔安裝及解除安裝對稱。`parsed_tsv_row` 集中一般 TSV 有效列判準，消除了前輪分歧；事故窗口的完整性判斷仍散在一般尾段讀取與全檔 `metric_window`，導致上述正確性風險。未見額外超出 issue 的架構或依賴變更。
- 豁免、待確認與限制：SCN-001～003 於 2026-11-12 有使用者核准來源；TBD-1／TBD-2 已有結論，沒有本輪 MUST FIX 豁免。過往 GUI 全套在另一執行方式曾 segfault，文件誠實記錄並以單獨 Xvfb 21 項通過作證；不把跳過的 14 項視為通過。

## 流程判定

**RETURN TO execute-task**。修正上述 MUST FIX 並提交後，須對新的完整 HEAD 重新獨立審查；本報告只對固定 `50a9376` 有效。
