# 審查報告

- 範圍：完整交付範圍（本地，已豁免 PR）；TARGET origin/main = 6d6066ed908ff64b1df9ad00be4485c02812a8bb，BASE 為 merge-base，範圍內 commit 為 5524b0e、2ba9ef7、0cbc4f2、df8a1cb、a3e841c、6c972c3
- Reviewed BASE SHA：6d6066ed908ff64b1df9ad00be4485c02812a8bb
- Reviewed HEAD SHA：6c972c33afadd3ce7df190b7abd79fc76bc3cd80
- Reviewed patch-id：f0f513fa7a5f974143ca5d5c9197600da7998a39（2026-11-04 以 `git diff 6d6066e 6c972c3 | git patch-id --stable` 重算，一致；`git merge-base origin/main HEAD` 為 6d6066e）
- 獨立 reviewer：Claude（宿主隔離 subagent，由協調者以 Agent 工具啟動；不是原實作者，也不是第一輪 review-9f5712f.md 的 reviewer，沒有參與任何實作或修正）
- Review artifact：docs/issues/issue-1/review-6c972c3.md
- 審查日期：2026-11-04
- 核准基線：5524b0ef78141af82d02086abd5200b58401e106（README `**核准 commit**` 已回填；依 acceptance.md 的 `git log -1 -G '^…\*\*核准來源\*\*…' 6c972c3` 推導也得到 5524b0e）
- 風險：High（README 分級 Large／High）

## 問題與風險

### MUST FIX

1. **rebase 整合遺漏：新的 UNCLEAN 事件在「最近事件」清單失去上游的嚴重度顏色**（src/freeze_watch.py:1401-1405 `_append_event_row`）
   - 原因：上游 6d6066e 新增「event-severity colours」（CHANGELOG 0.8.0），以 `kind in ("FREEZE", "KERNEL")` 套 `danger`、`GAP／INTERRUPTED／WARN` 套 `warm`。issue 1 把收集器的新事件改記為 `UNCLEAN`（src/freeze-monitor:581），其他五處事件種類清單（:37、:40、:148、:330、:621、:1580）都補了 `UNCLEAN`，唯獨這一處在 rebase 解衝突時沒有補。
   - 實測（2026-11-04，Xvfb 下對 HEAD 呼叫 `_append_event_row`）：`FREEZE → ['danger']`、`UNCLEAN → []`、`INTERRUPTED → ['warm']`、`GAP → ['warm']`。收集器已不再寫 FREEZE，所以之後每一次非正常關機在清單中都沒有顏色，看起來比單純的收集器中斷（INTERRUPTED，橘色）還不嚴重。
   - 為何是 MUST FIX：這是任務指定查核的 rebase 衝突區段，丟掉了上游的既有行為；也是同一份事件種類分類在多處重複、已分歧並造成行為不一致的情況。既有測試沒有涵蓋事件列樣式，所以 check.sh 全綠也抓不到。
   - 建議：在該處把 `UNCLEAN` 和 `FREEZE` 一起列為 `danger`（若要把種類集中成一個常數也可以，但最小修正是補一個值），並補一個先紅後綠的測試，斷言 UNCLEAN 事件列帶 `danger` class。

### SHOULD FIX

1. **NVIDIA 專有驅動（不支援的驅動）下，GPU JSON 沒有被精簡，每列約 9.3 KB，而且一直顯示「已達掃描上限」** `需決策`（src/freeze_gpu.py:106 以 `unknown:{identity}:{fd_name}` 當 key、:119-120、:169-173 只有 `sampled` 的閒置 client 才併入 `idle`）
   - 原因：沒有 `drm-client-id` 的 fd 每個都算一個 client，而且狀態是 `unsupported_identity`，不會被歸入 `idle`，所以每列都完整輸出。專有驅動的 GL／Vulkan 程序通常同時開著多個 `/dev/nvidiactl`、`/dev/nvidia0`、`/dev/nvidia-modeset`、`/dev/nvidia-uvm`。
   - 實測（fixture，2026-11-04）：6 個程序各 12 個 `/dev/nvidia*` fd，第二次取樣得到 64 個 client（到達 `MAX_CLIENTS`），`status=partial`、`truncated=True`，每列 9313 bytes，以 8640 列計約每日 80.5 MB，是本機 Intel 實測（約 0.6 KB／列、每日約 5.2 MB）的 15 倍，也比第一輪 MF-2 的 4.4 KB 更大。UI 會一直顯示「GPU 資料不完整」「已達掃描上限」，再列出幾十行「計數器不支援，僅確認持有裝置」，這就是第一輪 SF-2 指出的「永遠 partial，失去警示意義」，只是換成發生在 NVIDIA 上。
   - 判定：輸出仍受 64 個 client 的上限約束，所以「限制取樣成本」在形式上成立。即時熱度帶已改為依列數讀取（我在 9 MB 實際列寬的檔案上測得每次約 5.6 ms），不會再像第一輪那樣縮短。不支援的驅動也確實標成不支援，沒有冒充 0%。這裡沒有真實 NVIDIA 硬體的量測，以上是 fixture 推估；新版驅動的 nvidia-drm render node 是否提供 `drm-client-id`，我無法確認。
   - 待決問題：不支援的驅動，GPU 紀錄要不要也精簡？可選做法：(a) `unsupported_identity` 依「程序＋驅動」合併成一筆，只記持有者與 fd 數；(b) 不支援的持有者也只以名稱列入獨立的 `unsupported` 名單（與 `idle` 同樣處理）；(c) 接受現狀，在 README／troubleshooting 揭露 NVIDIA 專有驅動每日約增加數十 MB。reviewer 建議 (b)，與 TBD-3 選定的「精簡 JSON」一致，改動最小。

2. **`idle` 名單與有活動的 client 用同一個程式名稱，讀起來互相矛盾**（src/freeze_gpu.py:169-171、src/freeze_watch.py:301-302）
   - 實測（2026-11-04，本機真實 `/proc`，Xvfb 渲染整個儀表板）：GPU 區塊同時列出 `orca-ide · i915 · render 8.48%`、`chrome … 0.02%`、`gnome-shell … 1.19%`，下一行又寫「持有裝置、取樣期間無活動：bash, orca-ide, chrome, msedge, …, gnome-shell」。原因是同一個程序持有多個 DRM client，有活動的那個列在上面，閒置的另一個以名稱列入 `idle`。資料本身沒有錯，但這一行看起來是在說「orca-ide 沒有活動」，削弱了 SCN-005「區分持有者與實際活動」在畫面上的可讀性。
   - 建議：`idle` 不要列已經出現在 `clients` 的名稱，或把該行改成「另有閒置的 GPU client：…」。

### NICE TO HAVE

1. **`incident_rows` 仍用 `samples[0]` 判斷 tail 是否涵蓋窗口起點**（src/freeze_watch.py:269、:272）：第一輪建議「以第一個有效 epoch 判斷」，這次只修了半截列，沒有改這個判斷。探針：在 ≥4 MB 的檔案中，若剛好是 tail 第一列的 epoch 無法解析（中段損毀），`incident_rows` 回傳 0 列，同一事件的 `diagnostic_report` 卻有 211 列，也就是兩條讀取路徑在這個情況下仍然分歧。收集器每個 session 寫自己的檔案，epoch 來自 `date +%s`，正常資料不會出現這種列；要中段損毀又剛好落在那一列才會觸發，所以不列為 MUST FIX（第一輪對「需要檔案損毀才發生」的 SF-3 也是列 SHOULD FIX，這次的觸發條件又窄得多）。建議改用第一個能解析的 epoch。
2. 第一輪 NH-1（`last_sample=unknown` 時報告以重啟時間為基準，並混入新開機的核心行）、NH-2（`KERNEL_REPORT_PATTERN` 與收集器的 pattern 分歧，缺 `[drm] … reset/hang/timeout/ERROR`，裸字 `rcu`）、NH-3（docs/architecture.md:137「報告標示其讀回時間」與輸出不完全相符）、NH-5（`Gtk.FileChooserNative` 已棄用）、NH-6（scripts/check.sh 的 xvfb 分支沒有設 `GDK_BACKEND=x11`）、NH-7 的 `{"clients":[{}]}`（src/freeze_watch.py:296 `client["pids"]` 會拋 KeyError；`[]` 已修）都還在。使用者在 TBD-4 只把 SF 併入本輪，這些維持建議層級。NH-2 我也確認過：這類行仍然會以泛用分類列入報告，不會遺失證據，只是分類不精確，所以不升級。
3. docs/architecture.md:130 寫「程序中途結束直接略過」，但 readlink 成功之後 fdinfo 才消失（src/freeze_gpu.py:95-100）會記成 `unavailable`，該次取樣變成 partial。這是保守的設計，程式註解也寫明了，建議文件同步說明。
4. 收集器呼叫採樣器時沒有加 `-I`（src/freeze-monitor:711），與證據中的量測命令不同。兩者在同一個使用者底下執行，沒有權限邊界，只是一致性建議。
5. 證據持久力：evidence/README.md 說「解衝突後 check.sh exit 0（62 項）」，但沒有保存這次的 log，留下的 post-rebase-check.log 是 2026-10-07 rebase 到 d8748d6 時的紀錄。最終 HEAD 有 review-fix-check.log（71 項），我也重跑通過，所以不影響本次判定。
6. `git diff --check 6d6066e 6c972c3` 只在 kit 範本（docs/_templates/*、docs/agents/readme-templates.md）因 Markdown 硬換行出現行尾空白；程式、測試與 issue 文件都通過。

## 已查核維度

### 驗收與證據

被測版本：evidence/review-fix-source.json 的 12 個檔案 SHA-256 與 `git show 6c972c3:<path>` 逐一相符（2026-11-04 重算）。我在 `git archive 6c972c3` 的乾淨副本重跑 check.sh，71 項測試全部執行，沒有 skip。

| 編號 | 證據位置 | 結論 |
|---|---|---|
| SCN-001 | tests/test_window_layout.py `test_scn001_light_dark_normal_hover_selected_contrast`（主機佈景加固定 Adwaita，亮暗兩種，normal／hover／selected，label 與勾選 image）；evidence/dropdown-light.png、dropdown-dark.png | 通過。我重新擷取的截圖與 repo 內的檔案 SHA-256 完全相同，目視三種狀態的文字與勾選圖示都清楚。另外以 `GTK_THEME=Greybird`、`Adwaita:dark`、`Yaru` 重跑對比測試，全部 OK；也用 Yaru（亮色）擷取一次，App 的固定深色配色沒有被亮色佈景覆蓋。產品 CSS 來自上游，本範圍只新增測試。 |
| SCN-002 | test_previous_session `test_scn002_multiple_rotations_use_latest_sample`；test_freeze_watch `test_scn002_review_anchors_on_last_sample_and_crosses_rotation`、`test_review_survives_a_tail_cut_inside_a_row` | 通過。收集器端選最新有效檔，last_sample／silent_for 正確。回顧端的 MF-1 已修（見下一節），探針 E1、E4、E6 也通過。 |
| SCN-003 | test_previous_session 的 scn003 五項，新增 `test_scn003_session_without_samples_does_not_borrow_an_earlier_session` | 通過。我在乾淨副本重做 mutation（src/freeze-monitor:564 改成 `$2 == "NEVER"`），新測試 FAIL、舊測試照樣 ok，與 review-fix-mutation.log 一致，證明新測試有鑑別力。 |
| SCN-004 | test_previous_session `test_scn004_*`；test_freeze_watch `test_scn004_old_and_new_unclean_events_use_uncertain_labels`、`format_incident_summary` 的「原因未確認」與 `assertNotIn("凍結")`；check.sh 的 UNCLEAN／INTERRUPTED／STOP 斷言 | 標籤、摘要、標題列與報告都用「非正常關機／疑似當機，原因未確認」，同 boot 為 INTERRUPTED，判定成立。**但事件清單的嚴重度顏色漏了 UNCLEAN（MUST FIX 1）**。這不改變措辭，但這部分是上游行為的回歸。 |
| SCN-005 | tests/test_gpu_sample.py 12 項；test_previous_session `test_scn005_*` 兩項；GpuSummaryTests；check.sh 安裝後的 `gpu_processes` 欄位；evidence/review-fix-gpu-cost.json | fixture 層通過（差值、閒置、去重、PID 重用、計數器回退、capacity、缺計數器、fd 消失、權限、預算、其他使用者、受保護程序、新程序優先、非 UTF-8 名稱）。真實 `/proc` 量測可信（見下一節 MF-2）。不支援的驅動標示為「計數器不支援／活動未知」，沒有冒充 0。NVIDIA 專有驅動的資料量見 SHOULD FIX 1。 |
| SCN-006 | tests/test_diagnostic_report.py；test_window_layout `test_scn006_preview_does_not_write_and_cancel_keeps_it_readonly`；evidence/privacy-negative.log；evidence/report-preview.png | 通過。報告產生程式這輪只多了 `errors="replace"`；前 30 分鐘／後 5 分鐘、遮蔽、0600、預覽不寫檔、預覽與匯出使用同一個字串，都由測試涵蓋。探針 E4、E6 中，報告列數等於回顧列數加事件後 30 列。重新擷取的 report-preview.png 與 repo 內的檔案相同。ACCEPT 存檔路徑仍只靠程式碼閱讀確認（`report` 字串直接傳給 `write_diagnostic_report`）。 |

**核准**：`git diff c62159c 5524b0e` 沒有任何差異（range-diff 也顯示兩者相等），所以映射正確。`git diff 5524b0e 6c972c3 -- docs/issues/issue-1/README.md` 在 Gherkin 區塊只有「诊→診」一字簡轉繁，其餘都是記帳區段（核准 commit 回填、TBD-3～5、實作證據、Gate 豁免、Timeline、狀態）。條件、動作、結果都沒變，原核准有效；6 個 Scenario 都是「已核准」。

**rebase 衝突解法**（`git range-diff d8748d6..5b678f6 6d6066e..2ba9ef7`）：
- 程序清單：沿用上游的結構化 CPU／RAM 清單（`format_process_listing`／`_populate_process_list`），GPU 區塊改成獨立的標題加 label，接在後面。實際渲染（Xvfb，真實 GPU JSON）時 GPU 區塊可見，換行正常，上游清單沒有遺失。
- 事故摘要／標題：上游 `format_incident_summary` 原本寫「系統非正常關機或凍結（…）」，標題列寫「系統凍結」；現在改為「非正常關機／疑似當機，原因未確認（最後取樣 … · 中斷 …）」，沒有細節時補上「可能為斷電、強制重啟或當機」，並涵蓋 UNCLEAN。這符合 SCN-004。上游測試原有的「最後取樣」「中斷」斷言都保留，只新增斷言，沒有刪除或弱化上游測試（`git diff 6d6066e 6c972c3 -- tests/test_freeze_watch.py tests/test_window_layout.py` 只有新增）。上游把原始訊息放在 tooltip，這也保留了。
- 遺漏：上游新增的事件嚴重度顏色沒有補上 UNCLEAN（MUST FIX 1）。

0cbc4f2、df8a1cb、a3e841c 只動文件（`--name-status` 只有 AGENTS.md、CLAUDE.md（D）、docs/.dev-rules-kit.json、docs/AGENTS.md、docs/agents/*、issue README、review-9f5712f.md），沒有夾帶程式。

### 第一輪發現的處理

| 第一輪項目 | 結論 | 驗證方式 |
|---|---|---|
| MF-1 tail 截在列中間，回顧為空 | **已修**。`tail_text` 先多讀一個位元組再丟掉第一行，截點剛好在行首時也保留該行。殘留的窄缺口見 NICE 1。 | 重現紅燈：a3e841c 的 src 搭配 HEAD 的 tests，`test_review_survives_a_tail_cut_inside_a_row` FAIL。探針 E1（截點剛好在行首，181 列）、E2（檔案比窗口小）、E3（空檔、只有標題列）、E4（尾端 8 KB NUL 加半截列：回顧 181 列、報告 181 列）、E6（跨輪替且新檔 >4 MB：181 列，間隔都是 10 s，報告 211 列）全部符合預期。 |
| MF-2a 啟用 GPU 後熱度帶只剩約 5 分鐘 | **已修**。`read_tsv_tail` 以 `min_rows=180` 逐次放大 4 倍直到列數足夠或讀完整檔。 | 紅燈重現（`test_live_tail_keeps_half_an_hour_of_wide_rows`）；探針 E5／E5b（窄寬列混合，兩種順序）都 ≥180 列；以本機真實列寬加 GPU JSON（1063 bytes／列、9.2 MB）測得每次 5.6 ms、602 列。 |
| MF-2b 精簡 JSON 與成本證據（TBD-3） | **在已量測的 Intel 桌面上已修，數據可信**；NVIDIA 專有驅動沒有被精簡到（SHOULD FIX 1 `需決策`）。 | 我在真實 `/proc`（664 個程序，load 1.3～2.1）執行 `LC_ALL=C /usr/bin/python3 -I src/freeze_gpu.py --state <scratchpad> --session x` 共 8 次，每次間隔 2 秒：wall 0.07～0.12 s，user+sys 0.07～0.12 s；全部 `status=ok`、沒有截斷、`unavailable=0`、`protected=36`；第一次 34 個 client、7176 bytes，之後 605～740 bytes。在同一個 process 內量 `sample_gpu`，掃描本身約 40～50 ms，是 100 ms 預算的一半。與 review-fix-gpu-cost.json 的數字（中位數約 95 ms、約 0.6 KB、每日約 5.2 MB）相符。 |
| MF-2：放寬上限是否違反「限制取樣成本」 | **不違反**。成本上限仍是 100 ms 掃描預算（原本就是 100 ms）加外層 `timeout 1`。每程序 fd 從 64 放寬到 1024、總 fd 從 2048 放寬到 16384，只影響記憶體與能看到的範圍；舊的 64 上限反而會漏掉 fd 很多的 GPU 程序。以 10 秒週期計約佔單核心 0.7～1.2%，仍是 opt-in。CPU 約是收集器本身（sampling-cost.json 關閉時約 87 ms）的一倍，算不算「明顯」屬於門檻判斷；使用者已選定這個做法並要求實機量測，數據已如實揭露，我不另列缺失。 | 讀程式（src/freeze_gpu.py:17-20、:61、:82）並對照 a3e841c 的舊版；實機量測同上。 |
| SF-1 非 UTF-8 程序名稱 | **已修**。`stat`、`comm` 改以 bytes 讀取後 `decode(errors="replace")`，JSON 為 ensure_ascii。 | 紅燈重現（UnicodeDecodeError）；HEAD 測試通過。 |
| SF-2 掃描順序與永遠 partial | **已修**（Intel 實機）。先以 `/proc/PID` 的 `st_uid` 過濾出本人程序，PID 大的先掃；EACCES 記為 `protected`，不算 `unavailable`。 | 紅燈重現三項；實機 8 次都是 ok。另外確認 `protected` 的判定合理：核心的 `task_dump_owner` 對 world-readable 的 `/proc/PID` 目錄保留 euid，對 `fd/` 則讓不可傾印的程序歸 root，所以本人程序 EACCES 就代表不可傾印。本機 36 個受保護程序實際是 msedge renderer（26）、msedge／chrome zygote、ssh-agent、(sd-pam)、orca-ide、sh；瀏覽器真正開 GPU 的程序（chrome、msedge）仍出現在可見名單裡。fdinfo 讀取失敗仍記 `unavailable`，真正的資料缺口沒有被歸到 protected。UI 會顯示受保護的程序數，其他使用者的程序不檢查這件事也寫在 README／troubleshooting。 |
| SF-3 解碼分歧與無效位元組 | **已修**。`metrics_file_covering`、`metric_window` 都改為 `errors="replace"`，三條讀取路徑一致。 | 紅燈重現；`test_invalid_bytes_do_not_stop_the_review` 通過；E4 的 NUL 尾端通過（Python 3.14，csv 不會因 NUL 拋例外）。 |
| SF-4 移除後殘留 freeze_gpu.py | **已修**。uninstall.sh:73 加入刪除清單，check.sh:633 檢查 `~/.local/share/freeze-watch` 不存在。 | check.sh 在 mktemp HOME 內安裝、移除後通過。 |
| SF-5 證據持久力（SCN-003、截圖、固定佈景） | **已修**。 | mutation 重做（同上）；截圖雜湊一致並目視；對比測試涵蓋固定 Adwaita 與 image 部件。 |
| SF-6 與 TARGET 整合（TBD-5） | **已 rebase**，衝突區段已重審，結果見上一節；有一處遺漏（MUST FIX 1）。 | range-diff 與程式碼閱讀，並以 Xvfb 實測。 |
| NH-1～NH-8 | 未處理，維持建議層級（NICE 2、6）。NH-7 的 `[]` 已修。 | 程式碼閱讀。 |

### 相關失敗面

| 輸入／狀態 | 預期 | 現有覆蓋與實測 | 判定 |
|---|---|---|---|
| tail 截點在列中間 | 丟掉半截列，回顧 30 分鐘 | 測試 + E1 | 通過 |
| tail 截點剛好在行首 | 保留該行 | E1（前一個位元組是 `\n`，tail 剛好 2000 列，第一列完整） | 通過 |
| 檔案比 tail 窗口小／空檔／只有標題列 | 讀完整檔／回傳空 | E2、E3 | 通過 |
| 尾端損毀（NUL、半截列） | 不中止，窗口正確 | E4、SF-3 測試 | 通過 |
| tail 第一列中段損毀 | 回顧與報告一致 | 探針：回顧 0 列、報告 211 列 | 窄缺口（NICE 1） |
| 寬窄列混合 | 熱度帶 ≥180 列 | E5、E5b、測試 | 通過 |
| 跨輪替（新檔 >4 MB） | 兩檔接成連續窗口 | E6、SCN-002 測試 | 通過 |
| 當前 session 沒有有效取樣，前一個 session 有 | unknown，不借用 | 新測試 + mutation | 通過 |
| UNCLEAN 事件在「最近事件」清單 | 與 FREEZE 同為 danger | 探針：沒有 class | **失敗（MF-1）** |
| GPU 程序在掃描中結束 | 略過，不拋例外 | stat／fd 的 ENOENT／ESRCH 略過；readlink 之後才消失記為 unavailable | 通過（文件小落差，NICE 3） |
| PID 重用 | 重新建立基線 | `test_scn005_reused_pid_is_a_new_baseline` | 通過 |
| 受保護程序持有 GPU | 另計，不冒充無活動 | 測試 + 本機盤點（renderer／zygote） | 通過；受保護程序的活動本來就看不到，UI 會揭露數量 |
| 其他使用者的程序（root Xorg 等） | 不算失敗，限制要揭露 | 測試；README／troubleshooting「只檢查本人的程序」 | 通過 |
| 非 UTF-8 名稱 | 替換字元，不失敗 | 測試 | 通過 |
| 不支援的驅動（NVIDIA 專有） | 標示不支援，成本有界 | fixture：64 個 client、9.3 KB／列、永遠 partial | 有界、有標示，但資料量大（SF-1 `需決策`） |
| 同一程序有閒置與活動兩個 client | 畫面上可區分 | 實機渲染：同一個名稱同時出現在兩行 | 可讀性差（SF-2） |
| 取樣成本 | 有預算、實機可接受 | 實機 8 次 + 掃描本身 40～50 ms | 通過 |
| 報告遮蔽 | 不含路徑、參數、程序名稱 | 測試 + 負向對照；REPORT_FIELDS 不含 gpu_processes | 通過 |

### 需求、架構、安全、品質

- 需求：六個 Scenario 都有實作，沒有超出核准範圍。修正內容與 TBD-3～TBD-5 的決策相符。
- 架構：TSV 只在尾端附加欄位（第 36 欄），舊檔也能讀；GPU 採樣是獨立的標準庫腳本，預設關閉；安裝與移除成對。
- 安全：採樣器只讀 `stat`、`comm`、fd 連結與 fdinfo，不讀 cmdline；狀態檔在 umask 077 下以原子替換寫入，權限 0600；報告寫檔 0600。沒有發現權限提升或注入面。
- 跨 Task 重複：(1) 事件種類清單在 7 處重複，其中 1 處已分歧並造成行為不一致（MUST FIX 1）；(2) 回顧（tail 加 fallback）與報告（全檔串流）兩條讀取路徑，在正常資料下已一致，只剩中段損毀的窄缺口（NICE 1）；(3) 核心 pattern 兩份已分歧，只影響分類精度（NICE 2）；(4) Python `incident_paths` 與收集器 awk 的 session 檔案清單規則一致（都在 START／STOP 重設）。
- 過度設計：沒有推測性抽象；`read_tsv_path` 的放大迴圈只有幾行，有明確的終止條件（列數足夠或讀完整檔）。
- 常青文件：README.md、README.zh-TW.md、docs/architecture.md、docs/troubleshooting.md 已依 project.md 更新，「只檢查本人的程序」「受保護程序另列」「每日約 5 MB」「讀滿 180 列」都與實作及我的實測相符；例外是 NICE 2 的 NH-3 與 NICE 3。NVIDIA 的資料量文件沒有提到（SF-1）。

### 豁免、待確認與限制

- Gate 豁免：只有「建立 PR 與 PR 證據」（2026-11-04，使用者原話「這專案可以不走 pr 再本地直接審查」），本報告不要求 PR 證據；其他 gate 都沒有豁免。
- 待確認事項：TBD-1～TBD-5 都是「已解決」，狀態維持原樣。TBD-3 的做法在 Intel 上已達成，NVIDIA 是否也要精簡，列為 SF-1 的新決策題。
- 實作者揭露的限制（引擎占比只在 Intel i915 實機看過、AMD 只有 fixture、GitNexus 沒有本專案索引、尚未部署到真實服務）都如實記錄，不構成缺失。
- reviewer 的限制：沒有 AMD／NVIDIA 硬體，NVIDIA 的資料量是 fixture 推估；GTK 的 ACCEPT 存檔路徑只做程式碼閱讀；依指示沒有部署到真實服務，也沒有在真實 HOME 執行 install／uninstall。GitNexus MCP 沒有本專案的圖譜，呼叫端改用 grep 確認。

### 本次重跑的命令與結果（2026-11-04）

1. `git rev-parse HEAD origin/main`、`git merge-base origin/main HEAD`、`git diff 6d6066e HEAD | git patch-id --stable`：SHA 與 patch-id 都和指定範圍一致。
2. `git diff c62159c 5524b0e`（空）、`git range-diff d8748d6..backup/issue-1-pre-rebase 6d6066e..6c972c3`、`git diff 5524b0e 6c972c3 -- docs/issues/issue-1/README.md`：核准映射正確。
3. `git archive 6c972c3` 解到 scratchpad，執行 `env -u DISPLAY -u WAYLAND_DISPLAY GDK_BACKEND=x11 GSK_RENDERER=cairo TMPDIR=<scratchpad> xvfb-run -a bash scripts/check.sh`：exit 0，`Ran 71 tests … OK`，沒有 skip，`All checks passed.`。
4. 紅燈重現：a3e841c 的檔案搭配 6c972c3 的 tests 與 check.sh，跑 unittest：`FAILED (failures=10, errors=3)`，失敗項目與 review-fix-red.log 相同。
5. mutation 重現：src/freeze-monitor:564 改成 `$2 == "NEVER"`，新的 SCN-003 測試 FAIL，舊測試 ok。
6. 以 python 比對 review-fix-source.json 與 `git show 6c972c3:<path>`：12 個檔案全部 MATCH。
7. `tests/capture_issue1_ui.py` 重新擷取三張圖：SHA-256 與 repo 內的檔案相同，目視可讀；另以 `GTK_THEME=Yaru` 擷取亮色佈景，並以 Greybird、Adwaita:dark、Yaru 重跑 `DropdownContrastTests`，全部 OK。
8. 真實 `/proc` 執行 `LC_ALL=C /usr/bin/python3 -I src/freeze_gpu.py --state <scratchpad>/gpu-state.json --session x` 8 次，另在 process 內量 `sample_gpu` 5 次（結果見 MF-2）。
9. 探針（腳本與資料都放在 scratchpad，不持久化）：tail 邊界 E1～E6、中段損毀列、實際列寬的即時讀取耗時、NVIDIA fixture、事件列樣式、整個儀表板加 GPU 區塊的 Xvfb 渲染。
10. `git diff --check 6d6066e 6c972c3`：只有 kit 範本有行尾空白。

## 流程判定

RETURN TO execute-task

理由：獨立審查已完成，報告已保存於本檔。第一輪的 MF-1、MF-2（含 TBD-3 選定的讀取端修正與精簡 JSON）及 SF-1～SF-6 都已確認修正，實機成本數據可信。但 rebase 整合遺漏了上游的事件嚴重度顏色，新的 UNCLEAN 事件在事件清單中沒有 danger 樣式（MUST FIX 1）；這不在 Gate 豁免紀錄中，所以不能判 PASS。這項修正很小，修正後要以新的 HEAD 重新審查，重審範圍可以集中在該修正與新測試，並對照本報告。SF-1 的 NVIDIA 資料量標為 `需決策`，可以和這次修正一起決定。
