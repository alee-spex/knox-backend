import os
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

# ── WatchPower credentials from environment variables ──
WP_USER   = os.getenv("WP_USER")
WP_PASS   = os.getenv("WP_PASS")
DEVICE_SN = os.getenv("DEVICE_SN")

# ── Lazy WatchPower client — initialized on first use, not at startup ──
# This prevents Render deployment failures when the package isn't yet
# installed or env vars aren't set during the build phase.
_wp = None

def get_wp():
    global _wp
    if _wp is not None:
        return _wp
    if not WP_USER or not WP_PASS:
        raise HTTPException(
            status_code=503,
            detail="WatchPower credentials not configured. Set WP_USER and WP_PASS environment variables."
        )
    try:
        from watchpower_api import WatchPowerAPI
        _wp = WatchPowerAPI(WP_USER, WP_PASS)
        return _wp
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="watchpower_api package not installed. Add it to requirements.txt."
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"WatchPower connection failed: {e}")


class PriorityRequest(BaseModel):
    output: str   # SBU | SUB | UTI
    charger: str  # OSO | OSE | OSU


@app.get("/")
def root():
    return {
        "status": "Knox backend is live",
        "device": DEVICE_SN,
        "wp_user_set": bool(WP_USER),
        "wp_pass_set": bool(WP_PASS),
    }


@app.get("/status")
def get_status():
    if not DEVICE_SN:
        raise HTTPException(status_code=503, detail="DEVICE_SN environment variable not set.")
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
        raise HTTPException(status_code=400, detail=f"Invalid output priority: {req.output}")
    if req.charger not in valid_charger:
        raise HTTPException(status_code=400, detail=f"Invalid charger priority: {req.charger}")

    if not DEVICE_SN:
        raise HTTPException(status_code=503, detail="DEVICE_SN environment variable not set.")

    try:
        wp = get_wp()
        wp.set_output_priority(DEVICE_SN, req.output)
        wp.set_charger_priority(DEVICE_SN, req.charger)
        print(f"[Knox] Set output={req.output}, charger={req.charger}")
        return {"ok": True, "output": req.output, "charger": req.charger}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {
        "ok": True,
        "user_configured": bool(WP_USER),
        "device_configured": bool(DEVICE_SN),
        "wp_client_initialized": _wp is not None,
    }
