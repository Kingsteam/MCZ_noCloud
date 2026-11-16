"""Gemeinsame Basis für alle Entitäten des Ofens."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription

from .const import DOMAIN
from .server import McZServer


def device_info(entry_id: str) -> DeviceInfo:
    """Gerät des Ofens. Kennung ist der Config-Eintrag, nicht die Seriennummer:
    die kommt erst mit der Anmeldung des Ofens und wird dann nachgetragen."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        manufacturer="MCZ",
        model="Maestro",
        name="Pelletofen",
    )


class McZEntity(Entity):
    """Entität, die bei jeder Statusänderung des Servers aktualisiert wird."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self, server: McZServer, entry_id: str, description: EntityDescription
    ) -> None:
        self._server = server
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"
        self._attr_device_info = device_info(entry_id)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._server.add_listener(self._on_update))

    @callback
    def _on_update(self) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Werte gibt es nur, solange der Ofen verbunden ist und gemeldet hat."""
        return self._server.status.connected and bool(self._server.status.info)
