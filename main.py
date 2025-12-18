#!/usr/bin/env python3
import os
import json
import threading
import time
import logging
from fastapi import FastAPI, Depends, Request, HTTPException
from dotenv import load_dotenv

load_dotenv(os.getenv("ENV_FILE", ".env"))

import uvicorn
from paper_engine import paper_positions_with_pnl
from live_engine import live_positions_with_pnl

# ================== INIT ==================
load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("hedgegram")

CONTROL_API_KEY = os.getenv("CONTROL_API_KEY")
TRADE_MODE_FILE = "trade_mode.json"

app = FastAPI(title="Hedgegram Control")

# ================== STATE ==================
running = False
positions = []
pnl = 0.0
lock = threading.Lock()

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
    json.dump({"mode": mode}, open(TRADE_MODE_FILE, "w"))

# ================== STRATEGY LOOP ==================
def strategy():
    global running, positions, pnl

    log.info("Strategy thread started")

    while running:
        try:
            mode = get_mode()

            if mode == "paper":
                new_positions = paper_positions_with_pnl()
            elif mode == "live":
                new_positions = live_positions_with_pnl()
            else:
                raise RuntimeError(f"Unknown mode: {mode}")

            with lock:
                positions = new_positions
                pnl = round(sum(p.get("pnl", 0) for p in positions), 2)

        except Exception as e:
            log.error(f"Strategy error: {e}")

        time.sleep(5)

    log.info("Strategy thread stopped")

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

@app.get("/control/positions")
def get_positions(_: bool = Depends(auth)):
    with lock:
        return {
            "pnl": pnl,
            "positions": positions
        }

@app.get("/control/status")
def status(_: bool = Depends(auth)):
    with lock:
        return {
            "mode": get_mode(),
            "running": running,
            "pnl": pnl,
            "positions_count": len(positions)
        }

@app.post("/control/mode")
def mode(payload: dict, _: bool = Depends(auth)):
    try:
        set_mode(payload.get("mode"))
    except Exception:
        raise HTTPException(400, "Mode must be 'paper' or 'live'")
    return {"mode": payload["mode"]}

# ================== RUN ==================
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
