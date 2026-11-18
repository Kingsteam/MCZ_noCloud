"""Einrichtung über die Oberfläche."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er, selector
import voluptuous as vol

from .const import (
    CONF_PORT,
    CONF_ROOM_SENSOR,
    CONF_SYNC_CLOCK,
    DEFAULT_PORT,
    DEFAULT_SYNC_CLOCK,
    DOMAIN,
)

PORT_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=1024, max=65535, step=1, mode=selector.NumberSelectorMode.BOX
    )
)


class McZConfigFlow(ConfigFlow, domain=DOMAIN):
    """Einrichtungsdialog."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> McZOptionsFlow:
        """Optionen: externer Raumfühler."""
        return McZOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Port abfragen, auf dem der Ofen sich melden soll."""
        if user_input is not None:
            return self.async_create_entry(
                title="MCZ Pelletofen",
                data={CONF_PORT: int(user_input[CONF_PORT])},
            )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_PORT, default=DEFAULT_PORT): PORT_SELECTOR}
            ),
        )


class McZOptionsFlow(OptionsFlowWithReload):
    """Optionen: externer Raumfühler für das Thermostat.

    Gespeichert wird die ID aus dem Entitätsregister, nicht die entity_id:
    so bleibt der Bezug erhalten, wenn der Fühler umbenannt wird.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        registry = er.async_get(self.hass)
        errors: dict[str, str] = {}
        if user_input is not None:
            data: dict[str, Any] = {
                CONF_SYNC_CLOCK: bool(
                    user_input.get(CONF_SYNC_CLOCK, DEFAULT_SYNC_CLOCK)
                )
            }
            entity_id = user_input.get(CONF_ROOM_SENSOR)
            if not entity_id:
                return self.async_create_entry(data=data)
            if reg_entry := registry.async_get(entity_id):
                data[CONF_ROOM_SENSOR] = reg_entry.id
                return self.async_create_entry(data=data)
            errors[CONF_ROOM_SENSOR] = "sensor_not_registered"

        current = None
        registry_id = self.config_entry.options.get(CONF_ROOM_SENSOR)
        if registry_id and (reg_entry := registry.async_get(registry_id)):
            current = reg_entry.entity_id
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_ROOM_SENSOR,
                    description={"suggested_value": current},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor", device_class="temperature"
                    )
                ),
                vol.Optional(
                    CONF_SYNC_CLOCK,
                    default=self.config_entry.options.get(
                        CONF_SYNC_CLOCK, DEFAULT_SYNC_CLOCK
                    ),
                ): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
