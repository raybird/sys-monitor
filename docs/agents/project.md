# 專案客製規範

本檔由專案維護，初始化只在不存在時建立，更新上游時保留。規劃與交付前讀取；未填內容從 repo 的設定、現有文件與命令取得，不為填表猜測。

## 專案邊界與驗證入口

Freeze Watch 是 Linux 使用者層級的 Bash 收集器與 Python GTK4 儀表板；部署入口為 install.sh，驗證入口為 scripts/check.sh。測試需要發行版 Python 的 PyGObject、GTK4 與 dbus；無圖形顯示時使用 Xvfb。一般驗證不修改已安裝程式與真實服務。

## 提交與交付

分支使用 issue-ID 加描述，PR 目標為 main。提交訊息只描述功能，不含 AI 署名或結尾附註行。issue 文件位於 docs/issues/issue-ID/。

## 常青文件更新責任

- 收集格式與事件語意變更：docs/architecture.md。
- 使用者功能與設定變更：README.md、README.zh-TW.md。
- 診斷限制與操作方式變更：docs/troubleshooting.md。

## 本地 gate 與案例

既有 mcp-memory-libsql.db 是使用者的未追蹤檔案，不納入交付。圖形驗證應涵蓋亮色與暗色主題，不以 CSS 字串存在代替實際可讀性。

最後驗證日期：2026-10-05。
