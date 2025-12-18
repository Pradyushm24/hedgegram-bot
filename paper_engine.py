import json, os
from market_data import get_ltp

PAPER_POS_FILE = "paper_positions.json"

def load_paper_positions():
    if not os.path.exists(PAPER_POS_FILE):
        return []
    return json.load(open(PAPER_POS_FILE))

def paper_positions_with_pnl():
    out = []
    for p in load_paper_positions():
        ltp = get_ltp(p["symbol"])
        side = p["side"]
        qty  = int(p["qty"])
        avg  = float(p["avg"])

        pnl = (avg - ltp) * qty if side == "SELL" else (ltp - avg) * qty

        out.append({
            **p,
            "ltp": ltp,
            "pnl": round(pnl, 2)
        })
    return out
