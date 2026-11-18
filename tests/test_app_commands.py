"""Befehle aus dem Mitschnitt mit der MCZ-App: Kessel, Sommer/Winter,
technische Parameter, Zeitprogramm, Uhrzeit. Alle Daten sind erfunden."""

from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.mcz_local import protocol as P
from custom_components.mcz_local.const import CONF_SYNC_CLOCK, DOMAIN
from custom_components.mcz_local.services import program_to_slots, slots_to_program

from .test_control import call, cleanup, eid, start, until  # noqa: F401

pytestmark = pytest.mark.usefixtures("socket_enabled")


# --- reine Funktionen -------------------------------------------------------------


def test_chrono_day_roundtrip():
    """2 Bit je halbe Stunde, höchstwertige zuerst (wie im Mitschnitt)."""
    slots = [0] * 3 + [1] * 12 + [3] * 33
    text = P.encode_chrono_day(slots)
    assert text == "01555557FFFFFFFFFFFFFFFF"
    assert P.decode_chrono_day(text) == slots
    assert P.encode_chrono_day([2] * 48) == "A" * 24
    with pytest.raises(ValueError):
        P.encode_chrono_day([1] * 47)
    with pytest.raises(ValueError):
        P.encode_chrono_day([4] * 48)


def test_decode_chrono_and_extra():
    day = "5" * 6 + "F" * 18
    chrono = P.decode_chrono("|".join(["04", *[day] * 7, "13", "15", "17"]))
    assert chrono["temperatures"] == [19, 21, 23]
    assert chrono["days"][0][:12] == [1] * 12
    extra = P.decode_extra("03|02|03|ff|00b4|03|" + "|".join(["00"] * 16) + "|01|00")
    assert extra == {
        "eco_stop_delay": 180,
        "eco_hysteresis_neg": 3,
        "room_probe": "wifi",
        "relay_aux": "buffer_pump",
    }
    with pytest.raises(P.ProtocolError):
        P.decode_extra("03|01")


def test_build_clock_and_chrono_day():
    assert P.build_clock(datetime(2030, 1, 2, 3, 4)) == "C|C|SalvaDataOra|020120300304"
    assert P.build_chrono_day(1, [2] * 48) == "C|C|ScriviGiornoChrono|1|" + "A" * 24
    with pytest.raises(ValueError):
        P.build_chrono_day(7, [1] * 48)


def test_program_conversion():
    program = [
        {"start": "06:00", "level": "t3"},
        {"start": "00:00", "level": "t1"},
        {"start": "22:30", "level": "t2"},
    ]
    slots = program_to_slots(program)
    assert slots[:12] == [1] * 12
    assert slots[12] == 3
    assert slots[45:] == [2] * 3
    assert slots_to_program(slots) == [
        {"start": "00:00", "level": "t1"},
        {"start": "06:00", "level": "t3"},
        {"start": "22:30", "level": "t2"},
    ]
    assert program_to_slots([{"start": "07:00", "level": "t1"}])[:14] == [0] * 14
    for bad in ("06:15", "24:00", "x"):
        with pytest.raises(ServiceValidationError):
            program_to_slots([{"start": bad, "level": "t1"}])
    with pytest.raises(ServiceValidationError):
        program_to_slots([{"start": "06:00", "level": "t1"}] * 2)


# --- mit Home Assistant -----------------------------------------------------------


async def test_boiler_setpoint(hass: HomeAssistant, cleanup) -> None:  # noqa: F811
    """Kessel-Soll in halben Grad (Befehl 51), Grenzen 50 bis 80 °C."""
    entry, stove = await start(hass, {27: 120})
    cleanup.append(stove)
    number = eid(hass, "number", "boiler_setpoint", entry)
    assert float(hass.states.get(number).state) == 60.0
    await call(hass, "number", "set_value", number, value=61.5)
    await until(hass, lambda: (51, 123) in stove.writes)
    await until(hass, lambda: float(hass.states.get(number).state) == 61.5)
    with pytest.raises(ServiceValidationError):
        await call(hass, "number", "set_value", number, value=85)
    assert all(pid != 51 or val == 123 for pid, val in stove.writes)


async def test_season(hass: HomeAssistant, cleanup) -> None:  # noqa: F811
    """Sommer/Winter (58): Anzeige = zuletzt gesetzt, übersteht Neuladen."""
    entry, stove = await start(hass)
    cleanup.append(stove)
    select = eid(hass, "select", "season", entry)
    assert hass.states.get(select).state == "unknown"
    await call(hass, "select", "select_option", select, option="winter")
    await until(hass, lambda: stove.season == 0)
    assert hass.states.get(select).state == "winter"
    assert hass.states.get(select).attributes.get("assumed_state") is True
    await hass.async_block_till_done()
    assert entry.runtime_data.controller.assumed["season"] == 0


async def test_tech_params(hass: HomeAssistant, cleanup) -> None:  # noqa: F811
    """Technische Werte: Format ID|Bytes|Hex, Rückmeldung über Zusatzparameter."""
    entry, stove = await start(hass)
    cleanup.append(stove)
    delay = eid(hass, "number", "eco_stop_delay", entry)
    await until(hass, lambda: hass.states.get(delay).state == "120")
    await call(hass, "number", "set_value", delay, value=300)
    await until(hass, lambda: (148, 2, "012C") in stove.tech_writes)
    await until(hass, lambda: hass.states.get(delay).state == "300")

    hyst = eid(hass, "number", "boiler_hysteresis_neg", entry)
    assert hass.states.get(hyst).state == "unknown"  # meldet der Ofen nicht
    await call(hass, "number", "set_value", hyst, value=4)
    await until(hass, lambda: (296, 1, "04") in stove.tech_writes)
    await until(hass, lambda: hass.states.get(hyst).state == "4")

    with pytest.raises(ServiceValidationError):
        await call(hass, "number", "set_value", hyst, value=11)
    assert len([w for w in stove.tech_writes if w[0] == 296]) == 1


async def test_wiring_is_read_only(hass: HomeAssistant, cleanup) -> None:  # noqa: F811
    """Fühlerquelle und Relais gibt es nur zum Lesen, nie als Befehl."""
    entry, stove = await start(hass)
    cleanup.append(stove)
    probe = eid(hass, "sensor", "room_probe", entry)
    await until(hass, lambda: hass.states.get(probe).state == "ambient")
    assert not [s for s in hass.states.async_all("number") if "probe" in s.entity_id]
    assert all(pid not in (356, 365) for pid, _, _ in stove.tech_writes)


async def test_chrono_service_and_sensor(
    hass: HomeAssistant,
    cleanup,  # noqa: F811
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Zeitprogramm lesen (Attribute) und für mehrere Tage schreiben."""
    entry, stove = await start(hass)
    cleanup.append(stove)
    sensor = eid(hass, "sensor", "chrono_program", entry)
    await until(hass, lambda: hass.states.get(sensor).state in ("t1", "t3"))
    attrs = hass.states.get(sensor).attributes
    assert attrs["t1"] == 19
    assert attrs["mon"][1] == {"start": "06:00", "level": "t3"}

    await hass.services.async_call(
        DOMAIN,
        "set_chrono_day",
        {
            "days": ["mon", "sun"],
            "program": [
                {"start": "00:00", "level": "t1"},
                {"start": "07:30", "level": "t2"},
            ],
        },
        blocking=True,
    )
    await until(hass, lambda: stove.chrono[1][15] == 2 and stove.chrono[0][15] == 2)
    assert stove.chrono[2][15] == 3  # Dienstag unverändert
    await until(
        hass,
        lambda: hass.states.get(sensor).attributes["mon"][1]["start"] == "07:30",
    )
    # Die Stufe wird jede Minute neu berechnet (im Event-Loop, nicht im Thread)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()
    assert "from a thread" not in caplog.text


async def test_clock_sync(hass: HomeAssistant, cleanup) -> None:  # noqa: F811
    """Uhr wird bei der Anmeldung gestellt, per Knopf ebenso."""
    entry, stove = await start(hass)
    cleanup.append(stove)
    await until(hass, lambda: stove.clock is not None)
    stove.clock = None
    button = eid(hass, "button", "sync_clock", entry)
    await call(hass, "button", "press", button)
    await until(hass, lambda: stove.clock is not None)
    assert len(stove.clock) == 12
    await until(hass, lambda: entry.runtime_data.server.status.clock_set == stove.clock)


async def test_clock_sync_can_be_switched_off(hass: HomeAssistant, cleanup) -> None:  # noqa: F811
    _entry, stove = await start(hass, options={CONF_SYNC_CLOCK: False})
    cleanup.append(stove)
    await stove.ping()
    await hass.async_block_till_done()
    assert stove.clock is None
    assert not any(r.startswith("C|C|SalvaDataOra") for r in stove.requests)


async def test_not_connected_issue(hass: HomeAssistant, cleanup) -> None:  # noqa: F811
    """Meldet sich der Ofen nicht, erscheint nach 10 Minuten ein Hinweis."""
    from homeassistant.helpers import issue_registry as ir

    from .fake_stove import FakeStove

    entry, _ = await start(hass, stove=False)
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, "stove_not_connected") is None
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=11))
    await hass.async_block_till_done()
    issue = registry.async_get_issue(DOMAIN, "stove_not_connected")
    assert issue is not None
    assert issue.learn_more_url.endswith("docs/NETZWERK.md")

    stove = FakeStove(entry.runtime_data.server.port)
    cleanup.append(stove)
    await stove.connect()
    await until(hass, lambda: entry.runtime_data.server.status.connected)
    assert registry.async_get_issue(DOMAIN, "stove_not_connected") is None


async def test_connection_check(hass: HomeAssistant, cleanup) -> None:  # noqa: F811
    """Verbindungsprüfung: wartet, verbunden (mit Herkunft), getrennt."""
    from .fake_stove import FakeStove

    entry, _ = await start(hass, stove=False)
    check = eid(hass, "sensor", "connection_check", entry)
    state = hass.states.get(check)
    assert state.state == "waiting"
    assert state.attributes["port"] == entry.runtime_data.server.port

    stove = FakeStove(entry.runtime_data.server.port)
    await stove.connect()
    await until(hass, lambda: hass.states.get(check).state == "connected")
    attrs = hass.states.get(check).attributes
    assert attrs["remote_address"] == "127.0.0.1"
    assert attrs["connected_since"] is not None
    assert attrs["last_attempt"] is not None

    await stove.close()
    await until(hass, lambda: hass.states.get(check).state == "disconnected")
    assert hass.states.get(check).attributes["disconnected_since"] is not None
