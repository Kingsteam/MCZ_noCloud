# Test-Instanz (komplett simuliert)

Eine eigene Home-Assistant-Instanz zum Ausprobieren von `mcz_local`, **ohne echten Ofen und ohne echte Home-Assistant-Installation**.

- Konfiguration, Benutzer und Zugangsdaten liegen **außerhalb des Repos** in `~/.mcz-testinstanz`.
- `mcz_local` und der Simulator `mcz_sim` sind per Verweis eingebunden: Änderungen am Code wirken nach einem Neustart sofort.
- Der Simulator verbindet sich wie ein echtes Maestro-Modul mit `mcz_local` (Port 9100) und hat Tasten: *Zünden*, *Ausschalten*, *Störung A01*, *Verbindung 30 s trennen*, *Beispieldaten*.
- Home Assistant läuft nur auf `127.0.0.1:8124` (nicht im Netz erreichbar).

## Einmalig einrichten
```bash
uv venv --python 3.14 ../mcz-venv
VIRTUAL_ENV=../mcz-venv uv pip install -r requirements_test.txt -r devtools/testinstanz/requirements.txt
../mcz-venv/bin/python -m playwright install chromium
```

## Starten und beenden
```bash
../mcz-venv/bin/python devtools/testinstanz/start.py          # oder Doppelklick auf starten.command
../mcz-venv/bin/python devtools/testinstanz/start.py --reset  # alles neu anlegen
```
Dann im Browser <http://127.0.0.1:8124> öffnen. Benutzer `test`, das Passwort steht in `~/.mcz-testinstanz/zugang.json`.

**Beenden:** Strg+C im Fenster des Startskripts. Das Skript beendet auch den Home-Assistant-Prozess. Falls doch einer übrig bleibt: `pkill -f "homeassistant -c $HOME/.mcz-testinstanz"`.

## Bildschirmfotos fürs Handbuch
Während die Test-Instanz läuft (vorher *Simulator: Zünden* drücken und ein paar Minuten warten, damit der Verlauf etwas zeigt):
```bash
../mcz-venv/bin/python devtools/testinstanz/bildschirmfotos.py
```
Die Bilder landen in `docs/bilder/`. Vor dem Commit ansehen: keine echten Daten.

## Stolperfallen
- HA muss aus dem Konfigurationsordner gestartet werden (macht `start.py`), sonst findet es über das Repo nur dessen `custom_components` und der Simulator fehlt.
- Seit HA 2026.11 muss eine geänderte HTTP-Einstellung (Port) bestätigt werden, sonst springt HA nach 5 Minuten zurück auf 8123. `start.py` bestätigt das automatisch.
- Fehlermeldungen zu `radio_browser`, `met`, `google_translate` beim ersten Start sind harmlos (Onboarding schlägt Integrationen vor, deren Pakete fehlen).
