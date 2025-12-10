#!/usr/bin/env python3
"""
cancel_all.py - Cancel all open orders (safe-by-default)

Usage:
  # show what would be sent (reads live_auth.json)
  ./cancel_all.py --dry-run

  # actually send cancel request (be careful!)
  ./cancel_all.py --confirm

  # use control API to fetch live auth (may be masked) - not recommended
  ./cancel_all.py --from-control --confirm

Environment:
  - LIVE_AUTH_FILE (default: live_auth.json)
  - FLATTRADE_CANCEL_URL (default: https://piconnect.flattrade.in/PiConnectTP/CancelOrder)
  - CONTROL_API_URL (default: http://127.0.0.1:8000/control)
  - CONTROL_API_KEY (if using --from-control)
"""
import os
import sys
import json
import argparse
import logging
from typing import Tuple, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

# config / defaults
LIVE_AUTH_FILE = os.getenv("LIVE_AUTH_FILE", "live_auth.json")
FLATTRADE_CANCEL_URL = os.getenv("FLATTRADE_CANCEL_URL", "https://piconnect.flattrade.in/PiConnectTP/CancelOrder")
CONTROL_API_URL = os.getenv("CONTROL_API_URL", "http://127.0.0.1:8000/control")
CONTROL_API_KEY = os.getenv("CONTROL_API_KEY")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("cancel_all")

def load_live_auth_from_file(path: str = LIVE_AUTH_FILE) -> Tuple[bool, Optional[dict]]:
    if not os.path.exists(path):
        return False, None
    try:
        with open(path, "r") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return False, None
        if "jwtToken" not in data:
            return False, None
        return True, data
    except Exception as e:
        log.exception("Failed to read %s: %s", path, e)
        return False, None

def fetch_live_auth_from_control() -> Tuple[bool, Optional[dict], str]:
    """
    Call the control endpoint /control/liveauth to retrieve live auth.
    NOTE: the control endpoint may intentionally mask jwtToken for security.
    Returns (ok, data, msg)
    """
    url = CONTROL_API_URL.rstrip("/") + "/liveauth"
    headers = {}
    if CONTROL_API_KEY:
        headers["x-api-key"] = CONTROL_API_KEY
    try:
        r = requests.get(url, headers=headers, timeout=10)
    except Exception as e:
        return False, None, f"Request to control API failed: {e}"
    if r.status_code != 200:
        return False, None, f"Control API returned HTTP {r.status_code}: {r.text}"
    try:
        data = r.json()
    except Exception:
        return False, None, "Control API returned non-JSON"
    # If jwtToken is masked, cannot use it
    jwt = data.get("jwtToken") or data.get("token") or None
    if jwt and jwt.startswith("***"):
        return False, None, "Control API returned masked jwtToken; cannot use it for cancel"
    # control may not return full token (by design) so return what we have
    return True, data, "fetched from control API"

def do_cancel(jwt_token: str, sid: Optional[str], cancel_url: str = FLATTRADE_CANCEL_URL, timeout: int = 30):
    headers = {"Authorization": jwt_token, "Content-Type": "application/json"}
    payload = {"sid": sid} if sid else {}
    log.info("POST %s payload=%s", cancel_url, payload)
    r = requests.post(cancel_url, json=payload, headers=headers, timeout=timeout)
    try:
        body = r.json()
    except Exception:
        body = r.text
    return r.status_code, body, r

def parse_args():
    p = argparse.ArgumentParser(description="Cancel all open orders (safe-by-default).")
    p.add_argument("--dry-run", action="store_true", help="Don't send any HTTP request; just print payload and exit")
    p.add_argument("--confirm", action="store_true", help="Actually perform cancel request")
    p.add_argument("--from-control", action="store_true", help="Fetch live_auth from control API instead of local file (may be masked)")
    p.add_argument("--live-auth-file", default=LIVE_AUTH_FILE, help=f"Live auth file (default: {LIVE_AUTH_FILE})")
    p.add_argument("--cancel-url", default=FLATTRADE_CANCEL_URL, help=f"Cancel endpoint (default from env: {FLATTRADE_CANCEL_URL})")
    p.add_argument("--timeout", type=int, default=30)
    return p.parse_args()

def main():
    args = parse_args()

    if not args.confirm and not args.dry_run:
        log.warning("No --confirm or --dry-run provided. Defaulting to --dry-run (safe).")
        args.dry_run = True

    # Acquire live auth
    auth = None
    source = None
    if args.from_control:
        ok, data, msg = fetch_live_auth_from_control()
        if not ok:
            log.error("Failed to fetch live_auth from control API: %s", msg)
            # fallback to file
        else:
            auth = data
            source = "control_api"
    if auth is None:
        ok, data = load_live_auth_from_file(args.live_auth_file)
        if not ok:
            log.error("live_auth not found in file %s and --from-control not usable. Cannot cancel.", args.live_auth_file)
            sys.exit(3)
        auth = data
        source = f"file:{args.live_auth_file}"

    jwt = auth.get("jwtToken")
    sid = auth.get("sid") or auth.get("session") or auth.get("sidValue") if auth else None

    if not jwt:
        log.error("No jwtToken found in live auth (source=%s). Cannot cancel.", source)
        sys.exit(4)

    # Prepare payload / headers info
    headers = {"Authorization": jwt, "Content-Type": "application/json"}
    payload = {"sid": sid} if sid else {}

    log.info("Will attempt cancel using source=%s cancel_url=%s", source, args.cancel_url)

    if args.dry_run:
        print("DRY RUN - no network call will be made.")
        print("Cancel URL:", args.cancel_url)
        print("Headers:")
        # do not print full jwt if long; show only prefix/suffix
        safe_jwt = jwt
        if len(safe_jwt) > 20:
            safe_jwt = safe_jwt[:8] + "..." + safe_jwt[-8:]
        print("  Authorization:", safe_jwt)
        print("  Content-Type: application/json")
        print("Payload:", json.dumps(payload))
        sys.exit(0)

    # confirm path
    if not args.confirm:
        log.error("Refusing to proceed: --confirm flag required to actually send cancel request.")
        sys.exit(2)

    # Actually call cancel
    try:
        status_code, body, resp_obj = do_cancel(jwt, sid, cancel_url=args.cancel_url, timeout=args.timeout)
    except Exception as e:
        log.exception("Cancel request failed: %s", e)
        sys.exit(6)

    print("HTTP status:", status_code)
    print("Response body:")
    if isinstance(body, (dict, list)):
        print(json.dumps(body, indent=2))
    else:
        print(body)

    # If success code (200-ish) return 0, else non-zero
    if 200 <= status_code < 300:
        log.info("Cancel request completed (HTTP %s).", status_code)
        sys.exit(0)
    else:
        log.error("Cancel request returned HTTP %s", status_code)
        sys.exit(5)

if __name__ == "__main__":
    main()
