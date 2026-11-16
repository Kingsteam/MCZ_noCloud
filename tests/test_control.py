"""Tests der Steuerung: Climate, Schalter, Schutzgrenzen, Raumfühler."""

import asyncio
import socket
import time

from homeassistant.components.climate import HVACAction, HVACMode
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mcz_local.const import (
    CONF_PORT,
    CONF_ROOM_SENSOR,
    DOMAIN,
    MIN_OFF_BEFORE_ON_S,
)

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
    entity_id = er.async_get(hass).async_get_entity_id(
        platform, DOMAIN, f"{entry.entry_id}_{key}"
    )
    assert entity_id, key
    return entity_id


async def start(hass: HomeAssistant, fields=None, options=None, stove=True):
    port = free_port()
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_PORT: port}, options=options or {}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    server = entry.runtime_data.server
    server.poll_interval = 0.05
    server.write_gap = 0
    fake = None
    if stove:
        fake = FakeStove(port, fields)
        await fake.connect()
        await until(hass, lambda: bool(server.status.info))
    return entry, fake


@pytest.fixture
async def cleanup(hass: HomeAssistant):
    stoves = []
    yield stoves
    for s in stoves:
        await s.close()


async def call(hass, domain, service, entity_id, **data):
    await hass.services.async_call(
        domain, service, {"entity_id": entity_id, **data}, blocking=True
    )


async def test_setpoint_and_switches(hass: HomeAssistant, cleanup) -> None:
    """Solltemperatur und Schalter senden die richtigen Befehle."""
    entry, stove = await start(hass, {1: 0, 26: 42, 23: 0, 25: 1})
    cleanup.append(stove)
    climate = eid(hass, "climate", "climate", entry)
    assert hass.states.get(climate).attributes["temperature"] == 21.0

    await call(hass, "climate", "set_temperature", climate, temperature=21.5)
    await until(hass, lambda: (42, 43) in stove.writes)
    await until(
        hass, lambda: hass.states.get(climate).attributes["temperature"] == 21.5
    )

    eco = eid(hass, "switch", "eco_mode", entry)
    assert hass.states.get(eco).state == "off"
    await call(hass, "switch", "turn_on", eco)
    await until(hass, lambda: hass.states.get(eco).state == "on")
    assert (41, 1) in stove.writes

    chrono = eid(hass, "switch", "chronostat", entry)
    await call(hass, "switch", "turn_off", chrono)
    await until(hass, lambda: (1111, 0) in stove.writes)


async def test_setpoint_limits(hass: HomeAssistant, cleanup) -> None:
    """Außerhalb der Grenzen wird nichts gesendet."""
    entry, stove = await start(hass)
    cleanup.append(stove)
    climate = eid(hass, "climate", "climate", entry)
    with pytest.raises(ServiceValidationError):
        await call(hass, "climate", "set_temperature", climate, temperature=35)
    with pytest.raises(ServiceValidationError):
        await entry.runtime_data.controller.async_set_setpoint(4.0)
    assert stove.writes == []


async def test_off_then_on_is_blocked_for_30_minutes(
    hass: HomeAssistant, cleanup
) -> None:
    """Schutz gegen Takten: nach „Aus“ erst nach der Mindestpause wieder „Ein“."""
    entry, stove = await start(hass, {1: 12})
    cleanup.append(stove)
    controller = entry.runtime_data.controller
    climate = eid(hass, "climate", "climate", entry)
    assert hass.states.get(climate).state == HVACMode.HEAT
    assert hass.states.get(climate).attributes["hvac_action"] == HVACAction.HEATING

    await call(hass, "climate", "turn_off", climate)
    await until(hass, lambda: (34, 40) in stove.writes)
    await until(hass, lambda: hass.states.get(climate).state == HVACMode.OFF)

    with pytest.raises(HomeAssistantError) as err:
        await call(hass, "climate", "turn_on", climate)
    assert err.value.translation_key == "too_soon"
    assert (34, 1) not in stove.writes

    # Pause abgelaufen (Zeitpunkt zurückdatieren statt Uhr vorspulen)
    controller.last_stop = time.time() - MIN_OFF_BEFORE_ON_S - 1
    await call(hass, "climate", "set_hvac_mode", climate, hvac_mode="heat")
    await until(hass, lambda: (34, 1) in stove.writes)


async def test_stop_seen_from_stove_counts_and_is_stored(
    hass: HomeAssistant, hass_storage, cleanup
) -> None:
    """Geht der Ofen von selbst aus, zählt das auch, und es wird gespeichert."""
    entry, stove = await start(hass, {1: 12})
    cleanup.append(stove)
    controller = entry.runtime_data.controller
    assert controller.last_stop is None
    stove.fields[1] = 0
    await until(hass, lambda: controller.last_stop is not None)
    assert controller.seconds_until_on_allowed() > MIN_OFF_BEFORE_ON_S - 60
    await until(hass, lambda: f"{DOMAIN}.{entry.entry_id}" in hass_storage, timeout=5)
    assert hass_storage[f"{DOMAIN}.{entry.entry_id}"]["data"]["last_stop"]


async def test_pause_survives_restart(
    hass: HomeAssistant, hass_storage, cleanup
) -> None:
    """Gespeicherter Ausschaltzeitpunkt sperrt auch nach Neustart."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_PORT: free_port()})
    hass_storage[f"{DOMAIN}.{entry.entry_id}"] = {
        "version": 1,
        "key": f"{DOMAIN}.{entry.entry_id}",
        "data": {"last_stop": time.time() - 60},
    }
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    controller = entry.runtime_data.controller
    assert controller.seconds_until_on_allowed() > MIN_OFF_BEFORE_ON_S - 120


async def test_turn_on_refused_on_fault_and_when_disconnected(
    hass: HomeAssistant, cleanup
) -> None:
    """Bei Störung oder ohne Verbindung wird nicht eingeschaltet."""
    entry, stove = await start(hass, {1: 50})
    cleanup.append(stove)
    controller = entry.runtime_data.controller
    with pytest.raises(HomeAssistantError) as err:
        await controller.async_turn_on()
    assert err.value.translation_key == "stove_error"
    await stove.close()
    await until(hass, lambda: not entry.runtime_data.server.status.connected)
    with pytest.raises(HomeAssistantError) as err:
        await controller.async_turn_on()
    assert err.value.translation_key == "not_connected"
    with pytest.raises(HomeAssistantError):
        await controller.async_set_flag("eco_mode", True)
    assert (34, 1) not in stove.writes


async def test_write_gap_is_respected(hass: HomeAssistant, cleanup) -> None:
    """Zwischen zwei Befehlen liegt mindestens der Mindestabstand."""
    entry, stove = await start(hass)
    cleanup.append(stove)
    server = entry.runtime_data.server
    server.write_gap = 0.3
    t0 = time.monotonic()
    await server.async_write(41, 1)
    await server.async_write(41, 0)
    assert time.monotonic() - t0 >= 0.3
    with pytest.raises(ValueError):
        await server.async_write(36, 3)  # nicht freigegebene ID


async def test_room_sensor_option(hass: HomeAssistant, cleanup) -> None:
    """Externer Raumfühler ersetzt den Ofenfühler im Thermostat."""
    registry = er.async_get(hass)
    room = registry.async_get_or_create(
        "sensor", "test", "room1", suggested_object_id="raum"
    )
    hass.states.async_set(room.entity_id, "20.3", {"device_class": "temperature"})

    entry, stove = await start(hass, {6: 55})
    cleanup.append(stove)
    climate = eid(hass, "climate", "climate", entry)
    assert hass.states.get(climate).attributes["current_temperature"] == 27.5

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ROOM_SENSOR: room.entity_id}
    )
    assert entry.options == {CONF_ROOM_SENSOR: room.id}  # Register-ID, nicht entity_id
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    # nach dem Neuladen verbindet sich der Ofen neu
    stove2 = FakeStove(entry.data[CONF_PORT], {6: 55})
    cleanup.append(stove2)
    await stove2.connect()
    await until(hass, lambda: bool(entry.runtime_data.server.status.info))
    state = hass.states.get(climate)
    assert state.attributes["current_temperature"] == 20.3
    assert state.attributes["stove_ambient_temperature"] == 27.5

    # Umbenennen des Fühlers bricht den Bezug nicht
    registry.async_update_entity(room.entity_id, new_entity_id="sensor.wohnzimmer")
    hass.states.async_set("sensor.wohnzimmer", "19.0")
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    stove3 = FakeStove(entry.data[CONF_PORT], {6: 55})
    cleanup.append(stove3)
    await stove3.connect()
    await until(hass, lambda: bool(entry.runtime_data.server.status.info))
    assert hass.states.get(climate).attributes["current_temperature"] == 19.0


async def test_room_sensor_without_unique_id_is_rejected(hass: HomeAssistant) -> None:
    """Ein Fühler ohne Registereintrag kann nicht gewählt werden."""
    hass.states.async_set(
        "sensor.yaml_fuehler", "20.0", {"device_class": "temperature"}
    )
    entry, _ = await start(hass, stove=False)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ROOM_SENSOR: "sensor.yaml_fuehler"}
    )
    assert result["errors"] == {CONF_ROOM_SENSOR: "sensor_not_registered"}
    assert entry.options == {}
