# Troubleshooting

## The installer reports missing GTK dependencies

The bindings are distribution packages, so an interpreter from pyenv, asdf,
conda, or an activated virtualenv usually cannot see them even when the
packages are installed. Compare the two:

```bash
python3 -c 'import dbus, gi'
/usr/bin/python3 -c 'import dbus, gi'
```

If only the second succeeds, the installer will normally pick it on its own.
Ask it which interpreter it resolved, or name one explicitly:

```bash
./install.sh --print-python
./install.sh --python /usr/bin/python3
```

The answer is recorded as `FREEZE_WATCH_PYTHON` in
`~/.config/freeze-watch/env`, and both the systemd units and the `freeze-watch`
launcher read it from there. Editing that line is enough to move an existing
installation to a different interpreter.

## The events log says the kernel log is unavailable

Reading kernel messages needs group membership:

```bash
id -nG | tr ' ' '\n' | grep -E 'adm|systemd-journal'
sudo usermod -aG adm "$USER"
```

Log out and back in afterwards. Everything else keeps working without it; only
`KERNEL` events are lost.

Kernel messages also have to survive the reboot that follows a freeze. Check
that the journal is persistent rather than in-memory:

```bash
test -d /var/log/journal && echo persistent || echo volatile
```

If it reports `volatile`, create the directory and restart journald, otherwise
every forced reboot discards the evidence:

```bash
sudo mkdir -p /var/log/journal
sudo systemctl restart systemd-journald
```

## The tray icon is missing

Confirm the service is running:

```bash
systemctl --user status freeze-watch.service
journalctl --user-unit=freeze-watch.service -n 100 --no-pager
```

GNOME requires a StatusNotifier/AppIndicator extension. Ubuntu enables one by
default. On other GNOME installations, install and enable
`gnome-shell-extension-appindicator`.

## The dashboard has no temperature values

Check available hardware-monitor devices:

```bash
for device in /sys/class/hwmon/hwmon*; do
  printf '%s: ' "$device"
  cat "$device/name"
done
```

The CPU temperature comes from the first of `k10temp`, `coretemp`, `zenpower`,
`k8temp`, or `cpu_thermal` that is present, the GPU temperature from `amdgpu`,
`radeon`, or `nouveau`, and the drive temperature from `nvme`. A generic
`acpitz` device is deliberately ignored, because it usually reports a board or
ambient sensor and a wrong CPU temperature is worse than none when the log is
read back to explain a freeze.

Integrated Intel graphics report neither a hwmon temperature nor
`gpu_busy_percent`, so `gpu_temp_mC` and `gpu_busy_pct` stay `NA` on those
machines. The CPU package sensor covers the same silicon. Unsupported hardware
still receives load, memory, pressure, filesystem, and Docker data.

## The tray icon never appears after logging in

Some sessions never activate `graphical-session.target`, which is what would
normally pull in the tray service. Chrome Remote Desktop and several
lightweight session managers start the desktop outside the systemd user
hierarchy. Check with:

```bash
systemctl --user is-active graphical-session.target
```

If that prints `inactive`, the XDG autostart entry installed at
`~/.config/autostart/com.raybird.FreezeWatch-autostart.desktop` takes over at
the next login. To start the tray in the current session without logging out:

```bash
systemctl --user start freeze-watch.service
```

## Docker shows unavailable

Docker is optional. The dashboard and the metrics `docker_state` column name
the reason (checked 2026-11-06):

| State | Meaning | What to do |
|---|---|---|
| `unavailable:permission` | The Docker socket exists but this user may not open it | Grant access to the socket (see the warning below) |
| `unavailable:no_socket` | No socket at the Docker context's or `DOCKER_HOST`'s path | Check that Docker is installed and which context is selected |
| `unavailable:no_daemon` | The socket exists but nothing answers | Start the Docker daemon |
| `unavailable:nonlocal` | The context or `DOCKER_HOST` is TCP or SSH | Not supported on purpose: host PIDs and RAM would describe another machine. Select a local context |
| `unavailable:timeout` | Docker did not answer within the 6 s helper budget, or the 8 s outer limit stopped the helper | Usually a busy daemon; check `docker ps` response time |
| `unavailable:helper_failed` | The sampling helper exited with an error | Run the helper by hand (below) to see the traceback |
| `unavailable:error` | Another query error, such as an unexpected API reply | The helper reports no detail for these, so running it by hand only prints `unavailable:error` again. Check the endpoint and socket with the commands below and `docker version` |

To run the helper by hand with the interpreter and install location the
collector uses (`FREEZE_WATCH_PYTHON` read from the installer's env file,
falling back to `/usr/bin/python3` as the collector does; data under
`XDG_DATA_HOME`):

```bash
py="$(sed -n 's/^FREEZE_WATCH_PYTHON=//p' "${XDG_CONFIG_HOME:-$HOME/.config}/freeze-watch/env" 2>/dev/null | tail -1)"
"${py:-/usr/bin/python3}" \
  "${XDG_DATA_HOME:-$HOME/.local/share}/freeze-watch/container_probe.py" \
  now 0 "" "$(mktemp -d)"
```

`docker ps` succeeding is not enough on its own: with a remote context it works
while Freeze Watch reports `unavailable:nonlocal`. A local check is:

```bash
docker context inspect --format '{{.Endpoints.docker.Host}}'
ls -l /var/run/docker.sock   # or the unix:// path printed above
docker ps
```

Do not add a user to the Docker group without understanding that it grants
root-equivalent control of the host.

## 診斷限制與 GPU 活動

截至 2026-10-05，`UNCLEAN` 與歷史 `FREEZE` 只表示非正常關機／疑似當機。
應比對最後取樣、壓力、溫度與核心訊息，不把缺 STOP 當成已確認的 GPU 故障。
同 session 的跨日輪替會追蹤最新有效檔；缺失或空檔回退，全部不可用時顯示 unknown。

截至 2026-11-04，GPU 程序紀錄必須以 `FREEZE_WATCH_GPU_PROCESSES=1` 啟用。
權限不足、不支援 DRM 計數器與採樣上限都會顯示限制；「活動未知」與「0%」
意義不同。只檢查本人的程序；瀏覽器沙箱這類受保護的程序無法檢查，會另外列出
數量，不算資料不完整。「持有裝置、取樣期間無活動」列出的是有開 GPU 但沒在用的程式。預設不要求 root，也不會變更使用者群組。報告預覽只列安全的
數值與錯誤分類；需要完整原始核心訊息時，在本機檢查 events.log。

最後驗證日期：2026-11-04（GPU 活動判讀）。

## Logs

```bash
journalctl --user-unit=freeze-monitor.service -n 100 --no-pager
journalctl --user-unit=freeze-watch.service -n 100 --no-pager
tail -50 ~/.local/state/freeze-monitor/events.log
```
