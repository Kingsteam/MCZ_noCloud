"""Dienste: Zeitprogramm schreiben.

Ein Tag wird als Liste von Abschnitten angegeben, z. B.
  - {start: "00:00", level: t1}
  - {start: "06:00", level: t3}
  - {start: "22:00", level: t1}
Jeder Abschnitt gilt bis zum nächsten. Zeiten nur zur vollen oder halben Stunde.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .const import DOMAIN
from .protocol import CHRONO_SLOTS

SERVICE_SET_CHRONO_DAY = "set_chrono_day"
SERVICE_SYNC_CLOCK = "sync_clock"

# Wochentag -> Nummer im Ofen (0 = Sonntag)
DAYS: dict[str, int] = {
    "sun": 0,
    "mon": 1,
    "tue": 2,
    "wed": 3,
    "thu": 4,
    "fri": 5,
    "sat": 6,
}
LEVELS: dict[str, int] = {"off": 0, "t1": 1, "t2": 2, "t3": 3}

PERIOD_SCHEMA = vol.Schema(
    {
        vol.Required("start"): cv.string,
        vol.Required("level"): vol.In(list(LEVELS)),
    }
)
SET_CHRONO_SCHEMA = vol.Schema(
    {
        vol.Required("days"): vol.All(cv.ensure_list, [vol.In(list(DAYS))]),
        vol.Required("program"): vol.All(
            cv.ensure_list, vol.Length(min=1, max=CHRONO_SLOTS), [PERIOD_SCHEMA]
        ),
    }
)


def _invalid(reason: str) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="invalid_chrono_program",
        translation_placeholders={"reason": reason},
    )


def _slot(text: str) -> int:
    """„06:30“ -> 13 (halbe Stunden ab Mitternacht)."""
    try:
        hours, minutes = (int(x) for x in text.strip().split(":")[:2])
    except ValueError as err:
        raise _invalid(text) from err
    if not 0 <= hours <= 23 or minutes not in (0, 30):
        raise _invalid(text)
    return hours * 2 + minutes // 30


def program_to_slots(program: list[dict[str, Any]]) -> list[int]:
    """Abschnitte in 48 Halbstunden-Stufen umrechnen. Vor dem ersten: aus."""
    starts = sorted((_slot(p["start"]), LEVELS[p["level"]]) for p in program)
    if len({s for s, _ in starts}) != len(starts):
        raise _invalid("doppelte Uhrzeit")
    slots = [0] * CHRONO_SLOTS
    for i, (start, level) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else CHRONO_SLOTS
        slots[start:end] = [level] * (end - start)
    return slots


def slots_to_program(slots: list[int]) -> list[dict[str, str]]:
    """Gegenrichtung für die Anzeige: nur die Wechsel."""
    names = {v: k for k, v in LEVELS.items()}
    out: list[dict[str, str]] = []
    for i, level in enumerate(slots):
        if i == 0 or level != slots[i - 1]:
            out.append(
                {"start": f"{i // 2:02d}:{(i % 2) * 30:02d}", "level": names[level]}
            )
    return out


def _controller(hass: HomeAssistant):
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            return entry.runtime_data.controller
    raise ServiceValidationError(
        translation_domain=DOMAIN, translation_key="not_loaded"
    )


def async_setup_services(hass: HomeAssistant) -> None:
    """Dienste registrieren."""

    async def _set_chrono_day(call: ServiceCall) -> None:
        controller = _controller(hass)
        slots = program_to_slots(call.data["program"])
        for day in dict.fromkeys(call.data["days"]):  # Reihenfolge, ohne Doppelte
            await controller.async_set_chrono_day(DAYS[day], slots)

    async def _sync_clock(call: ServiceCall) -> None:
        await _controller(hass).async_sync_clock(dt_util.now())

    hass.services.async_register(
        DOMAIN, SERVICE_SET_CHRONO_DAY, _set_chrono_day, schema=SET_CHRONO_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_SYNC_CLOCK, _sync_clock)
