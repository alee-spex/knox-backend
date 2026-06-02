import os
import hashlib
import time
import traceback
import requests
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

# ── DessMonitor credentials ──
DESS_SECRET = os.getenv("DESS_SECRET")
DESS_TOKEN  = os.getenv("DESS_TOKEN")
DESS_PN     = os.getenv("DESS_PN")
DESS_SN     = os.getenv("DESS_SN")
DESS_DEVCODE = os.getenv("DESS_DEVCODE", "2429")  # default, may need updating
DESS_DEVADDR = os.getenv("DESS_DEVADDR", "1")

DESS_API = "https://web.dessmonitor.com/public/"

def dess_sign(action_params: str) -> dict:
    """Build signed DessMonitor API request params."""
    salt = str(int(time.time() * 1000))
    raw  = salt + DESS_SECRET + DESS_TOKEN + action_params
    sign = hashlib.sha1(raw.encode()).hexdigest()
    return {"sign": sign, "salt": salt, "token": DESS_TOKEN}

def dess_get(action: str, extra: dict = {}) -> dict:
    """Make a signed GET request to DessMonitor API."""
    # Build the action string for signing
    params = {
        "action":  action,
        "source":  "1",
        "devcode": DESS_DEVCODE,
        "pn":      DESS_PN,
        "devaddr": DESS_DEVADDR,
        "sn":      DESS_SN,
        "i18n":    "en_US",
        **extra,
    }
    # Build action_params string (sorted, & separated)
    action_str = "&" + "&".join(f"{k}={v}" for k, v in params.items())
    signed = dess_sign(action_str)
    full_params = {**signed, **params}
    r = requests.get(DESS_API, params=full_params, timeout=15)
    r.raise_for_status()
    data = r.json()
    if data.get("err", 0) != 0:
        raise RuntimeError(f"DessMonitor error {data.get('err')}: {data.get('desc')}")
    return data.get("dat", data)


class PriorityRequest(BaseModel):
    output: str   # SBU | SUB | UTI
    charger: str  # OSO | OSE | OSU

# Map human-readable priorities to DessMonitor command values
OUTPUT_MAP  = {"SBU": "0", "SUB": "1", "UTI": "2"}
CHARGER_MAP = {"OSO": "0", "OSE": "1", "OSU": "2"}


@app.get("/")
def root():
    return {
        "status": "Knox backend is live",
        "backend": "DessMonitor API",
        "sn": DESS_SN,
        "pn": DESS_PN,
        "secret_set": bool(DESS_SECRET),
        "token_set":  bool(DESS_TOKEN),
    }


@app.get("/health")
def health():
    return {
        "ok": True,
        "secret_configured": bool(DESS_SECRET),
        "token_configured":  bool(DESS_TOKEN),
        "pn_configured":     bool(DESS_PN),
        "sn_configured":     bool(DESS_SN),
    }


@app.get("/debug")
def debug():
    """Full diagnostic — tests DessMonitor API connection."""
    result = {
        "env": {
            "DESS_SECRET_length": len(DESS_SECRET) if DESS_SECRET else 0,
            "DESS_TOKEN": DESS_TOKEN,
            "DESS_PN": DESS_PN,
            "DESS_SN": DESS_SN,
            "DESS_DEVCODE": DESS_DEVCODE,
        },
        "api_test": None,
        "raw_data": None,
        "error": None,
        "traceback": None,
    }
    try:
        raw = dess_get("queryDeviceLastData")
        result["api_test"] = "success"
        result["raw_data"] = raw
    except Exception as e:
        result["api_test"] = "failed"
        result["error"] = str(e)
        result["traceback"] = traceback.format_exc()
    return result


@app.get("/status")
def get_status():
    """Return live inverter telemetry mapped to Knox controller fields."""
    try:
        raw = dess_get("queryDeviceLastData")
        pars = raw.get("pars", [])

        def get_val(field_id):
            for p in pars:
                if p.get("id") == field_id:
                    try:
                        return float(p.get("val", 0))
                    except:
                        return p.get("val", 0)
            return None

        def get_str(field_id):
            for p in pars:
                if p.get("id") == field_id:
                    return str(p.get("val", ""))
            return ""

        # Map DessMonitor fields → Knox controller expected fields
        battery_soc     = get_val("bt_battery_capacity") or get_val("bt_soc") or 0
        battery_voltage = get_val("bt_battery_voltage") or get_val("bt_vol") or 0
        battery_current = get_val("bt_battery_current") or get_val("bt_cur") or 0
        pv_power        = get_val("pv_total_power") or get_val("pv_power") or 0
        pv_voltage      = get_val("pv_input_voltage1") or get_val("pv_vol") or 0
        grid_voltage    = get_val("gd_grid_voltage") or get_val("gd_vol") or 0
        load_power      = get_val("bc_active_load_power") or get_val("bc_load_power") or 0
        load_percent    = get_val("bc_output_load_percent") or 0
        inverter_temp   = get_val("bc_inverter_temperature") or get_val("bc_temp") or 0
        ac_output_volt  = get_val("bc_ac_output_voltage") or get_val("bc_out_vol") or 0
        output_source   = get_str("bc_output_source_priority") or "SBU"
        charger_source  = get_str("bt_charger_source_priority") or "OSO"
        grid_available  = grid_voltage > 100

        return {
            "battery_soc":       round(battery_soc),
            "battery_voltage":   round(battery_voltage, 1),
            "battery_current":   round(battery_current, 1),
            "pv_power":          round(pv_power),
            "pv_voltage":        round(pv_voltage, 1),
            "grid_voltage":      round(grid_voltage, 1),
            "grid_available":    grid_available,
            "load_power":        round(load_power),
            "load_percent":      round(load_percent),
            "inverter_temp":     round(inverter_temp),
            "ac_output_voltage": round(ac_output_volt, 1),
            "output_source":     output_source,
            "charger_source":    charger_source,
            "timestamp":         raw.get("time", ""),
            "_raw_pars":         pars,   # included for field mapping debug
        }
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

    try:
        # Send output source priority command
        dess_get("sendCmdToDevice", {
            "param": f"POP{OUTPUT_MAP[req.output]}"
        })
        # Send charger source priority command
        dess_get("sendCmdToDevice", {
            "param": f"PCP{CHARGER_MAP[req.charger]}"
        })
        print(f"[Knox] Set output={req.output}, charger={req.charger}")
        return {"ok": True, "output": req.output, "charger": req.charger}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
