#!/bin/bash
#
# LightShow Pi installer
#
# Supported: Raspberry Pi OS / Debian 12 (bookworm) and 13 (trixie),
#            32-bit (armhf) or 64-bit (arm64).
#
# Usage:  sudo ./install.sh [options]
#
#   --with-service       install and enable a systemd service that starts the
#                        show at boot (lightshowpi.service)
#   --with-led           install LED strip support (BiblioPixel)
#   --with-wiringpi      install WiringPi 3.x (needed for I/O expanders and PiGlow)
#   --with-fm            install the 32-bit libraries used by the FM transmitter
#                        programs (Pi 1-4 only)
#   --with-sms           install the (legacy) SMS / Twitter dependencies
#   --all                all of the --with-* options above except --with-service
#   --skip-apt           don't install system packages (they must already be there)
#   --allow-unsupported  continue on an operating system that is not tested
#   --dry-run            print what would be done without changing anything
#   -h, --help           show this help
#
# What it changes on your system (all undone by ./uninstall.sh):
#   * installs Debian packages with apt (packages are NOT removed on uninstall)
#   * creates a Python virtual environment in <this folder>/.venv
#   * /etc/profile.d/lightshowpi.sh   (sets SYNCHRONIZED_LIGHTS_HOME and PATH)
#   * /usr/local/bin/lightshowpi      (symlink to bin/lightshowpi)
#   * /etc/systemd/system/lightshowpi.service   (only with --with-service)
#
# It does NOT rename /usr/bin/python, edit /etc/sudoers or change the
# graphics driver (the old installer did all three).

set -o pipefail

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${INSTALL_DIR}/.venv"
LOG_FILE="${LSP_INSTALL_LOG:-${INSTALL_DIR}/logs/install.log}"
OS_RELEASE="${LSP_OS_RELEASE:-/etc/os-release}"
PROFILE_FILE="${LSP_PROFILE_FILE:-/etc/profile.d/lightshowpi.sh}"
BIN_LINK="${LSP_BIN_LINK:-/usr/local/bin/lightshowpi}"
SERVICE_FILE="${LSP_SERVICE_FILE:-/etc/systemd/system/lightshowpi.service}"

WIRINGPI_VERSION="3.20"
WIRINGPI_SHA256_arm64="85f5965d57adb895b97b3f8b04083613d00964f930cb86822459eae5a97dc804"
WIRINGPI_SHA256_armhf="77b66d85109374f82ed5e1da03f7e710b3ec419fd9c39db10c0d66ca1542c055"

CORE_PACKAGES="python3 python3-venv python3-pip python3-numpy python3-alsaaudio python3-mutagen ffmpeg alsa-utils"
# installed when the distribution has them; otherwise the fallback is used
OPTIONAL_PACKAGES="python3-lgpio python3-legacy-cgi"
LED_PACKAGES="python3-serial python3-pil python3-setuptools python3-spidev"
SMS_PACKAGES="python3-bs4 python3-requests"

WITH_SERVICE=0; WITH_LED=0; WITH_WIRINGPI=0; WITH_FM=0; WITH_SMS=0
SKIP_APT=0; ALLOW_UNSUPPORTED=0; DRY_RUN=0

# ----------------------------------------------------------------- helpers
bold=""; red=""; yellow=""; green=""; reset=""
if [ -t 1 ]; then
    bold="$(tput bold 2>/dev/null)"; red="$(tput setaf 1 2>/dev/null)"
    yellow="$(tput setaf 3 2>/dev/null)"; green="$(tput setaf 2 2>/dev/null)"
    reset="$(tput sgr0 2>/dev/null)"
fi

log()  { echo "$*" >> "$LOG_FILE" 2>/dev/null; }
step() { echo; echo "${bold}==> $*${reset}"; log "==> $*"; }
info() { echo "    $*"; log "    $*"; }
warn() { echo "${yellow}WARNING:${reset} $*" >&2; log "WARNING: $*"; }
die()  {
    echo >&2
    echo "${red}${bold}ERROR:${reset} $*" >&2
    log "ERROR: $*"
    echo >&2
    echo "The install log is in ${LOG_FILE}" >&2
    echo "See docs/TROUBLESHOOTING.md for help." >&2
    exit 1
}

# run a command (or print it in --dry-run mode); output goes to the log
run() {
    if [ "$DRY_RUN" -eq 1 ]; then
        echo "    [dry-run] $*"
        return 0
    fi
    log "+ $*"
    "$@" >> "$LOG_FILE" 2>&1
}

usage() { sed -n '3,30p' "$0" | sed 's/^# \{0,1\}//'; }

# ----------------------------------------------------------------- options
for arg in "$@"; do
    case "$arg" in
        --with-service) WITH_SERVICE=1 ;;
        --with-led) WITH_LED=1 ;;
        --with-wiringpi) WITH_WIRINGPI=1 ;;
        --with-fm) WITH_FM=1 ;;
        --with-sms) WITH_SMS=1 ;;
        --all) WITH_LED=1; WITH_WIRINGPI=1; WITH_FM=1; WITH_SMS=1 ;;
        --skip-apt) SKIP_APT=1 ;;
        --allow-unsupported) ALLOW_UNSUPPORTED=1 ;;
        --dry-run) DRY_RUN=1 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $arg" >&2; usage >&2; exit 2 ;;
    esac
done

if [ "$DRY_RUN" -eq 0 ] && [ "$(id -u)" -ne 0 ]; then
    echo "Please run the installer with sudo:" >&2
    echo "    sudo $0 $*" >&2
    exit 1
fi

if [ "$DRY_RUN" -eq 0 ]; then
    mkdir -p "$(dirname "$LOG_FILE")"
    : > "$LOG_FILE" || die "Cannot write the install log $LOG_FILE"
else
    LOG_FILE=/dev/null
fi
log "LightShow Pi install started $(date)"
log "Options: $*"

echo "${bold}LightShow Pi installer${reset}"
echo "Install folder: ${INSTALL_DIR}"

# ----------------------------------------------------------------- checks
step "Checking your system"

[ -f "${INSTALL_DIR}/py/synchronized_lights.py" ] || \
    die "This script must be run from the LightShow Pi folder (py/synchronized_lights.py not found)."

case "$INSTALL_DIR" in
    *" "*) die "The install folder path contains a space: '$INSTALL_DIR'. Move LightShow Pi to a folder without spaces (for example /home/pi/lightshowpi)." ;;
esac

[ -r "$OS_RELEASE" ] || die "Cannot read $OS_RELEASE - unable to identify the operating system."
# shellcheck disable=SC1090
. "$OS_RELEASE"
OS_ID="${ID:-unknown}"
OS_LIKE="${ID_LIKE:-}"
OS_CODENAME="${VERSION_CODENAME:-unknown}"
info "Operating system: ${PRETTY_NAME:-$OS_ID} (${OS_CODENAME})"

SUPPORTED=0
case " $OS_ID $OS_LIKE " in
    *" debian "*|*" raspbian "*)
        case "$OS_CODENAME" in
            bookworm|trixie) SUPPORTED=1 ;;
        esac ;;
esac
if [ "$SUPPORTED" -eq 0 ]; then
    if [ "$ALLOW_UNSUPPORTED" -eq 1 ]; then
        warn "${PRETTY_NAME:-$OS_ID} is not a tested system. Continuing because --allow-unsupported was given."
    else
        case "$OS_CODENAME" in
            buster|bullseye)
                die "Debian/Raspberry Pi OS '$OS_CODENAME' is too old. Please flash Raspberry Pi OS Bookworm or Trixie with Raspberry Pi Imager. (To try anyway: --allow-unsupported)" ;;
            *)
                die "${PRETTY_NAME:-$OS_ID} is not supported. LightShow Pi supports Raspberry Pi OS / Debian 12 (bookworm) and 13 (trixie). To try anyway: sudo $0 --allow-unsupported" ;;
        esac
    fi
fi

command -v apt-get >/dev/null 2>&1 || [ "$SKIP_APT" -eq 1 ] || die "apt-get not found. This installer needs a Debian based system."

ARCH="$(dpkg --print-architecture 2>/dev/null || uname -m)"
info "Architecture: $ARCH"

IS_PI=0
if grep -qs "Raspberry Pi" /proc/device-tree/model; then
    IS_PI=1
    info "Board: $(tr -d '\0' < /proc/device-tree/model)"
else
    warn "This does not look like a Raspberry Pi. LightShow Pi will install, but GPIO will be simulated (no lights)."
fi

# ----------------------------------------------------------------- apt
pkg_available() {
    # true if apt has an installation candidate for the package
    local candidate
    candidate="$(apt-cache policy "$1" 2>/dev/null | awk '/Candidate:/ {print $2}')"
    [ -n "$candidate" ] && [ "$candidate" != "(none)" ]
}

install_packages() {
    # install_packages <required:0|1> <packages...>
    local required="$1"; shift
    local wanted=() missing=()
    for p in "$@"; do
        if pkg_available "$p"; then wanted+=("$p"); else missing+=("$p"); fi
    done
    if [ ${#missing[@]} -gt 0 ]; then
        if [ "$required" -eq 1 ]; then
            die "These required packages are not available from your apt sources: ${missing[*]}. Run 'sudo apt update' and check your internet connection."
        fi
        info "Not available from apt (will use a fallback if needed): ${missing[*]}"
    fi
    if [ ${#wanted[@]} -gt 0 ]; then
        info "Installing: ${wanted[*]}"
        run env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${wanted[@]}" || \
            die "apt-get could not install: ${wanted[*]}. Details are in ${LOG_FILE}."
    fi
}

if [ "$SKIP_APT" -eq 0 ]; then
    step "Installing system packages (this can take a few minutes)"
    run apt-get update || die "'apt-get update' failed. Check your internet connection and try again."
    install_packages 1 $CORE_PACKAGES
    install_packages 0 $OPTIONAL_PACKAGES
    [ "$WITH_LED" -eq 1 ] && install_packages 0 $LED_PACKAGES
    [ "$WITH_SMS" -eq 1 ] && install_packages 0 $SMS_PACKAGES
    if [ "$WITH_WIRINGPI" -eq 1 ] || [ "$WITH_SMS" -eq 1 ]; then
        install_packages 1 ca-certificates curl
    fi
    if [ "$WITH_SMS" -eq 1 ]; then
        install_packages 1 git
    fi
else
    step "Skipping system packages (--skip-apt)"
fi

# ----------------------------------------------------------------- WiringPi
if [ "$WITH_WIRINGPI" -eq 1 ]; then
    step "Installing WiringPi ${WIRINGPI_VERSION} (official release from github.com/WiringPi/WiringPi)"
    case "$ARCH" in
        arm64) WPI_SHA="$WIRINGPI_SHA256_arm64" ;;
        armhf) WPI_SHA="$WIRINGPI_SHA256_armhf" ;;
        *) WPI_SHA="" ;;
    esac
    if [ -z "$WPI_SHA" ]; then
        warn "WiringPi packages exist only for arm64 and armhf, not '$ARCH'. Skipping WiringPi."
    elif [ "$DRY_RUN" -eq 1 ]; then
        info "[dry-run] download and verify wiringpi_${WIRINGPI_VERSION}_${ARCH}.deb, then apt-get install it"
    else
        WPI_DEB="wiringpi_${WIRINGPI_VERSION}_${ARCH}.deb"
        WPI_TMP="$(mktemp -d)"
        WPI_URL="https://github.com/WiringPi/WiringPi/releases/download/v${WIRINGPI_VERSION}/${WPI_DEB}"
        run curl -fsSL -o "${WPI_TMP}/${WPI_DEB}" "$WPI_URL" || die "Could not download $WPI_URL"
        echo "${WPI_SHA}  ${WPI_TMP}/${WPI_DEB}" | sha256sum -c --status || \
            die "The downloaded WiringPi package failed its SHA-256 check. Not installing it."
        run apt-get install -y "${WPI_TMP}/${WPI_DEB}" || die "Installing WiringPi failed (see ${LOG_FILE})."
        rm -rf "$WPI_TMP"
        info "WiringPi installed: $(gpio -v 2>/dev/null | head -1)"
    fi
fi

# ----------------------------------------------------------------- FM
if [ "$WITH_FM" -eq 1 ]; then
    step "Installing FM transmitter support"
    if grep -qs "Raspberry Pi 5\|Raspberry Pi 500\|Compute Module 5" /proc/device-tree/model; then
        warn "The FM transmitter programs do not work on the Raspberry Pi 5 family. Skipping."
    elif [ "$ARCH" = "arm64" ]; then
        info "The FM programs are 32-bit; adding the armhf architecture for their libraries."
        run dpkg --add-architecture armhf || die "dpkg --add-architecture armhf failed"
        run apt-get update || die "apt-get update failed"
        install_packages 1 libc6:armhf libsndfile1:armhf
    elif [ "$ARCH" = "armhf" ]; then
        install_packages 1 libsndfile1
    else
        warn "FM transmitter support needs a Raspberry Pi (armhf/arm64). Skipping."
    fi
fi

# ----------------------------------------------------------------- venv
step "Creating the Python environment in ${VENV_DIR}"
PYTHON3="$(command -v python3)" || die "python3 is not installed."
PY_VERSION="$("$PYTHON3" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
info "Python ${PY_VERSION} (${PYTHON3})"
"$PYTHON3" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || \
    die "Python ${PY_VERSION} is too old; LightShow Pi needs Python 3.9 or newer."

if [ -x "${VENV_DIR}/bin/python" ] && ! "${VENV_DIR}/bin/python" -c "import sys" >/dev/null 2>&1; then
    info "Existing environment is broken (Python was upgraded?); recreating it."
    run rm -rf "${VENV_DIR}"
fi
if [ ! -x "${VENV_DIR}/bin/python" ]; then
    # --system-site-packages lets the environment use the apt packages
    # (numpy, alsaaudio, mutagen, lgpio) instead of compiling them with pip.
    run "$PYTHON3" -m venv --system-site-packages "${VENV_DIR}" || \
        die "Could not create the virtual environment. Is python3-venv installed?"
fi
PIP=("${VENV_DIR}/bin/python" -m pip install --disable-pip-version-check --no-input)

pip_install() {
    run "${PIP[@]}" "$@" || die "pip install $* failed. Details are in ${LOG_FILE}."
}

# Fallback for systems without the Debian python3-* packages (only with
# --allow-unsupported / --skip-apt): build them with pip.
if [ "$DRY_RUN" -eq 0 ]; then
    if ! "${VENV_DIR}/bin/python" -c "import numpy, alsaaudio, mutagen" >/dev/null 2>&1; then
        info "Some core Python modules are missing from apt; installing them with pip."
        info "(pyalsaaudio needs the ALSA headers: sudo apt install libasound2-dev build-essential)"
        pip_install -r "${INSTALL_DIR}/requirements/fallback.txt"
    fi
fi
pip_install -r "${INSTALL_DIR}/requirements/core.txt"
[ "$WITH_LED" -eq 1 ] && pip_install -r "${INSTALL_DIR}/requirements/led.txt"
[ "$WITH_SMS" -eq 1 ] && pip_install -r "${INSTALL_DIR}/requirements/sms.txt"

if [ "$DRY_RUN" -eq 0 ]; then
    "${VENV_DIR}/bin/python" -c "import numpy, alsaaudio, mutagen" >> "$LOG_FILE" 2>&1 || \
        die "The core Python modules (numpy, alsaaudio, mutagen) still cannot be imported."
    if [ "$IS_PI" -eq 1 ] && ! "${VENV_DIR}/bin/python" -c "import lgpio" >/dev/null 2>&1 && [ "$WITH_WIRINGPI" -eq 0 ]; then
        warn "No GPIO library is available (python3-lgpio is not in your apt sources). Install it with 'sudo apt install python3-lgpio' or re-run with --with-wiringpi."
    fi
    # let the owner of the folder manage the environment without sudo
    OWNER="$(stat -c %U "${INSTALL_DIR}")"
    if [ -n "$OWNER" ] && [ "$OWNER" != "root" ]; then
        chown -R "${OWNER}:" "${VENV_DIR}" "${INSTALL_DIR}/logs" 2>/dev/null || true
    fi
fi

# ----------------------------------------------------------------- files
step "Setting up commands and environment"
if [ "$DRY_RUN" -eq 1 ]; then
    info "[dry-run] write ${PROFILE_FILE}"
    info "[dry-run] link ${BIN_LINK} -> ${INSTALL_DIR}/bin/lightshowpi"
else
    mkdir -p "$(dirname "$PROFILE_FILE")"
    cat > "$PROFILE_FILE" <<EOF
# Added by the LightShow Pi installer ($(date +%Y-%m-%d)); removed by uninstall.sh
export SYNCHRONIZED_LIGHTS_HOME=${INSTALL_DIR}
case ":\$PATH:" in
    *":${INSTALL_DIR}/bin:"*) ;;
    *) export PATH="\$PATH:${INSTALL_DIR}/bin" ;;
esac
EOF
    chmod 644 "$PROFILE_FILE"
    mkdir -p "$(dirname "$BIN_LINK")"
    ln -sfn "${INSTALL_DIR}/bin/lightshowpi" "$BIN_LINK"
    info "Created ${PROFILE_FILE} and ${BIN_LINK}"
fi

if [ "$WITH_SERVICE" -eq 1 ]; then
    step "Installing the lightshowpi systemd service"
    if [ "$DRY_RUN" -eq 1 ]; then
        info "[dry-run] write ${SERVICE_FILE}; systemctl enable lightshowpi.service"
    else
        sed "s|@INSTALL_DIR@|${INSTALL_DIR}|g" "${INSTALL_DIR}/install-scripts/lightshowpi.service" > "$SERVICE_FILE"
        chmod 644 "$SERVICE_FILE"
        if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
            run systemctl daemon-reload
            run systemctl enable lightshowpi.service || warn "Could not enable lightshowpi.service"
            info "The show will start at boot. Start it now with: sudo systemctl start lightshowpi"
        else
            warn "systemd is not running here; ${SERVICE_FILE} was written but not enabled."
        fi
    fi
fi

# ----------------------------------------------------------------- check
step "Checking the installation"
if [ "$DRY_RUN" -eq 1 ]; then
    info "[dry-run] ${INSTALL_DIR}/bin/lightshowpi doctor"
    echo
    echo "Dry run finished; nothing was changed."
    exit 0
fi
DOCTOR_STATUS=0
SYNCHRONIZED_LIGHTS_HOME="$INSTALL_DIR" "${VENV_DIR}/bin/python" "${INSTALL_DIR}/py/doctor.py" || DOCTOR_STATUS=$?

echo
if [ "$DOCTOR_STATUS" -eq 0 ]; then
    echo "${green}${bold}LightShow Pi is installed.${reset}"
else
    echo "${yellow}${bold}LightShow Pi is installed, but the check above found problems to fix.${reset}"
fi
cat <<EOF

Next steps:
  1. Copy the example settings:   cp ${INSTALL_DIR}/config/overrides.cfg.example ${INSTALL_DIR}/config/overrides.cfg
     and edit gpio_pins / audio_out_card for your setup.
  2. Check everything:            lightshowpi doctor
  3. Test your lights:            lightshowpi flash
  4. Play the sample songs:       lightshowpi playlist

Full instructions: ${INSTALL_DIR}/docs/INSTALL.md
To uninstall:      sudo ${INSTALL_DIR}/uninstall.sh
EOF
exit 0
