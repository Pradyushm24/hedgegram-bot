#!/usr/bin/env python3
import os
import aiohttp
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = str(os.getenv("TELEGRAM_CHAT_ID"))
CONTROL_API_URL = os.getenv("CONTROL_API_URL", "http://127.0.0.1:8000/control")
CONTROL_API_KEY = os.getenv("CONTROL_API_KEY")

def is_admin(update: Update) -> bool:
    return str(update.effective_chat.id) == ADMIN_CHAT_ID

async def call_api(endpoint, method="GET", payload=None):
    headers = {"x-api-key": CONTROL_API_KEY}
    url = f"{CONTROL_API_URL}/{endpoint}"
    async with aiohttp.ClientSession() as session:
        if method == "POST":
            async with session.post(url, json=payload, headers=headers) as r:
                return await r.text()
        async with session.get(url, headers=headers) as r:
            return await r.text()

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update):
        await update.message.reply_text(await call_api("start", "POST"))

async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update):
        await update.message.reply_text(await call_api("stop", "POST"))

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update):
        await update.message.reply_text(await call_api("status"))

async def mode_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if len(context.args) != 2:
        await update.message.reply_text("Usage:\n/mode paper <PIN>\n/mode live <PIN>")
        return
    mode, pin = context.args
    await update.message.reply_text(
        await call_api("mode", "POST", {"mode": mode, "pin": pin})
    )

async def totp_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update) and context.args:
        await update.message.reply_text(
            await call_api("totp", "POST", {"totp": context.args[0]})
        )

async def panic_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if not context.args or context.args[0].lower() != "confirm":
        await update.message.reply_text("⚠️ To confirm: /panic confirm")
        return
    await update.message.reply_text(await call_api("panic", "POST"))

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update):
        await update.message.reply_text(
            "/start\n/stop\n/status\n/mode paper <PIN>\n/mode live <PIN>\n"
            "/totp 123456\n/panic confirm"
        )

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("mode", mode_cmd))
    app.add_handler(CommandHandler("totp", totp_cmd))
    app.add_handler(CommandHandler("panic", panic_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.run_polling()

if __name__ == "__main__":
    main()
