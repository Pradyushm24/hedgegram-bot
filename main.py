#!/usr/bin/env python3
import os, time, json, threading, logging, hashlib, datetime, requests
from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import uvicorn

# ================== INIT ==================
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("hedgegram")

CONTROL_API_KEY = os.getenv("CONTROL_API_KEY")
TRADE_MODE = os.getenv("TRADE_MODE", "paper")  # paper / live
FLAT_ID = os.getenv("FLATTRADE_CLIENT_ID")
FLAT_SECRET = os.getenv("FLATTRADE_API_SECRET")
LOGIN_URL = os.getenv("FLATTRADE_LOGIN_URL")

LIVE_AUTH_FILE = "live_auth.json"

app = FastAPI(title="Hedgegram Control")

running = False
state_lock = threading.Lock()
positions = []
pnl = 0.0
last_error = None

# ================== SECURITY ==================
def auth(req: Request):
    if req.headers.get("x-api-key") != CONTROL_API_KEY:
        raise HTTPException(401, "Invalid API key")

# ================== LIVE AUTH ==================
def save_live_auth(data):
    tmp = LIVE_AUTH_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, LIVE_AUTH_FILE)
    os.chmod(LIVE_AUTH_FILE, 0o600)

def load_live_auth():
    if not os.path.exists(LIVE_AUTH_FILE):
        return None
    return json.load(open(LIVE_AUTH_FILE))

# ================== PAPER MOCK ==================
def paper_positions():
    return [
        {"symbol": "BANKNIFTY", "qty": 25, "avg": 100, "ltp": 110},
        {"symbol": "BANKNIFTY", "qty": -25, "avg": 105, "ltp": 100}
    ]

def calc_pnl(pos):
    return round(sum((p["ltp"] - p["avg"]) * p["qty"] for p in pos), 2)

# ================== TELEGRAM ALERT ==================
def notify(msg):
    try:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat:
            return
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={"chat_id": chat, "text": msg}, timeout=5)
    except Exception:
        pass

# ================== EXIT ALL ==================
def exit_all(reason):
    global running
    log.error("EXIT ALL: %s", reason)
    notify(f"🚨 BOT STOPPED\nReason: {reason}\nAll positions exited")
    running = False
    # 🔴 real live cancel logic can be added here

# ================== STRATEGY LOOP ==================
def strategy():
    global positions, pnl, last_error, running
    log.info("Strategy started (%s)", TRADE_MODE)
    notify(f"✅ Bot started in {TRADE_MODE.upper()} mode")

    while running:
        try:
            if TRADE_MODE == "paper":
                positions = paper_positions()
            else:
                authd = load_live_auth()
                if not authd or "jwtToken" not in authd:
                    raise RuntimeError("Live auth missing or expired")

                # 🔴 LIVE POSITION FETCH PLACEHOLDER
                positions = []

            pnl = calc_pnl(positions)
            log.info("PNL: %s", pnl)

        except Exception as e:
            last_error = str(e)
            exit_all(last_error)
            break

        time.sleep(10)

    log.warning("Strategy stopped")

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
    global running
    running = False
    notify("⏸ Bot stopped manually")
    return {"status": "stopped"}

@app.get("/control/status")
def status(_: bool = Depends(auth)):
    return {
        "mode": TRADE_MODE,
        "running": running,
        "positions": len(positions),
        "pnl": pnl,
        "last_error": last_error
    }

@app.post("/control/totp")
def totp(payload: dict, _: bool = Depends(auth)):
    code = payload.get("totp")
    if not code:
        raise HTTPException(400, "Missing TOTP")

    pwd = hashlib.sha256((FLAT_ID + code + FLAT_SECRET).encode()).hexdigest()
    r = requests.post(LOGIN_URL, json={
        "UserName": FLAT_ID,
        "totp": code,
        "password": pwd
    }, timeout=15)

    data = r.json()
    if "jwtToken" not in data:
        notify("❌ TOTP login failed")
        return JSONResponse(502, {"error": data})

    save_live_auth(data)
    notify("🔐 Access token refreshed successfully")
    return {"status": "ok"}

@app.post("/control/panic")
def panic(_: bool = Depends(auth)):
    exit_all("PANIC EXIT (manual)")
    return {"status": "panic_executed"}

# ================== RUN ==================
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
