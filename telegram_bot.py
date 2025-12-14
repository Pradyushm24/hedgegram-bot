#!/usr/bin/env python3
import os, asyncio, aiohttp
from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, CommandHandler

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN = str(os.getenv("TELEGRAM_CHAT_ID"))
API = os.getenv("CONTROL_API_URL")
KEY = os.getenv("CONTROL_API_KEY")

def is_admin(update):
    return str(update.effective_chat.id) == ADMIN

async def call(endpoint, method="GET", data=None):
    headers = {"x-api-key": KEY}
    async with aiohttp.ClientSession() as s:
        if method == "POST":
            async with s.post(f"{API}/{endpoint}", json=data, headers=headers) as r:
                return await r.text()
        async with s.get(f"{API}/{endpoint}", headers=headers) as r:
            return await r.text()

async def start(u, c):
    if not is_admin(u): return
    await u.message.reply_text(await call("start","POST"))

async def stop(u,c):
    if not is_admin(u): return
    await u.message.reply_text(await call("stop","POST"))

async def status(u,c):
    if not is_admin(u): return
    await u.message.reply_text(await call("status"))

async def totp(u,c):
    if not is_admin(u): return
    if not c.args: return
    await u.message.reply_text(await call("totp","POST",{"totp":c.args[0]}))

async def panic(u,c):
    if not is_admin(u): return
    await u.message.reply_text(await call("panic","POST"))

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start",start))
app.add_handler(CommandHandler("stop",stop))
app.add_handler(CommandHandler("status",status))
app.add_handler(CommandHandler("totp",totp))
app.add_handler(CommandHandler("panic",panic))
app.run_polling()
