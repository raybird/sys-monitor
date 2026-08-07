#!/usr/bin/env bash

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly user_home="${HOME:?HOME is required}"
readonly bin_dir="${user_home}/.local/bin"
readonly data_home="${XDG_DATA_HOME:-${user_home}/.local/share}"
readonly data_dir="${data_home}/freeze-watch"
readonly applications_dir="${data_home}/applications"
readonly config_home="${XDG_CONFIG_HOME:-${user_home}/.config}"
readonly unit_dir="${config_home}/systemd/user"
readonly app_config_dir="${config_home}/freeze-watch"

compose_project=""
compose_project_was_set=0
no_start=0

usage() {
    cat <<'EOF'
Usage: ./install.sh [options]

Options:
  --compose-project NAME  Deep-monitor one Docker Compose project.
  --no-start              Install files without enabling or starting services.
  -h, --help              Show this help.
EOF
}

fail() {
    printf 'freeze-watch: %s\n' "$*" >&2
    exit 1
}

while (($# > 0)); do
    case "$1" in
        --compose-project)
            (($# >= 2)) || fail "--compose-project requires a value"
            compose_project="$2"
            compose_project_was_set=1
            shift 2
            ;;
        --no-start)
            no_start=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            fail "unknown option: $1"
            ;;
    esac
done

if [[ -n "${compose_project}" ]] &&
   [[ ! "${compose_project}" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
    fail "Compose project must match [A-Za-z0-9][A-Za-z0-9_.-]*"
fi

for command_name in bash awk df flock gzip install ps sync systemctl timeout; do
    command -v "${command_name}" >/dev/null 2>&1 ||
        fail "missing required command: ${command_name}"
done

if ! python3 -c "
import dbus
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gdk, Gio, GLib, Gtk
" >/dev/null 2>&1; then
    cat >&2 <<'EOF'
Missing Python GTK dependencies.

Ubuntu/Debian:
  sudo apt install python3 python3-gi python3-dbus gir1.2-gtk-4.0

Fedora:
  sudo dnf install python3 python3-gobject gtk4 python3-dbus
EOF
    exit 1
fi

if ((no_start == 0)); then
    systemctl --user show-environment >/dev/null 2>&1 ||
        fail "systemd user session is unavailable; retry with --no-start"
fi

install -d -m 0755 \
    "${bin_dir}" "${data_dir}" "${applications_dir}" "${unit_dir}" "${app_config_dir}"
install -m 0755 "${script_dir}/src/freeze-monitor" "${bin_dir}/freeze-monitor"
install -m 0755 "${script_dir}/src/freeze-monitor-maintain" "${bin_dir}/freeze-monitor-maintain"
install -m 0755 "${script_dir}/src/freeze-watch" "${bin_dir}/freeze-watch"
install -m 0755 "${script_dir}/src/freeze_watch.py" "${data_dir}/freeze_watch.py"
install -m 0644 \
    "${script_dir}/packaging/com.raybird.FreezeWatch.desktop" \
    "${applications_dir}/com.raybird.FreezeWatch.desktop"
install -m 0644 "${script_dir}"/systemd/user/*.service "${unit_dir}/"
install -m 0644 "${script_dir}"/systemd/user/*.timer "${unit_dir}/"

if ((compose_project_was_set == 1)) || [[ ! -e "${app_config_dir}/env" ]]; then
    printf 'FREEZE_WATCH_COMPOSE_PROJECT=%s\n' "${compose_project}" \
        > "${app_config_dir}/env"
    chmod 0600 "${app_config_dir}/env"
fi

if ((no_start == 0)); then
    systemctl --user daemon-reload
    systemctl --user enable --now freeze-monitor.service
    systemctl --user enable --now freeze-monitor-maintain.timer
    systemctl --user enable freeze-watch.service

    if systemctl --user is-active --quiet graphical-session.target; then
        systemctl --user restart freeze-watch.service
    else
        printf 'Freeze Watch GUI will start with the next graphical session.\n'
    fi
fi

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${applications_dir}" >/dev/null 2>&1 || true
fi

cat <<EOF
Freeze Watch installed.

Collector: ${bin_dir}/freeze-monitor
Dashboard: ${bin_dir}/freeze-watch
State:     ${XDG_STATE_HOME:-${user_home}/.local/state}/freeze-monitor
Config:    ${app_config_dir}/env
EOF
