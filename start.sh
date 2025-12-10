#!/bin/bash
#
# start.sh — Launch Hedgegram main engine + telegram bot in tmux
#

set -e

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$BASE_DIR"

LOG_DIR="$BASE_DIR/logs"
mkdir -p "$LOG_DIR"

MAIN_LOG="$LOG_DIR/bot-main.log"
TG_LOG="$LOG_DIR/bot-telegram.log"

MAIN_SESSION="hedgegram_main"
TG_SESSION="hedgegram_telegram"

# -------------------------------
# Load .env
# -------------------------------
if [ -f "$BASE_DIR/.env" ]; then
    echo "[start.sh] Loading .env ..."
    set -o allexport
    source "$BASE_DIR/.env"
    set +o allexport
fi

# -------------------------------
# Virtual environment
# -------------------------------
if [ ! -d "venv" ]; then
    echo "[start.sh] No venv found — creating ..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install requirements (safe, idempotent)
if [ -f requirements.txt ]; then
    echo "[start.sh] Installing requirements ..."
    pip install --quiet -r requirements.txt
fi

# Ensure python files are executable
chmod +x main.py telegram_bot.py cancel_all.py || true

# -------------------------------
# Start main.py in tmux
# -------------------------------
if tmux has-session -t "$MAIN_SESSION" 2>/dev/null; then
    echo "[start.sh] Main session already running: $MAIN_SESSION"
else
    echo "[start.sh] Starting MAIN bot in tmux ($MAIN_SESSION)..."
    tmux new-session -d -s "$MAIN_SESSION" \
        "cd $BASE_DIR && source venv/bin/activate && python3 main.py >> $MAIN_LOG 2>&1"
fi

# -------------------------------
# Start telegram_bot.py in tmux
# -------------------------------
if tmux has-session -t "$TG_SESSION" 2>/dev/null; then
    echo "[start.sh] Telegram session already running: $TG_SESSION"
else
    echo "[start.sh] Starting TELEGRAM bot in tmux ($TG_SESSION)..."
    tmux new-session -d -s "$TG_SESSION" \
        "cd $BASE_DIR && source venv/bin/activate && python3 telegram_bot.py >> $TG_LOG 2>&1"
fi

echo
echo "============================"
echo "  Hedgegram Bot Started"
echo "============================"
echo "Main logs:      $MAIN_LOG"
echo "Telegram logs:  $TG_LOG"
echo
echo "Attach: tmux attach -t $MAIN_SESSION"
echo "Attach: tmux attach -t $TG_SESSION"
