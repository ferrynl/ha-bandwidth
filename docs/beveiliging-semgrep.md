# Beveiligingsbevindingen (Semgrep) en wat we ermee hebben gedaan

Dit document legt vast wat de Semgrep-scan van 28 november 2026 (25 bevindingen op `main`) betekent, wat er in de code is veranderd en waarom sommige meldingen bewust zijn onderdrukt. Het is geschreven zodat een nieuwe lezer zonder voorkennis kan beoordelen of een keuze klopt.

## In het kort

| Groep | Aantal | Beoordeling | Wat er is gedaan |
|---|---|---|---|
| SQL met losse tekst (`sqlalchemy-execute-raw-query`) | 12 | Vals alarm: geen gebruikersinvoer in de SQL-tekst | Uitleg en `# nosemgrep` bij elke plek |
| Opgemaakte SQL (`formatted-sql-query`) | 6 | Vals alarm: alleen namen uit een vast schema | Namen gaan langs `identifier()`, plus `# nosemgrep` |
| Pad-traversal (`tainted-path-traversal-stdlib`) | 2 | Vals alarm, maar de code kon duidelijker | Code aangepast |
| `urllib` met dynamische waarde (`dynamic-urllib-use-detected`) | 2 | Alleen in tests, naar de eigen testserver | Tests omgezet naar `http.client` |
| Onveilige WebSocket (`detect-insecure-websocket`) | 2 | Intern Supervisor-adres, geen wss mogelijk | Uitleg en `# nosemgrep` |
| Dockerfile zonder `USER` (`missing-user`) | 1 | Terecht, bewust niet opgelost | Uitleg bij de regel, zie hieronder |

## Per groep

### SQL met losse tekst en opgemaakte SQL
De app gebruikt de standaard `sqlite3`-module, geen SQLAlchemy. Semgrep markeert elke `execute()` waarvan de SQL niet één vaste tekst is. In alle gevallen bestaat de SQL-tekst uit vaste stukken (bijvoorbeeld een rij vraagtekens voor een `IN (...)`-lijst) en gaan alle waarden als parameters mee. Een gebruiker kan dus geen SQL invoeren.

Alleen `storage_backup.py` zet tabel- en kolomnamen in de SQL-tekst, omdat SQLite namen niet als parameter toestaat. Die namen komen uit het vaste schema `TABLES`. Sinds deze wijziging gaat elke naam langs `identifier()`, die alles buiten het schema weigert. Een geüpload bestand kan dus nooit de vorm van een opdracht bepalen. Dat is getest (`test_hardening.py`).

### Pad-traversal
- **Dashboardbestanden** (`monitor.py`): vroeger werd het bestand per verzoek gelezen. Nu staat een vaste tabel `STATIC_FILES` en worden de bestanden één keer ingelezen. Een URL is alleen een sleutel in die tabel, dus er wordt nooit een pad uit een verzoek opgebouwd. Tests proberen `/../config.yaml`, `/monitor.py` en versleutelde varianten en krijgen 400 of 404.
- **Back-up-download**: de back-up wordt in blokken van 64 kB naar de verbinding geschreven in plaats van met `shutil.copyfileobj`. Het bestand komt uit een tijdelijke map die de app zelf aanmaakt.

### `urllib` in tests
De tests deden verzoeken aan een testserver op `127.0.0.1`. Ze gebruiken nu `http.client` via `ha_bandwidth/local_http.py`. Dat bestand hoort alleen bij de tests en zit niet in de Docker-image.

### WebSocket naar `ws://supervisor`
De Home Assistant Supervisor biedt zijn API-proxy aan op het interne add-onnetwerk onder de naam `supervisor`. Daar bestaat geen `wss`. Het verkeer verlaat de host niet. Daarom is de melding onderdrukt met een uitleg in de code. Het tweede geval is een test die dit adres controleert.

### Dockerfile zonder `USER` (bewust niet opgelost)
De melding is terecht: de container draait als root. We hebben dat laten staan omdat:
- de app schrijft in `/data`, dat de Supervisor als root aanmaakt;
- de add-on draait met `host_network` en de rechten `NET_RAW` om het netwerkverkeer te meten;
- een andere gebruiker zou beide breken, en dat is hier niet te testen in een echte Home Assistant.

Wil je dit toch oplossen, doe het dan als aparte stap, samen met een test op een echte installatie. De regel staat uitgelegd in de `Dockerfile`.

## Hoe werkt een onderdrukking?
Boven de betreffende regel staat een uitleg en daaronder `# nosemgrep: <regelnaam>`. Semgrep slaat dan alleen díe regel over, op díe plek. Alle andere regels blijven gelden. Zoek ze op met:

```
grep -rn "nosemgrep" ha_bandwidth/
```

Elke onderdrukking moet een uitleg hebben. Een nieuwe `execute()` met samengestelde SQL krijgt dus een nieuwe melding, en dat is de bedoeling: kijk dan of er echt geen invoer in de SQL-tekst komt.

## Wat is niet gecontroleerd
- De echte Semgrep-regels konden niet draaien, omdat de regelserver vanuit de ontwikkelomgeving niet bereikbaar was. De plaats van de onderdrukkingen is gecontroleerd met lokale regels met dezelfde naam. Kijk na het mergen of de volgende scan de bevindingen laat verdwijnen.
- De Docker-smoketest draait in CI.

## Zelf een scan draaien
```
pip install semgrep
semgrep --config auto ha_bandwidth/
```
(Vereist toegang tot semgrep.dev.)
