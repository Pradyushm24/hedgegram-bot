#!/usr/bin/env python3
"""
main.py - Hedgegram Trading Bot (FastAPI control + strategy loop)

Endpoints:
- POST /control/totp       JSON {"totp":"123456"}      (admin-only via x-api-key)
- POST /control/load_liveauth                      (reload live_auth.json into memory)
- GET  /control/liveauth                          (masked)
- POST /control/start
- POST /control/stop
- GET  /control/status
- GET  /control/pnl
- GET  /control/positions
- POST /control/panic   (emergency cancel using stored live_auth)

Notes:
- Run with: source venv/bin/activate && python main.py
- Keep secrets in .env (CONTROL_API_KEY, FLATTRADE_CLIENT_ID, FLATTRADE_API_SECRET, etc.)
"""
import os
import time
import json
import threading
import logging
import hashlib
import datetime
from typing import Dict, Any, Tuple

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, Request, HTTPException, Body
from fastapi.responses import JSONResponse
import uvicorn

# ---------- logging ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("hedgegram")

# ---------- load env ----------
load_dotenv()

CONTROL_API_KEY = os.getenv("CONTROL_API_KEY")
CONTROL_API_URL = os.getenv("CONTROL_API_URL", "http://127.0.0.1:8000/control")
FLATTRADE_CLIENT_ID = os.getenv("FLATTRADE_CLIENT_ID")
FLATTRADE_API_SECRET = os.getenv("FLATTRADE_API_SECRET")
FLATTRADE_LOGIN_URL = os.getenv("FLATTRADE_LOGIN_URL", "https://authapi.flattrade.in/ftauth")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "10"))

# Optional override for cancel endpoint
FLATTRADE_CANCEL_URL = os.getenv("FLATTRADE_CANCEL_URL", "https://piconnect.flattrade.in/PiConnectTP/CancelOrder")

# file names
FLATTRADE_CODE_FILE = "flattrade_code.json"  # written by callback endpoint
LIVE_AUTH_FILE = "live_auth.json"

# runtime
runtime_mode = os.getenv("TRADE_MODE", "paper").lower()  # "paper" or "live"

# ---------- timezone helper ----------
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
    KOLKATA = ZoneInfo("Asia/Kolkata")
except Exception:
    try:
        import pytz
        KOLKATA = pytz.timezone("Asia/Kolkata")
    except Exception:
        KOLKATA = None  # fallback: server local time will be used

# ---------- app + state ----------
app = FastAPI(title="Hedgegram Trading Bot Control API")
running = False
strategy_thread = None
strategy_lock = threading.Lock()
current_positions: Dict[str, Any] = {}
live_auth_lock = threading.Lock()

# ---------- security dependency ----------
def require_api_key(request: Request):
    if not CONTROL_API_KEY:
        logger.error("CONTROL_API_KEY not configured")
        raise HTTPException(status_code=500, detail="Server misconfigured")
    key = request.headers.get("x-api-key") or request.query_params.get("api_key")
    if not key or key != CONTROL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True

# ---------- broker helper placeholders ----------
def paper_fetch_positions():
    # Example / mock positions (used in paper mode)
    return [
        {"symbol": "FINNIFTY-MONTH-CE-5OTM", "qty": 65, "avg_price": 100.0, "ltp": 104.5},
        {"symbol": "FINNIFTY-MONTH-PE-5OTM", "qty": -65, "avg_price": 90.0, "ltp": 87.0},
    ]

def paper_place_order(symbol, qty, price):
    # returns a simulated order result
    return {"status": "filled", "symbol": symbol, "qty": qty, "avg_price": price}

def live_fetch_positions(auth: Dict[str, Any]):
    jwt = auth.get("jwtToken")
    sid = auth.get("sid")
    if not jwt or not sid:
        return []
    headers = {"Authorization": jwt}
    url = f"https://piconnect.flattrade.in/PiConnectTP/positions?sid={sid}"
    try:
        r = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        return r.json() if r.status_code == 200 else []
    except Exception:
        logger.exception("live_fetch_positions failed")
        return []

def live_place_order(auth: Dict[str, Any], symbol, qty, side):
    jwt = auth.get("jwtToken")
    sid = auth.get("sid")
    url = "https://piconnect.flattrade.in/PiConnectTP/placeorder"
    headers = {"Authorization": jwt}
    payload = {
        "symbol": symbol,
        "qty": qty,
        "side": side,
        "product": "MIS",
        "orderType": "MARKET",
        "exchange": "NFO",
        "sid": sid
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
        return r.json()
    except Exception:
        logger.exception("live_place_order failed")
        return {"status": "failed"}

# ---------- TOTP exchange & live_auth storage ----------
def exchange_totp_and_store(totp_code: str) -> Tuple[bool, Any]:
    """
    Exchange TOTP + requestCode/client (from flattrade_code.json) to obtain JWT token.
    Stores the returned object to LIVE_AUTH_FILE on success (permissions 600).
    Returns (True, body) on success or (False, body) on failure.
    """
    if not (FLATTRADE_CLIENT_ID and FLATTRADE_API_SECRET):
        logger.error("Missing Flattrade credentials in env")
        return False, {"error": "missing_credentials"}

    hashed_pass = hashlib.sha256((FLATTRADE_CLIENT_ID + totp_code + FLATTRADE_API_SECRET).encode()).hexdigest()
    payload = {"UserName": FLATTRADE_CLIENT_ID, "totp": totp_code, "password": hashed_pass}

    # optionally include requestCode / client from callback file
    try:
        if os.path.exists(FLATTRADE_CODE_FILE):
            with open(FLATTRADE_CODE_FILE, "r") as fh:
                data = json.load(fh)
            params = data.get("params", {}) if isinstance(data.get("params"), dict) else data
            req = params.get("requestCode") or params.get("request_code") or params.get("code") or params.get("auth_code")
            client_param = params.get("client") or params.get("Client") or None
            if req:
                payload["requestCode"] = req
            if client_param:
                payload["client"] = client_param
            logger.info("Using callback params: requestCode=%s client=%s", bool(req), client_param)
    except Exception:
        logger.exception("Failed to read flattrade_code.json (non-fatal)")

    try:
        headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
        r = requests.post(FLATTRADE_LOGIN_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
    except Exception as e:
        logger.exception("Auth request failed")
        return False, {"error": str(e)}

    try:
        body = r.json()
    except Exception:
        logger.error("Non-JSON response from flattrade")
        return False, {"raw": r.text}

    if r.status_code != 200 or "jwtToken" not in body:
        logger.warning("Flattrade login failed (status=%s) body=%s", r.status_code, body)
        return False, body

    # Save safely (atomic)
    try:
        tmp = LIVE_AUTH_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(body, f, indent=2)
        os.replace(tmp, LIVE_AUTH_FILE)
        try:
            os.chmod(LIVE_AUTH_FILE, 0o600)
        except Exception:
            pass
    except Exception:
        logger.exception("Failed to write live_auth.json")
        return False, {"error": "write_failed"}

    logger.info("Live auth saved to %s", LIVE_AUTH_FILE)
    return True, body

# ---------- load live_auth from disk ----------
def load_live_auth_from_file() -> bool:
    """
    Load live_auth.json (if exists) into app.state.live_auth safely.
    Returns True if loaded, False otherwise.
    """
    try:
        if not os.path.exists(LIVE_AUTH_FILE):
            return False
        with open(LIVE_AUTH_FILE, "r") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return False
        if "jwtToken" not in data:
            return False
        with live_auth_lock:
            app.state.live_auth = data
            app.state.live_auth_ts = time.time()
        logger.info("Loaded %s into memory (sid present=%s)", LIVE_AUTH_FILE, bool(data.get("sid")))
        return True
    except Exception:
        logger.exception("Failed to load live_auth.json")
        return False

# ---------- PnL ----------
def compute_pnl(positions):
    pnl = 0.0
    for p in positions:
        qty = p.get("qty", 0)
        pnl += (p.get("ltp", 0.0) - p.get("avg_price", 0.0)) * qty
    return round(pnl, 2)

# ---------- Strategy loop ----------
def strategy_loop():
    global running, current_positions, runtime_mode
    logger.info("Strategy loop started in %s mode", runtime_mode)
    while running:
        try:
            if runtime_mode == "paper":
                positions = paper_fetch_positions()
            else:
                auth = getattr(app.state, "live_auth", None)
                if not auth:
                    logger.warning("Live auth missing; skipping live fetch")
                    positions = []
                else:
                    positions = live_fetch_positions(auth)

            pnl = compute_pnl(positions)
            current_positions["positions"] = positions
            current_positions["pnl"] = pnl
            logger.info("Current PnL: %s", pnl)
        except Exception:
            logger.exception("Exception in strategy_loop iteration")
        time.sleep(10)
    logger.info("Strategy loop stopped")

# ---------- start / stop ----------
def start_bot():
    global running, strategy_thread
    with strategy_lock:
        if running:
            return {"status": "already_running"}
        running = True
        strategy_thread = threading.Thread(target=strategy_loop, daemon=True)
        strategy_thread.start()
    logger.info("Bot started")
    return {"status": "started"}

def stop_bot():
    global running
    with strategy_lock:
        running = False
    logger.info("Bot stopped")
    return {"status": "stopped"}

# ---------- Force-exit on expiry @ 14:00 IST ----------
def last_thursday(year: int, month: int) -> datetime.date:
    if month == 12:
        next_month = datetime.date(year + 1, 1, 1)
    else:
        next_month = datetime.date(year, month + 1, 1)
    last_day = next_month - datetime.timedelta(days=1)
    offset = (last_day.weekday() - 3) % 7  # Thursday -> weekday()==3
    return last_day - datetime.timedelta(days=offset)

def is_expiry_day(dt: datetime.datetime) -> bool:
    today = dt.date()
    y, m = today.year, today.month
    exp = last_thursday(y, m)
    return today == exp

def close_all_positions(force_reason="force_exit"):
    """
    Attempt to close all positions the strategy currently has.
    Returns a summary dict.
    """
    logger.info("Starting force-exit: %s", force_reason)
    auth = getattr(app.state, "live_auth", None)
    positions = current_positions.get("positions", []) or []
    results = []
    for p in positions:
        try:
            symbol = p.get("symbol") or p.get("scrip") or p.get("instr") or "unknown"
            qty = int(p.get("qty", 0))
            if qty == 0:
                continue
            side = "sell" if qty > 0 else "buy"
            close_qty = abs(qty)
            if runtime_mode == "paper":
                res = paper_place_order(symbol, -qty, p.get("ltp", p.get("avg_price", 0.0)))
                results.append({"symbol": symbol, "mode": "paper", "qty": close_qty, "side": side, "result": res})
                logger.info("Paper-close %s %s -> %s", symbol, side, res)
            else:
                if not auth:
                    results.append({"symbol": symbol, "error": "no_live_auth"})
                    logger.warning("Skipping live close for %s: no live_auth", symbol)
                    continue
                r = live_place_order(auth, symbol, close_qty, side)
                results.append({"symbol": symbol, "mode": "live", "qty": close_qty, "side": side, "result": r})
                logger.info("Live-close %s %s -> %s", symbol, side, r)
        except Exception:
            logger.exception("Exception closing position %s", p)
            results.append({"symbol": p.get("symbol", "unknown"), "error": "exception"})
    return {"closed": len(results), "details": results}

def expiry_force_exit_watcher():
    """
    Background watcher that triggers close_all_positions() once at 14:00 IST on expiry day.
    """
    logger.info("Starting expiry_force_exit_watcher (force exit on expiry day at 14:00 IST)")
    triggered_today = False
    while True:
        try:
            now_utc = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
            if KOLKATA:
                now_local = now_utc.astimezone(KOLKATA)
            else:
                now_local = datetime.datetime.now()
            # reset at local midnight
            if now_local.hour == 0 and now_local.minute == 0:
                triggered_today = False

            if is_expiry_day(now_local):
                if not triggered_today and now_local.hour == 14 and now_local.minute == 0:
                    logger.info("Expiry day 14:00 detected. Executing force-exit.")
                    res = close_all_positions(force_reason="expiry_14_00")
                    logger.info("Expiry force-exit result: %s", res)
                    triggered_today = True
        except Exception:
            logger.exception("expiry_force_exit_watcher error")
        time.sleep(30)

# ---------- FastAPI endpoints ----------
@app.post("/control/start")
def control_start(_=Depends(require_api_key)):
    return JSONResponse(status_code=200, content=start_bot())

@app.post("/control/stop")
def control_stop(_=Depends(require_api_key)):
    return JSONResponse(status_code=200, content=stop_bot())

@app.get("/control/status")
def control_status(_=Depends(require_api_key)):
    return {
        "mode": runtime_mode,
        "running": running,
        "positions_count": len(current_positions.get("positions", [])),
        "pnl": current_positions.get("pnl", 0.0)
    }

@app.get("/control/pnl")
def control_pnl(_=Depends(require_api_key)):
    return {"pnl": current_positions.get("pnl", 0.0), "positions": len(current_positions.get("positions", []))}

@app.get("/control/positions")
def control_positions(_=Depends(require_api_key)):
    positions = current_positions.get("positions", []) or []
    details = []
    total_pnl = 0.0
    for p in positions:
        symbol = p.get("symbol") or p.get("scrip") or p.get("instr") or "unknown"
        qty = p.get("qty", 0)
        avg_price = p.get("avg_price", p.get("avg", 0.0)) or 0.0
        ltp = p.get("ltp", p.get("last_price", 0.0)) or 0.0
        pnl = round((ltp - avg_price) * qty, 2)
        details.append({
            "symbol": symbol,
            "qty": qty,
            "avg_price": float(avg_price),
            "ltp": float(ltp),
            "pnl": pnl
        })
        total_pnl += pnl
    return {"positions": details, "pnl": round(total_pnl, 2), "positions_count": len(details)}

@app.post("/control/totp")
def control_totp(payload: dict = Body(...), _=Depends(require_api_key)):
    totp_code = str(payload.get("totp", "")).strip()
    if not totp_code:
        raise HTTPException(status_code=400, detail="Missing 'totp'")
    ok, data = exchange_totp_and_store(totp_code)
    if not ok:
        return JSONResponse(status_code=502, content={"error": "login_failed", "body": data})
    # store in memory too
    with live_auth_lock:
        app.state.live_auth = data
        app.state.live_auth_ts = time.time()
    logger.info("Flattrade login successful, live_auth stored (sid present=%s)", bool(data.get("sid")))
    return {"status": "ok", "sid_present": bool(data.get("sid"))}

@app.get("/control/liveauth")
def control_liveauth(_=Depends(require_api_key)):
    auth = getattr(app.state, "live_auth", None)
    if not auth:
        raise HTTPException(status_code=404, detail="No live auth")
    masked = {"jwtToken": "***REDACTED***", "sid": auth.get("sid"), "received_at": getattr(app.state, "live_auth_ts", None)}
    return masked

@app.post("/control/load_liveauth")
def control_load_liveauth(_=Depends(require_api_key)):
    ok = load_live_auth_from_file()
    if not ok:
        raise HTTPException(status_code=404, detail="live_auth.json not found or invalid")
    return {"status": "loaded"}

@app.post("/control/panic")
def control_panic(_=Depends(require_api_key)):
    auth = getattr(app.state, "live_auth", None)
    if not auth:
        return JSONResponse(status_code=400, content={"status": "error", "error": "no_live_auth"})
    jwt = auth.get("jwtToken")
    sid = auth.get("sid")
    if not jwt or not sid:
        return JSONResponse(status_code=400, content={"status": "error", "error": "incomplete_live_auth"})
    try:
        headers = {"Authorization": jwt, "Content-Type": "application/json"}
        payload = {"sid": sid}
        r = requests.post(FLATTRADE_CANCEL_URL, json=payload, headers=headers, timeout=30)
        try:
            body = r.json()
        except Exception:
            body = r.text
        logger.info("Cancel request sent, http=%s", r.status_code)
        return {"status": "sent", "http": r.status_code, "body": body}
    except Exception as e:
        logger.exception("panic cancel failed")
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})

# ---------- startup / shutdown ----------
@app.on_event("startup")
def on_startup():
    app.state.live_auth = None
    app.state.live_auth_ts = None
    logger.info("Hedgegram control API starting (mode=%s)", runtime_mode)
    # try to preload live_auth if present
    if load_live_auth_from_file():
        logger.info("live_auth.json pre-loaded at startup")
    # start expiry watcher thread
    t = threading.Thread(target=expiry_force_exit_watcher, daemon=True)
    t.start()
    # start strategy automatically if you want, otherwise call /control/start
    # start_bot()

@app.on_event("shutdown")
def on_shutdown():
    stop_bot()

# ---------- run server ----------
if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, log_level="info")
