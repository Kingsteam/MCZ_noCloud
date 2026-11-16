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

# Parameter-IDs der Schreibbefehle (WriteParametri)
CMD_POWER: Final = 34  # Ein/Aus - nur aus Community-Angaben, nicht im Mitschnitt
POWER_ON: Final = 1
POWER_OFF: Final = 40
CMD_ECO: Final = 41
CMD_SETPOINT: Final = 42  # Wert = Grad mal 2
CMD_SOUND: Final = 50
CMD_CHRONO: Final = 1111

# Abfrage-Takt für den Status („RecuperoInfo“), Sekunden
POLL_INTERVAL_S: Final = 10

# ---------------------------------------------------------------------------
# SICHERHEIT - Grenzen für Befehle an den Ofen
# ---------------------------------------------------------------------------

# Nur diese Parameter-IDs dürfen je per „WriteParametri“ geschrieben werden.
# 34 Ein/Aus, 41 Eco, 42 Solltemperatur (mal 2), 50 Töne, 1111 Chrono.
ALLOWED_WRITE_IDS: Final[frozenset[int]] = frozenset({34, 41, 42, 50, 1111})

# Solltemperatur Raum in °C (Ofen rechnet intern in halben Grad)
SETPOINT_MIN_C: Final = 5.0
SETPOINT_MAX_C: Final = 30.0

# Mindestabstand zwischen zwei Schreibbefehlen, Sekunden
MIN_WRITE_GAP_S: Final = 1.0

# Gegen Takten: Mindestpause zwischen „Aus“ und erneutem „Ein“, Sekunden
MIN_OFF_BEFORE_ON_S: Final = 30 * 60
