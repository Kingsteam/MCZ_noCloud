"""Kleiner Server, der für den Ofen die Rolle der MCZ-Cloud übernimmt.

Nur asyncio aus der Standardbibliothek, keine Home-Assistant-Abhängigkeit.
Ablauf: Engine.IO-3-Polling-Handshake, Upgrade auf WebSocket, Socket.IO v2.
Es wird immer nur eine Ofen-Verbindung gehalten; eine neue ersetzt die alte.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable
import contextlib
from dataclasses import dataclass, field
import hashlib
import logging
import secrets
import struct
import time
from typing import Any
from urllib.parse import parse_qs, urlsplit

from . import protocol as P
from .const import ERROR_HOLD_S, MIN_WRITE_GAP_S, SLOW_POLL_EVERY

_LOGGER = logging.getLogger(__name__)

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
HTTP_TIMEOUT_S = 10
MAX_HEADER_BYTES = 8192
MAX_FRAME_BYTES = 64 * 1024
# Ohne Lebenszeichen so lange warten, dann Verbindung als tot betrachten
IDLE_TIMEOUT_S = (P.PING_INTERVAL_MS + P.PING_TIMEOUT_MS) / 1000 + 5

OP_TEXT = 0x1
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA


class HandshakeError(Exception):
    """Anfrage ist kein gültiger Socket.IO-Verbindungsaufbau."""


class NotConnectedError(Exception):
    """Kein Ofen verbunden, Befehl kann nicht gesendet werden."""


@dataclass
class StoveStatus:
    """Was der Server über den Ofen weiß."""

    connected: bool = False
    identity: dict[str, Any] = field(default_factory=dict)
    info: dict[str, Any] = field(default_factory=dict)
    last_seen: float | None = None  # time.time() der letzten Nachricht
    last_info: float | None = None  # time.time() der letzten Statuszeile
    extra: dict[str, Any] = field(default_factory=dict)  # Zusatzparameter (03)
    chrono: dict[str, Any] = field(default_factory=dict)  # Zeitprogramm (04)
    clock_set: str | None = None  # zuletzt bestätigte Uhrzeit (AA|TTMMJJJJhhmm)
    # Für die Verbindungsprüfung (time.time())
    last_attempt: float | None = None  # irgendeine TCP-Verbindung kam an
    remote_address: str | None = None  # von wo die Ofen-Verbindung kommt
    connected_since: float | None = None
    disconnected_since: float | None = None
    error_seen: float | None = None  # time.time() der letzten Störungs-Zeile
    error_state: int | None = None  # Zustandsnummer dieser Störung (50-69)


# --- HTTP / WebSocket-Hilfen -------------------------------------------------


async def _read_http(reader: asyncio.StreamReader) -> tuple[str, str, dict[str, str]]:
    """HTTP-Kopf lesen: (Methode, Ziel, Kopfzeilen in Kleinbuchstaben)."""
    try:
        head = await asyncio.wait_for(
            reader.readuntil(b"\r\n\r\n"), timeout=HTTP_TIMEOUT_S
        )
    except asyncio.LimitOverrunError as err:
        raise HandshakeError("Kopf zu groß") from err
    if len(head) > MAX_HEADER_BYTES:
        raise HandshakeError("Kopf zu groß")
    lines = head.decode("latin-1").split("\r\n")
    try:
        method, target, _ = lines[0].split(" ", 2)
    except ValueError as err:
        raise HandshakeError("keine HTTP-Anfrage") from err
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            key, val = line.split(":", 1)
            headers[key.strip().lower()] = val.strip()
    return method, target, headers


def _query(target: str) -> dict[str, str]:
    parts = urlsplit(target)
    if not parts.path.startswith("/socket.io"):
        raise HandshakeError("falscher Pfad")
    return {k: v[0] for k, v in parse_qs(parts.query).items()}


def ws_frame(text: str, opcode: int = OP_TEXT) -> bytes:
    """Unmaskierten WebSocket-Rahmen (Server an Client) bauen."""
    data = text.encode()
    n = len(data)
    if n < 126:
        head = bytes([0x80 | opcode, n])
    elif n < 65536:
        head = bytes([0x80 | opcode, 126]) + struct.pack("!H", n)
    else:
        head = bytes([0x80 | opcode, 127]) + struct.pack("!Q", n)
    return head + data


async def ws_read(reader: asyncio.StreamReader) -> tuple[int, bytes]:
    """Einen WebSocket-Rahmen lesen: (Opcode, Nutzdaten)."""
    h = await reader.readexactly(2)
    opcode = h[0] & 0x0F
    n = h[1] & 0x7F
    if n == 126:
        n = struct.unpack("!H", await reader.readexactly(2))[0]
    elif n == 127:
        n = struct.unpack("!Q", await reader.readexactly(8))[0]
    if n > MAX_FRAME_BYTES:
        raise HandshakeError("Rahmen zu groß")
    mask = await reader.readexactly(4) if h[1] & 0x80 else b""
    data = await reader.readexactly(n)
    if mask:
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    return opcode, data


def _http_response(status: str, headers: list[tuple[str, str]], body: bytes) -> bytes:
    lines = [f"HTTP/1.1 {status}"] + [f"{k}: {v}" for k, v in headers]
    lines.append(f"Content-Length: {len(body)}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode() + body


# --- Verbindung zum Ofen -----------------------------------------------------


class StoveConnection:
    """Eine WebSocket-Verbindung zum Ofen."""

    def __init__(
        self,
        server: McZServer,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        self._server = server
        self._reader = reader
        self._writer = writer
        self._socket_id = "local-" + secrets.token_hex(4)
        self._poll_task: asyncio.Task | None = None
        self.joined = False
        self.peer: str | None = None

    async def send_text(self, text: str) -> None:
        self._writer.write(ws_frame(text))
        await self._writer.drain()

    async def send_request(self, richiesta: str) -> None:
        """Anfrage an den Ofen schicken (ProvaStufa)."""
        await self.send_text(
            P.sio_event(
                "ProvaStufa",
                {"richiesta": richiesta, "socketChiamata": self._socket_id},
            )
        )

    async def run(self) -> None:
        """Nachrichten lesen, bis die Verbindung endet."""
        try:
            while True:
                opcode, data = await asyncio.wait_for(
                    ws_read(self._reader), timeout=IDLE_TIMEOUT_S
                )
                if opcode == OP_CLOSE:
                    return
                if opcode == OP_PING:
                    self._writer.write(ws_frame(data.decode("latin-1"), OP_PONG))
                    await self._writer.drain()
                    continue
                if opcode != OP_TEXT:
                    continue
                self._server.touch()
                await self._on_text(data.decode("utf-8", "replace"))
        finally:
            if self._poll_task:
                self._poll_task.cancel()

    async def _on_text(self, text: str) -> None:
        if text == "5":  # Engine.IO-Upgrade abgeschlossen
            await self.send_text("40")
            return
        if text == "2":  # Engine.IO-Ping
            await self.send_text("3")
            return
        event = P.parse_sio_event(text)
        if event is None:
            _LOGGER.debug("Unbekannte Nachricht vom Ofen: %.80s", text)
            return
        name, payload = event
        if name == "join" and isinstance(payload, dict):
            self.joined = True
            self._server.on_join(self, payload)
            if self._poll_task is None:
                self._poll_task = asyncio.create_task(self._poll())
        elif name == "rispondo" and isinstance(payload, dict):
            self._server.on_answer(str(payload.get("stringaRicevuta", "")))
        else:
            _LOGGER.debug("Ereignis vom Ofen: %s", name)

    async def _poll(self) -> None:
        """Status regelmäßig abfragen, Zusatzparameter und Zeitprogramm seltener."""
        n = 0
        try:
            while True:
                if n % self._server.slow_poll_every == 0:
                    await self.send_request(P.build_read("RecuperoParametriExtra"))
                    await self.send_request(P.build_read("RecuperoGiornoChrono"))
                await self.send_request(P.build_read("RecuperoInfo"))
                n += 1
                await asyncio.sleep(self._server.poll_interval)
        except (ConnectionError, RuntimeError) as err:
            _LOGGER.debug("Abfrage beendet: %s", err)

    def close(self) -> None:
        self._writer.close()


class McZServer:
    """TCP-Server, der den Ofen annimmt und seinen Status sammelt."""

    def __init__(self, host: str, port: int, poll_interval: float) -> None:
        self.host = host
        self.port = port
        self.poll_interval = poll_interval
        self.status = StoveStatus()
        self._server: asyncio.Server | None = None
        self._conn: StoveConnection | None = None
        self._sessions: set[str] = set()
        self._listeners: list[Callable[[], None]] = []
        self._write_lock = asyncio.Lock()
        self._last_write = 0.0  # time.monotonic() des letzten Schreibbefehls
        self.write_gap = MIN_WRITE_GAP_S
        self.slow_poll_every = SLOW_POLL_EVERY
        self._join_listeners: list[Callable[[], None]] = []

    # Lebenszyklus
    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, self.host, self.port)
        if self.port == 0:  # für Tests: zufälliger freier Port
            self.port = self._server.sockets[0].getsockname()[1]
        _LOGGER.info("Warte auf den Ofen an Port %s", self.port)

    async def stop(self) -> None:
        if self._conn:
            self._conn.close()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        self._server = None

    # Befehle
    async def async_write(self, param_id: int, value: int) -> None:
        """Schreibbefehl senden. Nur freigegebene IDs (build_write prüft das).
        Der Ofen antwortet mit einer vollständigen Statuszeile."""
        await self.async_send(P.build_write(param_id, value))

    async def async_send(self, richiesta: str, refresh: str | None = None) -> None:
        """Befehl senden, höchstens einer je write_gap Sekunden.

        Nur mit Befehlen aus den build_*-Funktionen aufrufen, die die
        Sicherheitsgrenzen prüfen. Mit refresh wird danach diese Leseanfrage
        geschickt (z. B. Zusatzparameter nach einem technischen Wert)."""
        async with self._write_lock:
            if self._conn is None or not self.status.connected:
                raise NotConnectedError
            wait = self._last_write + self.write_gap - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            if self._conn is None:
                raise NotConnectedError
            _LOGGER.info("Befehl an den Ofen: %s", richiesta)
            try:
                await self._conn.send_request(richiesta)
            except (ConnectionError, RuntimeError) as err:
                raise NotConnectedError from err
            self._last_write = time.monotonic()
            if refresh:
                with contextlib.suppress(ConnectionError, RuntimeError):
                    await self._conn.send_request(P.build_read(refresh))

    # Beobachter
    def add_join_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        """Rückruf, sobald sich der Ofen (neu) anmeldet."""
        self._join_listeners.append(cb)
        return lambda: self._join_listeners.remove(cb)

    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        """Rückruf bei jeder Statusänderung; liefert Abmeldefunktion."""
        self._listeners.append(cb)
        return lambda: self._listeners.remove(cb)

    def notify(self) -> None:
        """Beobachter von außen anstoßen (z. B. nach einem gemerkten Wert)."""
        self._notify()

    def _notify(self) -> None:
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:
                _LOGGER.exception("Fehler in einem Statusbeobachter")

    # Ereignisse aus der Verbindung
    def touch(self) -> None:
        self.status.last_seen = time.time()

    def on_join(self, conn: StoveConnection, identity: dict[str, Any]) -> None:
        if self._conn is not None and self._conn is not conn:
            self._conn.close()  # alte Verbindung ersetzen
        self._conn = conn
        self.status.identity = {
            k: identity.get(k)
            for k in ("serialNumber", "macAddress", "type", "revision")
        }
        self.status.connected = True
        self.status.connected_since = time.time()
        self.status.remote_address = conn.peer
        _LOGGER.info("Ofen angemeldet (Firmware %s)", identity.get("revision"))
        self._notify()
        for cb in list(self._join_listeners):
            try:
                cb()
            except Exception:
                _LOGGER.exception("Fehler bei der Anmeldung des Ofens")

    def on_answer(self, frame: str) -> None:
        kind = frame[:3]
        try:
            if kind == "01|":
                self.status.info = self._hold_error(P.decode_info(frame))
                self.status.last_info = time.time()
            elif kind == "03|":
                self.status.extra = P.decode_extra(frame)
            elif kind == "04|":
                self.status.chrono = P.decode_chrono(frame)
            elif kind == "AA|":
                self.status.clock_set = frame[3:]
            else:
                return
        except P.ProtocolError as err:
            _LOGGER.warning("Antwort des Ofens nicht lesbar (%s): %s", kind, err)
            return
        self._notify()

    def _hold_error(self, info: dict[str, Any]) -> dict[str, Any]:
        """Störung nicht flackern lassen.

        Meldet der Ofen kurz nach einer Störung nur „schaltet ab“ oder „kühlt ab“,
        bleibt es eine Störung, bis ERROR_HOLD_S ohne Störungs-Zeile vergangen sind.
        Zündet oder brennt er wieder, oder ist er ganz aus, gilt das sofort.
        """
        now = time.time()
        if info.get("state_key") == "error":
            self.status.error_seen = now
            self.status.error_state = info.get("state")
            return info
        seen = self.status.error_seen
        if (
            seen is not None
            and now - seen < ERROR_HOLD_S
            and info.get("state_key") in P.SHUTDOWN_KEYS
        ):
            return {
                **info,
                "state_key": "error",
                "burning": False,
                "error_held": True,
                "reported_state": info.get("state"),
                "state": self.status.error_state,
            }
        self.status.error_seen = None
        self.status.error_state = None
        return info

    # Verbindungsaufbau
    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        conn: StoveConnection | None = None
        peer = writer.get_extra_info("peername")
        self.status.last_attempt = time.time()
        try:
            conn = await self._handshake(reader, writer)
            if conn is not None:
                conn.peer = peer[0] if peer else None
            if conn is not None:
                await conn.run()
        except HandshakeError as err:
            _LOGGER.debug("Verbindung abgelehnt: %s", err)
        except (TimeoutError, asyncio.IncompleteReadError, ConnectionError) as err:
            _LOGGER.debug("Verbindung beendet: %s", type(err).__name__)
        finally:
            writer.close()
            if conn is not None and conn is self._conn:
                self._conn = None
                self.status.connected = False
                self.status.disconnected_since = time.time()
                _LOGGER.info("Verbindung zum Ofen getrennt")
                self._notify()

    async def _handshake(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> StoveConnection | None:
        _, target, headers = await _read_http(reader)
        query = _query(target)
        if query.get("EIO") != "3":
            raise HandshakeError("nur Engine.IO 3")
        if query.get("transport") == "polling" and "sid" not in query:
            sid = secrets.token_urlsafe(15)[:20]
            self._sessions = {sid}  # nur die jüngste Sitzung gilt
            writer.write(
                _http_response(
                    "200 OK",
                    [
                        ("Content-Type", "text/plain; charset=UTF-8"),
                        ("Set-Cookie", f"io={sid}; Path=/; HttpOnly"),
                        ("Connection", "keep-alive"),
                    ],
                    P.eio_open_payload(sid).encode(),
                )
            )
            await writer.drain()
            # Der Ofen schickt das Upgrade auf derselben TCP-Verbindung
            _, target, headers = await _read_http(reader)
            query = _query(target)
        if (
            query.get("transport") != "websocket"
            or headers.get("upgrade", "").lower() != "websocket"
            or "sec-websocket-key" not in headers
        ):
            writer.write(_http_response("400 Bad Request", [], b""))
            await writer.drain()
            raise HandshakeError("kein WebSocket-Upgrade")
        if query.get("sid") and query["sid"] not in self._sessions:
            raise HandshakeError("unbekannte Sitzung")
        accept = base64.b64encode(
            hashlib.sha1((headers["sec-websocket-key"] + WS_GUID).encode()).digest()
        ).decode()
        resp = [
            "HTTP/1.1 101 Switching Protocols",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Accept: {accept}",
        ]
        if proto := headers.get("sec-websocket-protocol"):
            resp.append(f"Sec-WebSocket-Protocol: {proto.split(',')[0].strip()}")
        writer.write(("\r\n".join(resp) + "\r\n\r\n").encode())
        await writer.drain()
        return StoveConnection(self, reader, writer)
