# 審查報告
- 審查日期：2026-11-06
- 範圍：完整交付（本地審查），BASE..HEAD 共 4 個提交（c686ee6、c315961、53481ee、efd8c16），重點查核 c315961 之後的增量
- Reviewed BASE SHA：9a8807b1756e4453199bdefdff746acdf105e5cd
- Reviewed HEAD SHA：efd8c166e1ddc693646cd068bdda62b73dcc69be
- Reviewed patch-id：0be166e98b709a50af9e941c61cbe76e6c757a69（reviewer 重算，相符）
- 獨立 reviewer：Claude Code 隔離 subagent（不是原實作者；全程只讀，沒有修改受審檔案，沒有 commit／push，沒有啟停容器）
- Review artifact：docs/issues/issue-5/review-efd8c16.md

協調者提到的記帳提交 `bb5a7ea` 實際 SHA 是 `53481eed60641174c1fb1707b5da945492062a31`。這筆提交只新增 review-c315961.md，並改了 README 的 Gate 豁免紀錄、Timeline 與 `**狀態**`，都屬於記帳區段，沒有其他內容。

## 問題與風險

### MUST FIX

**M1：partial 案例改成 4 輪之後，抓不到 AC-1 要求的紅燈基線（整份取代突變）**

- 位置：`tests/test_container_probe.py:559-570`（`test_ac1_partial_round_keeps_the_restart_baseline`）。
- 規格：`docs/issues/issue-5/README.md:27` 的 AC-1 要求「把合併基準的 awk 暫時換回 f1b9bfa 的整份取代寫法，partial 那個案例必須失敗」。
- 重現：在 scratchpad 複本做突變 a（合併 awk 換回整份取代），在 tests/ 下跑 `python3 -m unittest -v test_container_probe.RestartBaselineTests ...`。HEAD 版的 partial 案例現在是 **ok**；c315961 版在同一個突變下是 FAIL。
- 原因：新增的第 3 輪 `restart_count=1` 會重新建立基準。整份取代在 partial 那一輪清掉基準，第 3 輪又把基準設回 1，第 4 輪 2 > 1，照樣寫出唯一一筆 `restarts=2(new)`。所以這個測試只抓得到「NA 被存成基準」（突變 f），抓不到「基準被清掉」，也就是 review-a7c2c36 S1 原本要補的那個回歸。
- 現在突變 a 只剩 AC-2 的對照組會紅，AC-1 本身已經沒有保護。
- 不實證據：`docs/issues/issue-5/README.md:66` 仍然寫「partial 案例 FAIL」，引用的 `artifacts/mutation-replace.log` 是舊的 3 輪測試跑出來的，對 HEAD 不成立。
- 責任說明：這是 reviewer 上一份報告 S1 的建議（`[1, NA, 1, 2]`）本身有缺陷造成的。實作者照建議修改，不是實作疏失。
- 建議：改成 5 輪，同時抓兩種回歸。下面兩種序列 reviewer 都在 scratchpad 實測過（`candidate_tests.py`）：
  - `[1, NA, 2, NA, 2]`，斷言只有 1 筆，而且內容含 `restarts=2(new)`；
  - `[1, NA, 1, NA, 2]`，斷言相同。
  - 結果：未突變的 h 兩種都 ok；突變 a、f、d 兩種都 FAIL。每個案例約 15 秒，比現在多一輪。
  - 修改後要對 HEAD 重跑突變 a 與 f，更新 `artifacts/mutation-replace.log`（或另存一份）、`artifacts/mutation-na-baseline.log`，以及 README 第 66–67 行的敘述。

### SHOULD FIX

無。

### NICE TO HAVE

**N1：手動執行的指令會在使用者目前的 shell 留下 `py` 變數**

- 位置：`docs/troubleshooting.md:130`。
- 舊版指令包在 `( … )` 子 shell 裡，新版直接在目前的 shell 設定 `py`，會覆蓋使用者原本同名的變數。
- 影響輕微。可以包回子 shell，或改用比較不會撞名的變數名稱。

上一輪的 N1（門檻精度）與 N6（artifacts 內的本機路徑）依使用者決定不處理，本次不再列出。新的 `mutation-na-baseline.log` 同樣含有 scratchpad 路徑，屬於 N6 的範圍。

## 已查核維度

### 驗收與證據

**check.sh**

| 環境 | 命令 | 結果 |
|---|---|---|
| reviewer 唯讀 worktree wt-review-i5b（detached efd8c16），`/usr/bin/python3` 3.14.4，沒有 DISPLAY，走 xvfb-run | `env -u DISPLAY -u WAYLAND_DISPLAY bash scripts/check.sh` | exit 0；Ran 129 tests in 87.064s，OK，0 個跳過；All checks passed；real 1m35s（與突變測試平行執行） |

**突變複跑**

複本由 `git archive efd8c16 src tests` 匯出，突變腳本與上一輪相同。命令是在各複本的 tests/ 下執行 `RestartBaselineTests` 加 m1_n1。

| 代號 | 突變 | partial | timeout | AC-2 | m1_n1 | 與 c315961 相比 |
|---|---|---|---|---|---|---|
| a | 整份取代 | **ok** | ok | FAIL | ok | **退步**：partial 從 FAIL 變成 ok（M1） |
| b | 拿掉一天刪除 | ok | ok | FAIL | ok | 相同 |
| c | 拿掉 `unavailable*` 提早 return | ok | ok | ok | FAIL | 相同 |
| d | c 加 a | **ok** | FAIL | FAIL | FAIL | partial 從 FAIL 變成 ok（M1） |
| e | 門檻改 80000 | ok | ok | ok | ok | 相同（上輪 N1，不處理） |
| f | 拿掉合併 awk 的 `$11 ~ /^[0-9]+$/` | **FAIL** | ok | ok | ok | **已修正**：上輪 S1 的突變現在抓得到，多寫一筆 `restarts=1(new)`，與 artifacts/mutation-na-baseline.log 相同 |
| g | 拿掉 `($12 in last)` | FAIL | FAIL | FAIL | FAIL | 相同 |
| h | 未修改 | ok | ok | ok | ok | 基線 |

reviewer 的額外情境：1→NA→1 不寫事件，在 h ok、在 f FAIL；同一張表新舊混合，在 h ok。

**逐條 AC**

| AC | 判定 | 證據 |
|---|---|---|
| AC-1 | **未通過** | 規格寫明的紅燈基線（突變 a 讓 partial 案例失敗）在 HEAD 不成立，README 的證據敘述也不實（M1）。逾時案例不受影響 |
| AC-2 | 通過 | 突變 b 只讓 AC-2 失敗；替身 `date` 生效的證據已改成正確的推理（README:75） |
| AC-3 | 通過 | 新指令照抄實跑，結果見下方「文件指令」 |
| AC-4 | 通過 | 上一輪已查核，本次增量沒有改到 issue 2 的文件 |
| AC-5 | 通過 | 本次增量沒有改到 |

**文件指令**

照抄 `docs/troubleshooting.md` 的區塊，只把 `TMPDIR` 指到 scratchpad：

- 正常情況：bash -x 顯示實際執行 `/usr/bin/python3`（從 env 檔讀到），exit 0，第一行 `ok`，7 列容器。
- env 檔不存在：退回 `/usr/bin/python3`，exit 0，沒有錯誤訊息。
- env 檔有 `FREEZE_WATCH_PYTHON=` 空值：同樣退回 `/usr/bin/python3`。
- `sed … | tail -1` 取最後一筆，與 `src/freeze-watch` 的 awk（END 時印出最後一個值）語意一致。後備值與收集器的 `src/freeze-monitor:249` 一致。
- 本機沒有 zsh，所以沒有測 zsh。

### 相關失敗面

| 失敗面 | 狀態 | 結論 |
|---|---|---|
| partial 時基準被清掉（整份取代） | HEAD 的 AC-1 測試抓不到 | M1 |
| partial 時 NA 被存成基準 | 抓得到 | 已修正 |
| 逾時、helper 失敗、一天刪除、初次出現的 ID | 結果與上一輪相同 | 通過 |

### 需求、架構、安全、品質

- 增量只改 tests、troubleshooting、issue 5 README 與 artifacts，`src/` 沒有修改。
- 拿掉 `'fail'` 選項、補上 class 之間的兩行空白，正確。
- 新指令不再執行 env 檔的內容，比舊版安全。

### 豁免、待確認與限制

- **措辭修改沒有改變 AC 的語意**：AC-2 對照組由「只消失一輪」改成「消失不到一天」。受測行為（超過一天未更新才刪除）、檢查方式和紅燈基線都沒有變，只是讓描述符合測試實際的兩輪對照組，而且已在 Timeline 記錄使用者「照建議修完之後合併」的來源。判定不需要重新核准。
- **`**風險**: Low\` 的反斜線**：`docs/agents/readme-templates.md` 的兩份範本都寫成 `**風險**: Low | Medium | High\`，原文就有反斜線，維持原樣是對的。撤回上一輪 N4 的第三點。
- **Gate 豁免紀錄**：53481ee 已補上，內容與 issue 1 的格式和授權來源一致，上一輪的 S2 已解決。
- `**狀態**`：efd8c16 從「待合併」改回「待獨立審查」，與目前的流程相符。

## 流程判定

**RETURN TO execute-task**

理由：
- M1：AC-1 規格寫明的紅燈基線（整份取代突變要讓 partial 案例失敗）在 HEAD 不成立，README 第 66 行的證據也對 HEAD 不實。依 review-evidence.md，必要驗收有缺口，加上證據不實，必須退回。
- 修法明確：改成 5 輪序列，再依 M1 的建議重跑突變 a、f 並更新 artifacts。
- 其他增量（S1 的突變 f、N2、N3、N4、Gate 豁免紀錄）都已驗證正確。
