# MCZ Maestro lokal (ohne Cloud)

Home-Assistant-Integration für MCZ-Pelletöfen mit Maestro-WLAN-Modul, **ohne MCZ-Cloud**.

> ⚠️ **Frühe Entwicklung, nur lesen.** Sensoren ja, Schalten noch nicht.
> Lesen ist **mit einem echten Ofen getestet** (MCZ Musa Hydro, Maestro-Modul Firmware 1.2.5): Werte stimmen mit der Anzeige am Ofen. Die Home-Assistant-Integration selbst lief dabei noch nicht auf echter Hardware, sondern derselbe Server-Code auf einem Rechner.

Bedienung: [docs/HANDBUCH.md](docs/HANDBUCH.md)

## Wie es funktioniert
Das Maestro-Modul baut von sich aus eine unverschlüsselte Verbindung zum MCZ-Server auf. Dein Router leitet diese Verbindung (nur für den Ofen) auf Home Assistant um, und diese Integration übernimmt die Rolle des Servers. Die MCZ-App funktioniert dann nicht mehr.

## Installation
Später über den Marketplace (früher HACS): *Einstellungen → Marketplace → eigenes Repository* mit dem Link zu diesem Repository.

## Lizenz
Apache-2.0. Feldpositionen des Protokolls nach öffentlich dokumentierten Community-Beobachtungen und eigenen Mitschnitten; kein fremder Code übernommen.
