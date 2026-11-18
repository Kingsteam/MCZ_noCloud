"""Zahlen: Kessel-Solltemperatur und technische Parameter."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import McZConfigEntry
from .const import BOILER_SETPOINT_MAX_C, BOILER_SETPOINT_MIN_C, TECH_PARAMS
from .control import StoveController
from .entity import McZEntity

# Diese technischen Werte meldet der Ofen in den Zusatzparametern zurück
REPORTED_TECH = frozenset({"eco_stop_delay", "eco_hysteresis_neg"})


@dataclass(frozen=True, kw_only=True)
class McZNumberDescription(NumberEntityDescription):
    """Beschreibung einer Zahl."""

    tech: bool = True


def _tech(key: str, unit: str, **kw) -> McZNumberDescription:
    _, _, low, high = TECH_PARAMS[key]
    return McZNumberDescription(
        key=key,
        translation_key=key,
        native_min_value=low,
        native_max_value=high,
        native_step=1,
        native_unit_of_measurement=unit,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        **kw,
    )


NUMBERS: tuple[McZNumberDescription, ...] = (
    McZNumberDescription(
        key="boiler_setpoint",
        translation_key="boiler_setpoint",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=BOILER_SETPOINT_MIN_C,
        native_max_value=BOILER_SETPOINT_MAX_C,
        native_step=1,  # der Ofen nimmt beim Kessel nur ganze Grad an
        mode=NumberMode.BOX,
        tech=False,
    ),
    _tech("boiler_hysteresis_pos", UnitOfTemperature.KELVIN),
    _tech("boiler_hysteresis_neg", UnitOfTemperature.KELVIN),
    _tech("room_hysteresis_pos", UnitOfTemperature.KELVIN),
    _tech("room_hysteresis_neg", UnitOfTemperature.KELVIN),
    _tech("eco_hysteresis_pos", UnitOfTemperature.KELVIN),
    _tech("eco_hysteresis_neg", UnitOfTemperature.KELVIN),
    _tech(
        "eco_stop_delay", UnitOfTime.SECONDS, device_class=NumberDeviceClass.DURATION
    ),
    _tech(
        "pump_min_temperature",
        UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: McZConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Zahlen anlegen."""
    controller = entry.runtime_data.controller
    async_add_entities(McZNumber(controller, entry.entry_id, d) for d in NUMBERS)


class McZNumber(McZEntity, NumberEntity):
    """Ein einstellbarer Wert des Ofens."""

    entity_description: McZNumberDescription

    def __init__(
        self,
        controller: StoveController,
        entry_id: str,
        description: McZNumberDescription,
    ) -> None:
        super().__init__(controller.server, entry_id, description)
        self._controller = controller
        # Werte, die der Ofen nicht meldet: zuletzt von hier gesetzt
        self._attr_assumed_state = (
            description.tech and description.key not in REPORTED_TECH
        )

    @property
    def native_value(self) -> float | None:
        if not self.entity_description.tech:
            return self._server.status.info.get("boiler_setpoint")
        return self._controller.tech_value(self.entity_description.key)

    async def async_set_native_value(self, value: float) -> None:
        if not self.entity_description.tech:
            await self._controller.async_set_boiler_setpoint(value)
        else:
            await self._controller.async_set_tech(
                self.entity_description.key, round(value)
            )
