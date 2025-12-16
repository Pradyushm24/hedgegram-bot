#!/usr/bin/env python3
import os
import time
import json
import threading
import logging
import hashlib
import datetime
import requests

from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import uvicorn

# ================== INIT ==================
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("hedgegram")

CONTROL_API_KEY = os.getenv("CONTROL_API_KEY")
FLAT_ID = os.getenv("FLATTRADE_CLIENT_ID")
FLAT_SECRET = os.getenv("FLATTRADE_API_SECRET")
LOGIN_URL = os.getenv("FLATTRADE_LOGIN_URL")

TRADE_MODE_PIN = os.getenv("TRADE_MODE_PIN", "0000")

MARGIN_ALERT = int(os.getenv("MARGIN_ALERT", "170000"))
MARGIN_EXIT = int(os.getenv("MARGIN_EXIT", "150000"))

LIVE_AUTH_FILE = "live_auth.json"
TRADE_MODE_FILE = "trade_mode.json"

app = FastAPI(title="Hedgegram Control")

running = False
positions = []
pnl = 0.0
last_error = None
expiry_done = False

# ================== SECURITY ==================
def auth(req: Request):
    if req.headers.get("x-api-key") != CONTROL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True

# ================== TELEGRAM ALERT ==================
def notify(msg: str):
    try:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat:
            return
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": msg},
            timeout=5
        )
    except Exception:
        pass

# ================== TRADE MODE ==================
def get_mode():
    if not os.path.exists(TRADE_MODE_FILE):
        return "paper"
    try:
        return json.load(open(TRADE_MODE_FILE)).get("mode", "paper")
    except Exception:
        return "paper"

def set_mode(mode: str):
    with open(TRADE_MODE_FILE, "w") as f:
        json.dump({"mode": mode}, f)

# ================== LIVE AUTH ==================
def save_live_auth(data: dict):
    tmp = LIVE_AUTH_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, LIVE_AUTH_FILE)
    os.chmod(LIVE_AUTH_FILE, 0o600)

def load_live_auth():
    if not os.path.exists(LIVE_AUTH_FILE):
        return None
    try:
        return json.load(open(LIVE_AUTH_FILE))
    except Exception:
        return None

# ================== MARGIN ==================
def fetch_available_margin():
    # 🔴 Replace with real Flattrade margin API
    return 250000

# ================== PAPER MOCK ==================
def paper_positions():
    return [
        {"symbol": "FINNIFTY", "qty": 40, "avg": 100, "ltp": 110},
        {"symbol": "FINNIFTY", "qty": -40, "avg": 105, "ltp": 100},
    ]

def calc_pnl(pos):
    return round(sum((p["ltp"] - p["avg"]) * p["qty"] for p in pos), 2)

# ================== EXIT ALL ==================
def exit_all(reason: str):
    global running, last_error
    running = False
    last_error = reason
    log.error("BOT STOPPED: %s", reason)
    notify(f"🚨 BOT STOPPED\nReason: {reason}\nAll positions exited")

# ================== STRATEGY LOOP ==================
def strategy():
    global running, positions, pnl

    mode = get_mode()
    notify(f"✅ Bot started in {mode.upper()} mode")
    log.info("Strategy started (%s)", mode)

    while running:
        try:
            if mode == "paper":
                positions = paper_positions()
            else:
                authd = load_live_auth()
                if not authd or "jwtToken" not in authd:
                    raise RuntimeError("Live auth missing / expired")
                positions = []  # 🔴 live fetch later

            pnl = calc_pnl(positions)
            margin = fetch_available_margin()

            log.info("PNL: %s | Margin: %s", pnl, margin)

            if margin <= MARGIN_EXIT:
                exit_all(f"MARGIN CRITICAL ₹{margin}")
                break

            if margin <= MARGIN_ALERT:
                notify(f"⚠️ Margin Low Alert\nAvailable ₹{margin}")

        except Exception as e:
            exit_all(str(e))
            break

        time.sleep(10)

    log.warning("Strategy stopped")

# ================== FINNIFTY MONTHLY EXPIRY ==================
def last_tuesday(year, month):
    if month == 12:
        next_month = datetime.date(year + 1, 1, 1)
    else:
        next_month = datetime.date(year, month + 1, 1)

    last_day = next_month - datetime.timedelta(days=1)
    offset = (last_day.weekday() - 1) % 7  # Tuesday = 1
    return last_day - datetime.timedelta(days=offset)

def expiry_watcher():
    global expiry_done
    while True:
        try:
            if not running:
                expiry_done = False
                time.sleep(30)
                continue

            now = datetime.datetime.now()
            today = now.date()
            expiry = last_tuesday(today.year, today.month)

            if (
                not expiry_done
                and today == expiry
                and now.hour == 14
                and now.minute == 0
            ):
                expiry_done = True
                exit_all("FINNIFTY MONTHLY EXPIRY AUTO EXIT 2PM")

        except Exception as e:
            log.exception("Expiry watcher error")

        time.sleep(30)

# ================== DAILY STATUS ==================
def daily_status():
    while True:
        now = datetime.datetime.now()
        if now.hour == 9 and now.minute == 10:
            notify(
                "📊 Daily Status\n"
                f"Mode: {get_mode().upper()}\n"
                f"Running: {running}\n"
                f"PnL: ₹{pnl}\n"
                f"Margin: ₹{fetch_available_margin()}\n"
                f"Positions: {len(positions)}"
            )
            time.sleep(60)
        time.sleep(30)

threading.Thread(target=expiry_watcher, daemon=True).start()
threading.Thread(target=daily_status, daemon=True).start()

# ================== API ==================
@app.post("/control/start")
def start(_: bool = Depends(auth)):
    global running
    if running:
        return {"status": "already_running"}
    running = True
    threading.Thread(target=strategy, daemon=True).start()
    return {"status": "started"}

@app.post("/control/stop")
def stop(_: bool = Depends(auth)):
    exit_all("Manual stop")
    return {"status": "stopped"}

@app.get("/control/status")
def status(_: bool = Depends(auth)):
    return {
        "mode": get_mode(),
        "running": running,
        "positions": len(positions),
        "pnl": pnl,
        "last_error": last_error,
    }

@app.post("/control/mode")
def mode(payload: dict, _: bool = Depends(auth)):
    m = payload.get("mode")
    pin = payload.get("pin")

    if m not in ("paper", "live"):
        raise HTTPException(400, "Invalid mode")

    if pin != TRADE_MODE_PIN:
        raise HTTPException(403, "Invalid PIN")

    set_mode(m)
    notify(f"⚙️ Trade mode set to {m.upper()}")
    return {"status": "ok", "mode": m}

@app.post("/control/totp")
def totp(payload: dict, _: bool = Depends(auth)):
    code = payload.get("totp")
    if not code:
        raise HTTPException(400, "Missing TOTP")

    pwd = hashlib.sha256((FLAT_ID + code + FLAT_SECRET).encode()).hexdigest()
    r = requests.post(
        LOGIN_URL,
        json={"UserName": FLAT_ID, "totp": code, "password": pwd},
        timeout=15,
    )

    data = r.json()
    if "jwtToken" not in data:
        notify("❌ TOTP login failed")
        return JSONResponse(502, {"error": data})

    save_live_auth(data)
    notify("🔐 Live access token refreshed")
    return {"status": "ok"}

@app.post("/control/panic")
def panic(_: bool = Depends(auth)):
    exit_all("PANIC EXIT (manual)")
    return {"status": "panic_executed"}

# ================== RUN ==================
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
