#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
CODE_ALL_DIR="$PROJECT_ROOT/ai-backend"
BACKEND_DIR="$CODE_ALL_DIR/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend-vue-prototype"
CONDA_ENV="${CONDA_ENV:-ppgl}"

OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-ppgl-qwen3-32b-q4:latest}"
OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:--1}"
BACKEND_HOST="${PPGL_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="8000"
FRONTEND_HOST="0.0.0.0"
FRONTEND_PORT="5173"
CURL_BIN="${CURL_BIN:-$(command -v curl)}"

if [ -f "$PROJECT_ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$PROJECT_ROOT/.env"
  set +a
fi

if [ -f "$CODE_ALL_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$CODE_ALL_DIR/.env"
  set +a
fi

PPGL_DATA_ROOT="${PPGL_DATA_ROOT:-$HOME/ppgl-assist-data}"
PPGL_LOG_DIR="${PPGL_LOG_DIR:-$PPGL_DATA_ROOT/logs}"
mkdir -p "$PPGL_LOG_DIR" "$PPGL_DATA_ROOT/cases" "$PPGL_DATA_ROOT/rag-documents" "$PPGL_DATA_ROOT/rag-index" "$PPGL_DATA_ROOT/rag-parsed"
export PPGL_DATA_ROOT

OLLAMA_LOG="$PPGL_LOG_DIR/ollama_server.log"
BACKEND_LOG="$PPGL_LOG_DIR/uvicorn_backend.log"
FRONTEND_LOG="$PPGL_LOG_DIR/frontend_vite.log"
BACKEND_PID_FILE="$PPGL_LOG_DIR/uvicorn_backend.pid"

JWT_SECRET_VALUE="${PPGL_AUTH_JWT_SECRET:-}"
if [ "${#JWT_SECRET_VALUE}" -lt 32 ]; then
  echo "PPGL_AUTH_JWT_SECRET must be set to a random value of at least 32 characters." >&2
  exit 1
fi
if [ -z "${PPGL_INTERNAL_API_KEY:-}" ]; then
  echo "PPGL_INTERNAL_API_KEY must be set." >&2
  exit 1
fi
export PPGL_AUTH_JWT_SECRET="$JWT_SECRET_VALUE"
export PPGL_INTERNAL_API_KEY

if command -v conda >/dev/null 2>&1; then
  CONDA_SH="$(conda info --base)/etc/profile.d/conda.sh"
  if [ -f "$CONDA_SH" ]; then
    # shellcheck disable=SC1090
    source "$CONDA_SH"
    conda activate "$CONDA_ENV"
  fi
fi

PYTHON_BIN="$(command -v python)"
ENV_PREFIX="$($PYTHON_BIN -c 'import sys; print(sys.prefix)')"

export CHAT_LLM_PROVIDER="${CHAT_LLM_PROVIDER:-openai_compat}"
export CHAT_OPENAI_BASE_URL="${CHAT_OPENAI_BASE_URL:-http://$OLLAMA_HOST:$OLLAMA_PORT/v1}"
export CHAT_OPENAI_MODEL="${CHAT_OPENAI_MODEL:-$OLLAMA_MODEL}"
export CHAT_OPENAI_API_KEY="${CHAT_OPENAI_API_KEY:-ollama}"

export REPORT_LLM_PROVIDER="${REPORT_LLM_PROVIDER:-openai_compat}"
export REPORT_OPENAI_BASE_URL="${REPORT_OPENAI_BASE_URL:-$CHAT_OPENAI_BASE_URL}"
export REPORT_OPENAI_MODEL="${REPORT_OPENAI_MODEL:-$CHAT_OPENAI_MODEL}"
export REPORT_OPENAI_API_KEY="${REPORT_OPENAI_API_KEY:-$CHAT_OPENAI_API_KEY}"
export REPORT_OPENAI_REASONING_EFFORT="${REPORT_OPENAI_REASONING_EFFORT:-}"
export OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:--1}"

export PATH="$ENV_PREFIX/bin:$PATH"
export LD_LIBRARY_PATH="$ENV_PREFIX/lib:${LD_LIBRARY_PATH:-}"
export NO_PROXY="127.0.0.1,localhost,${NO_PROXY:-}"
export no_proxy="127.0.0.1,localhost,${no_proxy:-}"

stop_existing() {
  pkill -f "uvicorn local_minicpm_server:app" 2>/dev/null || true
  if [ -f "$BACKEND_PID_FILE" ]; then
    backend_pid="$(tr -dc '0-9' < "$BACKEND_PID_FILE")"
    if [ -n "$backend_pid" ] && kill -0 "$backend_pid" 2>/dev/null; then
      # The backend is started with setsid below. Stopping its process group also
      # terminates an in-flight segmentation subprocess before queue recovery.
      kill -TERM -- "-$backend_pid" 2>/dev/null || kill -TERM "$backend_pid" 2>/dev/null || true
      for _ in $(seq 1 30); do
        kill -0 "$backend_pid" 2>/dev/null || break
        sleep 1
      done
    fi
    rm -f "$BACKEND_PID_FILE"
  else
    # Compatibility fallback for a backend started before PID tracking was added.
    pkill -f "uvicorn main:app" 2>/dev/null || true
  fi
  pkill -f "vite --host $FRONTEND_HOST --port $FRONTEND_PORT" 2>/dev/null || true
  sleep 1
}

wait_for_http() {
  local url="$1"
  local name="$2"
  local max_attempts="${3:-60}"
  local attempt
  for attempt in $(seq 1 "$max_attempts"); do
    if env -u LD_LIBRARY_PATH "$CURL_BIN" -fsS --noproxy "*" --max-time 2 "$url" >/dev/null 2>&1; then
      echo "$name started: $url"
      return 0
    fi
    sleep 1
  done
  echo "$name failed to start: $url" >&2
  return 1
}

ollama_keep_alive_json() {
  if [[ "$OLLAMA_KEEP_ALIVE" =~ ^-?[0-9]+$ ]]; then
    printf '%s' "$OLLAMA_KEEP_ALIVE"
  else
    printf '"%s"' "$OLLAMA_KEEP_ALIVE"
  fi
}

preload_ollama_model() {
  local keep_alive_json
  keep_alive_json="$(ollama_keep_alive_json)"
  echo "Preloading Ollama model: $OLLAMA_MODEL"
  env -u LD_LIBRARY_PATH "$CURL_BIN" -fsS --noproxy "*" --max-time 180 \
    "http://$OLLAMA_HOST:$OLLAMA_PORT/api/chat" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"$OLLAMA_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}],\"stream\":false,\"think\":false,\"keep_alive\":$keep_alive_json,\"options\":{\"num_predict\":1,\"temperature\":0}}" \
    >/dev/null
}

stop_existing

if ! command -v ollama >/dev/null 2>&1; then
  echo "ollama command not found. Install Ollama first." >&2
  exit 1
fi
if ! env -u LD_LIBRARY_PATH "$CURL_BIN" -fsS --noproxy "*" --max-time 2 \
  "http://$OLLAMA_HOST:$OLLAMA_PORT/api/tags" >/dev/null 2>&1; then
  setsid ollama serve >> "$OLLAMA_LOG" 2>&1 < /dev/null &
  echo "Ollama starting: http://$OLLAMA_HOST:$OLLAMA_PORT"
  wait_for_http "http://$OLLAMA_HOST:$OLLAMA_PORT/api/tags" "Ollama" 30
fi
if ! ollama list | awk '{print $1}' | grep -qx "$OLLAMA_MODEL"; then
  echo "Ollama model not found locally: $OLLAMA_MODEL" >&2
  echo "Run: ollama pull $OLLAMA_MODEL" >&2
  exit 1
fi
preload_ollama_model

cd "$BACKEND_DIR"
setsid "$PYTHON_BIN" -m uvicorn main:app \
  --host "$BACKEND_HOST" \
  --port "$BACKEND_PORT" \
  >> "$BACKEND_LOG" 2>&1 < /dev/null &
echo "$!" > "$BACKEND_PID_FILE"

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
echo "- Ollama:   $OLLAMA_LOG"
echo "- Model:    $OLLAMA_MODEL"
echo "- Backend:  $BACKEND_LOG"
echo "- Frontend: $FRONTEND_LOG"
