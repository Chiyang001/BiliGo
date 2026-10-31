#!/usr/bin/env bash
set -euo pipefail
umask 077

case "${1:-}" in
    -h|--help)
        echo "Usage: bash install_linux.sh [--with-deps]"
        echo "--with-deps also installs Chromium system libraries (may request sudo)."
        echo "Set PYTHON_BIN to select Python 3.11 or newer."
        exit 0 ;;
    ""|--with-deps) ;;
    *) echo "[ERROR] Unknown argument: $1" >&2; exit 2 ;;
esac
if (( $# > 1 )); then
    echo "[ERROR] Too many arguments. Use --help." >&2
    exit 2
fi

source "$(dirname -- "${BASH_SOURCE[0]}")/deploy/linux/environment.sh"
cd -- "$BILIGO_PROJECT_DIR"

python_bin="${PYTHON_BIN:-python3}"
if ! command -v "$python_bin" >/dev/null 2>&1; then
    echo "[ERROR] Python not found: $python_bin. Install Python 3.11+ and its venv package." >&2
    exit 1
fi
"$python_bin" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "Python 3.11+ is required")'
if [[ ! -x "$BILIGO_VENV_DIR/bin/python" ]]; then
    if ! "$python_bin" -m venv "$BILIGO_VENV_DIR"; then
        echo "[ERROR] Cannot create venv. Install the venv package for the selected Python." >&2
        exit 1
    fi
fi
python_venv="$BILIGO_VENV_DIR/bin/python"
"$python_venv" -m pip install -r requirements.txt

browser_args=(install chromium)
if [[ "${1:-}" == "--with-deps" ]]; then
    browser_args+=(--with-deps)
fi
"$python_venv" -m playwright "${browser_args[@]}"
"$python_venv" -c 'from playwright_runtime import ensure_playwright_ready; raise SystemExit(0 if ensure_playwright_ready() else 1)'
mkdir -p -- "$BILIGO_DATA_DIR"
echo "[OK] Linux environment is ready. Start with: bash start.sh"
echo "[INFO] Data directory: $BILIGO_DATA_DIR"
