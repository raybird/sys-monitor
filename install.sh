#!/usr/bin/env bash
#
# Freeze Watch installer.
#
# From a checkout:
#   ./install.sh [options]
#
# Without cloning:
#   curl -fsSL https://raw.githubusercontent.com/raybird/sys-monitor/main/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/raybird/sys-monitor/main/install.sh | bash -s -- --compose-project myproject
#
# The script installs entirely below $HOME and never needs root.

set -euo pipefail

readonly user_home="${HOME:?HOME is required}"
readonly bin_dir="${user_home}/.local/bin"
readonly data_home="${XDG_DATA_HOME:-${user_home}/.local/share}"
readonly data_dir="${data_home}/freeze-watch"
readonly applications_dir="${data_home}/applications"
readonly icon_theme_dir="${data_home}/icons/hicolor"
readonly config_home="${XDG_CONFIG_HOME:-${user_home}/.config}"
readonly unit_dir="${config_home}/systemd/user"
readonly autostart_dir="${config_home}/autostart"
readonly app_config_dir="${config_home}/freeze-watch"
readonly env_file="${app_config_dir}/env"
readonly state_dir="${XDG_STATE_HOME:-${user_home}/.local/state}/freeze-monitor"

readonly default_repo="raybird/sys-monitor"
readonly default_ref="main"

# Overridable so the test suite can observe how units are enabled and refreshed
# without touching the developer's own systemd user instance.
readonly systemctl_bin="${FREEZE_WATCH_SYSTEMCTL:-systemctl}"

# Every interpreter-dependent part of Freeze Watch imports exactly this set.
readonly python_probe='
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk
'

repo="${FREEZE_WATCH_REPO:-${default_repo}}"
ref="${FREEZE_WATCH_REF:-}"
python_bin="${FREEZE_WATCH_PYTHON:-}"
python_was_requested=0
source_dir="${FREEZE_WATCH_SOURCE:-}"
source_was_requested=0
compose_project=""
compose_project_was_set=0
no_start=0
print_python=0
download_dir=""

[[ -n "${python_bin}" ]] && python_was_requested=1
[[ -n "${source_dir}" ]] && source_was_requested=1

usage() {
    cat <<'EOF'
Usage: ./install.sh [options]
       curl -fsSL <raw-url>/install.sh | bash -s -- [options]

Options:
  --compose-project NAME  Deep-monitor one Docker Compose project.
  --python PATH           Use this Python interpreter instead of probing.
  --ref REF               Tag, branch, or commit to download when no local
                          source tree is present. Default: latest release,
                          falling back to "main".
  --repo OWNER/NAME       GitHub repository to download from.
                          Default: raybird/sys-monitor
  --source DIR            Install from an already extracted source tree.
  --no-start              Install files without enabling or starting services.
  --print-python          Print the resolved Python interpreter and exit.
  -h, --help              Show this help.

Environment:
  FREEZE_WATCH_PYTHON, FREEZE_WATCH_REF, FREEZE_WATCH_REPO,
  FREEZE_WATCH_SOURCE  Defaults for the matching options.
EOF
}

fail() {
    printf 'freeze-watch: %s\n' "$*" >&2
    exit 1
}

cleanup() {
    if [[ -n "${download_dir}" && -d "${download_dir}" ]]; then
        rm -rf -- "${download_dir}"
    fi
}
trap cleanup EXIT

while (($# > 0)); do
    case "$1" in
        --compose-project)
            (($# >= 2)) || fail "--compose-project requires a value"
            compose_project="$2"
            compose_project_was_set=1
            shift 2
            ;;
        --python)
            (($# >= 2)) || fail "--python requires a value"
            python_bin="$2"
            python_was_requested=1
            shift 2
            ;;
        --ref)
            (($# >= 2)) || fail "--ref requires a value"
            ref="$2"
            shift 2
            ;;
        --repo)
            (($# >= 2)) || fail "--repo requires a value"
            repo="$2"
            shift 2
            ;;
        --source)
            (($# >= 2)) || fail "--source requires a value"
            source_dir="$2"
            source_was_requested=1
            shift 2
            ;;
        --no-start)
            no_start=1
            shift
            ;;
        --print-python)
            print_python=1
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

if [[ ! "${repo}" =~ ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ ]]; then
    fail "Repository must look like OWNER/NAME: ${repo}"
fi

# --- Python interpreter -----------------------------------------------------

python_supports_freeze_watch() {
    local candidate="$1"
    [[ -n "${candidate}" ]] || return 1
    command -v "${candidate}" >/dev/null 2>&1 || return 1
    "${candidate}" -c "${python_probe}" >/dev/null 2>&1
}

# A system monitor outlives any one shell, so a version manager's shim
# (pyenv, asdf, conda, an activated virtualenv) is a poor default even when it
# happens to be first on PATH: it rarely carries the distribution's PyGObject
# and dbus bindings, and it can disappear from a systemd unit's environment.
# The distribution interpreter is therefore probed before whatever PATH offers.
resolve_python() {
    local candidate resolved seen=""
    local -a candidates=(/usr/bin/python3 /usr/local/bin/python3)

    resolved="$(command -v python3 2>/dev/null || true)"
    [[ -n "${resolved}" ]] && candidates+=("${resolved}")

    for candidate in "${candidates[@]}"; do
        case " ${seen} " in
            *" ${candidate} "*) continue ;;
        esac
        seen="${seen} ${candidate}"

        if python_supports_freeze_watch "${candidate}"; then
            printf '%s\n' "${candidate}"
            return 0
        fi
    done

    return 1
}

dependency_hint() {
    if command -v apt-get >/dev/null 2>&1; then
        printf '  sudo apt install python3 python3-gi python3-dbus gir1.2-gtk-4.0\n'
    elif command -v dnf >/dev/null 2>&1; then
        printf '  sudo dnf install python3 python3-gobject python3-dbus gtk4\n'
    elif command -v pacman >/dev/null 2>&1; then
        printf '  sudo pacman -S python python-gobject python-dbus gtk4\n'
    elif command -v zypper >/dev/null 2>&1; then
        printf '  sudo zypper install python3-gobject python3-gobject-Gdk \\\n'
        printf '      python3-dbus-python typelib-1_0-Gtk-4_0\n'
    elif command -v apk >/dev/null 2>&1; then
        printf '  sudo apk add python3 py3-gobject3 py3-dbus gtk4.0\n'
    elif command -v xbps-install >/dev/null 2>&1; then
        printf '  sudo xbps-install python3-gobject python3-dbus gtk4\n'
    else
        printf '  Install Python 3, PyGObject with GTK 4 typelibs, and dbus-python\n'
        printf '  using your distribution package manager.\n'
    fi
}

if ((python_was_requested == 1)); then
    python_supports_freeze_watch "${python_bin}" ||
        fail "${python_bin} cannot import dbus and GTK 4; pick another interpreter"
    python_bin="$(command -v "${python_bin}")"
else
    python_bin="$(resolve_python || true)"
fi

if [[ -z "${python_bin}" ]]; then
    {
        printf 'No Python interpreter with GTK 4 and dbus bindings was found.\n\n'
        printf 'Install the bindings:\n\n'
        dependency_hint
        printf '\nIf you manage Python with pyenv, asdf, conda, or a virtualenv,\n'
        printf 'those interpreters usually lack the system GTK bindings. Point the\n'
        printf 'installer at the distribution interpreter instead:\n\n'
        printf '  ./install.sh --python /usr/bin/python3\n'
    } >&2
    exit 1
fi

if ((print_python == 1)); then
    printf '%s\n' "${python_bin}"
    exit 0
fi

# --- Source tree ------------------------------------------------------------

# When the script is piped from curl there is no surrounding checkout, and
# BASH_SOURCE names a stream rather than a file. Only a real path is trusted,
# so a stray "main" file in the working directory cannot redirect the install.
script_dir=""
case "${BASH_SOURCE[0]:-}" in
    ""|bash|main|-|/dev/fd/*|/dev/stdin|/proc/self/fd/*) ;;
    *)
        if [[ -f "${BASH_SOURCE[0]}" ]]; then
            script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
        fi
        ;;
esac

has_source_tree() {
    [[ -n "$1" && -f "$1/src/freeze-monitor" && -f "$1/src/freeze_watch.py" ]]
}

fetch_url() {
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL --retry 3 --retry-delay 1 -- "$1"
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- -- "$1"
    else
        fail "downloading requires curl or wget"
    fi
}

latest_release_ref() {
    local body tag
    body="$(fetch_url "https://api.github.com/repos/${repo}/releases/latest" 2>/dev/null)" ||
        return 1
    tag="$(printf '%s' "${body}" |
        tr ',' '\n' |
        sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' |
        head -n 1)"
    [[ -n "${tag}" ]] || return 1
    printf '%s\n' "${tag}"
}

# The archive lands on disk before it is unpacked so that a failed transfer and
# a corrupt archive report themselves separately instead of surfacing as tar
# noise at the end of a broken pipe.
download_source() {
    local target="$1"
    local archive="${download_dir}/source.tar.gz"

    command -v tar >/dev/null 2>&1 || fail "downloading requires tar"

    if [[ -z "${ref}" ]]; then
        ref="$(latest_release_ref || true)"
        if [[ -z "${ref}" ]]; then
            ref="${default_ref}"
            printf 'No published release found; installing from %s.\n' "${ref}"
        fi
    fi

    printf 'Downloading %s@%s ...\n' "${repo}" "${ref}"
    fetch_url "https://codeload.github.com/${repo}/tar.gz/${ref}" > "${archive}" ||
        fail "could not download ${repo}@${ref}"

    mkdir -p -- "${target}"
    tar -xzf "${archive}" -C "${target}" --strip-components=1 2>/dev/null ||
        fail "the archive for ${repo}@${ref} could not be extracted"
    rm -f -- "${archive}"

    has_source_tree "${target}" ||
        fail "${repo}@${ref} does not contain a Freeze Watch source tree"
}

if ((source_was_requested == 1)); then
    has_source_tree "${source_dir}" ||
        fail "--source ${source_dir} is not a Freeze Watch source tree"
    source_dir="$(cd -- "${source_dir}" && pwd)"
elif has_source_tree "${script_dir}"; then
    source_dir="${script_dir}"
else
    download_dir="$(mktemp -d)"
    download_source "${download_dir}/tree"
    source_dir="${download_dir}/tree"
fi

version="unknown"
if [[ -r "${source_dir}/VERSION" ]]; then
    version="$(tr -d '[:space:]' < "${source_dir}/VERSION")"
fi

# --- Remaining prerequisites ------------------------------------------------

for command_name in bash awk df flock gzip install ps sync systemctl timeout; do
    command -v "${command_name}" >/dev/null 2>&1 ||
        fail "missing required command: ${command_name}"
done

if ((no_start == 0)); then
    "${systemctl_bin}" --user show-environment >/dev/null 2>&1 ||
        fail "systemd user session is unavailable; retry with --no-start"
fi

# --- Install ----------------------------------------------------------------

install -d -m 0755 \
    "${bin_dir}" "${data_dir}" "${applications_dir}" "${unit_dir}" "${app_config_dir}" \
    "${autostart_dir}" \
    "${icon_theme_dir}/scalable/apps" "${icon_theme_dir}/symbolic/apps"
install -m 0755 "${source_dir}/src/freeze-monitor" "${bin_dir}/freeze-monitor"
install -m 0755 "${source_dir}/src/freeze-monitor-maintain" "${bin_dir}/freeze-monitor-maintain"
install -m 0755 "${source_dir}/src/freeze-watch" "${bin_dir}/freeze-watch"
install -m 0755 "${source_dir}/src/freeze-watch-session" "${bin_dir}/freeze-watch-session"
install -m 0755 "${source_dir}/uninstall.sh" "${data_dir}/uninstall.sh"
install -m 0644 "${source_dir}/src/freeze_watch.py" "${data_dir}/freeze_watch.py"
install -m 0644 \
    "${source_dir}/packaging/com.raybird.FreezeWatch.desktop" \
    "${applications_dir}/com.raybird.FreezeWatch.desktop"
install -m 0644 \
    "${source_dir}/assets/icons/hicolor/scalable/apps/com.raybird.FreezeWatch.svg" \
    "${icon_theme_dir}/scalable/apps/com.raybird.FreezeWatch.svg"
install -m 0644 \
    "${source_dir}/assets/icons/hicolor/symbolic/apps/com.raybird.FreezeWatch-symbolic.svg" \
    "${source_dir}/assets/icons/hicolor/symbolic/apps/com.raybird.FreezeWatch-warning-symbolic.svg" \
    "${icon_theme_dir}/symbolic/apps/"
install -m 0644 "${source_dir}"/systemd/user/*.service "${unit_dir}/"
install -m 0644 "${source_dir}"/systemd/user/*.timer "${unit_dir}/"

# Desktop entries cannot express a home-relative program, and an autostart
# entry that misses because ~/.local/bin is absent from the session PATH fails
# silently. The placeholder is therefore expanded with plain string
# substitution, which has no pattern characters to escape.
autostart_entry="$(< "${source_dir}/packaging/com.raybird.FreezeWatch-autostart.desktop")"
printf '%s\n' "${autostart_entry//@BIN_DIR@/${bin_dir}}" \
    > "${autostart_dir}/com.raybird.FreezeWatch-autostart.desktop"
chmod 0644 "${autostart_dir}/com.raybird.FreezeWatch-autostart.desktop"

# The configuration file is rewritten on every run so that an upgrade always
# records the interpreter it verified, while settings the caller did not
# mention keep their previous value.
env_value() {
    local key="$1"
    [[ -r "${env_file}" ]] || return 0
    awk -v key="${key}" '
        index($0, key "=") == 1 { value = substr($0, length(key) + 2) }
        END { if (length(value)) print value }
    ' "${env_file}"
}

if ((compose_project_was_set == 0)); then
    compose_project="$(env_value FREEZE_WATCH_COMPOSE_PROJECT)"
fi

umask 077
{
    printf '# Written by the Freeze Watch installer. Safe to edit.\n'
    printf 'FREEZE_WATCH_PYTHON=%s\n' "${python_bin}"
    printf 'FREEZE_WATCH_COMPOSE_PROJECT=%s\n' "${compose_project}"
} > "${env_file}.new"
chmod 0600 "${env_file}.new"
mv -f "${env_file}.new" "${env_file}"

if ((no_start == 0)); then
    "${systemctl_bin}" --user daemon-reload

    # "enable --now" does nothing to a unit that is already running, so an
    # upgrade used to keep executing the previous program until the next
    # reboot. Anything already up is restarted onto the files just installed.
    enable_and_refresh() {
        local unit="$1"

        "${systemctl_bin}" --user enable "${unit}"

        if "${systemctl_bin}" --user is-active --quiet "${unit}"; then
            "${systemctl_bin}" --user restart "${unit}"
        else
            "${systemctl_bin}" --user start "${unit}"
        fi
    }

    enable_and_refresh freeze-monitor.service
    enable_and_refresh freeze-monitor-maintain.timer

    "${systemctl_bin}" --user enable freeze-watch.service

    if "${systemctl_bin}" --user is-active --quiet freeze-watch.service; then
        "${systemctl_bin}" --user restart freeze-watch.service
    elif "${systemctl_bin}" --user is-active --quiet graphical-session.target; then
        "${systemctl_bin}" --user start freeze-watch.service
    else
        printf 'Freeze Watch GUI will start with the next graphical session.\n'
    fi
fi

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${applications_dir}" >/dev/null 2>&1 || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "${icon_theme_dir}" >/dev/null 2>&1 || true
fi

case ":${PATH}:" in
    *":${bin_dir}:"*) ;;
    *)
        printf '\nNote: %s is not on PATH. Add it to run freeze-watch by name.\n' \
            "${bin_dir}"
        ;;
esac

cat <<EOF

Freeze Watch ${version} installed.

Python:    ${python_bin}
Collector: ${bin_dir}/freeze-monitor
Dashboard: ${bin_dir}/freeze-watch
State:     ${state_dir}
Config:    ${env_file}
Uninstall: ${data_dir}/uninstall.sh
EOF
