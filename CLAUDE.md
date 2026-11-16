# CLAUDE.md – MCZ_noCloud (`mcz_local`)

Gedächtnis für spätere Sessions. Bei jeder größeren Änderung aktuell halten. Sprache mit dem Nutzer: Deutsch (Österreich), einfach, jeden Schritt erklären. Der Nutzer ist kein Entwickler.

## Zweck
Home-Assistant-Integration, die einen MCZ-Pelletofen mit Maestro-WLAN-Modul **ohne MCZ-Cloud** anbindet. Das Modul verbindet sich unverschlüsselt per Socket.IO v2 (Engine.IO 3) mit dem Cloud-Server. Der Router leitet diese Verbindung auf Home Assistant um, und `mcz_local` spielt den Server.

## Sicherheitsregeln (nicht verhandelbar)
1. **Nie gegen die echte Home-Assistant-Installation des Nutzers entwickeln oder testen**, auch nicht über ein HA-MCP-Werkzeug. Nur automatische Tests mit simuliertem Ofen und die simulierte Test-Instanz.
2. **Keine Geheimnisse, keine Hausdaten im Repo:** keine Tokens, IP-Adressen, Seriennummern, MAC-Adressen, Namen, Koordinaten, echten Entitätsnamen. Auch nicht in Tests, Beispielen, Bildschirmfotos, Commit-Texten. Testdaten sind erfunden (`tests/conftest.py: make_info_line`). Echte Mitschnitte bleiben außerhalb des Repos.
3. **Sicherheitsgrenzen** stehen nur in `const.py` (Abschnitt SICHERHEIT) und werden in `tests/test_const.py` geprüft. Diese Tests nie abschwächen, überspringen oder löschen. Grenzen nur nach Rücksprache ändern.
4. **Schaltbefehle am echten Ofen nur gemeinsam mit dem Nutzer** testen, kurz und begrenzt.
5. **Fremdcode:** Das Projekt „maestrogateway“ steht unter GPL. Nichts daraus kopieren, nur Fakten (Feldpositionen) verwenden. Eigener Code steht unter MIT.
6. Keinen Pull Request ohne ausdrücklichen Auftrag.

## Aufbau
| Datei | Inhalt |
|---|---|
| `custom_components/mcz_local/manifest.json` | `domain`, `name`, dann Schlüssel alphabetisch. Version gemeinsam mit `pyproject.toml` anheben |
| `custom_components/mcz_local/const.py` | Konstanten, **Sicherheitsgrenzen** |
| `custom_components/mcz_local/protocol.py` | reines Protokoll ohne HA: Statuszeile entschlüsseln, Befehle bauen, Socket.IO-Hilfen |
| `custom_components/mcz_local/__init__.py` | Einrichten/Entladen, `runtime_data` (`McZData`) |
| `custom_components/mcz_local/config_flow.py` | Einrichtung über die Oberfläche (Port), nur ein Eintrag |
| `custom_components/mcz_local/strings.json`, `translations/` | Texte (Schlüssel nur `[a-z0-9-_]`) |
| `tests/` | pytest mit `pytest-homeassistant-custom-component` |
| `docs/KONZEPT.md` | Ziel, Architektur, Datenmodell, Phasen |
| `.github/workflows/` | `tests.yml`, `validate.yml` (hassfest + HACS), `release.yml` |

## Befehle
```bash
uv venv --python 3.14 ../mcz-venv                     # einmalig, außerhalb des Repos
VIRTUAL_ENV=../mcz-venv uv pip install -r requirements_test.txt
../mcz-venv/bin/ruff check . && ../mcz-venv/bin/ruff format --check .
../mcz-venv/bin/pytest -q
```
Die Version von `pytest-homeassistant-custom-component` in `requirements_test.txt` bestimmt die getestete HA-Version (0.13.375 = HA 2026.10.4).

## Arbeitsweise
Jeder Schritt auf eigenem Zweig → Tests und Linter lokal grün → pushen → GitHub-Prüfungen abwarten → nur bei Grün per Fast-Forward nach `main`. Commit-Texte auf Deutsch. Release: `release.yml` per `workflow_dispatch` auf `main` (liest Version aus `manifest.json`, Text aus `CHANGELOG.md`).

## Stolperfallen
- Ruff meckert über typografische Zeichen (– × −) in Kommentaren und Strings (RUF001–003): normale Zeichen verwenden.
- Coroutinen, die auf die Uhr warten, mit `hass.async_create_background_task` starten, sonst blockieren sie `async_block_till_done`.
- In Tests mit eingefrorener Zeit kein `asyncio.sleep`.
- **Haarnadel-NAT:** Liegen HA und Ofen im selben Netz, reicht eine reine DNAT-Regel nicht (Antwort käme direkt von HA). Zusätzlich Masquerade nötig. Gehört ins Handbuch, nicht in den Code.
- HA-Port 9000 ist oft schon belegt (z. B. Portainer). Port ist deshalb einstellbar, der Router kann den Port umschreiben.

## Stand
- Phase 1 (Grundgerüst, Protokoll, Tests) fertig, noch **nicht mit echter Hardware getestet**.
