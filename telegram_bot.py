#!/usr/bin/env python3
"""
telegram_bot.py - Admin Telegram bot for Hedgegram (complete)

Commands (admin only)
 - /totp <code>       -> send TOTP to main.py to generate token
 - /settoken [jwt]    -> save jwtToken (and optional sid) from args OR by replying to a message with token
 - /cleartoken        -> remove saved live_auth.json immediately
 - /start /stop /status /pnl
 - /panic confirm     -> run cancel_all.py --confirm (dangerous)

Notes:
 - live_auth.json is saved with chmod 600
 - bot will try to delete the admin messages containing tokens (best-effort)
 - daily_clear_loop removes live_auth.json at local midnight (Asia/Kolkata)
"""
import os
import sys
import json
import stat
import asyncio
import logging
import datetime
import time
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

import aiohttp
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# -----------------------
# Config / env
# -----------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_ADMIN_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # keep as string/int
CONTROL_API_URL = os.getenv("CONTROL_API_URL", "http://127.0.0.1:8000/control")
CONTROL_API_KEY = os.getenv("CONTROL_API_KEY")
LIVE_AUTH_FILE = "live_auth.json"

# -----------------------
# Logging
# -----------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("telegram_bot")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN not set in env")

# -----------------------
# Helpers
# -----------------------
def is_admin(chat_id) -> bool:
    try:
        return str(chat_id) == str(int(TELEGRAM_ADMIN_CHAT_ID))
    except Exception:
        return str(chat_id) == str(TELEGRAM_ADMIN_CHAT_ID)

def save_live_auth_atomic(jwt_token: str, sid: Optional[str] = None) -> None:
    """Write live_auth.json atomically and set 600 perms."""
    data = {"jwtToken": jwt_token}
    if sid:
        data["sid"] = sid
    tmp = LIVE_AUTH_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, LIVE_AUTH_FILE)
    try:
        os.chmod(LIVE_AUTH_FILE, 0o600)
    except Exception:
        pass

async def call_control(endpoint: str, method="GET", json_payload=None, timeout=15):
    url = CONTROL_API_URL.rstrip("/") + "/" + endpoint.lstrip("/")
    headers = {}
    if CONTROL_API_KEY:
        headers["x-api-key"] = CONTROL_API_KEY
    async with aiohttp.ClientSession() as session:
        try:
            if method.upper() == "GET":
                async with session.get(url, headers=headers, timeout=timeout) as resp:
                    text = await resp.text()
                    return resp.status, text
            else:
                async with session.post(url, json=json_payload, headers=headers, timeout=timeout) as resp:
                    text = await resp.text()
                    return resp.status, text
        except Exception as e:
            return 500, str(e)

# -----------------------
# Background: daily clear
# -----------------------
async def daily_clear_loop():
    """
    Clear live_auth.json daily at local midnight (Asia/Kolkata).
    This assumes server clock is IST or close; it computes next local midnight.
    """
    while True:
        try:
            now = datetime.datetime.now()
            tomorrow = now.date() + datetime.timedelta(days=1)
            next_midnight = datetime.datetime.combine(tomorrow, datetime.time.min)
            wait_seconds = (next_midnight - now).total_seconds()
            if wait_seconds <= 0:
                wait_seconds = 60
            await asyncio.sleep(wait_seconds)
            try:
                if os.path.exists(LIVE_AUTH_FILE):
                    os.remove(LIVE_AUTH_FILE)
                    logger.info("daily_clear_loop: removed live_auth.json at midnight")
            except Exception as e:
                logger.exception("daily_clear_loop error: %s", e)
        except Exception:
            logger.exception("daily_clear_loop outer error")
            await asyncio.sleep(60)

# -----------------------
# Command handlers
# -----------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id):
        await update.message.reply_text("Unauthorized.")
        return
    status, text = await call_control("start", method="POST")
    await update.message.reply_text(f"Start: {status} {text}")

async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id):
        await update.message.reply_text("Unauthorized.")
        return
    status, text = await call_control("stop", method="POST")
    await update.message.reply_text(f"Stop: {status} {text}")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id):
        await update.message.reply_text("Unauthorized.")
        return
    status, text = await call_control("status", method="GET")
    await update.message.reply_text(f"Status: {status}\n{text}")

async def pnl_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id):
        await update.message.reply_text("Unauthorized.")
        return
    status, text = await call_control("pnl", method="GET")
    await update.message.reply_text(f"PNL: {status}\n{text}")

async def totp_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id):
        await update.message.reply_text("Unauthorized.")
        return
    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: /totp <6-digit-code>")
        return
    totp = args[0].strip()
    if not totp.isdigit():
        await update.message.reply_text("TOTP must be numeric.")
        return

    await update.message.reply_text("Sending TOTP to server (admin-only).")
    status, text = await call_control("totp", method="POST", json_payload={"totp": totp})
    try:
        parsed = json.loads(text)
        await update.message.reply_text(f"TOTP exchange: {status}\n{parsed}")
    except Exception:
        await update.message.reply_text(f"TOTP exchange: {status}\n{text}")

async def panic_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id):
        await update.message.reply_text("Unauthorized.")
        return
    args = context.args or []
    if "confirm" not in [a.lower() for a in args]:
        await update.message.reply_text("Panic is destructive. To execute: /panic confirm")
        return

    await update.message.reply_text("Panic confirmed. Running cancel_all.py --confirm ... (this may take a while)")
    python_exe = sys.executable or "python3"
    proc = await asyncio.create_subprocess_exec(
        python_exe, "cancel_all.py", "--confirm",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    out = stdout.decode(errors="replace").strip()
    err = stderr.decode(errors="replace").strip()
    reply = f"Panic finished (exit {proc.returncode})\n\nStdout:\n{out[:3000]}\n\nStderr:\n{err[:2000]}"
    await update.message.reply_text(reply)

# -----------------------
# New: settoken / cleartoken
# -----------------------
async def settoken(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save access token (jwt) to live_auth.json.
    Usage: /settoken <jwt> [sid]
    Or: reply to a message that contains the token and run /settoken
    """
    if not is_admin(update.effective_chat.id):
        await update.message.reply_text("Unauthorized.")
        return

    args = context.args or []
    jwt = None
    sid = None

    # If replying to a message, prefer that text
    if update.message.reply_to_message and update.message.reply_to_message.text:
        reply_text = update.message.reply_to_message.text.strip()
        parts = reply_text.split()
        jwt = parts[0] if len(parts) >= 1 else None
        sid = parts[1] if len(parts) >= 2 else None
    elif len(args) >= 1:
        jwt = args[0].strip()
        if len(args) >= 2:
            sid = args[1].strip()

    if not jwt:
        await update.message.reply_text("Usage: /settoken <jwtToken> [sid]\nOr reply to a message that contains the token and run /settoken")
        return

    # Save safely
    try:
        save_live_auth_atomic(jwt, sid)
    except Exception as e:
        await update.message.reply_text(f"Failed to save token: {e}")
        return

    # Try to delete the original messages (best-effort)
    deleted_cmd = False
    deleted_original = False
    try:
        # delete the /settoken command message
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
        deleted_cmd = True
    except Exception:
        deleted_cmd = False

    try:
        if update.message.reply_to_message:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.reply_to_message.message_id)
            deleted_original = True
    except Exception:
        deleted_original = False

    # Send minimal confirmation and auto-delete it
    confirm_msg = "✅ Access token saved to server (live_auth.json)."
    if deleted_cmd and (not update.message.reply_to_message or deleted_original):
        confirm_msg += " Your messages were deleted from chat."
    else:
        confirm_msg += " Please delete your messages in this chat to remove traces."

    sent = await context.bot.send_message(chat_id=update.effective_chat.id, text=confirm_msg)
    # try to remove confirmation after short delay
    try:
        await asyncio.sleep(10)
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=sent.message_id)
    except Exception:
        pass

async def cleartoken(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id):
        await update.message.reply_text("Unauthorized.")
        return
    if os.path.exists(LIVE_AUTH_FILE):
        try:
            os.remove(LIVE_AUTH_FILE)
            await update.message.reply_text("✅ live_auth.json removed.")
        except Exception as e:
            await update.message.reply_text(f"Failed to remove file: {e}")
    else:
        await update.message.reply_text("No live_auth.json found.")

# -----------------------
# Setup & run
# -----------------------
def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # register handlers
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("pnl", pnl_cmd))
    app.add_handler(CommandHandler("totp", totp_cmd))
    app.add_handler(CommandHandler("panic", panic_cmd))
    app.add_handler(CommandHandler("settoken", settoken))
    app.add_handler(CommandHandler("cleartoken", cleartoken))

    logger.info("Starting Telegram bot")

    # start daily clear in background
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(daily_clear_loop())
    except Exception:
        pass

    app.run_polling()

if __name__ == "__main__":
    main()
