"""Tests: Integration startet den Server, Ofen verbindet sich, Entladen stoppt ihn."""

import asyncio
import socket

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mcz_local.const import CONF_PORT, DOMAIN

from .fake_stove import FAKE_IDENTITY, FakeStove

pytestmark = pytest.mark.usefixtures("socket_enabled")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def test_setup_stove_connects_and_unload(hass: HomeAssistant) -> None:
    """Server läuft nach dem Einrichten, simulierter Ofen meldet sich an."""
    port = free_port()
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_PORT: port})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.LOADED
    server = entry.runtime_data.server

    stove = FakeStove(port, {1: 31, 8: 130})
    await stove.connect()
    async with asyncio.timeout(5):
        while server.status.info.get("state") != 31:
            await asyncio.sleep(0.01)
    assert server.status.identity == FAKE_IDENTITY
    assert server.status.info["boiler_temperature"] == 65.0

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    await stove.close()
    # Port ist wieder frei (wie beim Neuladen der Integration)
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", port))


async def test_port_in_use_retries_later(hass: HomeAssistant) -> None:
    """Ist der Port belegt, versucht HA es später erneut (kein Absturz)."""
    with socket.socket() as blocker:
        blocker.bind(("0.0.0.0", 0))
        blocker.listen()
        port = blocker.getsockname()[1]
        entry = MockConfigEntry(domain=DOMAIN, data={CONF_PORT: port})
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        assert entry.state is ConfigEntryState.SETUP_RETRY
