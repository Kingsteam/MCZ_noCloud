"""Auswahl: Sommer/Winter."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import McZConfigEntry
from .const import SEASON_SUMMER, SEASON_WINTER
from .control import StoveController
from .entity import McZEntity

SEASONS: dict[str, int] = {"winter": SEASON_WINTER, "summer": SEASON_SUMMER}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: McZConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Auswahl anlegen."""
    async_add_entities([McZSeason(entry.runtime_data.controller, entry.entry_id)])


class McZSeason(McZEntity, SelectEntity):
    """Sommer/Winter. Der Ofen meldet das nicht zurück: Anzeige = zuletzt gesetzt."""

    _attr_assumed_state = True

    def __init__(self, controller: StoveController, entry_id: str) -> None:
        super().__init__(
            controller.server,
            entry_id,
            SelectEntityDescription(key="season", translation_key="season"),
        )
        self._controller = controller
        self._attr_options = list(SEASONS)

    @property
    def current_option(self) -> str | None:
        value = self._controller.assumed.get("season")
        return next((k for k, v in SEASONS.items() if v == value), None)

    async def async_select_option(self, option: str) -> None:
        await self._controller.async_set_season(SEASONS[option])
