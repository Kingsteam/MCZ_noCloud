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

from datetime import datetime
import json
from typing import Any

from .const import (
    ALLOWED_WRITE_IDS,
    BOILER_SETPOINT_MAX_C,
    BOILER_SETPOINT_MIN_C,
    FORBIDDEN_TECH_IDS,
    SETPOINT_MAX_C,
    SETPOINT_MIN_C,
    TECH_PARAMS,
)

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


def boiler_setpoint_raw(celsius: float) -> int:
    """Kessel-Solltemperatur in °C in halbe Grad umrechnen, mit Grenzen."""
    if not BOILER_SETPOINT_MIN_C <= celsius <= BOILER_SETPOINT_MAX_C:
        raise ValueError(f"Kessel-Solltemperatur {celsius} außerhalb der Grenzen")
    return round(celsius * 2)


def build_tech_write(key: str, value: int) -> str:
    """Technischen Parameter schreiben, nur freigegebene und in den Grenzen.

    Format laut Mitschnitt: „WriteTecniciParametri|ID|Bytes|Wert“, Wert als
    Hex mit 2 Zeichen je Byte, z. B. 148|2|0078 = 120 Sekunden.
    """
    if key not in TECH_PARAMS:
        raise ValueError(f"Technischer Parameter {key} ist nicht freigegeben")
    param_id, size, low, high = TECH_PARAMS[key]
    if param_id in FORBIDDEN_TECH_IDS:  # doppelte Absicherung
        raise ValueError(f"Parameter {param_id} ist gesperrt")
    value = int(value)
    if not low <= value <= high:
        raise ValueError(f"{key} = {value} außerhalb {low} bis {high}")
    return f"C|C|WriteTecniciParametri|{param_id}|{size}|{value:0{size * 2}X}"


# --- Zeitprogramm (Chrono) ------------------------------------------------------
# Je Tag 48 halbe Stunden ab 0:00, je 2 Bit: 0 aus, 1 T1, 2 T2, 3 T3.
# Tag 0 = Sonntag, 1 = Montag … 6 = Samstag (wie im Ofen).
CHRONO_SLOTS = 48
CHRONO_LEVELS = (0, 1, 2, 3)


def encode_chrono_day(slots: list[int]) -> str:
    """48 Stufen in 24 Hex-Zeichen packen (höchstwertige Bits zuerst)."""
    if len(slots) != CHRONO_SLOTS or any(s not in CHRONO_LEVELS for s in slots):
        raise ValueError("Ein Tag braucht 48 Stufen von 0 bis 3")
    value = 0
    for level in slots:
        value = (value << 2) | level
    return f"{value:024X}"


def decode_chrono_day(text: str) -> list[int]:
    """24 Hex-Zeichen in 48 Stufen auspacken."""
    if len(text) != 24:
        raise ProtocolError("Tagesprogramm muss 24 Hex-Zeichen haben")
    try:
        value = int(text, 16)
    except ValueError as err:
        raise ProtocolError("Tagesprogramm ist keine Hex-Zahl") from err
    return [(value >> (2 * (CHRONO_SLOTS - 1 - i))) & 3 for i in range(CHRONO_SLOTS)]


def decode_chrono(frame: str) -> dict[str, Any]:
    """Antwort „04|Tag0|…|Tag6|T1|T2|T3“ auf RecuperoGiornoChrono."""
    parts = frame.split("|")
    if len(parts) < 11 or parts[0] != "04":
        raise ProtocolError("keine Zeitprogramm-Zeile")
    days = [decode_chrono_day(p) for p in parts[1:8]]
    try:
        temps = [int(p, 16) for p in parts[8:11]]
    except ValueError as err:
        raise ProtocolError("Chrono-Temperatur ist keine Hex-Zahl") from err
    return {"days": days, "temperatures": temps}


def build_chrono_day(day: int, slots: list[int]) -> str:
    """Tagesprogramm schreiben (ScriviGiornoChrono)."""
    if not 0 <= day <= 6:
        raise ValueError("Tag muss zwischen 0 (Sonntag) und 6 (Samstag) liegen")
    return f"C|C|ScriviGiornoChrono|{day}|{encode_chrono_day(slots)}"


def build_clock(when: datetime) -> str:
    """Datum und Uhrzeit des Ofens stellen (SalvaDataOra|TTMMJJJJhhmm)."""
    return f"C|C|SalvaDataOra|{when:%d%m%Y%H%M}"


# --- Zusatzparameter (RecuperoParametriExtra) ----------------------------------
# Antwort „03|…“. Nur Felder, deren Bedeutung im Mitschnitt belegt ist.
ROOM_PROBES = {0x00: "thermostat", 0x01: "ambient", 0xFF: "wifi"}
RELAY_AUX = {0xFF: "not_connected", 0x01: "buffer_pump"}


def decode_extra(frame: str) -> dict[str, Any]:
    """Zusatzparameter lesen: Fühlerquelle, Eco-Stop-Werte, Relais."""
    parts = frame.split("|")
    if len(parts) < 23 or parts[0] != "03":
        raise ProtocolError("keine Zusatzparameter-Zeile")
    try:
        probe = int(parts[3], 16)
        relay = int(parts[22], 16)
        out: dict[str, Any] = {
            "eco_stop_delay": int(parts[4], 16),
            "eco_hysteresis_neg": int(parts[5], 16),
        }
    except ValueError as err:
        raise ProtocolError("Zusatzparameter ist keine Hex-Zahl") from err
    out["room_probe"] = ROOM_PROBES.get(probe, "unknown")
    out["relay_aux"] = RELAY_AUX.get(relay, "other")
    return out


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
