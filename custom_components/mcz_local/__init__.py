"""MCZ Maestro lokal: Pelletofen ohne Cloud.

Phase 1: nur Grundgerüst. Der Server für den Ofen folgt in Phase 2.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_PORT, DEFAULT_PORT


@dataclass
class McZData:
    """Laufzeitdaten eines Eintrags."""

    port: int


type McZConfigEntry = ConfigEntry[McZData]


async def async_setup_entry(hass: HomeAssistant, entry: McZConfigEntry) -> bool:
    """Eintrag einrichten."""
    entry.runtime_data = McZData(port=entry.data.get(CONF_PORT, DEFAULT_PORT))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: McZConfigEntry) -> bool:
    """Eintrag entladen."""
    return True
