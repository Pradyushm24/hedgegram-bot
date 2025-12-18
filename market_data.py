import os, requests, json
from dotenv import load_dotenv

load_dotenv()

LIVE_AUTH_FILE = "live_auth.json"

def load_live_auth():
    if not os.path.exists(LIVE_AUTH_FILE):
        return None
    return json.load(open(LIVE_AUTH_FILE))

def get_ltp(symbol: str) -> float:
    auth = load_live_auth()
    if not auth or "jwtToken" not in auth:
        raise RuntimeError("LTP needs live token")

    headers = {"Authorization": f"Bearer {auth['jwtToken']}"}
    r = requests.post(
        "https://api.flattrade.in/market/ltp",
        headers=headers,
        json={"symbols": [symbol]},
        timeout=5
    )
    data = r.json()
    return float(data[symbol]["ltp"])
