# 審查報告
- 審查日期：2026-11-06
- 範圍：完整交付（本地審查），BASE..HEAD 共 2 個提交（c686ee6 建立 AC、c315961 實作），10 個檔案
- Reviewed BASE SHA：9a8807b1756e4453199bdefdff746acdf105e5cd（= merge-base origin/main HEAD）
- Reviewed HEAD SHA：c315961f6f60b3a3272411b7d0533824c66513ea
- Reviewed patch-id：187b5c6b00116e507291204993c2605c99be8940（reviewer 以 `git diff BASE HEAD | git patch-id --stable` 重算，相符）
- 獨立 reviewer：Claude Code 隔離 subagent（不是原實作者；只讀，沒有修改受審檔案、沒有 commit／push、沒有啟停容器、沒有安裝到真實 HOME）
- Review artifact：docs/issues/issue-5/review-c315961.md

## 問題與風險

### MUST FIX

無。

### SHOULD FIX

**S1：partial 案例分不出「保留有效基準」和「把 NA 存成基準」，有一個合理的回歸突變存活（證據持久力）**

- 位置：`tests/test_container_probe.py:560-568`（`test_ac1_partial_round_keeps_the_restart_baseline`）；被保護的程式在 `src/freeze-monitor:327`。
- 突變 f：把合併 awk 的 `$12 != "" && $12 != "NA" && $11 ~ /^[0-9]+$/ { seen[$12] ...` 改成拿掉 `$11 ~ /^[0-9]+$/`。這樣 partial 那一輪會把 `NA` 寫成基準，之後任何 `restart_count > 0` 都會被當成新的重啟。
  - 結果：`RestartBaselineTests` 3 個測試和 m1_n1 全部 ok（exit 0，63 秒），這個突變沒被抓到。
  - 原因：在這個突變下，1 → NA → 2 照樣寫出 `restarts=2(new)`，因為 `2 > "NA"+0`。測試只斷言「有寫出 `(new)`」，沒有斷言「沒重啟時不寫 `(new)`」。
  - reviewer 另寫情境 1 → NA → 1、預期沒有任何 Docker anomaly：在 HEAD 是綠的；在突變 f 是紅的，多寫了一筆 `worker:...restarts=1(new)`。
- 影響：AC-1 的字面要求已經做到，現況行為也正確，所以這不是假綠燈。但測試名稱寫的是「保留基準」，它實際只保護了一半：回歸成「NA 覆寫基準」時會產生假的重啟事件，現有測試卻全綠。
- 建議：把 partial 案例改成 4 輪 `[1, NA, 1, 2]`，斷言只有 1 筆 alert，而且內容含 `restarts=2(new)`。這樣只多一輪（約 3 秒），突變 f 會因為多出 `restarts=1(new)` 而失敗。另一個做法是加一個 1 → NA → 1 不寫事件的案例，約多 11 秒。

**S2：issue 5 README 缺少 project.md 要求的 Gate 豁免紀錄**

- 位置：`docs/issues/issue-5/README.md`（沒有 `## Gate 豁免紀錄` 這一節；可以放在 `## Timeline`（第 94 行）之前）。
- 依據：`docs/agents/project.md` 的「提交與交付」寫明本專案不建立 PR，改由本地獨立審查，並且「各 issue 仍在 README 的 Gate 豁免紀錄記錄」。issue 1、issue 2 都有這一節，issue 5 沒有。
- 影響：只是流程留痕不完整。依 review-evidence.md「審查之後的提交」（流程契約 2.4），`## Gate 豁免紀錄` 屬於記帳區段，可以整節新增，不會讓本 PASS 失效。
- 建議：在保存本報告的記帳提交裡一併補上。格式照 issue 1 的表格：日期 2026-11-06；豁免項目是「不建立 PR 與 PR 證據，改由本地獨立審查報告承載」；使用者原話引用 2026-11-04 的「這專案可以不走 pr 再本地直接審查」，這項授權已記錄在 project.md、持續有效；殘餘風險是「沒有平台審查紀錄與這個分支的 CI」。這個分支還沒推到 origin，`gh run list` 查不到任何 CI。

### NICE TO HAVE

**N1：一天刪除的門檻值沒被釘住**

- 位置：`tests/test_container_probe.py:579-585`。
- 突變 e：把 `now - ce[2] <= 86400` 改成 `<= 80000`，4 個測試全部 ok。依測試的設計，門檻落在大約 10 秒到 90006 秒之間都會通過。
- 突變 b（完全拿掉刪除條件）和「門檻過小」這兩種情況，控制組都抓得到，所以這項只算邊界精度不足。
- 可選做法：分兩次跳時間，例如 +86000（基準要保留）與 +87000（基準要刪除）。這會多約 13 秒測試時間，要不要做由實作者權衡。

**N2：troubleshooting 的手動執行指令用 `.` 載入 env 檔，與程式的讀法不同；後備直譯器也和收集器不同**

- 位置：`docs/troubleshooting.md:129-134`。
- reviewer 照抄文件指令實跑（只把 `TMPDIR` 指到 scratchpad）：exit 0，第一行 `ok`，7 列容器。把 env 檔改成不存在時，會印出 `No such file or directory`，但仍以 `python3` 繼續，exit 0。
- 安全性：env 檔由使用者自己擁有、權限 0600，source 它不跨權限邊界，也沒有安全問題。
- 不一致處：
  - 專案自己讀這個檔都是用 awk 取值，不執行它（`src/freeze-watch:14-21`、`install.sh` 的 `env_value`）；systemd 則以 `EnvironmentFile` 解析。檔頭寫著「Safe to edit」，使用者如果寫入含空白、引號或 `;` 的值，shell source 的結果會和收集器實際拿到的值不同。
  - 後備值 `python3` 走的是 PATH，可能是版本管理器的 shim；收集器的預設是 `/usr/bin/python3`（`src/freeze-monitor:249`）。文件說「與收集器使用的直譯器相同」，在後備情況下不成立。
- 建議：
  ```bash
  py="$(sed -n 's/^FREEZE_WATCH_PYTHON=//p' "${XDG_CONFIG_HOME:-$HOME/.config}/freeze-watch/env" 2>/dev/null | tail -1)"
  "${py:-/usr/bin/python3}" ...
  ```
- 另外順帶一提（既有狀況，不在本 issue 範圍）：systemd unit 固定讀 `%h/.config/freeze-watch/env`（`systemd/user/freeze-monitor.service:7`），沒有依 `XDG_CONFIG_HOME`。

**N3：證據敘述有兩處不精確**

- `docs/issues/issue-5/README.md:72` 寫「拿掉刪除條件的突變失敗，這也證明替身 `date` 確實生效」，推論不成立。拿掉刪除條件後，不論時間有沒有跳，都會寫出 `(new)`，所以這個紅燈證明不了 date 替換。能證明的是：HEAD 跳時間的案例是綠的（沒跳成功就會寫出 `(new)` 而變紅），再加上控制組。
  - reviewer 另外保留一次實跑的 state 目錄，直接確認 date 替換生效：
    - metrics 的 epoch 在第 4 筆從 1793949895 跳到 1794039896；
    - events.log 有 `GAP sampling stalled for 90001s`，沒有 ROTATE；
    - metrics／docker 檔名不受影響。
  - 結論正確，只是推理寫錯。
- `docs/issues/issue-5/README.md:28`、`:69` 寫「只消失一輪就回來」，`tests/test_container_probe.py:582` 的註解寫 "gone for a round"，但控制組實際消失了兩輪（`[worker(1), gone, gone, worker(2)]`）。要配合時間跳在第 3 輪，兩輪是必要的，所以建議改文字，不改測試。

**N4：測試小瑕疵**

- `run_rounds` 支援 `'fail'`（`tests/test_container_probe.py:514`、`:529`），但沒有任何測試用到。這屬於 AGENTS.md 第三節說的推測性彈性，建議拿掉，或真的用上。
- `tests/test_container_probe.py:585-587`：新 class 結尾和 `class IntegratedReviewFollowupTests` 之間只空一行，其他 class 之間是兩行（PEP 8）。
- `docs/issues/issue-5/README.md:103`：`**風險**: Low\` 用反斜線換行，其他 metadata 行用兩個空白，寫法不一致（渲染結果相同）。

**N5：測試時間增加**

- `scripts/check.sh` 的單元測試：a7c2c36 是 126 個 50 秒，HEAD 是 129 個 83.6 秒，多了約 33 秒。新的 class 單獨跑約 50 秒。
- 這是收集器的結構造成的：間隔最小 1 秒，而且 `docker_every_samples=3` 是 readonly。不改 `src/freeze-monitor` 就沒有空間縮短，可以接受。
- flaky 餘裕：每次 subprocess timeout 60 秒，實測每次 13–20 秒。reviewer 同時跑 8 份突變時也穩定。

**N6：新增的 artifacts 含本機絕對路徑**

- `docs/issues/issue-5/artifacts/check.log` 有 `/home/kevin/...` 與 `/tmp/tmp.*`；`mutation-*.log` 有 `/tmp/claude-1000/-home-kevin-.../<session UUID>/scratchpad/...`，會露出本機使用者名稱和 session ID。
- 沒有 token、容器名稱或 ID、boot id，`manual-helper-run.txt` 也只保存摘要。issue 2 的 artifacts 早就有同樣的路徑。
- 要不要把路徑改成 `<repo>`、`<scratchpad>` 由使用者決定，不阻擋。

## 已查核維度

### 驗收與證據

**reviewer 自己執行的測試**

| 環境 | 命令 | 結果 |
|---|---|---|
| reviewer worktree（detached c315961），`/usr/bin/python3` 3.14.4，bash 5.3.9，沒有 DISPLAY，走 xvfb-run | `env -u DISPLAY -u WAYLAND_DISPLAY bash scripts/check.sh` | exit 0；Ran 129 tests in 83.588s，OK，0 個跳過（OK 行沒有 skipped）；All checks passed；real 1m32s；`RestartBaselineTests` 3 個都 ok |

**reviewer 自做的突變**

每份突變都是 scratchpad 內從 HEAD 匯出的複本（`git archive HEAD src tests`），8 份平行執行。命令是在各複本的 `tests/` 下跑 `python3 -m unittest -v test_container_probe.RestartBaselineTests test_container_probe.IntegratedReviewFollowupTests.test_m1_n1_...`。

| 代號 | 突變（`src/freeze-monitor`） | partial | timeout | AC-2 | m1_n1 | 判定 |
|---|---|---|---|---|---|---|
| a | 合併 awk 換回 f1b9bfa 整份取代 | FAIL | ok | FAIL | ok | 抓到；與 artifacts/mutation-replace.log 相同 |
| b | 拿掉 `if (now - ce[2] <= 86400)` | ok | ok | FAIL | ok | 抓到；與 artifacts/mutation-noprune.log 相同 |
| c | 拿掉 `unavailable*` 提早 return | ok | ok | ok | FAIL | 只有既有的 m1_n1 抓到；新測試不保護提早 return，README 已揭露 |
| d | c 加 a | FAIL | FAIL | FAIL | FAIL | 抓到；逾時案例保護的是「逾時後基準仍在」這個整體行為 |
| e | 門檻改 80000 | ok | ok | ok | ok | 存活（N1） |
| f | 合併 awk 拿掉 `$11 ~ /^[0-9]+$/` | ok | ok | ok | ok | 存活（S1）；reviewer 的 1→NA→1 案例在 f 為 FAIL、在 HEAD 為 ok |
| g | alert 拿掉 `($12 in last)` | FAIL | FAIL | FAIL | FAIL | 抓到 |
| h | 未修改的對照組 | ok | ok | ok | ok | 基線 |

- reviewer 另寫了 #5 範圍原文的字面情境（同一張表裡，過期的 ID 被刪、持續更新的 ID 保留，兩者之後都重啟）：HEAD ok，突變 a、f 也 ok。HEAD 只對持續更新的 ID 寫 `(new)`。
- 假綠燈判定：沒有假綠燈。
  - 新測試用真實 `src/freeze-monitor` 搭配替身 helper，期望值是人工推導的字面值（`restarts=2(new)`、筆數），不是重算實作。
  - 突變 a、b 的紅燈是真的，綠燈由目標行為驅動。
  - S1、N1 屬於證據持久力，依 verification.md 不阻擋。

**`BASH_FUNC_date%%` 替換 date 的查核**

- 生效：收集器開頭把 `PATH` 寫死（`src/freeze-monitor:5`），所以 PATH 上的替身無效；bash 從環境匯入函式則不受 PATH 影響。
  - HEAD 跳時間的案例是綠的，等於反證跳時間確實生效，否則會寫出 `(new)`。
  - reviewer 實跑看到的 epoch 跳動與 GAP 事件見 N3。
  - CI 是 ubuntu-24.04（bash 5.2），同樣支援這個機制。
- 對收集器其他 `date` 用途的影響：函式只對 `date +%s` 加 offset。
  - `date +%F`：跨日輪替與 `log_date`（`:85`、`:570`）；
  - `date --iso-8601=seconds`：檔名、時間戳、ROTATE、STOP（`:84`、`:573`、`:592`、`:635`）；
  - 以上都走 `command date`，不受影響，所以跳時間不會觸發輪替，檔名也不變。
  - `report_previous_session` 的 `date +%s` 在 offset 檔建立前就執行了。
  - 跳時間的那一輪會寫 GAP 事件，並切到寫穿模式（FLUSH）。測試只篩 `Docker anomaly`，所以不受影響。
- flaky 風險：
  - 真實時間跨過午夜時會輪替，但輪替不動 `last_restart_counts`，事件照寫。
  - offset 檔在第 n 次 helper 呼叫內寫入，從下一個樣本開始生效。替身 helper 斷言 `calls == len(rounds)`，可以確認每一輪都有執行。
  - 測試環境繼承 `os.environ`，開發者 shell 裡的 `FREEZE_WATCH_*` 可能干擾，這和既有的 m1_n1 寫法相同，不另列。
  - 判定低風險。

**逐條 AC**

| AC | 判定 | 證據 |
|---|---|---|
| AC-1 | 通過 | partial 與逾時兩個案例都用真實收集器；紅燈基線：突變 a 讓 partial 失敗（reviewer 重現）；逾時案例在 a 下仍綠，README 已誠實揭露原因。可改善處見 S1 |
| AC-2 | 通過 | 跳一天後不寫事件、不跳時寫 1 筆（控制組）；突變 b 只讓 AC-2 失敗（reviewer 重現）；替換 date 確實生效。文字與邊界見 N1、N3 |
| AC-3 | 通過 | `unavailable:error` 的描述與 `unavailable_reason`、`collect` 的例外範圍一致（`src/container_probe.py:66-77`、`:195-197`）：ValueError、SubprocessError（含 `docker context inspect` 失敗或超過 0.5 秒）和其他 OSError 都歸到 `error`，所以建議檢查 context 與 socket 是對的；文件指令照抄實跑可用；`ls -l /var/run/docker.sock` 在本機輸出 `srw-rw---- root docker`，註解提到 rootless 等其他 unix 路徑。改善見 N2 |
| AC-4 | 通過 | issue 2 README：文件清單的兩份報告都存在；涉及檔案的 ci.yml（03a15aa 加 cairo）與 troubleshooting 都屬實；風險段「已知邊界」與 `src/freeze_watch.py:1540`、`:1946` 的 `[-60:]` 和 `docs/architecture.md:248-251` 一致。evidence.md 的綠燈命令：reviewer 在 HEAD 重跑得到 Ran 18 tests OK，與 s1-green-py310.log 的 18 個相符；紅燈 log 是 Ran 2 tests，與記錄的兩個測試 ID 相符 |
| AC-5 | 通過 | `src/freeze_watch.py:149` 改成 `tuple[int, int \| float \| None]`，對應 `:161` 的 `math.inf`；只改註記，check.sh 全過 |

### 相關失敗面

| 失敗面 | 輸入／狀態 | 預期 | 覆蓋 | 結論 |
|---|---|---|---|---|
| 單一容器查詢失敗（partial、NA） | 1 → NA → 2 | 寫 `(new)` | 新測試，突變 a 會紅 | 通過；1 → NA → 1 不誤報只有 reviewer 的實跑證據（S1） |
| helper 逾時（exit 124） | 1 → 卡住 → 2 | 寫 `(new)` | 新測試，突變 d 會紅 | 通過 |
| helper 失敗（exit 1） | 跨失敗輪次 | 不重寫、不漏寫 | 既有 m1_n1，突變 c 會紅 | 通過 |
| 超過一天未更新 | 跳 90000 秒 | 刪除基準 | 新測試，突變 b 會紅 | 通過；門檻精度見 N1 |
| 同表新舊混合 | 一個過期、一個持續更新 | 刪過期、留持續更新 | reviewer 實跑 | 通過 |
| 初次出現的 ID | 第一筆 restart=1 | 不寫 `(new)` | 突變 g 讓全部紅 | 通過 |

### 需求、架構、安全、品質

- 範圍：
  - diff 只碰 README 列出的檔案；`src/freeze-monitor` 沒有修改（`git diff --stat` 為空），符合「原則上不修改」。
  - AC 和 #5 範圍 1～4 項一一對應，N1 依決定不處理，沒有超出範圍。
  - #5 原文建議「把 awk 抽出來，用字面值 prev／now 測試」，AC-2 改用替換 date 的真實 shell 測試。這是等價的驗證手段，還避免修改產品程式碼，依 acceptance.md「選擇等價的實作／驗證命令不需再次核准」。#5 的字面情境 reviewer 已實跑通過。
- 安全：
  - 新的測試只在 TemporaryDirectory 內執行，helper 是替身，不碰真實 Docker；check.sh 另外設了 `DOCKER_HOST=unix:///nonexistent`。
  - 文件指令只做唯讀 GET。
  - artifacts 沒有機敏資料（見 N6）。
- 品質：
  - 新的替身 helper 和 m1_n1 有部分重複，實作者已揭露，並以手術式修改為由沒有改寫既有測試，合理。
  - 行內 `import os`、`import subprocess` 沿用檔內既有寫法。
  - 小瑕疵見 N4。
- 提交訊息沒有 AI 署名。

### 豁免、待確認與限制

- 核准查核：
  - Small + Low，不需核准 commit。
  - 核准來源記錄了使用者 2026-11-06 的原話「合併進 main 然後照建議開後續 issue」，以及同日選擇 #5。
  - `git diff c686ee6 HEAD -- docs/issues/issue-5/README.md` 只改了任務狀態、完成證據和 `**狀態**`，驗收條件區塊沒有變，所以沒有規格漂移。
- issue 2 文件：
  - issue 2 已合併，狀態是「等待外部驗收窗」。這次只補文件清單、涉及檔案、已知邊界與命令，沒有動狀態、外部驗收窗或核准表。
  - review-a7c2c36 N5 指出，這些修改必須放在下一個要重審的提交，本次審查涵蓋了。
- Gate 豁免紀錄缺漏見 S2，可以在記帳提交補上。
- 限制：
  - reviewer 沒有在 Python 3.10 重跑。新測試只用標準庫，也只透過 subprocess 驅動 bash，沒有用到 3.11 以後的語法。
  - CI 還沒在這個分支執行。
  - 文件指令實跑時查詢了本機真實 Docker（只讀），只記摘要。

## 流程判定

**PASS**

理由：
- 獨立審查完成，沒有 MUST FIX。
- AC-1～AC-5 都有可重現的證據，reviewer 獨立重跑了 check.sh 與 8 組突變。
- S1、N1 屬於證據持久力，S2 是記帳區段的補記，依 review-evidence.md 都不阻擋。
- 建議在保存本報告的記帳提交中補上 S2 的 `## Gate 豁免紀錄`。S1 若要修，會改到 tests，需要重新審查，可以另開 issue 或併入下一個本來就要審查的提交。
