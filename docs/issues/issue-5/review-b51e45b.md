# 審查報告
- 審查日期：2026-11-06
- 範圍：完整交付（本地審查），BASE..HEAD 共 5 個提交（c686ee6、c315961、53481ee、efd8c16、b51e45b），重點查核 efd8c16 之後的增量 b51e45b
- Reviewed BASE SHA：9a8807b1756e4453199bdefdff746acdf105e5cd
- Reviewed HEAD SHA：b51e45b3c81176f5519d60091aa34c388d6cb800
- Reviewed patch-id：1706856b8bc5cc4ab3bc8f7c5d377b867170e465（reviewer 重算，相符）
- 獨立 reviewer：Claude Code 隔離 subagent（不是原實作者；全程只讀，沒有修改受審檔案，沒有 commit／push，沒有啟停容器）
- Review artifact：docs/issues/issue-5/review-b51e45b.md

## 問題與風險

### MUST FIX

無。review-efd8c16 的 M1 已修正，驗證結果見下方。

### SHOULD FIX

無。

### NICE TO HAVE

**N1：「限制」這一條指的是哪個突變，讀起來不清楚**

- 位置：`docs/issues/issue-5/README.md:78`。
- 原文是「逾時案例在這個突變下仍然通過」，原本緊接在整份取代的敘述後面。現在前面換成四種突變的表格，「這個突變」已經看不出是哪一個。
- 從表格看，逾時案例在四種突變下其實都是 ok。
- 建議改成「逾時案例在表中各突變下都通過」，或直接寫明「整份取代」。這是純措辭，不影響判定。

上一輪 c315961 審查的 N1（門檻精度）和 N6（artifacts 內的本機路徑）依使用者決定不處理，本次不再列出。

## 已查核維度

### 驗收與證據

**check.sh**

| 環境 | 命令 | 結果 |
|---|---|---|
| reviewer 唯讀 worktree wt-review-i5c（detached b51e45b），`/usr/bin/python3` 3.14.4，沒有 DISPLAY，走 xvfb-run | `env -u DISPLAY -u WAYLAND_DISPLAY bash scripts/check.sh` | exit 0；Ran 129 tests in 90.243s，OK，0 個跳過；All checks passed；real 1m38s（與突變測試平行執行） |

repo 內的 `artifacts/check.log` 是 Ran 129 tests in 90.267s、OK、All checks passed，與 reviewer 的結果一致。

**對 HEAD 重跑突變 a～h**

做法與前兩輪相同：從 b51e45b 用 `git archive HEAD src tests` 匯出新的複本，突變腳本也與前兩輪相同。命令是在各複本的 tests/ 下執行 `RestartBaselineTests` 加 m1_n1。

| 代號 | 突變 | partial | timeout | AC-2 | m1_n1 | 與 c315961／efd8c16 相比 |
|---|---|---|---|---|---|---|
| a | 整份取代 | **FAIL**（`0 != 1`） | ok | FAIL | ok | 已修正：在 efd8c16 是 ok |
| b | 拿掉一天刪除 | ok | ok | FAIL | ok | 相同 |
| c | 拿掉 `unavailable*` 提早 return | ok | ok | ok | FAIL | 相同 |
| d | c 加 a | **FAIL**（`0 != 1`） | FAIL | FAIL | FAIL | 已修正：在 efd8c16 是 ok |
| e | 門檻改 80000 | ok | ok | ok | ok | 相同（門檻精度不處理） |
| f | 拿掉合併 awk 的 `$11 ~ /^[0-9]+$/` | **FAIL**（`2 != 1`，多一筆 `restarts=1(new)`） | ok | ok | ok | 維持 efd8c16 的修正 |
| g | 拿掉 `($12 in last)` | FAIL | FAIL | FAIL | FAIL | 相同 |
| h | 未修改 | ok | ok | ok | ok | 基線 |

- partial 案例在 a、d、f 都失敗，其他突變沒有退步。
- 突變 a 在 c315961 是被 partial 與 AC-2 兩個測試抓到，現在也一樣。
- reviewer 的額外情境：1→NA→1 不寫事件，在 h ok、在 f FAIL；同一張表新舊混合，在 h ok。
- 這次的 5 輪序列 `[1, NA, 1, NA, 2]`，就是上一輪 reviewer 在 scratchpad 實測過的候選序列之一。

**證據敘述與 artifacts 是否對 HEAD 成立**

- `mutation-control.log`、`mutation-replace.log`、`mutation-noprune.log`、`mutation-na-baseline.log` 四份 log 的逐測試結果，與 README 第 71–76 行的表格完全一致，也與 reviewer 對 a、b、f、h 的重跑一致。
- log 內 traceback 的行號都對得上 HEAD 的 `tests/test_container_probe.py`：
  - 第 566 行：partial 案例的 `assertEqual(len(alerts), 1, alerts)`；
  - 第 582 行：AC-2 的對照組；
  - 第 584 行：AC-2 的跳時間案例。
  - 所以這些 log 確實是用目前的測試跑出來的。
- README 第 66–69 行如實記錄了 partial 案例三版的歷程，包括上一輪只重跑 NA 突變而漏掉整份取代突變這件事。

**逐條 AC**

| AC | 判定 | 證據 |
|---|---|---|
| AC-1 | 通過 | 規格寫明的紅燈基線（整份取代讓 partial 失敗）在 HEAD 成立，「把 NA 存成基準」這個回歸也抓得到；逾時案例保護的是「逾時後基準仍在」 |
| AC-2 | 通過 | 突變 b 只讓 AC-2 失敗；跳時間的案例本身就是替身 `date` 生效的證據 |
| AC-3 | 通過 | 指令照抄實跑：exit 0，第一行 `ok`，7 列容器。reviewer 先在呼叫端設 `py=KEEP`，再用 `.` 在同一個 shell 執行整個區塊，執行後 `py` 仍是 `KEEP`，確認子 shell 不會留下或覆蓋 `py` |
| AC-4 | 通過 | 增量沒有改到，結論沿用前兩輪 |
| AC-5 | 通過 | 增量沒有改到，結論沿用前兩輪 |

### 相關失敗面

| 失敗面 | 覆蓋 | 結論 |
|---|---|---|
| partial 時基準被清掉 | partial 案例（突變 a、d 會紅）＋ AC-2 對照組 | 通過 |
| partial 時 NA 被存成基準 | partial 案例（突變 f 會紅） | 通過 |
| 逾時、helper 失敗、一天刪除、初次出現的 ID | 結果與前兩輪相同 | 通過 |

### 需求、架構、安全、品質

- 增量只改 tests、troubleshooting、issue 5 的 README、報告與 artifacts，`src/` 沒有修改。
- 新的 partial 案例用 `count`、`partial` 兩個區域變數，與 AC-2 測試的 `worker`、`gone` 寫法一致。註解寫明每一輪各自抓哪一種回歸。
- troubleshooting 指令包回子 shell，不執行 env 檔的內容，後備值與收集器一致。

### 豁免、待確認與限制

- `review-efd8c16.md` 已保存。Timeline 記錄了 RETURN 與這次的修正。Gate 豁免紀錄沿用 53481ee 補上的內容。`**狀態**` 是「待獨立審查」，與目前流程相符。
- AC 本文從 efd8c16 之後沒有再修改，不需要重新核准。
- 限制：reviewer 沒有在 Python 3.10 重跑，CI 也還沒在這個分支執行（Gate 豁免紀錄已揭露）。文件指令實跑時查詢了本機真實 Docker，只讀、只記摘要。

## 流程判定

**PASS**

理由：
- 獨立審查完成，沒有 MUST FIX。
- AC-1～AC-5 的必要驗收都有對 HEAD 成立的證據。reviewer 對 HEAD 獨立重跑了突變 a～h 與 check.sh，結果與 README、artifacts 一致。
- N1 是純措辭，不阻擋，可以在記帳提交外另行處理，或不處理。
