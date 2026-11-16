"""Sicherheitsgrenzen. Diese Tests nie abschwächen, überspringen oder löschen."""

import pytest

from custom_components.mcz_local import const as C, protocol as P


def test_allowed_write_ids_are_exactly_these():
    """Nur Ein/Aus, Eco, Solltemperatur, Töne und Chrono sind schreibbar."""
    assert frozenset({34, 41, 42, 50, 1111}) == C.ALLOWED_WRITE_IDS


def test_setpoint_limits():
    """Solltemperatur bleibt zwischen 5 und 30 °C."""
    assert C.SETPOINT_MIN_C == 5.0
    assert C.SETPOINT_MAX_C == 30.0
    assert P.setpoint_raw(21.5) == 43
    for bad in (4.5, 30.5, -1, 100):
        with pytest.raises(ValueError):
            P.setpoint_raw(bad)


def test_anti_cycling_and_rate_limits():
    """Mindestpause vor Wiedereinschalten 30 Minuten, Befehle höchstens 1/s."""
    assert C.MIN_OFF_BEFORE_ON_S >= 30 * 60
    assert C.MIN_WRITE_GAP_S >= 1.0


def test_command_ids_are_allowed():
    """Jede Befehls-ID der Steuerung steht in der Freigabeliste."""
    for pid in (C.CMD_POWER, C.CMD_ECO, C.CMD_SETPOINT, C.CMD_SOUND, C.CMD_CHRONO):
        assert pid in C.ALLOWED_WRITE_IDS
    assert C.POWER_ON == 1
    assert C.POWER_OFF == 40
