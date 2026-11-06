# 審查報告

- 範圍：完整交付範圍（本地，已豁免 PR）；TARGET origin/main（審查當下為 6d6066e），BASE 為 merge-base
- Reviewed BASE SHA：d8748d6ece59bf0f9797ea164622be0dec9022b5
- Reviewed HEAD SHA：9f5712f850ca69172f46a13e5ec71b72d367f57c
- Reviewed patch-id：e9527f10458a1f5d78bd78df1910c81617b564f8（2026-11-04 以 `git diff d8748d6 9f5712f | git patch-id --stable` 重算，一致）
- 獨立 reviewer：Claude（宿主隔離 subagent，由協調者以 Agent 工具啟動；非原實作者，未參與 c62159c～9f5712f 的任何撰寫）
- Review artifact：docs/issues/issue-1/review-9f5712f.md
- 審查日期：2026-11-04
- 核准基線：c62159c02638e439f00a254d97dafe449b25f296（README `**核准 commit**` 已回填；依 acceptance.md 的 `git log -G '^…\*\*核准來源\*\*…'` 對 9f5712f 推導也得到 c62159c）

## 問題與風險

### MUST FIX

1. **事件回顧在大檔中回傳空窗口：tail 截斷產生的殘行讓判斷失效**（src/freeze_watch.py:247-259 `incident_rows`，搭配 :101 `read_tsv_path`）
   - 原因：`read_tsv_path(path, …, 4_000_000)` 從檔案中段開始讀時，第一行幾乎都是半截列，csv 解析後 `epoch` 會是其他欄位的值（例如 `'12'`）或 `NA`。`incident_rows` 用 `samples[0]` 的 epoch 判斷「tail 是否已涵蓋窗口起點」：殘行的 epoch 接近 0，所以永遠判定已涵蓋，不會改用 `metric_window` 讀全檔，接著又因 `0 < end - 1800` 直接 break。結果事件窗口不在最後 4 MB 內時，回顧列數為 0。
   - 重現（2026-11-04，探針對 HEAD 的 `incident_rows`／`diagnostic_report`）：8640 列、11.8 MB 的單日檔，GAP 在第 720 列。結果 `first_tail_row_epoch='12'`、`incident_rows=0`，同一事件的 `diagnostic_report` 卻有 211 筆取樣。GAP 移到檔尾附近（第 8000 列）時回顧正常（181 列）。啟用 GPU 紀錄後每列約 4.4 KB（見第 2 項），單日檔約 39.5 MB，GAP 發生在檔尾前約 2.4 小時以外就一律重現（實測 `incident_rows=0`）。
   - 為何是 MUST FIX：這是邏輯錯誤，而且屬於跨 Task 重複邏輯分歧。Task 1.2 的儀表板回顧（tail 讀取再補讀）與 Task 3.3 的報告（`metric_window` 全檔串流）對同一事件讀出不同資料，儀表板顯示空白，匯出報告卻有資料。既有測試 `tests/test_freeze_watch.py:199` `test_scn006_old_stall_still_has_data_after_the_file_grows` 能通過，只是因為 fixture 的每列長度固定，4 MB 截點剛好落在列首（實測 tail 第一列是完整的 `2023-11-16T12:49:10`），沒有涵蓋一般的截斷情況。這不是刻意的假綠燈，但這個綠燈不代表行為正確。
   - 建議：讓 `incident_rows` 與 `diagnostic_report` 共用同一條窗口讀取路徑（例如都用 `metric_window` 串流，或在 tail 讀取中丟掉 seek>0 時的第一行並以第一個有效 epoch 判斷），再補一個截點落在列中間的 fixture，紅燈先出現後再修。

2. **啟用 GPU 紀錄後，「最近 30 分鐘熱度帶」只剩約 5 分鐘；SCN-005「限制取樣成本」的成本證據不具代表性** `需決策`（src/freeze_watch.py:101、117、1140 的 160 KB tail，src/freeze_watch.py:629 `rows[-180:]`；src/freeze_gpu.py:78-114 的輸出內容；src/freeze-monitor:708-715）
   - 實測（2026-11-04，本機 625 個程序）：連續 5 次在真實 `/proc` 執行 `freeze_gpu.py`，wall 為 69.6～125.1 ms，CPU 為 69.4～113.9 ms，`status=partial`、`truncated=True`、`unavailable=280`、13 個 client，JSON 約 4.4 KB。evidence/sampling-cost.json 的硬體段落是 `visible_clients: 0`、`unavailable: 1`、`truncated: false`，每列只多約 57 bytes，應是在看不到主機程序的環境中量測，與本機實況差異很大。
   - 影響：用這份 4.4 KB JSON 建立 360 列測試檔，`read_tsv_tail` 只讀回 35 列（其中 1 列是殘行），涵蓋 5.5 分鐘；關閉時 360 列全部讀回。也就是說，啟用一個已核准的可選功能後，既有的 30 分鐘即時熱度帶與停擺標記實際只剩約 5 分鐘。metrics 檔約從每日 2.5 MB（本機現況）增加到約 38～40 MB。GitHub issue 1 的驗收方向第 4 點要求「GPU 記錄與匯出功能不明顯增加常態 CPU／磁碟負載」。
   - 揭露：實作者在 evidence/README.md 已寫明「本機可見 GPU client 為 0……滿載 GPU 的記錄量仍需在有可用硬體的環境觀察」。依 verification.md，主動揭露不構成缺失。這裡列為 MUST FIX 的是熱度帶縮短這個既有行為的回歸，以及「限制取樣成本」尚無有效證據，不是揭露本身。
   - 待決問題：每日磁碟增量多少算「不明顯增加」？可選做法：(a) 只修讀取端，讓即時檢視固定讀滿 180 列，不受列寬影響；寫入量維持原樣。(b) 另外精簡 JSON，只記有活動或狀態變化的 client，pids 與 names 只在持有者改變時輸出。(c) GPU 資料改寫入獨立的 gpu-*.tsv，有自己的保存期限。reviewer 建議 (a) 加 (b)：(a) 是修正回歸的必要條件；(b) 讓磁碟量回到同一個量級，不需要改檔案架構。不論選哪種，修正後都要在真實桌面 `/proc` 重新量測 CPU、每列 bytes 與每日增量，記入 evidence。

### SHOULD FIX

1. **GPU 採樣器遇到非 UTF-8 的程序名稱會整次失敗**（src/freeze_gpu.py:32、34）：`stat`／`comm` 用嚴格 UTF-8 的 `read_text()` 讀取，`UnicodeDecodeError` 不在 `except (OSError, IndexError)` 的範圍內。核心把 comm 截在 15 bytes，CJK 程式名稱很容易被切在多位元組字元中間（例如 Wine 下的中文 exe 名稱）。實測 `("a"+"測試程式測試").encode()[:15]` 的 fixture：採樣器 exit 1，收集器退回 `{"status":"unavailable","clients":[]}`。只要該程序還在，整個 GPU 紀錄就一直是 unavailable。基本監測不受影響，也沒有冒充零活動，所以不是 MUST FIX。建議改用 `read_bytes().decode(errors="replace")`，或逐程序捕捉 `ValueError`。
2. **掃描順序與「不完整」訊號**（src/freeze_gpu.py:23、28、38）：只掃 PID 最小的 512 個，本機有 625 個程序，所以每次都 truncated，而最新啟動的程序（PID 最大，例如剛開的遊戲）永遠掃不到。核心執行緒與其他使用者的程序約 280 個，全部記為 unavailable，`status` 因此永遠是 `partial`，UI 一直顯示「GPU 資料不完整：權限不足、掃描受限或採樣失敗」，失去警示意義。建議先用 `st_uid` 過濾出本人程序，再讀 fd；「不屬於本人而略過」與「本人程序讀取失敗」分開計數。
3. **解碼規則分歧**（src/freeze_watch.py:178 `metrics_file_covering`、:237 `metric_window`）：這兩處新增的讀取用嚴格 UTF-8，與 `tail_text` 的 `errors="replace"` 不一致。實測 metrics 檔只要有一個 0xFF 位元組，`read_incidents()`（有 GAP 事件時）、`incident_rows`、`diagnostic_report` 都會丟出 `UnicodeDecodeError`。這發生在每 2 秒執行的 `refresh` 計時回呼內，可能造成儀表板停止更新。收集器以 `LC_ALL=C` 寫入，JSON 用 `ensure_ascii`，正常資料都是 ASCII，要檔案損毀才會觸發，所以列為 SHOULD FIX。NUL 結尾（斷電常見樣態）實測可正常讀取。
4. **移除程式漏掉 freeze_gpu.py**（uninstall.sh:67-82）：install.sh:351 新安裝 `${data_dir}/freeze_gpu.py`，但 uninstall.sh 的刪除清單沒有它，移除後會留下這個檔案與 `~/.local/share/freeze-watch/`（`rmdir --ignore-fail-on-non-empty` 不報錯）。scripts/check.sh:629-636 沒有檢查這一項，所以 evidence 的「隔離安裝／移除均通過」沒有抓到。
5. **證據持久力**：
   - `tests/test_previous_session.py:91` `test_scn003_does_not_borrow_a_previous_session_rotation` 中，當前 session 的檔案本身有效，即使實作會跨 session 往回找也一樣通過；baseline-red.log 第 36 行顯示它在修正前就是 ok。建議補「當前 session 全部無有效取樣、前一個已 STOP 的 session 有有效取樣 → 必須是 unknown」。我以探針 P1 實測 HEAD 的行為正確（`last_sample=unknown metrics=unknown`）。
   - `tests/test_freeze_watch.py:199` 的截點對齊問題，見 MUST FIX 第 1 項。
   - SCN-001 的截圖（evidence/dropdown-*.png）擷取於 2026-10-05，那時 rebase 還沒把 CSS 換成上游樣式，不是 HEAD 的畫面。我在 HEAD 重新擷取，兩種主題都可讀（見下方），建議以 HEAD 重存。對比測試吃的是主機 GTK 佈景（本機 gsettings 為 Greybird），沒有固定 `GTK_THEME`，也只量測文字，沒有量測選取列的勾選圖示。建議另外固定 Adwaita 跑一次，並量測圖示顏色。
6. **與目前 TARGET 整合會衝突** `需決策`：origin/main 已前進到 6d6066e（`src/freeze_watch.py` +505 行）。`git merge-tree --write-tree origin/main 9f5712f` 回報 `CONFLICT (content): Merge conflict in src/freeze_watch.py`。本報告的結論只綁在 9f5712f，依 review-evidence.md，rebase 或解衝突後要重跑 scripts/check.sh，並重審衝突區段。待決問題：交付方式要 rebase 到 6d6066e（建議，維持線性歷史，重審範圍限於衝突區段與測試），還是建 merge commit？可與 MUST FIX 的修正一起處理。

### NICE TO HAVE

1. UNCLEAN 事件 `last_sample=unknown` 時（src/freeze_watch.py:202-208 `incident_end`），報告的基準時間退回重啟時間，並把新開機 5 分鐘內的 KERNEL 行列為「相關核心錯誤」。探針 P4 中，`+120s` 的 `EXT4-fs error new boot` 被列入。`metrics=unknown` 也會變成相對路徑 `Path("unknown")`。建議改為明示「最後取樣未知」，只列 previous boot 的行。
2. `KERNEL_REPORT_PATTERN`（src/freeze_watch.py:290）是收集器 `kernel_alert_pattern`（src/freeze-monitor:42）的第二份實作，而且已經分歧：缺 `\[drm[^]]*\].*(reset|hang|timeout|ERROR)`，會落到泛用分類；裸字 `rcu` 會比對到 `circuit` 之類的字。只影響分類精度，不影響遮蔽。
3. previous boot 的核心行在報告中顯示的是讀回時間，但沒有標示「讀回」。docs/architecture.md 寫的「報告標示其讀回時間」與實際輸出不完全相符。
4. 歷史 FREEZE 事件的 `metrics=` 指向 START 檔，跨輪替的回顧只讀得到該檔（探針 P7）。這是舊資料本身的限制，可在 docs/troubleshooting.md 揭露。
5. `Gtk.FileChooserNative` 已棄用（測試輸出 DeprecationWarning），可改用 `Gtk.FileDialog`。
6. scripts/check.sh:47-51（既有程式）的 xvfb 分支沒有設定 `GDK_BACKEND=x11`。主機有 `wayland-0` socket 時，即使取消 DISPLAY／WAYLAND_DISPLAY，GTK 仍可能連到真實 compositor。我第一次擷取截圖得到全黑的 245 bytes 圖檔，強制 x11 後才正常。
7. `gpu_summary`（src/freeze_watch.py:262）遇到 `[]`、`{"clients":[{}]}` 這類 JSON 會拋例外。這兩種只有手改資料才會出現。
8. 整個範圍的 `git diff --check` 只在 kit 範本（docs/_templates/*、docs/agents/readme-templates.md）因 Markdown 硬換行的行尾空白而失敗，程式檔沒有問題。evidence 記的「git diff --check 通過」是 2026-10-07 工作區層級的結果。

## 已查核維度

### 驗收與證據

| 編號 | 證據位置 | 被測版本 | 結論 |
|---|---|---|---|
| SCN-001 | tests/test_window_layout.py `test_scn001_light_dark_normal_hover_selected_contrast`；evidence/post-rebase-check.log；evidence/dropdown-light.png、dropdown-dark.png | post-rebase-source.json 的 14 個檔案雜湊與 HEAD 逐一相符（2026-11-04 重算） | 通過。真實 GTK 合成背景與文字顏色，亮暗兩種主題下的正常／hover／selected 對比都 ≥ 4.5；baseline-red.log 在 849e6aa 是紅燈。2026-11-04 在 HEAD 用 Xvfb（x11）重新擷取並目視：亮暗兩種主題的三種狀態、文字與勾選圖示都清楚可讀。App 使用固定的深色配色，所以「亮色」截圖也是深色，證明系統亮色佈景沒有滲入。產品 CSS 修正來自 BASE（d8748d6），本範圍只新增測試。限制見 SHOULD FIX 5。 |
| SCN-002 | test_previous_session `test_scn002_multiple_rotations_use_latest_sample`；test_freeze_watch `test_scn002_review_anchors_on_last_sample_and_crosses_rotation` | 同上，重跑通過 | 收集器端通過，回顧在小檔與跨輪替時通過。大檔中的回顧有 MUST FIX 1 的缺口（主要影響 GAP；UNCLEAN 的窗口在檔尾，所以會被 tail 涵蓋）。 |
| SCN-003 | test_previous_session 的 scn003 四項 | 同上 | 通過。探針 P1／P1b 補驗：當前 session 全部無效時不借用前一 session，NUL 結尾時回退到前一個有效列。`does_not_borrow` 測試的鑑別力不足（SHOULD FIX 5）。 |
| SCN-004 | test_previous_session `test_scn004_*`；test_freeze_watch `test_scn004_old_and_new_unclean_events_use_uncertain_labels`；check.sh 的 UNCLEAN／INTERRUPTED／STOP 斷言 | 同上 | 通過。UNCLEAN 訊息含 `cause=unknown (power loss, forced reboot or freeze)`，同 boot 時為 INTERRUPTED，UI 標籤與摘要都用疑似措辭，previous boot 的核心掃描照常觸發。 |
| SCN-005 | test_gpu_sample 七項；test_previous_session `test_scn005_*`；check.sh 安裝後的 gpu 欄位；evidence/sampling-cost.json | 同上 | fixture 層（差值、閒置、去重、PID 重用、回退、capacity、缺計數器、退出、權限、預算）通過。「限制取樣成本」在真實 `/proc` 的證據無效且有回歸（MUST FIX 2）；非 UTF-8 名稱與掃描順序見 SHOULD FIX 1、2。不支援的驅動標示為 `unsupported_*`／「活動未知」，沒有冒充 0%，判定成立。 |
| SCN-006 | test_diagnostic_report 四項；test_window_layout `test_scn006_preview_does_not_write_and_cancel_keeps_it_readonly`；evidence/privacy-negative.log；evidence/report-preview.png | 同上 | 通過。前 30 分鐘／後 5 分鐘、session 邊界、遮蔽、0600、預覽不寫檔，預覽與匯出使用同一個字串。隱私負向對照確實抓到洩漏。探針 P6 確認報告不含使用者名稱、home 路徑、token 或狀態目錄路徑。report-preview.png 擷取於 2026-10-05；HEAD 重新擷取後內容一致。 |

5b678f6 之後的 24542e0 與 9f5712f 只動文件（`--name-status` 只有 AGENTS.md、CLAUDE.md（D）、docs/.dev-rules-kit.json、docs/AGENTS.md、docs/agents/*、issue README），沒有夾帶程式；程式與測試的雜湊也與 post-rebase-source.json 相同，所以實作證據對 HEAD 仍然適用。刪掉的 CLAUDE.md 內容就是 AGENTS.md 原本已有的 GitNexus 區塊，沒有遺失任何規則。

核准來源：`git diff c62159c 9f5712f -- docs/issues/issue-1/README.md` 只有「诊→診」「确认→確認」兩處簡轉繁修正、核准 commit 回填，以及實作證據、豁免、Timeline、metadata 等記帳更動。Gherkin 的條件、動作、結果都沒變，原核准有效。核准來源結合 GitHub issue 1 的改善項目與驗收方向（2026-11-04 以 `gh issue view 1` 讀到原文），以及 2026-10-05 的兩句原話，可以追溯。

### 相關失敗面

| 輸入／狀態 | 預期 | 現有覆蓋與實測 | 判定 |
|---|---|---|---|
| 同 session 多次輪替後無 STOP | 取最新有效檔與 last_sample、silent_for | 單元測試 + check.sh | 通過 |
| 最新輪替檔為空、缺失、無效或 NUL 結尾 | 回退到同 session 較早的有效檔 | 單元測試；P1b（NUL 4 KB） | 通過 |
| 當前 session 全部無有效取樣，前一 session 有 | unknown，不借用 | 只有 P1 實測（測試無鑑別力） | 行為通過，證據待補（SF-5） |
| 已記錄 STOP | 不產生事件 | 單元測試 + check.sh | 通過 |
| 同 boot 中斷 vs boot id 改變 | INTERRUPTED vs UNCLEAN，都不斷言原因 | 單元測試 + check.sh | 通過 |
| 儀表板回顧時跨 session 混用 | 只用同 session 的檔案 | P2：前一 session 的 11111 沒出現 | 通過 |
| 大檔中的舊事件回顧（tail 截在列中間） | 回傳完整 30 分鐘 | P12／P11：0 列（報告 211 筆） | **失敗（MF-1）** |
| 啟用 GPU 後的即時 30 分鐘熱度帶 | 180 列 | P10：35 列／5.5 分鐘 | **失敗（MF-2）** |
| DRM fdinfo 權限不足、程序退出、計數器回退、缺計數器 | 降級，不冒充零 | fixture 測試 | 通過 |
| 不支援的驅動、NVIDIA 專有驅動 | 標示不支援 | `unsupported_identity`／`unsupported_counters`，UI 顯示「活動未知」或「計數器不支援」 | 通過 |
| comm 是截斷的 UTF-8 | 跳過該程序或替換字元 | P9：採樣器 exit 1，整批 unavailable | 降級但有標示（SF-1） |
| 程序數超過 512（本機 625） | 標示截斷，並涵蓋重要程序 | 真實 `/proc`：永遠 truncated／partial，最新程序沒掃到 | 有標示，訊號品質差（SF-2） |
| 取樣成本上限 | 有界，且不明顯增加負載 | CPU 受 100 ms 預算與 `timeout 1` 限制；磁碟約 15 倍 | **證據無效（MF-2）** |
| 報告遮蔽：home 路徑、命令列參數、使用者名稱、程序名稱 | 不出現 | 單元測試 + 負向對照 + P6 | 通過 |
| 預覽與匯出一致、預覽時不寫檔 | 同一份文本，0600 | 測試 + 程式碼閱讀（`report` 字串直接傳給 `_save_report`） | 通過（ACCEPT 路徑沒有 GTK 自動化，以程式碼閱讀確認） |
| metrics 檔含無效位元組 | 不讓儀表板中止 | P3／P3c：UnicodeDecodeError | 需檔案損毀才會發生（SF-3） |
| last_sample=unknown 的報告 | 明示未知，不混入新開機的資料 | P4：以重啟時間為基準，混入新開機的核心行 | 小瑕疵（NH-1） |

### 需求、架構、安全、品質

- 需求：六個 Scenario 都有對應實作，沒有超出核准範圍的功能。架構維持 TSV 欄位只往後附加（`gpu_processes` 是第 36 欄），舊檔也能讀；GPU 採樣是獨立的 Python 標準庫腳本，預設關閉。
- 安全：GPU 採樣只讀 comm、stat、fd 連結與 fdinfo，不讀 cmdline；狀態檔在 umask 077 下以 0600 原子替換；報告只輸出允許的數值欄位與核心分類，不輸出 `incident.message`（其中有 metrics 路徑）。寫檔權限 0600。沒有發現權限提升或命令注入面。
- 跨 Task 重複：(1) 回顧與報告的窗口讀取分歧，造成行為不一致，列為 MUST FIX 1；(2) 兩份核心比對 pattern 已分歧（NH-2）；(3) 解碼規則分歧（SF-3）；(4)「非正常關機／疑似當機」字串在三處重複，僅影響可讀性，不另列。
- 過度設計：沒有推測性抽象。`freeze_gpu.py` 約 145 行，上限常數直接寫在程式中，與文件描述相符。
- 文件：README、architecture、troubleshooting 已依 project.md 的常青文件觸發更新；內容與實作大致相符（NH-3 例外）。

### 豁免、待確認與限制

- Gate 豁免：只有「建立 PR 與 PR 證據」（2026-11-04，使用者原話「這專案可以不走 pr 再本地直接審查」）。本報告不要求 PR 證據；其他 gate 都沒有豁免，照常查核。
- 待確認事項：TBD-1、TBD-2 都是「已解決」（2026-10-05），狀態維持原樣，與交付相符。
- 實作者揭露的限制（GPU 實機活動只用 fixture 驗證、記錄量待實機觀察、GitNexus detect_changes 無法取得圖譜）都如實記錄，不構成缺失。本次實測補上了其中「記錄量」的部分，結果見 MF-2。
- reviewer 的限制：沒有在可產生 AMD／Intel 引擎活動的負載下驗證引擎百分比；GTK ACCEPT 存檔路徑只做程式碼閱讀；沒有部署到真實服務（依指示）。

### 本次重跑的命令與結果（2026-11-04）

1. `git diff d8748d6 9f5712f | git patch-id --stable` 得到 e9527f10458a1f5d78bd78df1910c81617b564f8；`git merge-base origin/main HEAD` 得到 d8748d6。
2. `git archive 9f5712f` 解到 scratchpad 的乾淨副本，執行 `env -u DISPLAY -u WAYLAND_DISPLAY TMPDIR=<scratchpad> bash scripts/check.sh`：exit 0，`Ran 55 tests … OK`，`All checks passed.`（install／uninstall 只在 check.sh 的 mktemp HOME 內執行，並以 stub systemctl 取代真實服務）。
3. 同一副本執行 `GDK_BACKEND=x11 GSK_RENDERER=cairo xvfb-run -a /usr/bin/python3 -m unittest discover -s tests`：exit 0，55 tests OK。
4. `GDK_BACKEND=x11 GSK_RENDERER=cairo xvfb-run -a python3 tests/capture_issue1_ui.py <scratchpad>`：重新擷取三張圖並目視，亮暗主題的選單三種狀態與報告預覽都可讀。
5. 以 python 比對 evidence/post-rebase-source.json 與 HEAD：14 個檔案全部 MATCH。
6. 探針 P1～P13（腳本放在 scratchpad，不持久化；輸入、預期與結果已寫在上表）。
7. 真實 `/proc` 跑 `LC_ALL=C python3 -I src/freeze_gpu.py --state <scratchpad> …` 共 5 次，結果見 MF-2。
8. `git merge-tree --write-tree origin/main 9f5712f`：`src/freeze_watch.py` 衝突。
9. `git diff --check d8748d6 9f5712f`：只有 kit 範本行尾空白（NH-8）。
10. `gh issue view 1`：讀取核准來源原文。

## 流程判定

RETURN TO execute-task

理由：獨立審查已完成，報告已保存於本檔。有 2 項 MUST FIX：MF-1 是回顧窗口的邏輯錯誤與跨 Task 分歧，而且該測試的綠燈是偶然對齊的結果；MF-2 是啟用 GPU 紀錄會讓即時 30 分鐘熱度帶縮短，「限制取樣成本」也缺少有效證據。MF-2 的成本門檻與儲存方式標為 `需決策`。這兩項都不在 Gate 豁免紀錄中，所以不能判 PASS。修正後要以新的 HEAD 重新審查；若同時 rebase 到 origin/main，衝突區段一併納入審查範圍。
