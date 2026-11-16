"""Simulierter Raumfühler (für die Option „eigener Raumfühler“)."""

from __future__ import annotations

from datetime import timedelta
import random

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval


async def async_setup_platform(
    hass: HomeAssistant, config, add_entities, discovery_info=None
):
    """Raumfühler anlegen."""
    add_entities([SimRoomSensor()])


class SimRoomSensor(SensorEntity):
    """Raumtemperatur Wohnzimmer (erfunden, schwankt leicht)."""

    _attr_name = "Simulator: Raumtemperatur Wohnzimmer"
    _attr_unique_id = "mcz_sim_room"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_should_poll = False
    _attr_native_value = 20.5

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_track_time_interval(self.hass, self._tick, timedelta(seconds=30))
        )

    async def _tick(self, _now) -> None:
        self._attr_native_value = round(
            min(
                22.5, max(19.0, self._attr_native_value + random.choice((-0.1, 0, 0.1)))
            ),
            1,
        )
        self.async_write_ha_state()
