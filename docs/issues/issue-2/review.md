# Issue #2 獨立審查報告

- 日期：2026-11-06
- 範圍：完整交付的固定未提交 working snapshot；不含 investigations/，不是已建立 PR 的審查。
- Reviewed BASE SHA：`6d6066ed908ff64b1df9ad00be4485c02812a8bb`
- Reviewed HEAD SHA：不存在；本機 Git 寫入與 GitHub object API 均受環境權限阻擋。
- Reviewed patch-id：`5e1fdb41fba4775c7d2e22a7c1d11c9389aa1503`。由下列 16 檔相對 BASE 的 diff 計算，包含未追蹤的新檔；不是 commit 身分。
- Snapshot manifest SHA-256：`bcdda0b2a4729e19a0b80e5e0ac890671996e698a7885e1b9c0dfb3e59e8b4d6`（原 `/tmp/issue2-files.json`，排序 key、緊密 JSON 編碼）。
- 獨立 reviewer：`/root/review_issue2`；不是原實作者。只讀產品，僅寫本報告。
- Review artifact：`docs/issues/2/review.md`
- 流程依據：使用者同意本次精簡流程，免缺失的 docs/AGENTS.md；沒有補造其他共用契約或核准。

## 固定版本

逐檔執行 `git hash-object <path>`，16 檔均與協調者給定清單一致。報告本身不在被審 snapshot 內。

| 檔案 | Git blob |
|---|---|
| README.md | 4eb671e3fa14736a478927fbbf977c2e540beb54 |
| README.zh-TW.md | 46558a1bfc58cb4aa7f558a72a4dede49f16c7a7 |
| docs/architecture.md | 6ebf409cdafad0ae33ed9377a15b044afa0455c3 |
| docs/issues/2/README.md | ac172a9028b32a4a014f0d98ab5b6d1a6f840b31 |
| docs/issues/2/artifacts/check-portable.log | 6ff7693b61cacfacb3b68eb8cf687dd8d71cabd6 |
| docs/issues/2/evidence.md | e4293029937e943814396d3a36675616e96bf5eb |
| docs/issues/2/implementation-plan.md | 26a270994de3475065e49080ed85f917e43cdb4c |
| install.sh | bee8995cb6de674cdea0171d4b2152c26226e32f |
| scripts/check.sh | 8f633f5919d0e28ca18a3be4e8d255cad1011592 |
| src/container_probe.py | acd39b5ea4893dd60bfb7e43c6a83f3436c9b7ca |
| src/freeze-monitor | c70a32f7310835d29ca1a37af119b04c07fcc0b2 |
| src/freeze_watch.py | ae3e8e396333c1101d8ef46c439b1324a0740249 |
| tests/test_container_probe.py | fe82259aba82c9fdfb6dde5cb5c5b9a227a30ed7 |
| tests/test_freeze_watch.py | 01500e5e239feb1628e95b3bc80099c986267ab8 |
| tests/test_window_layout.py | 5fa1367f2e3a62bf1208d54b8508f76dd550b70b |
| uninstall.sh | 693ce0265590255bcde6d77cba093341fea90daf |

## 問題與風險

### MUST FIX R1：停止／OOM 的容器不會被採樣

位置：`src/container_probe.py:121`、`:156`；`src/freeze_watch.py:614`。

`GET /containers/json` 預設只列執行中的容器。容器因 OOM／崩潰退出後，沒有後續 inspect，所以不能保存 `State.OOMKilled` 與退出狀態。最新清單只保留最新 timestamp，因而把最值得追查的容器移除。只有在 running 時填入 OOM 欄位，無法覆蓋 AC2 的重要失敗面。不可把 exited 當成「不存在任何容器」或把缺失當正常。

重現：fake daemon 先列一個 worker，再依 running-only listing 語意於停止後回傳 `[]`，`collect` 回傳 `ok` 與單筆 `sample_status=empty`，無 worker／OOM 資料。現有測試僅涵蓋 running／空 daemon，未涵蓋 OOM exited。

建議：在既定上限內納入選定 project 的停止容器，先 inspect 保存 state／OOM／restart，再依 running 狀態決定是否請求 stats/top。停止容器的 CPU/I/O 應明確未知或不適用；不得因 stats 不可取而丟掉 inspect 證據。原 running 容器數與 tasks 語意須保留。新增 exited OOM、stats 失敗仍保留狀態、停止後歷史可查看的測試。

### MUST FIX R2：全體採樣失敗後沒有清除差分基線

位置：`src/container_probe.py:119–126`、`:160–173`；`src/freeze-monitor:250`。

成功採樣後若 listing／endpoint 失敗，`collect` 在讀寫 cache 之前直接 return；外層硬逾時也不使舊 cache 失效。下一次成功仍用舊 counters 計 CPU 與 I/O。這與 `docs/architecture.md` 明定的「A missing sample resets the baseline」及 AC3 缺值後不產生假速率的界線不一致。讀寫增量跨越不可觀察缺口，被呈現為恢復後的區間值。

獨立可重現結果（fake Engine，真實 collect 與暫存 cache）：

```text
t=100 read=100: ok, read_bps=None
t=130 endpoint/listing OSError: unavailable, read_bps=None
t=160 read=700: ok, read_bps=10.0
```

恢復第一筆應未知，下一筆連續且有效樣本才恢復差分。需同時處理 listing 失敗、helper 被外層殺死與正常 per-container 失敗；加回歸測試，且不要讓補救檔案操作中斷主機監控。

### MUST FIX R3：證據文件仍宣稱不存在的遠端提交身分

位置：`docs/issues/2/evidence.md:55–57`。

文件寫「使用…Git object API…建立…tree／commit／branch」，並說 review 以「該遠端 SHA」為準。但協調者提供的實際結果為 API 也遭 approval policy 拒絕，沒有遠端 SHA。本次只能審查上述固定 blob snapshot。此段必須如實改寫，不能把計畫或嘗試當成已取得的版本證據。

### SHOULD FIX S1：CPU 差分的未知條件防護不完整

位置：`src/container_probe.py:167–173`。

CPU 未像 I/O 要求非空 StartedAt、時間前進；online_cpus 與 percpu_usage 都缺時會採 cores=0，得到看似有效的 0%。建議要求有效啟動身分、正核心數、正時間間隔，否則保留未知，新增缺 accounting／逆時／restart CPU 測試。原有 I/O 測試不能當成 CPU 差分測試。

## 已查核維度

### 驗收與證據

| AC | 查核與判定 |
|---|---|
| AC1 | 安裝接受逗號 project，保留單 project；helper 使用 full ID 與 Compose labels。80 容器、10 輪 32 overview／8 deep fixture 有覆蓋，deep 候選優先可避免單純 overview cap 排除。真實 daemon 成本與 timeout 下覆蓋速度未驗。 |
| AC2 | running 時的 CPU、memory/limit、tasks、restart、health、OOM 與未知文字已實作；R1 阻擋停止／OOM 事故證據，S1 指出 CPU 缺值邊界。不能判 AC2 完成。 |
| AC3 | bytes 原始值、多裝置加總、時間差、ID／restart／計數下降防護有測試；R2 為缺漏的全體失敗基線；CPU 缺值另見 S1。 |
| AC4 | 程序只留 pid/state/cpu/memory/comm，CPU／memory／D 聯集最多 15，表明 ps lifetime CPU、主機 RAM 分母；缺欄位、timeout 有未知原因。真實 Docker top 與 GTK 呈現仍未驗。 |
| AC5 | TSV 附加欄位、最多 60 個 matching ID 樣本、主機 at-or-before 45 秒對齊有資料層測試。只讀可用檔尾、不跨輪替已揭露；R1 也影響停止後最新清單的歷史入口。實際重啟回看／GTK refresh 狀態保留未驗。 |
| AC6 | OOM/unhealthy/nonzero restart/D/Z 為可解釋警示，未知無正常宣稱，文字不宣稱因果；欄位與時間顯示已實作。R1 使停止後的異常不可見；視覺醒目性未驗。 |
| AC7 | Docker 僅 GET，context inspect 僅解析本機 socket，拒絕 TCP/SSH，無 exec／提權。6 秒 cooperative、8 秒外層 timeout+1 秒 kill grace 與回應大小上限已揭露；主機迴圈 timeout 落盤整合測試通過紀錄可追溯。真實兩專案 CPU／I/O overhead 未量測，不能宣稱低成本已驗收。 |
| AC8 | 原 11 欄保留、CSV/TSV JSON roundtrip、有控制字元清理、舊 schema 顯示未知。沿原 rotation／compression／expiry 路徑，無另一套無界程序儲存；cache 僅 counters、0600。未保存 argv/env/logs。 |

### 相關失敗面與程式品質

- endpoint 缺失、遠端 daemon、HTTP 失敗、容器消失、回應超量、程序欄位不支援、空 daemon：具有回傳未知或有界失敗路徑；R1／R2 是未覆蓋的狀態轉換。
- 上限與公平：固定時間桶輪替、有界程序聯集、deep 優先；fixture 證實理想回應下公平，不證明 daemon 長時間慢回應下仍於固定輪數完成。超額 sample_state=partial 已揭露。
- 速率與 CPU：CPU 使用 Docker counters，程序 CPU 使用 ps lifetime，兩者口徑有分別說明。memory 為含 cache 原始 usage，文件與 UI 一致。缺值不應被核心數 fallback 轉成 0，見 S1。
- UI：詳情 formatter 集中；歷史與目前樣本共用，選擇 epoch、expanded ID 跨重建保留。container_signature 加入 evidence_detail/history_signature，避免只改新欄位卻不刷新。未見不必要新框架或有分歧的重複計算。
- 相容與架構：新增 helper 標準庫，安裝／移除包含 helper，來源下載沿既有整包路徑；read_tsv_path optional byte_limit 保留原呼叫，Docker 專用 2 MB limit。原主機欄位與採樣入口保留。
- 保密：Docker inspect 完整回應只在記憶體處理，寫入白名單欄位；comm 非 argv。未發現新增憑證、logs、環境寫盤或對容器寫入。
- 本 reviewer 沒有修改任何產品符號，因此沒有需先執行的 symbol impact；原實作 HIGH／CRITICAL 影響與 GitNexus 不完整索引限制已在 evidence.md 揭露，不能把 UNKNOWN 當成無風險。

### 測試真偽、限制與豁免

已讀完整新增 tests、check.sh 與 `artifacts/check-portable.log`。保存的命令明確傳入 GUI/systemd skip 旗標，61 tests、8 skips（53 passed），不是 61 全通過。shell integration 實際執行 helper 替身、落盤與 timeout；JSON 主程式序列化也真實測試，沒有只以字串斷言冒充整合驗證。

獨立追加的精準實驗以真實 collect/cache 驗證 R2（結果如上），並驗證 running listing 排除停止容器後輸出空 snapshot。本次沒有重跑沒有新疑慮的整套 shell checks。

GUI 在基本 Gtk.Label 就 segfault、Docker socket 無法連線、systemd verify socket 受限均有揭露；現有 GUI test 僅涵蓋直接建立 expander 的選擇與寬度，尚不能證明完整 refresh／incident／重新開啟畫面正確。現有證據支持部分實作驗證，不支持完整 AC／效能／桌面驗收通過。使用者同意精簡流程不等於豁免這些外部驗收。提交／PR 被阻擋不構成程式錯誤，但必須保留未提交狀態且更正 R3。

## 流程判定

**RETURN TO execute-task**。

此固定 snapshot 有 R1–R3 MUST FIX。修正後須重取 blob 清單／固定範圍，執行相應回歸測試並重新獨立審查。即使修正後沒有程式問題，GTK、真實 Docker 成本與實際事故回看仍需保留待驗；提交／PR 也仍待環境權限解決。本報告不是完整 AC PASS、不是已提交 HEAD 的審查 PASS，也不是可合併 PR 的背書。
