#!/usr/bin/env bash

set -euo pipefail

readonly repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
test_root=""

cleanup() {
    if [[ -n "${test_root}" && -d "${test_root}" ]]; then
        find "${test_root}" -mindepth 1 -delete
        rmdir "${test_root}"
    fi
}
trap cleanup EXIT

bash -n \
    "${repo_dir}/install.sh" \
    "${repo_dir}/uninstall.sh" \
    "${repo_dir}/src/freeze-monitor" \
    "${repo_dir}/src/freeze-monitor-maintain" \
    "${repo_dir}/src/freeze-watch"

python3 -m py_compile "${repo_dir}/src/freeze_watch.py"
python3 - <<PY
from pathlib import Path
from xml.etree import ElementTree

for icon in Path("${repo_dir}/assets/icons").rglob("*.svg"):
    ElementTree.parse(icon)
PY
python3 -m unittest discover -s "${repo_dir}/tests" -v

if command -v shellcheck >/dev/null 2>&1; then
    shellcheck \
        "${repo_dir}/install.sh" \
        "${repo_dir}/uninstall.sh" \
        "${repo_dir}/src/freeze-monitor" \
        "${repo_dir}/src/freeze-monitor-maintain" \
        "${repo_dir}/src/freeze-watch"
fi

if command -v systemd-analyze >/dev/null 2>&1; then
    systemd-analyze --user verify "${repo_dir}"/systemd/user/*
fi

test_root="$(mktemp -d)"
mkdir -p "${test_root}/home"
HOME="${test_root}/home" \
XDG_DATA_HOME="${test_root}/home/.local/share" \
XDG_CONFIG_HOME="${test_root}/home/.config" \
XDG_STATE_HOME="${test_root}/home/.local/state" \
    "${repo_dir}/install.sh" --no-start --compose-project example

test -x "${test_root}/home/.local/bin/freeze-monitor"
test -x "${test_root}/home/.local/bin/freeze-watch"
test -f "${test_root}/home/.config/systemd/user/freeze-watch.service"
test -f "${test_root}/home/.local/share/applications/com.raybird.FreezeWatch.desktop"
test -f "${test_root}/home/.local/share/icons/hicolor/scalable/apps/com.raybird.FreezeWatch.svg"
test -f "${test_root}/home/.local/share/icons/hicolor/symbolic/apps/com.raybird.FreezeWatch-symbolic.svg"
test -f "${test_root}/home/.local/share/icons/hicolor/symbolic/apps/com.raybird.FreezeWatch-warning-symbolic.svg"
test "$(< "${test_root}/home/.config/freeze-watch/env")" = \
    "FREEZE_WATCH_COMPOSE_PROJECT=example"

HOME="${test_root}/home" \
XDG_STATE_HOME="${test_root}/home/.local/state" \
FREEZE_WATCH_COMPOSE_PROJECT="" \
FREEZE_WATCH_MAX_SAMPLES=1 \
    "${test_root}/home/.local/bin/freeze-monitor"

test -n "$(find "${test_root}/home/.local/state/freeze-monitor" \
    -maxdepth 1 -name 'metrics-*.tsv' -print -quit)"

HOME="${test_root}/home" \
XDG_DATA_HOME="${test_root}/home/.local/share" \
XDG_CONFIG_HOME="${test_root}/home/.config" \
XDG_STATE_HOME="${test_root}/home/.local/state" \
    "${repo_dir}/uninstall.sh" --no-stop --purge-data

test ! -e "${test_root}/home/.local/bin/freeze-watch"
test ! -e "${test_root}/home/.local/share/applications/com.raybird.FreezeWatch.desktop"
test ! -e "${test_root}/home/.local/share/icons/hicolor/scalable/apps/com.raybird.FreezeWatch.svg"
test ! -e "${test_root}/home/.local/share/icons/hicolor/symbolic/apps/com.raybird.FreezeWatch-symbolic.svg"
test ! -e "${test_root}/home/.local/share/icons/hicolor/symbolic/apps/com.raybird.FreezeWatch-warning-symbolic.svg"
printf 'All checks passed.\n'
