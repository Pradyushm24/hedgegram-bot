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

FLAT_ID     = os.getenv("FLATTRADE_CLIENT_ID")
FLAT_SECRET = os.getenv("FLATTRADE_API_SECRET")
LOGIN_URL   = os.getenv("FLATTRADE_LOGIN_URL")

TRADE_MODE_PIN = os.getenv("TRADE_MODE_PIN", "0000")

MARGIN_ALERT = int(os.getenv("MARGIN_ALERT", "170000"))
MARGIN_EXIT  = int(os.getenv("MARGIN_EXIT",  "150000"))

LIVE_AUTH_FILE  = "live_auth.json"
TRADE_MODE_FILE = "trade_mode.json"
PAPER_POS_FILE  = "paper_positions.json"

app = FastAPI(title="Hedgegram Control")

running     = False
positions   = []
pnl         = 0.0
last_error  = None
expiry_done = False

# ================== SECURITY ==================
def auth(req: Request):
    if req.headers.get("x-api-key") != CONTROL_API_KEY:
        raise HTTPException(401, "Invalid API key")
    return True

# ================== TELEGRAM ALERT ==================
def notify(msg: str):
    try:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat  = os.getenv("TELEGRAM_CHAT_ID")
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
    return json.load(open(TRADE_MODE_FILE)).get("mode", "paper")

def set_mode(mode: str):
    json.dump({"mode": mode}, open(TRADE_MODE_FILE, "w"))

# ================== LIVE AUTH ==================
def load_live_auth():
    if not os.path.exists(LIVE_AUTH_FILE):
        return None
    return json.load(open(LIVE_AUTH_FILE))

# ================== REAL MARKET DATA ==================
def fetch_ltp(symbol: str) -> float:
    """
    REAL LTP for BOTH paper & live
    """
    auth = load_live_auth()
    if not auth or "jwtToken" not in auth:
        raise RuntimeError("Live auth missing for LTP")

    headers = {
        "Authorization": f"Bearer {auth['jwtToken']}",
        "Content-Type": "application/json"
    }

    payload = {
        "symbols": [symbol]
    }

    r = requests.post(
        "https://api.flattrade.in/market/ltp",
        headers=headers,
        json=payload,
        timeout=5
    )

    data = r.json()
    return float(data[symbol]["ltp"])

# ================== PAPER ENGINE ==================
def load_paper_positions():
    if not os.path.exists(PAPER_POS_FILE):
        return []
    return json.load(open(PAPER_POS_FILE))

def save_paper_positions(pos):
    json.dump(pos, open(PAPER_POS_FILE, "w"))

# ================== POSITION + PNL ==================
def enrich_positions(raw):
    out = []
    for p in raw:
        ltp = fetch_ltp(p["symbol"])
        pnl = round((ltp - p["avg"]) * p["qty"], 2)
        out.append({
            "symbol": p["symbol"],
            "qty": p["qty"],
            "avg": p["avg"],
            "ltp": ltp,
            "pnl": pnl
        })
    return out

def compute_pnl(pos):
    return round(sum(p["pnl"] for p in pos), 2)

# ================== MARGIN ==================
def fetch_available_margin():
    # 🔴 Replace later with real Flattrade margin API
    return 250000

# ================== EXIT ALL ==================
def exit_all(reason):
    global running, last_error
    running = False
    last_error = reason
    notify(f"🚨 BOT STOPPED\nReason: {reason}")

# ================== STRATEGY ==================
def strategy():
    global running, positions, pnl

    mode = get_mode()
    notify(f"✅ Bot started in {mode.upper()} mode")

    while running:
        try:
            if mode == "paper":
                raw = load_paper_positions()
            else:
                authd = load_live_auth()
                if not authd:
                    raise RuntimeError("Live auth missing")
                raw = []  # 🔴 live positions API later

            positions = enrich_positions(raw)
            pnl = compute_pnl(positions)
            margin = fetch_available_margin()

            if margin <= MARGIN_EXIT:
                exit_all(f"MARGIN CRITICAL ₹{margin}")
                break

            if margin <= MARGIN_ALERT:
                notify(f"⚠️ Margin Low Alert ₹{margin}")

        except Exception as e:
            exit_all(str(e))
            break

        time.sleep(5)  # near tick-by-tick

# ================== FINNIFTY MONTHLY EXPIRY ==================
def last_tuesday(y, m):
    nxt = datetime.date(y + (m == 12), 1 if m == 12 else m + 1, 1)
    last = nxt - datetime.timedelta(days=1)
    return last - datetime.timedelta(days=(last.weekday() - 1) % 7)

def expiry_watcher():
    global expiry_done
    while True:
        if not running:
            expiry_done = False
            time.sleep(30)
            continue

        now = datetime.datetime.now()
        if (
            not expiry_done
            and now.date() == last_tuesday(now.year, now.month)
            and now.hour == 14
            and now.minute == 0
        ):
            expiry_done = True
            exit_all("FINNIFTY MONTHLY EXPIRY AUTO EXIT 2PM")

        time.sleep(30)

threading.Thread(target=expiry_watcher, daemon=True).start()

# ================== API ==================
@app.post("/control/start")
def start(_: bool = Depends(auth)):
    global running
    if running:
        return {"status": "already_running"}
    running = True
    threading.Thread(target=strategy, daemon=True).start()
    return {"status": "started"}

@app.get("/control/status")
def status(_: bool = Depends(auth)):
    return {
        "mode": get_mode(),
        "running": running,
        "pnl": pnl,
        "positions": positions,
        "last_error": last_error
    }

@app.post("/control/mode")
def mode(payload: dict, _: bool = Depends(auth)):
    if payload.get("pin") != TRADE_MODE_PIN:
        raise HTTPException(403, "Invalid PIN")
    set_mode(payload["mode"])
    notify(f"⚙️ Mode changed to {payload['mode'].upper()}")
    return {"status": "ok"}

# ================== RUN ==================
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
