# Freeze Watch

Freeze Watch 是一套輕量 Linux 凍結診斷工具，包含背景採樣器、Docker
程序觀測、GTK4 儀表板，以及顯示即時 CPU 溫度的系統列圖示。

它的用途是保留「系統完全凍結、鍵盤滑鼠失效、只能強制重開」之前的證據。

## 功能

- CPU、GPU、NVMe 溫度，支援 AMD、Intel 與 ARM 平台
- 負載、記憶體、swap、磁碟與 Linux PSI 壓力（含 full 與不可中斷睡眠程序數）
- GPU busy、CPU 與記憶體最活躍程序
- CPU 熱節流、swap 進出、major fault 與磁碟佇列
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

## GPU 程序紀錄與診斷報告

截至 2026-10-05，GPU 程序紀錄預設關閉。在 `~/.config/freeze-watch/env`
設定 `FREEZE_WATCH_GPU_PROCESSES=1` 後執行
`systemctl --user restart freeze-monitor.service` 即可啟用；升級會保留設定。
支援 Linux DRM fdinfo（例如 AMD／Intel），其他驅動或無權限時會明確顯示
限制。裝置持有者與實際引擎活動分開，首次取樣或缺計數器時活動未知。
截至 2026-11-04，只檢查本人的程序，受保護的程序（例如瀏覽器沙箱）另列數量；
啟用後 metrics 檔每日約增加 5 MB（實機 34 個 GPU client）。

截至 2026-10-05，選取事件後按「預覽診斷報告」，確認後可匯出純文字檔。
範圍為事件前 30 分鐘／後 5 分鐘，預設省略路徑、程序名稱與參數，
核心訊息僅保留錯誤分類。缺資料不會被推測補齊。
非正常關機可能是斷電、強制重啟或當機，單憑缺少 STOP 無法確認原因。

最後驗證日期：2026-11-04（GPU 程序紀錄）。

## 紀錄位置

```text
~/.local/state/freeze-monitor/
```

詳細說明請參考 [架構](docs/architecture.md) 與
[疑難排解](docs/troubleshooting.md)。

## 容器內部狀況

同時深度監控兩個專案，沿用既有設定選項：

```bash
./install.sh --compose-project runwukong,runtelenexus
```

展開容器可查看 CPU、記憶體／上限、tasks／程序、OOM、重啟、health、
累計 block I/O bytes 與每秒速率，以及最多 15 個高 CPU／記憶體／D-state 程序。
選定專案已退出的容器仍保留 OOM／重啟與狀態，停止後的即時負載顯示未知。
使用詳情內的時間選單，可查看已存樣本與此前 45 秒內的主機溫度、I/O／RAM PSI；
事故回顧同樣使用落盤資料。選擇與展開狀態會跨即時更新保留。

未知、逾時、過期與資料缺口會標明；首次採樣、容器重建／重啟、計數器重置
不會顯示假速率。警示條件為 OOM、不健康、重啟、D 或 Z 大於 0；歷史重啟次數
不代表剛發生重啟，高負載與事故重疊也不代表因果。

採樣使用目前 Docker context／DOCKER_HOST 的本機 Unix socket，不需進入容器、
安裝 agent 或額外提權。遠端 TCP／SSH daemon 不支援主機程序歸因，會顯示不可用。
Block I/O 不包含所有快取命中的檔案讀取；核心未提供計數器時顯示未知。
