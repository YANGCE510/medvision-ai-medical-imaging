#!/usr/bin/env bash
set -euo pipefail

CODE_ALL_DIR="/path/to/PPGL/Code_ALL"
BACKEND_DIR="$CODE_ALL_DIR/backend"
FRONTEND_DIR="/path/to/PPGL/ppgl-frontend"
CONDA_SH="/path/to/anaconda3/etc/profile.d/conda.sh"
CONDA_ENV="ppgl-gpu38"

MINICPM_HOST="127.0.0.1"
MINICPM_PORT="18080"
BACKEND_HOST="0.0.0.0"
BACKEND_PORT="8000"
FRONTEND_HOST="0.0.0.0"
FRONTEND_PORT="5173"

MINICPM_LOG="$BACKEND_DIR/local_minicpm_server.log"
BACKEND_LOG="$BACKEND_DIR/uvicorn_backend.log"
FRONTEND_LOG="$FRONTEND_DIR/frontend_vite.log"
CURL_BIN="/usr/bin/curl"

if [ -f "$CODE_ALL_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$CODE_ALL_DIR/.env"
  set +a
fi

if [ -f "$CONDA_SH" ]; then
  # shellcheck disable=SC1090
  source "$CONDA_SH"
fi
conda activate "$CONDA_ENV"

export MINICPM_MODEL_DIR="${MINICPM_MODEL_DIR:-$CODE_ALL_DIR/models/MiniCPM5-1B}"
export CHAT_LLM_PROVIDER="${CHAT_LLM_PROVIDER:-openai_compat}"
export CHAT_OPENAI_BASE_URL="${CHAT_OPENAI_BASE_URL:-http://127.0.0.1:18080/v1}"
export CHAT_OPENAI_MODEL="${CHAT_OPENAI_MODEL:-MiniCPM5-1B}"
export CHAT_OPENAI_API_KEY="${CHAT_OPENAI_API_KEY:-EMPTY}"

export REPORT_LLM_PROVIDER="${REPORT_LLM_PROVIDER:-openai_compat}"
export REPORT_OPENAI_MODEL="${REPORT_OPENAI_MODEL:-gpt-5.5}"
export REPORT_OPENAI_REASONING_EFFORT="${REPORT_OPENAI_REASONING_EFFORT:-xhigh}"

if [ -z "${REPORT_OPENAI_BASE_URL:-}" ]; then
  read -r -p "REPORT_OPENAI_BASE_URL（例如 https://xxx/v1）: " REPORT_OPENAI_BASE_URL
  export REPORT_OPENAI_BASE_URL
fi

if [ -z "${REPORT_OPENAI_API_KEY:-}" ]; then
  read -r -s -p "REPORT_OPENAI_API_KEY: " REPORT_OPENAI_API_KEY
  echo
  export REPORT_OPENAI_API_KEY
fi

export PATH="/path/to/anaconda3/envs/$CONDA_ENV/bin:$PATH"
export LD_LIBRARY_PATH="/path/to/anaconda3/envs/$CONDA_ENV/lib:${LD_LIBRARY_PATH:-}"
export NO_PROXY="127.0.0.1,localhost,${NO_PROXY:-}"
export no_proxy="127.0.0.1,localhost,${no_proxy:-}"

stop_existing() {
  pkill -f "uvicorn local_minicpm_server:app" 2>/dev/null || true
  pkill -f "uvicorn main:app" 2>/dev/null || true
  pkill -f "vite --host $FRONTEND_HOST --port $FRONTEND_PORT" 2>/dev/null || true
  sleep 1
}

wait_for_http() {
  local url="$1"
  local name="$2"
  local max_attempts="${3:-60}"
  local attempt
  for attempt in $(seq 1 "$max_attempts"); do
    if env -u LD_LIBRARY_PATH "$CURL_BIN" -fsS --max-time 2 "$url" >/dev/null 2>&1; then
      echo "$name started: $url"
      return 0
    fi
    sleep 1
  done
  echo "$name failed to start: $url" >&2
  return 1
}

stop_existing

cd "$BACKEND_DIR"
setsid python -m uvicorn local_minicpm_server:app \
  --host "$MINICPM_HOST" \
  --port "$MINICPM_PORT" \
  >> "$MINICPM_LOG" 2>&1 < /dev/null &

echo "Local MiniCPM starting: http://$MINICPM_HOST:$MINICPM_PORT/health"
sleep 5

cd "$BACKEND_DIR"
setsid python -m uvicorn main:app \
  --host "$BACKEND_HOST" \
  --port "$BACKEND_PORT" \
  >> "$BACKEND_LOG" 2>&1 < /dev/null &

wait_for_http "http://127.0.0.1:$BACKEND_PORT/" "PPGL backend"

cd "$FRONTEND_DIR"
setsid ./node_modules/.bin/vite \
  --host "$FRONTEND_HOST" \
  --port "$FRONTEND_PORT" \
  >> "$FRONTEND_LOG" 2>&1 < /dev/null &

wait_for_http "http://127.0.0.1:$FRONTEND_PORT/" "PPGL frontend"

echo
echo "All services started."
echo "Jetson local: http://127.0.0.1:$FRONTEND_PORT/"
echo "LAN/Mac:      http://$(hostname -I | awk '{print $1}'):$FRONTEND_PORT/"
echo
echo "Logs:"
echo "- MiniCPM:  $MINICPM_LOG"
echo "- Backend:  $BACKEND_LOG"
echo "- Frontend: $FRONTEND_LOG"
