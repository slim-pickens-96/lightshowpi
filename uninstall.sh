#!/bin/bash
#
# LightShow Pi uninstaller - removes what install.sh added.
#
# Usage:  sudo ./uninstall.sh [--dry-run] [--purge]
#
#   --dry-run   show what would be removed
#   --purge     also delete this LightShow Pi folder (including your
#               config/overrides.cfg, playlists and logs!)
#
# Debian packages installed by install.sh (numpy, ffmpeg, ...) are kept because
# other programs may use them.  Remove them with apt if you no longer need them.

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE_FILE="${LSP_PROFILE_FILE:-/etc/profile.d/lightshowpi.sh}"
BIN_LINK="${LSP_BIN_LINK:-/usr/local/bin/lightshowpi}"
SERVICE_FILE="${LSP_SERVICE_FILE:-/etc/systemd/system/lightshowpi.service}"
DRY_RUN=0; PURGE=0

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --purge) PURGE=1 ;;
        -h|--help) sed -n '3,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done

if [ "$DRY_RUN" -eq 0 ] && [ "$(id -u)" -ne 0 ]; then
    echo "Please run with sudo: sudo $0 $*" >&2
    exit 1
fi

remove() {
    if [ -e "$1" ] || [ -L "$1" ]; then
        if [ "$DRY_RUN" -eq 1 ]; then echo "[dry-run] remove $1"; else rm -rf "$1" && echo "removed $1"; fi
    fi
}

# stop a running show and turn the lights off
if [ "$DRY_RUN" -eq 0 ] && [ -x "${INSTALL_DIR}/bin/stop_music_and_lights" ]; then
    "${INSTALL_DIR}/bin/stop_music_and_lights" >/dev/null 2>&1 || true
fi

if [ -f "$SERVICE_FILE" ]; then
    if [ "$DRY_RUN" -eq 1 ]; then
        echo "[dry-run] systemctl disable --now lightshowpi.service"
    elif command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
        systemctl disable --now lightshowpi.service >/dev/null 2>&1 || true
    fi
    remove "$SERVICE_FILE"
    if [ "$DRY_RUN" -eq 0 ] && command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
        systemctl daemon-reload || true
    fi
fi

# only remove the command link if it points at this installation
if [ -L "$BIN_LINK" ] && [ "$(readlink "$BIN_LINK")" = "${INSTALL_DIR}/bin/lightshowpi" ]; then
    remove "$BIN_LINK"
fi
if [ -f "$PROFILE_FILE" ] && grep -qi "lightshow pi" "$PROFILE_FILE"; then
    remove "$PROFILE_FILE"
fi
remove "${INSTALL_DIR}/.venv"

if [ "$PURGE" -eq 1 ]; then
    remove "${INSTALL_DIR}"
fi

# Things the OLD (pre-2026) installer did that we never undo automatically.
if [ -e /usr/bin/python2 ] && [ -L /usr/bin/python ] && [ ! -e /usr/lib/python2.7 ]; then
    echo
    echo "Note: an older LightShow Pi installer replaced /usr/bin/python with a link to python3."
    echo "      This is harmless. To undo it: sudo rm /usr/bin/python && sudo apt install python-is-python3"
fi
if grep -qs 'env_keep="\{0,1\}SYNCHRONIZED_LIGHTS_HOME' /etc/sudoers; then
    echo
    echo "Note: /etc/sudoers contains a line added by an older LightShow Pi installer:"
    echo "      Defaults  env_keep=SYNCHRONIZED_LIGHTS_HOME"
    echo "      It is harmless. To remove it, run 'sudo visudo' and delete that line."
fi

echo
if [ "$DRY_RUN" -eq 1 ]; then echo "Dry run finished; nothing was changed."; else echo "LightShow Pi has been uninstalled."; fi
