#!/usr/bin/env python3
import os, aiohttp, json
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = str(os.getenv("TELEGRAM_CHAT_ID"))
API = os.getenv("CONTROL_API_URL", "http://127.0.0.1:8000/control")
KEY = os.getenv("CONTROL_API_KEY")

def is_admin(update: Update):
    return str(update.effective_chat.id) == ADMIN_CHAT_ID

async def call_api(endpoint):
    headers = {"x-api-key": KEY}
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{API}/{endpoint}", headers=headers) as r:
            return await r.json()

async def positions_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    data = await call_api("positions")

    if not data["positions"]:
        await update.message.reply_text("📭 No open positions")
        return

    msg = "📌 Open Positions\n\n"
    for p in data["positions"]:
        msg += (
            f"{p['symbol']}\n"
            f"Qty: {p['qty']} | Avg: {p['avg']}\n"
            f"LTP: {p['ltp']} | PNL: ₹{p['pnl']}\n\n"
        )

    msg += f"💰 Total PNL: ₹{data['pnl']}"
    await update.message.reply_text(msg)

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("positions", positions_cmd))
    app.run_polling()

if __name__ == "__main__":
    main()
