#!/usr/bin/env bash

set -euo pipefail

readonly user_home="${HOME:?HOME is required}"
readonly bin_dir="${user_home}/.local/bin"
readonly data_home="${XDG_DATA_HOME:-${user_home}/.local/share}"
readonly data_dir="${data_home}/freeze-watch"
readonly applications_dir="${data_home}/applications"
readonly icon_theme_dir="${data_home}/icons/hicolor"
readonly config_home="${XDG_CONFIG_HOME:-${user_home}/.config}"
readonly unit_dir="${config_home}/systemd/user"
readonly app_config_dir="${config_home}/freeze-watch"
readonly state_dir="${XDG_STATE_HOME:-${user_home}/.local/state}/freeze-monitor"

purge_data=0
no_stop=0

usage() {
    cat <<'EOF'
Usage: ./uninstall.sh [options]

Options:
  --purge-data  Also remove configuration and all collected history.
  --no-stop     Remove files without contacting the user systemd manager.
  -h, --help    Show this help.
EOF
}

while (($# > 0)); do
    case "$1" in
        --purge-data)
            purge_data=1
            shift
            ;;
        --no-stop)
            no_stop=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            printf 'freeze-watch: unknown option: %s\n' "$1" >&2
            exit 1
            ;;
    esac
done

if ((no_stop == 0)); then
    systemctl --user disable --now freeze-watch.service 2>/dev/null || true
    systemctl --user disable --now freeze-monitor.service 2>/dev/null || true
    systemctl --user disable --now freeze-monitor-maintain.timer 2>/dev/null || true
fi

rm -f -- \
    "${bin_dir}/freeze-monitor" \
    "${bin_dir}/freeze-monitor-maintain" \
    "${bin_dir}/freeze-watch" \
    "${data_dir}/freeze_watch.py" \
    "${applications_dir}/com.raybird.FreezeWatch.desktop" \
    "${icon_theme_dir}/scalable/apps/com.raybird.FreezeWatch.svg" \
    "${icon_theme_dir}/symbolic/apps/com.raybird.FreezeWatch-symbolic.svg" \
    "${icon_theme_dir}/symbolic/apps/com.raybird.FreezeWatch-warning-symbolic.svg" \
    "${unit_dir}/freeze-watch.service" \
    "${unit_dir}/freeze-monitor.service" \
    "${unit_dir}/freeze-monitor-maintain.service" \
    "${unit_dir}/freeze-monitor-maintain.timer"
rmdir --ignore-fail-on-non-empty "${data_dir}" 2>/dev/null || true

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${applications_dir}" >/dev/null 2>&1 || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "${icon_theme_dir}" >/dev/null 2>&1 || true
fi

if ((purge_data == 1)); then
    case "${state_dir}" in
        "${user_home}"/*)
            if [[ -d "${state_dir}" ]]; then
                find "${state_dir}" -mindepth 1 -delete
                rmdir "${state_dir}"
            fi
            ;;
        *)
            printf 'Refusing to purge unexpected state path: %s\n' "${state_dir}" >&2
            exit 1
            ;;
    esac
    rm -f -- "${app_config_dir}/env"
    rmdir --ignore-fail-on-non-empty "${app_config_dir}" 2>/dev/null || true
fi

if ((no_stop == 0)); then
    systemctl --user daemon-reload
fi

if ((purge_data == 1)); then
    printf 'Freeze Watch removed, including configuration and collected history.\n'
else
    printf 'Freeze Watch removed. Collected history and configuration were preserved.\n'
fi
