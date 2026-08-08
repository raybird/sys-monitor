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
    "${repo_dir}/src/freeze-watch-session"
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
test -x "${test_home}/.local/bin/freeze-watch-session"
test -x "${test_home}/.local/share/freeze-watch/uninstall.sh"
test -f "${test_home}/.config/systemd/user/freeze-watch.service"
test -f "${test_home}/.local/share/applications/com.raybird.FreezeWatch.desktop"
test -f "${test_home}/.local/share/icons/hicolor/scalable/apps/com.raybird.FreezeWatch.svg"
test -f "${test_home}/.local/share/icons/hicolor/symbolic/apps/com.raybird.FreezeWatch-symbolic.svg"
test -f "${test_home}/.local/share/icons/hicolor/symbolic/apps/com.raybird.FreezeWatch-warning-symbolic.svg"
grep -qxF "FREEZE_WATCH_COMPOSE_PROJECT=example" "${test_env}"
grep -qxF "${installed_python_line}" "${test_env}"
test "$(stat -c '%a' "${test_env}")" = "600"

# A desktop entry cannot express a home-relative program, so the autostart
# entry has to carry an absolute one.
readonly test_autostart="${test_home}/.config/autostart/com.raybird.FreezeWatch-autostart.desktop"
test -f "${test_autostart}"
grep -qxF "Exec=${test_home}/.local/bin/freeze-watch-session" "${test_autostart}"
if grep -q '@BIN_DIR@' "${test_autostart}"; then
    printf 'autostart entry still carries the @BIN_DIR@ placeholder\n' >&2
    exit 1
fi

if command -v desktop-file-validate >/dev/null 2>&1; then
    desktop-file-validate \
        "${test_autostart}" \
        "${test_home}/.local/share/applications/com.raybird.FreezeWatch.desktop"
fi

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

# An upgrade has to restart whatever is already running, otherwise the previous
# program keeps executing until the next reboot. A stub stands in for systemctl
# so the behaviour can be asserted without touching the real user instance.
stub_systemctl="${test_home}/stub-systemctl"
cat > "${stub_systemctl}" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "${FREEZE_WATCH_SYSTEMCTL_LOG}"
if [[ "$*" == *"is-active --quiet "* ]]; then
    # Pattern removal on $* applies per positional parameter, so the joined
    # string has to be materialised before the last word can be taken.
    arguments="$*"
    unit="${arguments##* }"
    case " ${FREEZE_WATCH_STUB_ACTIVE:-} " in
        *" ${unit} "*) exit 0 ;;
        *) exit 3 ;;
    esac
fi
exit 0
STUB
chmod 0755 "${stub_systemctl}"

install_with_stub() {
    local log="$1"
    local active="$2"

    : > "${log}"
    HOME="${test_home}" \
    XDG_DATA_HOME="${test_home}/.local/share" \
    XDG_CONFIG_HOME="${test_home}/.config" \
    XDG_STATE_HOME="${test_home}/.local/state" \
    FREEZE_WATCH_SYSTEMCTL="${stub_systemctl}" \
    FREEZE_WATCH_SYSTEMCTL_LOG="${log}" \
    FREEZE_WATCH_STUB_ACTIVE="${active}" \
        "${repo_dir}/install.sh" > /dev/null
}

readonly upgrade_log="${test_root}/systemctl-upgrade.log"
install_with_stub "${upgrade_log}" \
    "freeze-monitor.service freeze-monitor-maintain.timer freeze-watch.service"
grep -qxF -- '--user restart freeze-monitor.service' "${upgrade_log}"
grep -qxF -- '--user restart freeze-monitor-maintain.timer' "${upgrade_log}"
grep -qxF -- '--user restart freeze-watch.service' "${upgrade_log}"

# A session that never activates graphical-session.target still has to see the
# tray restarted when it is already running, which is the case that regressed.
readonly headless_log="${test_root}/systemctl-headless.log"
install_with_stub "${headless_log}" "freeze-watch.service"
grep -qxF -- '--user start freeze-monitor.service' "${headless_log}"
grep -qxF -- '--user restart freeze-watch.service' "${headless_log}"

readonly fresh_log="${test_root}/systemctl-fresh.log"
install_with_stub "${fresh_log}" ""
grep -qxF -- '--user start freeze-monitor.service' "${fresh_log}"
grep -qxF -- '--user enable freeze-watch.service' "${fresh_log}"
if grep -qE -- '--user (start|restart) freeze-watch.service' "${fresh_log}"; then
    printf 'the tray was started without a graphical session\n' >&2
    exit 1
fi

HOME="${test_home}" \
XDG_STATE_HOME="${test_home}/.local/state" \
FREEZE_WATCH_COMPOSE_PROJECT="" \
FREEZE_WATCH_MAX_SAMPLES=1 \
    "${test_home}/.local/bin/freeze-monitor"

test -n "$(find "${test_home}/.local/state/freeze-monitor" \
    -maxdepth 1 -name 'metrics-*.tsv' -print -quit)"

# Temperature sources are matched by preference, not by the order the kernel
# numbered the devices in, and a machine with only an Intel package sensor has
# to report a CPU temperature rather than NA.
fake_hwmon() {
    local root="$1"
    shift
    local index=0 entry name value

    for entry in "$@"; do
        name="${entry%%:*}"
        value="${entry##*:}"
        mkdir -p "${root}/hwmon${index}"
        printf '%s\n' "${name}" > "${root}/hwmon${index}/name"
        printf '%s\n' "${value}" > "${root}/hwmon${index}/temp1_input"
        index=$((index + 1))
    done
}

cpu_temp_for() {
    local root="$1"
    local state="$2"
    shift 2

    fake_hwmon "${root}" "$@"
    HOME="${test_home}" \
    XDG_STATE_HOME="${state}" \
    FREEZE_WATCH_COMPOSE_PROJECT="" \
    FREEZE_WATCH_MAX_SAMPLES=1 \
    FREEZE_WATCH_HWMON_ROOT="${root}" \
        "${test_home}/.local/bin/freeze-monitor"

    awk -F'\t' 'NR == 2 { print $10 }' \
        "$(find "${state}/freeze-monitor" -maxdepth 1 -name 'metrics-*.tsv' -print -quit)"
}

test "$(cpu_temp_for "${test_root}/hwmon-intel" "${test_root}/state-intel" \
    acpitz:27800 nvme:43850 coretemp:49000)" = "49000"

test "$(cpu_temp_for "${test_root}/hwmon-order" "${test_root}/state-order" \
    coretemp:49000 k10temp:61000)" = "61000"

test "$(cpu_temp_for "${test_root}/hwmon-none" "${test_root}/state-none" \
    acpitz:27800)" = "NA"

HOME="${test_home}" \
XDG_DATA_HOME="${test_home}/.local/share" \
XDG_CONFIG_HOME="${test_home}/.config" \
XDG_STATE_HOME="${test_home}/.local/state" \
    "${repo_dir}/uninstall.sh" --no-stop --purge-data

test ! -e "${test_home}/.local/bin/freeze-watch"
test ! -e "${test_home}/.local/bin/freeze-watch-session"
test ! -e "${test_autostart}"
test ! -e "${test_home}/.local/share/freeze-watch/uninstall.sh"
test ! -e "${test_home}/.local/share/applications/com.raybird.FreezeWatch.desktop"
test ! -e "${test_home}/.local/share/icons/hicolor/scalable/apps/com.raybird.FreezeWatch.svg"
test ! -e "${test_home}/.local/share/icons/hicolor/symbolic/apps/com.raybird.FreezeWatch-symbolic.svg"
test ! -e "${test_home}/.local/share/icons/hicolor/symbolic/apps/com.raybird.FreezeWatch-warning-symbolic.svg"
test ! -e "${test_env}"
printf 'All checks passed.\n'
