# 審查報告
- 範圍：局部 diff（第四輪 PASS 之後的文件提交）；完整範圍審查見 review-1a78e03.md
- Reviewed BASE SHA：1a78e0381693a318d559e5c323f1da1a0ef88e5a
- Reviewed HEAD SHA：f355bfeefdacee00d0a820dc64ab8396be98ff66
- Reviewed patch-id：3495e56a57f16bf9b560f50c8b61727d3eb36644（`git diff 1a78e03 f355bfe | git patch-id --stable`）
- 獨立 reviewer：Claude Code 隔離 subagent（Opus 5.5），不是原實作者，也沒有參與前四輪審查
- Review artifact：docs/issues/issue-1/review-f355bfe.md
- 審查日期：2026-11-04

範圍內有兩個提交：db3adab（父提交 1a78e03，只新增 review-1a78e03.md）與 f355bfe（父提交 db3adab，修改 docs/architecture.md 與 issue README）。兩個都不是 merge 提交。f355bfe 改到記帳區段以外的檔案（docs/architecture.md），依 review-evidence.md「審查之後的提交」不能沿用第四輪 PASS，所以做這次重新審查。

## 問題與風險
- MUST FIX：無
- SHOULD FIX：無
- NICE TO HAVE：
  1. docs/architecture.md:120 前半句「已列為有活動」沿用了舊措辭。程式實際排除的是所有已列在 `clients` 的名稱（src/freeze_gpu.py:185），其中也包括引擎狀態是 `baseline`、`counter_regressed`（活動未知）的 client。自建探針確認：同一程式一個 client 閒置、另一個是新 client（`baseline`）時，`clients` 只有 `[('9', {'render': 'baseline'})]`，`idle` 是 `[]`。新句子把「（活動未知）」只放在 `unsupported` 後面，讀者可能以為 `clients` 只有「有活動」的列。上一句已寫明「每列 JSON 只記有活動或活動未知的 client」，所以合起來讀仍然正確。這個措辭在 1a78e03 之前就有，不是這次提交造成的，不阻擋。可以改成「已列在 `clients`、或同時列在 `unsupported` 的程式不列入」。
  2. 改過的這一行比前後的 CJK 行長很多（其他行約 40 字換行）。Markdown 顯示結果相同，只影響原始檔閱讀。

## 已查核維度
- **變更範圍**：`git diff 1a78e03 f355bfe --name-status` 的結果是 `M docs/architecture.md`、`M docs/issues/issue-1/README.md`、`A docs/issues/issue-1/review-1a78e03.md`，和任務說明一致。`git diff 1a78e03 f355bfe -- src tests scripts install.sh` 是空的，沒有程式或測試變更。`--stat` 是 3 個檔案，+143／-1。工作區只有使用者既有的未追蹤檔案 mcp-memory-libsql.db（project.md 有登記，不納入交付）。
- **文件與實作一致性**：讀了 src/freeze_gpu.py:105-112、128、168-187。`unsupported` 的名稱有兩個來源：沒有數字 client id 的持有者（:107-112），以及沒有引擎計數器的 client（:168-171）。`idle` 收集的是讀數都為零的 client 名稱（:178-180）。最後扣掉 `clients` 的所有名稱和 `unsupported` 的所有名稱（:185-187）。新句子「已列為有活動、或同時列在 `unsupported`（活動未知）的程式不列入」正確描述了第二種排除，解決了第四輪 SHOULD FIX 1 指出的缺漏：讀者不會再以為不在 `idle` 的程式一定在 `clients`。下一句「沒有 client id 或引擎計數器的持有者……列在 `unsupported`，不冒充零活動」和兩個來源一致。用語（`idle`、`unsupported`、「活動未知」、「程式」）和同段、第四輪報告、docs/troubleshooting.md 的說法一致。`/usr/bin/python3 -m unittest tests.test_gpu_sample` 跑了 14 個測試，全部 OK。其中 `test_scn005_unmeasured_holder_is_not_listed_idle` 覆蓋了 `unsupported` 排除，`test_scn005_active_name_is_not_also_listed_idle` 覆蓋了有活動排除。自建探針另外確認真正閒置的程式仍會列在 `idle`（`idle: ['gpu-owner']`）。唯一的落差是 NICE 1 的既有措辭。
- **Timeline**：README 的差異只有 `## Timeline` 表格新增一列：「2026-11-04｜第四輪審查 PASS（1a78e03）；決定補上 architecture.md 的 idle 語意，並只審查該文件提交｜使用者」。內容和 review-1a78e03.md 的判定（PASS、SHOULD FIX 1）、這次提交的內容、任務說明的使用者決定都相符。日期是當日日期，其他章節、標題與粗體欄位都沒有變。
- **對完整範圍 PASS 的影響**：沒有程式、測試、規格（Gherkin）或核准欄位的變更，SCN-001～006 的證據和核准基線都沒有受影響。architecture.md 的改動只讓常青文件更貼近 1a78e03 已審查的行為，不改變任何行為。db3adab 只新增報告，新增後沒有再修改。沒有理由認為第四輪對 6d6066e..1a78e03 的 PASS 失效。第四輪 PASS（綁 1a78e03）加上這次局部 PASS（綁 f355bfe），合起來涵蓋 6d6066e..f355bfe。

## 流程判定
PASS
