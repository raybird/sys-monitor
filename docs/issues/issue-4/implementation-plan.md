# 實作計畫

核准、範圍與風險以 [README.md](README.md) 為準。

## 實作步驟

1. ⏳ **helper 計算區間 CPU**（SCN-001～004）
   - 內容：
     - `src/container_probe.py` 讀深度容器每個程序的 `/proc/<pid>/stat`，取 utime、stime、starttime。
     - 用 `docker-counters.json` 裡前一次的資料（pid、starttime、ticks、讀取時間）計算 `cpu_interval`。
     - 套用每容器 1024 個、0.2 秒的上限；`/proc` 根目錄可由測試替換。
   - 驗證：假 `/proc` 目錄的單元測試，期望值手算，先紅後綠。涵蓋區間值、首次採樣、PID 重用、新程序、超過數量、超過時間、權限不足。
   - 完成判準：SCN-001～004 的 helper 端行為都有測試；既有 `process_sample` 測試不變且通過。
2. ⏳ **保存與相容**（SCN-005，依賴 1）
   - 內容：`cpu_interval` 寫入 `process_sample` JSON；cache 只保留本輪深度容器中仍存在的程序。
   - 驗證：舊格式 TSV 的讀取測試；cache 內容的測試。
   - 完成判準：TSV 欄位不變；舊紀錄顯示不變；cache 不保留已結束的程序。
3. ⏳ **儀表板顯示**（SCN-001、002、004、005，依賴 1、2）
   - 內容：`src/freeze_watch.py` 容器詳情的程序列改為「CPU 區間 x%（平均 y%）」，並依情況顯示排序說明與退回原因。
   - 驗證：`container_detail` 的資料層測試，涵蓋區間值、未知、超過預算、無法讀取、舊紀錄。
   - 完成判準：各狀態的文字都有斷言。
4. ⏳ **真實對照組與文件**（全部 Scenario，依賴 1～3）
   - 內容：
     - 用已知負載的程序做對照組。在容器內啟動程序前，先取得使用者同意。
     - 更新 `README.md`、`README.zh-TW.md`、`docs/architecture.md` 的口徑說明。
   - 驗證：對照組的區間 CPU 接近預期；`env -u DISPLAY -u WAYLAND_DISPLAY bash scripts/check.sh` 全過、沒有跳過。
   - 完成判準：對照組數值、查詢方式與文件更新都記錄在本檔或 evidence.md。
5. 📝 **交付**（全部 Scenario，依賴 1～4）
   - 本地獨立審查，報告存於本目錄；通過後依使用者指示合併。
