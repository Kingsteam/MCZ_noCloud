"""Protokoll zwischen MCZ-Maestro-Modul und Server (Socket.IO v2 / Engine.IO 3).

Reine Funktionen ohne Home-Assistant-Abhängigkeit, damit sie einfach testbar sind.

Ablauf (Ofen = Client, Integration = Server):
  Ofen  GET /socket.io/?EIO=3&transport=polling          -> 200, Body "<len>:0{sid...}"
  Ofen  GET /socket.io/?EIO=3&transport=websocket&sid=.. -> 101 (Subprotokoll "arduino")
  Ofen  "5" (Upgrade)            Server "40" (Connect)
  Ofen  42["join",{serialNumber, macAddress, type, revision}]
  Server 42["ProvaStufa",{"richiesta":"C|C|RecuperoInfo","socketChiamata":"<id>"}]
  Ofen  42["rispondo",{...,"stringaRicevuta":"01|...","socketChiamata":"<id>"}]
  Ofen  "2" (Ping)               Server "3" (Pong)
"""

from __future__ import annotations

import json
from typing import Any

from .const import ALLOWED_WRITE_IDS, SETPOINT_MAX_C, SETPOINT_MIN_C

PING_INTERVAL_MS = 5000
PING_TIMEOUT_MS = 25000

# Statuszeile Typ 01 (RecuperoInfo): Position -> (Schlüssel, Typ)
# Typ: i = Ganzzahl, t = Temperatur (Rohwert / 2), s = Sekunden
INFO_FIELDS: dict[int, tuple[str, str]] = {
    1: ("state", "i"),
    2: ("fan_ambient", "i"),
    5: ("fume_temperature", "i"),
    6: ("ambient_temperature", "t"),
    7: ("puffer_temperature", "t"),
    8: ("boiler_temperature", "t"),
    9: ("ntc3_temperature", "t"),
    11: ("active_set", "i"),
    12: ("fume_fan_rpm", "i"),
    13: ("auger_rpm_set", "i"),
    14: ("auger_rpm_live", "i"),
    15: ("three_way_valve", "i"),
    16: ("pump_pwm", "i"),
    17: ("brazier", "i"),
    18: ("profile", "i"),
    20: ("active_mode", "i"),
    21: ("active_live", "i"),
    22: ("control_mode", "i"),
    23: ("eco_mode", "i"),
    24: ("silent_mode", "i"),
    25: ("chronostat", "i"),
    26: ("temperature_setpoint", "t"),
    27: ("boiler_setpoint", "t"),
    28: ("motherboard_temperature", "t"),
    29: ("power_level", "i"),
    30: ("firmware_version", "i"),
    37: ("operating_seconds_total", "s"),
    43: ("hours_to_service", "i"),
    44: ("minutes_to_switch_off", "i"),
    45: ("ignitions", "i"),
    47: ("pellet_sensor", "i"),
    49: ("sound_effects", "i"),
    59: ("return_temperature", "t"),
    60: ("antifreeze", "i"),
}
NOT_CONNECTED = 0xFF  # Fühler nicht vorhanden (Anzeige wäre 127,5 °C)

# Zustandsnummern (Feld 1). Schlüssel sind Übersetzungsschlüssel.
STATES: dict[int, str] = {
    0: "off",
    1: "check",
    2: "cleaning_cold",
    3: "loading_cold",
    4: "start1_cold",
    5: "start2_cold",
    6: "cleaning_hot",
    7: "loading_hot",
    8: "start1_hot",
    9: "start2_hot",
    10: "stabilising",
    11: "power1",
    12: "power2",
    13: "power3",
    14: "power4",
    15: "power5",
    30: "diagnostics",
    31: "on",
    40: "switching_off",
    41: "cooling",
    42: "cleaning_low",
    43: "cleaning_high",
    44: "unlocking_auger",
    45: "auto_eco",
    46: "standby",
    48: "diagnostics",
    49: "filling_auger",
}
ERROR_STATES = range(50, 70)
BURNING_STATES = frozenset(range(1, 16)) | {31}


class ProtocolError(ValueError):
    """Antwort des Ofens passt nicht zum erwarteten Format."""


def decode_info(frame: str) -> dict[str, Any]:
    """Statuszeile „01|...“ in ein Wörterbuch übersetzen."""
    parts = frame.split("|")
    if len(parts) < 2 or parts[0] != "01":
        raise ProtocolError("keine RecuperoInfo-Zeile")
    out: dict[str, Any] = {}
    for pos, (key, typ) in INFO_FIELDS.items():
        if pos >= len(parts):
            continue
        try:
            raw = int(parts[pos], 16)
        except ValueError as err:
            raise ProtocolError(f"Feld {pos} ist keine Hex-Zahl") from err
        if typ == "t":
            out[key] = None if raw == NOT_CONNECTED else raw / 2
        else:
            out[key] = raw
    state = out.get("state")
    if state in STATES:
        out["state_key"] = STATES[state]
    elif state in ERROR_STATES:
        out["state_key"] = "error"
    else:
        out["state_key"] = "unknown"
    out["burning"] = state in BURNING_STATES
    return out


# --- Befehle ----------------------------------------------------------------

READ_REQUESTS = (
    "RecuperoInfo",
    "RecuperoParametri",
    "RecuperoParametriExtra",
    "RecuperaAllarmi",
    "RecuperoGiornoChrono",
    "RecuperoVersioneSW",
)


def build_read(request: str = "RecuperoInfo") -> str:
    """Leseanfrage bauen."""
    if request not in READ_REQUESTS:
        raise ValueError(request)
    return f"C|C|{request}"


def build_write(param_id: int, value: int) -> str:
    """Schreibbefehl bauen, nur für freigegebene Parameter-IDs."""
    if param_id not in ALLOWED_WRITE_IDS:
        raise ValueError(f"Parameter {param_id} ist nicht freigegeben")
    return f"C|C|WriteParametri|{param_id}|{int(value)}"


def setpoint_raw(celsius: float) -> int:
    """Solltemperatur in °C in den Rohwert (halbe Grad) umrechnen, mit Grenzen."""
    if not SETPOINT_MIN_C <= celsius <= SETPOINT_MAX_C:
        raise ValueError(f"Solltemperatur {celsius} außerhalb der Grenzen")
    return round(celsius * 2)


# --- Socket.IO / Engine.IO 3 -------------------------------------------------


def eio_open_payload(sid: str) -> str:
    """Antwort auf den ersten Polling-Request (Format „<Länge>:<Paket>“)."""
    pkt = "0" + json.dumps(
        {
            "sid": sid,
            "upgrades": ["websocket"],
            "pingInterval": PING_INTERVAL_MS,
            "pingTimeout": PING_TIMEOUT_MS,
        },
        separators=(",", ":"),
    )
    return f"{len(pkt)}:{pkt}"


def sio_event(name: str, data: Any) -> str:
    """Socket.IO-Ereignis als Text."""
    return "42" + json.dumps([name, data], separators=(",", ":"))


def parse_sio_event(text: str) -> tuple[str, Any] | None:
    """„42[...]“ -> (Name, Daten), sonst None."""
    if not text.startswith("42"):
        return None
    try:
        arr = json.loads(text[2:])
    except json.JSONDecodeError:
        return None
    if not isinstance(arr, list) or not arr or not isinstance(arr[0], str):
        return None
    return arr[0], (arr[1] if len(arr) > 1 else None)
