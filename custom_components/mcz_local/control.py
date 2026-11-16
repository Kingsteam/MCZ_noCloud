"""Steuerung des Ofens mit Schutzgrenzen (alle Grenzen aus const.py).

- Befehle nur, wenn der Ofen verbunden ist.
- Einschalten nicht bei Störung und nicht vor Ablauf der Mindestpause nach dem
  letzten Ausschalten (gegen Takten). Der Zeitpunkt wird gespeichert und
  übersteht einen Neustart von Home Assistant.
- Solltemperatur nur innerhalb der Grenzen.
"""

from __future__ import annotations

import logging
import time

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.storage import Store

from . import protocol as P
from .const import (
    CMD_CHRONO,
    CMD_ECO,
    CMD_POWER,
    CMD_SETPOINT,
    CMD_SOUND,
    DOMAIN,
    MIN_OFF_BEFORE_ON_S,
    POWER_OFF,
    POWER_ON,
    SETPOINT_MAX_C,
    SETPOINT_MIN_C,
)
from .server import McZServer, NotConnectedError

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1

FLAGS: dict[str, tuple[int, str]] = {
    # Schalter-Schlüssel -> (Parameter-ID, Feld in der Statuszeile)
    "eco_mode": (CMD_ECO, "eco_mode"),
    "chronostat": (CMD_CHRONO, "chronostat"),
    "sound_effects": (CMD_SOUND, "sound_effects"),
}


def _error(key: str, **placeholders: str) -> HomeAssistantError:
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders=placeholders or None,
    )


class StoveController:
    """Einzige Stelle, die Befehle an den Ofen schickt."""

    def __init__(self, hass: HomeAssistant, server: McZServer, entry_id: str) -> None:
        self.hass = hass
        self.server = server
        self._store: Store[dict] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}")
        self.last_stop: float | None = None  # time.time() des letzten Ausgehens
        self._was_burning: bool | None = None

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.last_stop = data.get("last_stop")

    @callback
    def observe(self) -> None:
        """Ausgehen des Ofens erkennen, egal wer ihn ausgeschaltet hat."""
        info = self.server.status.info
        if not info:
            return
        burning = bool(info.get("burning"))
        if self._was_burning and not burning:
            self._mark_stop()
        self._was_burning = burning

    def _mark_stop(self) -> None:
        self.last_stop = time.time()
        self._store.async_delay_save(lambda: {"last_stop": self.last_stop}, 1)

    def seconds_until_on_allowed(self) -> float:
        if self.last_stop is None:
            return 0.0
        return max(0.0, self.last_stop + MIN_OFF_BEFORE_ON_S - time.time())

    async def _write(self, param_id: int, value: int) -> None:
        try:
            await self.server.async_write(param_id, value)
        except NotConnectedError as err:
            raise _error("not_connected") from err

    # --- Befehle ---------------------------------------------------------------
    async def async_turn_on(self) -> None:
        info = self.server.status.info
        if not self.server.status.connected:
            raise _error("not_connected")
        if info.get("state_key") == "error":
            raise _error("stove_error")
        if info.get("burning"):
            return  # läuft schon
        if (wait := self.seconds_until_on_allowed()) > 0:
            raise _error("too_soon", minutes=str(int(wait // 60) + 1))
        await self._write(CMD_POWER, POWER_ON)

    async def async_turn_off(self) -> None:
        await self._write(CMD_POWER, POWER_OFF)
        self._mark_stop()

    async def async_set_setpoint(self, celsius: float) -> None:
        try:
            raw = P.setpoint_raw(celsius)
        except ValueError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="setpoint_out_of_range",
                translation_placeholders={
                    "min": str(SETPOINT_MIN_C),
                    "max": str(SETPOINT_MAX_C),
                },
            ) from err
        await self._write(CMD_SETPOINT, raw)

    async def async_set_flag(self, key: str, on: bool) -> None:
        param_id, _ = FLAGS[key]
        await self._write(param_id, 1 if on else 0)
