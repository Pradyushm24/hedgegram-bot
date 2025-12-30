#!/usr/bin/env python3

import os
import json
import logging
import requests
from fastapi import FastAPI, Request
import uvicorn
from dotenv import load_dotenv

# ================= LOAD ENV =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# ================= LOGGING ==================
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("callback")

# ================= CONFIG ===================
FLAT_CLIENT_ID = os.getenv("FLATTRADE_CLIENT_ID")
FLAT_SECRET = os.getenv("FLATTRADE_API_SECRET")
TOKEN_URL = "https://authapi.flattrade.in/ftauth/token"

LIVE_AUTH_FILE = os.path.join(BASE_DIR, "live_auth.json")

# ================= FASTAPI ==================
app = FastAPI(title="Hedgegram Callback")

# ======================================================
# 🔁 FLATTRADE CALLBACK (ACCEPTS BOTH GET & POST)
# ======================================================
@app.api_route("/callback", methods=["GET", "POST"])
async def flattrade_callback(request: Request):
    try:
        # ---- Read incoming data ----
        if request.method == "GET":
            data = dict(request.query_params)
        else:
            data = await request.json()

        log.info(f"📥 Flattrade callback received: {data}")

        code = data.get("code")
        client = data.get("client")

        if not code:
            return {"status": "ignored", "reason": "no auth code"}

        if not FLAT_CLIENT_ID or not FLAT_SECRET:
            log.error("❌ Missing FLATTRADE creds in .env")
            return {"status": "error", "reason": "missing credentials"}

        # ---- Exchange auth code → access token ----
        r = requests.post(
            TOKEN_URL,
            json={
                "client_id": FLAT_CLIENT_ID,
                "client_secret": FLAT_SECRET,
                "code": code
            },
            timeout=15
        )

        token_data = r.json()

        if "jwtToken" not in token_data:
            log.error(f"❌ Token exchange failed: {token_data}")
            return {"status": "error", "response": token_data}

        # ---- Save token securely ----
        with open(LIVE_AUTH_FILE, "w") as f:
            json.dump(token_data, f, indent=2)

        try:
            os.chmod(LIVE_AUTH_FILE, 0o600)
        except Exception:
            pass

        log.info("🔐 LIVE ACCESS TOKEN GENERATED & SAVED")

        return {
            "status": "ok",
            "message": "Live token generated",
            "client": client
        }

    except Exception as e:
        log.exception("❌ Callback processing error")
        return {"status": "error", "error": str(e)}

# ================= RUN SERVER =================
if __name__ == "__main__":
    print("🚀 CALLBACK SERVER STARTING ON 127.0.0.1:8080")
    uvicorn.run(app, host="127.0.0.1", port=8080)
