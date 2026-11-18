"""Sensoren des Ofens."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    REVOLUTIONS_PER_MINUTE,
    EntityCategory,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from . import McZConfigEntry
from .entity import McZEntity
from .protocol import ROOM_PROBES, STATES
from .services import DAYS, LEVELS, slots_to_program

STATE_OPTIONS = sorted({*STATES.values(), "error", "unknown"})


@dataclass(frozen=True, kw_only=True)
class McZSensorDescription(SensorEntityDescription):
    """Beschreibung eines Sensors."""

    value: Callable[[dict[str, Any]], Any]
    # Nur anlegen, wenn der Ofen einen Wert meldet (Fühler kann fehlen: FF)
    optional: bool = False


def _temp(key: str, **kw: Any) -> McZSensorDescription:
    return McZSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda i: i.get(key),
        **kw,
    )


SENSORS: tuple[McZSensorDescription, ...] = (
    McZSensorDescription(
        key="state",
        translation_key="state",
        device_class=SensorDeviceClass.ENUM,
        options=STATE_OPTIONS,
        value=lambda i: i.get("state_key"),
    ),
    McZSensorDescription(
        key="state_code",
        translation_key="state_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value=lambda i: i.get("state"),
    ),
    _temp("boiler_temperature"),
    _temp("ambient_temperature"),
    _temp("temperature_setpoint"),
    _temp("fume_temperature"),
    _temp("return_temperature", optional=True),
    _temp("puffer_temperature", optional=True),
    _temp(
        "motherboard_temperature",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    McZSensorDescription(
        key="power_level",
        translation_key="power_level",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda i: i.get("power_level"),
    ),
    McZSensorDescription(
        key="pump_pwm",
        translation_key="pump_pwm",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda i: i.get("pump_pwm"),
    ),
    McZSensorDescription(
        key="fume_fan_rpm",
        translation_key="fume_fan_rpm",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda i: i.get("fume_fan_rpm"),
    ),
    McZSensorDescription(
        key="ignitions",
        translation_key="ignitions",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value=lambda i: i.get("ignitions"),
    ),
    McZSensorDescription(
        key="operating_hours",
        translation_key="operating_hours",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        value=lambda i: (
            None
            if i.get("operating_seconds_total") is None
            else round(i["operating_seconds_total"] / 3600, 1)
        ),
    ),
    McZSensorDescription(
        key="hours_to_service",
        translation_key="hours_to_service",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        value=lambda i: i.get("hours_to_service"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: McZConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Sensoren anlegen; optionale erst, wenn der Ofen einen Wert meldet."""
    server = entry.runtime_data.server
    async_add_entities(
        McZSensor(server, entry.entry_id, d) for d in SENSORS if not d.optional
    )
    pending = {d.key: d for d in SENSORS if d.optional}

    @callback
    def _add_optional() -> None:
        info = server.status.info
        if not info or not pending:
            return
        new = [d for d in pending.values() if d.value(info) is not None]
        for d in new:
            del pending[d.key]
        if new:
            async_add_entities(McZSensor(server, entry.entry_id, d) for d in new)

    entry.async_on_unload(server.add_listener(_add_optional))
    _add_optional()
    async_add_entities(
        [McZRoomProbe(server, entry.entry_id), McZChrono(server, entry.entry_id)]
    )


class McZSensor(McZEntity, SensorEntity):
    """Ein Messwert des Ofens."""

    entity_description: McZSensorDescription

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self._server.status.info)


class McZRoomProbe(McZEntity, SensorEntity):
    """Woher der Ofen die Raumtemperatur nimmt (nur lesen, siehe const.py)."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, server, entry_id: str) -> None:
        super().__init__(
            server,
            entry_id,
            SensorEntityDescription(key="room_probe", translation_key="room_probe"),
        )
        self._attr_options = [*sorted(set(ROOM_PROBES.values())), "unknown"]

    @property
    def native_value(self) -> str | None:
        return self._server.status.extra.get("room_probe")


class McZChrono(McZEntity, SensorEntity):
    """Zeitprogramm: Zustand = Stufe jetzt, Attribute = Programm je Tag."""

    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(self, server, entry_id: str) -> None:
        super().__init__(
            server,
            entry_id,
            SensorEntityDescription(
                key="chrono_program", translation_key="chrono_program"
            ),
        )
        self._attr_options = list(LEVELS)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Stufe wechselt zur halben Stunde, auch ohne neue Daten vom Ofen
        self.async_on_remove(
            async_track_time_interval(self.hass, self._tick, timedelta(minutes=1))
        )

    @callback
    def _tick(self, _now: datetime) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return super().available and bool(self._server.status.chrono)

    @property
    def native_value(self) -> str | None:
        chrono = self._server.status.chrono
        if not chrono:
            return None
        now = dt_util.now()
        day = (now.weekday() + 1) % 7  # Python: Montag 0; Ofen: Sonntag 0
        level = chrono["days"][day][now.hour * 2 + now.minute // 30]
        return {v: k for k, v in LEVELS.items()}[level]

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        chrono = self._server.status.chrono
        if not chrono:
            return None
        t1, t2, t3 = chrono["temperatures"]
        attrs: dict[str, Any] = {"t1": t1, "t2": t2, "t3": t3}
        for name, num in DAYS.items():
            attrs[name] = slots_to_program(chrono["days"][num])
        return attrs
