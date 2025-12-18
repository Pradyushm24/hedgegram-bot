import os, json, requests
from market_data import get_ltp
from dotenv import load_dotenv

load_dotenv()

LIVE_AUTH_FILE = "live_auth.json"
FLAT_ID = os.getenv("FLATTRADE_CLIENT_ID")

def load_live_auth():
    if not os.path.exists(LIVE_AUTH_FILE):
        return None
    return json.load(open(LIVE_AUTH_FILE))

def live_positions_with_pnl():
    auth = load_live_auth()
    if not auth:
        raise RuntimeError("Live auth missing")

    headers = {"Authorization": f"Bearer {auth['jwtToken']}"}
    r = requests.post(
        "https://piconnect.flattrade.in/PiConnectTP/PositionBook",
        headers=headers,
        json={"clientcode": FLAT_ID},
        timeout=10
    )

    out = []
    for p in r.json():
        qty = int(p.get("netqty", 0))
        if qty == 0:
            continue

        ltp = get_ltp(p["tsym"])
        avg = float(p["netavgprc"])
        side = "SELL" if qty < 0 else "BUY"
        pnl = (avg - ltp) * abs(qty) if side == "SELL" else (ltp - avg) * qty

        out.append({
            "symbol": p["tsym"],
            "side": side,
            "qty": abs(qty),
            "avg": avg,
            "ltp": ltp,
            "pnl": round(pnl, 2)
        })
    return out
