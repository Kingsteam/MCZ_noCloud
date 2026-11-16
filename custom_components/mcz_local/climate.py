"""Thermostat-Entität: Ein/Aus und Solltemperatur des Ofens."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityDescription,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from . import McZConfigEntry
from .const import CONF_ROOM_SENSOR, SETPOINT_MAX_C, SETPOINT_MIN_C
from .control import StoveController
from .entity import McZEntity

# Zustände, in denen der Ofen als „aus“ gilt (sonst eingeschaltet)
OFF_STATES = frozenset({"off", "switching_off", "cooling"})
IDLE_STATES = frozenset({"standby", "auto_eco"})

DESCRIPTION = ClimateEntityDescription(
    key="climate", translation_key="stove", name=None
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: McZConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Thermostat anlegen."""
    room_sensor = None
    if registry_id := entry.options.get(CONF_ROOM_SENSOR):
        reg_entry = er.async_get(hass).async_get(registry_id)
        room_sensor = reg_entry.entity_id if reg_entry else None
    async_add_entities(
        [
            McZClimate(
                entry.runtime_data.controller, entry.entry_id, DESCRIPTION, room_sensor
            )
        ]
    )


class McZClimate(McZEntity, ClimateEntity):
    """Der Ofen als Thermostat."""

    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_min_temp = SETPOINT_MIN_C
    _attr_max_temp = SETPOINT_MAX_C

    def __init__(
        self,
        controller: StoveController,
        entry_id: str,
        description: ClimateEntityDescription,
        room_sensor: str | None,
    ) -> None:
        super().__init__(controller.server, entry_id, description)
        self._controller = controller
        self._room_sensor = room_sensor
        self._attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._room_sensor:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, [self._room_sensor], self._on_room_sensor
                )
            )

    @callback
    def _on_room_sensor(self, _event: Event[EventStateChangedData]) -> None:
        self.async_write_ha_state()

    @property
    def _info(self) -> dict[str, Any]:
        return self._server.status.info

    @property
    def current_temperature(self) -> float | None:
        """Externer Raumfühler, falls eingestellt und gültig, sonst Ofenfühler."""
        if self._room_sensor and (state := self.hass.states.get(self._room_sensor)):
            try:
                return float(state.state)
            except ValueError:
                pass
        return self._info.get("ambient_temperature")

    @property
    def target_temperature(self) -> float | None:
        return self._info.get("temperature_setpoint")

    @property
    def hvac_mode(self) -> HVACMode | None:
        key = self._info.get("state_key")
        if key is None:
            return None
        return HVACMode.OFF if key in OFF_STATES else HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction | None:
        key = self._info.get("state_key")
        if key is None:
            return None
        if self._info.get("burning"):
            return HVACAction.HEATING
        if key in IDLE_STATES:
            return HVACAction.IDLE
        return HVACAction.OFF

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "stove_ambient_temperature": self._info.get("ambient_temperature"),
            "room_sensor": self._room_sensor,
        }

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self._controller.async_turn_off()
        else:
            await self._controller.async_turn_on()

    async def async_turn_on(self) -> None:
        await self._controller.async_turn_on()

    async def async_turn_off(self) -> None:
        await self._controller.async_turn_off()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (temp := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self._controller.async_set_setpoint(float(temp))
