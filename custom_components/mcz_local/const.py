"""Konstanten für mcz_local.

Sicherheitskritische Grenzen stehen gesammelt im Abschnitt SICHERHEIT.
Sie werden in tests/test_const.py geprüft. Nur nach Rücksprache ändern.
"""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "mcz_local"

CONF_PORT: Final = "port"
DEFAULT_PORT: Final = 9000
# Auf allen Adressen lauschen; der Router leitet nur den Ofen hierher um
LISTEN_HOST: Final = "0.0.0.0"

CONF_ROOM_SENSOR: Final = "room_sensor"  # Entitätsregister-ID, nicht entity_id
CONF_SYNC_CLOCK: Final = "sync_clock"  # Uhr des Ofens automatisch stellen
DEFAULT_SYNC_CLOCK: Final = True

# Parameter-IDs der Schreibbefehle (WriteParametri), alle im Mitschnitt mit
# der MCZ-App bestätigt (siehe docs/PROTOKOLL.md)
CMD_POWER: Final = 34
POWER_ON: Final = 1
POWER_OFF: Final = 40
CMD_ECO: Final = 41
CMD_SETPOINT: Final = 42  # Wert = Grad mal 2
CMD_SOUND: Final = 50
CMD_BOILER_SETPOINT: Final = 51  # Kessel-Solltemperatur, Wert = Grad mal 2
CMD_SEASON: Final = 58
SEASON_WINTER: Final = 0  # im Mitschnitt bestätigt
SEASON_SUMMER: Final = 1  # angenommen, noch nicht beobachtet
CMD_CHRONO: Final = 1111

# Abfrage-Takt für den Status („RecuperoInfo“), Sekunden
POLL_INTERVAL_S: Final = 10
# Seltener: Zusatzparameter und Zeitprogramm, alle n Status-Abfragen
SLOW_POLL_EVERY: Final = 30
# Uhr des Ofens stellen: bei jeder Anmeldung und danach so oft (Sekunden)
CLOCK_SYNC_INTERVAL_S: Final = 6 * 3600

# ---------------------------------------------------------------------------
# SICHERHEIT - Grenzen für Befehle an den Ofen
# ---------------------------------------------------------------------------

# Nur diese Parameter-IDs dürfen je per „WriteParametri“ geschrieben werden.
# 34 Ein/Aus, 41 Eco, 42 Solltemperatur (mal 2), 50 Töne,
# 51 Kessel-Solltemperatur (mal 2), 58 Sommer/Winter, 1111 Chrono.
# Bewusst NICHT: 148 (Pelletstand-Sensor; ohne Sensor droht eine Störung).
ALLOWED_WRITE_IDS: Final[frozenset[int]] = frozenset({34, 41, 42, 50, 51, 58, 1111})
ALLOWED_SEASON_VALUES: Final[frozenset[int]] = frozenset({SEASON_WINTER, SEASON_SUMMER})

# Solltemperatur Raum in °C (Ofen rechnet intern in halben Grad)
SETPOINT_MIN_C: Final = 5.0
SETPOINT_MAX_C: Final = 30.0

# Kessel-Solltemperatur (Wasser) in °C
BOILER_SETPOINT_MIN_C: Final = 50.0
BOILER_SETPOINT_MAX_C: Final = 80.0

# Technische Parameter („WriteTecniciParametri|ID|Bytes|Hex“): nur diese,
# nur in diesen Grenzen. Schlüssel -> (ID, Bytes, Minimum, Maximum).
# Bewusst NICHT: 356 (Quelle Raumfühler) und 365 (Relais-Ausgang). Das ist
# die Verdrahtung der Anlage; ein falscher Wert legt die Regelung lahm
# (im Mitschnitt gesehen: Raumtemperatur 126 °C) oder schaltet fremde Geräte.
TECH_PARAMS: Final[dict[str, tuple[int, int, int, int]]] = {
    "boiler_hysteresis_pos": (297, 1, 0, 10),  # K über Kessel-Soll
    "boiler_hysteresis_neg": (296, 1, 1, 10),  # K unter Kessel-Soll bis Neustart
    "room_hysteresis_pos": (289, 1, 0, 3),
    "room_hysteresis_neg": (288, 1, 0, 3),
    "eco_hysteresis_pos": (295, 1, 0, 5),
    "eco_hysteresis_neg": (294, 1, 0, 5),
    "eco_stop_delay": (148, 2, 60, 1800),  # Sekunden
    "pump_min_temperature": (517, 1, 40, 70),  # °C Wasser, ab dann Pumpe an
}
FORBIDDEN_TECH_IDS: Final[frozenset[int]] = frozenset({356, 365})

# Mindestabstand zwischen zwei Schreibbefehlen, Sekunden
MIN_WRITE_GAP_S: Final = 1.0

# Gegen Takten: Mindestpause zwischen „Aus“ und erneutem „Ein“, Sekunden
MIN_OFF_BEFORE_ON_S: Final = 30 * 60
