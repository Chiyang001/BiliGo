#!/bin/sh
set -e

mkdir -p "$BILIGO_DATA_DIR"
python -c "from app_paths import ensure_data_files; ensure_data_files()"
python -c "from playwright_runtime import ensure_playwright_ready; import sys; sys.exit(0 if ensure_playwright_ready() else 1)"

exec "$@"
