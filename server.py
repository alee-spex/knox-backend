import os
import hashlib
import traceback
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Knox Inverter Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

WP_USER   = os.getenv("WP_USER")
WP_PASS   = os.getenv("WP_PASS")
DEVICE_SN = os.getenv("DEVICE_SN")

_wp = None

def get_wp():
    global _wp
    if _wp is not None:
        return _wp
    if not WP_USER or not WP_PASS:
        raise HTTPException(status_code=503, detail="Credentials not configured.")
    try:
        from watchpower_api import WatchPowerAPI
        client = WatchPowerAPI()
        client.login(WP_USER, WP_PASS)
        _wp = client
        return _wp
    except ImportError:
        raise HTTPException(status_code=503, detail="watchpower_api not installed.")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Login failed: {e}")


class PriorityRequest(BaseModel):
    output: str
    charger: str


@app.get("/")
def root():
    return {"status": "Knox backend is live", "device": DEVICE_SN}


@app.get("/health")
def health():
    return {
        "ok": True,
        "user_configured": bool(WP_USER),
        "device_configured": bool(DEVICE_SN),
        "wp_client_initialized": _wp is not None,
    }


@app.get("/debug")
def debug():
    """Full diagnostic — shows login attempt details and raw API response."""
    result = {
        "env": {
            "WP_USER": WP_USER,                          # show username (safe)
            "WP_PASS_length": len(WP_PASS) if WP_PASS else 0,
            "WP_PASS_md5": hashlib.md5(WP_PASS.encode()).hexdigest() if WP_PASS else None,
            "WP_PASS_has_spaces": WP_PASS != WP_PASS.strip() if WP_PASS else False,
            "DEVICE_SN": DEVICE_SN,
        },
        "wp_login": None,
        "raw_status": None,
        "error": None,
        "traceback": None,
    }

    # Try 1: login with password as-is
    try:
        from watchpower_api import WatchPowerAPI
        client = WatchPowerAPI()
        client.login(WP_USER, WP_PASS)
        result["wp_login"] = "success (plain password)"
    except Exception as e1:
        result["wp_login"] = f"failed plain: {e1}"

        # Try 2: login with MD5-hashed password (some WatchPower versions require this)
        try:
            md5_pass = hashlib.md5(WP_PASS.encode()).hexdigest()
            client2 = WatchPowerAPI()
            client2.login(WP_USER, md5_pass)
            result["wp_login"] = "success (MD5 hashed password)"
            client = client2
        except Exception as e2:
            result["wp_login_md5"] = f"failed md5: {e2}"
            result["error"] = str(e1)
            result["traceback"] = traceback.format_exc()
            return result

    # If login worked, try get_device_status
    try:
        raw = client.get_device_status(DEVICE_SN)
        result["raw_status"] = raw
    except Exception as e:
        result["error"] = str(e)
        result["traceback"] = traceback.format_exc()

    return result


@app.get("/status")
def get_status():
    if not DEVICE_SN:
        raise HTTPException(status_code=503, detail="DEVICE_SN not set.")
    try:
        wp = get_wp()
        data = wp.get_device_status(DEVICE_SN)
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/set-priority")
def set_priority(req: PriorityRequest):
    valid_output  = ["SBU", "SUB", "UTI"]
    valid_charger = ["OSO", "OSE", "OSU"]

    if req.output not in valid_output:
        raise HTTPException(status_code=400, detail=f"Invalid output: {req.output}")
    if req.charger not in valid_charger:
        raise HTTPException(status_code=400, detail=f"Invalid charger: {req.charger}")
    if not DEVICE_SN:
        raise HTTPException(status_code=503, detail="DEVICE_SN not set.")

    try:
        wp = get_wp()
        wp.set_output_priority(DEVICE_SN, req.output)
        wp.set_charger_priority(DEVICE_SN, req.charger)
        return {"ok": True, "output": req.output, "charger": req.charger}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
