#!/usr/bin/env python3
"""Bildschirmfotos aus der laufenden Test-Instanz für das Handbuch.

Voraussetzung: start.py läuft. Anmeldung über das gespeicherte Token aus
zugang.json (liegt außerhalb des Repos), es wird kein Passwort eingetippt.

Aufruf: ../mcz-venv/bin/python devtools/testinstanz/bildschirmfotos.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
import urllib.request

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:8124"
CLIENT_ID = f"{BASE}/"
ZIEL = REPO / "docs" / "bilder"


def token(cfg: Path) -> dict:
    zugang = json.loads((cfg / "zugang.json").read_text())
    body = (
        f"grant_type=refresh_token&refresh_token={zugang['refresh_token']}"
        f"&client_id={CLIENT_ID}"
    ).encode()
    req = urllib.request.Request(f"{BASE}/auth/token", body, method="POST")
    with urllib.request.urlopen(req) as r:
        tok = json.loads(r.read())
    tok["refresh_token"] = zugang["refresh_token"]
    return tok


def template(tok: dict, tpl: str) -> str:
    req = urllib.request.Request(
        f"{BASE}/api/template",
        json.dumps({"template": tpl}).encode(),
        {
            "Authorization": f"Bearer {tok['access_token']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        return r.read().decode().strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(Path.home() / ".mcz-testinstanz"))
    a = ap.parse_args()
    tok = token(Path(a.config).expanduser())
    device_id = template(
        tok, "{{ integration_entities('mcz_local') | first | device_id }}"
    )
    verlauf = template(
        tok,
        "{{ integration_entities('mcz_local') | select('match', 'sensor\\\\.')"
        " | select('search', 'zustand$|wassertemperatur|abgastemperatur')"
        " | join(',') }}",
    )
    hass_tokens = {
        "access_token": tok["access_token"],
        "token_type": "Bearer",
        "expires_in": tok["expires_in"],
        "hassUrl": BASE,
        "clientId": CLIENT_ID,
        "expires": int(time.time() * 1000) + tok["expires_in"] * 1000,
        "refresh_token": tok["refresh_token"],
    }
    seiten = {
        "geraet.png": f"/config/devices/device/{device_id}",
        "integration.png": "/config/integrations/integration/mcz_local",
        "verlauf.png": f"/history?entity_id={verlauf}",
    }
    ZIEL.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="de-DE",
            color_scheme="light",
        )
        tokens_js = json.dumps(json.dumps(hass_tokens))
        ctx.add_init_script(
            f"localStorage.setItem('hassTokens', {tokens_js});"
            "localStorage.setItem('selectedLanguage', '\"de\"');"
        )
        page = ctx.new_page()
        for name, pfad in seiten.items():
            page.goto(BASE + pfad)
            page.wait_for_timeout(8000)
            page.screenshot(path=str(ZIEL / name))
            print("gespeichert:", ZIEL / name)
        browser.close()


if __name__ == "__main__":
    main()
