# Issue #2 第二次獨立審查

- 日期：2026-11-06
- 範圍：相對 BASE 的完整固定未提交 snapshot；包含第一次報告與紅綠證據，不含 investigations/。
- Reviewed BASE SHA：`6d6066ed908ff64b1df9ad00be4485c02812a8bb`
- Reviewed HEAD SHA：不存在；沒有 commit／遠端 branch／PR。
- Reviewed patch-id：`572bb71ccf0d745685fc15312b4dc5749b731945`（依 manifest 19 檔相對 BASE 的完整 diff，含新檔）。
- Manifest SHA-256：`9277ad7aa20835ede382f71e7d9474f9482d95f2fdf16f4a2c53a91695e423c3`（`/tmp/issue2-fixed-files.json`，排序 key、緊密 JSON 編碼）。
- 獨立 reviewer：`/root/review_issue2`；非原實作者；僅寫本報告。
- Artifact：`docs/issues/2/review-followup.md`。第一次報告保留於 `review.md`；本報告不在本輪 snapshot 中。
- 流程依使用者核准的精簡流程；沒有將缺失的共用流程契約補造為已存在。

## 必修問題

### MUST FIX R4：deep 優先再截斷 overview 使部分容器永久飢餓

位置：`src/container_probe.py:165–171`。

overview 先在全體排序清單用 32 步長輪替，再插入 deep priority 並截斷回 32。當 deep 集合固定時，插入所擠出的尾端容器可能永遠沒有其他時間桶補上。新增停止容器後，這會永久遺漏部分退出／OOM 證據，違反已宣告的超額輪替公平性。

獨立精準實驗：fake Engine 的 `/containers/json?all=1` 回 64 個 tracked 容器，ID 000–007 為 running，008–063 為 exited；inspect 回對應狀態，056–063 可設為 OOM。stats 與 top 即時成功。對真實 collect 依 epoch `0,30,...,570` 執行 20 輪，記錄所有 inspect ID：

```text
64 tracked containers, 8 running, 56 stopped; 20 rounds
never inspected: [56, 57, 58, 59, 60, 61, 62, 63]
```

原因：deep 固定為前 8 個；全體 overview 只有 offset=0 與32。offset=0 保留000–031，offset=32 插入000–007後只保留032–055。056–063在兩種時間桶都沒有機會被採樣，即使 daemon 完全健康、預算足夠亦如此。原 80 個全 running 的 fixture 僅檢查 deep 覆蓋，不能證明 mixed overview 公平。

建議：先選 deep，再對剩餘非 deep pool 依實際剩餘名額獨立輪替，或用明確 cursor 保證有界輪替覆蓋。新增 mixed running／stopped（含停止 OOM）及 nontracked running 的 overview 公平測試，同時保持最多32列／8deep／15程序。

## 初次發現的修正覆核

| 發現 | 本輪結果 |
|---|---|
| R1 running-only 遺失 stopped/OOM | `all=1`，保留 running 與 tracked stopped；先 inspect，停止不查 stats/top；狀態附加在第24欄，shell running count 保留。單容器 exited OOM／stats失敗保存inspect的回歸測試通過。基本問題已修，但超額 stopped 覆蓋尚受 R4 阻擋。 |
| R2 全體失聯後舊差分基線 | listing failure invalidate cache；個別 stats 失敗不寫入該 counter；cache write failure移除cache並清空本輪rate；shell helper failure／timeout及collector restart清除cache。失聯→恢復首筆未知的實際 collect 回歸通過，程式路徑一致。 |
| R3 不存在的遠端 SHA | evidence／plan／issue狀態如實揭露Git與GitHub兩途徑被擋，沒有commit／branch／PR，採blob固定snapshot。舊review內的舊狀態為保留的歷史紀錄，不是目前完成宣稱。已修。 |
| S1 CPU未知防護 | cpu_percent要求非空同StartedAt、前進時間、正cores、有效counter；呼叫前核對cache entry id與型別。逆時、空StartedAt、0cores、有效40%差分與毀損cache回歸通過。已修。 |

## 驗收、失敗面與品質

本輪重讀完整產品diff、helper、新增tests、安裝／移除與文件，以及19檔manifest逐檔核對，全部blob吻合；沒有修改產品符號，因此沒有新增symbol impact前置操作。初次報告中關於架構、欄位相容、控制字元處理、程序白名單、保密與依賴的查核仍適用於未變更部分。

- AC1：多project、ID／label、單project保留；R4表示輪替公平尚未完成，不能以80全running deep測試宣稱整體公平。
- AC2：新停止狀態、OOM、restart保留與CPU未知防護方向正確，R4仍可能讓部分退出容器永遠遺漏；GTK實際呈現未驗。
- AC3：I/O ID／StartedAt／時間／下降／缺值與CPU差分防護、失聯後重置已覆核。cache寫入失敗清rate避免不可靠連續性。未發現本輪新增速率必修問題。
- AC4：程序聯集有界、comm而非argv、主機PID／lifetime CPU／主機RAM分母與失敗原因保留。停止容器用stopped原因。真實daemon與GTK未驗。
- AC5：檔尾最多60筆同ID歷史與at-or-before45秒主機對齊保留；停止容器保留歷史入口，但R4仍影響超額容器。跨輪替／壓縮歷史不在承諾範圍，已揭露。實際重啟回看與完整refresh流程未驗。
- AC6：警示與非因果文字保留，未知CPU摘要改為未知；不宣稱正常。停止OOM可警示，但R4仍可能無樣本。視覺QA待驗。
- AC7：GET唯讀、本機socket、6秒合作預算／8秒timeout+1秒grace、2MB回應與32/8/15上限未擴大。硬timeout後刪cache不依賴helper配合。公平性見R4；真實CPU/I/O成本未量測，時間上限不是效能驗收。
- AC8：原11欄位置保留，container_state為第24附加欄，cache不保存程序，舊檔新欄未知，沿用輪替維護；安裝／移除helper與單project相容。未新增argv／環境／容器logs落盤。

未見新第三方依賴、過度抽象或分歧重複邏輯。例外處理、停止分支與cache清除沒有更動容器，也沒有為本機socket額外提權。shell統計只計running，避免新增stopped證據改變原主機計數語意。時間桶公平演算法是本輪唯一新增必修發現。

## 測試與限制

- 已讀 recovery-red.log 的6個失敗斷言與 recovery-green.log；紅燈確實對應R1/R2/S1問題，不是任意更改預期值。
- 已讀 final check-portable.log：67 tests，59通過／8 GUI明確skip，後續shell安裝／升級／移除／主機訊號整合完成。不能稱67個測試全通過。
- reviewer獨立執行 `/usr/bin/python3 -m unittest discover -s tests -p test_container_probe.py -k RecoveryRegressionTests -v`：6 tests全部通過，exit0。另以真實collect追加20輪mixed fixture，重現R4。
- 硬timeout測試現在先建立cache再掛住，驗證外層清除與host metrics保存；實際完整GTK refresh／incident／reopen仍沒有測試或視覺證據。
- Docker socket不可連、基本Gtk.Label在Xvfb崩潰、systemd驗證受sandbox限制均保留未完成。沒有重跑無新疑慮的整套shell測試，也沒有把fixture成本當成實際daemon成本。
- 沒有實際HEAD、PR與合併；本報告不是commit/PR審查PASS，也不是完整AC驗收。

## 流程判定

**RETURN TO execute-task**：修正R4並加入mixed overview公平回歸，重新固定snapshot與重審。R1–R3及S1的上述基本修正可保留。GTK／真實Docker效能／systemd／實際事故回看及提交PR仍受阻或待驗，不能宣告完整完成。

## 固定版本附錄

| 檔案 | Git blob |
|---|---|
| README.md | 06c64a17efce3af205e196223f1499c6b9032cb1 |
| README.zh-TW.md | 67d03565286285909cb1708075c06ea6ac36f3aa |
| docs/architecture.md | 2b937ac9791c366deea515f144ce7ba255f94e90 |
| docs/issues/2/README.md | ce3802b759c95ffff17b1c0bca315521107286d7 |
| docs/issues/2/artifacts/check-portable.log | 96dca3a73a3bf0601b7276429f37cb81d5d8325a |
| docs/issues/2/artifacts/recovery-green.log | 8924fd7a51d620540a681c0440997cf0d2bc1990 |
| docs/issues/2/artifacts/recovery-red.log | f5f8531b4d514b936acc219f7fecb95c10515693 |
| docs/issues/2/evidence.md | 9ed471867c51dcfc2f9542c60a19b0cf1cc77216 |
| docs/issues/2/implementation-plan.md | 2eb6d9f3f1148f64a1ba5b3d7c6f10b4fb84d39a |
| docs/issues/2/review.md | d970159a1b64e4ef75f4f768407aa8268598934b |
| install.sh | bee8995cb6de674cdea0171d4b2152c26226e32f |
| scripts/check.sh | 8f633f5919d0e28ca18a3be4e8d255cad1011592 |
| src/container_probe.py | ca850cb9d8f7b852ae00b835bf5fb16e186d5f74 |
| src/freeze-monitor | 0e311f09a7d1dae2132451c7230d863917fd52c7 |
| src/freeze_watch.py | 17df776f4ec979461e6e79528d94adc1927b9c6f |
| tests/test_container_probe.py | 12d57c849fa8e7ba319e73a3294de48bb171997f |
| tests/test_freeze_watch.py | 01500e5e239feb1628e95b3bc80099c986267ab8 |
| tests/test_window_layout.py | 5fa1367f2e3a62bf1208d54b8508f76dd550b70b |
| uninstall.sh | 693ce0265590255bcde6d77cba093341fea90daf |
