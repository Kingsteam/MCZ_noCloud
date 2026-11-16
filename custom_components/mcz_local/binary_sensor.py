"""Binärsensoren: Verbindung zum Ofen, Ofen in Betrieb, Störung."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import McZConfigEntry
from .entity import McZEntity
from .server import StoveStatus


@dataclass(frozen=True, kw_only=True)
class McZBinaryDescription(BinarySensorEntityDescription):
    """Beschreibung eines Binärsensors."""

    value: Callable[[StoveStatus], bool | None]
    always_available: bool = False


BINARY_SENSORS: tuple[McZBinaryDescription, ...] = (
    McZBinaryDescription(
        key="connected",
        translation_key="connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        always_available=True,
        value=lambda s: s.connected,
    ),
    McZBinaryDescription(
        key="burning",
        translation_key="burning",
        device_class=BinarySensorDeviceClass.RUNNING,
        value=lambda s: s.info.get("burning"),
    ),
    McZBinaryDescription(
        key="error",
        translation_key="error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value=lambda s: s.info.get("state_key") == "error",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: McZConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Binärsensoren anlegen."""
    server = entry.runtime_data.server
    async_add_entities(
        McZBinarySensor(server, entry.entry_id, d) for d in BINARY_SENSORS
    )


class McZBinarySensor(McZEntity, BinarySensorEntity):
    """Ein Ja/Nein-Wert des Ofens."""

    entity_description: McZBinaryDescription

    @property
    def available(self) -> bool:
        if self.entity_description.always_available:
            return True
        return super().available

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value(self._server.status)
