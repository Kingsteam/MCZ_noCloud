"""MCZ Maestro lokal: Pelletofen ohne Cloud.

Die Integration startet einen kleinen Server, mit dem sich der Ofen statt mit
der MCZ-Cloud verbindet (siehe server.py), und stellt seine Werte als
Entitäten bereit.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .const import CONF_PORT, DEFAULT_PORT, DOMAIN, LISTEN_HOST, POLL_INTERVAL_S
from .control import StoveController
from .server import McZServer

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.SENSOR,
    Platform.SWITCH,
]


@dataclass
class McZData:
    """Laufzeitdaten eines Eintrags."""

    server: McZServer
    controller: StoveController


type McZConfigEntry = ConfigEntry[McZData]


async def async_setup_entry(hass: HomeAssistant, entry: McZConfigEntry) -> bool:
    """Eintrag einrichten: Server starten, Entitäten anlegen."""
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
    controller = StoveController(hass, server, entry.entry_id)
    await controller.async_load()
    entry.async_on_unload(server.add_listener(controller.observe))
    entry.runtime_data = McZData(server=server, controller=controller)

    async def _stop(_event: Event) -> None:
        await server.stop()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Seriennummer und Firmware ins Gerät eintragen, sobald der Ofen sich meldet
    known: dict[str, str | None] = {}

    @callback
    def _update_device() -> None:
        ident = server.status.identity
        if not ident or ident == known:
            return
        known.clear()
        known.update(ident)
        registry = dr.async_get(hass)
        for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
            registry.async_update_device(
                device.id,
                serial_number=ident.get("serialNumber"),
                sw_version=ident.get("revision"),
            )

    entry.async_on_unload(server.add_listener(_update_device))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: McZConfigEntry) -> bool:
    """Eintrag entladen: Entitäten entfernen, Server stoppen."""
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.server.stop()
    return ok
