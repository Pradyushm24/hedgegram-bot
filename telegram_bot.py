#!/usr/bin/env python3
import os
import asyncio
import aiohttp

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ================== INIT ==================
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = str(os.getenv("TELEGRAM_CHAT_ID"))
CONTROL_API_URL = os.getenv("CONTROL_API_URL", "http://127.0.0.1:8000/control")
CONTROL_API_KEY = os.getenv("CONTROL_API_KEY")

if not TOKEN or not ADMIN_CHAT_ID or not CONTROL_API_KEY:
    raise RuntimeError("Missing TELEGRAM or CONTROL API env variables")

# ================== HELPERS ==================
def is_admin(update: Update) -> bool:
    return str(update.effective_chat.id) == ADMIN_CHAT_ID

async def call_api(endpoint: str, method="GET", payload=None):
    headers = {"x-api-key": CONTROL_API_KEY}
    url = f"{CONTROL_API_URL}/{endpoint}"

    async with aiohttp.ClientSession() as session:
        try:
            if method == "POST":
                async with session.post(url, json=payload, headers=headers) as r:
                    return await r.text()
            else:
                async with session.get(url, headers=headers) as r:
                    return await r.text()
        except Exception as e:
            return f"API error: {e}"

# ================== COMMANDS ==================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    res = await call_api("start", "POST")
    await update.message.reply_text(res)

async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    res = await call_api("stop", "POST")
    await update.message.reply_text(res)

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    res = await call_api("status")
    await update.message.reply_text(res)

async def mode_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    if not context.args or context.args[0] not in ("paper", "live"):
        await update.message.reply_text("Usage:\n/mode paper\n/mode live")
        return

    mode = context.args[0]
    res = await call_api("mode", "POST", {"mode": mode})
    await update.message.reply_text(res)

async def totp_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    if not context.args:
        await update.message.reply_text("Usage: /totp 123456")
        return

    code = context.args[0]
    res = await call_api("totp", "POST", {"totp": code})
    await update.message.reply_text(res)

async def panic_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    if not context.args or context.args[0].lower() != "confirm":
        await update.message.reply_text("⚠️ To confirm: /panic confirm")
        return

    res = await call_api("panic", "POST")
    await update.message.reply_text(res)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    await update.message.reply_text(
        "📌 Hedgegram Commands\n\n"
        "/start  → Start bot\n"
        "/stop   → Stop bot\n"
        "/status → Bot status\n"
        "/mode paper → Paper trading\n"
        "/mode live  → Live trading\n"
        "/totp 123456 → Refresh live token\n"
        "/panic confirm → Emergency exit\n"
    )

# ================== RUN ==================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("mode", mode_cmd))
    app.add_handler(CommandHandler("totp", totp_cmd))
    app.add_handler(CommandHandler("panic", panic_cmd))
    app.add_handler(CommandHandler("help", help_cmd))

    print("✅ Telegram bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
