"""Schalter: Eco, Chrono, Töne."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import McZConfigEntry
from .control import FLAGS, StoveController
from .entity import McZEntity

SWITCHES: tuple[SwitchEntityDescription, ...] = (
    SwitchEntityDescription(key="eco_mode", translation_key="eco_mode"),
    SwitchEntityDescription(key="chronostat", translation_key="chronostat"),
    SwitchEntityDescription(
        key="sound_effects",
        translation_key="sound_effects",
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: McZConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Schalter anlegen."""
    controller = entry.runtime_data.controller
    async_add_entities(McZSwitch(controller, entry.entry_id, d) for d in SWITCHES)


class McZSwitch(McZEntity, SwitchEntity):
    """Ein Ein/Aus-Parameter des Ofens."""

    def __init__(
        self,
        controller: StoveController,
        entry_id: str,
        description: SwitchEntityDescription,
    ) -> None:
        super().__init__(controller.server, entry_id, description)
        self._controller = controller

    @property
    def is_on(self) -> bool | None:
        value = self._server.status.info.get(FLAGS[self.entity_description.key][1])
        return None if value is None else bool(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._controller.async_set_flag(self.entity_description.key, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._controller.async_set_flag(self.entity_description.key, False)
