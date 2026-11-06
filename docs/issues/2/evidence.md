# 驗證證據（2026-11-06）

## 範圍與環境

- 基線：6d6066ed908ff64b1df9ad00be4485c02812a8bb。
- 分支：issue-2-container-inspection。
- 本機 Python：/usr/bin/python3（3.14）；Linux，受限制的執行環境。
- 未啟停容器、部署服務或修改主機設定。安裝／移除測試只操作臨時 HOME。

## 紅燈

- 新增 Counter/Sampling 測試首次執行因 container_probe.py 尚不存在而失敗。
- UI 資料層新增 4 個測試首次執行因 latest_containers/container_detail 尚不存在而失敗。
- 後續以實際 helper、shell 與資料解析實作通過相同斷言。

## 綠燈與限制

命令：`FREEZE_WATCH_SKIP_GUI_TESTS=1 FREEZE_WATCH_SKIP_SYSTEMD_VERIFY=1 bash scripts/check.sh`

結果：exit 0；68 tests，60 通過，8 GUI tests 明確 skipped；後續安裝、升級設定保留、雙 project 設定、移除、主機訊號、kernel fixture、事故與 flush 的 shell 整合檢查通過。完整輸出：[artifacts/check-portable.log](artifacts/check-portable.log)。

- `git diff --check` 通過。
- 新增 helper 測試實際執行 Python 主程式 TSV 序列化、主機 Bash loop 與失敗替身，不只比對文字。
- 卡住 60 秒的 helper 替身被外層 timeout 終止；測試要求 11 秒內完成並確認 host metrics 落盤。
- 80 容器 fixture，10 輪最多 32 overview／8 deep，80 容器均取得 deep 查詢；程序最多 15。
- 原始 bytes 多裝置加總、實際時間差、重建／重啟／重置／缺值／逆時、未知 accounting、私有 cache、空快照、失敗快照、遠端 endpoint 拒絕、中文 JSON TSV roundtrip 均有測試。
- UI 資料層驗證不讀未來主機樣本、主機缺口、舊檔附加欄位、缺值與警示判準。

## 未執行／受阻驗證

- 未跑真實 runwukong／runtelenexus 負載：目前 sandbox 無權連接 Docker Unix socket；helper 實際執行回傳 unavailable。fixture 的 6／8 秒預算不能替代真實採樣成本量測。
- GTK：原始 scripts/check.sh 與 Xvfb 路徑均在建立 Gtk.Label 時 segmentation fault。最小重現 `GDK_BACKEND=x11 GSK_RENDERER=cairo xvfb-run -a /usr/bin/python3 -c 'import gi; gi.require_version("Gtk","4.0"); from gi.repository import Gtk; print(Gtk.init_check(),flush=True); Gtk.Label(label="test")'`：init_check True，建立 Label 時崩潰。因此沒有視覺 QA 證據，新容器 widget 測試保留給正常桌面／CI 執行。
- systemd-analyze --user verify 受 sandbox socket 限制失敗；未以忽略錯誤假冒通過，使用明確跳過旗標另跑可執行檢查。
- Memoria recall 無相關命中；共享資料庫只讀，feedback 寫入受限。本地文件保存本次決策與理由。

## 驗收對照

| 驗收 | 證據與目前結論 |
|---|---|
| AC1 | 雙 project 安裝設定、原單 project／升級保留、ID／label fixture、輪替公平測試通過 |
| AC2 | 欄位／未知資料與 OOM、health、重啟警示測試通過；widget 真實呈現待驗 |
| AC3 | CounterTests、RecoveryRegressionTests 與 FailureAndLimitTests 差分／重置／JSON／欄位測試通過 |
| AC4 | 程序 union 上限、D 保留、僅必要欄位、失敗原因與 CPU 口徑資料層通過；真實容器／widget 待驗 |
| AC5 | TSV 相容、已存樣本選擇邏輯與主機前向禁止／缺口測試；重啟後真實視覺操作待驗。只提供匹配檔案尾端可用歷史，跨輪替／壓縮讀取不在此實作承諾內 |
| AC6 | 已知異常才警示，未知不自動正常，時間與相關非因果文字；視覺 QA 待驗 |
| AC7 | 真實 shell helper 失敗／硬逾時仍保存 host metrics，查詢數與程序上限測試通過；真實負載成本待驗 |
| AC8 | 舊檔讀取、同一 docker TSV 輪替／維護路徑、JSON 及臨時 HOME 安裝移除檢查通過 |

## 精煉與影響

code-simplify 檢查：保留原始 11 欄位置與現有 UI 方法相容呼叫；程序選擇／欄位解析集中 helper，詳情文字由同一 formatter 供新舊樣本使用。未引入第三方依賴、通用框架或重複的歷史儲存層。

GitNexus：refresh、container_signature、_append_container_row 為 HIGH，影響 UI 開啟／refresh／事故切換；read_tsv_path 為 CRITICAL（4 direct、6 flows），僅增加有預設值的 byte_limit 參數，保留原有讀取行為。Bash 與新增 helper 符號未被索引，風險 UNKNOWN，已使用 shell／單元測試補足。提交前執行 detect_changes，結果另見本次工具紀錄；不把索引缺失解讀為無風險。

## 提交方式與受阻狀態

本機 .git/index.lock 因唯讀檔案系統無法建立，未產生本地提交。GitHub create_tree 工具同樣回覆 `MCP tool call requires approval, but approval policy is never`；沒有建立 tree、遠端 commit、branch 或 PR。HEAD SHA 不存在，不得稱為已提交或等待合併。

原始碼與證據保留在工作區；以逐檔 Git blob manifest 固定未提交的交付範圍供獨立審查。不含 investigations/。後續需要可寫 Git／GitHub 環境才能完成提交與 PR。

## 獨立審查修正

初次報告 [review.md](review.md) 的 R1、R2、R3 與 S1 已處理：

- GET all=1，保留所有 running 與選定 project 的已退出容器；先 inspect 保存 OOM／重啟／狀態，再決定是否查 stats/top。已停止不顯示假即時負載，running count 維持原語意。
- Docker 全體失聯、個別 stats 缺失、helper failure／硬逾時、cache 寫入失敗及 collector 重啟都使對應差分基線失效；恢復首筆未知。
- CPU 要求非空匹配 StartedAt／ID、前進時間、正核心數與有效前筆 counter；毀損 cache entry 可恢復。
- 回歸測試先取得 6 個失敗斷言（含 CPU 三個 subtests），修正後同組通過。紅燈與綠燈輸出保存在 artifacts/recovery-red.log、artifacts/recovery-green.log。
- 如實記錄兩條提交途徑受阻；未虛構任何 SHA 或 PR。

最後 UI 未知 CPU 的摘要文字改為「未知」，以 py_compile 與 29 個 dashboard 資料層測試重驗；GUI 仍未驗證，不沿用不存在的視覺證據。

第二輪 [review-followup.md](review-followup.md) 新增 R4：deep 優先項插入 overview 再截斷會永久漏採樣部分 exited/OOM 容器。新增64混合狀態20輪測試，修正前確實失敗；改持久游標走訪整體排序清單後轉綠，仍維持每輪32 overview／8 deep上限。另保留80全running公平性測試。證據 artifacts/rotation-red.log。
