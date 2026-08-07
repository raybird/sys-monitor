# Freeze Watch

Freeze Watch 是一套輕量 Linux 凍結診斷工具，包含背景採樣器、Docker
程序觀測、GTK4 儀表板，以及顯示即時 CPU 溫度的系統列圖示。

它的用途是保留「系統完全凍結、鍵盤滑鼠失效、只能強制重開」之前的證據。

## 功能

- CPU、GPU、NVMe 溫度
- 負載、記憶體、swap、磁碟與 Linux PSI 壓力
- GPU busy 與最活躍程序
- Docker CPU、記憶體、tasks、OOM、重啟與 zombie
- 可指定一個 Docker Compose project 做深度程序觀測
- 系統列即時顯示 `CPU 58°`
- GTK4 儀表板與最近 30 分鐘熱度帶
- 每日換檔、14 天後壓縮、90 天後刪除
- 全部以使用者身分執行，不需要 root daemon

## Ubuntu 24.04 相依套件

```bash
sudo apt install python3 python3-gi python3-dbus gir1.2-gtk-4.0
```

## 安裝

```bash
git clone https://github.com/raybird/sys-monitor.git
cd sys-monitor
./install.sh --compose-project runtelenexus
```

若不需要指定 Compose project：

```bash
./install.sh
```

安裝器可以重複執行，不會刪除既有監測資料。
安裝後也能從桌面應用程式清單搜尋「Freeze Watch 系統監測」開啟。

## 移除

保留設定與歷史：

```bash
./uninstall.sh
```

連同設定與歷史一起刪除：

```bash
./uninstall.sh --purge-data
```

## 紀錄位置

```text
~/.local/state/freeze-monitor/
```

詳細說明請參考 [架構](docs/architecture.md) 與
[疑難排解](docs/troubleshooting.md)。
