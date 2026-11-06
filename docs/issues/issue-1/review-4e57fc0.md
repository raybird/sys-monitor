# 審查報告

- 範圍：完整交付範圍（本地，已豁免 PR）；本輪重點為 6c972c3..4e57fc0。TARGET origin/main = 6d6066ed908ff64b1df9ad00be4485c02812a8bb，範圍內 commit 為 5524b0e、2ba9ef7、0cbc4f2、df8a1cb、a3e841c、6c972c3、61a93c3、4e57fc0（皆非 merge）
- Reviewed BASE SHA：6d6066ed908ff64b1df9ad00be4485c02812a8bb
- Reviewed HEAD SHA：4e57fc071d8601413aeb4804123ede5d0e0f1875
- Reviewed patch-id：1c5aac5724017b4b4d67987d2a246d154f0d08d6（2026-11-04 以 `git diff 6d6066e 4e57fc0 | git patch-id --stable` 重算，一致；`git merge-base origin/main HEAD` 為 6d6066e）
- 獨立 reviewer：Claude（宿主隔離 subagent，由協調者以 Agent 工具啟動；不是原實作者，也不是第一輪 review-9f5712f.md 或第二輪 review-6c972c3.md 的 reviewer，沒有參與任何實作或修正）
- Review artifact：docs/issues/issue-1/review-4e57fc0.md
- 審查日期：2026-11-04
- 核准基線：5524b0ef78141af82d02086abd5200b58401e106（README `**核准 commit**` 已回填；依 acceptance.md 的 `git log -1 -G '^…\*\*核准來源\*\*…' 4e57fc0` 推導也得到 5524b0e）
- 風險：High（README 分級 Large／High）

## 問題與風險

### MUST FIX

無。

### SHOULD FIX

1. **混合顯示卡（Intel＋NVIDIA 專有驅動）下，同一個程式同時列在「nvidia 計數器不支援」與「持有裝置、取樣期間無活動」** `需決策`（src/freeze_gpu.py:178-185；src/freeze_watch.py:302、:304；docs/troubleshooting.md:129）
   - 原因：TBD-7 的去重只排除 `clients` 裡的名稱（:184 `active`），沒有排除 `unsupported` 的名稱。程式自己對「活動未知」的處理並不一致：首次採樣或計數器回退（`baseline`／`counter_regressed`）的 client 會留在 `clients`，所以會從閒置名單排除；但驅動不支援造成的活動未知，名稱仍會進閒置名單。
   - 實測（fixture，2026-11-04）：程式 `game` 持有一個閒置的 i915 client，加上兩個 `/dev/nvidia0` fd。輸出為 `"idle":["game"],"unsupported":{"nvidia":["game"]}`，畫面顯示「nvidia 計數器不支援，僅確認持有裝置：game」和「持有裝置、取樣期間無活動：game」兩行。docs/troubleshooting.md:129 把後者解釋為「有開 GPU 但沒在用的程式」。PRIME 卸載時，遊戲實際在 NVIDIA 上滿載，Intel 那個 client 只是閒置，讀者卻會讀成「這個程式沒在用 GPU」。gnome-shell、Xwayland 在混合筆電上也會同時持有兩張卡。
   - 為何不是 MUST FIX：同一個區塊仍明確標示這個程式持有不支援計數器的 NVIDIA 裝置；閒置那行指的是 i915 client，本身是真的。實作也照 TBD-7 的字面決定（「閒置名單排除有活動的名稱」）完成。這和第二輪 SF-2 一樣屬於可讀性與誤導風險，而且 4e57fc0 之前就是這樣，不是這次修正引入的退步。不過混合筆電是 NVIDIA 最常見的配置，加上 troubleshooting 的那句解釋，有違 SCN-005「不支援的驅動……不冒充零活動」的精神，所以列為 SHOULD FIX，不列 NICE。
   - 待決問題：活動未知（不支援計數器）的程式，要不要也從閒置名單排除？可選做法：(a) `active` 也納入 `unsupported` 的名稱，和 `baseline` 的處理一致，只改一行；(b) 閒置名單依驅動分行，例如「i915 持有裝置、取樣期間無活動：…」，JSON 也要改成依驅動分組；(c) 維持現狀，在 troubleshooting 註明同一程式可能另外持有不支援的裝置。reviewer 建議 (a)：改動最小，語意也和目前「活動未知不算閒置」的處理一致。

2. **事件嚴重度顏色在實際畫面上不會出現（上游 6d6066e 既有的 CSS 優先順序問題），第二輪 MUST FIX 的修正因此只有 class 層級的效果** `需決策`（src/freeze_watch.py:1048 `.data-list row label { color: #dfe8ed; }` 蓋過 :1050 的 `.danger`／`.warm`；tests/test_window_layout.py:90-104）
   - 實測（2026-11-04，Xvfb，真實的 `data-list` ListBox，以 `Gtk.Widget.get_color()` 讀取實際顏色，亮暗兩種模式）：4e57fc0 的 UNCLEAN、FREEZE（class `danger`）、INTERRUPTED、GAP（class `warm`）、ROTATE（無 class），內文全部是 rgb(223,232,237)；BASE 6d6066e 也完全一樣（FREEZE 有 `danger` class，畫面上卻不是紅色）。截圖目視確認五種事件都是同一個淺灰色，在固定的深色配色上可讀。`.data-list row label` 的權重（1 個 class 加 2 個元素選擇器）高於 `.danger`（1 個 class），所以 label 顏色固定是 #dfe8ed。
   - 影響：4e57fc0 讓 UNCLEAN 與 FREEZE 的 class 一致，這部分正確，也達成 Task 4.4 寫的完成判準「UNCLEAN 與 FREEZE 同為 danger」。但第二輪報告描述的可見影響（UNCLEAN 看起來比橘色的 INTERRUPTED 還不嚴重）實際上不存在，因為 INTERRUPTED 在畫面上也不是橘色。新測試只斷言 CSS class，是代理指標；紅燈是真的，綠燈也由目標行為驅動，所以**不是假綠燈**。依 verification.md，這屬於證據持久力與代理指標的問題。另外，project.md 要求「不以 CSS 字串存在代替實際可讀性」，這個測試沒有驗證實際顏色。
   - 為何不是 MUST FIX：這是 BASE 既有的上游缺陷，本 issue 沒有改 CSS（`git diff 6d6066e 4e57fc0 -- src/freeze_watch.py` 不含 CSS 規則的增刪）。修正後 UNCLEAN 與 FREEZE 在 class 與畫面上都一致，沒有退步。SCN-004 也不要求顏色。
   - 待決問題：要不要在本 issue 修正上游的 CSS 優先順序（例如改成 `.data-list row label.danger`／`.warm`／`.muted`，並把測試改為斷言 `get_color()` 的實際顏色）？還是另開 issue？reviewer 建議另開 issue：這會改變上游所有事件列（以及 `.muted` 中繼資料列）的外觀，超出 issue 1 的核准範圍。若選擇另開，本報告的判定不受影響。

### NICE TO HAVE

1. **兩種「不支援」情況的上限計算不一致**（src/freeze_gpu.py:107-119、:168-171）：沒有 client id 的 fd 在 MAX_CLIENTS 檢查前就 `continue`，不占 client 名額；有 client id 但沒有 `drm-engine-*` ns 計數器的（`unsupported_counters`），仍然每個 client 占一個名額，名稱最多 4 個持有者。輸出形式一致（都依驅動列名稱），但上限不同。探針：70 個沒有計數器的 amdgpu client 會得到 `partial`／`truncated`，畫面顯示「GPU 資料不完整」「已達掃描上限」，名單列出 64 個；70 個 NVIDIA 持有者則是 `ok`，名單列出 70 個。實際會碰到 `unsupported_counters` 的驅動，有 Intel `xe`（kernel 6.11 起提供的是 `drm-cycles-*`，不是 `drm-engine-* ns`，所以 xe 機器全部會標成「xe 計數器不支援」）、VM 的 virtio_gpu，以及可能提供 fdinfo 的 nvidia-drm。一般桌面不會超過 64 個 client，所以影響很小。建議 `unsupported_counters` 也在建立 client 前就依驅動列名稱，或至少在文件說明這個差異；xe 只標示不支援也建議寫進 README 的限制。
2. **`unsupported` 名單沒有自己的上限**（src/freeze_gpu.py:110-112）：只受 512 個程序限制。探針：512 個名稱都不同的 NVIDIA 持有者，每列 10.8 KB。實際上 comm 最長 15 bytes，常見桌面只有數十個不同名稱，所以影響不大；docs/architecture.md:129-131 的上限清單可以補上這一項。
3. **沒有 `drm-driver` 的 `/dev/dri/*` fd 顯示為「unsupported 計數器不支援，僅確認持有裝置：…」**（src/freeze_gpu.py:105；src/freeze_watch.py:302）：英文字串直接出現在中文畫面上。建議顯示成「未知驅動」。`/dev/nvidia*` 改記為 `nvidia` 的命名是正確的（探針 P3、P4、P5b）。
4. `gpu_summary` 遇到 `"unsupported"` 不是 dict 的資料會拋出 AttributeError（src/freeze_watch.py:301）。這和第一輪 NH-7（`{"clients":[{}]}` 拋 KeyError）屬於同一類，只有資料損毀才會發生。
5. 4e57fc0 之前格式的列（`unsupported_identity` client，engines 為空），現在顯示「活動未知」，不再是「計數器不支援，僅確認持有裝置」（src/freeze_watch.py:300）。main 從未發布過 GPU 欄位，只影響開發期間自己產生的資料，可以不處理。
6. 證據描述與持久力：evidence/README.md 寫修正前「UNCLEAN 事件內文只有 `muted`」，但實際紅燈（我重現的結果與 review2-fix-red.log 一致）是內文沒有任何 class（`'danger' not found in []`），`muted` 是下一行的中繼資料。review2-fix-check.log 沒有記錄被測 commit，也沒有像 review-fix-source.json 那樣的雜湊清單。我已在 4e57fc0 的乾淨副本重跑，所以不影響判定。
7. 前幾輪未處理、仍成立的建議（不重複展開）：`incident_rows` 以 `samples[0]` 判斷窗口起點（第二輪 NICE 1）；第一輪的 NH-1、NH-2、NH-3、NH-5、NH-6；收集器呼叫採樣器時沒有加 `-I`（第二輪 NICE 4）；kit 範本有行尾空白（第二輪 NICE 6）。第二輪 NICE 3（architecture 的「程序中途結束」措辭）已在 4e57fc0 同步修正（docs/architecture.md:132-133）。

## 已查核維度

### 驗收與證據

被測版本：在 `git archive 4e57fc0` 的乾淨副本重跑 check.sh，exit 0，74 項測試全部執行，沒有 skip，最後一行為 `All checks passed.`。

| 編號 | 證據位置 | 結論 |
|---|---|---|
| SCN-001 | tests/test_window_layout.py 的對比測試；evidence/dropdown-light.png、dropdown-dark.png | 通過。4e57fc0 沒有改選單 CSS。我用 tests/capture_issue1_ui.py 重新擷取三張圖，SHA-256 與 repo 內的檔案完全相同。另外以真實 `data-list` 擷取亮暗兩種模式的事件清單與 GPU 區塊，文字都可讀（固定深色配色）。 |
| SCN-002 | test_previous_session、test_freeze_watch 的 scn002 與尾端讀取測試 | 通過。4e57fc0 沒有動到讀取路徑（`git diff 6c972c3 4e57fc0 -- src/freeze_watch.py` 只改了 `gpu_summary` 與 `_append_event_row`）。自建探針：5.4 MB、列寬不一、GPU 欄位用新的 `unsupported` 格式，四種截點變化下，回顧都是 181 列，報告都是 211 列（含事件後 30 列）。 |
| SCN-003 | test_previous_session 的 scn003 六項 | 通過。程式沒有變更，check.sh 通過。 |
| SCN-004 | test_previous_session `test_scn004_*`；test_freeze_watch 標籤／摘要；新的 `test_unclean_event_is_marked_as_danger`；check.sh 的 UNCLEAN／INTERRUPTED／STOP 斷言 | 通過。措辭維持「非正常關機／疑似當機，原因未確認」，同 boot 為 INTERRUPTED。UNCLEAN 與 FREEZE 的事件列 class 已一致；畫面顏色沒有差異的原因見 SHOULD FIX 2（上游 CSS）。src/freeze_watch.py 其餘六處事件種類清單（:37、:40、:148、:332、:623、:1582）都包含 UNCLEAN，收集器與 check.sh 也沒有其他只認 FREEZE 的地方。 |
| SCN-005 | tests/test_gpu_sample.py 13 項；GpuSummaryTests；test_previous_session `test_scn005_*`；evidence/review2-fix-gpu-cost.json | 通過，附 SHOULD FIX 1。持有者與活動仍分開；不支援的驅動依驅動名稱明確標示「計數器不支援」，沒有冒充 0%；權限不足、程序退出、受保護程序都會降級處理；成本有上限（見下一節）。 |
| SCN-006 | tests/test_diagnostic_report.py；test_window_layout 預覽測試；evidence/privacy-negative.log；report-preview.png | 通過。報告程式沒有變更，`REPORT_FIELDS` 不含 `gpu_processes`。探針在 metrics 中放入 `/home/...`、`--token=`、程序名稱，以及 GPU `unsupported` 名稱，報告中都沒有出現；核心訊息只留分類（`ring gfx timeout`）。重新擷取的 report-preview.png 雜湊一致。 |

**核准**：`git diff 5524b0e 4e57fc0 -- docs/issues/issue-1/README.md` 的 Gherkin 區塊只有「诊→診」一字簡轉繁，其餘差異都在記帳區段（核准 commit 回填、「已确认→已確認」、TBD-3～7、實作證據、Timeline、狀態）。條件、動作、結果都沒有改變，原核准有效；6 個 Scenario 都是「已核准」。

### 第二輪發現的處理

| 第二輪項目 | 結論 | 驗證方式 |
|---|---|---|
| MUST FIX 1：UNCLEAN 事件列沒有 danger | **已修**（src/freeze_watch.py:1405）。class 與 FREEZE、KERNEL 一致。但實際畫面上，這些 class 的顏色都被上游 CSS 蓋掉（SHOULD FIX 2），所以第二輪描述的可見差異其實不存在；這次修正達成 class 一致，沒有退步。 | 紅燈重現（61a93c3 的 src：`'danger' not found in []`）；HEAD 綠燈；Xvfb 以 `get_color()` 讀實際顏色，HEAD 與 BASE 都量了，並截圖目視。 |
| SF-1（TBD-6「只列名稱」）：沒有 client id 的驅動每個 fd 一筆 client | **已依決定實作**。沒有 client id 的 fd 依驅動以名稱列在 `unsupported`，不占 client 名額；沒有計數器的 client 也併到同一份名單。6×12 個 `/dev/nvidia0` fd 的 fixture 得到 `ok`、沒有截斷、輸出小於 200 bytes（原本 9.3 KB 且截斷）。上限計算不一致見 NICE 1。 | 紅燈重現（`'partial' != 'ok'`）；自建探針 P1～P7。 |
| SF-2（TBD-7「一起修」）：同一程式同時列為有活動與閒置 | **已依決定實作**。閒置名單排除 `clients` 的名稱。名稱相同但 PID 不同時也會排除（P10），這是合理的。殘留的混合顯示卡情況見 SHOULD FIX 1。 | 紅燈重現（`['gpu-owner'] != []`）；探針 P1、P2、P10、P11。 |
| NICE 1～6 | NICE 3 已修；其餘未處理，維持建議層級（本報告 NICE 7）。 | 程式碼與文件閱讀。 |

### 相關失敗面

| 輸入／狀態 | 預期 | 現有覆蓋與實測 | 判定 |
|---|---|---|---|
| NVIDIA 專有驅動（`/dev/nvidia*`，沒有 drm-driver、client id） | 依驅動列名稱，不截斷，標示不支援 | 測試；P5b：70 個持有者，`ok`、523 bytes | 通過 |
| 混合顯示卡：程式的 i915 client 閒置，另持有 nvidia | 不讓讀者以為這個程式沒有使用 GPU | P1：同時列在 nvidia 不支援與閒置兩行 | **SHOULD FIX 1** |
| 混合顯示卡：i915 有活動，另持有 nvidia | 兩行都正確 | P2：「game · i915 · render 60%」＋「nvidia 計數器不支援：game」 | 通過 |
| 有 client id 但沒有計數器（amdgpu 舊格式、xe、virtio_gpu、nvidia-drm） | 依驅動列名稱 | 測試；P4（nvidia-drm）；P5a：超過 64 個 client 時為 partial | 通過；上限不一致見 NICE 1 |
| `/dev/dri/*` 沒有 drm-driver | 標示不支援 | P3：顯示「unsupported 計數器不支援」 | 通過；措辭見 NICE 3 |
| 名稱不是 UTF-8（NVIDIA 路徑） | 替換字元，不失敗 | P7：`g�me�` | 通過 |
| `unsupported` 名稱的資料量上限 | 有上限 | P6：512 個不同名稱，10.8 KB | 有界（NICE 2） |
| 同名但 PID 不同，一個有活動、一個閒置 | 不重複列出 | P10 | 通過 |
| 首次採樣（baseline） | 「活動未知」，不算閒置 | P11；測試 | 通過 |
| 真實 `/proc`（Intel i915，654 個程序，本人 368 個程序、14 153 個 fd） | ok、成本有上限 | 8 次 CLI：wall 0.07～0.10 s，user+sys 0.07～0.10 s；第 1 次為基線，34 個 client、7192 bytes；之後 714～843 bytes；第 2 次因 load 3.05 出現一次 `partial`／`truncated`（protected 從 35 降到 33，推測是 100 ms 預算用完）。之後又跑 30 次，全部 ok。同一程序內 15 次的掃描時間為 41～54 ms。狀態檔權限 600。 | 通過。預算用完時會如實標成 partial，不是缺陷；穩定後每列比 evidence 記錄的 461～588 bytes 稍大（有活動的 client 較多），約每日 6～7 MB，與文件寫的「約 5 MB」同一量級 |
| 舊格式的 GPU 列 | 能顯示 | P8：顯示「活動未知」 | 通過（NICE 5） |
| 資料損毀（`unsupported` 不是 dict） | 不讓儀表板中止 | P9：AttributeError | NICE 4（同 NH-7） |
| UNCLEAN／FREEZE／INTERRUPTED／GAP 事件列 | UNCLEAN 與 FREEZE 一致 | 測試（class）；`get_color()` 實測（全部 #dfe8ed，HEAD 與 BASE 相同） | class 一致，通過；顏色不可見是上游問題（SHOULD FIX 2） |
| 回顧尾端截在列中間（>4 MB、列寬不一） | 回顧 181 列，報告 211 列 | 自建探針，四種截點變化 | 通過 |
| 報告遮蔽（路徑、參數、程序名稱、GPU 名稱） | 都不出現 | 自建探針 + 既有負向測試 | 通過 |

### 需求、架構、安全、品質

- 需求：4e57fc0 的三項修正都在 TBD-6、TBD-7 與第二輪 MUST FIX 的範圍內，沒有新增未核准的行為。GPU JSON 新增 `unsupported` 欄位，對應的常青文件（docs/architecture.md:117-122）已更新；README 與 troubleshooting 原本的措辭仍正確，只有 troubleshooting:129 對閒置名單的解釋在混合顯示卡下不精確（SHOULD FIX 1）。
- 架構：採樣器仍是獨立的標準庫腳本，TSV 欄位位置沒變。改動集中在 `sample_gpu` 的分類與 `gpu_summary` 的呈現，沒有擴散到收集器或安裝流程。
- 安全：新增的 `unsupported` 名稱只來自 comm（tab 與換行已替換，JSON 以 ensure_ascii 輸出），沒有讀 cmdline；報告不輸出 GPU 欄位。沒有新的權限提升或注入面。
- 跨 Task 重複：(1) 事件種類清單仍有 7 處重複，目前都一致；(2) 「活動未知不算閒置」在 baseline 與不支援兩條路徑的處理已分歧（SHOULD FIX 1）。這會造成可讀性與誤導風險，但資料本身沒有錯；依上面的理由，列為 SHOULD FIX 並附決策題，而不是 MUST FIX。(3) 兩種「不支援」的上限計算不同（NICE 1）。
- 過度設計：沒有。修正淨增 14 行，邏輯簡單。

### 豁免、待確認與限制

- Gate 豁免：只有「建立 PR 與 PR 證據」（2026-11-04，使用者原話「這專案可以不走 pr 再本地直接審查」），本報告不要求 PR 證據；其他 gate 都沒有豁免。
- 待確認事項：TBD-1～TBD-7 都是「已解決」，實作與 TBD-6、TBD-7 的決定相符。本報告新增兩個決策題（SHOULD FIX 1、2）。
- 實作者揭露的限制（沒有 NVIDIA 實機、AMD 只有 fixture、GitNexus 沒有本專案索引、尚未部署到真實服務）都如實記錄，不構成缺失。
- reviewer 的限制：本機只有 Intel i915，`unsupported` 路徑在真實 `/proc` 沒有被觸發（實測 `unsup {}`），NVIDIA、混合顯示卡、xe 都只有 fixture 或依 kernel 文件推論；xe 使用 `drm-cycles-*` 這點來自我對 kernel DRM usage stats 的了解，沒有實機確認。依指示沒有部署到真實服務，也沒有在真實 HOME 執行 install／uninstall。GTK 的 ACCEPT 存檔路徑只做程式碼閱讀（與第二輪相同）。

### 本次重跑的命令與結果（2026-11-04）

1. `git rev-parse HEAD origin/main`、`git merge-base origin/main HEAD`、`git diff 6d6066e HEAD | git patch-id --stable`：SHA 與 patch-id 都和指定範圍一致；工作區只有未追蹤的 mcp-memory-libsql.db。
2. `git log -1 -G '^…\*\*核准來源\*\*…' 4e57fc0 -- docs/issues/issue-1/README.md` 得到 5524b0e；`git diff 5524b0e 4e57fc0 -- docs/issues/issue-1/README.md` 確認 Gherkin 只有一字簡轉繁。`git show --name-status 61a93c3` 只新增 review-6c972c3.md。
3. `git archive 4e57fc0` 解到 scratchpad，執行 `env -u DISPLAY -u WAYLAND_DISPLAY GDK_BACKEND=x11 GSK_RENDERER=cairo TMPDIR=<scratchpad> xvfb-run -a bash scripts/check.sh`：exit 0，`Ran 74 tests … OK`，`All checks passed.`。
4. 紅燈重現：61a93c3 的 src 搭配 4e57fc0 的 tests，執行 `xvfb-run -a /usr/bin/python3 -m unittest discover -s tests`：`FAILED (failures=5)`，失敗的 5 項與 review2-fix-red.log 完全相同，失敗原因都和目標行為直接相關。
5. `git diff --check 6d6066e 4e57fc0 -- src tests scripts install.sh uninstall.sh docs/issues docs/architecture.md docs/troubleshooting.md README.md README.zh-TW.md`：通過。
6. 真實 `/proc`：`LC_ALL=C /usr/bin/python3 -I src/freeze_gpu.py --state <scratchpad>/gpu-state.json --session x` 跑 8 次（間隔 2 秒）再跑 30 次（間隔 1 秒），另在同一程序內量 `sample_gpu` 15 次，結果見「相關失敗面」。
7. GPU fixture 探針 P1～P11（腳本在 scratchpad 的 r3probe/probe_gpu.py，不持久化）。
8. Xvfb 渲染：真實 `data-list` 事件列在亮暗兩種模式下以 `get_color()` 讀色，HEAD 與 BASE 都量；擷取事件列與 GPU 區塊的截圖並目視；tests/capture_issue1_ui.py 重新擷取三張圖，雜湊一致。
9. 尾端讀取與報告遮蔽探針（>4 MB、列寬不一、含敏感字串與 `unsupported` 名稱）。

## 流程判定

PASS

理由：獨立審查已完成，報告保存於本檔。第二輪的 MUST FIX 已修，class 與 FREEZE 一致，紅綠燈都重現。SF-1、SF-2 都照 TBD-6、TBD-7 的決定實作。完整範圍 6d6066e..4e57fc0 重跑 check.sh 全綠，六個 Scenario 都有有效證據，抽查的尾端讀取、報告遮蔽、截圖在 HEAD 仍然成立。沒有 MUST FIX。兩項 SHOULD FIX 都標了 `需決策`：混合顯示卡下閒置名單的誤導，以及上游 CSS 讓嚴重度顏色不可見。這兩項依 review-evidence.md 不阻擋 PASS，但建議先請使用者決定 SHOULD FIX 1 要不要在合併前處理。若處理，會產生新的程式提交，需依「審查之後的提交」重新審查。
