# Issue 1 — 改善當機紀錄選單對比與診斷可靠性

## 概述

來源：[GitHub issue 1](https://github.com/raybird/sys-monitor/issues/1)。修正選單可讀性、輪替後的取樣定位與非正常關機的證據表達，並規劃可選 GPU 活動紀錄及診斷匯出。

## 文件清單

- [需求現況](requirement-analysis.md)
- [實作與驗證計畫](implementation-plan.md)

未建立 technical-analysis.md：前三項沿用既有架構，尚未出現需要比較的替代方案；GPU 與匯出範圍待確認後再評估。

## 關鍵差異

| 項目 | 變更前 | 目標 |
|---|---|---|
| 選單 | 背景可能被系統主題覆蓋 | 亮暗主題各狀態均可讀 |
| 前次 session | 只讀 START 的 metrics | 使用同一 session 最新有效取樣 |
| 非正常關機 | 直接記 FREEZE、顯示凍結 | 顯示非正常關機／疑似當機及不確定性 |

## 涉及檔案

- src/freeze-monitor：前次 session 判讀與 GPU 採樣整合。
- src/freeze_watch.py：選單、事件回顧與匯出預覽。
- tests/：收集器重現、資料與 GTK 驗證。
- scripts/check.sh：既有整合判準與必要新測試入口。
- install.sh：僅 GPU 紀錄需要額外程式時調整部署。
- README.md、README.zh-TW.md、docs/architecture.md、docs/troubleshooting.md：功能與診斷語意。
- docs/AGENTS.md、docs/agents/、docs/_templates/、docs/.dev-rules-kit.json：本次核准的流程初始化。

## Gherkin 驗收劇本

```gherkin
Feature: 可讀且保留不確定性的當機診斷

  @SCN-001
  Scenario: 亮暗主題均可讀取事件選單
    Given 系統使用亮色或暗色 GTK 主題
    When 開啟事件選單並檢視正常、滑鼠停留與選取狀態
    Then 每種狀態的文字與圖示均可辨識

  @SCN-002
  Scenario: 多次跨日輪替後非正常結束
    Given 同一 session 跨日輪替多次且未記錄 STOP
    When 新的收集器判讀前次 session
    Then metrics 與 last_sample 指向最新有效取樣
    And silent_for 使用該取樣計算
    And 事件回顧使用結束前的資料並可跨輪替讀取

  @SCN-003
  Scenario: 輪替檔案不可用與正常結束
    Given 最後輪替檔為空、缺失或沒有有效取樣
    When 判讀前次 session
    Then 使用同一 session 較早的有效取樣或明確顯示 unknown
    And 不使用其他 session 的資料
    And 已記錄 STOP 的 session 不產生非正常結束事件

  @SCN-004
  Scenario: 非正常關機不足以確認當機原因
    Given 前次 session 缺少 STOP 且 boot id 改變
    When 顯示新事件或歷史 FREEZE 事件
    Then 以非正常關機或疑似當機呈現
    And 保留最後取樣與核心證據而不斷言硬體或 GPU 故障
    And 同一 boot 的收集器中斷仍區分為 INTERRUPTED

  @SCN-005
  Scenario: 可選 DRM fdinfo 程序與引擎活動紀錄
    Given 使用者開啟 GPU 程序紀錄
    When 取樣可存取的 GPU 程序與引擎
    Then 區分裝置持有者與取樣期間的實際活動
    And 權限不足、不支援計數器或程序退出不影響基本監測
    And 限制取樣成本
    And 不支援的驅動明確標示而不冒充零活動

  @SCN-006
  Scenario: 預覽後匯出診斷報告
    Given 使用者選取事件
    When 預覽並匯出報告
    Then 純文字報告包含事件前 30 分鐘與後 5 分鐘的溫度與 CPU、記憶體、I/O 壓力及相關核心錯誤
    And 預覽與匯出內容一致
    And 預設避免包含敏感路徑與程序參數
```

## Gherkin 核准紀錄

- **核准 commit**: c62159c02638e439f00a254d97dafe449b25f296
- **核准來源**: GitHub issue 1 的改善與驗收方向；使用者於 2026-10-05 指示「繼續」。同日回覆「先支援 Linux DRM fdinfo（AMD／Intel 等），不支援的驅動明確標示」與「採用這個範圍與格式」，核准純文字預覽與事件前 30 分鐘／後 5 分鐘、預設移除路徑與程序參數。

| Scenario | 核准日期 | 狀態 |
|---|---|---|
| SCN-001 | 2026-10-05 | 已核准 |
| SCN-002 | 2026-10-05 | 已核准 |
| SCN-003 | 2026-10-05 | 已核准 |
| SCN-004 | 2026-10-05 | 已核准 |
| SCN-005 | 2026-10-05 | 已核准 |
| SCN-006 | 2026-10-05 | 已核准 |

## 風險與首要驗證

- **最大風險**：錯讀前次 session 的舊取樣，或把非正常關機誤解為已確認硬體故障；後續匯出有敏感資訊外洩風險。
- **風險等級與理由**：High — 報告涉及敏感路徑與程序參數；核心診斷亦需避免錯誤因果推論。
- **首要驗證**：先建立 session／輪替的隔離 fixture 重現錯讀；匯出規格核准後先以含敏感資訊的已知樣本驗證預覽遮蔽。
- **選擇理由**：直接對比正確取樣檔、時間與敏感資訊字面值，比端到端猜測更能定位風險。
- **完成證據**：錯讀案例先紅後綠，STOP、同 boot、多次輪替與缺失檔均通過；匯出敏感樣本在預覽與檔案均不可見。

## 待確認事項

| 編號 | 事項 | 狀態 | 影響 |
|---|---|---|---|
| TBD-1 | GPU 支援範圍 | 已解決 | 2026-10-05 使用者核准 DRM fdinfo；其他驅動標示不支援 |
| TBD-2 | 匯出格式與區間 | 已解決 | 2026-10-05 使用者核准純文字預覽、前 30 分鐘／後 5 分鐘、預設遮蔽 |

## 實作證據

2026-10-07：任務與驗收證據見 [實作計畫](implementation-plan.md) 與 [驗證紀錄](evidence/README.md)。獨立審查尚未執行。

## Gate 豁免紀錄

| 日期 | 豁免項目 | 使用者原話 | 殘餘風險 |
|---|---|---|---|
| 2026-11-04 | 建立 PR 與 PR 證據（Proof of Test 改由本地審查報告承載） | 「這專案可以不走 pr 再本地直接審查」 | 沒有平台上的審查紀錄與 CI；審查範圍與結論只保存在本地的 review 報告與 Git 歷史 |

## Timeline

| 日期 | 異動 | 負責人 |
|---|---|---|
| 2026-10-05 | 使用者「繼續」核准執行已列出的流程初始化；建立規格並依既有需求核准 SCN-001 至 SCN-004 | 使用者／開發助理 |
| 2026-10-05 | 核准 SCN-005／SCN-006 的驅動範圍與報告格式、區間 | 使用者 |
| 2026-11-04 | 豁免建立 PR，改為本地獨立審查 | 使用者 |

---
**建立日期**: 2026-10-05
**分級**: Large — 跨 Bash 收集與 GTK 資料呈現，另有 GPU 採樣與報告功能
**風險**: High
**狀態**: 待本地獨立審查
