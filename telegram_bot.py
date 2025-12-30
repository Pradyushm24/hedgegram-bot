#!/usr/bin/env python3
import os
import aiohttp
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ================== LOAD ENV ==================
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CONTROL_API_KEY = os.getenv("CONTROL_API_KEY")
API_BASE = os.getenv("CONTROL_API_BASE", "http://127.0.0.1:8000/control")

# ================== HELPERS ==================
async def api_get(endpoint):
    async with aiohttp.ClientSession() as s:
        async with s.get(
            f"{API_BASE}/{endpoint}",
            headers={"x-api-key": CONTROL_API_KEY},
            timeout=10,
        ) as r:
            return await r.json()

async def api_post(endpoint):
    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"{API_BASE}/{endpoint}",
            headers={"x-api-key": CONTROL_API_KEY},
            timeout=10,
        ) as r:
            return await r.json()

def pretty(obj):
    if isinstance(obj, dict):
        return "\n".join(f"{k}: {v}" for k, v in obj.items())
    return str(obj)

# ================== COMMANDS ==================
async def start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    res = await api_post("start")
    await update.message.reply_text(pretty(res))

async def stop_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    res = await api_post("stop")
    await update.message.reply_text(pretty(res))

async def status_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    res = await api_get("status")
    await update.message.reply_text(pretty(res))

async def positions_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    res = await api_get("positions")
    if not res:
        await update.message.reply_text("No positions")
    else:
        await update.message.reply_text(pretty(res))

async def paper_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    res = await api_post("paper")
    await update.message.reply_text("🧪 Mode switched to PAPER")

async def live_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    res = await api_post("live")
    if "error" in res:
        await update.message.reply_text(f"❌ {res['error']}")
    else:
        await update.message.reply_text("🚀 Mode switched to LIVE")

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Hedgegram Commands\n\n"
        "/start – start bot\n"
        "/stop – stop bot\n"
        "/status – current status\n"
        "/positions – open positions\n"
        "/paper – paper mode\n"
        "/live – live mode\n"
        "/help – this message"
    )

# ================== MAIN ==================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("positions", positions_cmd))
    app.add_handler(CommandHandler("paper", paper_cmd))
    app.add_handler(CommandHandler("live", live_cmd))
    app.add_handler(CommandHandler("help", help_cmd))

    print("✅ Telegram bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
