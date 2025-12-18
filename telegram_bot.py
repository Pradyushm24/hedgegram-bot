#!/usr/bin/env python3
import os
import aiohttp
from dotenv import load_dotenv
load_dotenv(os.getenv("ENV_FILE", ".env"))
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ================== INIT ==================
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = str(os.getenv("TELEGRAM_CHAT_ID"))
CONTROL_API_URL = os.getenv("CONTROL_API_URL", "http://127.0.0.1:8000/control")
CONTROL_API_KEY = os.getenv("CONTROL_API_KEY")

# ================== HELPERS ==================
def is_admin(update: Update) -> bool:
    return str(update.effective_chat.id) == ADMIN_CHAT_ID

async def api_get(endpoint: str):
    headers = {"x-api-key": CONTROL_API_KEY}
    url = f"{CONTROL_API_URL}/{endpoint}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as r:
            return await r.json()

async def api_post(endpoint: str, payload=None):
    headers = {"x-api-key": CONTROL_API_KEY}
    url = f"{CONTROL_API_URL}/{endpoint}"

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as r:
            return await r.json()

# ================== COMMANDS ==================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    res = await api_post("start")
    await update.message.reply_text(str(res))

async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    res = await api_post("stop")
    await update.message.reply_text(str(res))

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    res = await api_get("status")
    await update.message.reply_text(str(res))

async def positions_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    data = await api_get("positions")

    positions = data.get("positions", [])
    pnl = data.get("pnl", 0)

    if not positions:
        await update.message.reply_text("📭 No open positions")
        return

    msg = "📌 *Open Positions*\n\n"
    for p in positions:
        msg += (
            f"*{p['symbol']}*\n"
            f"Qty: {p['qty']} | Avg: {p['avg']}\n"
            f"LTP: {p['ltp']} | PNL: ₹{p['pnl']}\n\n"
        )

    msg += f"💰 *Total PNL:* ₹{pnl}"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def mode_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    if len(context.args) != 2:
        await update.message.reply_text("Usage:\n/mode paper <PIN>\n/mode live <PIN>")
        return

    mode, pin = context.args
    res = await api_post("mode", {"mode": mode, "pin": pin})
    await update.message.reply_text(str(res))

async def totp_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    if not context.args:
        await update.message.reply_text("Usage: /totp 123456")
        return

    res = await api_post("totp", {"totp": context.args[0]})
    await update.message.reply_text(str(res))

async def panic_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    if not context.args or context.args[0].lower() != "confirm":
        await update.message.reply_text("⚠️ To confirm: /panic confirm")
        return

    res = await api_post("panic")
    await update.message.reply_text(str(res))

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    await update.message.reply_text(
        "🤖 Hedgegram Commands\n\n"
        "/start\n"
        "/stop\n"
        "/status\n"
        "/positions\n"
        "/mode paper <PIN>\n"
        "/mode live <PIN>\n"
        "/totp 123456\n"
        "/panic confirm\n"
    )

# ================== RUN ==================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("positions", positions_cmd))
    app.add_handler(CommandHandler("mode", mode_cmd))
    app.add_handler(CommandHandler("totp", totp_cmd))
    app.add_handler(CommandHandler("panic", panic_cmd))
    app.add_handler(CommandHandler("help", help_cmd))

    print("✅ Telegram bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
