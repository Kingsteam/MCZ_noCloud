# MCZ Maestro lokal (ohne Cloud)

Home-Assistant-Integration für MCZ-Pelletöfen mit Maestro-WLAN-Modul, **ohne MCZ-Cloud**.

> ⚠️ **Frühe Entwicklung.** Noch nicht mit echter Hardware getestet. Noch keine Entitäten.

## Wie es funktioniert
Das Maestro-Modul baut von sich aus eine unverschlüsselte Verbindung zum MCZ-Server auf. Dein Router leitet diese Verbindung (nur für den Ofen) auf Home Assistant um, und diese Integration übernimmt die Rolle des Servers. Die MCZ-App funktioniert dann nicht mehr.

## Installation
Später über den Marketplace (früher HACS): *Einstellungen → Marketplace → eigenes Repository* mit dem Link zu diesem Repository.

## Lizenz
MIT. Feldpositionen des Protokolls nach öffentlich dokumentierten Community-Beobachtungen und eigenen Mitschnitten; kein fremder Code übernommen.
