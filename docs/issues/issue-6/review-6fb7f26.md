# Issue #6 第六輪獨立審查報告

- 審查日期：2026-11-12
- 範圍：`origin/main` merge-base 至固定 HEAD 的完整本機交付；專案依 `docs/agents/project.md` 不建立 PR。
- Reviewed BASE SHA：`f76a4c945d2405f66bb60284d7a75e80f7339254`
- Reviewed HEAD SHA：`6fb7f26b809dae4c667d6615f41da7e80d0a3ed6`
- Reviewed patch-id：`d42990adb547c836f698097bba20866903ec7d73`
- 核准基線 SHA：`0c489cbdf3ef2fa8c40a9086016643d6cce6b4f1`，依 `git log -G '核准來源'` 推得；README 的核准 commit 仍為「待提交」。
- 獨立 reviewer：`/root/issue6_review`，與原實作者 `/root` 分離。
- Review artifact：`docs/issues/issue-6/review-6fb7f26.md`

## 問題與風險

- MUST FIX：無。
- SHOULD FIX：`src/freeze_watch.py:1877-1923` 的即時與歷史狀態顯示，尚無直接 GUI 文字斷言。現有函式測試驗證資料與時間判準，Xvfb 套件驗證畫面版面與主題；補 `refresh` 對過期、恢復、損壞及零有效樣本的文字斷言，可提高日後回歸保護。這是證據持久力建議，現有綠燈有效，不阻擋本輪。

## 已查核維度

- 前輪 MUST FIX：`src/freeze_watch.py:349-368` 的 `metric_window` 對無效列先以 epoch、其次以 timestamp 定位；可定位且在事故窗外的列不再設 `incomplete`，無法定位的列仍保守標示。`incident_rows` 於 `src/freeze_watch.py:371-394` 在各讀取分支重算窗口損壞旗標，移除尾段解析先前掛在有效列上的全檔旗標；歷史零樣本路徑於 `src/freeze_watch.py:1886-1894` 也採窗口判準。隔離測試：00:00 完整列、00:20 截斷或 NUL 列，報告與歷史資料均不標損壞；23:58 截斷列及無法定位列均標損壞；00:02 截斷列只在含事件後 5 分鐘的報告標損壞，歷史前 30 分鐘資料不標。這與兩種窗口一致。
- SCN-001：舊版 24 欄、NUL／截斷／無效 epoch、只有損壞列、合法窗外樣本及窗外損壞列均有有效與反向對照；最後有效樣本得保留。SCN-002：固定時鐘的 60／61 秒邊界、缺資料與恢復，歷史回顧不套即時時鐘。SCN-003：GPU 停用、版本缺席、核心初始可讀、成功零命中、掃描失敗與重複原始命中／去重紀錄可區分；安全匯出僅含數值與分類。三項核准驗收均有對應證據。
- 測試證據：`docs/issues/issue-6/implementation-plan.md` 記錄固定版本沙箱外 `FREEZE_WATCH_SKIP_GUI_TESTS=1 ./scripts/check.sh` 156 項通過、14 項 GUI skipped，含 shell、安裝及解除安裝；另以 Xvfb 執行 `tests.test_window_layout` 21 項通過，含亮暗主題。Reviewer 另執行 `/usr/bin/python3 -m unittest tests.test_diagnostic_report tests.test_freeze_watch` 59 項通過，並確認固定完整 diff 的 `--check` 通過與 patch-id 相符；隔離臨時資料重驗前輪反例與窗內正例。紅綠紀錄在計畫中逐輪列明，未把跳過或先前 GUI 全套 segfault 當作通過。
- 相關失敗面：資料列完整／舊版短欄／損壞／缺資料分流；即時採樣過期及恢復；事故前與報告事件後窗口差異；可定位窗外損壞與無法定位損壞；核心掃描不可讀、成功零命中及重複命中；舊紀錄缺版本。上述均依程式路徑、反向對照或既有測試覆核，未發現剩餘阻擋錯誤。
- 需求、架構、安全與品質：沿用 TSV 與事件架構，無新增依賴、root 權限、GPU 自動採樣或真實服務操作。`install.sh`／`uninstall.sh` 的 VERSION 佈署對稱；報告不包含原始 journal、檔案路徑或程序命令。一般 TSV 解析共用 `parsed_tsv_row`，事故窗口另用 `metric_window` 判斷時間與損壞，分工合理；未見跨 Task 重複造成行為分歧或無需求的架構擴張。
- 豁免、待確認與限制：SCN-001～003 與 60 秒門檻有 2026-11-12 使用者核准來源；TBD-1／TBD-2 已有結論，事故原因仍未知且文件未過度推論。GUI 曾在另一全套執行方式 segfault；單獨 Xvfb GUI 21 項的實際通過及 14 項跳過已分開揭露。

## 流程判定

**PASS**。本結論綁定固定 `6fb7f26b809dae4c667d6615f41da7e80d0a3ed6`；後續若僅新增本報告提交，須依 `review` 的 artifact 有效性檢查判定是否可沿用。
