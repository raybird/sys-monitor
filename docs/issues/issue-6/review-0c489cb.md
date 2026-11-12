# Issue #6 獨立審查報告

- 審查日期：2026-11-12
- 範圍：本機完整交付 diff，`origin/main` merge-base 至被審查提交；專案規範不建立 PR。
- Reviewed BASE SHA：`f76a4c945d2405f66bb60284d7a75e80f7339254`
- Reviewed HEAD SHA：`0c489cbdf3ef2fa8c40a9086016643d6cce6b4f1`
- Reviewed patch-id：`3a748b81af7e1258609dbe4a9b97a4d1fdcefb10`
- 核准基線 SHA：`0c489cbdf3ef2fa8c40a9086016643d6cce6b4f1`；`**核准 commit**` 仍為「待提交」，依 `git log -G` 核准來源欄位推得。
- 獨立 reviewer：`/root/issue6_review`，與原實作者 `/root` 分離。
- Review artifact：`docs/issues/issue-6/review-0c489cb.md`

## 問題與風險

1. **MUST FIX｜SCN-003 核心零命中可能是假綠燈。** `src/freeze_watch.py:496-501` 只憑 `START kernel=ok` 且報告範圍內沒有 `KERNEL` event，輸出「核心紀錄：可讀，未命中」。該欄位由 `src/freeze-monitor:619-632` 的啟動時可讀檢查寫入；真正掃描每 30 個主機樣本才執行，事故前數分鐘可能尚未掃描。`src/freeze-monitor:774-776` 的 `--after-cursor` 命令失敗也會被 process substitution／`|| true` 吞掉，不會改為不可讀。因此「未命中」可能只是沒有查過或查詢失敗。請保存最近一次成功掃描與覆蓋範圍，或把無法證實的狀態表為「可讀性已確認；是否有異常未知」，並加入掃描失敗與未掃描窗口的測試。
2. **MUST FIX｜SCN-001 無有效列時無法區分損壞與缺資料。** `src/freeze_watch.py:119-143` 遇到只有標頭與 NUL／截斷列的檔案會回傳 `[]`，`sample_freshness` 因而只能顯示「資料缺失」，損壞訊號遺失。用系統 Python 建立標頭加 `b'2026-11-12T08:00:00+08:00\t\x00\x00\n'` 的 TSV 實測，`read_tsv_path(...) == []`，與純標頭檔相同。請在零有效列時也保留損壞狀態，並以對照測試區分兩者。
3. **MUST FIX｜文件狀態互相矛盾。** `docs/issues/issue-6/README.md:6` 仍稱產品行為「待核准草案，尚未開始實作」，同檔核准表卻列三項已核准，metadata 表示實作與驗證完成。這會誤導後續 dev-cycle 偵測與審查；請更新概述為目前真實狀態。
4. **SHOULD FIX｜GUI 驗收證據較窄。** `tests/test_freeze_watch.py:101` 測到 `sample_freshness` 的文字，但未斷言 `FreezeWatch.refresh` 實際讓即時畫面顯示過期、恢復後消失、回顧畫面不誤報。既有 21 項 GUI 測試檢查版面與主題，對此新互動沒有直接保護。建議加入至少一個畫面層級對照測試；這是證據持久力與整合覆蓋建議，不將現有測試稱為假綠燈。

## 已查核維度

- 驗收與核准：`docs/issues/issue-6/README.md` 有 SCN-001～003 與 2026-11-12 使用者「依照建議核准」來源；核准表集合完整。上述三個 MUST FIX 使 SCN-001、SCN-003 目前未通過；SCN-002 的 60／61 秒邊界有固定時間測試。
- 測試證據：`docs/issues/issue-6/implementation-plan.md` 記錄紅燈與綠燈、`FREEZE_WATCH_SKIP_GUI_TESTS=1 ./scripts/check.sh` 沙箱外通過（153 項、14 略過），以及 Xvfb 下 `tests.test_window_layout` 21 項通過。安裝／解除安裝檢查包含新增 VERSION 清理。這些結果可支持已涵蓋路徑；未涵蓋的損壞零有效列、未掃描／查詢失敗路徑不能由總數代替。
- 輸入與狀態失敗面：合法舊格式 24 欄與損壞尾列有測試；只有損壞列未涵蓋且實際丟失狀態。即時樣本 60／61 秒有測試；主機與容器一起停住時主機提示可見。核心啟動不可讀與可讀零 event 有測試，但測試把 `kernel=ok` 直接當成功完整掃描，未模擬真正掃描時序或失敗。
- 安全與權限：報告版本以有限字元集擷取，沒有輸出原始 journal 或程序名稱；沒有擴張權限。版本檔由安裝與解除安裝管理。架構變更侷限收集器、儀表板、安裝器、對應文件與測試。
- 品質：`read_tsv_path`、`read_tsv_before`、`metric_window` 各自實作有效列判斷，已有行為分歧風險；本輪主要問題是零有效列狀態遺失。建議修復時共用最小判準，避免舊版相容性再次分歧。
- 豁免與待確認：`TBD-1`、`TBD-2` 已記核准結論；沒有明列測試或 review 豁免。先前 GTK 全套曾 segfault，單獨 Xvfb GUI 套件通過；沙箱 socket `EPERM` 不計入產品失敗。

## 流程判定

**RETURN TO execute-task**。三項 MUST FIX 需修正並以新提交重新取得完整差異與獨立審查；此報告只對上述固定 HEAD 有效。
