# Issue 2 — 容器內部監控與當機前歷史對照

## 概述

來源：[GitHub issue 2](https://github.com/raybird/sys-monitor/issues/2)。

這個 issue 讓 Freeze Watch 同時深度觀測多個 Compose project（優先是 `runwukong`、`runtelenexus`），並保存以下資料，讓使用者事後能判斷主機凍結前，容器是否有運算負載、磁碟活動或程序異常：

- 容器的 CPU、記憶體、block I/O、程序與 OOM／重啟／health。
- 每筆容器樣本對齊到當時的主機溫度與 PSI。

採樣決策：

- 使用 Docker 本機 Unix socket 的唯讀 Engine API 取得原始 bytes，不拿 Docker CLI 的顯示用字串做差分。
- 預設每 3 個主機樣本查詢一次。
- 時間上限：helper 協作預算 6 秒，外層硬上限 8 秒。
- 數量上限：最多 32 個容器；每次 8 個深度容器；每個容器最多 15 個程序（CPU、記憶體、D 各取前 5）。
- 遠端 Docker endpoint 不做主機程序歸因。

## 文件清單

- [implementation-plan.md](implementation-plan.md)
- [驗證證據](evidence.md)
- 審查報告：[review.md](review.md)、[review-followup.md](review-followup.md)、[review-final.md](review-final.md)（前次 session，未提交的工作區快照）、[review-1e33e63.md](review-1e33e63.md)

不建立 requirement-analysis.md 與 technical-analysis.md：分級是 Medium。

## 關鍵差異

| 項目 | 變更前 | 變更後 |
|---|---|---|
| 深度觀測 | 單一 Compose project，透過 docker CLI | 多個 project，透過唯讀 Engine API，有時間與數量上限 |
| 磁碟活動 | 無 | 原始 block I/O bytes，以及依實際時間差計算的速率 |
| 程序 | 只有數量 | CPU／記憶體／D 前列程序，只保存必要欄位 |
| 歷史對照 | 無 | 選擇已保存的容器樣本，對齊此前 45 秒內的主機溫度與 PSI |
| 容器警示 | 重啟次數大於 0 就警示 | 只警示追蹤中的專案；重啟要比前一筆採樣增加才算；D 沿用主機門檻 |

## 涉及檔案

- `src/container_probe.py`：新增的標準庫採樣 helper。
- `src/freeze-monitor`：呼叫 helper、外層逾時、TSV 欄位、容器異常事件。
- `src/freeze_watch.py`：容器清單、詳情、歷史對照與警示樣式。
- `install.sh`、`uninstall.sh`、`scripts/check.sh`：部署、移除、驗證入口。
- `tests/test_container_probe.py`、`tests/test_freeze_watch.py`、`tests/test_window_layout.py`。
- `README.md`、`README.zh-TW.md`、`docs/architecture.md`：使用說明與收集格式。

既有的 `investigations/` 不納入交付。

## Gherkin 驗收劇本

```gherkin
Feature: 容器內部負載與當機前歷史對照

  @SCN-001
  Scenario: 同時深度監控多個 Compose project
    Given 設定追蹤 runwukong 與 runtelenexus，或沿用舊版的單一 project 設定
    When 收集器採樣容器
    Then 每列記錄容器 ID、Compose project 與 service
    And 兩個 project 的容器都能取得深度樣本
    And 升級後保留原本的單一 project 設定

  @SCN-002
  Scenario: 容器狀態欄位與未知值
    Given 追蹤中的容器正在執行，或已經退出
    When 使用者在儀表板展開該容器
    Then 顯示 CPU、記憶體用量與上限、tasks 與程序數、重啟次數、OOM、health
    And 沒有 healthcheck 時顯示不適用，取不到的值顯示未知，不顯示成 0 或正常
    And 已退出的容器保留 OOM、重啟與狀態，即時負載顯示未知

  @SCN-003
  Scenario: 磁碟讀寫 bytes 與速率不產生假數值
    Given 同一容器的前後兩次採樣
    When 計算讀寫速率
    Then 以原始累計 bytes 的差除以實際時間差
    And 首次採樣、容器重建、重啟、計數器下降、缺值、時間不前進或查詢失敗之後，速率為未知，不為負值
    And 說明 block I/O 不等同所有檔案讀取

  @SCN-004
  Scenario: 展開容器程序
    Given 正在執行的追蹤容器取得深度樣本
    When 使用者展開該容器
    Then 列出 CPU、記憶體與 D 狀態前列的程序，最多 15 筆，含名稱、主機 PID、狀態與採樣時間
    And 標明程序 CPU 是 ps 的生命週期平均，剛突然升高的長壽程序可能排不進前 5
    And 讀不到程序時顯示原因

  @SCN-005
  Scenario: 重啟後回看中斷前的容器樣本
    Given 收集器非正常結束後重新啟動
    When 使用者在儀表板選擇該事故並展開容器
    Then 顯示事故前最後落盤的容器樣本，不顯示事故之後的資料
    And 每筆已保存樣本對齊此前 45 秒內的主機溫度與 I/O／RAM PSI，沒有對應時標示缺口
    And 顯示最後容器採樣時間，落後主機樣本超過 60 秒時標示資料過期或缺口

  @SCN-006
  Scenario: 已知異常醒目且判準可解釋
    Given 追蹤中的容器出現 OOM、unhealthy、Z 大於 0、比前一次採樣新增的重啟，或 D 狀態程序至少 4 個
    When 儀表板顯示容器清單
    Then 該列以醒目色標示，tooltip 說明判準
    And D 至少 8 個或其他異常時，收集器寫入一筆 Docker anomaly 事件
    And 文字說明高負載與事故時間重疊只是線索，不代表因果

  @SCN-007
  Scenario: 不警示未追蹤容器、舊的重啟次數與 D 波動
    Given 未追蹤的容器出現 OOM，或追蹤中的容器重啟次數與前一次採樣相同，或 D 數在門檻之上波動
    When 收集器與儀表板判定警示
    Then 未追蹤的容器不警示
    And 沒有新增重啟時不因累計重啟次數警示，收集器重啟後的第一次採樣也不警示
    And D 數改變但異常集合不變時，不重複寫入事件

  @SCN-008
  Scenario: Docker 失效時主機監控照常運作
    Given Docker socket 不存在、無權限、是遠端 endpoint、回應卡住或逾時
    When 收集器採樣
    Then 主機樣本照常落盤，容器樣本明確標示不可用，不沿用舊的容器快照
    And 只使用唯讀 GET 查詢，不提權、不進入或修改容器
    And 單次查詢受容器數、程序數與時間上限約束

  @SCN-009
  Scenario: 舊檔相容與最少必要欄位
    Given 舊版 11 欄的 docker TSV，以及既有的輪替與清理機制
    When 儀表板讀取，或維護程式輪替清理
    Then 舊列可以載入，新欄位顯示未知
    And 新資料沿用同一份 docker TSV 的輪替與保留
    And 程序只保存 pid、狀態、CPU、記憶體與名稱，不保存 argv、環境變數或容器 log
```

## Gherkin 核准紀錄

- **核准 commit**: 0903fe7
- **核准來源**：
  - SCN-006、SCN-007：使用者 2026-11-06 回覆「照你的建議處理 D1、M3、S3、S7」，接受 [review-1e33e63.md](review-1e33e63.md) S3 的建議：重啟改成增量判斷；D 沿用主機門檻 4／8；未追蹤容器不警示。
  - SCN-001～005、008、009：由 issue #2 的 AC1–AC8 轉寫。使用者 2026-11-06 回覆「1. 核准」，確認轉寫正確並核准（TBD-1）。

| Scenario | 核准日期 | 狀態 |
|---|---|---|
| SCN-001 | 2026-11-06 | 已核准 |
| SCN-002 | 2026-11-06 | 已核准 |
| SCN-003 | 2026-11-06 | 已核准 |
| SCN-004 | 2026-11-06 | 已核准 |
| SCN-005 | 2026-11-06 | 已核准 |
| SCN-006 | 2026-11-06 | 已核准 |
| SCN-007 | 2026-11-06 | 已核准 |
| SCN-008 | 2026-11-06 | 已核准 |
| SCN-009 | 2026-11-06 | 已核准 |

## 風險與首要驗證

- **最大風險**：採樣本身拖慢主機，或 Docker 卡住時拖垮主機監控。
- **風險等級與理由**：Medium。主機凍結診斷是這個工具的核心；如果監控本身造成負擔，會干擾它要診斷的現象。但影響只限使用者層級、可以回復，不涉及資料損失或權限。
- **首要驗證**：失敗注入測試，包括 helper 卡住 60 秒、Docker 不可用、遠端 endpoint、慢速 socket；再加上真實 Docker 唯讀量測。
- **選擇理由**：最壞情況的上限可以用失敗注入直接證明。平常的耗時要量真實 socket，fixture 無法代表。
- **完成證據**：
  - 卡住的 helper 在 11 秒內被終止，主機樣本照常落盤。
  - 真實閒置狀態 8 個容器的採樣耗時 0.21 秒。
  - 高負載下的成本已豁免，見 Gate 豁免紀錄。

## 待確認事項

| 編號 | 事項 | 狀態 | 影響 |
|---|---|---|---|
| TBD-1 | SCN-001～005、008、009 是否如實轉寫 issue #2 的 AC1–AC8 並核准 | 已解決（2026-11-06）：使用者回覆「1. 核准」 | SCN-001～005、008、009 |
| TBD-2 | D1：PR #3 與 project.md「不建立 PR」衝突 | 已解決（2026-11-06）：使用者照審查建議，整合 main 後改走本地獨立審查，PR #3 保留為參考。見 Gate 豁免紀錄 | 交付方式 |
| TBD-3 | M3：高負載採樣成本、視覺 QA、跨重啟回看未驗證 | 已解決（2026-11-06）：視覺 QA 與跨重啟回看已在 xvfb 下補做（[evidence.md](evidence.md)）；高負載成本豁免，合併後以等待外部驗收窗觀察 | SCN-002、005、008 |
| TBD-4 | S3：容器警示門檻與事件雜訊 | 已解決（2026-11-06）：重啟改增量判斷；D 門檻 4／8；未追蹤容器不警示。轉為 SCN-006、SCN-007 | SCN-006、007 |
| TBD-5 | S7：程序 CPU 用生命週期平均排序 | 不影響本次交付（2026-11-06）：使用者接受此限制並寫入文件（SCN-004）。追蹤：[#4](https://github.com/raybird/sys-monitor/issues/4) | SCN-004 |
| TBD-6 | 審查發現 S2、S4、S5、S6、S8、S9 與 N1～N8 是否在本 issue 修正 | 已解決（2026-11-06）：使用者回覆「2. 一起修」，全部在本 issue 修正，見 implementation-plan.md 步驟 7 | S5 影響 SCN-002、006 的未知呈現；S6 影響 SCN-005 的回看範圍；S2 影響 SCN-003 的速率分母 |

## Gate 豁免紀錄

| 日期 | 豁免項目 | 使用者原話 | 殘餘風險 |
|---|---|---|---|
| 2026-11-06 | 不以 PR #3 做交付審查，改依 project.md 由獨立 reviewer 在本地審查 | 照你的建議處理 D1、M3、S3、S7 | 合併沒有平台審查紀錄；PR #3 上的審查留言只對應 1e33e63 |
| 2026-11-06 | 不量測真實高負載下的採樣成本 | 照你的建議處理 D1、M3、S3、S7 | 高負載時 helper 的實際耗時未知。目前只有閒置 8 個容器實測 0.21 秒；外層 8 秒硬上限保護主機採樣。合併後在下一次 runwukong／runtelenexus 高負載時段，觀察容器樣本是否出現 unavailable 或逾時 |

## Timeline

| 日期 | 異動 | 負責人 |
|---|---|---|
| 2026-11-06 | 前次 session 建立 issue 文件與實作，推送 1e33e63 並開 Draft PR #3 | - |
| 2026-11-06 | 獨立審查 1e33e63，判定 RETURN TO execute-task（[review-1e33e63.md](review-1e33e63.md)） | - |
| 2026-11-06 | 使用者照審查建議決定 D1、M3、S3、S7。整合 main；文件移到 issue-2 並改用 Medium 範本；S3 規格修訂為 SCN-006、SCN-007；開 #4 追蹤 S7 | - |
| 2026-11-06 | 使用者核准全部 Scenario，並決定審查建議 S2、S4、S5、S6、S8、S9、N1～N8 一起修 | - |

---
**建立日期**: 2026-11-06  
**分級**: Medium  
**風險**: Medium\
**狀態**: 待獨立審查
