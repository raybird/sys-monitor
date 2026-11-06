# Issue #2：容器內部監控

- **分級**：Medium
- **風險**：中；採樣額外負擔、資料缺口誤讀、容器重建串錯。
- **狀態**：實作與獨立審查修正已完成；外部驗證與提交受阻
- **日期**：2026-11-06
- **需求**：https://github.com/raybird/sys-monitor/issues/2
- **核准來源**：使用者於本次對話同意以 Issue #2 AC1–AC8 為範圍，採「本地計畫 → 實作與驗證 → 提交 PR → 獨立審查 → 等待使用者合併」。本次免用缺少的 docs/AGENTS.md 流程契約；不代表補造共用流程規則。
- **任務唯一來源**：[implementation-plan.md](implementation-plan.md)

## 驗收

AC1：同時深度監控多個 Compose project，容器 ID、project/service 識別及單專案相容。
AC2：CPU、記憶體／上限、tasks／程序、重啟、OOM、health，未知與不適用明確。
AC3：原始 block I/O bytes 與按實際時間差計算的速率；重建、重啟、重置、缺值與首次採樣不產生假速率。
AC4：展開 CPU／記憶體前列與 D-state 程序，含名稱、主機 PID、狀態、時間與 CPU 統計口徑；失敗有原因。
AC5：持久化樣本與主機溫度／PSI 時間對照，事故後可回看，資料缺口與最後採樣明確。
AC6：異常醒目且判準可解釋，未知不視為正常；不宣稱當機因果。
AC7：主機唯讀查詢，有採樣／程序／容器數與時間預算，不提權、不改容器，不阻斷主機監控。
AC8：舊檔相容、沿用輪替保留，僅存必要程序欄位，不保存 argv、環境或容器 logs。

## 範圍與限制

涉及 src/freeze-monitor、src/freeze_watch.py、新增標準庫採樣 helper、install.sh、tests、使用／架構文件。既有 investigations/ 不納入交付。

採樣決策：使用 Docker 本機 Unix socket 的唯讀 Engine API 取得精確 bytes，原始 Docker CLI 的顯示用字串不作差分。預設每三個主機樣本查詢一次；整次 helper 最多 6 秒，外層硬上限 8 秒；最多 32 容器、每次 8 個深度容器、每容器最多 15 個程序（CPU／記憶體／D 各 5）。deep 超額以時間桶輪替；overview 以持久游標分配剩餘名額，避免已退出容器被永久擠出。缺值顯示原因。遠端 Docker endpoint 不做主機程序歸因。

## 待確認與未執行

- 真實兩組容器下的效能量測與人工桌面觀測依環境權限執行；不得以 fixture 通過代替真實主機證據。
- 不啟停容器、不壓測、不部署或調整主機／容器資源限制。
- 預算先以有界查詢與失敗注入驗證，真實負載若不可達，交付保留為 draft 並揭露。
