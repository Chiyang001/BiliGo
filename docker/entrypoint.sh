#!/bin/sh
set -e

mkdir -p "$BILIGO_DATA_DIR"
python -c "from app_paths import ensure_data_files; ensure_data_files()"

exec "$@"
