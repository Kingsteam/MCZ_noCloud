"""MCZ Maestro lokal: Pelletofen ohne Cloud.

Die Integration startet einen kleinen Server, mit dem sich der Ofen statt mit
der MCZ-Cloud verbindet (siehe server.py), und stellt seine Werte als
Entitäten bereit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    issue_registry as ir,
)
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .const import (
    CLOCK_SYNC_INTERVAL_S,
    CONF_PORT,
    CONF_SYNC_CLOCK,
    DEFAULT_PORT,
    DEFAULT_SYNC_CLOCK,
    DOMAIN,
    LISTEN_HOST,
    NETWORK_DOCS_URL,
    NOT_CONNECTED_ISSUE_DELAY_S,
    POLL_INTERVAL_S,
)
from .control import StoveController
from .server import McZServer
from .services import async_setup_services

ISSUE_NOT_CONNECTED = "stove_not_connected"

_LOGGER = logging.getLogger(__name__)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Dienste einmalig registrieren."""
    async_setup_services(hass)
    return True


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

    # Einrichtungshilfe: meldet sich der Ofen nicht, Hinweis mit Netzwerk-Anleitung
    @callback
    def _check_connected(_now: object) -> None:
        if server.status.connected:
            return
        ir.async_create_issue(
            hass,
            DOMAIN,
            ISSUE_NOT_CONNECTED,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_NOT_CONNECTED,
            translation_placeholders={"port": str(server.port)},
            learn_more_url=NETWORK_DOCS_URL,
        )

    @callback
    def _clear_issue() -> None:
        if server.status.connected:
            ir.async_delete_issue(hass, DOMAIN, ISSUE_NOT_CONNECTED)

    entry.async_on_unload(
        async_call_later(hass, NOT_CONNECTED_ISSUE_DELAY_S, _check_connected)
    )
    entry.async_on_unload(server.add_join_listener(_clear_issue))

    # Uhr des Ofens stellen: bei jeder Anmeldung und danach regelmäßig. Sonst
    # läuft das Zeitprogramm nach einer Zeitumstellung zur falschen Zeit.
    if entry.options.get(CONF_SYNC_CLOCK, DEFAULT_SYNC_CLOCK):

        async def _sync_clock(*_args: object) -> None:
            if not server.status.connected:
                return
            try:
                await controller.async_sync_clock(dt_util.now())
            except HomeAssistantError as err:
                _LOGGER.debug("Uhr nicht gestellt: %s", err)

        @callback
        def _on_join() -> None:
            entry.async_create_background_task(
                hass, _sync_clock(), "mcz_local_sync_clock"
            )

        entry.async_on_unload(server.add_join_listener(_on_join))
        if server.status.connected:  # Ofen hat sich schon während des Setups gemeldet
            _on_join()
        entry.async_on_unload(
            async_track_time_interval(
                hass, _sync_clock, timedelta(seconds=CLOCK_SYNC_INTERVAL_S)
            )
        )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: McZConfigEntry) -> bool:
    """Eintrag entladen: Entitäten entfernen, Server stoppen."""
    ir.async_delete_issue(hass, DOMAIN, ISSUE_NOT_CONNECTED)
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.server.stop()
    return ok
