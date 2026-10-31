#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    echo "Usage: bash start.sh [--version | --reset-panel-password]"
    echo "Install first with: bash install_linux.sh --with-deps"
    echo "See LINUX.md for data paths, desktop login and systemd deployment."
    exit 0
fi

source "$(dirname -- "${BASH_SOURCE[0]}")/deploy/linux/environment.sh"
cd -- "$BILIGO_PROJECT_DIR"
python_venv="$BILIGO_VENV_DIR/bin/python"
if [[ ! -x "$python_venv" ]]; then
    echo "[ERROR] Linux Python environment is missing. Run: bash install_linux.sh --with-deps" >&2
    exit 1
fi

# Desktop users get the panel automatically; SSH/systemd sessions stay in console.
if [[ -z "${BILIGO_OPEN_BROWSER+x}" ]]; then
    if [[ -n "${DISPLAY:-}" ]]; then
        export BILIGO_OPEN_BROWSER=1
    else
        export BILIGO_OPEN_BROWSER=0
    fi
fi
mkdir -p -- "$BILIGO_DATA_DIR"
exec "$python_venv" "$BILIGO_PROJECT_DIR/launcher.py" "$@"
