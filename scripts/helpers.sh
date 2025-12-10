#!/bin/bash
#
# helpers.sh — Shared helper functions used by start.sh, monitor.sh, cancel_all.sh
#

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
ENV_FILE="$ROOT_DIR/.env"

mkdir -p "$LOG_DIR"

# -------------------------------
# Load environment safely
# -------------------------------
load_env() {
  if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC2046
    export $(grep -v '^#' "$ENV_FILE" | xargs)
  else
    echo "[helpers.sh] WARNING: .env file missing at $ENV_FILE"
  fi
}

# -------------------------------
# Logging helpers
# -------------------------------
log_info() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO] $1"
}

log_error() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] $1" >&2
}

rotate_log() {
  local file="$1"
  if [[ -f "$file" ]]; then
    mv "$file" "$file.$(date +%F_%H%M%S)"
  fi
}

# -------------------------------
# Check if a process is running
# -------------------------------
is_running() {
  local name="$1"
  pgrep -f "$name" >/dev/null 2>&1
}

# -------------------------------
# Start a Python script in tmux
# -------------------------------
start_tmux() {
  local session="$1"
  local command="$2"

  if tmux has-session -t "$session" 2>/dev/null; then
    log_info "tmux session '$session' already running."
    return
  fi

  log_info "Starting tmux session: $session"
  tmux new-session -d -s "$session" "$command"
}

# -------------------------------
# Stop tmux session
# -------------------------------
stop_tmux() {
  local session="$1"
  if tmux has-session -t "$session" 2>/dev/null; then
    log_info "Stopping tmux session '$session'"
    tmux kill-session -t "$session"
  fi
}

# -------------------------------
# Health check API
# -------------------------------
check_api() {
  local endpoint="$1"
  curl -s -H "x-api-key: $CONTROL_API_KEY" "http://127.0.0.1:8000/control/$endpoint"
}

# -------------------------------
# Notify via Telegram (admin only)
# -------------------------------
notify_telegram() {
  local message="$1"

  if [[ -z "$TELEGRAM_BOT_TOKEN" ]] || [[ -z "$TELEGRAM_CHAT_ID" ]]; then
    log_error "Telegram env variables missing; cannot send message."
    return
  fi

  curl -s -X POST \
    "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -d chat_id="$TELEGRAM_CHAT_ID" \
    -d text="$message" >/dev/null
}
