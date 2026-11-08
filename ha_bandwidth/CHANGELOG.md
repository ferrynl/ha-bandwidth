# Changelog

## 0.10.8

- Home Assistant ontdekt verkeerssensoren voor server, WAN, modem, apps en apparaten via MQTT.
- Exporteer een dashboard met bewerkbare Home Assistant-entiteitskaarten en losse kaarten voor de bestaande grafieken, tabellen, netwerkkaart en back-upbeheer.

## 0.10.7

- Dashboard in het Nederlands, Engels, Spaans en Duits. De taalkeuze rechtsboven wordt per browser bewaard.

## 0.10.6

- Automatische dagback-ups van dinsdag tot en met zondag en een weekback-up op maandag. De app bewaart de 25 nieuwste en kan ze terugzetten of verwijderen via Back-up.

## 0.10.4

- De vergelijkingsgrafiek gebruikt beter onderscheidbare kleuren en per bron een eigen lijnstijl. Lichtere vlakken en lijnen op de voorgrond verbeteren de leesbaarheid bij overlap.

## 0.10.3

- Download staat als vlak boven de nullijn en upload eronder. Ontbrekende metingen blijven open en de waarden per tijdvak zijn opvraagbaar.

## 0.10.2

- IPinfo-resultaten worden per publiek IP opgeslagen en verschijnen direct in IP- en bestemmingstabellen, ook na een herstart.
- De verkeersgrafieken krijgen balken met een licht bovenvlak, een donker zijvlak en schaduw.

## 0.10.1

- Vermeld de HTTP-status van een mislukte Zyxel-login en een eventuele Zyxel-resultaatcode, zonder inloggegevens of sessiegegevens te loggen.

## 0.10.0

- Optionele rechtstreekse Zyxel-uitlezing via `Traffic_Status` voor Cellular WAN 1 en 2.
- Houd de beginstanden per interface apart, zodat een tellerreset geen verkeer van de andere interface weggooit.

## 0.9.9

- Maak onderscheid tussen ongewijzigde Zyxel-tellers en werkelijk gemeten verkeer.
- Meld ontbrekende rechten voor de bridge-tabel en gebruik bekende wifi-poorten uit die tabel ook bij beperkte iwinfo-toegang.
- Verberg de dubbele modemstip wanneer het geconfigureerde IP overeenkomt.

## 0.9.8

- Herken bridge-poorten met `ifname` of `dev` in de OpenWrt-uitvoer.
- Gebruik de bridge-tabel ook voor wifi- en mesh-aansluitingen. Rechtstreeks gemelde wifi-associaties hebben voorrang.

## 0.9.7

- Accepteert Zyxel-sensor-ID’s met of zonder `sensor.` en meldt fouten per configuratieveld.
- Gedateerde meldingen voor uitlezing, storingen, herstel van verbindingen, versieovergangen en back-upacties.

## 0.9.6

- Vergelijk de bestaande Home Assistant-modemtellers naast OpenWrt WAN en de HA-server.

## 0.9.5

- Optioneel modem tussen internet en OpenWrt op de netwerkkaart, met instelbare naam en beheer-IP.

## 0.9.4

- Plaats OpenWrt centraal en verdeel alle apparaten rondom de router. Groepen zijn standaard open.
- Toon wifi per frequentieband via iwinfo of hostapd. Toon een LAN-poort als de bridge-tabel die bevestigt.

## 0.9.2

- Interactieve netwerkkaart met versleepbare knooppunten, zoom, verschuiven, zoeken en uitklapbare apparaatgroepen.

## 0.9.1

- Compacte apparatenwolk met zoekveld, gegroepeerd per wifi-netwerk of onbekende verbinding.
- IP-, MAC- en verkeersdetails verschijnen bij selectie van een apparaat.

## 0.9.0

- Bekende OpenWrt-apparaatnamen staan in de kolom **Domein / apparaat**. Het MAC-adres blijft onder het IP-adres zichtbaar.
- **Apparaten** bevat een netwerkdiagram met OpenWrt, zichtbare wifi-clients en apparaten waarvan de verbinding onbekend is. Gemeten apparaten zijn aanklikbaar.

## 0.8.0

- IP-adressen in **Server**, **Apps** en **IP-adressen** tonen de huidige apparaatnaam en het MAC-adres uit OpenWrt, indien bekend.
- Dubbelzinnige IP-adressen krijgen geen apparaatkoppeling. Apparaatnamen en MAC-adressen zijn doorzoekbaar in de tabellen.

## 0.7.0

- Zoek en sorteer in alle verkeerstabellen. Klik op een kolomkop om de sorteerrichting te wijzigen.
- Zoek publieke IP-adressen via IPinfo op voor ASN, netwerkorganisatie en organisatiedomein. Dit werkt met een IPinfo Lite-token en wordt op verzoek uitgevoerd.

## 0.6.0

- **Apparaten** toont upload en download per wifi- of bekabeld apparaat via OpenWrt Bandwidth Monitor.
- Klik op een apparaat om de grafiek te filteren. IPv4- en IPv6-verkeer met hetzelfde MAC-adres wordt samengevoegd.

## 0.5.0

- **Server** toont de grootste bronnen en bestemmingen op de serverinterface, inclusief verkeer dat niet afzonderlijk onder **Apps** zichtbaar is.
- De tabel toont domein indien herkenbaar, IP-adres, adrestype, protocol, poort en upload en download. Bestaande totalen blijven bewaard.

## 0.4.0

- HA-Bandwidth leest WAN-upload en -download rechtstreeks uit OpenWrt via ubus.
- **OpenWrt vergelijken** toont het WAN-verkeer van alle apparaten achter de router naast het verkeer van de HA-server.
- Bestaande gegevens en back-ups blijven behouden. Oude WAN-metingen via Home Assistant-sensoren worden apart gehouden van de nieuwe OpenWrt-metingen.

## 0.3.0

- Nieuwe tab **Back-up** voor het downloaden en terugzetten van de meetdatabase, met een automatische kopie van vóór het terugzetten.
- Nieuwe tab **Modem vergelijken** met een gezamenlijke grafiek en aparte upload- en downloadtotalen voor de modem en de HA-server.
- Modemmetingen worden opgehaald via twee instelbare cumulatieve Home Assistant-sensoren.

## 0.2.0

- Klik op een appnaam om de bestemmingen voor de gekozen dag, week, maand of het jaar te bekijken.
- Per bestemming zie je het IP-adres, het protocol, de poort en de hoeveelheid download en upload. Waar beschikbaar wordt de domeinnaam getoond met de herkomst TLS of DNS.
- De bestemmingsmeting werkt voor apps op een Docker-bridge. Verkeer van apps op het gedeelde hostnetwerk blijft opgenomen in de servermeting.
- Bestaande verkeerstotalen blijven bewaard. De bestemmingshistorie begint na deze update.

## 0.1.0

- Eerste versie met upload- en downloadgrafieken voor serververkeer, apps en IP-adressen.
- Dag-, week-, maand- en jaaroverzichten met lokale opslag in SQLite.
