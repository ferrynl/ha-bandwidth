# HA-Bandwidth

Home Assistant OS-app voor upload, download en de grootste verbruikers per dag, week, maand en jaar.

## Installatie via GitHub

1. Open **Instellingen → Apps → App store → ⋮ → Repositories**.
2. Voeg `https://github.com/ferrynl/ha-bandwidth` toe.
3. Installeer **HA-Bandwidth**. Zet bij de app **Beveiligde modus** uit om Docker-statistieken te lezen. Start de app en open de webinterface. Schakel eventueel **Weergeven in zijbalk** in.
4. Controleer bovenaan het dashboard of de gemeten interface de gewenste aansluiting is. Zet onder **Configuratie** zo nodig `interface` op de exacte interfacenaam. De standaardtijdzone is `Europe/Amsterdam`.

## Wat wordt gemeten?

- **Server** meet upload en download op één netwerkinterface. Standaard kiest de app de interface van de IPv4-default-route en valt zij terug op IPv6. De cijfers bevatten zowel lokaal verkeer als internetverkeer.
- **Apps** toont Docker-containers met een eigen netwerknamespace en bruikbare tellers. Onder **Gedeeld hostnetwerk** staan containers die de hostinterface delen, zoals Home Assistant Core. Dat verkeer zit in het servertotaal. Een integratie binnen Core heeft hier geen aparte teller. App-tellers kunnen intern Docker-verkeer bevatten. Tel de appregels en het servertotaal daarom niet bij elkaar op.
- **IP-adressen** toont de externe kant van inkomend en uitgaand IPv4- en IPv6-verkeer op de gekozen interface. Dit zijn waargenomen IP-bytes. Packet drops, offloading, tunnels en het verschil tussen IP- en linklaag kunnen afwijkingen geven ten opzichte van het servertotaal. Het dashboard slaat geen packetinhoud op en koppelt IP-adressen niet aan individuele apps. Met `track_peers: false` kan deze meting uit.
- Historie begint na installatie. Verkeer van vóór de installatie, zoals een bestaande routerteller, kan niet worden teruggehaald. Tellers worden iedere 30 seconden uitgelezen. Een onderbreking of herstart kan een meetgat veroorzaken.
- Het dagoverzicht is per uur, week en maand per dag, en jaar per maand. De app bewaart 400 lokale kalenderdagen in SQLite in de eigen `/data`-map. Gebruik een Home Assistant-back-up van de app om historie te behouden.

De app gebruikt de Docker-socket uitsluitend voor leesverzoeken. Toegang tot de Docker-socket is een ruime hostmachtiging, ook met een alleen-lezen mount. Ingress biedt toegang via Home Assistant. De HTTP-server weigert verbindingen vanaf andere bronadressen dan de Supervisor-ingressproxy.
