#!/usr/bin/env bash
set -euo pipefail

CODE_ALL_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$CODE_ALL_DIR/.." && pwd)"
BACKEND_DIR="$CODE_ALL_DIR/backend"
CONDA_ENV="${CONDA_ENV:-ppgl}"

BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
MINICPM_HOST="${MINICPM_HOST:-127.0.0.1}"
MINICPM_PORT="${MINICPM_PORT:-18080}"
OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-ppgl-qwen3-32b-q4:latest}"
OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:--1}"
CURL_BIN="${CURL_BIN:-$(command -v curl)}"

MODE="${1:-backend-only}"

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

BACKEND_LOG="$PPGL_LOG_DIR/uvicorn_backend.log"
MINICPM_LOG="$PPGL_LOG_DIR/local_minicpm_server.log"

JWT_SECRET_VALUE="${PPGL_AUTH_JWT_SECRET:-}"
if [ "$MODE" != "stop" ] && [ "${#JWT_SECRET_VALUE}" -lt 32 ]; then
  echo "PPGL_AUTH_JWT_SECRET must be set to a random value of at least 32 characters." >&2
  exit 1
fi
if [ "$MODE" != "stop" ] && [ -z "${PPGL_INTERNAL_API_KEY:-}" ]; then
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
export PATH="$ENV_PREFIX/bin:$PATH"
export LD_LIBRARY_PATH="$ENV_PREFIX/lib:${LD_LIBRARY_PATH:-}"
export NO_PROXY="127.0.0.1,localhost,${NO_PROXY:-}"
export no_proxy="127.0.0.1,localhost,${no_proxy:-}"

export MINICPM_MODEL_DIR="${MINICPM_MODEL_DIR:-$CODE_ALL_DIR/models/MiniCPM5-1B}"
export CHAT_LLM_PROVIDER="${CHAT_LLM_PROVIDER:-openai_compat}"
export CHAT_OPENAI_BASE_URL="${CHAT_OPENAI_BASE_URL:-http://$OLLAMA_HOST:$OLLAMA_PORT/v1}"
export CHAT_OPENAI_MODEL="${CHAT_OPENAI_MODEL:-$OLLAMA_MODEL}"
export CHAT_OPENAI_API_KEY="${CHAT_OPENAI_API_KEY:-ollama}"
export OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:--1}"
export REPORT_LLM_PROVIDER="${REPORT_LLM_PROVIDER:-openai_compat}"
export REPORT_OPENAI_BASE_URL="${REPORT_OPENAI_BASE_URL:-$CHAT_OPENAI_BASE_URL}"
export REPORT_OPENAI_MODEL="${REPORT_OPENAI_MODEL:-$CHAT_OPENAI_MODEL}"
export REPORT_OPENAI_API_KEY="${REPORT_OPENAI_API_KEY:-$CHAT_OPENAI_API_KEY}"

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
    MODE="with-ollama"
    ;;
  with-chat|with-ollama)
    stop_backend
    stop_minicpm
    stop_frontend
    export CHAT_LLM_PROVIDER="openai_compat"
    export CHAT_OPENAI_BASE_URL="http://$OLLAMA_HOST:$OLLAMA_PORT/v1"
    export CHAT_OPENAI_MODEL="$OLLAMA_MODEL"
    export CHAT_OPENAI_API_KEY="${CHAT_OPENAI_API_KEY:-ollama}"
    export REPORT_LLM_PROVIDER="${REPORT_LLM_PROVIDER:-openai_compat}"
    export REPORT_OPENAI_BASE_URL="${REPORT_OPENAI_BASE_URL:-http://$OLLAMA_HOST:$OLLAMA_PORT/v1}"
    export REPORT_OPENAI_MODEL="${REPORT_OPENAI_MODEL:-$OLLAMA_MODEL}"
    export REPORT_OPENAI_API_KEY="${REPORT_OPENAI_API_KEY:-ollama}"
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
  setsid "$PYTHON_BIN" -m uvicorn local_minicpm_server:app \
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
    setsid ollama serve >> "$PPGL_LOG_DIR/ollama_server.log" 2>&1 < /dev/null &
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
setsid "$PYTHON_BIN" -m uvicorn main:app \
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
echo "- RAG search:         http://$(hostname -I | awk '{print $1}'):$BACKEND_PORT/api/rag/search"
echo "- RAG query:          http://$(hostname -I | awk '{print $1}'):$BACKEND_PORT/api/rag/query"
echo
echo "Logs:"
echo "- Backend: $BACKEND_LOG"
if [ "$MODE" = "with-minicpm" ]; then
  echo "- MiniCPM: $MINICPM_LOG"
fi
if [ "$MODE" = "with-chat" ] || [ "$MODE" = "with-ollama" ]; then
  echo "- Ollama:  $PPGL_LOG_DIR/ollama_server.log"
  echo "- Model:   $OLLAMA_MODEL"
  echo "- Keep-alive: $OLLAMA_KEEP_ALIVE"
fi
