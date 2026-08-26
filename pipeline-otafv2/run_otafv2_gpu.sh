#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PPGL_PYTHON:-$(command -v python)}"
ENV_PREFIX="$($PYTHON_BIN -c 'import sys; print(sys.prefix)')"

export PYTHONNOUSERSITE=1
export LD_LIBRARY_PATH="${ENV_PREFIX}/lib:${LD_LIBRARY_PATH:-}"

exec "$PYTHON_BIN" "${SCRIPT_DIR}/run_otafv2.py" "$@"
