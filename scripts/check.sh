#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly repo_dir
test_root=""

cleanup() {
    if [[ -n "${test_root}" && -d "${test_root}" ]]; then
        find "${test_root}" -mindepth 1 -delete
        rmdir "${test_root}"
    fi
}
trap cleanup EXIT

readonly shell_sources=(
    "${repo_dir}/install.sh"
    "${repo_dir}/uninstall.sh"
    "${repo_dir}/scripts/check.sh"
    "${repo_dir}/src/freeze-monitor"
    "${repo_dir}/src/freeze-monitor-maintain"
    "${repo_dir}/src/freeze-watch"
)

bash -n "${shell_sources[@]}"

# The installer owns interpreter selection, so the suite tests what it picks
# rather than whatever python3 the calling shell happens to resolve.
python_bin="$("${repo_dir}/install.sh" --print-python)"
readonly python_bin
printf 'Using interpreter: %s\n' "${python_bin}"

"${python_bin}" -m py_compile "${repo_dir}/src/freeze_watch.py"
"${python_bin}" - <<PY
from pathlib import Path
from xml.etree import ElementTree

for icon in Path("${repo_dir}/assets/icons").rglob("*.svg"):
    ElementTree.parse(icon)
PY
"${python_bin}" -m unittest discover -s "${repo_dir}/tests" -v

if command -v shellcheck >/dev/null 2>&1; then
    shellcheck "${shell_sources[@]}"
fi

test_root="$(mktemp -d)"
mkdir -p "${test_root}/home"

readonly test_home="${test_root}/home"
readonly test_env="${test_home}/.config/freeze-watch/env"
readonly installed_python_line="FREEZE_WATCH_PYTHON=${python_bin}"

run_installer() {
    HOME="${test_home}" \
    XDG_DATA_HOME="${test_home}/.local/share" \
    XDG_CONFIG_HOME="${test_home}/.config" \
    XDG_STATE_HOME="${test_home}/.local/state" \
        "${repo_dir}/install.sh" "$@"
}

run_installer --no-start --compose-project example

test -x "${test_home}/.local/bin/freeze-monitor"
test -x "${test_home}/.local/bin/freeze-watch"
test -x "${test_home}/.local/share/freeze-watch/uninstall.sh"
test -f "${test_home}/.config/systemd/user/freeze-watch.service"
test -f "${test_home}/.local/share/applications/com.raybird.FreezeWatch.desktop"
test -f "${test_home}/.local/share/icons/hicolor/scalable/apps/com.raybird.FreezeWatch.svg"
test -f "${test_home}/.local/share/icons/hicolor/symbolic/apps/com.raybird.FreezeWatch-symbolic.svg"
test -f "${test_home}/.local/share/icons/hicolor/symbolic/apps/com.raybird.FreezeWatch-warning-symbolic.svg"
grep -qxF "FREEZE_WATCH_COMPOSE_PROJECT=example" "${test_env}"
grep -qxF "${installed_python_line}" "${test_env}"
test "$(stat -c '%a' "${test_env}")" = "600"

# The units expand %h to the caller's home, so they can only be verified
# against a home that has the programs installed.
if command -v systemd-analyze >/dev/null 2>&1; then
    HOME="${test_home}" \
    XDG_CONFIG_HOME="${test_home}/.config" \
        systemd-analyze --user verify \
            "${test_home}"/.config/systemd/user/*.service \
            "${test_home}"/.config/systemd/user/*.timer
fi

# Installing from an extracted tree is the path a curl bootstrap takes once the
# archive is unpacked, and rerunning must not discard the recorded project.
run_installer --no-start --source "${repo_dir}"
grep -qxF "FREEZE_WATCH_COMPOSE_PROJECT=example" "${test_env}"
grep -qxF "${installed_python_line}" "${test_env}"

run_installer --no-start --compose-project other
grep -qxF "FREEZE_WATCH_COMPOSE_PROJECT=other" "${test_env}"

# The launcher must take its interpreter from the recorded configuration, not
# from whatever python3 the caller's PATH resolves to.
stub_python="${test_home}/stub-python"
cat > "${stub_python}" <<'STUB'
#!/usr/bin/env bash
printf 'stub %s\n' "$1"
STUB
chmod 0755 "${stub_python}"
printf 'FREEZE_WATCH_PYTHON=%s\n' "${stub_python}" > "${test_env}"

launcher_output="$(
    HOME="${test_home}" \
    XDG_DATA_HOME="${test_home}/.local/share" \
    XDG_CONFIG_HOME="${test_home}/.config" \
    FREEZE_WATCH_PYTHON='' \
        "${test_home}/.local/bin/freeze-watch"
)"
test "${launcher_output}" = \
    "stub ${test_home}/.local/share/freeze-watch/freeze_watch.py"

HOME="${test_home}" \
XDG_STATE_HOME="${test_home}/.local/state" \
FREEZE_WATCH_COMPOSE_PROJECT="" \
FREEZE_WATCH_MAX_SAMPLES=1 \
    "${test_home}/.local/bin/freeze-monitor"

test -n "$(find "${test_home}/.local/state/freeze-monitor" \
    -maxdepth 1 -name 'metrics-*.tsv' -print -quit)"

HOME="${test_home}" \
XDG_DATA_HOME="${test_home}/.local/share" \
XDG_CONFIG_HOME="${test_home}/.config" \
XDG_STATE_HOME="${test_home}/.local/state" \
    "${repo_dir}/uninstall.sh" --no-stop --purge-data

test ! -e "${test_home}/.local/bin/freeze-watch"
test ! -e "${test_home}/.local/share/freeze-watch/uninstall.sh"
test ! -e "${test_home}/.local/share/applications/com.raybird.FreezeWatch.desktop"
test ! -e "${test_home}/.local/share/icons/hicolor/scalable/apps/com.raybird.FreezeWatch.svg"
test ! -e "${test_home}/.local/share/icons/hicolor/symbolic/apps/com.raybird.FreezeWatch-symbolic.svg"
test ! -e "${test_home}/.local/share/icons/hicolor/symbolic/apps/com.raybird.FreezeWatch-warning-symbolic.svg"
test ! -e "${test_env}"
printf 'All checks passed.\n'
