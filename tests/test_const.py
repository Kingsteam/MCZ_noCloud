"""Sicherheitsgrenzen. Diese Tests nie abschwächen, überspringen oder löschen."""

import pytest

from custom_components.mcz_local import const as C, protocol as P


def test_allowed_write_ids_are_exactly_these():
    """Nur Ein/Aus, Eco, Solltemperatur, Töne, Kessel-Soll, Sommer/Winter, Chrono.

    148 (Pelletstand-Sensor) bleibt gesperrt: ohne Sensor droht eine Störung.
    """
    assert frozenset({34, 41, 42, 50, 51, 58, 1111}) == C.ALLOWED_WRITE_IDS
    assert 148 not in C.ALLOWED_WRITE_IDS
    assert frozenset({0, 1}) == C.ALLOWED_SEASON_VALUES


def test_boiler_setpoint_limits():
    """Kessel-Solltemperatur bleibt zwischen 50 und 80 °C."""
    assert C.BOILER_SETPOINT_MIN_C == 50.0
    assert C.BOILER_SETPOINT_MAX_C == 80.0
    assert P.boiler_setpoint_raw(61) == 122
    for bad in (49.5, 80.5, 0, 100):
        with pytest.raises(ValueError):
            P.boiler_setpoint_raw(bad)


def test_tech_params_are_exactly_these():
    """Nur diese technischen Parameter, nur in diesen Grenzen."""
    assert C.TECH_PARAMS == {
        "boiler_hysteresis_pos": (297, 1, 0, 10),
        "boiler_hysteresis_neg": (296, 1, 1, 10),
        "room_hysteresis_pos": (289, 1, 0, 3),
        "room_hysteresis_neg": (288, 1, 0, 3),
        "eco_hysteresis_pos": (295, 1, 0, 5),
        "eco_hysteresis_neg": (294, 1, 0, 5),
        "eco_stop_delay": (148, 2, 60, 1800),
        "pump_min_temperature": (517, 1, 40, 70),
    }


def test_wiring_params_are_forbidden():
    """Quelle Raumfühler (356) und Relais-Ausgang (365) sind nie schreibbar."""
    assert frozenset({356, 365}) <= C.FORBIDDEN_TECH_IDS
    ids = {pid for pid, _, _, _ in C.TECH_PARAMS.values()}
    assert not ids & C.FORBIDDEN_TECH_IDS


def test_tech_write_limits():
    """Werte außerhalb der Grenzen und unbekannte Parameter werden abgelehnt."""
    for key, (_pid, _size, low, high) in C.TECH_PARAMS.items():
        P.build_tech_write(key, low)
        P.build_tech_write(key, high)
        with pytest.raises(ValueError):
            P.build_tech_write(key, low - 1)
        with pytest.raises(ValueError):
            P.build_tech_write(key, high + 1)
    for bad in ("room_probe", "relay_aux", "356", "pellet_sensor"):
        with pytest.raises(ValueError):
            P.build_tech_write(bad, 1)


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
    for pid in (
        C.CMD_POWER,
        C.CMD_ECO,
        C.CMD_SETPOINT,
        C.CMD_SOUND,
        C.CMD_BOILER_SETPOINT,
        C.CMD_SEASON,
        C.CMD_CHRONO,
    ):
        assert pid in C.ALLOWED_WRITE_IDS
    assert C.POWER_ON == 1
    assert C.POWER_OFF == 40
