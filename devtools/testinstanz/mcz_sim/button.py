"""Tasten zum Steuern des Simulators."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant

from . import DOMAIN, IGNITION, SHUTDOWN, SimStove

BUTTONS = {
    "zuenden": ("Simulator: Zünden", lambda s: s.run_sequence(IGNITION)),
    "ausschalten": ("Simulator: Ausschalten", lambda s: s.run_sequence(SHUTDOWN)),
    "stoerung": ("Simulator: Störung A01", lambda s: s.fault()),
    "trennen": ("Simulator: Verbindung 30 s trennen", lambda s: s.disconnect()),
    "beispieldaten": ("Simulator: Beispieldaten", lambda s: s.reset()),
}


async def async_setup_platform(
    hass: HomeAssistant, config, add_entities, discovery_info=None
):
    """Tasten anlegen."""
    sim: SimStove = hass.data[DOMAIN]
    add_entities(
        SimButton(sim, key, name, action) for key, (name, action) in BUTTONS.items()
    )


class SimButton(ButtonEntity):
    """Eine Taste des Simulators."""

    _attr_should_poll = False

    def __init__(self, sim: SimStove, key: str, name: str, action) -> None:
        self._sim = sim
        self._action = action
        self._attr_name = name
        self._attr_unique_id = f"mcz_sim_{key}"

    async def async_press(self) -> None:
        self._action(self._sim)
