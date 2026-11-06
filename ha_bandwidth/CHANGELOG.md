# Changelog

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
