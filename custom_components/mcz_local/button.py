"""Knopf: Uhr des Ofens stellen."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import McZConfigEntry
from .control import StoveController
from .entity import McZEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: McZConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Knopf anlegen."""
    async_add_entities([McZClockButton(entry.runtime_data.controller, entry.entry_id)])


class McZClockButton(McZEntity, ButtonEntity):
    """Datum und Uhrzeit des Ofens auf die Zeit von Home Assistant stellen."""

    def __init__(self, controller: StoveController, entry_id: str) -> None:
        super().__init__(
            controller.server,
            entry_id,
            ButtonEntityDescription(
                key="sync_clock",
                translation_key="sync_clock",
                entity_category=EntityCategory.CONFIG,
            ),
        )
        self._controller = controller

    async def async_press(self) -> None:
        await self._controller.async_sync_clock(dt_util.now())
