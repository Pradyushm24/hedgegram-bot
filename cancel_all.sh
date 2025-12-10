#!/bin/bash
#
# cancel_all.sh — Safe wrapper around cancel_all.py
#
# Usage:
#   ./cancel_all.sh               # dry run (default)
#   ./cancel_all.sh confirm       # actual cancel (dangerous)
#
# Notes:
# - Loads .env so CONTROL_API_KEY, FLATTRADE_CANCEL_URL etc. are available
# - Logs output into logs/cancel_all.log
# - Ensures cancel_all.py is executable
#

set -e

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$BASE_DIR"

LOG_DIR="$BASE_DIR/logs"
LOG_FILE="$LOG_DIR/cancel_all.log"

mkdir -p "$LOG_DIR"

# Load environment variables (.env)
if [ -f "$BASE_DIR/.env" ]; then
    set -o allexport
    source "$BASE_DIR/.env"
    set +o allexport
fi

# Ensure python script is executable
chmod +x cancel_all.py

ACTION="--dry-run"
if [ "$1" == "confirm" ] || [ "$1" == "--confirm" ]; then
    ACTION="--confirm"
fi

echo "=== CANCEL ALL START ($(date)) ===" | tee -a "$LOG_FILE"

# Run cancel script with python
./cancel_all.py $ACTION 2>&1 | tee -a "$LOG_FILE"

echo "=== CANCEL ALL END ($(date)) ===" | tee -a "$LOG_FILE"
echo
echo "Done. Log saved at: $LOG_FILE"
