# Issue #6 第二輪獨立審查報告

- 審查日期：2026-11-12
- 範圍：`origin/main` merge-base 至新提交的完整本機交付；專案不建立 PR。
- Reviewed BASE SHA：`f76a4c945d2405f66bb60284d7a75e80f7339254`
- Reviewed HEAD SHA：`eaa5cc15815dffe2902a4083831409d707b093a7`
- Reviewed patch-id：`efb2f968480941d8b3f0aca2c35bc306fe79da5b`
- 核准基線 SHA：`0c489cbdf3ef2fa8c40a9086016643d6cce6b4f1`，依 `git log -G` 核准來源欄位推得；README 的核准 commit 仍為「待提交」。
- 獨立 reviewer：`/root/issue6_review`，與原實作者 `/root` 分離。
- Review artifact：`docs/issues/issue-6/review-eaa5cc1.md`

## 問題與風險

1. **MUST FIX｜前次 boot 讀取失敗會停掉目前 boot 的核心採樣。** `src/freeze-monitor:626-630` 在 UNCLEAN 開機時先以 `scan_kernel_log -k -b -1` 讀前次 boot；該呼叫失敗時 `src/freeze-monitor:449-451` 將共用的 `kernel_log_state` 設為 `unavailable`，隨後 `src/freeze-monitor:779-783` 因狀態非 `ok` 而不再掃描目前 boot。隔離實測：預置一個異 boot 的未結束 START，假 journalctl 對 `-b -1` 回傳 7、對目前 boot 查詢回傳 0，collector 正常退出但新 START 為 `kernel=unavailable`、完全沒有目前 boot 的 `KERNEL_SCAN`。這會在最需調查的非正常重啟後遺失新的核心證據。請分開處理前次 boot 掃描失敗與目前 boot 的可讀狀態，並驗證目前 boot 仍持續掃描。
2. **MUST FIX｜重複核心錯誤會被宣稱零命中。** `src/freeze-monitor:432-445` 在 `line == last_kernel_alert` 時先跳過，該行不增加 `count`；成功事件卻寫 `matches=0`。若同樣的核心錯誤在前次記錄超出事故回顧的 30 分鐘後再度出現，報告窗口沒有新的 `KERNEL` event，`src/freeze_watch.py:513-517` 會顯示「零命中」。這與 SCN-003 區分真正零命中與無證據的目標相反。請區分原始匹配數和去重後寫出的事件數，或將文字精確限定為「無新增紀錄」，並以重複訊息對照測試。
3. **SHOULD FIX｜事故匯出在零有效列時仍不標損壞。** 即時與事故回顧 UI 已透過 `empty_sample_status` 辨識只有損壞列，但 `diagnostic_report` 仍以 `metric_window` 的空清單輸出「沒有可讀取的取樣」，未指出資料損壞。若安全匯出也需表達 SCN-001 的資料完整性，建議補報告對照；目前 SCN-001 文字要求即時與事故回顧載入，故列改善建議。
4. **SHOULD FIX｜新 GUI 行為的回歸保護仍偏窄。** 新測試斷言 `sample_freshness` 與 `empty_sample_status`，亮暗主題測試涵蓋版面，尚未直接斷言 `FreezeWatch.refresh` 在逾 60 秒、恢復、回顧三種模式的顯示。這屬證據持久力與整合覆蓋建議，不否定現有測試的真實紅綠燈。

## 已查核維度

- 第一輪三項 MUST FIX：README 概述已與核准及實作狀態一致。只有損壞列時，`empty_sample_status` 與畫面入口能顯示資料不完整；測試與空白檔對照成立。核心狀態不再只用 START 可讀性推論零命中，而是等待 `KERNEL_SCAN` 成功事件；未掃描與掃描失敗顯示未知／不可讀。上列兩個新發現仍使 SCN-003 未通過。
- 核心掃描實證：隔離假 journalctl 讓目前 boot 掃描成功或失敗，collector 皆正常退出；成功路徑有 `KERNEL_SCAN status=ok`，失敗路徑只有 `kernel log scan unavailable`。另以上述 UNCLEAN 前次 boot 失敗情境證明目前 boot 掃描被錯誤抑制。
- SCN-001：合法舊欄位、NUL 尾列、只有損壞列與純標頭對照具測試；事故報告零有效列的狀態呈現為改善建議。SCN-002：固定時間 60／61 秒、無資料與恢復測試存在，歷史回顧程式路徑避開即時時鐘。
- SCN-003：報告測試涵蓋新 session 的成功掃描、初始可讀但未掃描、初始不可讀及掃描失敗；舊紀錄的版本／狀態維持未知。重複事件與前次 boot 失敗是欠缺的關鍵失敗面。
- 總體測試：`docs/issues/issue-6/implementation-plan.md` 記錄沙箱外非 GUI `./scripts/check.sh` 154 項（14 GUI 略過）、Xvfb GUI 21 項通過；本 reviewer 另跑 12 項資料與報告測試通過。測試總數不替代上述未涵蓋路徑。`install.sh`／`uninstall.sh` 的 VERSION 處理、資料與報告隱私邊界維持一致。
- 架構／安全：新增 `KERNEL_SCAN` 是有界事件，未增權限或輸出原始 journal；修改集中在收集器、儀表板、安裝與相應文件。`read_tsv_path`、`read_tsv_before`、`metric_window` 的驗證規則仍有重複，後續修改應留意相容性分歧。
- 豁免與待確認：TBD-1、TBD-2 均有核准結論，沒有此輪 MUST FIX 的豁免；未核准的部署或合併不在本次審查範圍。

## 流程判定

**RETURN TO execute-task**。修正兩項 MUST FIX 並提交後，須對新的完整 HEAD 重新獨立審查；本報告只對上述固定提交有效。
