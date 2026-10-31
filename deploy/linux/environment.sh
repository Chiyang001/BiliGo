#!/usr/bin/env bash
# Shared by install_linux.sh and start.sh; source this file with Bash.
if [[ "$(uname -s)" != "Linux" ]]; then
    echo "[ERROR] This entry point requires Linux. Use start.bat on Windows." >&2
    return 1
fi

BILIGO_PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
export BILIGO_VENV_DIR="${BILIGO_VENV_DIR:-$BILIGO_PROJECT_DIR/.venv-linux}"
export BILIGO_DATA_DIR="${BILIGO_DATA_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/biligo-linux}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-${XDG_CACHE_HOME:-$HOME/.cache}/biligo-linux/ms-playwright}"
export PYTHONUNBUFFERED=1

# Relative overrides always refer to the project, even when called elsewhere.
for biligo_path_var in BILIGO_VENV_DIR BILIGO_DATA_DIR PLAYWRIGHT_BROWSERS_PATH; do
    biligo_path_value="${!biligo_path_var}"
    if [[ "$biligo_path_value" != /* ]] &&
       [[ "$biligo_path_var" != "PLAYWRIGHT_BROWSERS_PATH" || "$biligo_path_value" != "0" ]]; then
        printf -v "$biligo_path_var" '%s/%s' "$BILIGO_PROJECT_DIR" "$biligo_path_value"
    fi
done
unset biligo_path_var biligo_path_value
