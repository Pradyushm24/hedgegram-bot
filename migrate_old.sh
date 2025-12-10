#!/usr/bin/env bash
# migrate_old.sh - migrate legacy hedgegram folder into new structured repo
#
# Usage:
#   ./migrate_old.sh /old/vps/folder/path
#
# What it does:
#   ✓ Detects old files (main.py, telegram_bot.py, config.json, .env, logs…)
#   ✓ Copies them into new structure WITHOUT overwriting existing files
#   ✓ Creates backup copies automatically
#   ✓ Ensures correct dirs: logs/, scripts/, examples/
#
# Safe: nothing destructive, no deletes.

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <old_hedgegram_folder>"
    exit 1
fi

OLD_DIR="$1"
NEW_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Hedgegram Migration Tool ==="
echo "Old folder: $OLD_DIR"
echo "New repo : $NEW_DIR"
echo

# --- Ensure directories exist ---
mkdir -p "$NEW_DIR/logs"
mkdir -p "$NEW_DIR/scripts"
mkdir -p "$NEW_DIR/examples"
mkdir -p "$NEW_DIR/backups"

timestamp=$(date +%F_%H-%M-%S)

copy_safe() {
    src="$1"
    dst="$2"

    if [ ! -f "$src" ]; then
        echo "SKIP: $src not found"
        return
    fi

    if [ -f "$dst" ]; then
        echo "BACKUP: $dst → backups/${dst##*/}.$timestamp.bak"
        cp "$dst" "$NEW_DIR/backups/${dst##*/}.$timestamp.bak"
    fi

    echo "COPY: $src → $dst"
    cp "$src" "$dst"
}

echo "Migrating main files..."
copy_safe "$OLD_DIR/main.py"          "$NEW_DIR/main.py"
copy_safe "$OLD_DIR/telegram_bot.py"  "$NEW_DIR/telegram_bot.py"
copy_safe "$OLD_DIR/cancel_all.py"    "$NEW_DIR/cancel_all.py"

echo
echo "Migrating config files..."
copy_safe "$OLD_DIR/config.json"      "$NEW_DIR/config.json"
copy_safe "$OLD_DIR/.env"             "$NEW_DIR/.env"

echo
echo "Migrating optional shell scripts..."
copy_safe "$OLD_DIR/start.sh"         "$NEW_DIR/start.sh"
copy_safe "$OLD_DIR/monitor.sh"       "$NEW_DIR/monitor.sh"
copy_safe "$OLD_DIR/cancel_all.sh"    "$NEW_DIR/cancel_all.sh"

echo
echo "Migrating logs..."
for f in "$OLD_DIR"/*.log; do
    if [ -f "$f" ]; then
        echo "COPY LOG: $f → logs/"
        cp "$f" "$NEW_DIR/logs/"
    fi
done

echo
echo "Migrating callback/example configs if exist..."
copy_safe "$OLD_DIR/flattrade_code.json" "$NEW_DIR/examples/flattrade_code.example.json"

echo
echo "Migration complete!"
echo "Backups saved in: $NEW_DIR/backups/"
echo "Logs saved in   : $NEW_DIR/logs/"
echo
echo "Now review your .env manually before running:"
echo "  nano .env"
echo
echo "Start services with:"
echo "  ./start.sh"
