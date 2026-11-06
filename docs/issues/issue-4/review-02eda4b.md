# 審查報告
- 審查日期：2026-11-06
- 範圍：完整交付（本地審查），`abd3a3d..02eda4b`，18 檔，+1201／−21
- Reviewed BASE SHA：abd3a3dbef60fb4a9e69d8ec07fa6d0d1d8fe455（等於 `git merge-base origin/main HEAD`，已核對）
- Reviewed HEAD SHA：02eda4b5bdfd1fcfa5bfb8a5306974961b09feaf
- Reviewed patch-id：7dc599b1dae89334697b56136c741333d3a27b89（`git diff abd3a3d HEAD | git patch-id --stable` 重算結果相同）
- 獨立 reviewer：Claude Code 隔離 subagent（Opus 5.5），不是原實作者；全程唯讀，worktree 前後 `git status --short` 都是空的
- Review artifact：docs/issues/issue-4/review-02eda4b.md
- 核准基線：`**核准 commit**` 為 fcac9ae（不是 `待提交`，不必另外推導）

## 問題與風險

### MUST FIX

**M1. SCN-002、SCN-004「高 CPU 前 5 依生命週期平均排序」沒有有效測試（假綠燈）**
- 位置：`tests/test_container_probe.py:552`、`:558`（SCN-002）；`:586`、`:593`（SCN-004 時間預算段）；`tests/test_container_probe.py:31`（既有測試也沒有檢查順序）。
- 問題：兩個測試的輸入列本來就照生命週期平均由高到低排（`10` 是 40%，`20` 是 1%）。退回模式下所有 `cpu_interval` 都是 None，就算排序鍵錯用區間值（全部是 −1），穩定排序也會照輸入順序輸出 `['10','20']`。所以斷言分不出「依生命週期排序」和「沒有依生命週期排序」。
- 突變證據：在 `src/container_probe.py:213` 把 `if fallback:` 改成 `if False:`，讓退回時仍用區間值排序。`ProcessCpuIntervalTests`、`CounterTests`、`ProcessCpuIntervalDetailTests` 共 14 個測試全過；完整的 `test_container_probe` 加 `test_freeze_watch` 共 90 個也全過（`/usr/bin/python3 -m unittest test_container_probe test_freeze_watch` → `Ran 90 tests ... OK`）。
- 正式程式碼本身是對的：reviewer 用反序輸入（`20` 在前）探測 HEAD，輸出是 `[('10', 40.0, None, 'no_previous'), ('20', 1.0, None, 'no_previous')]`。但依 verification.md，「假綠燈一律不得作為證據」。evidence.md 的驗收對照把 SCN-002、SCN-004 判為「通過」，可是這個 Then 子句在交付的證據裡沒有涵蓋。
- 建議（只改測試）：把 `:552` 與 `:586` 的 rows 改成 `[['20','S','1','1',...], ['10','S','40','1',...]]`，斷言不變。reviewer 已在 scratch 複本實測：未突變版 7 個測試全過；M1 突變版有 4 個失敗（SCN-002 三個 subTest 與 SCN-004）。修完把這個突變補進 evidence.md 的突變表。

### SHOULD FIX

**S1. 儀表板遇到 `cpu_fallback` 不是字串時會拋出未攔截的 TypeError**
- 位置：`src/freeze_watch.py:895-897`。
- 問題：`fallback` 取自 JSON，沒有檢查型別。值是 list 或 dict 時，`{...}.get(fallback, fallback)` 會丟出 `TypeError: unhashable type`，而這段在 try 區塊外面。呼叫端 `src/freeze_watch.py:1963` 在 `refresh()` 裡，沒有 try。依 PyGObject 的慣例，timeout callback 拋例外時會印出 traceback 並視為回傳 False，定時刷新可能因此停止；`:1570`、`:1576` 的選取 callback 也會受影響。
- 實測：`cpu_fallback=['x']` 與 `{'a':1}` 都得到 `EXC TypeError`。其他異常輸入都能容錯：process 是 str 或 int、混入非 dict、processes 是 dict、`'NA'`、缺 pid 都顯示「程序：未知」；`cpu_interval` 是字串或 NaN 時顯示 `abc%`、`nan%`，不會崩潰。
- 觸發條件：helper 只會寫出字串，所以要 TSV 被竄改或損壞才會發生，機率低。但這是新增的崩潰路徑，舊程式碼在這種輸入下是容錯的。
- 建議：改成 `p.get('cpu_fallback') if isinstance(p.get('cpu_fallback'), str)`，或把整段排序說明移進既有的 try；補一個異常 JSON 的測試。

**S2. TBD-3 與 architecture.md 對輪替限制的描述不正確**
- 位置：`docs/architecture.md:220-222`（"with more than 8 tracked running containers the rotation makes each one start again from `no_previous`"）、`docs/issues/issue-4/README.md:125`（「每次輪到都從『尚無前一筆』開始，看不到區間值」）。
- 實測：reviewer 用假 Engine 與假 `/proc`，在 HEAD 的 `collect()` 連跑 4 輪，統計每輪深度採樣中有區間值的容器數（`r0` 一律 0，下表是 r1～r3）：

  | 追蹤中的執行容器 | 有區間值的容器（r1～r3） |
  |---|---|
  | 8 | 8 |
  | 9 | 7 |
  | 12 | 4 |
  | 15 | 1 |
  | 16 | 0 |
  | 20 | 0 |

- 原因：深度游標每輪前進 8 格，連續兩輪都輪到的容器會保留讀數。超過 8 個時不是全部看不到，而是每輪有 max(0, 16−N) 個容器有區間值；到 16 個以上才每輪都是 `no_previous`。
- 建議：改寫兩處描述。TBD-3 的影響評估（要不要保留沒輪到的容器的讀數）也要依正確數字重新陳述。

**S3. 深度採樣用 Docker top 的 PID 去讀主機 `/proc`，前提是 daemon 與主機共用 PID namespace，但沒有交叉核對（需決策）**
- 位置：`src/container_probe.py:159`、`:167`；`README.md:235-237`。README 只排除 TCP／SSH，理由是「host PID … would otherwise refer to a different machine」。
- 問題：Docker Desktop for Linux 或其他由 VM 提供的 Unix socket（例如 Lima、Colima），`docker context` 指向的仍是本機 Unix socket，會通過 `endpoint()`，但 top 回的是 VM 內的 PID。issue 4 之前這只讓 PID 顯示錯誤；現在會讀主機上同號的無關程序：第一輪記下讀數，第二輪就算出「看起來合理」的區間 CPU，冠上容器程序的名稱。這正是 README 的「最大風險：區間 CPU 算錯但看起來合理」。starttime 檢查擋不住，因為兩輪讀的是同一個主機程序。
- 本機實況：reviewer 對真實 Docker 唯讀跑 helper 兩輪，15 個程序的 `/proc/<pid>/stat` comm 與 top 的 comm 不一致數為 0，所以這台主機沒有這個問題。
- 待決問題：要不要支援或防範 VM 型 daemon？
- 可選做法：(a) 比對 `/proc/<pid>/stat` 括號內的 comm 與 top 的 `name`（前 15 字元做前綴比對；ps 對 zombie 可能附加 ` <defunct>`），不一致時整個容器記為 `proc_unreadable`；(b) 只在文件寫明「需要 daemon 與主機共用 PID namespace，不支援 Docker Desktop／VM 型 socket」。
- reviewer 建議 (a)：大約 3 行，成本可以忽略，能把靜默誤判變成標示得出來的退回。

### NICE TO HAVE

- **N1. `isdigit()` 防護與 1024 邊界沒有測試覆蓋**（`src/container_probe.py:149`、`:157`）。
  - 突變 `if not pid.isdigit()` 改成 `if False` 時，90 個測試全過；`> MAX_PROC_READS` 改成 `>=` 時也全過。實測剛好 1024 個時不會退回，符合規格「超過 1024 個」。
  - 實際穿越風險低：PID 欄由 root 的 dockerd 產生，容器內無法注入；`'../x'` 這類字串會被擋下；Unicode 數字（例如 `'١٢'`）通過 `isdigit()` 但只會 FileNotFoundError 後略過；開頭是 0 的 `'010'` 核心不接受，同樣略過。
  - 可改成 `pid.isascii() and pid.isdigit()`，並補 `'../1'` 與剛好 1024 個的測試。
- **N2. 新程序用自身存活時間當分母，短命程序容易擠進前 5（需決策；已核准的 SCN-003 行為）**（`src/container_probe.py:183-186`）。
  - 實測：在讀取前 0.01 秒啟動、用了 1 tick 的程序顯示 100.0%。healthcheck 這類短命程序可能排在持續吃 30% 的長壽程序前面。
  - 可選：設最短存活時間（例如不足 1 秒記為 null），或改用區間長度當分母。維持現狀也合規格。
- **N3. 區間值相同或都是 None 時，順序取決於 Docker top 的輸出順序**（`src/container_probe.py:216`）。
  - 可加生命週期平均當第二排序鍵：`key=lambda p: (-1 if p['cpu_interval'] is None else p['cpu_interval'], p['cpu'])`。
- **N4. 被竄改的 cache 損失範圍**（`src/container_probe.py:179`）。
  - `procs` 值是 `[start, "x"]` 或 `[start, None]` 且 start 相符時，`ticks >= old[1]` 會丟 TypeError，`collect` 攔下後該容器本輪變成 `unavailable_or_timeout`；下一輪會自行恢復。
  - 這和既有計數器 cache 的容錯程度一致（`cpu_percent` 的 TypeError 也是整列 unavailable）。`at` 是 NaN 時會寫出 `cpu_interval: NaN`，儀表板顯示 `nan%`。
  - 要求不高，可加 `isinstance(old[1], int)` 與 `math.isfinite(previous_at)`。
- **N5. 邊界 `born == previous_at` 與「ticks 倒退」守衛沒有測試**。
  - 把 `<=` 改成 `<`、或拿掉 `ticks >= old[1]` 的突變都會存活。
  - 前者只差 1 tick 的精度；後者在核心上不會發生（utime/stime 單調遞增，同 PID 同 starttime 就是同一個程序），影響可以忽略，列出供參考。

## 已查核維度

### 驗收與證據

- **check.sh**：在 worktree 執行 `env -u DISPLAY -u WAYLAND_DISPLAY bash scripts/check.sh`，exit 0，`Ran 139 tests in 90.152s`，`OK`，沒有 skipped，`All checks passed.`。與 evidence 的 139 = 129 + 10 相符。
- **核准查核**：`git diff fcac9ae HEAD -- docs/issues/issue-4/README.md` 的變動只在文件清單、核准紀錄（待提交→fcac9ae、待核准→已核准）、首要驗證第 3 點（改為主機對照組，有 TBD-2 使用者決定）、待確認事項、Timeline、狀態。`## Gherkin 驗收劇本` 區塊零差異，沒有漂移。
  - 核准來源是 2026-11-06 使用者回答三題，並選「核准全部」，日期與內容可追溯。原話在對話中，reviewer 無法直接取得原文，以 README 紀錄為準。
  - fcac9ae 承載的 Gherkin 與 HEAD 相同，核准 commit 有效。
  - GitHub issue #4 的「初步方向」寫「除以…核心數」，已被核准規格「100% 為一個核心」取代，實作依核准規格。
- **SCN-001**：通過。
  - 期望值是獨立手算：pid 99 為 (700−200)/100/10×100 = 50.0；閒置程序 0.0；snapshot 是字面值。
  - 實作者的排序突變與分母突變有效。reviewer 另做 50% 工作週期的主機對照組：`cpu_interval` 49.3，ps 平均 31.5，理論值約 3.5/11 = 31.8，比實作者的 100% 飽和對照組更能排除上限截斷。
  - 儀表板字串有斷言。
- **SCN-002**：「區間記為未知」與「標示原因」有效；「依生命週期平均排序」是假綠燈，見 M1。
  - 收集器重啟會清 cache：`src/freeze-monitor:82` 啟動時執行 `rm -f docker-counters.json`；helper 失敗、逾時或 unavailable 也會清（`:267`、`:290`）。SCN-002 的說法成立。重開機後 CLOCK_BOOTTIME 歸零，`at <= previous_at` 也會擋下。
- **SCN-003**：通過。
  - 手算 53.3 = 400/100/7.5×100、50.0 = 250/100/5×100；`50` 在上一輪之前就啟動，結果是 null；`30` 已結束，不留在 snapshot。
  - starttime 突變與「拿掉 born 分支」「born 分支改用區間分母」兩個 reviewer 突變都被抓到。
  - 實作者主動揭露先調整舊 tick 才讓 starttime 突變有效，屬證據品質的一部分，不扣分。
- **SCN-004**：數量、時間、權限三種退回與 `snapshot is None` 都有斷言；拿掉時間檢查的突變被抓到。排序子句見 M1。
  - 「其他容器不受影響」：`read_proc_times` 每個容器呼叫一次，沒有共用狀態，依程式碼推理成立。
- **SCN-005**：通過。
  - `FIELDS` 沒有改；BASE 與 HEAD 都是 24 欄，reviewer 的真實採樣兩輪也都是 24 欄。
  - 舊列顯示有斷言；cache 只留下仍存在的深度程序。真實 cache 權限 0600，每筆是 `[start, ticks]` 兩個值，沒有名稱。
- **被修改的既有測試**：只有 `test_bounded_processes_preserve_dstate_and_never_argv`：解包改成 5 個值、欄位集合加兩個鍵，都對應 SCN-001 核准的行為變更，其餘斷言不變，理由成立。
- **reviewer 的真實 Docker 唯讀採樣**：在 scratchpad state 目錄跑兩輪 `container_probe.py`。
  - 第一輪 exit 0、0.13 秒、15 個程序都是 `no_previous`；第二輪 exit 0、0.11 秒、15 個程序都有區間值；cache 有 6 個容器。
  - 與 evidence 一致。

### 相關失敗面

- **tick 換算**：使用 `os.sysconf('SC_CLK_TCK')`；utime、stime、starttime 取自最後一個 `)` 之後的第 11、12、19 欄，對應 proc(5) 的第 14、15、22 欄，正確。comm 含括號或空白的情況有測試。截斷的 stat 或沒有括號的 stat 會退回 `proc_unreadable`（reviewer 實測）。
- **時鐘同域**：`/proc` 的 starttime 以開機為基準，與 CLOCK_BOOTTIME 同域，讀取者在主機的 time namespace。`at` 在讀完全部 stat 後才取，誤差最多 0.2 秒，相對 30 秒的週期小於 0.7%。CLOCK_BOOTTIME 包含 suspend 期間，而 suspend 時 tick 不增加，所以 suspend 會讓區間值偏低，不會偏高。
- **邊界**：`born == at` 與 `born > at` 回傳 None，沒有除以零；時鐘沒前進會退回 `no_previous`，有測試；`born == previous_at` 會納入計算（N5）。
- **PID 重用與 ticks 倒退**：靠 starttime 判斷 PID 重用，正確；倒退守衛見 N5。
- **previous 結構損壞**：`procs` 不是 dict、`at` 不是數字、previous 不是 dict 都退回 `no_previous`；值不是 list 時該程序記為 null；值是 `[start, 非數字]` 見 N4。舊 cache 沒有 `procs` 鍵時退回 `no_previous`。
- **預算**：
  - 數量檢查在讀取前；時間檢查在每次讀取前，所以最多超出一次讀取的時間。
  - `/proc` 讀取不受 helper 的 6 秒 deadline 管，但 8 個深度容器最多合計 1.6 秒。deadline 過了之後，下一個 Engine 呼叫會立即 TimeoutError，所以總時間大約 6 秒加 0.2 秒，仍在外層 `timeout -k 1s 8s` 內。
  - 讀的是 stat，不是 cmdline，不會等 mmap_lock，凍結時也比較不會卡住。
  - 實測主機 641 個 stat 共 17 毫秒，換算 1024 個約 27 毫秒，遠低於 0.2 秒。
- **輪替**：TBD-3 的描述見 S2。

### 需求、架構、安全、品質

- **安全**：
  - 只讀 `/proc/<pid>/stat`，不讀 argv；cache 只存 `{at, procs: {pid: [start, ticks]}}`；名稱沿用既有的 comm（80 字元上限）。
  - 路徑穿越見 N1，實際風險低。PID namespace 的假設見 S3。
  - cache 寫入流程不變：0600 權限、原子替換、umask 077。
- **公開 repo 的 artifacts**：
  - check.log、red.log、mutation-*.log 裡有 `/home/kevin/...` 與 scratchpad 路徑、主機 PID 2797998；evidence.md 有 `runwukong,runtelenexus`。
  - 這些在先前的 issue（issue-1、issue-2 的 artifacts）與 README 早已公開，沒有 token、容器 ID 或名稱外洩。real-docker-summary 刻意只保存摘要，處理得當。
- **文件**：
  - README 英文版與 zh-TW 版內容對等，與實作一致：100% 為一個核心、同時列出生命週期平均、四種退回條件。
  - architecture.md 對計算、starttime、新程序、`cpu_interval`、`cpu_fallback`、cache 內容的描述都正確，只有輪替那句不正確（S2）。
- **品質**：
  - 新增三個小函式，沒有新的設定項，風格與既有程式碼一致：例外分類、`dict(...)`、中文說明。
  - `process_sample` 改成回傳 5 個值的 tuple 可以接受；沒有明顯重複或過度設計。
  - GitNexus 沒有登錄本 repo；`process_sample` 只在 `collect:348` 與測試中呼叫，影響範圍已核對。

### 豁免、待確認與限制

- 沒有 Gate 豁免紀錄。
- TBD-1、TBD-2 已解決，並有日期與使用者選項。
- TBD-3 標示「待確認、不阻擋」：本機只有 6 個執行中的追蹤容器，不阻擋的理由成立，但描述需依 S2 更正。
- 實作者揭露主機對照組沒有經過 Docker top，這是正當的測試限制揭露，不構成缺失。reviewer 的真實唯讀採樣與 comm 比對補上了這段在本機的證據。

## 流程判定

RETURN TO execute-task

理由：M1。SCN-002、SCN-004 的 Then「高 CPU 前 5 依生命週期平均排序」只有一個無法區分對錯的斷言，突變存活，屬於必要驗收的證據缺口（假綠燈）。正式程式碼經 reviewer 探測是正確的，修正只要改兩組測試的輸入順序並補突變證據。建議同時處理 S1（新增的儀表板崩潰路徑）與 S2（文件描述不正確），S3 需要使用者決定處理方式。
