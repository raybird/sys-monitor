# 審查報告
- 審查日期：2026-11-06
- 範圍：完整交付（本地審查）。分支 `issue-2-container-inspection`，BASE = `git merge-base origin/main HEAD`，46 個檔案，+4370／-143。範圍內含 merge 提交 `23ca87c`；這次重點是 `f1b9bfa..a7c2c36` 的增量（18 檔），完整範圍也重新核對過。
- Reviewed BASE SHA：`bd56e948dba6c4f1cb8d7bff82e25e811c7b5ec2`
- Reviewed HEAD SHA：`a7c2c36252caf3ddf922f5606505519030431443`
- Reviewed patch-id：`39e452267bc3a03f081db5a87c21492a87a869ac`。reviewer 以 `git diff bd56e94 a7c2c36 | git patch-id --stable` 重算，結果相同；merge-base 也重算確認是 bd56e94。
- 獨立 reviewer：Claude Code 隔離 subagent，不是原實作者。只讀 detached worktree `wt-review3`（HEAD = a7c2c36）：沒有修改受審檔案，沒有啟停容器，沒有安裝到真實 HOME。暫存與突變測試都放在 scratchpad。
- Review artifact：docs/issues/issue-2/review-a7c2c36.md
- 核准基線：`**核准 commit**` 是 `145a341`，已回填。

## 問題與風險

### MUST FIX

無。

### SHOULD FIX

**S1：M1 的核心改動（shell 端合併基準）沒有自動化測試鎖住（證據持久力）**

- 位置：
  - 合併邏輯：`src/freeze-monitor:325-329`
  - 唯一的 shell 測試：`tests/test_container_probe.py:511-550`
- 問題：新測試只涵蓋「整輪 helper 失敗」。這條路徑被 `src/freeze-monitor:306-308` 的提早 return 擋下，根本不會執行合併 awk。SCN-006 另有一條已核准的條件「該容器查詢失敗的採樣時，仍以失敗前最近一筆有效樣本比較」，只有合併邏輯能保護，卻沒有任何測試。
- 突變測試：reviewer 在 scratchpad 複製一份 HEAD，把合併 awk 換回 f1b9bfa 的「整份取代」寫法。
  - `IntegratedReviewFollowupTests` 2 個測試仍然 OK。
  - 同一份突變碼跑情境 B（restart=1 → partial 且該容器 restart_count=NA → restart=2），events.log 沒有任何 Docker anomaly。
  - 也就是說，M1 的 shell 修正被回退時，測試抓不到。
- 現況行為是正確的：reviewer 用真實 HEAD 的 `src/freeze-monitor` 搭配替身 helper 實跑情境 B，寫出 `worker:oom=false,restarts=2(new),...`。所以這不是假綠燈。依 verification.md「證據持久力」，這項不阻擋本次驗收。
- 建議：在 `IntegratedReviewFollowupTests` 加一個 partial 情境（該容器 `restart_count=NA`、`sample_status=unavailable_or_timeout`），斷言跨過那一輪後仍寫出 `(new)` 事件。可以順便讓同一測試的 helper 卡住一輪，涵蓋 timeout（exit 124）。一天後刪除的邏輯，可以把 awk 抽出來，用字面值 prev／now 測試。

### NICE TO HAVE

**N1：partial 輪次中單一容器查詢失敗時，持續存在的異常會重寫事件**（`需決策`）

- 位置：`src/freeze-monitor:315-322`、`:330-333`。
- 重現（真實收集器，情境 F）：db 持續 unhealthy，中間一輪 partial 且 db 的 inspect 失敗（health=NA）。結果寫了兩筆相同的 `db:...health=unhealthy;` WARN。
- 同類殘留（情境 H）：追蹤中執行的容器超過 8 個時，非 deep 列的 Z／D 是 NA；容器總數超過 32 時，停止的追蹤容器會輪流出現。異常集合因此忽有忽無，也會重寫事件。
- 依字面規格不違反：SCN-007 只要求「Docker 不可用的採樣」不重寫，`docs/architecture.md` 也寫明只限「沒有 Docker 資料的一輪」。影響是事件雜訊，不會漏事件。目前環境 6 個追蹤容器，觸發不到。
- 待決問題：去重要不要延伸到「該容器查詢失敗或沒輪到」？
- 可選做法：
  - 該容器的欄位是 NA 時，沿用上一輪對它的異常判定。
  - 維持現狀。
- reviewer 建議：維持現狀，在 README 限制或 #4 一類的後續 issue 記一筆。

**N2：troubleshooting 的處置欄有兩處不精確**

- 位置：`docs/troubleshooting.md:121-122`。
- `unavailable:error` 寫「As above」，但 helper 會吞掉例外，手動執行只會再印出 `unavailable:error`，看不到原因。
- 指令寫死 `python3` 與 `~/.local/share`。收集器實際用的是 `FREEZE_WATCH_PYTHON`（安裝時記在 `~/.config/freeze-watch/env`）與 `${XDG_DATA_HOME}`。helper 只用標準庫，多數情況仍然可以跑。
- 安全性沒有問題：只做唯讀 GET，暫存目錄由 `mktemp -d` 建立。
- 建議：error 一列改成「檢查 `docker context inspect` 與 socket 路徑」，並註明直譯器以 env 檔為準。

**N3：儀表板與收集器的重啟基準還有兩個已記錄的邊界差異**

- 位置：`src/freeze_watch.py:1942-1947`、`:1534`。
- 跨日輪替後，新檔第一筆在儀表板沒有比較對象，收集器仍會寫事件。另外儀表板只看該 ID 最後 60 筆，收集器保留一天。
- 前者已寫入 `docs/architecture.md:248-251`，並指出 events.log 是完整紀錄；前一輪的建議也沒有要求修這一點。影響只在 UI 少亮一次。
- 可以考慮在 README 風險段補一句，讓 SCN-006 的例外有明文依據。

**N4：S1 的 3.10 綠燈證據沒有記錄命令**

- 位置：`docs/issues/issue-2/artifacts/s1-green-py310.log`。
- 這份證據是「Ran 18 tests」，沒有寫是哪些測試。
- reviewer 獨立重跑：3.10.16 下 `-m unittest test_container_probe`，32 個測試 OK。

**N5：小瑕疵**

- `src/freeze_watch.py:149`：`epoch_after` 的型別註記仍是 `int | None`，實際會回傳 `math.inf`（float），不影響行為。
- `docs/issues/issue-2/README.md:20-25`：「文件清單」沒有列 `review-f1b9bfa.md`；「涉及檔案」沒有列 `docs/troubleshooting.md` 與 `.github/workflows/ci.yml`。這兩節不屬於記帳區段，PASS 之後再改會使本報告失效，要併在下一個本來就要重審的提交處理。

## 已查核維度

### 驗收與證據

**測試執行**

| 環境 | 命令 | 結果 |
|---|---|---|
| reviewer 本機，worktree a7c2c36，`/usr/bin/python3` 3.14.4，沒有 DISPLAY，走 xvfb | `env -u DISPLAY -u WAYLAND_DISPLAY bash scripts/check.sh` | exit 0；Ran 126 tests，OK，0 個跳過；All checks passed；50 秒 |
| Python 3.10.16（scratchpad uv），在 tests/ 下 | `python3.10 -m unittest test_container_probe` | Ran 32 tests，OK |
| GitHub Actions（headSha a7c2c36），run 42175684656（push）與 42175689392（pull_request） | `./scripts/check.sh` | 兩次都 success；Ran 126 tests，OK；All checks passed |

- CI：f1b9bfa 的 CI 失敗原因是 `ModuleNotFoundError: No module named 'cairo'`。這次加裝 `python3-gi-cairo` 後已轉綠。
- 測試清單：bd56e94 的 76 個、f1b9bfa 的 122 個測試定義在 HEAD 全部存在。HEAD 共 126 個，多出 4 個新測試（m1_n1、s1、n3、widget m1），沒有遺失或改名。

**紅燈真偽（reviewer 獨立重跑）**

做法：取 HEAD 的 tests 搭配 f1b9bfa 的 src，在 scratchpad 執行。

- `test_m1_n1_...` 失敗，3 筆事件，預期 2 筆：db 在失敗輪次後被重寫，而且沒有 worker 的 `(new)` 事件。M1 與 N1 都是真紅燈。
- `test_n3_...` 失敗：顯示「CPU：未知%」。
- widget `test_m1_...` 失敗：`False is not true`，沒有標示醒目色。
- `HardTimeoutTest` 與 `CollectorIntegrationTests` 新增的 docker_state 斷言在舊碼也綠。這兩項本來就是補自動化保護（N5），evidence 有誠實揭露。
- S1：舊 `read_time` 在 3.10 對 `.1234Z`、`.123456789Z`、`Z`、`.5+08:00` 全部退回後備值；新碼都解析正確。

**被修改的既有測試**

增量只對既有測試**加**斷言：`test_unavailable_endpoint_records_explicit_empty_snapshot`、`test_hung_helper_has_hard_limit_and_host_survives`、S6 的舊讀法對照。另外把 `if __name__` 移到檔尾。沒有弱化任何斷言。

**真實 Docker 唯讀量測**

- 命令：`python3 -I src/container_probe.py <ts> <epoch> runwukong,runtelenexus <scratchpad>`，3.10 與 3.14 各跑兩次。
- 每次 exit 0、約 0.1 秒、state=ok、8 列：7 個追蹤容器（其中 1 個 exited），加上 portainer（未追蹤）。
- 第二輪算出了速率。
- **3.10 下 cache 的 epoch 帶小數**，例如 `1793947579.171126`，迴圈 epoch 是 1793947579，證明真實 Docker 時間戳在 3.10 已能解析。
- cache 權限 600。

**核准查核**

- `git diff 145a341 a7c2c36 -- docs/issues/issue-2/README.md` 只有兩處：`**核准 commit**` 由 `待提交` 改為 `145a341`，`**狀態**` 改為「待獨立審查」。Gherkin 沒有變動。
- 145a341 本身就是修訂 SCN-006／007 的提交：
  - 新增「同一容器 ID 最近一筆有效樣本」的 Given。
  - 新增「helper 失敗、逾時或該容器查詢失敗」的 And。
  - 去重改為「D 或 Z」。
  - 新增「Docker 不可用的那一輪不重寫事件」。
  - 內容與 review-f1b9bfa M1／N1 的建議一致。
- 核准來源：使用者 2026-11-06 原話「都依照建議修」，並記入 TBD-7。前兩次核准的原話「照你的建議處理 D1、M3、S3、S7」、「1. 核准」也都在。狀態表與 9 個 Scenario 集合完全相等。

**SCN 逐項判定**

| SCN | 證據 | 判定 |
|---|---|---|
| 001 | check.sh 雙 project 與單 project 升級；真實輸出兩組專案都有 ID／project／service | 通過 |
| 002 | RecoveryRegressionTests、未知樣式、widget 測試；N3「未知%」已修，有紅綠燈 | 通過 |
| 003 | io_rates 邊界、S2 讀取時間；S1 在 3.10 下獨立重跑通過，真實 cache 也帶小數 | 通過 |
| 004 | 上限 15、5 個欄位、生命週期平均標示 | 通過（沒有變動） |
| 005 | `read_tsv_before` 8 MB 測試加舊讀法對照（N7）；N2 改成 inf | 通過 |
| 006 | 門檻、tooltip 測試；shell 測試涵蓋 helper 失敗跨輪；GUI 測試涵蓋單一容器 NA；reviewer 實跑真實收集器：helper 失敗（測試）、逾時（情境 D）、單一容器查詢失敗（情境 B）都寫出 `(new)` 事件；同一份 TSV 儀表板也都標示 warm | 通過。單一容器查詢失敗的 shell 路徑只有 reviewer 實跑證據（S1） |
| 007 | 未追蹤、首次採樣、D 波動測試；N1 shell 測試（失敗輪次不重寫）；reviewer 情境 G（helper 回 `unavailable:no_daemon` 且 exit 0）不重寫；容器重建成新 ID（情境 C）兩邊都不警示 | 通過（N1 是字面規格以外的殘留） |
| 008 | 卡住的 helper 在 11 秒內終止，並新增斷言 metrics 記為 `unavailable:timeout`；`helper_failed` 斷言；慢速 socket、遠端 endpoint | 通過；高負載成本已豁免 |
| 009 | 舊 11 欄、輪替沿用、空列一致 | 通過（沒有變動） |

**假綠燈：未發現。**

- 新斷言的期望值都是獨立字面值：例如 `1793923200.1234` 等 epoch，以及事件字串 `worker:oom=false,restarts=2(new)`。
- S1 是證據持久力問題，不是假綠燈。

### 相關失敗面

| 失敗面 | 輸入／狀態 | 預期 | 覆蓋與實測 | 判定 |
|---|---|---|---|---|
| 基準跨 helper 失敗 | ok r=1 → exit 1 → ok r=2 | 寫 `(new)` | 自動測試 | 通過 |
| 基準跨逾時 | ok r=1 → 卡住 60 秒 → ok r=2 | 寫 `(new)` | reviewer 實跑（D）：`unavailable:timeout` 之後寫出 `restarts=2(new)` | 通過，沒有自動化 |
| 單一容器 inspect 失敗 | partial，restart=NA | 保留基準 | reviewer 實跑（B）寫出事件；突變成整份取代後漏寫，現有測試卻仍綠 | 通過（S1） |
| 容器重建 | w1 r=0 → w2 r=1 → w2 r=1 | 不警示 | 實跑（C）：收集器沒有事件；儀表板依 ID 分歷史，也沒有 warm | 一致 |
| 跨日輪替 | rotate 不動 `last_restart_counts` | 收集器沿用 | 程式碼推理；儀表板新檔沒有前一筆，已記錄於文件 | 通過（N3） |
| 收集器重啟 | 新行程 `last_restart_counts=""`，新檔名帶 start_stamp | 第一筆兩邊都不警示 | 程式碼推理：儀表板讀最新檔，只有重啟後的列 | 一致 |
| 一天後刪除 | prev `a=1@0;b=2@90000`，now=90001 | 刪 a、留 b、新增本輪 | 抽出 awk 在 mawk 與 busybox awk 實測相符 | 通過，沒有自動化 |
| awk 解析邊界 | 空 ID、`NA`、`x=y=z`、`e=@...` | 不誤判 | 空字串與 NA 被濾掉；ID 含 `=` 時 split 不等於 2，只會失去基準，不會誤報；Docker ID 是 64 位 hex，實際不會出現 | 通過 |
| awk printf 的 `>` | 第 321 行 `($9 + 0 > 0 ? ...)` | 是比較，不是重導向 | mawk 與 busybox 輸出正確，沒有產生檔名 `0`／`8` 的殘留檔；grep 全檔沒有其他 printf 參數裡未加括號的比較 | 通過 |
| N1 提早 return | unavailable:* | 不跳過必要更新 | INFO 狀態事件、docker 計數歸零、空列落盤、cache 刪除都在 return 之前；metrics 由呼叫端寫；跳過的只有 alert 與基準更新，符合設計 | 通過 |
| partial 輪次 | 走完整個 alert 與合併流程 | — | 實跑（F）會重寫持續中的異常 | 字面規格內（N1） |
| S1 正規化 | `.000000001-05:00`、`0001-01-01T00:00:00Z`、`.Z`、空白分隔、小寫 z、naive 時間、秒為 60、月 13、`+24:00`、非 ASCII 數字、尾端換行、None、整數、list、缺 key | 合法的解析，其餘退回後備值 | 3.10 與 3.14 實測：合法輸入都正確解析；停止容器的年份 1 退回後備值；其餘全部退回後備值、不拋例外。naive 時間改為拒絕，比舊碼依本地時區解讀更安全 | 通過 |
| troubleshooting | 原因碼對照與指令 | 與程式一致 | 原因碼與 `unavailable_reason` 及 shell 的 124／137 對應一致；`docker context inspect --format '{{.Endpoints.docker.Host}}'` 與 helper 的指令相同；只做唯讀操作 | 通過（N2） |
| CI | ubuntu runner | 綠 | a7c2c36 兩個 run 都 success，126 個測試 OK | 通過 |

**前一輪發現的獨立核對**

- 已修正：
  - M1：收集器改為合併基準；儀表板改用 `previous_restart_sample`。
  - S1：讀取時間在 3.10 可用。
  - S2：troubleshooting 已補（剩 N2 的小瑕疵）。
  - N1、N2、N3、N4、N5、N6、N7。
  - CI 缺 cairo。
- 依決定維持現狀：N8。

### 需求、架構、安全、品質

- 需求：增量全部可追溯到 TBD-7 的決定與修訂後的 SCN-006／007，沒有越界。
- 安全：helper 仍然只用 GET，拒絕遠端 endpoint。新增的 regex 對輸入有界，`fullmatch` 不會回溯爆炸。troubleshooting 沒有引入危險指令，並保留 docker 群組等同 root 的警告。
- 架構：基準狀態只存在收集器的記憶體，大小有界（每輪最多 32 個 ID，一天過期），沒有新增檔案或依賴。
- 品質：
  - shell 與 Python 兩份重啟判準現在語意一致，邊界差異已記錄（N3）。
  - 兩段 awk 各自解析一次 prev，可以接受。
  - 沒有過度設計。
  - 風格沿用既有寫法，`freeze-monitor:321` 偏長，與既有風格相同。

### 豁免、待確認與限制

- 豁免一：不以 PR #3 交付，改走本地審查。豁免二：不量測高負載採樣成本。兩項都有原話與殘餘風險，本報告沿用。合併後依前一輪建議，把狀態改為等待外部驗收窗，並以 `unavailable:timeout`、`partial` 與列層級的 `unavailable_or_timeout` 比例作為觀察判準。
- TBD-1～7 都已解決，各有日期與來源。
- 實作者主動揭露的限制，不算缺失：一天後刪除的邏輯沒有測試；GitNexus 無法使用；實作中 awk 誤當重導向的失誤已記錄並修正。
- 主 repo 有一個未追蹤的 `mcp-memory-libsql.db`，不在交付範圍，不要誤提交。

## 流程判定

**PASS**

- 獨立審查完成，沒有 MUST FIX。
- 前一輪的 M1、S1、S2、N1～N7 與 CI，reviewer 都獨立驗證為已修正：真實收集器實跑、3.10 重跑、真實 Docker 唯讀量測、CI 轉綠。
- 9 個 Scenario 都有證據。SCN-006 單一容器查詢失敗的路徑由 reviewer 實跑補證；它缺少自動化保護，列為 SHOULD FIX S1，依 verification.md「證據持久力」不阻擋。
- 核准有效（145a341），豁免齊備。
- 本 PASS 只綁定 a7c2c36。之後的提交若超出 review-evidence.md「審查之後的提交」允許的記帳範圍，例如處理 S1 補測試或 N5 改 README 清單，就要重新審查。
