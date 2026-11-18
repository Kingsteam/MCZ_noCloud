# Changelog

Alle nennenswerten Änderungen. Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionen nach [SemVer](https://semver.org/lang/de/).

## [Unreleased]

## [0.5.1] - 2026-11-18
### Hinzugefügt
- `docs/NETZWERK.md`: allgemeine Anleitung zur Umleitung im Router (DNAT, bei gleichem Netz Masquerade), mit Beispielen für UniFi, OPNsense/pfSense, OpenWrt, MikroTik.
- Einrichtungshilfe: Meldet sich der Ofen 10 Minuten nach dem Start nicht, erscheint unter *Reparaturen* ein Hinweis mit Link zur Anleitung. Er verschwindet, sobald sich der Ofen meldet.

## [0.5.0] - 2026-11-18
### Hinzugefügt
- Kessel-Solltemperatur (50–80 °C) und Sommer/Winter.
- Feineinstellungen unter *Konfiguration*: Kessel-, Raum- und Eco-Stop-Hysterese, Eco-Stop-Abschaltverzögerung, Pumpe ab Wassertemperatur. Jeder Wert mit festen Grenzen.
- Zeitprogramm: Sensor „Zeitprogramm jetzt“ mit dem Programm je Wochentag; Dienst `mcz_local.set_chrono_day`.
- Uhr des Ofens: Knopf, Dienst `mcz_local.sync_clock` und automatisch bei jeder Anmeldung sowie alle 6 Stunden (abschaltbar).
- Diagnose „Quelle Raumfühler“ (nur Anzeige).
- `docs/PROTOKOLL.md`: alle Befehle aus dem Mitschnitt mit der MCZ-App.
### Sicherheit
- Quelle Raumfühler (356), Relais-Ausgang (365) und Pelletstand-Sensor (148) sind bewusst nicht schreibbar.
### Wichtig
- Nur simuliert getestet. Die Befehle sind im Mitschnitt mit der MCZ-App bestätigt; „Sommer“ (Wert 1) ist angenommen.

## [0.4.0] - 2026-11-16
### Hinzugefügt
- Thermostat „Pelletofen“: Ein/Aus und Solltemperatur (5–30 °C, halbe Grad).
- Schalter Eco, Chrono und Töne.
- Schutzgrenzen für alle Befehle: nur bei Verbindung, nicht bei Störung, höchstens ein Befehl pro Sekunde, nach dem Ausgehen 30 Minuten Pause vor dem nächsten Einschalten (übersteht Neustarts).
- Option: eigener Raumfühler als Ist-Temperatur des Thermostats.
### Wichtig
- Schaltbefehle sind nur simuliert getestet. Der Befehl Ein/Aus (Parameter 34) stammt aus Community-Angaben und ist noch nicht am echten Ofen bestätigt.

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
