# HA-Bandwidth

Home Assistant OS-app voor upload, download en de grootste verbruikers per dag, week, maand en jaar.

## Installatie via GitHub

1. Open **Instellingen → Apps → App store → ⋮ → Repositories**.
2. Voeg `https://github.com/ferrynl/ha-bandwidth` toe.
3. Installeer **HA-Bandwidth**. Zet bij de app **Beveiligde modus** uit om Docker-statistieken te lezen. Start de app en open de webinterface. Schakel eventueel **Weergeven in zijbalk** in.
4. Controleer bovenaan het dashboard of de gemeten interface de gewenste aansluiting is. Zet onder **Configuratie** zo nodig `interface` op de exacte interfacenaam. De standaardtijdzone is `Europe/Amsterdam`.

## Filteren, sorteren en IPinfo

Gebruik de zoekbalk boven een verkeerstabel en klik op een kolomkop om te sorteren. Dit werkt op de weergegeven regels en laat de grafiek en periodetotalen intact.

Vul bij **HA-Bandwidth → Configuratie** je IPinfo Lite-token in bij `ipinfo_token`, sla op en herstart de app. Klik naast een publiek IP-adres op **IPinfo** om het ASN, de netwerkorganisatie en het organisatiedomein op te zoeken. Alleen een aangeklikt publiek adres wordt naar IPinfo gestuurd. Het organisatiedomein komt van IPinfo en kan verschillen van het TLS- of DNS-domein dat in het verkeer is waargenomen. [IPinfo Lite](https://ipinfo.io/developers/lite-api)

## Lokale IP-adressen herkennen

Met de bestaande OpenWrt-verbinding toont HA-Bandwidth bij bekende IP-adressen de apparaatnaam en het MAC-adres uit `luci-rpc.getHostHints`. Dit werkt in **Server**, **Apps** en **IP-adressen**. Het routeraccount moet de methode mogen lezen. De namen worden gekoppeld op basis van de huidige routerlijst en kunnen afwijken voor oudere metingen als een adres intussen opnieuw is toegewezen. Een adres dat OpenWrt aan meer dan één MAC-adres koppelt, krijgt geen apparaatnaam.

## OpenWrt vergelijken

Vul op het tabblad **Configuratie** van HA-Bandwidth het LAN-adres van je OpenWrt-router in bij `openwrt_url` (bijvoorbeeld `http://192.168.1.1`). Vul de gebruikersnaam en het wachtwoord van de router in bij `openwrt_username` en `openwrt_password`. Laat `openwrt_interface` op `wan` staan als dat de naam van je WAN-interface is. Sla op, herstart de app en open **OpenWrt vergelijken**.

De router moet vanuit Home Assistant bereikbaar zijn op de HTTP(S)-interface voor ubus. Op een standaardinstallatie met uhttpd wordt `/ubus` geleverd door `uhttpd-mod-ubus`. De app gebruikt `session.login`, `network.interface.wan status` (met jouw interfacenaam) en `network.device status`. Een rpcd-account met leesrechten voor die twee statusmethoden volstaat. HTTPS vereist een certificaat dat de app vertrouwt. [OpenWrt ubus-documentatie](https://openwrt.org/docs/techref/ubus)

OpenWrt WAN telt verkeer over de gekozen WAN-interface van alle aangesloten apparaten samen. Verkeer tussen lokale apparaten gaat normaal niet via WAN. De HA-server meet zijn eigen interface inclusief lokaal verkeer. De grafiek toont beide bronnen met dezelfde tijdindeling en schaal. De eerste uitlezing legt de beginstand vast. Ook na een tellerreset of wisseling van interface wordt eerst een nieuwe beginstand vastgelegd.

Eerder ingestelde cumulatieve Home Assistant-sensoren blijven bruikbaar als `openwrt_url` leeg is. Die historie wordt apart bewaard van de rechtstreekse OpenWrt-metingen.

## Netwerkdiagram

Op **Apparaten** verbindt het diagram internet, OpenWrt en de apparaten die de router kent of waarvoor in de gekozen periode verkeer is gemeten. Wifi-clients die OpenWrt rechtstreeks ziet, worden per SSID gegroepeerd. Bij andere apparaten geeft de lijn alleen de logische route via OpenWrt weer. Het diagram kan de fysieke poort of route via een losse switch, mesh-node of accesspoint niet afleiden. Klik op een gemeten apparaat om de verkeersgrafiek te selecteren.

## Verkeer per apparaat

Installeer `luci-app-nlbwmon` op OpenWrt en controleer of **Status → Bandwidth Monitor** op de router verkeer toont. De app gebruikt de bestaande OpenWrt-verbinding en leest hetzelfde overzicht als LuCI. Voor een beperkt routeraccount is leestoegang tot `luci-app-nlbwmon` nodig. Apparaatnamen uit OpenWrt worden gebruikt als ze beschikbaar zijn.

Open **Apparaten** in HA-Bandwidth. De tabel toont upload en download per apparaat voor de gekozen periode. Klik op een apparaatnaam voor de bijbehorende grafiek. De app voegt IPv4- en IPv6-regels met hetzelfde MAC-adres samen. Zonder herkenbaar MAC-adres gebruikt de app het IP-adres. Metingen beginnen na de eerste uitlezing van de router. OpenWrt meet via de router gevolgde verbindingen. Lokaal verkeer dat rechtstreeks via wifi of een switch loopt, valt buiten die meting.

## Back-up

Open **Back-up** om een SQLite-kopie met de volledige meetgeschiedenis te downloaden. Selecteer een SQLite-back-up van HA-Bandwidth, bevestig de vervanging en klik op **Back-up terugzetten**. De app controleert het bestand en bewaart automatisch één downloadbare kopie van de meetgegevens van vóór het terugzetten. Het uploadmaximum is 256 MiB. Een back-up via Home Assistant zelf blijft beschikbaar voor de hele app inclusief instellingen.

## Bronnen en bestemmingen van de server

Op **Server** staan vanaf 0.5.0 de grootste IP-bronnen en -bestemmingen op de gekozen serverinterface. De tabel omvat ook zichtbaar verkeer van Home Assistant Core en andere software op het gedeelde hostnetwerk. Ze wijst dat verkeer niet toe aan een proces of integratie. Bij download is het adres de bron en bij upload de bestemming. De aanduiding Publiek IP of Lokaal / speciaal IP is gebaseerd op de adresruimte. De optie `track_peers` bestuurt deze meting.

## Bestemmingen per app

Kies **Apps** en klik op een appnaam. Het detailoverzicht volgt de ingestelde dag, week, maand of het jaar. Per regel zie je het domein, het IP-adres, het IP-protocol (zoals TCP of UDP), de poort van de wederpartij en de gemeten download en upload. De tabel toont maximaal 100 regels, gesorteerd op verbruik.

De app meet op Docker-bridges. Home Assistant Core en andere containers die de hostnetwerknamespace delen hebben hier geen eigen uitsplitsing. Een zichtbaar TLS ClientHello kan de domeinnaam van een verbinding opleveren. Een eenduidig, waargenomen DNS-antwoord geeft een aanwijzing voor het domein. Bij gedeelde IP-adressen, verborgen DNS of een niet-zichtbare TLS-handshake kan alleen het IP-adres overblijven. De app ontsleutelt geen verkeer en schrijft geen packetinhoud naar schijf.

De bestemmingshistorie begint met versie 0.2.0. Bestaande verkeerstotalen blijven bewaard. Met `track_app_destinations: false` stop je het verzamelen van nieuwe app-bestemmingen.

## Wat wordt gemeten?

- **Server** meet upload en download op één netwerkinterface. Standaard kiest de app de interface van de IPv4-default-route en valt zij terug op IPv6. De cijfers bevatten zowel lokaal verkeer als internetverkeer.
- **Apps** toont Docker-containers met een eigen netwerknamespace en bruikbare tellers. Onder **Gedeeld hostnetwerk** staan containers die de hostinterface delen, zoals Home Assistant Core. Dat verkeer zit in het servertotaal. Een integratie binnen Core heeft hier geen aparte teller. App-tellers kunnen intern Docker-verkeer bevatten. Tel de appregels en het servertotaal daarom niet bij elkaar op.
- **IP-adressen** toont de externe kant van inkomend en uitgaand IPv4- en IPv6-verkeer op de gekozen interface. Dit zijn waargenomen IP-bytes. Packet drops, offloading, tunnels en het verschil tussen IP- en linklaag kunnen afwijkingen geven ten opzichte van het servertotaal. Het dashboard slaat geen packetinhoud op en koppelt IP-adressen niet aan individuele apps. Met `track_peers: false` kan deze meting uit.
- Historie begint na installatie. Verkeer van vóór de installatie, zoals een bestaande routerteller, kan niet worden teruggehaald. Tellers worden iedere 30 seconden uitgelezen. Een onderbreking of herstart kan een meetgat veroorzaken.
- Het dagoverzicht is per uur, week en maand per dag, en jaar per maand. De app bewaart 400 lokale kalenderdagen in SQLite in de eigen `/data`-map. Gebruik een Home Assistant-back-up van de app om historie te behouden.

De app gebruikt de Docker-socket uitsluitend voor leesverzoeken. Toegang tot de Docker-socket is een ruime hostmachtiging, ook met een alleen-lezen mount. Ingress biedt toegang via Home Assistant. De HTTP-server weigert verbindingen vanaf andere bronadressen dan de Supervisor-ingressproxy.
