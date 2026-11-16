"""Simulierter MCZ-Ofen für die Test-Instanz (nicht Teil der Integration).

Verbindet sich wie ein echtes Maestro-Modul mit mcz_local auf 127.0.0.1 und
beantwortet Statusabfragen. Über Tasten lassen sich Zünden, Ausschalten,
Störungen und Verbindungsabbrüche auslösen. Alle Werte sind erfunden.

configuration.yaml:
    mcz_sim:
      port: 9100
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import random
import struct

from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.typing import ConfigType

DOMAIN = "mcz_sim"
_LOGGER = logging.getLogger(__name__)

IDENTITY = {
    "serialNumber": "0000000000001",
    "macAddress": "000000000001",
    "type": "stove",
    "revision": "1.0.0",
}

# Beispieldaten (Feldposition -> Rohwert), Temperaturen in halben Grad
SAMPLE = {
    1: 0, 5: 25, 6: 42, 7: 0xFF, 8: 70, 9: 0xFF, 12: 0, 16: 0, 26: 43, 27: 140,
    28: 60, 29: 0, 37: 1520 * 3600, 43: 480, 45: 1234, 59: 0xFF,
}  # fmt: skip

# Ablauf beim Zünden: (Zustand, Sekunden)
IGNITION = [(2, 6), (3, 6), (4, 6), (5, 6), (10, 6), (12, 0)]
SHUTDOWN = [(40, 6), (41, 10), (0, 0)]


def _frame(text: str) -> bytes:
    data = text.encode()
    mask = os.urandom(4)
    n = len(data)
    head = (
        bytes([0x81, 0x80 | n])
        if n < 126
        else bytes([0x81, 0x80 | 126]) + struct.pack("!H", n)
    )
    return head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data))


class SimStove:
    """Ein simulierter Ofen als Client."""

    def __init__(self, hass: HomeAssistant, port: int) -> None:
        self.hass = hass
        self.port = port
        self.fields: dict[int, int] = dict(SAMPLE)
        self.online = True
        self._writer: asyncio.StreamWriter | None = None
        self._sequence: asyncio.Task | None = None

    # Beispieldaten / Bedienung
    def reset(self) -> None:
        self.fields = dict(SAMPLE)

    def run_sequence(self, steps: list[tuple[int, int]]) -> None:
        if self._sequence:
            self._sequence.cancel()
        self._sequence = self.hass.async_create_background_task(
            self._run(steps), "mcz_sim_sequence"
        )

    async def _run(self, steps: list[tuple[int, int]]) -> None:
        for state, wait in steps:
            self.fields[1] = state
            if state == 3:
                self.fields[45] += 1
            await asyncio.sleep(wait)

    def apply_write(self, pid: int, val: int) -> None:
        """Wie der echte Ofen auf Schreibbefehle reagieren."""
        if pid == 34:
            self.run_sequence(IGNITION if val == 1 else SHUTDOWN)
        elif pid == 42:
            self.fields[26] = val
        elif pid in (41, 50, 1111):
            self.fields[{41: 23, 50: 49, 1111: 25}[pid]] = val

    def fault(self) -> None:
        if self._sequence:
            self._sequence.cancel()
        self.fields[1] = 50  # A01 Zündung fehlgeschlagen

    def disconnect(self, seconds: int = 30) -> None:
        self.online = False
        if self._writer:
            self._writer.close()
        self.hass.loop.call_later(seconds, setattr, self, "online", True)

    # Physik in grob: Temperaturen folgen dem Zustand
    async def physics(self) -> None:
        while True:
            await asyncio.sleep(2)
            burning = 2 <= self.fields[1] <= 15 or self.fields[1] == 31
            target_water = 140 if burning else 60
            self.fields[8] += (target_water > self.fields[8]) - (
                target_water < self.fields[8]
            )
            self.fields[5] = max(25, min(160, self.fields[5] + (3 if burning else -2)))
            self.fields[12] = 1450 if burning else 0
            self.fields[16] = 60 if burning and self.fields[8] > 100 else 0
            self.fields[29] = 2 if burning else 0
            if burning:
                self.fields[37] += 2
            self.fields[6] = max(
                30, min(48, self.fields[6] + random.choice((-1, 0, 0, 1)))
            )

    def info_line(self) -> str:
        parts = ["01"] + ["00"] * 60
        for pos, val in self.fields.items():
            parts[pos] = format(val, "02x")
        return "|".join(parts)

    # Verbindung
    async def connect_loop(self) -> None:
        while True:
            if self.online:
                try:
                    await self._session()
                except (OSError, asyncio.IncompleteReadError, ValueError) as err:
                    _LOGGER.debug("Simulator: Verbindung beendet (%s)", err)
            await asyncio.sleep(3)

    async def _http(self, reader, writer, request: str) -> tuple[str, str]:
        writer.write(request.encode())
        await writer.drain()
        head = (await reader.readuntil(b"\r\n\r\n")).decode()
        body = ""
        for line in head.split("\r\n"):
            if line.lower().startswith("content-length:"):
                body = (await reader.readexactly(int(line.split(":")[1]))).decode()
        return head, body

    async def _session(self) -> None:
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        self._writer = writer
        host = f"Host: example.invalid:{self.port}\r\n"
        _, body = await self._http(
            reader,
            writer,
            f"GET /socket.io/?EIO=3&transport=polling HTTP/1.1\r\n{host}\r\n",
        )
        sid = json.loads(body.split(":", 1)[1][1:])["sid"]
        key = base64.b64encode(os.urandom(16)).decode()
        head, _ = await self._http(
            reader,
            writer,
            f"GET /socket.io/?EIO=3&transport=websocket&sid={sid} HTTP/1.1\r\n{host}"
            "Connection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Version: 13\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Protocol: arduino\r\n\r\n",
        )
        if not head.startswith("HTTP/1.1 101"):
            raise ValueError("kein Upgrade")
        writer.write(_frame("5"))
        writer.write(_frame("42" + json.dumps(["join", IDENTITY])))
        await writer.drain()
        _LOGGER.info("Simulator: mit mcz_local verbunden")

        async def pinger() -> None:  # wie das echte Modul: Ping alle 5 s
            while True:
                await asyncio.sleep(5)
                writer.write(_frame("2"))
                await writer.drain()

        ping_task = asyncio.create_task(pinger())
        try:
            while True:
                h = await reader.readexactly(2)
                n = h[1] & 0x7F
                if n == 126:
                    n = struct.unpack("!H", await reader.readexactly(2))[0]
                text = (await reader.readexactly(n)).decode()
                if h[0] & 0x0F == 0x8:
                    return
                if text.startswith('42["ProvaStufa"'):
                    payload = json.loads(text[2:])[1]
                    req = payload["richiesta"]
                    if req.startswith("C|C|WriteParametri|"):
                        pid, val = (int(x) for x in req.split("|")[3:5])
                        _LOGGER.info("Simulator: Befehl %s = %s", pid, val)
                        self.apply_write(pid, val)
                    if req == "C|C|RecuperoInfo" or req.startswith(
                        "C|C|WriteParametri|"
                    ):
                        answer = {
                            "stringaRicevuta": self.info_line(),
                            "socketChiamata": payload.get("socketChiamata"),
                        }
                        writer.write(_frame("42" + json.dumps(["rispondo", answer])))
                        await writer.drain()
        finally:
            ping_task.cancel()
            writer.close()


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Simulator starten."""
    port = int(config.get(DOMAIN, {}).get("port", 9100))
    sim = SimStove(hass, port)
    hass.data[DOMAIN] = sim
    tasks = [
        hass.async_create_background_task(sim.connect_loop(), "mcz_sim_connect"),
        hass.async_create_background_task(sim.physics(), "mcz_sim_physics"),
    ]

    def _stop(_event) -> None:
        for task in tasks:
            task.cancel()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop)
    for platform in (Platform.BUTTON, Platform.SENSOR):
        hass.async_create_task(async_load_platform(hass, platform, DOMAIN, {}, config))
    return True
