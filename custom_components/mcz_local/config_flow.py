"""Einrichtung über die Oberfläche."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector
import voluptuous as vol

from .const import CONF_PORT, DEFAULT_PORT, DOMAIN

PORT_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=1024, max=65535, step=1, mode=selector.NumberSelectorMode.BOX
    )
)


class McZConfigFlow(ConfigFlow, domain=DOMAIN):
    """Einrichtungsdialog."""

    VERSION = 1

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
