# Handbuch: MCZ Maestro lokal (ohne Cloud)

> ⚠️ **Stand 0.3.0: nur lesen.** Die Integration zeigt Werte des Ofens an, schalten kann sie noch nicht. Das Lesen ist mit einem echten Ofen getestet (Werte stimmen mit der Ofenanzeige), die Integration als Ganzes noch nicht. Alle Bilder stammen aus einer simulierten Test-Instanz.

## Was die Integration macht
Das WLAN-Modul (Maestro) im Ofen meldet sich von selbst beim MCZ-Server. Wenn dein Router diese Verbindung auf Home Assistant umleitet, übernimmt diese Integration die Rolle des Servers. Home Assistant fragt dann alle 10 Sekunden den Zustand des Ofens ab. Eine Internetverbindung braucht es dafür nicht.

**Wichtig:** Solange die Umleitung aktiv ist, funktioniert die MCZ-App nicht mehr.

## Einrichten
1. Integration installieren (später über *Einstellungen → Marketplace*).
2. *Einstellungen → Geräte & Dienste → Integration hinzufügen → „MCZ Maestro lokal“*.
3. Port eingeben (Standard **9000**, wie beim MCZ-Server). Nur ändern, wenn auf Home Assistant schon etwas diesen Port benutzt; dann muss der Router auf den neuen Port umleiten.
4. Umleitung im Router einrichten (Anleitung folgt in `docs/NETZWERK.md`).
5. Die Umleitung wirkt nur auf **neue** Verbindungen. Den Ofen deshalb einmal kurz stromlos machen; danach meldet er sich innerhalb einer Minute.
6. Wird die Umleitung wieder entfernt, verbindet sich der Ofen von selbst wieder mit der MCZ-Cloud, sobald diese Integration die Verbindung schließt (z. B. Integration deaktivieren).

![Integration](bilder/integration.png)

## Was du siehst
Das Gerät **Pelletofen** mit Seriennummer und Firmware des Moduls (werden bei der ersten Anmeldung des Ofens eingetragen):

![Gerät](bilder/geraet.png)

| Entität | Bedeutung |
|---|---|
| Zustand | Was der Ofen gerade macht, z. B. *Aus*, *Start 1 kalt*, *Leistung 2*, *Abkühlen*, *Störung* |
| Wassertemperatur | Kesselwasser (Hydro-Öfen) |
| Raumtemperatur | Fühler im Ofen. Achtung: Er sitzt nah an der Wärmequelle und kann deutlich zu hoch messen. Für Automationen besser einen eigenen Raumfühler verwenden |
| Solltemperatur | am Ofen eingestellte Wunschtemperatur |
| Abgastemperatur | im Abgasrohr |
| Rücklauf-/Puffertemperatur | nur wenn der Fühler angeschlossen ist |
| Zündungen | Zähler aller Zündvorgänge; steigt er schnell, taktet der Ofen |
| Betriebsstunden, Stunden bis Wartung | Zähler des Ofens |
| In Betrieb | *Ein*, solange der Ofen zündet oder brennt |
| Störung | *Problem*, wenn der Ofen einen Alarm (A01 …) meldet |
| Verbunden | ob der Ofen gerade mit Home Assistant verbunden ist |
| Diagnose (Zustandsnummer, Leistungsstufe, Pumpe, Abgasgebläse, Platinentemperatur) | Rohwerte für die Fehlersuche |

Ist der Ofen **nicht verbunden**, zeigen alle Werte „Nicht verfügbar“, nur *Verbunden* steht auf *Getrennt*.

## Verlauf
Zustand und Temperaturen landen im Verlauf von Home Assistant, z. B. um zu sehen, wie oft der Ofen zündet:

![Verlauf](bilder/verlauf.png)

## Wenn etwas nicht geht
- **„Port lässt sich nicht öffnen“:** Ein anderes Programm benutzt den Port. Anderen Port wählen (Integration löschen und neu hinzufügen) und die Umleitung im Router anpassen.
- **Verbunden bleibt auf *Getrennt*:** Umleitung im Router prüfen. Liegen Ofen und Home Assistant im **selben Netz**, braucht es zusätzlich eine Masquerade-Regel (siehe `docs/NETZWERK.md`). Ofen kurz stromlos machen.
