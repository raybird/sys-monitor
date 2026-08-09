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
# Widget measurements need a display, and GTK 4 segfaults without one, so a
# virtual server is used when the suite runs headless. The tests that need it
# skip themselves when neither is available.
if [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]] || ! command -v xvfb-run >/dev/null 2>&1; then
    "${python_bin}" -m unittest discover -s "${repo_dir}/tests" -v
else
    # The GL renderer cannot initialise against a virtual framebuffer.
    GSK_RENDERER=cairo \
        xvfb-run -a "${python_bin}" -m unittest discover -s "${repo_dir}/tests" -v
fi

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

# The tool was written on AMD hardware, so the widened lists have to keep
# reading it exactly as before. Both readings are checked, and the AMD sensors
# are deliberately given higher device numbers than the ones that would
# otherwise win, since preference order is what decides this rather than the
# order the kernel enumerated them in.
amd_root="${test_root}/hwmon-amd"
amd_state="${test_root}/state-amd"
fake_hwmon "${amd_root}" nvme:41850 acpitz:27800 amdgpu:58000 k10temp:62500
HOME="${test_home}" \
XDG_STATE_HOME="${amd_state}" \
FREEZE_WATCH_COMPOSE_PROJECT="" \
FREEZE_WATCH_MAX_SAMPLES=1 \
FREEZE_WATCH_HWMON_ROOT="${amd_root}" \
    "${test_home}/.local/bin/freeze-monitor"

amd_metrics="$(find "${amd_state}/freeze-monitor" \
    -maxdepth 1 -name 'metrics-*.tsv' -print -quit)"
test "$(awk -F'\t' 'NR == 2 { print $10 }' "${amd_metrics}")" = "62500"
test "$(awk -F'\t' 'NR == 2 { print $11 }' "${amd_metrics}")" = "58000"
test "$(awk -F'\t' 'NR == 2 { print $12 }' "${amd_metrics}")" = "41850"

# The dashboard keeps its own copy of the sensor lists, so it is checked
# against the same synthetic machine.
FREEZE_WATCH_HWMON_ROOT="${amd_root}" "${python_bin}" - <<PY
import importlib.util

spec = importlib.util.spec_from_file_location(
    "freeze_watch_amd", "${repo_dir}/src/freeze_watch.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

expected = {"cpu": 62.5, "gpu": 58.0, "nvme": 41.85}
actual = module.direct_temperatures()
assert actual == expected, f"AMD readings drifted: {actual} != {expected}"
PY

# A kernel without pressure accounting reports NA, which awk compares as a
# string unless forced numeric. "NA" sorts above "20.0", so every sample used
# to raise an I/O pressure warning, on every machine that lacks the feature.
mkdir -p "${test_root}/pressure-absent"
HOME="${test_home}" \
XDG_STATE_HOME="${test_root}/state-no-psi" \
FREEZE_WATCH_COMPOSE_PROJECT="" \
FREEZE_WATCH_MAX_SAMPLES=1 \
FREEZE_WATCH_PRESSURE_ROOT="${test_root}/pressure-absent" \
    "${test_home}/.local/bin/freeze-monitor"

no_psi_metrics="$(find "${test_root}/state-no-psi/freeze-monitor" \
    -maxdepth 1 -name 'metrics-*.tsv' -print -quit)"
readonly no_psi_metrics
test "$(awk -F'\t' 'NR == 2 { print $16 }' "${no_psi_metrics}")" = "NA"
test "$(awk -F'\t' 'NR == 2 { print $27 }' "${no_psi_metrics}")" = "NA"

# "some" pressure means at least one task stalled, "full" means every task did,
# which is the stronger of the two signals and used to be discarded.
live_metrics="$(find "${test_home}/.local/state/freeze-monitor" \
    -maxdepth 1 -name 'metrics-*.tsv' -print -quit)"
readonly live_metrics
head -1 "${live_metrics}" | grep -qF 'io_psi_full_avg10'
head -1 "${live_metrics}" | grep -qF 'dstate_count'
head -1 "${live_metrics}" | grep -qF 'top_memory_processes'

# Every row has to carry every column. A printf format shorter than its
# argument list silently wraps and writes a second, mangled line.
readonly metrics_columns=35
test "$(awk -F'\t' 'NR == 1 { print NF }' "${live_metrics}")" = "${metrics_columns}"
test "$(awk -F'\t' 'NR == 2 { print NF }' "${live_metrics}")" = "${metrics_columns}"
test "$(awk -F'\t' 'END { print NR }' "${live_metrics}")" = "2"

# Synthetic pressure files give "some" and "full" different values, so reading
# the wrong line cannot pass by looking numeric.
synthetic_pressure="${test_root}/pressure-synth"
mkdir -p "${synthetic_pressure}"
for kind in cpu memory io; do
    printf 'some avg10=7.77 avg60=0.00 avg300=0.00 total=1\n' \
        > "${synthetic_pressure}/${kind}"
    printf 'full avg10=3.33 avg60=0.00 avg300=0.00 total=1\n' \
        >> "${synthetic_pressure}/${kind}"
done

# A stub ps presents processes in uninterruptible sleep, which cannot be
# conjured on a healthy machine but is the signature worth counting.
stub_ps="${test_home}/stub-ps"
cat > "${stub_ps}" <<'STUB'
#!/usr/bin/env bash
if [[ "$*" == *"stat="* ]]; then
    printf 'S\nD\nSl\nD+\nDL\nR\n'
else
    printf 'stuck 0.0 0.1\n'
fi
STUB
chmod 0755 "${stub_ps}"

HOME="${test_home}" \
XDG_STATE_HOME="${test_root}/state-signals" \
FREEZE_WATCH_COMPOSE_PROJECT="" \
FREEZE_WATCH_MAX_SAMPLES=1 \
FREEZE_WATCH_PRESSURE_ROOT="${synthetic_pressure}" \
FREEZE_WATCH_PS="${stub_ps}" \
    "${test_home}/.local/bin/freeze-monitor"

signals_metrics="$(find "${test_root}/state-signals/freeze-monitor" \
    -maxdepth 1 -name 'metrics-*.tsv' -print -quit)"
readonly signals_metrics
test "$(awk -F'\t' 'NR == 2 { print $16 }' "${signals_metrics}")" = "7.77"
test "$(awk -F'\t' 'NR == 2 { print $27 }' "${signals_metrics}")" = "3.33"
# S, D, Sl, D+, DL, R: the three beginning with D are the ones that count.
test "$(awk -F'\t' 'NR == 2 { print $28 }' "${signals_metrics}")" = "3"

# Throttle counts, swap traffic, and disk queue depth are cumulative counters
# read from files, so synthetic ones pin down both the reading and the delta.
counters="${test_root}/counters"
mkdir -p "${counters}/cpu/cpu0/thermal_throttle" "${counters}/cpu/cpu1/thermal_throttle"
printf '4\n' > "${counters}/cpu/cpu0/thermal_throttle/package_throttle_count"
printf '7\n' > "${counters}/cpu/cpu1/thermal_throttle/package_throttle_count"
printf 'pswpin 500\npswpout 120\npgmajfault 9000\n' > "${counters}/vmstat"
printf '259 0 %s 1 2 3 4 5 6 7 8 9 4242 11\n' \
    "$(basename "$(readlink -f /sys/class/block/"$(basename \
        "$(df -P / | awk 'NR == 2 { print $1 }')")" 2>/dev/null)" 2>/dev/null)" \
    > "${counters}/diskstats" 2>/dev/null || true

run_counter_sample() {
    HOME="${test_home}" \
    XDG_STATE_HOME="$1" \
    FREEZE_WATCH_COMPOSE_PROJECT="" \
    FREEZE_WATCH_MAX_SAMPLES=1 \
    FREEZE_WATCH_CPU_ROOT="${counters}/cpu" \
    FREEZE_WATCH_VMSTAT="${counters}/vmstat" \
    FREEZE_WATCH_DISKSTATS="${counters}/diskstats" \
        "${test_home}/.local/bin/freeze-monitor"
}

run_counter_sample "${test_root}/state-counters"
counter_metrics="$(find "${test_root}/state-counters/freeze-monitor" \
    -maxdepth 1 -name 'metrics-*.tsv' -print -quit)"
readonly counter_metrics

# The highest package count wins, not the first one enumerated.
test "$(awk -F'\t' 'NR == 2 { print $29 }' "${counter_metrics}")" = "7"
# A first sample has nothing to subtract from, so the deltas are unknown.
test "$(awk -F'\t' 'NR == 2 { print $30 }' "${counter_metrics}")" = "NA"
test "$(awk -F'\t' 'NR == 2 { print $32 }' "${counter_metrics}")" = "NA"
test -n "$(awk -F'\t' 'NR == 2 { print $35 }' "${counter_metrics}")"

# Advance the counters and take a second sample to prove the deltas subtract.
printf 'pswpin 1700\npswpout 120\npgmajfault 9001\n' > "${counters}/vmstat"
HOME="${test_home}" \
XDG_STATE_HOME="${test_root}/state-counters-2" \
FREEZE_WATCH_COMPOSE_PROJECT="" \
FREEZE_WATCH_MAX_SAMPLES=2 \
FREEZE_WATCH_INTERVAL_SECONDS=1 \
FREEZE_WATCH_CPU_ROOT="${counters}/cpu" \
FREEZE_WATCH_VMSTAT="${counters}/vmstat" \
FREEZE_WATCH_DISKSTATS="${counters}/diskstats" \
    "${test_home}/.local/bin/freeze-monitor"
second_metrics="$(find "${test_root}/state-counters-2/freeze-monitor" \
    -maxdepth 1 -name 'metrics-*.tsv' -print -quit)"
readonly second_metrics
# Unchanged counters between two samples must read as zero, not as unknown.
test "$(awk -F'\t' 'NR == 3 { print $30 }' "${second_metrics}")" = "0"
if grep -q 'I/O pressure' "${test_root}/state-no-psi/freeze-monitor/events.log"; then
    printf 'an absent pressure file raised a spurious warning\n' >&2
    exit 1
fi

# The collector is a post-mortem tool, so a session that never wrote STOP has
# to be reported by the next one. A different boot id means the machine went
# down without shutting down; the same boot id means only the collector died.
current_boot="$(< /proc/sys/kernel/random/boot_id)"
readonly current_boot

seed_previous_session() {
    local state="$1"
    local previous_boot="$2"
    local closing_event="$3"
    local monitor_dir="${state}/freeze-monitor"
    local previous_metrics="${monitor_dir}/metrics-previous.tsv"

    mkdir -p "${monitor_dir}"
    printf 'timestamp\tepoch\tuptime_s\n' > "${previous_metrics}"
    printf '2026-08-09T10:00:00+08:00\t1786312800\t1000\n' >> "${previous_metrics}"
    printf '2026-08-09T10:00:10+08:00\t1786312810\t1010\n' >> "${previous_metrics}"

    printf '2026-08-09T09:59:00+08:00\tSTART\tboot=%s metrics=%s interval=10s flush=30s\n' \
        "${previous_boot}" "${previous_metrics}" > "${monitor_dir}/events.log"
    if [[ -n "${closing_event}" ]]; then
        printf '2026-08-09T10:00:20+08:00\t%s\tmonitor stopped\n' "${closing_event}" \
            >> "${monitor_dir}/events.log"
    fi
}

run_collector() {
    local state="$1"
    shift

    HOME="${test_home}" \
    XDG_STATE_HOME="${state}" \
    FREEZE_WATCH_COMPOSE_PROJECT="" \
    FREEZE_WATCH_MAX_SAMPLES=1 \
        env "$@" "${test_home}/.local/bin/freeze-monitor"
}

seed_previous_session "${test_root}/state-freeze" "00000000-0000-0000-0000-000000000000" ""
run_collector "${test_root}/state-freeze"
grep -q $'\tFREEZE\t' "${test_root}/state-freeze/freeze-monitor/events.log"
grep -q 'last_sample=2026-08-09T10:00:10+08:00' \
    "${test_root}/state-freeze/freeze-monitor/events.log"

seed_previous_session "${test_root}/state-interrupted" "${current_boot}" ""
run_collector "${test_root}/state-interrupted"
grep -q $'\tINTERRUPTED\t' \
    "${test_root}/state-interrupted/freeze-monitor/events.log"

seed_previous_session "${test_root}/state-clean" "00000000-0000-0000-0000-000000000000" "STOP"
run_collector "${test_root}/state-clean"
if grep -qE $'\t(FREEZE|INTERRUPTED)\t' \
    "${test_root}/state-clean/freeze-monitor/events.log"; then
    printf 'a clean shutdown was reported as a freeze\n' >&2
    exit 1
fi

# Two samples one second apart, with the stall threshold lowered to match, are
# enough to exercise the gap detector without waiting for a real stall.
HOME="${test_home}" \
XDG_STATE_HOME="${test_root}/state-gap" \
FREEZE_WATCH_COMPOSE_PROJECT="" \
FREEZE_WATCH_MAX_SAMPLES=2 \
FREEZE_WATCH_INTERVAL_SECONDS=1 \
FREEZE_WATCH_STALL_SECONDS=1 \
    "${test_home}/.local/bin/freeze-monitor"
grep -q $'\tGAP\t' "${test_root}/state-gap/freeze-monitor/events.log"

# Kernel evidence is read through journalctl so that group permissions and the
# previous boot both work. A stub stands in for it.
stub_journalctl="${test_home}/stub-journalctl"
cat > "${stub_journalctl}" <<'STUB'
#!/usr/bin/env bash
case "$*" in
    *--show-cursor*) printf -- '-- cursor: s=stub;i=1;b=stub\n'; exit 0 ;;
    *"-b -1"*) cat "${FREEZE_WATCH_STUB_PREVIOUS_BOOT:-/dev/null}"; exit 0 ;;
    *--after-cursor*) cat "${FREEZE_WATCH_STUB_KERNEL:-/dev/null}"; exit 0 ;;
esac
exit "${FREEZE_WATCH_STUB_PROBE_STATUS:-0}"
STUB
chmod 0755 "${stub_journalctl}"

# Vendor spellings differ enough that the pattern is checked against recorded
# message shapes rather than against whatever this machine happens to log. The
# ignore set guards the other direction: a pattern broad enough to catch every
# hang also catches every boot.
kernel_pattern="$(
    sed -n "s/^readonly kernel_alert_pattern='\(.*\)'$/\1/p" \
        "${repo_dir}/src/freeze-monitor"
)"
test -n "${kernel_pattern}"

kernel_corpus_failures=0
while IFS=$'\t' read -r verdict message; do
    [[ -n "${verdict}" && "${verdict}" != \#* ]] || continue
    if printf '%s\n' "${message}" | grep -qaE "${kernel_pattern}"; then
        observed="match"
    else
        observed="ignore"
    fi
    if [[ "${observed}" != "${verdict}" ]]; then
        printf 'kernel pattern: expected %s, got %s, for: %s\n' \
            "${verdict}" "${observed}" "${message}" >&2
        kernel_corpus_failures=1
    fi
done < "${repo_dir}/tests/kernel-samples.tsv"
((kernel_corpus_failures == 0)) || exit 1

# A short log for the reporting test, kept below the per-scan cap so that what
# is and is not reported depends on the pattern rather than on truncation.
cat > "${test_root}/kernel-alerts.txt" <<'LOG'
usb 1-3: new high-speed USB device number 5 using xhci_hcd
i915 0000:00:02.0: [drm] GPU HANG: ecode 12:1:85dffffb, in gnome-shell [3210]
Adding 2097148k swap on /swapfile
INFO: task kworker/2:1:184 blocked for more than 122 seconds.
LOG

awk -F'\t' '$1 == "match" { print $2 }' \
    "${repo_dir}/tests/kernel-samples.tsv" > "${test_root}/kernel-flood.txt"

run_kernel_scan() {
    local state="$1"
    shift

    HOME="${test_home}" \
    XDG_STATE_HOME="${state}" \
    FREEZE_WATCH_COMPOSE_PROJECT="" \
    FREEZE_WATCH_MAX_SAMPLES=1 \
    FREEZE_WATCH_JOURNALCTL="${stub_journalctl}" \
        env "$@" "${test_home}/.local/bin/freeze-monitor"
}

run_kernel_scan "${test_root}/state-kernel" \
    FREEZE_WATCH_STUB_KERNEL="${test_root}/kernel-alerts.txt"
readonly kernel_events="${test_root}/state-kernel/freeze-monitor/events.log"
grep -q 'GPU HANG' "${kernel_events}"
grep -q 'blocked for more than' "${kernel_events}"

# Ordinary boot chatter must not be promoted to an incident.
if grep -qE 'new high-speed USB device|Adding .* swap' "${kernel_events}"; then
    printf 'routine kernel messages were reported as incidents\n' >&2
    exit 1
fi

# One failing device can emit thousands of near-identical lines, and a log that
# scrolls past the freeze is no better than no log, so each scan is capped.
run_kernel_scan "${test_root}/state-kernel-flood" \
    FREEZE_WATCH_STUB_KERNEL="${test_root}/kernel-flood.txt"
test "$(grep -c $'\tKERNEL\t' \
    "${test_root}/state-kernel-flood/freeze-monitor/events.log")" = "3"

# The previous boot is only read when the machine went down without shutting
# down, otherwise every restart would replay the same lines.
seed_previous_session "${test_root}/state-kernel-freeze" \
    "00000000-0000-0000-0000-000000000000" ""
run_kernel_scan "${test_root}/state-kernel-freeze" \
    FREEZE_WATCH_STUB_PREVIOUS_BOOT="${test_root}/kernel-alerts.txt"
grep -q 'previous boot: .*GPU HANG' \
    "${test_root}/state-kernel-freeze/freeze-monitor/events.log"

seed_previous_session "${test_root}/state-kernel-clean" \
    "00000000-0000-0000-0000-000000000000" "STOP"
run_kernel_scan "${test_root}/state-kernel-clean" \
    FREEZE_WATCH_STUB_PREVIOUS_BOOT="${test_root}/kernel-alerts.txt"
if grep -q 'previous boot:' \
    "${test_root}/state-kernel-clean/freeze-monitor/events.log"; then
    printf 'the previous boot was replayed after a clean shutdown\n' >&2
    exit 1
fi

# An unreadable journal is normal for a user outside the adm group, and has to
# degrade rather than fail.
run_kernel_scan "${test_root}/state-no-journal" FREEZE_WATCH_STUB_PROBE_STATUS=1
grep -q 'kernel log unavailable' \
    "${test_root}/state-no-journal/freeze-monitor/events.log"
test -n "$(find "${test_root}/state-no-journal/freeze-monitor" \
    -maxdepth 1 -name 'metrics-*.tsv' -print -quit)"

# Elevated conditions switch the log to write-through, which is announced once
# on the transition rather than on every sample.
fake_hwmon "${test_root}/hwmon-hot" coretemp:92000
HOME="${test_home}" \
XDG_STATE_HOME="${test_root}/state-hot" \
FREEZE_WATCH_COMPOSE_PROJECT="" \
FREEZE_WATCH_MAX_SAMPLES=2 \
FREEZE_WATCH_INTERVAL_SECONDS=1 \
FREEZE_WATCH_HWMON_ROOT="${test_root}/hwmon-hot" \
    "${test_home}/.local/bin/freeze-monitor"
test "$(grep -c $'\tFLUSH\t' "${test_root}/state-hot/freeze-monitor/events.log")" = "1"

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
