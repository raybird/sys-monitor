# 審查報告
- 審查日期：2026-11-06
- 範圍：完整交付（本地審查，第三輪）。完整範圍是 `abd3a3d..63ab312`，25 檔，+1955／−21。本輪差異 `ef3c759..63ab312` 另外逐行讀過：13 檔，+373／−48；其中 `1d3f900` 是修正，`63ab312` 只回填核准 commit
- Reviewed BASE SHA：abd3a3dbef60fb4a9e69d8ec07fa6d0d1d8fe455（= `git merge-base origin/main HEAD`）
- Reviewed HEAD SHA：63ab3127f457e38ac895a2cbb80eee82dfaabbef
- Reviewed patch-id：f2315f160a1d7054382d7cd9782e2a3c6df7fd4a（用 `git diff abd3a3d HEAD | git patch-id --stable` 重算，結果相同）
- 獨立 reviewer：Claude Code 隔離 subagent（Opus 5.5），不是原實作者
  - 全程唯讀，審查前後 worktree 的 `git status --short` 都沒有輸出。
  - 沒有 docker exec，沒有啟停容器，也沒有安裝到真實 HOME。
  - 突變與實驗都放在 scratchpad 的 `r3/`。
- Review artifact：docs/issues/issue-4/review-63ab312.md
- 核准基線：`**核准 commit**` 是 1d3f900，已填寫，不是 `待提交`

## 問題與風險

### MUST FIX

無。

### SHOULD FIX

無。

### NICE TO HAVE

**N1. `isprintable()` 這個條件沒有測試保護**
- 位置：`src/container_probe.py:177`、`tests/test_container_probe.py:637-647`
- reviewer 突變 `no_isprintable`：把條件改成 `comm.isascii() and comm == ' '.join(comm.split())`，`test_container_probe` 全部通過。
  - 原因：測試裡唯一的控制字元例子是 `x\tz`。tab 也算空白，所以空白條件就已經把它排除了。
- 實際後果：
  - 核心 comm 若含不屬於空白的控制字元（`\x01`、`\x1b`、`\x7f`），拿掉這個條件後會被拿去比對。
  - 實測 ps 會把這些字元顯示成 `x.z`（C locale）或 `x?z`（UTF-8），只要那個程序還在，就會固定誤判退回。
  - HEAD 的實作是對的，缺的只是回歸保護。
- 建議：在 `shown` 加一組 `'x\x01z': 'x?z'`，或 `'x\x7fz': 'x.z'`。

**N2. 只有單一內部空白的名稱，沒有測試確認它們仍會被比對**
- 位置：`src/container_probe.py:177`、`tests/test_container_probe.py:613`、`:630`
- reviewer 突變 `no_space_at_all`：把條件改成較嚴格的 `' ' not in comm`，測試全部通過。
- 後果：這個突變不會產生錯誤數字，只會讓含空白的名稱退出比對，VM 偵測力略降。
  - 實測主機 595 個程序沒有任何名稱含空白，所以影響很小。
- 建議（可選）：補一組 top `a b`、核心 `a c` 的不一致例子，斷言會退回。

**N3. architecture.md 寫 ps 把控制字元換成 `?`，但在 C locale 下實際是 `.`**
- 位置：`docs/architecture.md:211`，原文是「`?` for non-ASCII under a C locale or for control characters」。
- 實測 procps-ng 4.0.4：
  - 在 `LANG=C` 下，`x\tz`、`x\x01z`、`x\x7fz`、`x\x1bz` 都顯示成 `x.z`。
  - 在 UTF-8 下才是 `x?z`。
- 這只是文字精確度問題，不影響結論（這類名稱不比對）。
- 測試註解 `tests/test_container_probe.py:639` 寫「procps-ng 4.0.4 output on the right」，但右欄混用了 C locale（`????????????`、`caf??`）與 UTF-8（`x?z`）的輸出，可以註明 locale。

## 已查核維度

### 驗收與證據

- **check.sh**：在 worktree 執行 `env -u DISPLAY -u WAYLAND_DISPLAY bash scripts/check.sh`。
  - 結果：exit 0，`Ran 149 tests in 90.217s`，`OK`，跳過 0 個，`All checks passed.`。
  - 安裝與移除都在 `/tmp/tmp.*/home` 內進行。
  - 149 = 147 + 2，與 evidence 相符。
- **核准查核**：
  - **核准 commit 有效**：`git diff 1d3f900 HEAD -- docs/issues/issue-4/README.md` 只差一行，`**核准 commit**: 待提交` → `1d3f900`。1d3f900 承載的 Gherkin 與 HEAD 逐字相同。整個 `1d3f900..HEAD` 只改了這個檔案。
  - **SCN-004 第二次修訂**：
    - Given 的括號內加上「只比對可列印 ASCII、沒有開頭、結尾或連續空白的名稱，其他名稱 ps 會改寫顯示方式，不比對」。
    - When、Then 與標示文字都沒有改。
    - 這段文字就是第二輪審查的選項 (b)，與使用者「只比對單純 ASCII 名稱」的決定一致，沒有擴大範圍。
    - N1～N3 是測試、實作細節與文件，沒有改變 Gherkin，符合「一併處理」。
  - **核准表**：SCN-004 列為「2026-11-06（第二次修訂）已核准」，其餘不變。核准表與現存的 SCN-001～005 完全相等。
  - **核准來源**：新增了一筆依 review-ef3c759 S1 再修訂的紀錄；上一輪修訂的核准 commit 12ac70b 也移到它自己那一筆，可以追溯。
  - **TBD-4**：已解決，答案與 SCN-004 文字一致，Timeline 也有對應一列。
  - 使用者原話不在 reviewer 可取得的範圍，以 README 的紀錄為準。
- **red-review2-fix.log**：S1 的 6 個 subTest 都因 `cpu_fallback` 失敗；`10**400` 出現 `OverflowError`。與 evidence 描述相符。
- **SCN-001～003、SCN-005**：本輪沒有改動相關程式碼，既有測試全部通過。
- **SCN-004（第二次修訂）**：通過，以下突變都被抓到：
  - 拿掉 `isascii`：抓到 2 個 subTest。
  - 拿掉空白條件：抓到 3 個。
  - 只做 strip：抓到 `a  b`。
  - 把 startswith 改成相等比較：被前綴測試抓到。
  - 拿掉 isfinite：被 `nan` subTest 抓到。
  - `isprintable` 與單一空白名稱的保護缺口，見 N1、N2。

### 前一輪發現的覆核

| 發現 | 判定 | reviewer 的證據 |
|---|---|---|
| S1 ps 改寫名稱造成固定誤判 | 已解決 | 見下方「主機實測」。用 `/proc/self/comm` 設定 124 個程序的名稱，在 LANG=C、C.UTF-8、en_US.UTF-8 下跑 procps-ng 4.0.4 的 `ps -eo pid,stat,pcpu,pmem,comm -q…`，依 moby v28.1.1 的 `fieldsASCII` 與 `parsePSOutput` 解析後交給 HEAD 的 `read_proc_times`：3 種 locale × 124 個程序都沒有退回 |
| N1 名稱比對只分得出首字元 | 已解決 | `test_mismatch_sharing_the_first_letter_still_falls_back`（top `node`，核心 `nginx`） |
| N2 極大整數的 `at` 讓 helper 失敗 | 已解決 | `isinstance(previous_at, float)`，`10**400` subTest 會擋住；bool 也一併排除 |
| N3 文件沒寫未知值排在哪裡 | 已解決 | `docs/architecture.md:199-200` 補上「which rank after every known one」 |
| N4 VM 情境下 PID 全都不存在 | 不修，理由成立 | 不會產生錯誤數字；evidence:90 已記錄 |

### 相關失敗面

- **主機實測「單純名稱」判定**（procps-ng 4.0.4，依 moby 方式解析）：
  - **名稱被保留，也比對成功**：ASCII 0x20～0x7e 這 95 個字元逐一嵌在 `a?b` 中間，三種 locale 下 ps 都原樣輸出。其他情況：
    - `a b`、`a b c d e f g h`；
    - 剛好 15 字元，以及超過後被截斷的名稱；
    - `a(b)c`、`a) (b c`、`%`、`?`、`\x41`、`x<defunct>`；
    - 殭屍程序 `zomb` 與 `zo mb`，ps 會加上 ` <defunct>`。
  - **ps 改寫、也已被排除**：開頭或結尾空白、連續空白、所有控制字元、非 ASCII、無效 UTF-8、NBSP。
  - 結論：
    - 沒有找到「判定為單純，ps 卻改寫」的名稱，所以涵蓋完整。
    - 也沒有找到「ps 原樣顯示，卻被誤排除」的 ASCII 名稱。唯一的取捨是 UTF-8 locale 下 ps 原樣顯示的非 ASCII 名稱不比對，這是決策 (b) 的範圍。
- **VM 偵測力**：本機主機 595 個 PID（其中 ≤2000 的有 167 個）的 comm 全部是單純名稱，包括 kworker 這類核心執行緒。VM 情境下比對對象就是這些程序，偵測力基本保留。
- **moby 解析單一內部空白**：讀了 moby v28.1.1 `daemon/top_unix.go`。
  - `fieldsASCII` 只用 `\t \n \f \r` 與空格切欄。
  - 多出來的欄位由 `appendProcess2ProcList` 以單一空格合併（這個函式的本體沒有取得原始碼，依第二輪審查的描述與上述欄位處理推定）。
  - comm 是最後一欄，所以 `a b` 會原樣保留，實測模擬也相符。
  - ps 執行時不另設 env 或 locale，繼承 dockerd 的環境，與 S1 的前提一致。
- **`at` 只接受 float**：
  - `boot_seconds()` 是 `time.clock_gettime(CLOCK_BOOTTIME)`，型別一定是 float（已實測）。
  - cache 只經過 Python `json.dump`／`json.loads`（`src/container_probe.py:278`、`:374`）。float 序列化後一定帶 `.0` 或指數，讀回仍是 float，實測 `1000.0`、`1e16` 都一樣。
  - 測試也都傳 float。正常流程不會被誤判成 `no_previous`。
- **舊 cache 相容**：
  - issue 4 之前的 cache 沒有 `procs`，會走 `no_previous`。
  - 02eda4b、ef3c759 寫入的 `at` 本來就是 float，可以直接沿用。
  - 只有竄改才會出現整數 `at`，結果是退回一輪，不會失敗。
- **文件**：
  - README 雙語版本（`README.md:229-230`、`README.zh-TW.md:158-159`）都改成「單純 ASCII 程序名稱不一致」，兩邊對等，與實作一致。
  - architecture.md:206-212 把名稱不一致改寫成「likely」另一個 namespace，並列出不比對的名稱，與實作一致。小的不精確處見 N3。
- **新 artifacts 的敏感資訊**：
  - 新增或變更的 artifacts 只含 `/home/kevin/Documents/RCodes/sys-monitor/...` 路徑（先前已公開）與 `/tmp/tmp.*` 暫存路徑。
  - 沒有 token、容器 ID 或容器名稱；real-docker-summary 只有計數摘要。

### 需求、架構、安全、品質

- 修正只有 1 行判定加 1 行條件，另外把 `(int, float)` 改成 `float`，沒有新的抽象或設定項。註解精簡，風格與既有程式碼一致，沒有重複。
- 安全面沒有變化：仍然只讀 `/proc/<pid>/stat`，PID 只接受 ASCII 數字，cache 不保存名稱。
- 影響範圍：`read_proc_times` 只被 `process_sample` 呼叫，`process_sample` 只在 `collect` 與測試中呼叫，沒有跨服務的影響。

### 豁免、待確認與限制

- 沒有 Gate 豁免紀錄。
- TBD-1、TBD-2、TBD-4 已解決。TBD-3 仍待確認，但不阻擋本 issue，理由與第二輪相同。
- 限制：
  - 依禁止事項，沒有在容器內建立特殊名稱的程序，名稱實測是用主機 ps 加 moby 解析邏輯模擬，沒有經過真實的 Docker top。
  - dockerd 的實際 locale 無法讀取（要 root）。
  - BusyBox ps 這類非 procps 的主機 ps 沒有實測。
- reviewer 突變 8 組（含未突變版本）。結果放在 scratchpad 的 `r3/mut.out`，名稱實測放在 `r3/names.out`：
  - 未突變版本全部通過。
  - 6 組被抓到。
  - `no_isprintable`、`no_space_at_all` 兩組存活，見 N1、N2。

## 流程判定

PASS

理由：
- 沒有 MUST FIX，也沒有 SHOULD FIX。
- SCN-004 第二次修訂忠實反映使用者選的 (b)，核准 commit 1d3f900 有效，核准表、核准來源與 TBD-4 一致。
- 第二輪的 S1、N1、N2、N3 都已解決。S1 經 reviewer 用 procps-ng 實測三種 locale、124 個名稱，沒有固定誤判；VM 偵測力也保留。
- check.sh 149 個測試全過，沒有跳過。
- N1～N3 只是測試保護與文件精確度，可以在後續一併補上。
