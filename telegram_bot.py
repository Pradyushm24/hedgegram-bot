#!/usr/bin/env python3
import os
import aiohttp
import json
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

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

async def call_api(endpoint: str):
    headers = {"x-api-key": CONTROL_API_KEY}
    url = f"{CONTROL_API_URL}/{endpoint}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as r:
            return await r.text()

# ================== COMMANDS ==================
async def positions_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    raw = await call_api("status")

    try:
        data = json.loads(raw)
    except Exception:
        await update.message.reply_text("❌ Failed to read position data")
        return

    positions = data.get("positions", [])
    pnl = data.get("pnl", 0)

    if not positions:
        await update.message.reply_text("📭 No open positions")
        return

    msg = "📌 Open Positions\n\n"
    for p in positions:
        msg += (
            f"{p['symbol']}\n"
            f"Qty: {p['qty']} | Avg: {p['avg']}\n"
            f"LTP: {p['ltp']} | PNL: ₹{p['pnl']}\n\n"
        )

    msg += f"💰 Total PNL: ₹{pnl}"
    await update.message.reply_text(msg)

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    raw = await call_api("status")
    await update.message.reply_text(raw)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    headers = {"x-api-key": CONTROL_API_KEY}
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{CONTROL_API_URL}/start", headers=headers) as r:
            await update.message.reply_text(await r.text())

async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    headers = {"x-api-key": CONTROL_API_KEY}
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{CONTROL_API_URL}/stop", headers=headers) as r:
            await update.message.reply_text(await r.text())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await update.message.reply_text(
        "🤖 Hedgegram Commands\n\n"
        "/start → Start bot\n"
        "/stop → Stop bot\n"
        "/status → Bot status\n"
        "/positions → Open positions\n"
        "/help → This message"
    )

# ================== RUN ==================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("positions", positions_cmd))
    app.add_handler(CommandHandler("help", help_cmd))

    print("✅ Telegram bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
