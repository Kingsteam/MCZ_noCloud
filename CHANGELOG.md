# Changelog

Alle nennenswerten Änderungen. Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionen nach [SemVer](https://semver.org/lang/de/).

## [Unreleased]

## [0.3.0] - 2026-11-16
### Hinzugefügt
- Gerät „Pelletofen“ mit Seriennummer und Firmware des Moduls.
- Sensoren: Zustand, Wasser-, Raum-, Soll-, Abgastemperatur, Zündungen, Betriebsstunden, Stunden bis Wartung; Diagnose: Leistungsstufe, Pumpe, Abgasgebläse, Platinentemperatur, Zustandsnummer.
- Rücklauf- und Puffertemperatur nur, wenn der Fühler angeschlossen ist.
- Binärsensoren: Verbunden, In Betrieb, Störung.
- Simulierte Test-Instanz mit Ofen-Simulator, Handbuch mit Bildschirmfotos.
### Noch nicht
- Schalten (Ein/Aus, Solltemperatur, Eco, Chrono). Nicht mit echter Hardware getestet.

## [0.2.0] - 2026-11-16
### Hinzugefügt
- Server für den Ofen in der Integration: nimmt die Verbindung des Maestro-Moduls an (Engine.IO 3 / WebSocket / Socket.IO v2), fragt alle 10 s den Status ab und entschlüsselt ihn.
- Belegter Port wird erkannt; Home Assistant versucht es dann später erneut.
- Simulierter Ofen für die Tests.
### Noch nicht
- Keine Entitäten (folgen in 0.3.0). Nicht mit echter Hardware getestet.

## [0.1.0] - 2026-11-16
### Hinzugefügt
- Grundgerüst der Integration `mcz_local`: Einrichtung über die Oberfläche (Port), Protokoll-Modul (Statuszeile entschlüsseln, Befehle bauen), Tests und GitHub-Prüfungen.
- Noch keine Verbindung zum Ofen, keine Entitäten.
