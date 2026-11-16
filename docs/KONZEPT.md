# Konzept

## Ziel
Ein MCZ-Pelletofen mit Maestro-WLAN-Modul soll sich ganz ohne MCZ-Cloud aus Home Assistant lesen und steuern lassen. Grundlage für eine spätere eigene Heizungssteuerung (Takten vermeiden, vorausschauend heizen).

## Architektur
```
Ofen (Maestro-Modul) ── TCP, Socket.IO v2 ──> [Router: Umleitung der Cloud-Adresse] ──> Home Assistant: mcz_local (Port einstellbar)
```
- Das Modul ist **Client**, `mcz_local` ist **Server**. Das Modul meldet sich mit `join` an (Seriennummer, MAC, Firmware), ohne Passwort.
- `mcz_local` fragt alle 10 s den Status ab (`C|C|RecuperoInfo`) und schickt Befehle (`C|C|WriteParametri|<id>|<wert>`). Antworten kommen als `rispondo` mit `|`-getrennten Hex-Feldern.
- Eigener kleiner WebSocket-/Engine.IO-3-Server mit asyncio, **ohne Fremdbibliothek** (die gängigen Socket.IO-Bibliotheken sprechen das alte Protokoll v2 nicht mehr zuverlässig).
- Die MCZ-App funktioniert nicht mehr, solange die Umleitung aktiv ist (bewusst in Kauf genommen).

## Datenmodell
- **Konfiguration** (Config-Entry): Port.
- **Gerät:** wird beim ersten `join` angelegt; Kennung = Seriennummer des Moduls (kommt vom Ofen, nicht fest eingebaut).
- **Entitäten (geplant):**
  - `climate`: Ein/Aus, Solltemperatur (Grenzen aus `const.py`)
  - Sensoren: Zustand, Wasser-/Kesseltemperatur, Raum, Abgas, Leistungsstufe, Pumpe, Zündungen, Betriebsstunden
  - Schalter: Eco, Chrono, Töne
  - Binärsensor „verbunden“
  - Fühler, die der Ofen als `FF` meldet (nicht angeschlossen), werden nicht angelegt.

## Sicherheit
- Nur freigegebene Parameter-IDs schreibbar (`ALLOWED_WRITE_IDS`).
- Solltemperatur 5–30 °C.
- Höchstens ein Befehl pro Sekunde.
- Gegen Takten: nach „Aus“ mindestens 30 Minuten Pause vor dem nächsten „Ein“.

## Phasen
1. ✅ Grundgerüst, Protokoll-Modul, Tests, GitHub-Prüfungen
2. ✅ Server im HA-Prozess + simulierter Ofen in den Tests
3. ✅ Nur lesen: Sensoren, „verbunden“, Test-Instanz, Handbuch mit Bildschirmfotos
4. Schalten: Climate und Schalter mit Schutzgrenzen (zuerst simuliert, dann gemeinsam am echten Ofen)
5. Dauerbetrieb (Installation über den Marketplace) und `docs/NETZWERK.md`: allgemeine Anleitung zur Umleitung im Router (DNAT, bei gleichem Netz zusätzlich Masquerade) mit einem neutralen Beispiel, ohne echte Adressen
6. Später: Heizungssteuerung nach Messphase
