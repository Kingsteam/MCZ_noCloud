#!/usr/bin/env python3
"""Simulierte Home-Assistant-Test-Instanz für mcz_local starten.

- Konfiguration, Benutzer und Zugangsdaten liegen AUSSERHALB des Repos
  (Standard: ~/.mcz-testinstanz).
- mcz_local und der Simulator mcz_sim werden per Verweis eingebunden.
- Beim ersten Start wird HA automatisch eingerichtet (Onboarding) und
  mcz_local mit dem Simulator-Port angelegt.

Aufruf (aus dem Repo, mit der Test-venv):
    ../mcz-venv/bin/python devtools/testinstanz/start.py [--reset]
Beenden: Strg+C (beendet auch den Home-Assistant-Prozess).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO = Path(__file__).resolve().parents[2]
HIER = Path(__file__).resolve().parent
HA_PORT = 8124
OFEN_PORT = 9100
BASE = f"http://127.0.0.1:{HA_PORT}"
CLIENT_ID = f"{BASE}/"

CONFIG_YAML = f"""\
homeassistant:
  name: Testhaus
  unit_system: metric
  time_zone: UTC
  latitude: 0
  longitude: 0
  elevation: 0
  country: DE
  language: de
  currency: EUR

frontend:
config:
history:
logbook:
http:
  server_host: 127.0.0.1
  server_port: {HA_PORT}

logger:
  default: warning
  logs:
    custom_components.mcz_local: debug
    custom_components.mcz_sim: info

mcz_sim:
  port: {OFEN_PORT}
"""


def call(method: str, path: str, data=None, token: str | None = None, form=False):
    body = None
    headers = {}
    if data is not None:
        if form:
            body = "&".join(f"{k}={v}" for k, v in data.items()).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, body, headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode()
        return json.loads(text) if text else None


def wait_for_ha(proc: subprocess.Popen, timeout: float = 180) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if proc.poll() is not None:
            sys.exit("Home Assistant hat sich beendet, siehe Log oben.")
        try:
            call("GET", "/api/")
            return
        except urllib.error.HTTPError:
            return  # HA antwortet (z. B. 401) -> läuft
        except urllib.error.URLError, ConnectionError:
            time.sleep(1)
    sys.exit("Home Assistant startet nicht.")


def onboard(cfg: Path) -> dict:
    """Erstbenutzer anlegen und Onboarding abschließen. Liefert Zugangsdaten."""
    zugang_datei = cfg / "zugang.json"
    try:
        steps = {s["step"]: s["done"] for s in call("GET", "/api/onboarding")}
    except urllib.error.HTTPError:
        steps = {"user": True}  # Onboarding abgeschlossen: Endpunkt gibt es nicht mehr
    if steps.get("user"):
        return json.loads(zugang_datei.read_text())
    zugang = {"username": "test", "password": secrets.token_urlsafe(12)}
    res = call(
        "POST",
        "/api/onboarding/users",
        {"client_id": CLIENT_ID, "name": "Test", "language": "de", **zugang},
    )
    tok = call(
        "POST",
        "/auth/token",
        {
            "grant_type": "authorization_code",
            "code": res["auth_code"],
            "client_id": CLIENT_ID,
        },
        form=True,
    )
    t = tok["access_token"]
    call("POST", "/api/onboarding/core_config", {}, t)
    call("POST", "/api/onboarding/analytics", {}, t)
    call(
        "POST",
        "/api/onboarding/integration",
        {"client_id": CLIENT_ID, "redirect_uri": CLIENT_ID},
        t,
    )
    zugang["refresh_token"] = tok["refresh_token"]
    zugang_datei.write_text(json.dumps(zugang, indent=2))
    zugang_datei.chmod(0o600)
    return zugang


def access_token(zugang: dict) -> str:
    tok = call(
        "POST",
        "/auth/token",
        {
            "grant_type": "refresh_token",
            "refresh_token": zugang["refresh_token"],
            "client_id": CLIENT_ID,
        },
        form=True,
    )
    return tok["access_token"]


def promote_http(token: str) -> None:
    """Port-Einstellung bestätigen (seit HA 2026.11, sonst Rücksprung nach 5 Min.)."""
    import asyncio

    import aiohttp

    async def run() -> None:
        async with (
            aiohttp.ClientSession() as session,
            session.ws_connect(f"{BASE}/api/websocket") as ws,
        ):
            await ws.receive_json()
            await ws.send_json({"type": "auth", "access_token": token})
            await ws.receive_json()
            await ws.send_json({"id": 1, "type": "http/config"})
            cfg = await ws.receive_json()
            if not (cfg.get("result") or {}).get("pending"):
                return
            await ws.send_json({"id": 2, "type": "http/config/promote"})
            res = await ws.receive_json()
            print("HTTP-Einstellung bestätigt:", res.get("success"))

    asyncio.run(run())


def ensure_mcz_local(token: str) -> None:
    entries = call(
        "GET", "/api/config/config_entries/entry?domain=mcz_local", token=token
    )
    if entries:
        return
    flow = call(
        "POST", "/api/config/config_entries/flow", {"handler": "mcz_local"}, token
    )
    res = call(
        "POST",
        f"/api/config/config_entries/flow/{flow['flow_id']}",
        {"port": OFEN_PORT},
        token,
    )
    print("mcz_local eingerichtet:", res.get("type"))


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--config", default=str(Path.home() / ".mcz-testinstanz"))
    ap.add_argument(
        "--reset", action="store_true", help="Test-Instanz komplett neu anlegen"
    )
    ap.add_argument(
        "--ohne-integration",
        action="store_true",
        help="mcz_local nicht automatisch einrichten",
    )
    a = ap.parse_args()

    cfg = Path(a.config).expanduser()
    if REPO in cfg.resolve().parents or cfg.resolve() == REPO:
        sys.exit("Die Test-Instanz darf nicht im Repo liegen.")
    if a.reset and cfg.exists():
        shutil.rmtree(cfg)
    (cfg / "custom_components").mkdir(parents=True, exist_ok=True)
    (cfg / "configuration.yaml").write_text(CONFIG_YAML)
    for name, src in (
        ("mcz_local", REPO / "custom_components" / "mcz_local"),
        ("mcz_sim", HIER / "mcz_sim"),
    ):
        link = cfg / "custom_components" / name
        if not link.is_symlink():
            link.symlink_to(src)

    # cwd = Konfigurationsordner: sonst findet HA nur die custom_components im Repo
    proc = subprocess.Popen(
        [sys.executable, "-m", "homeassistant", "-c", str(cfg), "--skip-pip"], cwd=cfg
    )

    def beenden(*_):
        print("\nBeende Home Assistant …")
        proc.terminate()
        try:
            proc.wait(30)
        except subprocess.TimeoutExpired:
            proc.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, beenden)
    signal.signal(signal.SIGTERM, beenden)

    try:
        wait_for_ha(proc)
        zugang = onboard(cfg)
        token = access_token(zugang)
        promote_http(token)
        if not a.ohne_integration:
            ensure_mcz_local(token)
        print(f"\nTest-Instanz läuft: {BASE}")
        print(
            f"Benutzer: {zugang['username']}, Passwort steht in {cfg / 'zugang.json'}"
        )
        print("Beenden mit Strg+C.\n")
        proc.wait()
    finally:
        if proc.poll() is None:  # HA nie verwaist zurücklassen
            proc.terminate()
            proc.wait(30)


if __name__ == "__main__":
    main()
