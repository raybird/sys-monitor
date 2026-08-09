# Freeze Watch

Freeze Watch 是一套輕量 Linux 凍結診斷工具，包含背景採樣器、Docker
程序觀測、GTK4 儀表板，以及顯示即時 CPU 溫度的系統列圖示。

它的用途是保留「系統完全凍結、鍵盤滑鼠失效、只能強制重開」之前的證據。

## 功能

- CPU、GPU、NVMe 溫度，支援 AMD、Intel 與 ARM 平台
- 負載、記憶體、swap、磁碟與 Linux PSI 壓力（含 full 與不可中斷睡眠程序數）
- GPU busy 與最活躍程序
- Docker CPU、記憶體、tasks、OOM、重啟與 zombie
- 可指定一個 Docker Compose project 做深度程序觀測
- 系統列即時顯示 `CPU 58°`
- GTK4 儀表板、最近 30 分鐘熱度帶與採樣停擺標記
- 事故回顧：選一次凍結或停擺，看它發生前的半小時
- 每日換檔、14 天後壓縮、90 天後刪除
- 全部以使用者身分執行，不需要 root daemon

## 系統需求

- Linux 且有 systemd 使用者服務
- Python 3、PyGObject/GTK4、dbus-python
- Bash 與常見 GNU/Linux 工具
- Docker 為選用
- 系統列需要 StatusNotifier/AppIndicator host

| 發行版 | 套件 |
| --- | --- |
| Debian、Ubuntu | `python3 python3-gi python3-dbus gir1.2-gtk-4.0` |
| Fedora、RHEL | `python3 python3-gobject python3-dbus gtk4` |
| Arch | `python python-gobject python-dbus gtk4` |
| openSUSE | `python3-gobject python3-gobject-Gdk python3-dbus-python typelib-1_0-Gtk-4_0` |
| Alpine | `python3 py3-gobject3 py3-dbus gtk4.0` |
| Void | `python3-gobject python3-dbus gtk4` |

缺套件時安裝器會偵測套件管理員並印出對應指令。在 Ubuntu 以外的 GNOME 上，
系統列可能還需要 `gnome-shell-extension-appindicator`。

## 安裝

不需要 clone，一行搞定：

```bash
curl -fsSL https://raw.githubusercontent.com/raybird/sys-monitor/main/install.sh | bash
```

安裝器會抓取最新的 release，全部裝在 `$HOME` 底下，不需要 root。
要透過管線傳參數：

```bash
curl -fsSL https://raw.githubusercontent.com/raybird/sys-monitor/main/install.sh |
  bash -s -- --compose-project runtelenexus
```

從 checkout 執行的行為一樣，會安裝當前工作目錄的版本：

```bash
git clone https://github.com/raybird/sys-monitor.git
cd sys-monitor
./install.sh
```

安裝器可以重複執行，不會刪除既有監測資料。
安裝後也能從桌面應用程式清單搜尋「Freeze Watch 系統監測」開啟。

### 選項

| 選項 | 用途 |
| --- | --- |
| `--compose-project NAME` | 深度觀測指定的 Docker Compose project |
| `--python PATH` | 指定直譯器，不自動偵測 |
| `--ref REF` | 安裝指定的 tag、branch 或 commit |
| `--repo OWNER/NAME` | 從 fork 安裝 |
| `--source DIR` | 從已解壓的原始碼目錄安裝 |
| `--no-start` | 只安裝檔案，不啟用服務 |
| `--print-python` | 印出偵測到的直譯器後結束 |

每個選項都有對應的 `FREEZE_WATCH_` 環境變數，透過管線安裝時更好用：

```bash
curl -fsSL https://raw.githubusercontent.com/raybird/sys-monitor/main/install.sh |
  FREEZE_WATCH_REF=v0.2.0 bash
```

### Python 直譯器

Freeze Watch 需要發行版隨附的 GTK 4 與 dbus binding。pyenv、asdf、conda
或已啟用的 virtualenv 通常沒有這些 binding，即使它們佔用了 `PATH` 上的
`python3` 也一樣。因此安裝器會逐一探測候選直譯器，把可用的那個記錄在
`~/.config/freeze-watch/env`，儀表板再從那裡讀取。要自己指定就用
`--python /path/to/python3`。

## 移除

安裝器會留一份解除安裝腳本，不需要 checkout 也不需要連網：

```bash
~/.local/share/freeze-watch/uninstall.sh
```

加上 `--purge-data` 會連設定與歷史一起刪除。這支腳本本身不依賴原始碼，
從 checkout 執行或用管線都可以：

```bash
curl -fsSL https://raw.githubusercontent.com/raybird/sys-monitor/main/uninstall.sh | bash
```

## 紀錄位置

```text
~/.local/state/freeze-monitor/
```

詳細說明請參考 [架構](docs/architecture.md) 與
[疑難排解](docs/troubleshooting.md)。
