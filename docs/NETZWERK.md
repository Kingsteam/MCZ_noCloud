# Netzwerk: den Ofen auf Home Assistant umleiten

Das Maestro-Modul im Ofen verbindet sich von selbst mit dem MCZ-Server, und zwar unverschlüsselt über **TCP-Port 9000**. Der Name und die Adresse des Servers sind fest eingebaut; ändern lässt sich das am Ofen nicht. Damit sich der Ofen stattdessen mit Home Assistant verbindet, muss der **Router** diese Verbindung umleiten.

> Alle Adressen in dieser Anleitung sind Beispiele. Setze deine eigenen ein.

## Was du brauchst
| Wert | Beispiel | Woher |
|---|---|---|
| IP des Ofens | `192.168.20.50` | Router, Liste der Geräte. Am besten eine **feste** IP vergeben (DHCP-Reservierung) |
| IP von Home Assistant | `192.168.20.10` | *Einstellungen → System → Netzwerk* |
| Adresse des MCZ-Servers | `app.mcz.it` | Seine aktuelle IP findest du mit `nslookup app.mcz.it` |
| Port | `9000` | wie in der Integration eingestellt |

## Die Regeln

### 1. Umleitung (DNAT, „Destination NAT“, „Portumleitung“)
Verbindungen **vom Ofen** zum **MCZ-Server, Port 9000** gehen stattdessen an **Home Assistant, Port 9000**.

| Feld | Wert |
|---|---|
| Typ | Destination NAT (DNAT) |
| Eingangs-Schnittstelle | das Netz, in dem der Ofen hängt |
| Protokoll | TCP |
| Quelle | IP des Ofens |
| Ziel | IP des MCZ-Servers, Port 9000 |
| Umleiten an | IP von Home Assistant, Port 9000 |

Grenze die Regel **auf die IP des Ofens** ein. So bleiben alle anderen Geräte unberührt.

### 2. Nur wenn Ofen und Home Assistant im **selben Netz** sind: Masquerade
Sonst antwortet Home Assistant dem Ofen direkt, an der Umleitung vorbei, und der Ofen verwirft die Antwort, weil sie nicht vom MCZ-Server zu kommen scheint. Abhilfe schafft eine zweite Regel:

| Feld | Wert |
|---|---|
| Typ | Masquerade (oder Source NAT auf die Router-IP) |
| Ausgangs-Schnittstelle | das gemeinsame Netz |
| Protokoll | TCP |
| Quelle | IP des Ofens |
| Ziel | IP von Home Assistant, Port 9000 |

Liegen Ofen und Home Assistant in **verschiedenen Netzen** (z. B. Ofen im IoT-VLAN, HA im Server-VLAN), brauchst du diese Regel nicht. Dafür muss die **Firewall** Verbindungen vom Ofen zu HA auf TCP 9000 erlauben.

## Beispiele für verschiedene Router
Die Bezeichnungen sind je nach Firmware leicht anders.

- **UniFi (Network 9 oder neuer):** *Einstellungen → Routing → NAT → Eintrag erstellen*. Typ *Destination NAT* und, falls nötig, einen zweiten Eintrag *Masquerade*, jeweils mit den Feldern oben.
- **OPNsense / pfSense:** *Firewall → NAT → Port Forward*: Interface = Netz des Ofens, Source = Ofen, Destination = MCZ-Server, Port 9000, Redirect target = HA, Port 9000. Für dasselbe Netz zusätzlich *NAT reflection* oder eine *Outbound-NAT-Regel*.
- **OpenWrt:** *Netzwerk → Firewall → Port Forwards* mit Quelle = Ofen, externe IP = MCZ-Server. Für dasselbe Netz *NAT Loopback* aktivieren.
- **MikroTik:** `/ip firewall nat add chain=dstnat src-address=<Ofen> dst-address=<MCZ-Server> protocol=tcp dst-port=9000 action=dst-nat to-addresses=<HA> to-ports=9000` und für dasselbe Netz `chain=srcnat src-address=<Ofen> dst-address=<HA> protocol=tcp dst-port=9000 action=masquerade`.
- **Fritz!Box und die meisten Provider-Router:** Sie können ausgehende Verbindungen nicht umleiten. Möglich ist dann nur ein eigener DNS-Eintrag für `app.mcz.it`, der auf Home Assistant zeigt (z. B. mit Pi-hole oder AdGuard Home). Das klappt nur, wenn das Modul den Namen auflöst und nicht eine fest eingebaute IP benutzt. Das ist noch nicht getestet.

## Aktivieren
1. **Zuerst** die Integration in Home Assistant einrichten. Sie wartet dann auf Port 9000.
2. Dann die Regel(n) im Router anlegen.
3. Die Umleitung gilt nur für **neue** Verbindungen. Eine bestehende Verbindung des Ofens zur Cloud bleibt erhalten, bis sie abbricht. Den Ofen deshalb kurz stromlos machen oder die Verbindung im Router trennen. Danach meldet er sich innerhalb einer Minute.
4. In Home Assistant steht *Verbunden* jetzt auf *Verbunden*. Meldet sich der Ofen 10 Minuten nach dem Einrichten noch immer nicht, zeigt Home Assistant unter *Einstellungen → Reparaturen* einen Hinweis.

## Prüfen
Die Integration hat dafür den Diagnose-Sensor **Verbindungsprüfung**:

| Zustand | Bedeutung |
|---|---|
| *Wartet auf den Ofen* | Home Assistant lauscht, aber es kommt nichts an: Umleitung fehlt oder greift noch nicht (Ofen kurz stromlos machen) |
| *Verbunden* | alles gut. Das Attribut *Verbindung von* zeigt die Absenderadresse: mit Masquerade die Router-Adresse, sonst die des Ofens |
| *Getrennt* | war verbunden, ist es nicht mehr; *Getrennt seit* sagt, wann |

Kommt zwar ein *Letzter Verbindungsversuch*, aber kein *Verbunden*, erreicht etwas den Port, spricht aber nicht das Ofen-Protokoll (z. B. ein Port-Scanner oder ein falsch umgeleitetes Gerät).

- **Verbunden bleibt auf *Getrennt*:** Stimmt die IP des Ofens? Ist der Zähler der Regel im Router gestiegen? Bei demselben Netz: Gibt es die Masquerade-Regel?
- **Mitschnitt am Router** (falls möglich): Es müssen Pakete vom Ofen zu HA auf Port 9000 zu sehen sein.
- Im Log von Home Assistant erscheint „Ofen angemeldet“, sobald es klappt.

## Rückweg
Die Regel(n) im Router löschen oder deaktivieren und den Ofen kurz stromlos machen. Er verbindet sich wieder mit der MCZ-Cloud, und die MCZ-App funktioniert wieder.

**Wichtig:** Solange die Umleitung aktiv ist, funktioniert die MCZ-App nicht. Die Integration ersetzt sie (siehe Handbuch).

## Sicherheit
Die Verbindung zwischen Ofen und Server ist unverschlüsselt und ohne Passwort, bei der MCZ-Cloud genauso wie hier. Öffne Port 9000 deshalb **nie zum Internet hin**. Die Umleitung betrifft nur Verbindungen, die vom Ofen ausgehen.
