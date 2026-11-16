"""MCZ Maestro lokal: Pelletofen ohne Cloud.

Die Integration startet einen kleinen Server, mit dem sich der Ofen statt mit
der MCZ-Cloud verbindet (siehe server.py). Entitäten folgen in Phase 3.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_PORT, DEFAULT_PORT, DOMAIN, LISTEN_HOST, POLL_INTERVAL_S
from .server import McZServer


@dataclass
class McZData:
    """Laufzeitdaten eines Eintrags."""

    server: McZServer


type McZConfigEntry = ConfigEntry[McZData]


async def async_setup_entry(hass: HomeAssistant, entry: McZConfigEntry) -> bool:
    """Eintrag einrichten: Server starten."""
    server = McZServer(
        LISTEN_HOST, entry.data.get(CONF_PORT, DEFAULT_PORT), POLL_INTERVAL_S
    )
    try:
        await server.start()
    except OSError as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="port_in_use",
            translation_placeholders={"port": str(server.port), "error": str(err)},
        ) from err
    entry.runtime_data = McZData(server=server)

    async def _stop(_event: Event) -> None:
        await server.stop()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: McZConfigEntry) -> bool:
    """Eintrag entladen: Server stoppen."""
    await entry.runtime_data.server.stop()
    return True
