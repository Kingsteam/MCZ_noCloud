"""Simulierter Ofen (Client) für Tests.

Verhält sich wie das Maestro-Modul: Polling-Handshake, Upgrade auf WebSocket,
„join“ mit erfundener Kennung, Antworten auf „ProvaStufa“. Keine echten Daten.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
import struct

from custom_components.mcz_local import protocol as P

from .conftest import make_info_line

FAKE_IDENTITY = {
    "serialNumber": "1234567890123",
    "macAddress": "AABBCCDDEEFF",
    "type": "stove",
    "revision": "9.9.9",
}

DEFAULT_FIELDS = {1: 0, 6: 41, 7: 0xFF, 8: 100, 26: 42, 45: 7}


def masked_frame(text: str, opcode: int = 0x1) -> bytes:
    data = text.encode()
    mask = os.urandom(4)
    n = len(data)
    if n < 126:
        head = bytes([0x80 | opcode, 0x80 | n])
    else:
        head = bytes([0x80 | opcode, 0x80 | 126]) + struct.pack("!H", n)
    return head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data))


class FakeStove:
    """Ein Ofen, der sich mit dem Server verbindet."""

    def __init__(self, port: int, fields: dict[int, int] | None = None) -> None:
        self.port = port
        self.fields = dict(DEFAULT_FIELDS if fields is None else fields)
        self.requests: list[str] = []
        self.writes: list[tuple[int, int]] = []
        self.tech_writes: list[tuple[int, int, str]] = []
        self.clock: str | None = None
        self.season: int | None = None
        # Zusatzparameter (erfunden): Fühler im Ofen, 2 min, Hysterese 1, Relais N.C.
        self.extra = {3: 0x01, 4: 120, 5: 1, 22: 0xFF}
        # Zeitprogramm (erfunden): alle Tage 0-6 T1, 6-22 T3, 22-24 T1
        day = [1] * 12 + [3] * 32 + [1] * 4
        self.chrono = [list(day) for _ in range(7)]
        self.chrono_temps = [19, 21, 23]
        self.got_connect = asyncio.Event()
        self.got_pong = asyncio.Event()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._task: asyncio.Task | None = None

    async def _http(self, request: str) -> tuple[str, str]:
        assert self._writer and self._reader
        self._writer.write(request.encode())
        await self._writer.drain()
        head = (await self._reader.readuntil(b"\r\n\r\n")).decode()
        body = ""
        for line in head.split("\r\n"):
            if line.lower().startswith("content-length:"):
                n = int(line.split(":", 1)[1])
                body = (await self._reader.readexactly(n)).decode()
        return head, body

    async def connect(self, join: bool = True) -> None:
        self._reader, self._writer = await asyncio.open_connection(
            "127.0.0.1", self.port
        )
        host = f"Host: example.invalid:{self.port}\r\n"
        head, body = await self._http(
            f"GET /socket.io/?EIO=3&transport=polling HTTP/1.1\r\n{host}"
            "User-Agent: arduino-WebSocket-Client\r\n\r\n"
        )
        assert head.startswith("HTTP/1.1 200")
        sid = json.loads(body.split(":", 1)[1][1:])["sid"]
        key = base64.b64encode(os.urandom(16)).decode()
        head, _ = await self._http(
            f"GET /socket.io/?EIO=3&transport=websocket&sid={sid} HTTP/1.1\r\n{host}"
            "Connection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Version: 13\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Protocol: arduino\r\n\r\n"
        )
        assert head.startswith("HTTP/1.1 101")
        self._task = asyncio.create_task(self._loop())
        await self.send("5")
        await asyncio.wait_for(self.got_connect.wait(), 5)
        if join:
            await self.send(P.sio_event("join", FAKE_IDENTITY))

    async def send(self, text: str) -> None:
        assert self._writer
        self._writer.write(masked_frame(text))
        await self._writer.drain()

    async def ping(self) -> None:
        """Ping schicken und auf Pong warten: alles davor ist angekommen."""
        self.got_pong.clear()
        await self.send("2")
        await asyncio.wait_for(self.got_pong.wait(), 5)

    async def _loop(self) -> None:
        from custom_components.mcz_local.server import ws_read

        assert self._reader
        try:
            while True:
                opcode, data = await ws_read(self._reader)
                if opcode == 0x8:
                    return
                text = data.decode()
                if text == "40":
                    self.got_connect.set()
                elif text == "3":
                    self.got_pong.set()
                elif ev := P.parse_sio_event(text):
                    name, payload = ev
                    if name == "ProvaStufa":
                        await self._answer(payload)
        except asyncio.IncompleteReadError, ConnectionError:
            return

    def extra_line(self) -> str:
        parts = ["03"] + ["00"] * 23
        for pos, val in self.extra.items():
            parts[pos] = format(val, "04x" if pos == 4 else "02x")
        return "|".join(parts)

    def chrono_line(self) -> str:
        days = [P.encode_chrono_day(d) for d in self.chrono]
        temps = [format(t, "02x") for t in self.chrono_temps]
        return "|".join(["04", *days, *temps])

    async def _answer(self, payload: dict) -> None:
        req = payload["richiesta"]
        self.requests.append(req)
        parts = req.split("|")
        answer: str | None = "00|00"
        if req.startswith("C|C|WriteParametri|"):
            pid, val = (int(x) for x in parts[3:5])
            self.writes.append((pid, val))
            self.apply_write(pid, val)
            answer = make_info_line(self.fields)
        elif req.startswith("C|C|WriteTecniciParametri|"):
            # wie der echte Ofen: keine Antwort, Wert erst in den Zusatzparametern
            pid, size, raw = int(parts[3]), int(parts[4]), parts[5]
            self.tech_writes.append((pid, size, raw))
            pos = {148: 4, 294: 5}.get(pid)
            if pos is not None:
                self.extra[pos] = int(raw, 16)
            answer = None
        elif req.startswith("C|C|ScriviGiornoChrono|"):
            self.chrono[int(parts[3])] = P.decode_chrono_day(parts[4])
            answer = make_info_line(self.fields)
        elif req.startswith("C|C|SalvaDataOra|"):
            self.clock = parts[3]
            answer = "AA|" + parts[3]
        elif req == "C|C|RecuperoInfo":
            answer = make_info_line(self.fields)
        elif req == "C|C|RecuperoParametriExtra":
            answer = self.extra_line()
        elif req == "C|C|RecuperoGiornoChrono":
            answer = self.chrono_line()
        if answer is None:
            return
        await self.send(
            P.sio_event(
                "rispondo",
                {
                    "stringaRicevuta": answer,
                    "socketChiamata": payload.get("socketChiamata"),
                },
            )
        )

    def apply_write(self, pid: int, val: int) -> None:
        """Wie der echte Ofen: Wert übernehmen (Antwort ist die Statuszeile)."""
        if pid == 34:
            self.fields[1] = 3 if val == 1 else 40
        elif pid == 42:
            self.fields[26] = val
        elif pid == 51:
            self.fields[27] = val
        elif pid == 58:
            self.season = val
        else:
            field = {41: 23, 50: 49, 1111: 25}[pid]
            self.fields[field] = val

    async def close(self) -> None:
        if self._writer:
            self._writer.close()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
