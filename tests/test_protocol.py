"""Tests für das Protokoll-Modul."""

import pytest

from custom_components.mcz_local import protocol as P

from .conftest import make_info_line


def test_decode_info_temperatures_and_state():
    """Temperaturen sind halbe Grad, nicht angeschlossene Fühler werden None."""
    line = make_info_line({1: 12, 6: 41, 7: 0xFF, 8: 120, 26: 42, 45: 300})
    info = P.decode_info(line)
    assert info["state"] == 12
    assert info["state_key"] == "power2"
    assert info["burning"] is True
    assert info["ambient_temperature"] == 20.5
    assert info["puffer_temperature"] is None
    assert info["boiler_temperature"] == 60.0
    assert info["temperature_setpoint"] == 21.0
    assert info["ignitions"] == 300


@pytest.mark.parametrize(
    ("state", "key", "burning"),
    [
        (0, "off", False),
        (46, "standby", False),
        (53, "error", False),
        (99, "unknown", False),
    ],
)
def test_state_keys(state, key, burning):
    """Zustände werden auf Übersetzungsschlüssel abgebildet."""
    info = P.decode_info(make_info_line({1: state}))
    assert info["state_key"] == key
    assert info["burning"] is burning


def test_decode_info_short_line_skips_missing_fields():
    """Eine kürzere Zeile ergibt nur die vorhandenen Felder."""
    info = P.decode_info(make_info_line({1: 0}, length=10))
    assert "ignitions" not in info
    assert info["state"] == 0


@pytest.mark.parametrize("bad", ["00|01|02", "", "01|zz"])
def test_decode_info_rejects_garbage(bad):
    """Falsche Zeilen werfen ProtocolError."""
    with pytest.raises(P.ProtocolError):
        P.decode_info(bad)


def test_build_read():
    """Leseanfragen nur aus der bekannten Liste."""
    assert P.build_read() == "C|C|RecuperoInfo"
    with pytest.raises(ValueError):
        P.build_read("WriteParametri")


def test_build_write_only_allowed_ids():
    """Schreibbefehle nur für freigegebene Parameter."""
    assert P.build_write(42, 41) == "C|C|WriteParametri|42|41"
    with pytest.raises(ValueError):
        P.build_write(36, 3)


def test_socketio_roundtrip():
    """Ereignisse bauen und wieder lesen."""
    text = P.sio_event("ProvaStufa", {"richiesta": "C|C|RecuperoInfo"})
    assert text.startswith("42[")
    assert P.parse_sio_event(text) == ("ProvaStufa", {"richiesta": "C|C|RecuperoInfo"})
    assert P.parse_sio_event("3") is None
    assert P.parse_sio_event("42{kaputt") is None


def test_eio_open_payload_length_prefix():
    """Polling-Antwort beginnt mit der korrekten Länge."""
    payload = P.eio_open_payload("abc")
    length, pkt = payload.split(":", 1)
    assert int(length) == len(pkt)
    assert pkt.startswith('0{"sid":"abc"')
