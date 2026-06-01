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

# ── Uncomment these lines once watchpower-api is confirmed working ──
# from watchpower_api import WatchPowerAPI
# wp = WatchPowerAPI(WP_USER, WP_PASS)

class PriorityRequest(BaseModel):
    output: str   # SBU | SUB | UTI
    charger: str  # OSO | OSE | OSU

@app.get("/")
def root():
    return {"status": "Knox backend is live", "device": DEVICE_SN}

@app.get("/status")
def get_status():
    try:
        # ── REAL: uncomment below when watchpower-api is connected ──
        # data = wp.get_device_status(DEVICE_SN)
        # return data

        # ── PLACEHOLDER: returns mock until API is wired ──
        return {
            "battery_soc": 72,
            "battery_voltage": 51.2,
            "battery_current": 8.4,
            "pv_power": 1840,
            "pv_voltage": 362.0,
            "grid_voltage": 221.0,
            "grid_available": True,
            "load_power": 950,
            "load_percent": 32,
            "output_source": "SBU",
            "charger_source": "OSO",
            "inverter_temp": 44,
            "ac_output_voltage": 220.3,
            "timestamp": "live"
        }
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

    try:
        # ── REAL: uncomment below when watchpower-api is connected ──
        # wp.set_output_priority(DEVICE_SN, req.output)
        # wp.set_charger_priority(DEVICE_SN, req.charger)

        print(f"[Knox] Set output={req.output}, charger={req.charger}")
        return {"ok": True, "output": req.output, "charger": req.charger}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"ok": True, "user_configured": bool(WP_USER), "device_configured": bool(DEVICE_SN)}
