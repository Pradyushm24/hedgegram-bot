#!/usr/bin/env bash
# monitor.sh - show only Hedgegram-relevant log lines in real time
# Usage:
#   ./monitor.sh            # watch main bot log (today)
#   ./monitor.sh main       # same as above
#   ./monitor.sh tg         # watch telegram log (today)
#   ./monitor.sh <path>     # watch a specific log file

set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$BASE_DIR"

# choose which log to watch
MODE="${1:-main}"   # main | tg | <path>
DATE=$(date +%F)

if [ "$MODE" = "main" ]; then
  LOGFILE="$BASE_DIR/logs/bot-main.log"
elif [ "$MODE" = "tg" ]; then
  LOGFILE="$BASE_DIR/logs/bot-telegram.log"
elif [ -f "$MODE" ]; then
  LOGFILE="$MODE"
else
  # fallback to default pattern (compat with older script naming)
  if [ -f "$BASE_DIR/bot-$DATE.log" ]; then
    LOGFILE="$BASE_DIR/bot-$DATE.log"
  elif [ -f "$BASE_DIR/logs/bot-main.log" ]; then
    LOGFILE="$BASE_DIR/logs/bot-main.log"
  else
    echo "Log file not found. Pass 'main', 'tg' or a full path to a log file."
    exit 1
  fi
fi

echo "[monitor.sh] Watching: $LOGFILE"
if [ ! -f "$LOGFILE" ]; then
  echo "Log file does not exist: $LOGFILE"
  exit 1
fi

# Noise patterns to drop (common probes / static assets)
NOISE_RE='GET / HTTP|favicon.ico|robots.txt|/webui/|/geoserver|/containers/json|/api/.env|hello.world|/remote/logincheck|.git/config|/websocket'

# Positive-interest keywords (only these lines will be shown after noise filter)
KEEP_RE='Flattrade|totp|login|live_auth|PNL|PnL|Current PnL|Placed|Order|ERROR|WARN|Exception|login_failed|TOTP exchange|Panic|CancelOrder|live_auth|PlacedOrder|SL hit|Trail|reentry|force_exit|positions|PNL:'

# follow the file with filtering:
#   1) remove noisy lines,
#   2) show only lines that match KEEP_RE (this keeps output focused)
#   3) preserve line buffering for real-time display
tail -n 200 -F "$LOGFILE" 2>/dev/null \
  | grep --line-buffered -v -E "$NOISE_RE" \
  | grep --line-buffered -E "$KEEP_RE" || true
