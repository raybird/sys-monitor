# 審查報告
- 審查日期：2026-11-06
- 範圍：完整交付（本地審查，第二輪），`abd3a3d..ef3c759`，22 檔，+1630／−21；修正差異 `02eda4b..ef3c759` 另外逐行讀過
- Reviewed BASE SHA：abd3a3dbef60fb4a9e69d8ec07fa6d0d1d8fe455（等於 `git merge-base origin/main HEAD`，已核對）
- Reviewed HEAD SHA：ef3c75972804747e1c2cc1365d5f8fab70b373cf
- Reviewed patch-id：469fbcab14aca86eccf41a066e823fe3b00300a0（`git diff abd3a3d HEAD | git patch-id --stable` 重算，結果相同）
- 獨立 reviewer：Claude Code 隔離 subagent（Opus 5.5），不是原實作者。全程唯讀，worktree 在審查前後執行 `git status --short` 都沒有輸出；沒有 docker exec，也沒有啟停容器
- Review artifact：docs/issues/issue-4/review-ef3c759.md
- 核准基線：`**核准 commit**` 是 12ac70b，已填寫，不是 `待提交`

## 問題與風險

### MUST FIX

無。

### SHOULD FIX

**S1. 名稱比對拿 ps 跳脫後的顯示字串去比核心原始 comm，正常主機上會固定誤判，並被寫成「另一個 PID namespace」（需決策）**
- 位置：
  - `src/container_probe.py:168`、`:175-176`
  - `docs/architecture.md:206-209`（"the daemon then sees another PID namespace"）
  - `README.md:229-230`、`README.zh-TW.md:158-159`
- 實測方法：在主機上啟動自己的短命程序，用 `prctl(PR_SET_NAME)` 設定 comm，再執行 procps-ng 4.0.4 的 `ps -eo pid,stat,pcpu,pmem,comm`。輸出依 moby `parsePSOutput` 的方式處理：以 ASCII 空白切欄，最後一欄用單一空格合併。處理結果交給 HEAD 的 `read_proc_times`。

  | 核心 comm | `LANG=C` 的 top 名稱 → 結果 | `en_US.UTF-8` 的 top 名稱 → 結果 |
  |---|---|---|
  | `very-long-proce`（15 bytes 截斷） | 相同 → 通過 | 相同 → 通過 |
  | `a(b)c` | 相同 → 通過 | 相同 → 通過 |
  | `睡眠工作`、`café` | `????????????`、`caf??` → `proc_unreadable` | 相同 → 通過 |
  | `a工作工作工`（15 bytes 切在多位元組字元中間） | `a??????????????` → 退回 | `a工作工作??` → 退回 |
  | `a  b`（連續空白） | `a b` → 退回 | `a b` → 退回 |
  | `abcdefghijklmn `（截斷後結尾是空白） | — | `abcdefghijklmn` → 退回 |
  | ` lead`（開頭空白） | `lead` → 退回 | `lead` → 退回 |
  | `x<TAB>z`、`bad\xff` | `x.z`、`bad?` → 退回 | `x?z`、`bad?` → 退回 |

- 頻率：
  - dockerd 用 C／POSIX locale 時（精簡伺服器常見），只要容器裡有一個程序名稱含非 ASCII 字元，就會觸發。
  - 用 UTF-8 時，觸發條件是：超過 5 個中日韓字的名稱被截斷、名稱含控制字元、開頭或連續空白，或用 setproctitle 一類方式改名後在第 15 byte 正好是空白。
  - 這類名稱在容器裡少見。本機 systemd 管理員環境是 `LANG=en_US.UTF-8`，dockerd 應該繼承這個值，但 environ 要 root 才讀得到，沒有直接證實。真實唯讀採樣 15 個程序都沒有誤判，與 evidence 一致。
- 後果：
  - 固定誤判時，只要那個程序還在，該容器每一輪都退回，issue 4 的效益在這個容器完全消失。
  - 標示的原因是「無法讀取 /proc」，architecture.md 還寫成 daemon 在另一個 PID namespace，診斷會被誤導。
  - 不會產生錯誤數字：退回後的行為就是 issue 4 之前的行為，而且有標示。
  - 這個行為形式上符合修訂後的 SCN-004（「名稱與 Docker top 回傳的不一致」），所以列為 SHOULD FIX，不是 MUST FIX。
- 暫時性誤判：程序在 top 與讀 stat 之間 exec 或改名、或 PID 結束後被重用。這要命中幾十毫秒的窗口，機率很低。但退回時 `snapshot` 是 None（`:210`、`:356`），下一輪會變成 `no_previous`，所以一次誤判會損失兩輪區間值。
- 待決問題：要不要排除 ps 表示法造成的誤判？
- 可選做法：
  - (a) 維持現狀，只修正 architecture.md：說明名稱不一致也可能是 ps 跳脫了非 ASCII 或空白字元，不一定是另一個 namespace。
  - (b) 只在核心 comm 是「可列印 ASCII、沒有開頭、結尾或連續空白」時才比對，其餘程序不比對。約 1 行。VM 情境下主機同號 PID 多半是 ASCII 名稱（kworker、systemd 等），偵測力保留。
  - (c) 改成以容器為單位判斷，例如沒有任何程序名稱相符，或多數不相符才退回。這也能容忍 exec 競態，但規則較複雜。
- reviewer 建議 (b)，並同時修正 architecture.md 的措辭。

### NICE TO HAVE

- **N1. 名稱比對的測試只能區分「第一個字元不同」**（`tests/test_container_probe.py:618-628`、`:630-637`）。
  - 突變：把 `:175` 改成 `process['name'][:1] == comm[:1]`，`ProcessCpuIntervalTests`、`CounterTests`、`ProcessCpuIntervalDetailTests` 全過。原因是測試用的 `python`／`sshd`、`node`／`node` 首字元剛好分得開。
  - `:631` 的 top 名稱 `very-long-process-name` 不是 procps 4.0.4 的實際輸出：實測 ps 也只輸出 15 字元 `very-long-proce`。測試仍然成立，但不代表真實的 ps。
  - 建議補一組首字元相同的不一致例子，例如 top 是 `node`、核心是 `nginx`。
- **N2. 被竄改的 cache 若 `at` 是極大整數，helper 會整個失敗**（`src/container_probe.py:213`）。
  - `math.isfinite(10**400)` 會丟 OverflowError，不在 `collect` 的 except 清單（`:360`、`:362`）裡。實測 `{'at': 1後面400個0}` 得到 `EXC OverflowError`。
  - 結果是那一輪 `unavailable:helper_failed`，整輪容器資料都是 unavailable。`src/freeze-monitor:290` 會刪掉 cache，下一輪自行恢復。
  - 同類情況：Docker 回非字串的 pid 或名稱時，`:159`、`:175` 會丟 AttributeError，同樣讓 helper 失敗。moby 的契約是 `[][]string`，實際不會發生。
  - 只有竄改自己的 0600 檔案才會觸發，可以改成 `isinstance(previous_at, float)`，或攔截 OverflowError。
- **N3. 區間值未知的程序一律排在所有已知程序之後，包括 0.0 的閒置程序**（`src/container_probe.py:223`）。
  - 實際影響：存活不到 1 秒的忙碌新程序，在有 5 個以上已知程序時排不進高 CPU 前 5。這是 1 秒門檻的自然結果，規格沒有規定未知程序的位置。
  - architecture.md:199-200 的 "Ties and unknown intervals rank by the lifetime average" 沒有寫出「未知排在已知之後」，可補半句。
- **N4. VM 情境下，如果 top 列出的 PID 在主機上全都不存在**，每個都走 `FileNotFoundError` 略過（`:162-163`），不會退回。
  - 詳情會顯示「依兩次採樣之間的區間 CPU 排序」，但每個程序都是「未知」，數字不會錯。
  - VM 內常見的小號 PID 在主機上多半存在，所以機率低，列出供參考。

## 已查核維度

### 驗收與證據

- **check.sh**：在 worktree 執行 `env -u DISPLAY -u WAYLAND_DISPLAY bash scripts/check.sh`，exit 0，`Ran 147 tests in 96.058s`，`OK`，跳過 0 個，`All checks passed.`。與 evidence 的 147 = 139 + 8 相符。
- **核准查核**：
  - `git diff 12ac70b HEAD -- docs/issues/issue-4/README.md` 只差一行：`**核准 commit**: 待提交` → `12ac70b`。12ac70b 承載的 Gherkin 與 HEAD 逐字相同，核准 commit 有效。
  - `git diff fcac9ae 12ac70b` 的 Gherkin 只有兩處修訂：
    - SCN-003 加上「；存活不到 1 秒的記為未知」，對應 N2 的決定。
    - SCN-004 的 Given 加上「/proc 裡的程序名稱與 Docker top 回傳的不一致（例如 Docker 跑在 VM 裡，PID 指向主機上別的程序）」，Then 的標示文字不變，對應 S3「比對程序名稱」以及「標示『無法讀取 /proc』」的決定。
  - 兩處都沒有超出決定範圍。N1、N3、N4、N5 屬於實作細節，不改變 Gherkin，符合「一併處理」的授權。
  - 核准表：SCN-003、SCN-004 是「2026-11-06（修訂）已核准」，其餘是「2026-11-06 已核准」，與核准來源一致。表格與現存的 Scenario 集合完全相等。
  - 使用者原話不在 reviewer 可取得的範圍，以 README 紀錄為準。
- **SCN-001**：通過。手算期望值、排序與分母突變仍然有效；主機對照組重跑的數值相同（100.0／41.3）。
- **SCN-002**：通過。輸入已改成低生命週期平均的程序在前。reviewer 自己的突變「第二排序鍵改成遞增 `-p['cpu']`」讓 SCN-002 三個 subTest、SCN-004、同分測試失敗，M1 的假綠燈已經消除。
- **SCN-003（修訂）**：通過。1 秒門檻測試涵蓋 0.5 秒、剛好 1 秒，以及 `born == previous_at`；把 `>= 1` 改成 `> 1` 或 `>= 0.5` 的突變都被抓到。
- **SCN-004（修訂）**：
  - 數量、時間、權限、名稱四種退回都有斷言；以下突變都被抓到：
    - 名稱不一致時只略過該程序；
    - 退回時仍保存 snapshot；
    - 拿掉時間檢查。
  - 名稱比對的強度不足（N1），對正常主機的誤判見 S1。
- **SCN-005**：通過，`FIELDS` 沒有改；舊列的顯示有斷言。
- **被修改的既有測試**：`stat()` 改成必須傳入名稱，各測試兩邊的名稱一致，期望值沒有改。這是名稱比對的必然結果，理由成立。

### 第一輪發現的覆核

| 發現 | 判定 | reviewer 的證據 |
|---|---|---|
| M1 退回排序是假綠燈 | 已解決 | 原突變（`:217` 改成 `if False:`）現在讓 8 個測試失敗或出錯；新突變「次鍵遞增」讓 4 個測試失敗。另以 20000 組隨機輸入確認：退回模式下統一排序鍵與舊的 `lambda p: p['cpu']` 的前 5 完全相同（Python 的 sorted 在 reverse 時仍保持穩定），所以 evidence 說 `rankfallback` 已不是突變是正確的 |
| S1 儀表板的 TypeError | 已解決 | `freeze_watch.py:895` 只取字串；list、dict、int 三個 subTest，`dashstr` 突變被抓到 |
| S2 輪替描述 | 已解決 | architecture.md:223-229 與 TBD-3 改成 max(0, 16−N)，與第一輪實測一致 |
| S3 PID namespace | 依使用者決定實作 (a) | 名稱比對能擋住 VM 情境；但會產生新的誤判面，見本輪 S1 |
| N1 | 已解決 | `isascii` 與 `../1`、阿拉伯數字 PID、剛好 1024 個的測試都有；`count`、`isascii` 突變被抓到 |
| N2 | 已解決 | 見 SCN-003 |
| N3 | 已解決 | 同分測試；`unknown_ranks_high` 突變被同分測試與 PID 重用測試抓到 |
| N4 | 已解決 | 舊 tick 不是整數時只讓該程序未知；`at` 是 NaN 或 inf 時退回 `no_previous`。剩下極大整數的情況，見 N2 |
| N5 | 已解決 | `borneq` 與 `tickback` 都有刻畫測試 |

reviewer 突變的完整結果：未突變版本全過；12 個突變中 11 個被抓到，只有 `name_first_char_only` 存活（N1）。

### 相關失敗面

- **名稱比對**：見 S1。補充：
  - 核心執行緒不會出現在容器的 top 裡。
  - 用 `data.index(b'(')` 取 comm 是正確的。stat 開頭是「十進位 pid + 空格 + `(`」，第一個 `(` 一定是 comm 的起點，comm 本身含 `(` 或 `)` 也沒問題：真實程序 `a(b)c` 通過，`a) (b c` 有測試，改成 `rindex` 的突變被抓到。
- **1 秒門檻**：
  - starttime 是 tick 精度，born 最多被低估 0.01 秒，誤差不到 1%。
  - `at` 在讀完全部 stat 後才取，最多晚 0.2 秒，只會讓分母變大、數值偏低，不會讓剛啟動的程序被讀成滿載。
  - 在前一輪 top 與前一輪 `at` 之間啟動的程序記為未知，不會算錯。
- **統一排序鍵**：退回模式下等價，見上表。非退回模式的未知程序排序位置，見 N3。
- **cache 損壞**：
  - 以下情況都能容錯：`procs` 是 list、`old[0]` 是 list、`old[1]` 是 bool、`at` 是負數、bool 或 NaN。
  - bool 或負數的 `at` 會算出偏差的數值，但只有竄改才會發生。
  - 極大整數的 `at` 會讓 helper 失敗，見 N2。
- **文件**：
  - README 雙語版本對等：100% 為一個核心、存活不到 1 秒記為未知、五種退回條件。
  - architecture.md 對 `cpu_interval`、`cpu_fallback`、cache 內容與輪替的描述正確；只有 `:206-209` 把名稱不一致一律解讀成另一個 namespace（S1），`:199-200` 少寫未知程序的位置（N3）。
- **新 artifacts 的敏感資訊**：新增或變更的 6 個 artifacts 只有 `/home/kevin/Documents/RCodes/sys-monitor/...` 路徑，與先前 issue 已公開的相同。沒有 token、容器 ID 或容器名稱；real-docker-summary 只保存摘要。

### 需求、架構、安全、品質

- **安全**：仍然只讀 `/proc/<pid>/stat`，不讀 argv；名稱比對只在記憶體中進行，cache 不保存名稱；PID 只接受 ASCII 數字，擋住路徑穿越。
- **品質**：
  - 修正後的程式比首次交付更精簡：兩個排序分支合成一個排序鍵。`read_proc_times` 改收 process dict，避免另建一份名稱對照。
  - 沒有新的設定項，風格與既有程式碼一致，沒有重複或過度設計。
  - GitNexus 沒有登錄本 repo；`process_sample` 只在 `collect`（`:355`）與測試中呼叫，`read_proc_times` 只在 `process_sample` 中呼叫。

### 豁免、待確認與限制

- 沒有 Gate 豁免紀錄。
- TBD-1、TBD-2 已解決。TBD-3 仍待確認，但不阻擋本 issue：數字已依第一輪實測更正，本機 6 個執行中的追蹤容器都在每輪的深度採樣內，理由成立。
- 限制：
  - reviewer 無法讀 dockerd 的 environ（要 root），dockerd 實際的 locale 是由 systemd 管理員環境推定。
  - 依禁止事項，沒有在容器內建立非 ASCII 名稱的程序，所以 S1 的證據是以主機 ps 模擬 moby 的解析方式取得，沒有經過真實的 Docker top。

## 流程判定

PASS

理由：沒有 MUST FIX。第一輪的 M1、S1、S2、N1、N3、N4、N5 都已解決，並經 reviewer 自己設計的突變驗證；S3 與 N2 依使用者決定實作，修訂後的 SCN-003、SCN-004 忠實反映決定，核准 commit 12ac70b 有效。check.sh 147 個測試全過、沒有跳過。

S1 不會產生錯誤數字，退回後的行為等同 issue 4 之前並有標示，形式上也符合已核准的 SCN-004，所以列為 SHOULD FIX（需決策），由使用者選擇 (a)、(b) 或 (c)。如果使用者選 (b) 或 (c)，會改變 SCN-004 的退回條件與程式碼，需要重新核准並重新審查。
