#!/usr/bin/env bash
set -euo pipefail

CODE_ALL_DIR="/path/to/PPGL/Code_ALL"
BACKEND_DIR="$CODE_ALL_DIR/backend"
CONDA_SH="/path/to/anaconda3/etc/profile.d/conda.sh"
CONDA_ENV="ppgl-gpu38"

BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
MINICPM_HOST="${MINICPM_HOST:-127.0.0.1}"
MINICPM_PORT="${MINICPM_PORT:-18080}"
OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3.5:9b}"
OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:--1}"

BACKEND_LOG="$BACKEND_DIR/uvicorn_backend.log"
MINICPM_LOG="$BACKEND_DIR/local_minicpm_server.log"
CURL_BIN="/usr/bin/curl"

MODE="${1:-backend-only}"

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

export PATH="/path/to/anaconda3/envs/$CONDA_ENV/bin:$PATH"
export LD_LIBRARY_PATH="/path/to/anaconda3/envs/$CONDA_ENV/lib:${LD_LIBRARY_PATH:-}"
export NO_PROXY="127.0.0.1,localhost,${NO_PROXY:-}"
export no_proxy="127.0.0.1,localhost,${no_proxy:-}"

export MINICPM_MODEL_DIR="${MINICPM_MODEL_DIR:-$CODE_ALL_DIR/models/MiniCPM5-1B}"
export CHAT_LLM_PROVIDER="${CHAT_LLM_PROVIDER:-openai_compat}"
export CHAT_OPENAI_BASE_URL="${CHAT_OPENAI_BASE_URL:-http://127.0.0.1:$MINICPM_PORT/v1}"
export CHAT_OPENAI_MODEL="${CHAT_OPENAI_MODEL:-MiniCPM5-1B}"
export CHAT_OPENAI_API_KEY="${CHAT_OPENAI_API_KEY:-EMPTY}"
export OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:--1}"

stop_backend() {
  pkill -f "uvicorn main:app" 2>/dev/null || true
}

stop_minicpm() {
  pkill -f "uvicorn local_minicpm_server:app" 2>/dev/null || true
}

stop_frontend() {
  pkill -f "vite --host" 2>/dev/null || true
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
  echo "Preloading Ollama model: $OLLAMA_MODEL (keep_alive=$OLLAMA_KEEP_ALIVE)"
  env -u LD_LIBRARY_PATH "$CURL_BIN" -fsS --noproxy "*" --max-time 180 \
    "http://$OLLAMA_HOST:$OLLAMA_PORT/api/chat" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"$OLLAMA_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}],\"stream\":false,\"think\":false,\"keep_alive\":$keep_alive_json,\"options\":{\"num_predict\":1,\"temperature\":0}}" \
    >/dev/null
  echo "Ollama model preloaded: $OLLAMA_MODEL"
}

unload_ollama_model() {
  if env -u LD_LIBRARY_PATH "$CURL_BIN" -fsS --noproxy "*" --max-time 2 \
    "http://$OLLAMA_HOST:$OLLAMA_PORT/api/tags" >/dev/null 2>&1; then
    env -u LD_LIBRARY_PATH "$CURL_BIN" -fsS --noproxy "*" --max-time 30 \
      "http://$OLLAMA_HOST:$OLLAMA_PORT/api/generate" \
      -H "Content-Type: application/json" \
      -d "{\"model\":\"$OLLAMA_MODEL\",\"keep_alive\":0}" \
      >/dev/null 2>&1 || true
    echo "Ollama model unloaded: $OLLAMA_MODEL"
  fi
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

case "$MODE" in
  backend-only)
    stop_backend
    stop_minicpm
    stop_frontend
    ;;
  with-chat|with-ollama)
    stop_backend
    stop_minicpm
    stop_frontend
    export CHAT_LLM_PROVIDER="openai_compat"
    export CHAT_OPENAI_BASE_URL="http://$OLLAMA_HOST:$OLLAMA_PORT/v1"
    export CHAT_OPENAI_MODEL="$OLLAMA_MODEL"
    export CHAT_OPENAI_API_KEY="${CHAT_OPENAI_API_KEY:-ollama}"
    ;;
  with-minicpm)
    stop_backend
    stop_minicpm
    stop_frontend
    ;;
  stop)
    unload_ollama_model
    stop_backend
    stop_minicpm
    stop_frontend
    echo "PPGL node services stopped."
    exit 0
    ;;
  *)
    echo "Usage: $0 [backend-only|with-chat|with-ollama|with-minicpm|stop]" >&2
    exit 2
    ;;
esac

sleep 1

if [ "$MODE" = "with-minicpm" ]; then
  cd "$BACKEND_DIR"
  setsid python -m uvicorn local_minicpm_server:app \
    --host "$MINICPM_HOST" \
    --port "$MINICPM_PORT" \
    >> "$MINICPM_LOG" 2>&1 < /dev/null &
  echo "Local MiniCPM starting: http://$MINICPM_HOST:$MINICPM_PORT/health"
fi

if [ "$MODE" = "with-chat" ] || [ "$MODE" = "with-ollama" ]; then
  if ! command -v ollama >/dev/null 2>&1; then
    echo "ollama command not found. Install Ollama first, then rerun this command." >&2
    exit 1
  fi
  if ! env -u LD_LIBRARY_PATH "$CURL_BIN" -fsS --noproxy "*" --max-time 2 \
    "http://$OLLAMA_HOST:$OLLAMA_PORT/api/tags" >/dev/null 2>&1; then
    setsid ollama serve >> "$BACKEND_DIR/ollama_server.log" 2>&1 < /dev/null &
    echo "Ollama starting: http://$OLLAMA_HOST:$OLLAMA_PORT"
    wait_for_http "http://$OLLAMA_HOST:$OLLAMA_PORT/api/tags" "Ollama" 30
  fi
  if ! ollama list | awk '{print $1}' | grep -qx "$OLLAMA_MODEL"; then
    echo "Ollama model not found locally: $OLLAMA_MODEL" >&2
    echo "Run: ollama pull $OLLAMA_MODEL" >&2
    exit 1
  fi
  preload_ollama_model
fi

cd "$BACKEND_DIR"
setsid python -m uvicorn main:app \
  --host "$BACKEND_HOST" \
  --port "$BACKEND_PORT" \
  >> "$BACKEND_LOG" 2>&1 < /dev/null &

wait_for_http "http://127.0.0.1:$BACKEND_PORT/" "PPGL backend"

echo
echo "PPGL node started in mode: $MODE"
echo "External Web base URL: http://$(hostname -I | awk '{print $1}'):$BACKEND_PORT"
echo
echo "Useful endpoints:"
echo "- Pipeline/API:       http://$(hostname -I | awk '{print $1}'):$BACKEND_PORT"
echo "- Streaming chat:     http://$(hostname -I | awk '{print $1}'):$BACKEND_PORT/api/llm/chat/stream"
echo
echo "Logs:"
echo "- Backend: $BACKEND_LOG"
if [ "$MODE" = "with-minicpm" ]; then
  echo "- MiniCPM: $MINICPM_LOG"
fi
if [ "$MODE" = "with-chat" ] || [ "$MODE" = "with-ollama" ]; then
  echo "- Ollama:  $BACKEND_DIR/ollama_server.log"
  echo "- Model:   $OLLAMA_MODEL"
  echo "- Keep-alive: $OLLAMA_KEEP_ALIVE"
fi
