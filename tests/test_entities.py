"""Tests der Entitäten mit simuliertem Ofen."""

import asyncio
import socket

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mcz_local.const import CONF_PORT, DOMAIN
from custom_components.mcz_local.protocol import STATES
from custom_components.mcz_local.sensor import STATE_OPTIONS

from .fake_stove import FakeStove

pytestmark = pytest.mark.usefixtures("socket_enabled")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def until(hass: HomeAssistant, cond, timeout: float = 5) -> None:
    async with asyncio.timeout(timeout):
        while not cond():
            await asyncio.sleep(0.01)
    await hass.async_block_till_done()


def eid(hass: HomeAssistant, platform: str, key: str, entry) -> str:
    """entity_id über das Register finden (nicht über den Namen)."""
    entity_id = er.async_get(hass).async_get_entity_id(
        platform, DOMAIN, f"{entry.entry_id}_{key}"
    )
    assert entity_id, key
    return entity_id


@pytest.fixture
async def setup(hass: HomeAssistant):
    port = free_port()
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_PORT: port})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entry.runtime_data.server.poll_interval = 0.05
    yield hass, entry, port
    await hass.config_entries.async_unload(entry.entry_id)


async def test_unavailable_until_stove_connects(setup) -> None:
    """Ohne Ofen: Sensoren nicht verfügbar, „verbunden“ ist aus."""
    hass, entry, _ = setup
    assert (
        hass.states.get(eid(hass, "binary_sensor", "connected", entry)).state
        == STATE_OFF
    )
    state = hass.states.get(eid(hass, "sensor", "boiler_temperature", entry))
    assert state.state == STATE_UNAVAILABLE


async def test_values_device_and_disconnect(setup) -> None:
    """Werte kommen an, Gerät bekommt Firmware, Trennen macht Sensoren unverfügbar."""
    hass, entry, port = setup
    server = entry.runtime_data.server
    stove = FakeStove(
        port, {1: 12, 6: 41, 7: 0xFF, 8: 120, 26: 42, 45: 7, 59: 90, 37: 0}
    )
    await stove.connect()
    await until(hass, lambda: server.status.info.get("state") == 12)

    assert (
        hass.states.get(eid(hass, "binary_sensor", "connected", entry)).state
        == STATE_ON
    )
    assert (
        hass.states.get(eid(hass, "binary_sensor", "burning", entry)).state == STATE_ON
    )
    assert (
        hass.states.get(eid(hass, "binary_sensor", "error", entry)).state == STATE_OFF
    )
    assert hass.states.get(eid(hass, "sensor", "state", entry)).state == "power2"
    assert (
        hass.states.get(eid(hass, "sensor", "boiler_temperature", entry)).state
        == "60.0"
    )
    assert (
        hass.states.get(eid(hass, "sensor", "ambient_temperature", entry)).state
        == "20.5"
    )
    assert hass.states.get(eid(hass, "sensor", "ignitions", entry)).state == "7"
    # Rücklauf ist angeschlossen (Wert 45 °C), Puffer nicht (FF) -> nicht angelegt
    assert (
        hass.states.get(eid(hass, "sensor", "return_temperature", entry)).state
        == "45.0"
    )
    assert (
        er.async_get(hass).async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_puffer_temperature"
        )
        is None
    )

    registry = dr.async_get(hass)
    (device,) = dr.async_entries_for_config_entry(registry, entry.entry_id)
    assert (DOMAIN, entry.entry_id) in device.identifiers
    assert device.sw_version == "9.9.9"
    assert device.serial_number == "1234567890123"

    stove.fields[1] = 53  # Störung
    await until(hass, lambda: server.status.info.get("state") == 53)
    assert hass.states.get(eid(hass, "sensor", "state", entry)).state == "error"
    assert hass.states.get(eid(hass, "binary_sensor", "error", entry)).state == STATE_ON

    await stove.close()
    await until(hass, lambda: not server.status.connected)
    assert (
        hass.states.get(eid(hass, "binary_sensor", "connected", entry)).state
        == STATE_OFF
    )
    assert (
        hass.states.get(eid(hass, "sensor", "boiler_temperature", entry)).state
        == STATE_UNAVAILABLE
    )


def test_state_options_cover_all_states() -> None:
    """Jeder Zustand hat eine Auswahl-Option, Schlüssel sind gültig."""
    assert set(STATES.values()) | {"error", "unknown"} == set(STATE_OPTIONS)
    for key in STATE_OPTIONS:
        assert key == key.strip("_-")
        assert all(c.isdigit() or c.islower() or c in "_-" for c in key)
