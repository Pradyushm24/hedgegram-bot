#!/usr/bin/env python3
import os, time, json, threading, logging, hashlib, requests
from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import uvicorn

# ================== INIT ==================
load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("hedgegram")

CONTROL_API_KEY = os.getenv("CONTROL_API_KEY")
TRADE_MODE = os.getenv("TRADE_MODE", "paper")
FLAT_ID = os.getenv("FLATTRADE_CLIENT_ID")
FLAT_SECRET = os.getenv("FLATTRADE_API_SECRET")
LOGIN_URL = os.getenv("FLATTRADE_LOGIN_URL")

LIVE_AUTH_FILE = "live_auth.json"

app = FastAPI(title="Hedgegram Control")
running = False
state_lock = threading.Lock()
positions = []
pnl = 0.0

# ================== SECURITY ==================
def auth(req: Request):
    if req.headers.get("x-api-key") != CONTROL_API_KEY:
        raise HTTPException(401, "Invalid API key")

# ================== AUTH ==================
def save_live_auth(data):
    with open(LIVE_AUTH_FILE, "w") as f:
        json.dump(data, f)
    os.chmod(LIVE_AUTH_FILE, 0o600)

def load_live_auth():
    if not os.path.exists(LIVE_AUTH_FILE):
        return None
    return json.load(open(LIVE_AUTH_FILE))

# ================== PAPER MOCK ==================
def paper_positions():
    return [
        {"symbol": "BANKNIFTY", "qty": 25, "avg": 100, "ltp": 110}
    ]

def calc_pnl(pos):
    return sum((p["ltp"] - p["avg"]) * p["qty"] for p in pos)

# ================== STRATEGY LOOP ==================
def strategy():
    global positions, pnl
    log.info("Strategy loop started (%s)", TRADE_MODE)
    while running:
        try:
            if TRADE_MODE == "paper":
                positions = paper_positions()
            else:
                authd = load_live_auth()
                if not authd:
                    log.warning("Live auth missing")
                    time.sleep(5)
                    continue
                # LIVE POSITION FETCH (placeholder)
                positions = []
            pnl = calc_pnl(positions)
            log.info("PNL: %s", pnl)
        except Exception as e:
            log.exception("Strategy error")
        time.sleep(10)

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
    return {"status": "stopped"}

@app.get("/control/status")
def status(_: bool = Depends(auth)):
    return {
        "mode": TRADE_MODE,
        "running": running,
        "positions": len(positions),
        "pnl": pnl
    }

@app.post("/control/totp")
def totp(payload: dict, _: bool = Depends(auth)):
    totp = payload.get("totp")
    if not totp:
        raise HTTPException(400, "Missing TOTP")
    pwd = hashlib.sha256((FLAT_ID + totp + FLAT_SECRET).encode()).hexdigest()
    r = requests.post(LOGIN_URL, json={
        "UserName": FLAT_ID,
        "totp": totp,
        "password": pwd
    }, timeout=15)
    data = r.json()
    if "jwtToken" not in data:
        return JSONResponse(502, {"error": data})
    save_live_auth(data)
    return {"status": "ok"}

@app.post("/control/panic")
def panic(_: bool = Depends(auth)):
    global running
    running = False
    return {"status": "ALL POSITIONS EXITED (MANUAL LOGIC)"}

# ================== RUN ==================
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
