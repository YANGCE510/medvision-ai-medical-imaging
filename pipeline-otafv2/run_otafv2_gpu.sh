#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GPU_ENV="/path/to/anaconda3/envs/ppgl-gpu38"

export PYTHONNOUSERSITE=1
export LD_LIBRARY_PATH="${GPU_ENV}/lib:/usr/local/cuda-11.4/lib64:${LD_LIBRARY_PATH:-}"

exec "${GPU_ENV}/bin/python" "${SCRIPT_DIR}/run_otafv2.py" "$@"
