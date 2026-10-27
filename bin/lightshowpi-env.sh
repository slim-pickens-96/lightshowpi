# shellcheck shell=bash
#
# Common environment for the LightShow Pi scripts in this directory.
# Sourced (not executed) by bin/play, bin/start_music_and_lights, etc.
#
# * Works out SYNCHRONIZED_LIGHTS_HOME from the script location if it is not
#   already set, so a fresh login shell is no longer required after install.
# * Uses the Python interpreter from the LightShow Pi virtual environment
#   ($SYNCHRONIZED_LIGHTS_HOME/.venv) created by install.sh.
# * Runs Python as root through sudo (GPIO and the FM transmitter need it),
#   passing the variables LightShow Pi needs.  Set LIGHTSHOWPI_NO_SUDO=1 to
#   run as the current user (for example if your user is in the gpio group).
# * LIGHTSHOWPI_PYTHON=/path/to/python overrides the interpreter.

if [ -z "${SYNCHRONIZED_LIGHTS_HOME}" ]; then
    SYNCHRONIZED_LIGHTS_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
export SYNCHRONIZED_LIGHTS_HOME

if [ ! -f "${SYNCHRONIZED_LIGHTS_HOME}/py/synchronized_lights.py" ]; then
    echo "ERROR: SYNCHRONIZED_LIGHTS_HOME=${SYNCHRONIZED_LIGHTS_HOME} does not look like a" >&2
    echo "LightShow Pi folder (py/synchronized_lights.py is missing)." >&2
    echo "Unset the variable or point it to the folder you installed LightShow Pi in." >&2
    exit 1
fi

if [ -n "${LIGHTSHOWPI_PYTHON}" ]; then
    # explicit interpreter (development, testing or a custom environment)
    LSP_PYTHON="${LIGHTSHOWPI_PYTHON}"
elif [ -x "${SYNCHRONIZED_LIGHTS_HOME}/.venv/bin/python" ]; then
    LSP_PYTHON="${SYNCHRONIZED_LIGHTS_HOME}/.venv/bin/python"
    PATH="${SYNCHRONIZED_LIGHTS_HOME}/.venv/bin:${PATH}"
    export PATH
elif command -v python3 >/dev/null 2>&1; then
    LSP_PYTHON="$(command -v python3)"
    echo "WARNING: LightShow Pi virtual environment not found; using ${LSP_PYTHON}." >&2
    echo "         Run: sudo ${SYNCHRONIZED_LIGHTS_HOME}/install.sh" >&2
else
    echo "ERROR: python3 is not installed. Run: sudo ${SYNCHRONIZED_LIGHTS_HOME}/install.sh" >&2
    exit 1
fi

LSP_ENV_VARS=("SYNCHRONIZED_LIGHTS_HOME=${SYNCHRONIZED_LIGHTS_HOME}" "PATH=${PATH}")
for _lsp_var in LIGHTSHOWPI_GPIO_BACKEND LIGHTSHOWPI_CPUINFO LIGHTSHOWPI_DT_MODEL LIGHTSHOWPI_SIM_TRACE; do
    if [ -n "${!_lsp_var}" ]; then
        LSP_ENV_VARS+=("${_lsp_var}=${!_lsp_var}")
    fi
done

if [ "$(id -u)" -eq 0 ] || [ -n "${LIGHTSHOWPI_NO_SUDO}" ]; then
    LSP_SUDO=(env)
else
    LSP_SUDO=(sudo env)
fi

# Run a LightShow Pi Python program (as root unless LIGHTSHOWPI_NO_SUDO is set).
# The interpreter path ends in ".../bin/python" so the existing
# "pkill -f 'python $SYNCHRONIZED_LIGHTS_HOME/py'" commands keep working.
lsp_python() {
    "${LSP_SUDO[@]}" "${LSP_ENV_VARS[@]}" "${LSP_PYTHON}" "$@"
}

# Run a command as root (unless already root / LIGHTSHOWPI_NO_SUDO is set)
lsp_sudo() {
    if [ "$(id -u)" -eq 0 ] || [ -n "${LIGHTSHOWPI_NO_SUDO}" ]; then
        "$@"
    else
        sudo "$@"
    fi
}
