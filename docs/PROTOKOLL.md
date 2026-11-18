# Protokoll: Befehle des Maestro-Moduls

Ermittelt durch einen passiven Mitschnitt der unverschlüsselten Verbindung zwischen Ofen und MCZ-Server, während die MCZ-App bedient wurde (MCZ Hydro-Ofen, Maestro-Modul Firmware 1.2.5). Es wurde kein App-Code untersucht. Alle Beispiele sind neutral; Seriennummern und Adressen fehlen absichtlich.

Der Server schickt Anfragen als Socket.IO-Ereignis `ProvaStufa` mit `{"richiesta": "C|C|…"}`. Der Ofen antwortet mit `rispondo` und `{"stringaRicevuta": "…"}`. Die ersten zwei Zeichen der Antwort sagen, was sie enthält.

## Lesen

| Anfrage | Antwort | Inhalt |
|---|---|---|
| `RecuperoInfo` | `01\|…` | Status (Zustand, Temperaturen, Eco, Chrono, Kessel-Soll …), siehe `INFO_FIELDS` in `protocol.py` |
| `RecuperoParametriExtra` | `03\|…` | Zusatzparameter; belegt: Feld 3 Quelle Raumfühler, Feld 4 Eco-Stop-Verzögerung (Sekunden, 4 Hex-Zeichen), Feld 5 Eco-Stop-Hysterese unten, Feld 22 Relais-Ausgang |
| `RecuperoGiornoChrono` | `04\|Tag0\|…\|Tag6\|T1\|T2\|T3` | Zeitprogramm, siehe unten |
| `RecuperoParametri`, `RecuperaAllarmi`, `RecuperoVersioneSW` | `00`, `0A`, `0E` | noch nicht ausgewertet |

## Schreiben: normale Parameter
`WriteParametri|ID|Wert` (Wert dezimal). Der Ofen antwortet mit einer vollständigen Statuszeile `01|…`.

| ID | Bedeutung | Werte |
|---|---|---|
| 34 | Ein / Aus | 1 ein, 40 aus. Beim Ausschalten geht auch Chrono aus |
| 41 | Eco-Stop | 0 aus, 1 ein |
| 42 | Raum-Solltemperatur | °C × 2 |
| 50 | Töne | 0 aus, 1 ein (die App schickt bei jeder Anmeldung 0) |
| 51 | Kessel-Solltemperatur | °C × 2 |
| 58 | Sommer / Winter | 0 Winter; 1 vermutlich Sommer (nicht beobachtet) |
| 148 | Pelletstand-Sensor | 0 aus, 1 ein. **Nicht freigegeben**: ohne Sensor droht eine Störung |
| 1111 | Chrono | 0 aus, 1 ein |

## Schreiben: technische Parameter
`WriteTecniciParametri|ID|Bytes|Wert` (Wert hexadezimal, 2 Zeichen je Byte). Der Ofen antwortet darauf nicht; manche Werte stehen danach in den Zusatzparametern.

| ID | App-Bezeichnung | Bytes | Beispiel |
|---|---|---|---|
| 297 | Heizkessel positive Hysterese | 1 | `297\|1\|00` |
| 296 | Heizkessel negative Hysterese | 1 | `296\|1\|02` |
| 289 | Raum positive Hysterese | 1 | |
| 288 | Raum negative Hysterese | 1 | |
| 295 | Positive Hysterese Eco Stop | 1 | |
| 294 | Negative Hysterese Eco Stop | 1 | |
| 148 | Abschaltverzögerung Eco Stop (Sekunden) | 2 | `148\|2\|0078` = 120 s |
| 517 | Mindesttemperatur Zirkulator On (°C) | 1 | `517\|1\|32` = 50 °C |
| 356 | Eingang NTC 1 (Quelle Raumfühler) | 1 | 00 Thermostat, 01 Fühler im Ofen, FF Wi-Fi-Sonde. **Gesperrt** |
| 365 | Relay aux | 1 | FF nicht belegt, 01 Pumpe Pufferspeicher. **Gesperrt** |

Hinweis: Technischer Parameter 148 und normaler Parameter 148 sind verschiedene Dinge.

**Warum 356 und 365 gesperrt sind:** Das ist die Verdrahtung der Anlage. Steht die Quelle des Raumfühlers auf „Wi-Fi-Sonde“, meldet der Ofen 126 °C Raumtemperatur und regelt nur noch nach dem Kessel, bis ihm jemand die Temperatur übers Netz schickt. Wie das geht, ist noch nicht bekannt. Ein falsch belegter Relais-Ausgang kann ein angeschlossenes Gerät schalten. Die MCZ-App zeigt in diesen Menüs nicht zuverlässig an, was im Ofen steht.

## Zeitprogramm
- Je Tag 24 Hex-Zeichen = 48 halbe Stunden ab 0:00, je 2 Bit, höchstwertige zuerst: `00` aus, `01` T1, `10` T2, `11` T3. Beispiel: `555555…` = T1 ab Mitternacht, `AAAAAA…` = T2.
- Tag 0 = Sonntag, 1 = Montag … 6 = Samstag.
- T1, T2, T3: ganze °C, hexadezimal (`15` = 21 °C).
- Schreiben: `ScriviGiornoChrono|Tag|24 Hex-Zeichen`. Der Ofen antwortet mit einer Statuszeile.
- Ist Chrono an, übernimmt der Ofen die Raum-Solltemperatur aus der aktuellen Stufe (T1/T2/T3).

## Uhrzeit
`SalvaDataOra|TTMMJJJJhhmm`, z. B. `SalvaDataOra|020120300304` = 2. 1. 2030, 03:04. Antwort: `AA|TTMMJJJJhhmm`. Geht die Uhr falsch, schaltet das Zeitprogramm zur falschen Zeit.

## Leistungsstufe
Im Mitschnitt gab es keinen Befehl dafür; die App bietet sie nur im Installateur-Menü an. Der Hydro-Ofen regelt die Leistung selbst nach dem Abstand zur Kessel-Solltemperatur.
