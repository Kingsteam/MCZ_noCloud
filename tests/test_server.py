"""Tests für den Ofen-Server mit simuliertem Ofen (ohne Home Assistant)."""

import asyncio

import pytest

from custom_components.mcz_local.server import McZServer

from .fake_stove import FAKE_IDENTITY, FakeStove

# Echte Sockets nur auf 127.0.0.1 (Server und simulierter Ofen im Test)
pytestmark = pytest.mark.usefixtures("socket_enabled")


@pytest.fixture
async def server():
    srv = McZServer("127.0.0.1", 0, poll_interval=0.05)
    await srv.start()
    yield srv
    await srv.stop()


async def wait_for(cond, timeout=5.0):
    """Warten, bis eine Bedingung gilt (echte Zeit, keine eingefrorene Uhr)."""
    async with asyncio.timeout(timeout):
        while not cond():
            await asyncio.sleep(0.01)


async def test_join_and_status(server):
    """Ofen meldet sich an, Server fragt Status ab und entschlüsselt ihn."""
    events = []
    server.add_listener(lambda: events.append(server.status.connected))
    stove = FakeStove(server.port, {1: 12, 6: 41, 8: 120, 7: 0xFF})
    await stove.connect()
    await wait_for(lambda: server.status.info.get("state") == 12)
    assert server.status.connected
    assert server.status.identity == FAKE_IDENTITY
    assert server.status.info["ambient_temperature"] == 20.5
    assert server.status.info["boiler_temperature"] == 60.0
    assert server.status.info["puffer_temperature"] is None
    assert stove.requests[0] == "C|C|RecuperoInfo"
    assert events and events[0] is True
    await stove.close()


async def test_polling_repeats(server):
    """Der Status wird wiederholt abgefragt, Änderungen kommen an."""
    stove = FakeStove(server.port)
    await stove.connect()
    await wait_for(lambda: len(stove.requests) >= 3)
    stove.fields[1] = 46
    await wait_for(lambda: server.status.info.get("state_key") == "standby")
    assert all(r == "C|C|RecuperoInfo" for r in stove.requests)
    await stove.close()


async def test_ping_pong(server):
    """Engine.IO-Ping wird mit Pong beantwortet."""
    stove = FakeStove(server.port)
    await stove.connect()
    await stove.ping()
    await stove.close()


async def test_disconnect_sets_not_connected(server):
    """Nach dem Trennen meldet der Server „nicht verbunden“."""
    stove = FakeStove(server.port)
    await stove.connect()
    await wait_for(lambda: server.status.connected)
    await stove.close()
    await wait_for(lambda: not server.status.connected)


async def test_new_connection_replaces_old(server):
    """Ein zweiter Verbindungsaufbau ersetzt den ersten (Ofen startet neu)."""
    first = FakeStove(server.port)
    await first.connect()
    await wait_for(lambda: server.status.connected)
    second = FakeStove(server.port, {1: 31})
    await second.connect()
    await wait_for(lambda: server.status.info.get("state") == 31)
    await asyncio.sleep(0.1)
    assert server.status.connected
    await first.close()
    await second.close()


async def test_rejects_non_socketio_request(server):
    """Fremde Anfragen werden abgewiesen, der Server läuft weiter."""
    reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
    writer.write(b"GET / HTTP/1.1\r\nHost: x\r\n\r\n")
    await writer.drain()
    assert await reader.read() == b""
    writer.close()
    stove = FakeStove(server.port)
    await stove.connect()
    await wait_for(lambda: server.status.connected)
    await stove.close()


async def test_garbage_answer_is_ignored(server):
    """Eine kaputte Statuszeile bringt den Server nicht aus dem Tritt."""
    stove = FakeStove(server.port)
    await stove.connect()
    await stove.send('42["rispondo",{"stringaRicevuta":"01|zz"}]')
    await stove.send("42kaputt")
    await stove.ping()
    assert server.status.connected
    await stove.close()
