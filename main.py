#!/usr/bin/env python3
import os
import json
import time
import threading
import logging
from fastapi import FastAPI, Depends, Request, HTTPException
from dotenv import load_dotenv
import uvicorn

# ================== LOAD ENV (PM2 SAFE) ==================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# ================== IMPORT ENGINES ==================
from paper_engine import paper_positions_with_pnl
from live_engine import live_positions_with_pnl

# ================== LOGGING ==================
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("hedgegram")

# ================== CONFIG ==================
CONTROL_API_KEY = os.getenv("CONTROL_API_KEY")
TRADE_MODE_FILE = "trade_mode.json"
LIVE_AUTH_FILE = "live_auth.json"

# ================== FASTAPI ==================
app = FastAPI(title="Hedgegram Control")

# ================== RUNTIME STATE ==================
running = False
positions = []
pnl = 0.0

# ================== AUTH ==================
def auth(req: Request):
    if req.headers.get("x-api-key") != CONTROL_API_KEY:
        raise HTTPException(401, "Invalid API key")
    return True

# ================== MODE ==================
def get_mode() -> str:
    if not os.path.exists(TRADE_MODE_FILE):
        return "paper"
    try:
        return json.load(open(TRADE_MODE_FILE)).get("mode", "paper")
    except Exception:
        return "paper"

def set_mode(mode: str):
    if mode not in ("paper", "live"):
        raise ValueError("Invalid mode")
    with open(TRADE_MODE_FILE, "w") as f:
        json.dump({"mode": mode}, f)

# ================== STRATEGY LOOP ==================
def strategy():
    global running, positions, pnl
    log.info("Strategy started")
    while running:
        try:
            # 🔒 LIVE SAFETY
            if get_mode() == "live" and not os.path.exists(LIVE_AUTH_FILE):
                log.warning("Live auth missing — switching to PAPER mode")
                set_mode("paper")

            if get_mode() == "paper":
                positions = paper_positions_with_pnl()
            else:
                positions = live_positions_with_pnl()

            pnl = round(sum(p.get("pnl", 0) for p in positions), 2)

        except Exception as e:
            log.error(f"Strategy error: {e}")

        time.sleep(5)

    log.info("Strategy stopped")

# ================== CONTROL APIs ==================
@app.post("/control/start")
def start(_: bool = Depends(auth)):
    global running
    if running:
        return {"status": "already running"}
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
        "mode": get_mode(),
        "running": running,
        "pnl": pnl,
        "positions_count": len(positions),
    }

@app.get("/control/positions")
def get_positions(_: bool = Depends(auth)):
    return positions

@app.post("/control/paper")
def paper(_: bool = Depends(auth)):
    set_mode("paper")
    return {"mode": "paper"}

@app.post("/control/live")
def live(_: bool = Depends(auth)):
    if not os.path.exists(LIVE_AUTH_FILE):
        return {
            "error": "Live auth missing",
            "hint": "Generate access token first"
        }
    set_mode("live")
    return {"mode": "live"}

# ================== AUTO START SAFE ==================
if get_mode() == "live" and not os.path.exists(LIVE_AUTH_FILE):
    log.warning("Live auth missing at boot — forcing PAPER mode")
    set_mode("paper")

# ================== MAIN ==================
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
