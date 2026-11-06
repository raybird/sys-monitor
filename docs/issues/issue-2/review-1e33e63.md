# 審查報告

- 審查日期：2026-11-06
- 範圍：完整 PR（GitHub PR #3，Draft，Refs issue #2，分支 `issue-2-container-inspection`）。BASE 為 `git merge-base origin/main 1e33e63`
- Reviewed BASE SHA：`6d6066ed908ff64b1df9ad00be4485c02812a8bb`
- Reviewed HEAD SHA：`1e33e631685f92772fc4843d7046d921a0a71b0d`（等於 PR source HEAD，只有一個提交，22 個檔案，+1533／-135）
- Reviewed patch-id：`35d538f087c046ba6d0794daf9adbd6d0ed213cb`
- 獨立 reviewer：Claude Code 隔離 subagent（general-purpose），只讀 detached worktree，不是原實作者。流程面由協調者 session 查核
- Review artifact：`docs/issues/issue-2/review-1e33e63.md`（本機保存，尚未提交）；已貼到 PR：https://github.com/raybird/sys-monitor/pull/3#issuecomment-6676460259
- 核准基線：`1e33e631685f92772fc4843d7046d921a0a71b0d`
  - 依 acceptance.md 的 pattern，對 `docs/issues/2/README.md` 的 `**核准來源**` 欄位行推導。
  - 這個基線就是被審查提交本身：規格與實作在同一個提交首次進版，沒有更早的 Git 比對基線。
  - 核准來源只寫「使用者於本次對話同意」，無法追溯到原話與日期。

## 問題與風險

### MUST FIX

- **M1 與 main 衝突，無法合併**
  - `git merge-tree --write-tree origin/main 1e33e63` 顯示 5 個檔案有內容衝突：`install.sh`、`scripts/check.sh`、`src/freeze-monitor`、`src/freeze_watch.py`、`uninstall.sh`。
  - origin/main 已前進到 `bd56e94`，內含 issue #1 與 dev-rules-kit 流程導入。
  - 本報告審查的 HEAD 不是可交付版本。整合後要以新的 BASE／HEAD 重跑測試並重新審查，本次結論不能沿用到整合後的提交。

- **M2 issue 文件不符 main 的流程契約 2.4 與 project.md**
  - 分支從 `docs/AGENTS.md` 導入前的基線建立，被審查提交裡沒有這份檔案。整合進 main 後就受它約束，但目前：
    - 目錄是 `docs/issues/2/`，project.md 規定 `docs/issues/issue-2/`。
    - 分級 Medium、風險中，README 卻沒有 `## Gherkin 驗收劇本`、`## Gherkin 核准紀錄`、`**核准 commit**`；`**狀態**` 不是合法值（「實作與獨立審查修正已完成；外部驗證與提交受阻」）。
    - 「本次免用缺少的 docs/AGENTS.md 流程契約」是 gate 豁免，卻沒有記在 `## Gate 豁免紀錄`，也沒有使用者原話與日期。
  - 建議：整合時把文件移到 `docs/issues/issue-2/`，套用 Medium 範本，把 AC1–AC8 轉成 Gherkin，並向使用者取得可追溯的核准（原話與日期）。豁免照規格寫進 Gate 豁免紀錄。

- **M3 必要驗證未執行，也沒有豁免**
  - issue #2 步驟 4 要求「以代表性負載驗證採樣成本」「人工檢視 UI 與跨重啟回看」，至今仍未完成：
    - 真實高負載下的採樣成本：reviewer 只量了閒置狀態的 8 個容器，約 0.21 秒。
    - 亮暗主題的視覺 QA：project.md 本地 gate 要求涵蓋亮色與暗色。
    - 跨重啟回看的實際操作。
  - 沒有任何豁免紀錄，依 review-evidence.md 屬於必要驗收覆蓋缺口。
  - `需決策`：這三項要在合併前補做，還是逐項豁免並記錄殘餘風險？reviewer 建議：視覺 QA 與跨重啟回看在本機桌面補做（成本低）；高負載成本可以豁免，記入 Gate 豁免紀錄，並以「等待外部驗收窗」觀察下一次 runwukong／runtelenexus 高負載時段。

### SHOULD FIX

- **S1 issue 文件過時，與實際狀態矛盾**
  - 位置：`docs/issues/2/README.md:5`；`docs/issues/2/evidence.md`「提交方式與受阻狀態」「未執行／受阻驗證」兩段；`docs/issues/2/implementation-plan.md` 步驟 3、4 與「本次進度」。
  - 文件仍寫「沒有 commit 或 PR」「HEAD SHA 不存在」「GUI 會 segfault、沒有 widget 證據」。
  - 實際上 HEAD 已提交、PR 已存在；CI run 42153168060（headSha `1e33e63`，xvfb）跑了 68 個測試全部 OK、0 skip。
  - 建議：用實際 SHA、CI run 與真實採樣數據改寫。這不是誇大通過，所以不列為不實回報。

- **S2 速率分母用迴圈開頭的整數秒 epoch，不是實際讀取時間**
  - 位置：`src/container_probe.py:88`、`:218`。
  - AC3 要求按實際間隔計算。同一輪內各容器被讀的時間最多可偏移到 6 秒預算，容器多或主機負載高時誤差可能到 10–20%。
  - 建議：改用 stats 回應的 `read` 時間戳，或每次 GET 時取 `time.time()`。

- **S3 警示門檻與事件雜訊**（`需決策`）
  - 位置：`src/freeze-monitor:287-289`、`src/freeze_watch.py:666-668`。
  - 現況：
    - D>0 或 restart_count>0 就警示，範圍擴大到所有容器（包括未追蹤的 portainer）。舊版只警示 tracked 容器，這個行為改變沒有寫進文件。
    - 事件字串帶著 D 數，D 一變就會重複寫入 WARN，事件清單會被洗版。
    - 歷史重啟次數大於 0 的容器會永久顯示成 warm 色。
    - 主機端門檻是 D≥4 才 elevated、≥8 才 warn，容器端卻是 >0，兩邊口徑不一致。
  - 待決問題：
    1. 容器的 D 門檻要多少？
    2. 重啟要不要改成「跟上一筆比有增加才算」？
    3. 未追蹤容器要不要納入警示？
  - 建議：重啟改成增量判斷；D 沿用主機門檻，或至少不放進去重用的事件字串；未追蹤容器不警示。

- **S4 失敗原因全部歸成 `unavailable`**
  - 位置：`src/container_probe.py:148-150`。
  - socket 不存在、權限不足、遠端 endpoint、逾時都輸出同一個狀態。舊版的 `not_installed` 也被移除了，AC4、AC7 要的「失敗有原因」因此退化。
  - 建議：改成 `unavailable:<reason>`。

- **S5「未知」與正常同色**
  - 位置：`src/freeze_watch.py:1212-1213`。
  - `sample_status` 不是 ok（不可用、逾時、已停止）的列跟正常列一樣是 muted 色；記憶體欄直接顯示原始的「NA」。AC6 要求未知不能看起來像正常。
  - 建議：加上獨立樣式，NA 轉成「未知」。

- **S6 磁碟增量與歷史回看範圍沒有寫進預算**
  - 依真實資料推估：8 容器約 9.6 MB/天（舊格式約 1.5 MB/天），保留 14 天約 130 MB 以上。
  - UI 只讀尾端 2 MB（`src/freeze_watch.py:1558`、`:1566`），8 容器時約涵蓋 5 小時。GAP 事故如果發生在當天檔案較早的位置，會讀不到已經落盤的資料，與 AC5 的「事故後可回看」有落差。
  - 建議：在文件寫明磁碟預算與回看限制。GAP 回看要不要依 epoch 定位讀取，由使用者決定。

- **S7 程序「高 CPU 前 5」用 ps 的生命週期平均排序**（`需決策`）
  - 位置：`src/container_probe.py:104`、`:222`。
  - 口徑已有標示（`src/freeze_watch.py:648`），形式上符合 AC4。但長時間執行、此刻突然飆高的程序排不進前 5。
  - 待決問題：接受這個限制，或改用兩輪之間 `/proc/<pid>/stat` 的差分（需要另外設計預算）？
  - 建議：本次接受並寫進限制，差分另開 issue。

- **S8 內部 6 秒預算不是硬上限**
  - 位置：`src/container_probe.py:32-50`。
  - 只在每次請求前檢查 deadline。慢速回應的 socket（實驗：每 0.4 秒送 1 byte）40 秒後仍未結束，只靠外層 `timeout 8s` 終止，那一輪已採到的列也全部丟失。
  - 主機採樣最壞每 30 秒延遲約 9 秒，但不會停擺。
  - 建議：在 read 迴圈裡檢查 deadline，並保留部分結果。

- **S9 測試名稱與內容不符**
  - 位置：`tests/test_container_probe.py:168`。
  - `test_exact_fields_match_dashboard_and_shell_header` 只比對了 shell 表頭，沒有比對 `freeze_watch.DOCKER_FIELDS`。三處欄位目前一致，但缺少測試保護。
  - 建議：補上 `probe.FIELDS == freeze_watch.DOCKER_FIELDS`。

### NICE TO HAVE

- **N1 從檔案中段讀取時沒有丟掉不完整的首行**
  - 位置：`src/freeze_watch.py:101-113`（原本就有的行為）。
  - JSON 欄位會加 CSV 引號，首行如果從引號中間開始，會再吞掉一筆真資料（已重現：4 行解析成 3 筆）。
- **N2 浮點數沒有四捨五入**
  - 位置：`src/container_probe.py:216-217`。
  - 例如 `1950.4761904761904`，浪費空間，詳情畫面也直接顯示。
- **N3 deep 輪替用 `epoch//30` 時間桶**
  - 位置：`src/container_probe.py:162-163`。
  - 改用非預設間隔時可能出現週期性漏採，例如間隔 20 秒、剛好 16 個容器時，會有半數永遠輪不到 deep 採樣。
- **N4「不可用」空列由 Python 與 shell 各寫一份**
  - 位置：`src/container_probe.py:140-141`、`src/freeze-monitor:276`。
  - 欄位值有差異：is_tracked 一邊是 NA、一邊是 0；process_status 一邊是 NA、一邊是 unavailable。目前 UI 會過濾，行為上沒有差異。
- **N5 父類測試重複執行**
  - 位置：`tests/test_container_probe.py:183`。
  - `HardTimeoutTest` 繼承 `CollectorIntegrationTests`，父類的 2 個測試會重複跑。
- **N6 check.sh 會查本機真實 Docker**
  - check.sh 的 freeze-monitor 整合跑法會以唯讀 GET 查本機 Docker socket，結果受本機環境影響。
  - 建議：設 `DOCKER_HOST=unix:///nonexistent` 讓它封閉。
- **N7 計數口徑沒有寫進文件**
  - `hero_docker` 在 `:1462` 設定後，在 `:1583` 被覆寫。
  - 超過 32 容器或超過 8 個 tracked running 時，計數只涵蓋本輪樣本。
- **N8 清單重建會關掉下拉選單**
  - detail 文字一變就整個重建清單，打開中的下拉選單會被關掉。

### 流程決策（`需決策`）

- **D1 PR 與專案交付方式衝突**
  - project.md 與 2026-11-04 的使用者決定是：本專案不建立 PR，由本地獨立 reviewer 審查，報告存在 `docs/issues/issue-ID/`。PR #3 與此牴觸。
  - 待決問題：issue #2 要改走本地審查流程（關閉或保留 PR 只作參考），還是本次例外使用 PR？
  - 建議：整合 main 後沿用專案流程，在本地審查。PR 關閉或保留為參考，並在 Gate 豁免紀錄註明。

## 已查核維度

- **驗收與證據**

  | AC | 證據位置 | 結論 |
  |---|---|---|
  | AC1 | check.sh 雙 project／升級保留；fixture；reviewer 真實 helper 輸出（兩組專案都有 ID、project、service） | 通過 |
  | AC2 | fixture、RecoveryRegressionTests；真實 health 有 healthy 與 not_configured；CI 的 GUI 測試 | 大致通過；未知呈現（S5）；視覺 QA 未做（M3） |
  | AC3 | `io_rates` 單元測試（id、started、逆時、counter 下降、缺值）、collect 層基線失效、`artifacts/recovery-*.log` 紅綠燈 | 通過；分母口徑見 S2 |
  | AC4 | `process_sample` 上限 15、保留 D、最少欄位；真實 top 解析 | 通過；原因粗（S4）；CPU 口徑需決策（S7） |
  | AC5 | 不讀未來樣本與缺口標示的測試；GUI 選擇保留 | 部分通過：GAP 在檔案中段可能讀不到（S6）；跨重啟操作未驗（M3） |
  | AC6 | `container_warning` 測試、tooltip、非因果文字 | 部分通過（S3、S5） |
  | AC7 | 只用 GET；真實 shell 硬逾時測試（11 秒內）；80／64 容器上限 fixture；reviewer 真實量測 0.21 秒，失效時很快回 unavailable | 通過；內部預算非硬上限（S8）；高負載成本未量（M3） |
  | AC8 | 舊 11 欄檔案測試；沿用 docker-*.tsv 輪替；uninstall 會刪 probe；只用 comm，不讀 Health.Log、argv、env | 通過；磁碟增量沒有寫進預算（S6） |

  測試執行：

  | 環境 | 命令 | 結果 |
  |---|---|---|
  | reviewer 本機 | `env -u DISPLAY -u WAYLAND_DISPLAY bash scripts/check.sh`（xvfb） | exit 0，68 tests OK，0 skip，All checks passed |
  | reviewer 本機 | 帶壞掉的 DISPLAY 執行 | segfault；既有測試在同環境也失敗，判定為環境問題 |
  | CI | run 42153168060 | success，68 OK |

  假綠燈：未發現。S9 的測試名稱與內容不符，但斷言是真實比對，屬於證據持久力問題。

- **相關失敗面**

  | 情境 | 判定 |
  |---|---|
  | 首次、重建、重啟、counter 下降、缺值、時間逆行 | 單元測試覆蓋，OK |
  | 單一容器查詢失敗、Docker 失聯、helper 失敗或逾時、collector 重啟 | 基線失效有測試，OK |
  | helper 卡住 | 真實 shell 測試，OK |
  | 慢速 socket 回應 | 只靠外層 timeout（S8） |
  | 權限不足、socket 不存在、遠端 endpoint | 會回 unavailable，但原因遺失（S4） |
  | TSV 注入（tab、換行） | 先取代控制字元，有中文往返測試，OK；引號加部分首行有小問題（N1） |
  | 舊欄位 TSV | 有測試，OK |
  | 輪替、保留、uninstall | OK |
  | 多 project 與單 project 升級 | OK |
  | 歷史不讀未來樣本 | 有測試，OK |
  | 資料缺口 | 部分（S6） |
  | running 與 exited 混合輪替 | 64 混合、80 全 running fixture，OK；時間桶邊界見 N3 |

- **需求、架構、安全、品質**
  - 需求：AC 範圍沒有越界。採樣預算（每 3 個主機樣本、6／8 秒、32／8／15）是實作方自訂，issue #2 原本寫「先量測再定義」，屬於 M3 的一部分。
  - 架構：改成 stdlib-only 的 helper，透過 Unix socket 唯讀查詢，比多次 docker CLI fork 更有界。沒有第三方依賴。
  - 安全：只用 GET，不 exec、不讀 logs、argv、env；拒絕遠端 endpoint；cache 權限 0600。
  - 品質：跨檔重複沒有造成行為分歧（N4、S9）。`container_probe.py` 與測試檔的行很長、很密，與既有風格不一致，但不影響正確性。

- **豁免、待確認與限制**
  - README 宣稱的「免用流程契約」沒有寫進 Gate 豁免紀錄（M2）。
  - 實作者主動揭露的限制（GUI、真實負載、2 MB 尾端、不跨輪替）不算缺失，但需要更新為現況（S1）。

## 流程判定

**RETURN TO execute-task**

- 程式碼本身沒有阻擋合併的錯誤。
- 但與 main 有衝突（M1）、流程文件不符契約（M2）、必要驗證未執行也沒有豁免（M3）。
- 整合後要以新的 BASE／HEAD 重新驗證與審查。D1、M3、S3、S7 需要使用者先決定。
