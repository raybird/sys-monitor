# 審查報告
- 審查日期：2026-11-06
- 範圍：完整交付（本地審查）。分支 `issue-2-container-inspection`，BASE = `git merge-base origin/main HEAD`，38 個檔案，+3466／-141。範圍內含 merge 提交 `23ca87c`（把 main 合進分支、解 5 個衝突），本次一併審查。
- Reviewed BASE SHA：`bd56e948dba6c4f1cb8d7bff82e25e811c7b5ec2`
- Reviewed HEAD SHA：`f1b9bfa1533653dd70cf3058a874648470be4547`
- Reviewed patch-id：`b4f20319b1d060ad74d7bc76d960af685333e68b`（reviewer 以 `git diff bd56e94 f1b9bfa | git patch-id --stable` 重算，結果相同）
- 獨立 reviewer：Claude Code 隔離 subagent（general-purpose），不是原實作者。只讀 detached worktree `wt-rereview`（HEAD = f1b9bfa）；沒有修改檔案，也沒有啟停容器。
- Review artifact：docs/issues/issue-2/review-f1b9bfa.md
- 核准基線：`**核准 commit**` 是 `0903fe7`，已回填，不是 `待提交`。另外依 pattern 推導，最後修改 `**核准來源**` 欄位行的提交是 `96d6160`，僅供參考。

## 問題與風險

### MUST FIX

- **M1：收集器與儀表板的「新增重啟」基準不一致，重啟遇到失敗的一輪就漏寫事件**（`需決策`）
  - 位置：
    - shell 端：`src/freeze-monitor:316`。每輪用本輪的 rows 整份取代 `last_restart_counts`。
    - 儀表板端：`src/freeze_watch.py:903`、`:1527`、`:1936-1940`。用同一 container ID 上一筆已保存的樣本當基準。
  - 分歧處：
    - helper 失敗或逾時的那一輪，rows 只有空列，shell 會清空基準。
    - 某個容器那一輪 inspect 失敗時，它的 restart_count 是 NA，基準也會被丟掉。
    - 儀表板則跳過空列，拿失敗前那筆比較。
  - 重現（reviewer 實跑真實 `src/freeze-monitor`，替身 helper 依序回 restart=1、exit 1、restart=2）：
    - `docker-*.tsv` 依序是 `worker 1 / (空列 unavailable) / worker 2`。
    - `events.log` 只有三筆 `Docker monitor state`，**沒有任何 `Docker anomaly`**。
    - 同一份檔案餵給 `container_warning(latest, history[-2])`，回傳 `True`，表示儀表板會醒目標示。
  - 反方向也不一致：
    - 同一個收集器跨日輪替後，新檔的第一筆在儀表板沒有前一筆可比，所以不標示。
    - shell 仍保有記憶體裡的基準，所以會寫事件。
  - 影響：
    - SCN-006 要求「比前一次採樣新增的重啟 → 收集器寫入一筆 Docker anomaly 事件」，但漏寫正好發生在 helper 逾時前後。那是高負載、最需要證據的時段。
    - events.log 是事後回看的持久紀錄，而 UI 只會在那一筆樣本亮一次。
    - `docs/architecture.md:225-226` 有寫「unavailable sample 後沒有基線」，但這只是記錄了分歧，沒有消除它，Gherkin 也沒有這條例外。
  - 待決問題：「前一次採樣」要指同一 container ID 最近一筆有效樣本，還是收集器的上一輪？
  - reviewer 建議：
    - 採「同 ID 最近一筆有效樣本」，與儀表板一致。
    - shell 端把本輪的有效值合併進既有對照表，只更新有數值的 ID；不要整份取代。
    - 收集器重啟時維持空表，SCN-007 不變。
    - 補一個真實 shell 測試，情境為「ok → helper 失敗 → 重啟次數 +1」。

### SHOULD FIX

- **S1：S2 的讀取時間在 Python 3.10 以下會靜默失效，測試也會紅**
  - 位置：`src/container_probe.py:84`。
  - 原因：
    - Docker 的 `read` 是 `...Z` 結尾的 RFC3339Nano。
    - `datetime.fromisoformat` 要到 3.11 才接受 `Z`，也才接受 3 或 6 位以外的小數位數；Go 會去掉尾端的 0，所以位數不固定。
    - 3.10（例如 Ubuntu 22.04）會丟 ValueError，每一輪都退回迴圈 epoch，S2 修正等於沒做。
    - `tests/test_container_probe.py:363` 的 `test_s2_rates_divide_by_each_containers_read_time` 在 3.10 會失敗。
  - 專案沒有宣告 Python 最低版本：README 只寫「Python 3」，install.sh 只探測模組。
  - 本機實測 3.11 與 3.14 都能解析 `.1234Z`、`.123456789Z`、`+08:00`。
  - 建議：先把 `Z` 換成 `+00:00`，小數補齊或截到 6 位再解析；或在文件寫明最低 Python 版本。

- **S2：`docs/troubleshooting.md` 沒有跟著改**
  - 位置：`docs/troubleshooting.md:109-118`。
  - project.md 規定「診斷限制與操作方式變更：docs/troubleshooting.md」。
  - 本次有兩項行為改變：
    - 不可用時改成帶原因碼：`permission`、`no_socket`、`no_daemon`、`nonlocal`、`timeout`、`helper_failed`、`error`。
    - TCP／SSH context 由原本 docker CLI 可以採樣，改成固定 `unavailable:nonlocal`。
  - 「Docker shows unavailable」一節仍只叫使用者跑 `docker ps`。可是遠端 context 下 `docker ps` 會成功，Freeze Watch 卻顯示不可用，文件會誤導。
  - 建議：補上原因碼的對照與處置，並寫明遠端 endpoint 是刻意不支援。

### NICE TO HAVE

- **N1：持續存在的異常，會在失敗或輪替的那一輪之後重寫事件**
  - 位置：`src/freeze-monitor:313`、`:320`。
  - 失敗或逾時的那一輪 alert 是空字串，`last_docker_alert` 被清空；下一輪同樣的異常字串會再寫一次 WARN。例如追蹤中的容器長時間 unhealthy，或已退出的 OOM 容器。
  - 追蹤中執行的容器超過 8 個時，非 deep 列的 Z 與 D 是 NA，異常集合隨輪替忽有忽無，也會重複寫入。
  - 事件字串含 Z 的數值，Z 波動也會重寫。
  - 目前環境沒有觸發：6 個追蹤中執行的容器，共 8 個容器。SCN-007 只要求 D 去重。
  - 可以考慮在 unavailable 的那一輪不重設 `last_docker_alert`。

- **N2：`read_tsv_before` 的 EOF 哨兵值錯用**
  - 位置：`src/freeze_watch.py:161`。
  - `size + 1` 要拿來跟 unix epoch（約 1.79e9）比較，正常大小的檔案永遠不會大於 end。二分搜尋落在最後一行時，就退成 `cut = size`。
  - 實測：最後一行大於 byte_limit 時回傳 `[]`。
  - 2 MB 上限下，除非單行超過 2 MB，否則無害；reviewer 另做 3000 組隨機檔（CRLF、沒有結尾換行、沒有表頭、同 epoch 多列）與暴力解比對，0 筆不符。
  - 建議改成 `math.inf`。

- **N3：詳情裡 CPU 未知時顯示「CPU：未知%」**
  - 位置：`src/freeze_watch.py:858`。

- **N4：新測試類別寫在 `if __name__ == "__main__": unittest.main()` 之後**
  - 位置：`tests/test_freeze_watch.py:407`、`tests/test_window_layout.py:346`。
  - 直接執行檔案時，新類別不會被定義，也就不會跑。check.sh 用 discover，所以不受影響。

- **N5：shell 端的原因碼沒有自動化測試**
  - 包括 exit 124／137 對應的 `unavailable:timeout`，以及 `unavailable:helper_failed`。
  - reviewer 手動實跑：卡住的 helper 8 秒後 metrics 記 `unavailable:timeout`；helper 回 exit 3 時記 `unavailable:helper_failed`，兩者都正確。
  - 建議在 `HardTimeoutTest` 加斷言 metrics 的 `docker_state`。

- **N6：N8 用 `get_visible()` 偵測下拉選單**
  - 位置：`src/freeze_watch.py:1510`。
  - 視窗在選單開著時被隱藏，`visible` 可能仍為 True，重建會延到選單關閉才做。這是延後，不是永遠不重建，因為簽章維持過期。
  - 改用 `get_mapped()` 較穩。

- **N7：紅燈證據較弱**
  - S4（UI）、S5、S6 的紅燈只是函式不存在（AttributeError），不是目標行為的紅燈。
  - S6 可以補一個舊 tail 讀法找不到早期事故的對照。
  - 這屬於證據持久力的問題，不是假綠燈。綠燈斷言都是獨立的字面值或真實檔案。

- **N8：即時模式每 2 秒重讀並解析 2 MB docker TSV**
  - reviewer 用真實列型態做出 3 MB 的檔案，每次 refresh 約 28 ms（8 個容器）。目前可以接受；可在檔案 mtime 與 size 不變時跳過。

## 已查核維度

### 驗收與證據

**測試執行**

| 環境 | 命令 | 結果 |
|---|---|---|
| reviewer 本機，worktree f1b9bfa（沒有 DISPLAY，走 xvfb-run，`/usr/bin/python3` 3.14.4） | `env -u DISPLAY -u WAYLAND_DISPLAY bash scripts/check.sh` | exit 0；Ran 122 tests，OK，0 個跳過；All checks passed；28.3 秒 |

- check.sh 先匯出 `DOCKER_HOST=unix:///nonexistent`，安裝與移除只操作 `mktemp -d` 的臨時 HOME。
- 測試清單比對：main（bd56e94）的 76 個、1e33e63 的 66 個測試定義在 HEAD 全部存在；HEAD 共 122 個，沒有遺失。

**真實 Docker 唯讀量測**

- 命令：`python3 -I src/container_probe.py <ts> <epoch> runwukong,runtelenexus <scratchpad>`，執行兩次。
- 每次 exit 0、約 0.22 秒。
- 輸出 8 列：runwukong 4 列（其中 1 個已退出）、runtelenexus 3 列、portainer 1 列（未追蹤，標 `not_tracked`）。
- 第二輪算出了速率；cache 的 `epoch` 是 Docker read 時間（帶小數），權限 600。

**核准查核**

- `git diff 0903fe7 f1b9bfa -- docs/issues/issue-2/README.md` 只改了 `**核准 commit**`（待提交 → 0903fe7）與 `**狀態**` 兩個值，Gherkin 沒有變動，核准仍然有效。
- 0903fe7 本身就是把 9 個 Scenario 改成已核准的提交，承載當次核准的規格。
- 核准來源有原話與日期：「照你的建議處理 D1、M3、S3、S7」（SCN-006、007）、「1. 核准」（其餘 7 個），都是 2026-11-06，可追溯到本次對話。
- 狀態表與現存 Scenario 集合完全相等。

**SCN 逐項判定**

| SCN | 證據 | 判定 |
|---|---|---|
| 001 | check.sh 雙 project 安裝與單 project 升級；真實輸出兩組專案都有 ID、project、service | 通過 |
| 002 | RecoveryRegressionTests（已退出容器保留 OOM／重啟）、`container_summary` 未知樣式、widget 測試、截圖 | 通過（N3 小瑕疵） |
| 003 | io_rates 各種邊界、基線失效、S2 讀取時間測試（字面值 100.0） | 通過；3.10 以下見 S1 |
| 004 | 上限 15、保留 D、只有 5 個欄位；生命週期平均已標示；原因對照表 | 通過 |
| 005 | `read_tsv_before` 8 MB 檔案測試、reviewer 隨機比對、跨重啟 QA 截圖、hero 過期標示 | 通過（N2 不影響） |
| 006 | UI 門檻與 tooltip 測試；真實 shell 事件測試（D 8→9→10 只寫 1 筆） | **部分**：重啟跨失敗輪次時漏寫事件（M1） |
| 007 | 未追蹤、首次採樣、D 波動的測試 | 通過 |
| 008 | 卡住的 helper 小於 11 秒、S8 真實慢速 socket 測試（小於 2.5 秒且保留已完成的列）、S4 真實 socket 原因 | 通過；高負載成本已豁免 |
| 009 | 舊 11 欄檔案、N4 空列一致、輪替沿用、uninstall 會刪 probe | 通過 |

**假綠燈查核：未發現。**

- 修改過的既有測試有兩個，都附了正當理由（核准行為已改變）：
  - `test_known_anomalies_only_are_flagged`
  - `test_unavailable_endpoint_records_explicit_empty_snapshot`
- 主線上的既有測試沒有被改動。

### 相關失敗面

| 失敗面 | 輸入／狀態 | 預期 | 覆蓋 | 判定 |
|---|---|---|---|---|
| S8：SIGALRM 與 http.client、socket timeout 的交互 | 每 0.2 秒送 1 byte | 在預算處切斷，保留已完成的列 | 真實 socket 測試 | 通過 |
| S8：alarm 在 try 或 finally 之外觸發 | `setitimer` 與 `try` 之間、`finally` 第一行之前 | 不洩漏到 `get` 之外 | 程式碼推理：`TimeoutError` 仍從 `get` 拋出，被 collect 的三個 except 接住；唯一副作用是 handler 沒還原、連線沒關，對短命行程無害 | 通過 |
| S8：非主執行緒呼叫 | `signal.signal` 丟 ValueError | — | 被 except 接住，結果變成 `unavailable:error` | 目前只在 `main()` 呼叫，可接受 |
| S8：與外層 timeout 的關係 | 預算 6 秒；`endpoint()` 的 0.5 秒子行程也算在預算內 | 外層 `timeout -k 1s 8s` 作最後防線 | 實測 hang 8 秒 | 通過 |
| S2：`read` 時間戳格式、時鐘、後備值 | 本機 daemon 與收集器同一個時鐘；年份 1 或亂碼退回迴圈 epoch；舊 cache 的 epoch 在收集器啟動時刪除（`src/freeze-monitor:82`），不會混用 | — | 後備值有測試 | 3.11 以上通過；3.10 以下見 S1 |
| S4：原因碼 | shell 的 `unavailable*` 比對正確；124／137 → timeout；UI `docker_state_label` 支援舊值 `unavailable`（顯示原因未記錄），未知原因顯示原文，`not_installed` 原樣顯示 | — | UI 有測試，shell 為手動驗證 | 通過（N5） |
| S6：二分搜尋 | 排序、表頭、空檔、最後一行沒有換行、CRLF、多列同 epoch、檔案寫入中途 | 與暴力解一致 | 隨機比對 3000 組 0 錯；log(size) 次 seek，refresh 成本可接受 | 通過（N2） |
| S3：shell 與 Python 的判準 | 追蹤判定、OOM、unhealthy、Z、D 4／8 | 一致 | 測試 | 通過 |
| S3：重啟基準 | — | 一致 | — | **不一致（M1）** |
| N3：deep 游標 | 16、10、6 個追蹤容器 | 全部輪到 | 測試與推算 | 通過 |
| N4：空列 | — | 兩邊寫出相同的列 | 逐欄比對測試 | 通過 |
| N8：延後重建 | 選單開啟時 | 延後到關閉後才重建 | 簽章維持過期，關閉後下一次 refresh 必定重建，不會永遠不重建 | 通過（N6） |
| merge 衝突解法 | 5 個檔案 | 不遺漏任一邊 | 以 `--remerge-diff` 核對：install、uninstall、check 取聯集；metrics 表頭用 main 的（含 `gpu_processes`）；docker 表頭用分支的 24 欄；`read_tsv_path` 用 main 的（含 `min_rows` 與首行丟棄，N1 因此已解決）；兩邊的測試全數保留 | 沒有遺漏 |

**前一輪發現的獨立核對**

- 已修正：S1、S4、S5、S6、S8、S9、N1～N8。
- 部分修正：
  - S2：只在 3.11 以上有效（S1）。
  - S3：門檻與追蹤範圍已修正，重啟基準有分歧（M1）。
- 已關閉：S7 經使用者接受並開 #4 追蹤；M1／M2／M3／D1 已處理。

### 需求、架構、安全、品質

- 需求：範圍與已核准的 Gherkin 相符，沒有越界。
- 安全：
  - 只用 GET；不讀 logs、argv、env。
  - 拒絕遠端 endpoint。
  - 程序名稱已移除控制字元；cache 權限 0600，以原子方式寫入。
- 架構：Python 標準庫的 helper 是獨立行程，SIGALRM 只作用在 helper 自己的行程內，主機迴圈不受影響。
- 品質：
  - 跨檔重複邏輯（shell awk 與 Python 的警示）已分歧並造成不一致，即 M1。
  - 空列重複已由 N4 測試鎖住。
  - 沒有明顯的過度設計。
  - 風格：`container_probe.py` 的行偏長；README.md 的新章節放在 `## License` 之後。

### 豁免、待確認與限制

- 豁免一：不以 PR #3 交付，改走本地審查。有使用者原話與殘餘風險，本報告沿用。
- 豁免二：高負載採樣成本不量測。有原話與殘餘風險。
  - 合併後建議把 README `**狀態**` 改成 `等待外部驗收窗`，並寫明觀察判準：容器列的 `unavailable_or_timeout` 比例、`partial`、`unavailable:timeout` 的次數。
  - 再做一次反向自檢：單一容器 0.5 秒的 socket 逾時，在負載下也會造成每列未知；若只看清單層級的 unavailable，判準會誤判為綠燈。
- TBD-1～6 都已解決，各有日期與來源。
- 實作者主動揭露的限制，不算缺失：GitNexus 沒有註冊這個 repo；視覺 QA 由 agent 在 xvfb 下看截圖；跨重啟是用改寫 boot id 模擬。

## 流程判定

**RETURN TO execute-task**

- 理由：有 1 項 MUST FIX（M1）。收集器與儀表板重複實作的「新增重啟」基準已經分歧，reviewer 實跑重現：重啟跨 helper 失敗的一輪後，events.log 沒有 Docker anomaly，UI 卻會醒目標示。這也讓 SCN-006 的事件要求在高負載時段失效。
- M1 標了 `需決策`：要先由使用者決定「前一次採樣」的語意，reviewer 建議採同 ID 最近一筆有效樣本。
- 修正後要以新的 HEAD 重跑 check.sh 並重新審查。
- 本報告綁定 f1b9bfa；之後若有程式提交，不符合 review-evidence.md「審查之後的提交」的沿用條件。
- 其餘項目：核准有效；測試在 reviewer 本機 122 個全綠、0 個跳過；merge 衝突解法正確；豁免齊備。
