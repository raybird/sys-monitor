# Issue #2 最終未提交快照獨立審查

- 日期：2026-11-06
- 範圍：完整固定工作區交付相對 BASE；含前兩輪報告與測試證據，不含 investigations/。
- Reviewed BASE SHA：`6d6066ed908ff64b1df9ad00be4485c02812a8bb`
- Reviewed HEAD SHA：不存在；這是未提交 snapshot，沒有已建立 PR。
- Reviewed patch-id：`bd07371d1d4ac3f6f7a093ff237c19402996f0be`（manifest 21 檔相對 BASE，包含新檔）。
- Manifest SHA-256：`167e8720fce18282047b2a23878200940e2c1f8f051e509a6ee9751f867691bd`（`/tmp/issue2-fixed-files.json`，排序 key、緊密 JSON 編碼）。
- 獨立 reviewer：`/root/review_issue2`，非原實作者；本輪只寫此報告。
- Review artifact：`docs/issues/2/review-final.md`；本報告不在被審 snapshot 內。
- 適用使用者核准的精簡流程；不補造缺失共用契約、不補造提交或合併證據。

## 程式審查結論

**未提交程式快照未發現必修問題；完整驗收與交付受阻。**

MUST FIX：無新增；先前 R1–R4 已修正，S1 防護亦已處理。這是固定未提交程式內容的獨立查核結論，不是完整 AC PASS、已提交 HEAD／PR 的 PASS 或可合併狀態。

## R4 修正覆核

`src/container_probe.py` 現在先放入 deep 容器，再從全體依 ID 排序清單的 `__overview_cursor` 開始走訪，僅跳過已選入的 deep，收滿32個或走完一輪停止，保存下一個位置。

在固定容器清單與可用cache下，每個走訪位置都使cursor前進；被跳過的容器已由deep採樣，因此不再因priority插入／截斷永久排除尾端。deep最多8個，剩餘名額至少24，維持overview上限32；空清單不進取餘迴圈，小清單走完即可，不重複選入deep。非法非整數cursor重設為0，負值／超範圍整數經取餘規整；cache失效一併清除cursor。沒有引入另一份無界狀態或寫入Docker。

已讀 rotation-red.log，修正前真實漏掉056–063；獨立重跑64 mixed與80全running回歸，均通過。公平性的保證仍以穩定清單、成功cache與查詢預算為前提；持續容器變動、失聯或daemon慢回應不保證固定輪數取得所有完整資料，未將fixture當成生產保證。

## 先前問題結案覆核

| 發現 | 本快照結果 |
|---|---|
| R1 停止／OOM遺漏 | all=1，保留running與tracked stopped，inspect先於stats，停止不查stats/top，保存state/OOM/restart；running主機計數保留。R4修正使超額stopped也有輪替機會。 |
| R2 失敗後沿用基線 | listing失敗、helper失敗／硬逾時、cache寫入失敗、collector重啟均清除cache；個別stats失敗不保留其counter。恢復首筆CPU/I/O未知，下一筆有效資料才差分。 |
| R3 不存在的提交宣稱 | evidence與plan如實記兩條提交途徑受阻，沒有commit／遠端branch／PR，blob snapshot為審查身分。舊報告作歷史保留。 |
| S1 CPU缺值 | 非空同StartedAt、匹配ID、前進epoch、正cores、有效counter，下降或不前進未知；毀損cache entry可恢復。 |
| R4 overview永久飢餓 | 持久cursor逐步走訪取代插入後截斷，mixed64與running80回歸皆通過。 |

## 完整查核維度

本輪逐檔 `git hash-object` 確認21檔與manifest完全一致，讀取最後產品變動與證據；未變更部分沿前兩輪已完成的完整diff查核。沒有修改產品符號，沒有新增需impact的程式操作；GitNexus原實作HIGH／CRITICAL與未索引符號UNKNOWN限制仍保留在evidence中。

| 驗收 | 內容與證據結論 |
|---|---|
| AC1 | 多Compose project、full ID/service識別、單project設定保留；32overview／8deep輪替現在同時覆蓋mixed stopped與allrunning fixture。真實兩專案未驗。 |
| AC2 | CPU、memory/limit、tasks/processes、OOM/restart/health/state與缺值已實作；stopped明確無即時負載，inspect可在stats失敗時留證。GTK呈現待驗。 |
| AC3 | 原始block bytes多裝置加總，實際epoch差、ID／啟動／重置／缺值保護與CPU分母、恢復基線均覆核；沒有把未知資料轉有效0%。 |
| AC4 | comm而非argv；CPU/memory/D union最多15，PID為主機PID，程序CPU為ps lifetime、memory為主機RAM百分比，錯誤原因與上限明確。真實top與widget仍待驗。 |
| AC5 | 附加TSV持久化、匹配ID最多60筆、此前45秒主機對齊與缺口，無未來樣本；檔尾／不跨輪替壓縮界線已揭露。實際重啟回看與完整GUI refresh待驗。 |
| AC6 | OOM/unhealthy/nonzero restart/D/Z醒目條件與非因果文字有明文；未知與停止負載明確，最後採樣時間與過期文字存在。視覺醒目性待驗。 |
| AC7 | 本機socket GET唯讀、拒遠端歸因、無提權／exec；6秒cooperative／8秒+1秒kill grace、2MB／32／8／15限制、硬逾時仍保留host metrics。fixture不能代替真實CPU/I/O成本。 |
| AC8 | 原11欄相容、新state第24欄，沿輪替／壓縮／保留機制；0600 cache僅identity/counter/cursor，程序只存必要欄位，無argv/env/logs落盤。 |

安全／架構／品質：沒有新增第三方依賴、對容器寫操作、容器內agent或額外權限；程序欄位白名單與TSV控制字元清理保留。詳情formatter與採樣欄位集中，歷史選擇與signature刷新設計未新增分歧重複。安裝／升級／移除helper接入既有路徑，read_tsv_path預設參數保留原呼叫。cursor狀態與counter共用失敗處理，不引入第二套儲存生命週期。

失敗面覆核包含空daemon、endpoint失聯、stats失敗但inspect有效、容器停止／OOM、counter下降、CPU缺值／逆時、毀損cache、全體硬timeout、超額mixed輪替與舊schema。可讀錯誤轉未知，限制與失敗不宣稱健康。

## 驗證證據與剩餘限制

reviewer獨立執行：

```text
PYTHONPATH=tests /usr/bin/python3 -m unittest \
  test_container_probe.MixedRotationRegressionTests \
  test_container_probe.FailureAndLimitTests.test_more_than_32_containers_do_not_starve_deep_projects \
  test_container_probe.RecoveryRegressionTests -v
Ran 8 tests in 0.030s — OK, exit 0
```

`git diff --check`也通過。未重跑沒有新疑慮的整套shell。已讀最後portable log：68 tests，60通過、8GUI明確skip，後續安裝／升級／移除／主機訊號shell整合完成；不得稱68全通過。回歸紅燈與綠燈來源可追溯，新增mixed測試確實重現修正前漏採，不是只核對文字。

仍缺：真實runwukong/runtelenexus負載與採樣成本、真實Docker top、GTK完整widget／視覺QA與重啟事故回看、systemd user verify。Docker socket權限、Gtk.Label基本崩潰與systemd socket限制已揭露，沒有假冒通過或以fixture替代。

提交交付亦未完成：本機Git readonly、GitHub create_tree遭「requires approval, but approval policy is never」阻擋。沒有已提交HEAD／branch／PR。這些受阻不等同程式必修，也不等同已被豁免。後續在可用環境補驗、提交、取得正式固定SHA與PR，再依實際內容核對審查artifact有效性。

## 流程判定

程式內容：**此固定未提交快照未發現必修問題**。

整體流程：**完整驗收與提交PR仍受阻／待驗**，不是全流程PASS、等待合併或已完成。前兩輪RETURN所列產品問題已在此快照處理；無需因相同外部限制重複修產品，但不得消除待驗項目或虛構提交身分。

## 固定版本附錄

| 檔案 | Git blob |
|---|---|
| README.md | 06c64a17efce3af205e196223f1499c6b9032cb1 |
| README.zh-TW.md | 67d03565286285909cb1708075c06ea6ac36f3aa |
| docs/architecture.md | 1dbf84707ef5926a96ccee665dfa1a252e865ffb |
| docs/issues/2/README.md | 9dd32b8392203b780f1dc27f557a04df21d9532c |
| docs/issues/2/artifacts/check-portable.log | 7676d7b166ea659c11d42750c054cb278d218135 |
| docs/issues/2/artifacts/recovery-green.log | 8924fd7a51d620540a681c0440997cf0d2bc1990 |
| docs/issues/2/artifacts/recovery-red.log | f5f8531b4d514b936acc219f7fecb95c10515693 |
| docs/issues/2/artifacts/rotation-red.log | 06c5361733ca165d28def0f20e7792e375b512ee |
| docs/issues/2/evidence.md | b15ac375cdc5be06ae38d04f8318d50cc3d10b3f |
| docs/issues/2/implementation-plan.md | d5b07ea69b0dfbfe11729f72861d5771ae111b2a |
| docs/issues/2/review-followup.md | cab6eda7ca141888da48c6ba52f3794fc496abe2 |
| docs/issues/2/review.md | d970159a1b64e4ef75f4f768407aa8268598934b |
| install.sh | bee8995cb6de674cdea0171d4b2152c26226e32f |
| scripts/check.sh | 8f633f5919d0e28ca18a3be4e8d255cad1011592 |
| src/container_probe.py | 21a3990f464c8aee97931a4816b6a3be76ef6992 |
| src/freeze-monitor | 0e311f09a7d1dae2132451c7230d863917fd52c7 |
| src/freeze_watch.py | 17df776f4ec979461e6e79528d94adc1927b9c6f |
| tests/test_container_probe.py | 4eca1210173069360a612f55d715a2ff9fb53f51 |
| tests/test_freeze_watch.py | 01500e5e239feb1628e95b3bc80099c986267ab8 |
| tests/test_window_layout.py | 5fa1367f2e3a62bf1208d54b8508f76dd550b70b |
| uninstall.sh | 693ce0265590255bcde6d77cba093341fea90daf |
