"""Gemeinsame Test-Hilfen."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Eigene Integrationen in allen Tests erlauben."""
    return


def make_info_line(values: dict[int, int], length: int = 61) -> str:
    """Erfundene Statuszeile „01|…“ mit Hex-Feldern bauen.

    Es werden absichtlich keine echten Mitschnitt-Daten verwendet.
    """
    parts = ["01"] + ["00"] * (length - 1)
    for pos, val in values.items():
        parts[pos] = format(val, "02x")
    return "|".join(parts)
