# 審查報告

- 範圍：完整交付範圍（本地，已豁免 PR）；本輪重點為 4e57fc0..1a78e03。TARGET origin/main = 6d6066ed908ff64b1df9ad00be4485c02812a8bb。範圍內的 commit 為 5524b0e、2ba9ef7、0cbc4f2、df8a1cb、a3e841c、6c972c3、61a93c3、4e57fc0、a1c7a76、1a78e03，都不是 merge commit（`git log --merges 6d6066e..1a78e03` 為 0 筆）
- Reviewed BASE SHA：6d6066ed908ff64b1df9ad00be4485c02812a8bb
- Reviewed HEAD SHA：1a78e0381693a318d559e5c323f1da1a0ef88e5a
- Reviewed patch-id：286a6a633ec1e2563648617b3d716ccd3af65bbf（2026-11-04 以 `git diff 6d6066e 1a78e03 | git patch-id --stable` 重算，結果一致；`git merge-base origin/main HEAD` 為 6d6066e；工作區只有使用者未追蹤的 mcp-memory-libsql.db）
- 獨立 reviewer：Claude（宿主隔離的 subagent，由協調者以 Agent 工具啟動）。我不是原實作者，也不是第一輪 review-9f5712f.md、第二輪 review-6c972c3.md、第三輪 review-4e57fc0.md 的 reviewer，沒有參與任何實作或修正
- Review artifact：docs/issues/issue-1/review-1a78e03.md
- 審查日期：2026-11-04
- 核准基線：5524b0ef78141af82d02086abd5200b58401e106（README 的 `**核准 commit**` 已回填；依 acceptance.md 執行 `git log -1 -G '^…\*\*核准來源\*\*…' 1a78e03 -- docs/issues/issue-1/README.md`，推導結果同為 5524b0e）
- 風險：High（README 分級為 Large／High）

## 問題與風險

### MUST FIX

無。

### SHOULD FIX

1. **`idle` 欄位的語意改了，docs/architecture.md 沒有同步更新**（docs/architecture.md:119-121；對應程式 src/freeze_gpu.py:183-187）
   - 1a78e03 之後，`idle` 會排除兩種名稱：已列在 `clients`（有活動或活動未知）的，以及已列在 `unsupported` 的。architecture.md:120 仍寫「已列為有活動的程式不重複列出」，沒有提到第二種。依 docs/agents/project.md，「收集格式與事件語意變更」要更新 docs/architecture.md。程式的行為正確；docs/troubleshooting.md:129「有開 GPU 但沒在用的程式」的說法，反而因這次修正變得更準確。
   - 影響：直接讀 TSV 裡 JSON 的人，會以為某個程式只要不在 `idle`，就一定出現在 `clients`。混合顯示卡的程式在穩定狀態下 `clients` 與 `idle` 都沒有它，只出現在 `unsupported`（見下方「相關失敗面」P1、P4、P5）。這只是文件精確度的問題，不影響本次驗收判定。
   - 建議：把 architecture.md:120 的括號改成「已列在 `clients` 或 `unsupported` 的程式不重複列出；同時持有不支援計數器裝置的程式，活動視為未知」，一句話即可。

### NICE TO HAVE

1. **`.data-list row label.safe` 目前沒有標籤會用到**（src/freeze_watch.py:1049）。四個清單裡的標籤只會拿到 `danger`、`warm`、`hot`、`muted` 或沒有 class（:1339、:1366-1370、:1407-1410）。刪掉這條規則，測試照樣通過（突變測試結果是 OK），代表它沒有測試保護，目前也沒有作用。保留下來讓四個等級對稱沒有壞處；如果保留，可以補一句註解說明是為了對稱。
2. **清單內的 `muted` 仍然被 `.data-list row label` 蓋成 #dfe8ed**（src/freeze_watch.py:1048 蓋過 :1031）：事件的時間與種類那一行、程序與容器清單中正常負載的明細，畫出來都是 #dfe8ed，清單外的 `muted` 則是 #9badb7（亮暗主題都實測過）。這是 BASE 就有的行為，TBD-9 的決定只涵蓋等級顏色，所以 1a78e03 沒改不算缺失。只影響視覺層次，可讀性沒有問題（對比 12.0 以上）。之後若要處理，可以加一條 `.data-list row label.muted`。
3. **顏色測試的證據持久力**（tests/test_window_layout.py:106-132）：
   - (a) 期望值寫死調色盤的十六進位值。這是獨立的字面真相，不是同義反覆；但之後調整配色時就要一起改測試。可以考慮改成比較「同一個 class 放在清單外解析出的顏色」，或斷言「不等於清單一般文字的顏色」。
   - (b) 用的是已棄用的 `get_style_context().get_color()`，GTK 4.10 起可以改用 `Gtk.Widget.get_color()`。
   - (c) `_install_css()` 會把 provider 永久掛在 display 上，影響同一個行程裡之後的測試。DropdownContrastTests（:267）原本就是這樣，目前不影響結果（調整測試順序重跑仍通過）。
4. **review3-fix-check.log 的被測版本寫的是「a1c7a76 加上第三輪修正的工作區」，不是 1a78e03**（docs/issues/issue-1/evidence/review3-fix-check.log:1）。我已經在 `git archive 1a78e03` 的乾淨副本重跑 check.sh，所以不影響判定；之後的 evidence 建議記錄提交後的 SHA，或附上像 review-fix-source.json 那樣的雜湊清單。
5. 前幾輪提出、目前仍成立且未處理的建議（只列項目）：第三輪 NICE 1（兩種「不支援」的 client 上限算法不一致）、NICE 2（`unsupported` 名單本身沒有上限）、NICE 3（沒有 drm-driver 時顯示英文字「unsupported 計數器不支援」；本輪探針 P5 仍是如此）、NICE 4（`unsupported` 不是 dict 時拋出 AttributeError）、NICE 5（舊格式資料列顯示「活動未知」）；第二輪 NICE 1（`incident_rows` 用 `samples[0]` 判斷窗口起點）、NICE 4（收集器呼叫採樣器時沒有加 `-I`）、NICE 6（kit 範本有行尾空白）；第一輪 NH-1、NH-2、NH-3、NH-5、NH-6。

## 已查核維度

### 驗收與證據

被測版本：在 `git archive 1a78e03` 解出的乾淨副本執行 `env -u DISPLAY -u WAYLAND_DISPLAY GDK_BACKEND=x11 GSK_RENDERER=cairo xvfb-run -a bash scripts/check.sh`。結果 exit 0，`Ran 76 tests in 22.645s`、`OK`，沒有 skip，最後一行是 `All checks passed.`。另外連續跑完整 unittest 5 次，每次都是 76 項 OK。

| 編號 | 證據位置 | 結論 |
|---|---|---|
| SCN-001 | tests/test_window_layout.py DropdownContrastTests；evidence/dropdown-light.png、dropdown-dark.png | **通過**。1a78e03 新增的 CSS 規則只作用在 `.data-list row label`，選單在 hero 區（src/freeze_watch.py:1159），彈出選單是獨立的 surface，不在 `.data-list` 之下。我在 HEAD 用 tests/capture_issue1_ui.py 重新擷取三張圖，SHA-256 與 repo 內的檔案完全相同（dropdown-dark 723d9406…、dropdown-light cfd6f256…、report-preview ad404cc2…）。 |
| SCN-002 | test_previous_session、test_freeze_watch 的 scn002 與尾端讀取測試 | **通過**。4e57fc0..1a78e03 沒有改到讀取路徑（`git diff 4e57fc0 1a78e03 --stat -- src` 只有 freeze_gpu.py 4 行、freeze_watch.py 4 行 CSS），check.sh 全綠。 |
| SCN-003 | test_previous_session 的 scn003 測試 | **通過**。程式沒有變更，check.sh 全綠，收集器的 UNCLEAN／INTERRUPTED／STOP 斷言也都通過。 |
| SCN-004 | test_previous_session `test_scn004_*`；test_freeze_watch；`test_unclean_event_is_marked_as_danger`；新的 `test_event_severity_colour_is_what_is_drawn` | **通過**。措辭沒有變。UNCLEAN、FREEZE、KERNEL 的內文在畫面上實際是 #ef6861；INTERRUPTED、GAP、WARN 是 #d8c568；STOP、ROTATE 維持 #dfe8ed（Xvfb 實際繪製並取樣像素，見下節）。第三輪 SHOULD FIX 2 描述的「class 正確、畫面沒有顏色」已經消失。 |
| SCN-005 | tests/test_gpu_sample.py（含新的 `test_scn005_unmeasured_holder_is_not_listed_idle`）；GpuSummaryTests；自建探針 P1～P6；真實 /proc | **通過**，附 SHOULD FIX 1（文件）。持有者與活動仍然分開；不支援的驅動依驅動名稱標示「計數器不支援」，沒有冒充 0%，也不再同時出現在閒置名單；真正閒置的程式仍會列出（P1 的 `idle-app`）。權限不足、成本上限的行為沒有變（真實 /proc 6 次都是 ok，每次 0.075～0.099 秒）。 |
| SCN-006 | tests/test_diagnostic_report.py；test_window_layout 的預覽測試；evidence/privacy-negative.log；report-preview.png | **通過**。報告程式沒有變更。我的抽查探針在 400 列 metrics 中放入 `/home/kevin/...`、`--token=abc`、GPU 的 `unsupported`／`idle` 名稱，核心訊息也帶 `--pw=`，報告裡都沒有出現；`ring gfx timeout` 分類有保留。重新擷取的 report-preview.png 雜湊一致。 |

**核准**：`git diff 5524b0e 1a78e03 -- docs/issues/issue-1/README.md` 的 Gherkin 區塊只有一個字由簡轉繁（「诊」改為「診」），其他差異都在記帳區段（核准 commit 回填、「确认」改為「確認」、TBD-3～9、實作證據、Gate 豁免、Timeline、狀態）。條件、動作、結果都沒有變，原核准有效，6 個 Scenario 的狀態都是「已核准」。`git show --name-status a1c7a76` 只新增了 review-4e57fc0.md。

**紅綠燈**：
- 紅燈重現：用 a1c7a76 的完整 archive，把 tests 換成 1a78e03 的版本，執行 `xvfb-run -a /usr/bin/python3 -m unittest discover -s tests`。結果 `Ran 76 tests`、`FAILED (failures=2)`，兩個失敗與 evidence/review3-fix-red.log 完全相同：`['gpu-owner'] != []`，以及 `(223, 232, 237) != (240, 160, 70)`。失敗原因都直接對應目標行為。
- 突變測試：在 HEAD 分別刪除 warm、hot、danger 規則，顏色測試各自失敗，回報的期望值分別是 (216,197,104)、(240,160,70)、(239,104,97)；刪除 safe 規則測試仍然 OK（NICE 1）。刪除 `active.update(...unsupported...)` 這一行，GPU 新測試失敗。
- 結論：紅燈是真的，綠燈也是由目標行為驅動，**沒有假綠燈**。

### 第三輪 `需決策` 項目的處理

| 第三輪項目 | 使用者決定 | 結論 | 驗證方式 |
|---|---|---|---|
| SF-1：混合顯示卡下，不支援計數器的程式被列為閒置（TBD-8） | 「排除並在本 issue 修」，即選項 (a) | **已依決定實作，行為正確**。src/freeze_gpu.py:186 把 `unsupported` 的名稱併進 `active`。P1：`game`（i915 閒置，另持有 nvidia）不再出現在閒置名單，同時真正閒置的 `idle-app` 仍然列出；畫面顯示「nvidia 計數器不支援，僅確認持有裝置：game ｜ 持有裝置、取樣期間無活動：idle-app」。P2：i915 有活動時，兩行都正確。P4（xe 沒有 ns 計數器）與 P5（`/dev/dri` 沒有 drm-driver）也一致排除。P6 只持有 nvidia，不受影響。修正前的 src 在 P1、P3、P4、P5 都會把程式同時列在「不支援」與「閒置」。只有 Intel 的機器 `unsupported` 是空的，所以這行不起作用：真實 /proc 上閒置名單仍有 7～8 個名稱。 | 紅燈重現、突變測試、探針 P1～P6（HEAD 與 a1c7a76 對照）、真實 /proc 6 次 |
| SF-2：清單列的等級顏色被通用文字顏色蓋掉（TBD-9） | 「在本 issue 修」：修正 CSS 優先順序，測試改量實際顏色 | **已依決定實作，畫面確實有顏色**。src/freeze_watch.py:1049-1052 的權重（2 個 class 加 2 個元素選擇器）高於 :1048（1 個 class 加 2 個元素選擇器）。只有 9 個預期的標籤顏色改變（事件內文 6 種、程序 hot／warm 明細、容器 warm 明細），清單外的 danger 與 muted、一般標籤、清單內的名稱與 muted、選單都沒有變（與 a1c7a76 的 src 逐一比對）。測試改成讀 GTK 解析出的顏色，紅燈是真的。 | 下面的 GTK 探針；紅燈重現；突變測試；截圖雜湊比對 |

**GTK 顏色測試是否代表實際畫面（重點 3）**：我在 Xvfb 1280×1024×24 下自建探針（scratchpad 的 r4probe/probe_colours.py，沒有持久化）。探針用真實的 `data-list` ListBox 與 `_append_event_row`／`_append_process_row`／`_append_container_row` 建出 8 種事件、3 種程序、2 種容器，加上清單外的 danger、muted、一般標籤與選單，然後分兩種情況讀色：

- **不 present**：做法與測試相同。
- **present**：實際呈現視窗並跑主迴圈，用 `Gtk.WidgetPaintable` 加 renderer 的 `render_texture` 取得實際繪製的像素，在每個標籤的 bounds 內取離背景最遠的像素當作文字顏色；另外用 `import -window root` 截取 X server 的畫面，目視確認。

兩種情況在亮色（prefer-dark=false）、暗色（prefer-dark=true）以及正常、滑鼠停留（PRELIGHT）組合下，所有標籤的解析顏色都相同，與實際繪製的像素也相同。唯一差異是 `warmproc` 名稱取樣到 #dee7ec，那是抗鋸齒造成的 1 階誤差。滑鼠停留的列背景在繪製結果中實際是 #1b2931，一般列是 #151d23。另外用 `GTK_THEME=Greybird`（主機目前的主題）、`Yaru`、`Yaru-dark`、`Adwaita:dark`、`HighContrast` 重跑，繪製出的文字顏色與預設主題完全相同，因為 app CSS 的優先權是 APPLICATION，高於主題。結論：在這幾種情況下，不 present 讀到的顏色就是畫面上的顏色，用這個方式取代主迴圈有效。

**可讀性**：用 WCAG 公式自己計算，數字與 evidence 相符。

| 文字顏色 | 一般列 #151d23 | 滑鼠停留 #1b2931 | 選取 #223640 |
|---|---|---|---|
| danger #ef6861 | 5.54 | 4.85 | 4.09 |
| hot #f0a046 | 7.97 | 6.98 | 5.88 |
| warm #d8c568 | 9.83 | 8.60 | 7.25 |

最低的是 danger 在滑鼠停留時的 4.85，仍高於一般文字 4.5 的門檻。四個 `data-list` 清單都設成 `SelectionMode.NONE`（src/freeze_watch.py:1228、:1236、:1247、:1255），所以選取背景不會出現。截圖目視確認亮暗主題下紅、黃、橘三色清楚可辨。

**穩定性**：check.sh 跑 1 次、完整 unittest 跑 5 次、test_window_layout 單獨跑 5 次，顏色測試單獨跑，以及「顏色測試 → Dropdown → RowWidth → ReportPreview → 顏色測試」的重排順序，全部 OK；`GSK_RENDERER=gl` 下 RowWidthTests 也 OK。我沒有重現 evidence 提到的「跑主迴圈會 segfault」。不過我的探針是在獨立行程裡跑主迴圈，不能證明它和其他 GTK 測試放在同一個行程時也安全，所以實作者改成不 present 的做法是合理的。

### 相關失敗面

| 輸入／狀態 | 預期 | 現有覆蓋與實測 | 判定 |
|---|---|---|---|
| P1 混合顯示卡：程式在 i915 閒置，另持有 /dev/nvidia0；旁邊有一個真正閒置的程式 | 前者不列為閒置；後者照列 | 新測試涵蓋前者；探針 P1：`idle:["idle-app"]`、`unsupported:{"nvidia":["game"]}` | 通過 |
| P2 混合顯示卡：i915 有活動，另持有 nvidia | 顯示活動，並標示 nvidia 不支援 | P2：`render 50.00%` 加「nvidia 計數器不支援：game」 | 通過 |
| P3 名稱相同、PID 不同：一個只持有 nvidia，另一個 i915 閒置 | 依名稱彙總 | P3：閒置名單沒有 firefox，只列在 nvidia 不支援 | 可接受。與 TBD-7 依名稱去重的設計一致，畫面本來就以名稱呈現；代價是同名的另一個閒置程序不會單獨列出 |
| P4 同一程序同時有 xe（沒有 ns 計數器）與 i915 閒置 | 不列為閒置 | P4 | 通過 |
| P5 `/dev/dri` 沒有 drm-driver，加上 i915 閒置 | 不列為閒置 | P5；畫面顯示「unsupported 計數器不支援」 | 通過；措辭問題同第三輪 NICE 3 |
| P6 只持有 nvidia | 只列在不支援 | P6 | 通過 |
| 首次採樣（baseline） | 活動未知，不列為閒置 | 既有測試；P1～P5 第一次採樣的 `idle` 都是空的 | 通過 |
| 真實 /proc（Intel i915） | ok、成本有上限、閒置名單不受影響 | 6 次：都是 ok、沒有截斷，0.075～0.099 秒；第 1 次是基線，34 個 client、7193 bytes；之後 461～589 bytes；`unsupported` 為 `{}`，閒置 7～8 個；狀態檔權限 600 | 通過 |
| 事件 UNCLEAN／FREEZE／KERNEL／INTERRUPTED／GAP／WARN／STOP／ROTATE，亮暗主題、正常與停留 | 嚴重度顏色實際畫出，其餘不變 | 新測試涵蓋 UNCLEAN、INTERRUPTED、STOP；探針涵蓋全部 8 種與 4 種狀態，另跑 5 個主題 | 通過 |
| 程序清單 hot／warm／muted、容器 warm／muted | 等級顏色畫出；muted 維持原狀 | 新測試涵蓋 hot；探針涵蓋其餘 | 通過（muted 的上游行為見 NICE 2） |
| 清單外的 danger／muted／一般標籤、選單、報告預覽 | 不受影響 | 探針與 a1c7a76 比對完全相同；三張截圖雜湊一致 | 通過 |
| 清單列的選取狀態 | 不會出現 | 4 個清單都是 `SelectionMode.NONE` | 不適用（就算出現，danger 的對比也有 4.09） |
| 報告遮蔽（路徑、參數、GPU 名稱） | 都不出現 | 既有負向測試與本輪抽查探針 | 通過 |

### 需求、架構、安全、品質

- **需求**：1a78e03 的兩處程式修正分別對應 TBD-8 與 TBD-9 的使用者決定，沒有新增未核准的行為。TBD-9 寫的是「修正 CSS 優先順序，測試改量實際顏色」，實作只修了等級顏色，沒有動 muted，屬於最小的解讀，可以接受（NICE 2）。常青文件缺一句 `idle` 語意的更新（SHOULD FIX 1）。
- **架構**：改動只在 `sample_gpu` 的閒置名單分類（多 1 行）與 CSS（多 4 行），沒有擴散到收集器、TSV 欄位、安裝流程或報告。
- **安全**：沒有新增輸入面。`unsupported` 的名稱原本就只來自 comm，報告不輸出 GPU 欄位（抽查確認）。
- **品質**：測試的紅燈、突變與穩定性都驗證過。跨 Task 重複：「活動未知不算閒置」原本在 baseline 與不支援兩條路徑的處理不一致，這次已經統一，第三輪指出的分歧消失。過度設計：沒有；只有 `.safe` 規則目前用不到（NICE 1）。

### 豁免、待確認與限制

- **Gate 豁免**：只豁免了「建立 PR 與 PR 證據」（2026-11-04，使用者原話「這專案可以不走 pr 再本地直接審查」），本報告不要求 PR 證據。其他 gate 都沒有豁免。
- **待確認事項**：TBD-1～TBD-9 都是「已解決」，實作與 TBD-8、TBD-9 的決定相符。本報告沒有新增 `需決策` 項目。
- **實作者揭露的限制**：揭露了 segfault 的原因與改法，不構成缺失；沒有 NVIDIA 與混合顯示卡實機的限制也沿用前幾輪的揭露。
- **reviewer 的限制**：
  - 本機只有 Intel i915，NVIDIA、xe、混合顯示卡都只有 fixture 驗證，真實 /proc 沒有觸發 `unsupported` 路徑。
  - 圖形驗證在 Xvfb 下以 cairo renderer 進行，沒有在真實 Wayland 或 X 桌面確認；GL renderer 只跑了 RowWidthTests。
  - 依指示沒有部署到真實服務，也沒有在真實 HOME 執行 install.sh／uninstall.sh（check.sh 用的是暫存 HOME）。
  - 探針腳本放在 scratchpad，沒有持久化；輸出結果已摘錄在本報告。

### 本次重跑的命令與結果（2026-11-04）

1. `git rev-parse HEAD origin/main`、`git merge-base origin/main HEAD`、`git diff 6d6066e HEAD | git patch-id --stable`：SHA 與 patch-id 都與指定範圍一致。`git log --merges 6d6066e..1a78e03` 為 0 筆。
2. `git log -1 -G '^…\*\*核准來源\*\*…' 1a78e03 -- docs/issues/issue-1/README.md` 得到 5524b0e；`git diff 5524b0e 1a78e03 -- docs/issues/issue-1/README.md` 確認 Gherkin 只有一個字由簡轉繁。
3. `git archive 1a78e03` 解到 scratchpad，執行 `env -u DISPLAY -u WAYLAND_DISPLAY GDK_BACKEND=x11 GSK_RENDERER=cairo TMPDIR=<scratchpad> xvfb-run -a bash scripts/check.sh`：exit 0，76 項 OK，`All checks passed.`。
4. 紅燈：a1c7a76 的 archive 搭配 1a78e03 的 tests，執行 `xvfb-run -a /usr/bin/python3 -m unittest discover -s tests`：`FAILED (failures=2)`，與 review3-fix-red.log 相同。
5. 突變測試：分別刪除 4 條 CSS 規則各一次，以及刪除 GPU 那一行，結果見「紅綠燈」。
6. 穩定性：完整 unittest 跑 5 次、test_window_layout 跑 5 次、顏色測試單獨跑、重排順序跑，以及 `GSK_RENDERER=gl` 跑 RowWidthTests，全部 OK。
7. GTK 探針：HEAD 分 present 與不 present，再與 a1c7a76 的 src 對照，涵蓋亮暗主題與正常、停留狀態，另跑 5 個 GTK_THEME；截圖目視確認。
8. `tests/capture_issue1_ui.py` 重新擷取，三張 PNG 的 SHA-256 與 repo 內一致。
9. GPU fixture 探針 P1～P6（HEAD 與 a1c7a76 對照）；真實 /proc：`LC_ALL=C /usr/bin/python3 -I src/freeze_gpu.py --state <scratchpad>/gpu-state.json --session x` 跑 6 次，間隔 2 秒。
10. 報告遮蔽抽查探針（400 列 metrics、敏感路徑與參數、GPU 名稱）。
11. `git diff --check 6d6066e 1a78e03 -- src tests scripts install.sh uninstall.sh docs/issues docs/architecture.md docs/troubleshooting.md README.md README.zh-TW.md`：通過。

## 流程判定

PASS

理由：獨立審查已完成，報告保存在本檔。第三輪兩項 `需決策` 都依使用者的決定（TBD-8、TBD-9）實作。我自己重現了紅燈，突變測試確認新測試確實守住目標行為。在 Xvfb 下實際繪製並取樣像素，證實等級顏色在亮暗主題、正常與滑鼠停留狀態下都畫出來，而且可讀，其他標籤與選單都沒有受影響。完整範圍 6d6066e..1a78e03 在乾淨副本重跑 check.sh 全綠，六個 Scenario 都有有效證據；抽查的選單截圖、報告預覽、報告遮蔽、真實 /proc 採樣在 HEAD 仍然成立。

沒有 MUST FIX，也沒有新的 `需決策`。SHOULD FIX 1（architecture.md 的 `idle` 語意）是文件精確度問題，不阻擋 PASS。若在合併前修正，新的提交會改到記帳區段以外的檔案，需依 review-evidence.md「審查之後的提交」重新審查，或在 Gate 豁免紀錄留下「不重審」的決定。
