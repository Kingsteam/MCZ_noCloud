"""Tests für die Einrichtung über die Oberfläche."""

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mcz_local.const import CONF_PORT, DOMAIN


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    """Formular zeigen, Port übernehmen, Eintrag anlegen."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PORT: 9100}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_PORT: 9100}


async def test_only_one_entry(hass: HomeAssistant) -> None:
    """Eine zweite Einrichtung wird abgelehnt."""
    MockConfigEntry(domain=DOMAIN, data={CONF_PORT: 9000}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_setup_and_unload(hass: HomeAssistant) -> None:
    """Eintrag lässt sich laden und entladen."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_PORT: 9000})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert entry.runtime_data.port == 9000
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is config_entries.ConfigEntryState.NOT_LOADED
