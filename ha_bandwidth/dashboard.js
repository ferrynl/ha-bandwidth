export function mountDashboard(document, fetch, pageUrl, shared) {

const locales = {nl: "nl-NL", en: "en-GB", es: "es-ES", de: "de-DE"};
const translationColumn = {en: 0, es: 1, de: 2};
const translations = new Map([
  ["Dashboard downloaden mislukt.",["Could not download the dashboard.","No se pudo descargar el panel.","Das Dashboard konnte nicht heruntergeladen werden."]],
  ["Home Assistant-installatie controleren",["Check Home Assistant setup","Comprobar la instalación de Home Assistant","Home-Assistant-Einrichtung prüfen"]],
  ["Home Assistant-installatie",["Home Assistant setup","Instalación de Home Assistant","Home-Assistant-Einrichtung"]],
  ["De MQTT-broker ontvangt de meetwaarden. De MQTT-integratie maakt er entiteiten van in Home Assistant.",["The MQTT broker receives measurements. The MQTT integration turns them into Home Assistant entities.","El broker MQTT recibe las mediciones. La integración MQTT las convierte en entidades de Home Assistant.","Der MQTT-Broker empfängt Messwerte. Die MQTT-Integration stellt sie als Entitäten in Home Assistant bereit."]],
  ["Opnieuw controleren",["Check again","Comprobar de nuevo","Erneut prüfen"]],
  ["Sluiten",["Close","Cerrar","Schließen"]],
  ["Installatie wordt gecontroleerd…",["Checking setup…","Comprobando instalación…","Einrichtung wird geprüft…"]],
  ["Alle controles zijn geslaagd.",["All checks passed.","Todas las comprobaciones son correctas.","Alle Prüfungen waren erfolgreich."]],
  ["Volg de onderstaande stappen en controleer daarna opnieuw.",["Follow the steps below, then check again.","Sigue los pasos siguientes y vuelve a comprobar.","Befolge die folgenden Schritte und prüfe danach erneut."]],
  ["De installatiecheck kon niet worden geladen. Probeer het opnieuw.",["Could not load the setup check. Try again.","No se pudo cargar la comprobación. Inténtalo de nuevo.","Die Prüfung konnte nicht geladen werden. Versuche es erneut."]],
  ["MQTT-broker",["MQTT broker","Broker MQTT","MQTT-Broker"]],
  ["MQTT-integratie",["MQTT integration","Integración MQTT","MQTT-Integration"]],
  ["Publicatie vanuit HA-Bandwidth",["Publishing from HA-Bandwidth","Publicación desde HA-Bandwidth","Veröffentlichung durch HA-Bandwidth"]],
  ["HA-Bandwidth-entiteiten",["HA-Bandwidth entities","Entidades de HA-Bandwidth","HA-Bandwidth-Entitäten"]],
  ["Gereed",["Ready","Listo","Bereit"]],
  ["Ontbreekt",["Missing","Falta","Fehlt"]],
  ["Nog niet gereed",["Not ready yet","Aún no está listo","Noch nicht bereit"]],
  ["Uitgeschakeld",["Disabled","Desactivado","Deaktiviert"]],
  ["Niet te controleren",["Could not verify","No se pudo comprobar","Prüfung nicht möglich"]],
  ["Installeer en start Mosquitto broker in de appstore, of start je bestaande MQTT-broker die bij Supervisor is geregistreerd.",["Install and start Mosquitto broker from the app store, or start your existing MQTT broker registered with Supervisor.","Instala e inicia Mosquitto broker desde la tienda de aplicaciones o inicia tu broker MQTT registrado en Supervisor.","Installiere und starte Mosquitto broker aus dem App-Store oder starte deinen bei Supervisor registrierten MQTT-Broker."]],
  ["Open appstore",["Open app store","Abrir tienda de aplicaciones","App-Store öffnen"]],
  ["Open Apparaten en diensten. Kies Configureren bij de gevonden MQTT-integratie, of kies Integratie toevoegen en zoek naar MQTT.",["Open Devices & services. Select Configure for discovered MQTT, or add an integration and search for MQTT.","Abre Dispositivos y servicios. Configura la integración MQTT detectada o añade una integración y busca MQTT.","Öffne Geräte und Dienste. Konfiguriere die erkannte MQTT-Integration oder füge eine Integration hinzu und suche nach MQTT."]],
  ["Open Apparaten en diensten",["Open Devices & services","Abrir Dispositivos y servicios","Geräte und Dienste öffnen"]],
  ["Zet publish_to_ha aan onder HA-Bandwidth → Configuratie en herstart de app.",["Enable publish_to_ha under HA-Bandwidth → Configuration and restart the app.","Activa publish_to_ha en HA-Bandwidth → Configuración y reinicia la aplicación.","Aktiviere publish_to_ha unter HA-Bandwidth → Konfiguration und starte die App neu."]],
  ["Wacht ongeveer een minuut nadat de broker is gestart. Controleer het HA-Bandwidth-logboek als dit zo blijft.",["Wait about a minute after the broker starts. Check the HA-Bandwidth log if this persists.","Espera aproximadamente un minuto después de iniciar el broker. Consulta el registro de HA-Bandwidth si el problema continúa.","Warte nach dem Brokerstart etwa eine Minute. Prüfe das HA-Bandwidth-Protokoll, falls der Status bleibt."]],
  ["Controleer of MQTT verbonden is met dezelfde broker en of MQTT Discovery aanstaat. Als je de sensoren hebt hernoemd, kijk dan bij het apparaat HA-Bandwidth.",["Check that MQTT is connected to the same broker and MQTT Discovery is enabled. If you renamed the sensors, check the HA-Bandwidth device.","Comprueba que MQTT esté conectado al mismo broker y que la detección MQTT esté activada. Si cambiaste el nombre de los sensores, consulta el dispositivo HA-Bandwidth.","Prüfe, ob MQTT mit demselben Broker verbunden und MQTT Discovery aktiviert ist. Wenn du Sensoren umbenannt hast, prüfe das Gerät HA-Bandwidth."]],
  ["Home Assistant of Supervisor gaf geen bruikbaar antwoord. Probeer het opnieuw zodra Home Assistant volledig is gestart.",["Home Assistant or Supervisor did not return a usable response. Try again after Home Assistant has started fully.","Home Assistant o Supervisor no devolvió una respuesta válida. Inténtalo de nuevo cuando Home Assistant haya iniciado por completo.","Home Assistant oder Supervisor lieferte keine verwertbare Antwort. Versuche es nach dem vollständigen Start von Home Assistant erneut."]],
  ["Home Assistant-dashboard downloaden",["Download Home Assistant dashboard","Descargar panel de Home Assistant","Home Assistant-Dashboard herunterladen"]],
  ["Publiek IP",["Public IP","IP pública","Öffentliche IP"]],
  ["Lokaal / speciaal IP",["Local / special-use IP","IP local / de uso especial","Lokale IP / IP für besondere Zwecke"]],
  ["5G-modem via HA",["5G modem via HA","Módem 5G mediante HA","5G-Modem über HA"]],
  ["HA-server",["HA server","Servidor HA","HA-Server"]],
  ["beginstand gelezen, wacht op volgende meting",["initial reading recorded, waiting for the next measurement","lectura inicial registrada, esperando la siguiente medición","Ausgangswert erfasst, nächste Messung steht aus"]],
  ["tellers uitgelezen, maar deze zijn sinds de vorige meting niet veranderd",["counters read, unchanged since the previous measurement","contadores leídos, sin cambios desde la medición anterior","Zähler ausgelesen, seit der letzten Messung unverändert"]],
  ["verkeer gemeten",["traffic measured","tráfico medido","Datenverkehr gemessen"]],
  ["Taal",["Language","Idioma","Sprache"]],
  ["HOME ASSISTANT · NETWERK",["HOME ASSISTANT · NETWORK","HOME ASSISTANT · RED","HOME ASSISTANT · NETZWERK"]],
  ["Metingen ophalen…",["Loading measurements…","Cargando mediciones…","Messwerte werden geladen…"]],
  ["Meetbron",["Measurement source","Fuente de medición","Messquelle"]],
  ["Server",["Server","Servidor","Server"]],
  ["Apps",["Apps","Aplicaciones","Apps"]],
  ["IP-adressen",["IP addresses","Direcciones IP","IP-Adressen"]],
  ["Apparaten",["Devices","Dispositivos","Geräte"]],
  ["OpenWrt vergelijken",["Compare OpenWrt","Comparar OpenWrt","OpenWrt vergleichen"]],
  ["Back-up",["Backup","Copia de seguridad","Sicherung"]],
  ["Back-up van meetgegevens",["Measurement backup","Copia de seguridad de mediciones","Sicherung der Messdaten"]],
  ["Download een kopie van alle metingen. Terugzetten vervangt de huidige meetgegevens. De app bewaart vóór het terugzetten automatisch een herstelkopie.",["Download a copy of all measurements. Restoring replaces the current measurements. The app automatically saves a recovery copy before restoring.","Descarga una copia de todas las mediciones. Al restaurar se sustituyen las mediciones actuales. La aplicación guarda automáticamente una copia de recuperación antes de restaurar.","Lade eine Kopie aller Messwerte herunter. Beim Wiederherstellen werden die aktuellen Messdaten ersetzt. Die App speichert vorher automatisch eine Wiederherstellungskopie."]],
  ["Back-up downloaden",["Download backup","Descargar copia de seguridad","Sicherung herunterladen"]],
  ["Kopie van vóór het terugzetten downloaden",["Download pre-restore copy","Descargar copia previa a la restauración","Kopie vor der Wiederherstellung herunterladen"]],
  ["SQLite-back-up (max. 256 MiB)",["SQLite backup (max. 256 MiB)","Copia SQLite (máx. 256 MiB)","SQLite-Sicherung (max. 256 MiB)"]],
  ["Ik wil de huidige meetgegevens vervangen.",["I want to replace the current measurements.","Quiero sustituir las mediciones actuales.","Ich möchte die aktuellen Messdaten ersetzen."]],
  ["Back-up terugzetten",["Restore backup","Restaurar copia de seguridad","Sicherung wiederherstellen"]],
  ["Periode kiezen",["Choose a period","Elegir período","Zeitraum wählen"]],
  ["Periode",["Period","Período","Zeitraum"]],
  ["Dag",["Day","Día","Tag"]],
  ["Week",["Week","Semana","Woche"]],
  ["Maand",["Month","Mes","Monat"]],
  ["Jaar",["Year","Año","Jahr"]],
  ["Datum",["Date","Fecha","Datum"]],
  ["Vandaag",["Today","Hoy","Heute"]],
  ["Verkeer per bron",["Traffic by source","Tráfico por fuente","Datenverkehr nach Quelle"]],
  ["Bron",["Source","Fuente","Quelle"]],
  ["Download",["Download","Descarga","Download"]],
  ["Upload",["Upload","Subida","Upload"]],
  ["Totaal",["Total","Total","Gesamt"]],
  ["Bestemmingen",["Destinations","Destinos","Ziele"]],
  ["Domein / apparaat",["Domain / device","Dominio / dispositivo","Domain / Gerät"]],
  ["IP-adres",["IP address","Dirección IP","IP-Adresse"]],
  ["Type adres",["Address type","Tipo de dirección","Adresstyp"]],
  ["Protocol",["Protocol","Protocolo","Protokoll"]],
  ["Poort wederpartij",["Remote port","Puerto remoto","Gegenstellenport"]],
  ["Netwerkdiagram",["Network diagram","Diagrama de red","Netzwerkdiagramm"]],
  ["Zoek op naam, IP of MAC…",["Search by name, IP or MAC…","Buscar por nombre, IP o MAC…","Nach Name, IP oder MAC suchen…"]],
  ["Zoek in de apparatenwolk",["Search network devices","Buscar dispositivos de red","Netzwerkgeräte suchen"]],
  ["Zoomen op de netwerkkaart",["Zoom the network map","Ampliar o reducir el mapa de red","Netzwerkkarte zoomen"]],
  ["Uitzoomen",["Zoom out","Alejar","Verkleinern"]],
  ["Inzoomen",["Zoom in","Acercar","Vergrößern"]],
  ["Alles in beeld",["Fit all","Mostrar todo","Alles anzeigen"]],
  ["Interactieve netwerkkaart",["Interactive network map","Mapa de red interactivo","Interaktive Netzwerkkarte"]],
  ["Geen apparaten gevonden.",["No devices found.","No se encontraron dispositivos.","Keine Geräte gefunden."]],
  ["Toon verkeersgrafiek",["Show traffic chart","Mostrar gráfico de tráfico","Datenverkehrsdiagramm anzeigen"]],
  ["Verkeer over tijd",["Traffic over time","Tráfico a lo largo del tiempo","Datenverkehr im Zeitverlauf"]],
  ["Alle bronnen",["All sources","Todas las fuentes","Alle Quellen"]],
  ["● Download",["● Download","● Descarga","● Download"]],
  ["● Upload",["● Upload","● Subida","● Upload"]],
  ["HA-download",["HA download","Descarga de HA","HA-Download"]],
  ["HA-upload",["HA upload","Subida de HA","HA-Upload"]],
  ["Voor deze periode zijn nog geen metingen opgeslagen.",["No measurements have been saved for this period.","No hay mediciones guardadas para este período.","Für diesen Zeitraum wurden keine Messwerte gespeichert."]],
  ["Download boven de nullijn en upload eronder",["Download above zero and upload below","Descargas por encima de cero y subidas por debajo","Download oberhalb der Nulllinie, Upload darunter"]],
  ["Verkeer per netwerkinterface",["Traffic by network interface","Tráfico por interfaz de red","Datenverkehr nach Netzwerkschnittstelle"]],
  ["Klik op een regel om de grafiek en totalen op die bron te filteren.",["Select a row to filter the chart and totals by source.","Selecciona una fila para filtrar el gráfico y los totales por fuente.","Wähle eine Zeile aus, um Diagramm und Summen nach Quelle zu filtern."]],
  ["Containers met een gedeeld netwerk",["Containers sharing a network","Contenedores con red compartida","Container mit gemeinsamem Netzwerk"]],
  ["Internetverkeer per wifi- of bekabeld apparaat via OpenWrt Bandwidth Monitor. Klik op een apparaat om alleen het verkeer daarvan te bekijken.",["Internet traffic per wireless or wired device via OpenWrt Bandwidth Monitor. Select a device to see its traffic.","Tráfico de Internet por dispositivo Wi-Fi o cableado mediante OpenWrt Bandwidth Monitor. Selecciona un dispositivo para ver su tráfico.","Internetverkehr pro WLAN- oder kabelgebundenem Gerät über OpenWrt Bandwidth Monitor. Wähle ein Gerät aus, um dessen Datenverkehr zu sehen."]],
  ["Verkeer per apparaat",["Traffic by device","Tráfico por dispositivo","Datenverkehr nach Gerät"]],
  ["OpenWrt WAN telt het internetverkeer van alle apparaten die via de router online gaan. De HA-server telt op zijn eigen netwerkinterface ook lokaal verkeer mee.",["OpenWrt WAN counts internet traffic for devices that connect through the router. The HA server also counts local traffic on its own network interface.","La WAN de OpenWrt cuenta el tráfico de Internet de los dispositivos conectados a través del router. El servidor HA también cuenta el tráfico local de su propia interfaz de red.","OpenWrt WAN zählt den Internetverkehr der Geräte, die über den Router online sind. Der HA-Server zählt auf seiner eigenen Netzwerkschnittstelle auch lokalen Datenverkehr."]],
  ["Netwerkinterface van de server. Lokaal verkeer en internetverkeer zitten in dit totaal.",["Server network interface. The total includes local and internet traffic.","Interfaz de red del servidor. El total incluye tráfico local y de Internet.","Netzwerkschnittstelle des Servers. Die Summe umfasst lokalen Datenverkehr und Internetverkehr."]],
  ["Verkeer van containers met eigen tellers. Dit kan intern Docker-verkeer bevatten en overlapt deels met het servertotaal.",["Traffic from containers with their own counters. This can include internal Docker traffic and partially overlaps with the server total.","Tráfico de contenedores con contadores propios. Puede incluir tráfico interno de Docker y coincidir en parte con el total del servidor.","Datenverkehr von Containern mit eigenen Zählern. Dieser kann internen Docker-Verkehr enthalten und sich teilweise mit der Serversumme überschneiden."]],
  ["Top 30 apps en containers",["Top 30 apps and containers","30 aplicaciones y contenedores principales","Top 30 Apps und Container"]],
  ["Bron-IP voor downloads en doel-IP voor uploads op de serverinterface. Dit zijn waargenomen IP-bytes.",["Source IP for downloads and destination IP for uploads on the server interface. These are observed IP bytes.","IP de origen para descargas e IP de destino para subidas en la interfaz del servidor. Son bytes IP observados.","Quell-IP für Downloads und Ziel-IP für Uploads an der Serverschnittstelle. Angezeigt werden beobachtete IP-Bytes."]],
  ["Top 30 IP-adressen",["Top 30 IP addresses","30 direcciones IP principales","Top 30 IP-Adressen"]],
  ["Filter deze tabel…",["Filter this table…","Filtrar esta tabla…","Diese Tabelle filtern…"]],
  ["Filter ",["Filter ","Filtrar ","Filtern: "]],
  ["verkeer",["traffic","tráfico","Datenverkehr"]],
  ["bestemmingen",["destinations","destinos","Ziele"]],
  ["vergelijking",["comparison","comparación","Vergleich"]],
  ["Apparaat zonder naam",["Unnamed device","Dispositivo sin nombre","Unbenanntes Gerät"]],
  ["Huidige apparaatkoppeling uit OpenWrt",["Current device association from OpenWrt","Asociación actual del dispositivo en OpenWrt","Aktuelle Gerätezuordnung aus OpenWrt"]],
  ["Zoek netwerk en domein op voor ",["Look up network and domain for ","Consultar red y dominio de ","Netzwerk und Domain nachschlagen für "]],
  ["Netwerk opzoeken…",["Looking up network…","Buscando red…","Netzwerk wird gesucht…"]],
  ["Geen netwerkgegevens gevonden.",["No network information found.","No se encontraron datos de red.","Keine Netzwerkdaten gefunden."]],
  ["Bekijk op IPinfo",["View on IPinfo","Ver en IPinfo","Auf IPinfo anzeigen"]],
  ["IPinfo ophalen mislukt.",["Could not load IPinfo.","No se pudo consultar IPinfo.","IPinfo konnte nicht geladen werden."]],
  ["Wijs een tijdvak aan voor de waarden.",["Point to a time slot to see its values.","Señala un intervalo para ver sus valores.","Zeige auf einen Zeitabschnitt, um die Werte zu sehen."]],
  ["Geen meting",["No measurement","Sin medición","Kein Messwert"]],
  ["Grootste bronnen en bestemmingen van de server",["Top server sources and destinations","Principales fuentes y destinos del servidor","Größte Quellen und Ziele des Servers"]],
  ["Bestemmingen · ",["Destinations · ","Destinos · ","Ziele · "]],
  ["Waargenomen IP-verkeer. TLS geeft een zichtbare domeinnaam aan. DNS is een aanwijzing.",["Observed IP traffic. TLS identifies a visible domain name. DNS indicates a possible match.","Tráfico IP observado. TLS identifica un dominio visible. DNS indica una posible coincidencia.","Beobachteter IP-Verkehr. TLS identifiziert einen sichtbaren Domainnamen. DNS weist auf eine mögliche Zuordnung hin."]],
  ["De bestemmingsmeting staat uit.",["Destination monitoring is disabled.","La medición de destinos está desactivada.","Die Zielmessung ist deaktiviert."]],
  ["Nog geen bronnen of bestemmingen gemeten voor deze periode. De serverdetails beginnen bij versie 0.5.0.",["No sources or destinations measured for this period. Server details are available starting with version 0.5.0.","No se han medido fuentes ni destinos para este período. Los detalles del servidor están disponibles desde la versión 0.5.0.","Für diesen Zeitraum wurden keine Quellen oder Ziele gemessen. Serverdetails sind ab Version 0.5.0 verfügbar."]],
  ["Geen bestemmingen gemeten voor deze app en periode.",["No destinations measured for this app and period.","No se han medido destinos para esta aplicación y este período.","Für diese App und diesen Zeitraum wurden keine Ziele gemessen."]],
  [" Bij download zie je het bron-IP. Bij upload zie je het doel-IP.",[" Downloads show the source IP. Uploads show the destination IP."," Las descargas muestran la IP de origen. Las subidas muestran la IP de destino."," Downloads zeigen die Quell-IP. Uploads zeigen die Ziel-IP."]],
  [" Apparaatnamen en MAC-adressen komen uit de huidige OpenWrt-lijst.",[" Device names and MAC addresses come from the current OpenWrt list."," Los nombres y las direcciones MAC provienen de la lista actual de OpenWrt."," Gerätenamen und MAC-Adressen stammen aus der aktuellen OpenWrt-Liste."]],
  [" De tabel toont de 100 grootste regels.",[" The table shows the 100 largest entries."," La tabla muestra las 100 entradas con más tráfico."," Die Tabelle zeigt die 100 größten Einträge."]],
  ["Overige verbindingen",["Other connections","Otras conexiones","Weitere Verbindungen"]],
  ["OpenWrt-interface actief: ",["OpenWrt interface active: ","Interfaz OpenWrt activa: ","OpenWrt-Schnittstelle aktiv: "]],
  ["OpenWrt is niet ingesteld.",["OpenWrt is not configured.","OpenWrt no está configurado.","OpenWrt ist nicht eingerichtet."]],
  ["Vul modem_download_entity en modem_upload_entity in bij Configuratie.",["Enter modem_download_entity and modem_upload_entity under Configuration.","Introduce modem_download_entity y modem_upload_entity en Configuración.","Trage modem_download_entity und modem_upload_entity unter Konfiguration ein."]],
  ["Nog geen modemmetingen voor deze periode.",["No modem measurements for this period yet.","Todavía no hay mediciones del módem para este período.","Für diesen Zeitraum liegen noch keine Modem-Messwerte vor."]],
  ["Aansluiting niet gemeten",["Connection not measured","Conexión sin medir","Verbindung nicht gemessen"]],
  [" apparaten · Sleep een knooppunt of de achtergrond. Zoom met het muiswiel of twee vingers.",[" devices · Drag a node or the background. Zoom with the mouse wheel or two fingers."," dispositivos · Arrastra un nodo o el fondo. Usa la rueda del ratón o dos dedos para cambiar el zoom."," Geräte · Ziehe einen Knoten oder den Hintergrund. Zoome mit dem Mausrad oder zwei Fingern."]],
  ["Nog geen apparaten beschikbaar.",["No devices available yet.","Todavía no hay dispositivos disponibles.","Noch keine Geräte verfügbar."]],
  ["Geen meting in deze periode.",["No measurement in this period.","No hay mediciones en este período.","Keine Messung in diesem Zeitraum."]],
  ["Interface onbekend",["Unknown interface","Interfaz desconocida","Unbekannte Schnittstelle"]],
  [" · laatste meetronde ",[" · last measurement at "," · última medición a las "," · letzte Messung um "]],
  [" · historie vanaf ",[" · history since "," · historial desde "," · Verlauf ab "]],
  ["Wachten op de eerste meetronde",["Waiting for the first measurement","Esperando la primera medición","Warte auf die erste Messung"]],
  ["OpenWrt-apparaatnamen niet beschikbaar. ",["OpenWrt device names are unavailable. ","Los nombres de dispositivos OpenWrt no están disponibles. ","OpenWrt-Gerätenamen sind nicht verfügbar. "]],
  ["Stel OpenWrt in onder HA-Bandwidth → Configuratie.",["Set up OpenWrt under HA-Bandwidth → Configuration.","Configura OpenWrt en HA-Bandwidth → Configuración.","Richte OpenWrt unter HA-Bandwidth → Konfiguration ein."]],
  ["IP-meting staat uit.",["IP monitoring is disabled.","La medición IP está desactivada.","Die IP-Messung ist deaktiviert."]],
  ["Actief zonder bruikbare tellers: ",["Active without usable counters: ","Activos sin contadores utilizables: ","Aktiv ohne nutzbare Zähler: "]],
  ["Automatische back-ups",["Automatic backups","Copias de seguridad automáticas","Automatische Sicherungen"]],
  ["Dinsdag t/m zondag een dagback-up, maandag een weekback-up. {count} van {limit} opgeslagen.",["Daily backup Tuesday through Sunday, weekly backup on Monday. {count} of {limit} saved.","Copia diaria de martes a domingo y semanal el lunes. {count} de {limit} guardadas.","Tägliche Sicherung von Dienstag bis Sonntag, wöchentliche Sicherung am Montag. {count} von {limit} gespeichert."]],
  ["Weekback-up",["Weekly backup","Copia semanal","Wöchentliche Sicherung"]],
  ["Dagback-up",["Daily backup","Copia diaria","Tägliche Sicherung"]],
  ["Terugzetten",["Restore","Restaurar","Wiederherstellen"]],
  ["Verwijderen",["Delete","Eliminar","Löschen"]],
  ["Deze back-up terugzetten? De huidige meetgegevens worden vervangen.",["Restore this backup? The current measurements will be replaced.","¿Restaurar esta copia? Se sustituirán las mediciones actuales.","Diese Sicherung wiederherstellen? Die aktuellen Messdaten werden ersetzt."]],
  ["Deze back-up definitief verwijderen?",["Permanently delete this backup?","¿Eliminar esta copia de forma permanente?","Diese Sicherung endgültig löschen?"]],
  ["De meetgegevens zijn teruggezet.",["Measurements restored.","Se han restaurado las mediciones.","Die Messdaten wurden wiederhergestellt."]],
  ["Back-up verwijderd.",["Backup deleted.","Copia eliminada.","Sicherung gelöscht."]],
  ["Het bestand is groter dan 256 MiB.",["The file exceeds 256 MiB.","El archivo supera los 256 MiB.","Die Datei ist größer als 256 MiB."]],
  ["Back-up terugzetten…",["Restoring backup…","Restaurando copia…","Sicherung wird wiederhergestellt…"]],
  ["Terugzetten mislukt. ",["Restore failed. ","No se pudo restaurar la copia. ","Wiederherstellung fehlgeschlagen. "]],
  ["Dashboard kon de metingen niet ophalen (",["Could not load measurements (","No se pudieron cargar las mediciones (","Messwerte konnten nicht geladen werden ("]],
  ["Deze back-up is niet meer beschikbaar.",["This backup is no longer available.","Esta copia ya no está disponible.","Diese Sicherung ist nicht mehr verfügbar."]],
  ["De bewerking is mislukt. Bekijk het app-logboek.",["The operation failed. Check the app log.","La operación falló. Consulta el registro de la aplicación.","Der Vorgang ist fehlgeschlagen. Prüfe das App-Protokoll."]],
  ["Dit bestand kon niet worden teruggezet als SQLite-back-up.",["This file could not be restored as a SQLite backup.","No se pudo restaurar este archivo como copia SQLite.","Diese Datei konnte nicht als SQLite-Sicherung wiederhergestellt werden."]],
  ["Het terugzetten of opslaan van de herstelkopie is mislukt.",["Could not restore the backup or save the recovery copy.","No se pudo restaurar la copia o guardar la copia de recuperación.","Die Sicherung konnte nicht wiederhergestellt oder die Wiederherstellungskopie nicht gespeichert werden."]],
  ["Het SQLite-bestand is beschadigd.",["The SQLite file is corrupt.","El archivo SQLite está dañado.","Die SQLite-Datei ist beschädigt."]],
  ["Dit bestand bevat geen ondersteunde HA-Bandwidth-database.",["This file does not contain a supported HA-Bandwidth database.","Este archivo no contiene una base de datos compatible de HA-Bandwidth.","Diese Datei enthält keine unterstützte HA-Bandwidth-Datenbank."]],
  ["De back-up bevat ongeldige meetgegevens.",["The backup contains invalid measurements.","La copia contiene mediciones no válidas.","Die Sicherung enthält ungültige Messdaten."]],
  ["Lokaal",["Local","Local","Lokal"]],
  ["Publiek",["Public","Pública","Öffentlich"]],
  ["Onbekend",["Unknown","Desconocido","Unbekannt"]],
  ["Bekabeld",["Wired","Cableado","Kabelgebunden"]],
]);

const languageSelect = document.getElementById("dashboard-language");
const languageKey = "ha-bandwidth.language";
const requestedLanguage = pageUrl.searchParams.get("lang");
let savedLanguage;
try {
  savedLanguage = window.localStorage.getItem(languageKey);
} catch {
  // The URL keeps the selection when browser storage is blocked.
}
const language = Object.hasOwn(locales, requestedLanguage) ? requestedLanguage
  : Object.hasOwn(locales, savedLanguage) ? savedLanguage : "nl";
const locale = locales[language];

function t(message, values = {}) {
  const translated = translations.get(message)?.[translationColumn[language]] ?? message;
  return translated.replace(/\{(\w+)\}/g, (placeholder, key) => values[key] ?? placeholder);
}

document.documentElement.lang = language;
languageSelect.value = language;
const textNodes = document.createTreeWalker(document.querySelector("main"), NodeFilter.SHOW_TEXT);
for (let node = textNodes.nextNode(); node; node = textNodes.nextNode()) {
  const label = node.data.trim();
  if (translations.has(label)) node.data = node.data.replace(label, () => t(label));
}
for (const element of document.querySelectorAll("main [aria-label], main [placeholder]")) {
  for (const attribute of ["aria-label", "placeholder"]) {
    if (element.hasAttribute(attribute)) element.setAttribute(attribute, t(element.getAttribute(attribute)));
  }
}
languageSelect.addEventListener("change", () => {
  try {
    window.localStorage.setItem(languageKey, languageSelect.value);
    if (shared || !pageUrl.searchParams.has("lang")) {
      window.location.reload();
      return;
    }
    pageUrl.searchParams.delete("lang");
  } catch {
    pageUrl.searchParams.set("lang", languageSelect.value);
  }
  window.location.assign(pageUrl);
});

const el = id => document.getElementById(id);
const format = new Intl.NumberFormat(locale, {maximumFractionDigits: 2});
const views = {
  device: [t("Internetverkeer per wifi- of bekabeld apparaat via OpenWrt Bandwidth Monitor. Klik op een apparaat om alleen het verkeer daarvan te bekijken."), t("Verkeer per apparaat")],
  compare: [t("OpenWrt WAN telt het internetverkeer van alle apparaten die via de router online gaan. De HA-server telt op zijn eigen netwerkinterface ook lokaal verkeer mee."), ""],
  host: [t("Netwerkinterface van de server. Lokaal verkeer en internetverkeer zitten in dit totaal."), t("Verkeer per netwerkinterface")],
  app: [t("Verkeer van containers met eigen tellers. Dit kan intern Docker-verkeer bevatten en overlapt deels met het servertotaal."), t("Top 30 apps en containers")],
  peer: [t("Bron-IP voor downloads en doel-IP voor uploads op de serverinterface. Dit zijn waargenomen IP-bytes."), t("Top 30 IP-adressen")],
};
const monthFormat = new Intl.DateTimeFormat(locale, {month: "short", timeZone: "UTC"});
const dateFormat = new Intl.DateTimeFormat(locale, {dateStyle: "medium", timeZone: "UTC"});
const months = Array.from({length: 12}, (_, index) => monthFormat.format(Date.UTC(2020, index, 1)));
const embeddedCards = new Set(["history", "ranking", "destinations", "app-details", "shared", "topology", "comparison", "backup"]);
const embeddedCard = pageUrl.searchParams.get("card");
const embeddedKind = pageUrl.searchParams.get("kind");
if (embeddedCards.has(embeddedCard)) document.body.dataset.dashboardCard = embeddedCard;
let kind = Object.hasOwn(views, embeddedKind) || embeddedKind === "backup" ? embeddedKind : "host";
let period = "day";
let source = "";
let sourceLabel = "";
let request = 0;
let focusDestinations = false;
const tableControls = new Map();
const ipDetails = new Map();
const tableCollator = new Intl.Collator(locale, {numeric: true, sensitivity: "base"});

function updateTable(id) {
  const body = el(id);
  const table = body.closest("table");
  let control = tableControls.get(id);
  if (!control) {
    const input = document.createElement("input");
    input.type = "search";
    input.className = "table-filter";
    input.placeholder = t("Filter deze tabel…");
    input.setAttribute("aria-label", t("Filter ") + ({
      rows: t("verkeer"), "destination-rows": t("bestemmingen"), "comparison-rows": t("vergelijking"),
    })[id]);
    table.parentElement.before(input);
    control = {input, views: new Map(), headings: [...table.querySelectorAll("th")]};
    tableControls.set(id, control);
    input.addEventListener("input", () => {
      control.state.query = input.value;
      updateTable(id);
    });
    control.headings.forEach((heading, column) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "sort-header";
      button.textContent = heading.textContent;
      heading.replaceChildren(button);
      button.addEventListener("click", () => {
        const state = control.state;
        state.direction = state.column === column ? -state.direction
          : column >= control.headings.length - 3 ? -1 : 1;
        state.column = column;
        updateTable(id);
      });
    });
  }
  if (!control.views.has(kind)) {
    control.views.set(kind, {query: "", column: control.headings.length - 1, direction: -1});
  }
  const state = control.views.get(kind);
  control.state = state;
  if (control.input.value !== state.query) control.input.value = state.query;
  control.input.hidden = body.rows.length === 0;
  const tokens = state.query.toLocaleLowerCase(locale).trim().split(/\s+/).filter(Boolean);
  const rows = [...body.rows];
  rows.sort((left, right) => {
    const a = left.cells[state.column];
    const b = right.cells[state.column];
    const an = a.dataset.sortNumber;
    const bn = b.dataset.sortNumber;
    if (an === undefined && bn !== undefined) return 1;
    if (an !== undefined && bn === undefined) return -1;
    const order = an !== undefined ? Number(an) - Number(bn) : tableCollator.compare(a.textContent, b.textContent);
    return state.direction * order;
  });
  for (const row of rows) {
    const searchable = (row.textContent + " " + (row.dataset.search || "")).toLocaleLowerCase(locale);
    row.hidden = !tokens.every(token => searchable.includes(token));
    body.append(row);
  }
  control.headings.forEach((heading, column) => {
    if (column === state.column) heading.setAttribute("aria-sort", state.direction === 1 ? "ascending" : "descending");
    else heading.removeAttribute("aria-sort");
  });
}

function countCells(row, rx, tx, available = true) {
  for (const value of [rx, tx, rx + tx]) {
    const cell = row.insertCell();
    cell.textContent = available ? bytes(value) : "—";
    if (available) cell.dataset.sortNumber = value;
  }
}

function addRouterHost(cell, host) {
  if (!host) return;
  const label = document.createElement("span");
  label.className = "ip-result";
  label.textContent = [host.name || t("Apparaat zonder naam"), host.mac].filter(Boolean).join(" · ");
  label.title = t("Huidige apparaatkoppeling uit OpenWrt");
  cell.append(label);
}

function addIpLookup(cell, ip, stored) {
  if (!ip) return;
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "IPinfo";
  button.className = "ip-lookup";
  button.setAttribute("aria-label", t("Zoek netwerk en domein op voor ") + ip);
  const result = document.createElement("span");
  result.className = "ip-result";
  result.setAttribute("role", "status");
  const render = () => {
    const details = stored || ipDetails.get(ip);
    button.hidden = Boolean(details && !details.pending && !details.error &&
      (details.asn || details.as_name || details.as_domain));
    button.disabled = details?.pending === true;
    result.textContent = details?.pending ? t("Netwerk opzoeken…")
      : details?.error || (details && [details.asn, details.as_name, details.as_domain].filter(Boolean).join(" · "))
        || (details ? t("Geen netwerkgegevens gevonden.") : "");
    if (details && !details.pending) {
      const link = document.createElement("a");
      link.href = "https://ipinfo.io/" + encodeURIComponent(ip);
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = t("Bekijk op IPinfo");
      result.append(" ", link);
    }
    cell.parentElement.dataset.search = ip + " " + result.textContent;
  };
  button.addEventListener("click", async () => {
    if (!stored && (!ipDetails.has(ip) || ipDetails.get(ip).error)) {
      ipDetails.set(ip, {pending: true});
      render();
      try {
        const response = await fetch("./api/ipinfo?" + new URLSearchParams({ip}));
        const data = await response.json();
        if (!response.ok) throw new Error(data.error ? t(data.error) : t("IPinfo ophalen mislukt."));
        if (data.asn || data.as_name || data.as_domain) ipDetails.set(ip, data);
        else ipDetails.set(ip, {error: t("Geen netwerkgegevens gevonden.")});
      } catch (error) {
        ipDetails.set(ip, {error: error.message});
      }
    }
    for (const id of ["rows", "destination-rows"]) {
      for (const refresh of el(id).querySelectorAll(".ip-lookup")) {
        if (refresh.dataset.ip === ip) refresh.refreshIpDetails();
      }
      if (tableControls.has(id)) updateTable(id);
    }
  });
  button.dataset.ip = ip;
  button.refreshIpDetails = render;
  cell.append(button, result);
  render();
}

function bytes(value) {
  let index = 0;
  const units = ["B", "kB", "MB", "GB", "TB", "PB"];
  while (value >= 1000 && index < units.length - 1) {
    value /= 1000;
    index += 1;
  }
  return format.format(value) + " " + units[index];
}

function timeline(data) {
  const values = new Map(data.buckets.map(row => [row.bucket, row]));
  const router = new Map((data.router_buckets || []).map(row => [row.bucket, row]));
  const modem = new Map((data.modem_buckets || []).map(row => [row.bucket, row]));
  const slots = [];
  if (period === "day") {
    for (let hour = 0; hour < 24; hour++) {
      const label = String(hour).padStart(2, "0");
      slots.push([data.start + "T" + label, hour % 3 === 0 ? label + ":00" : ""]);
    }
  } else if (period === "year") {
    months.forEach((month, index) => {
      slots.push([data.start.slice(0, 4) + "-" + String(index + 1).padStart(2, "0"), month]);
    });
  } else {
    const cursor = new Date(data.start + "T00:00:00Z");
    for (let index = 0; cursor.toISOString().slice(0, 10) <= data.end; index++) {
      const key = cursor.toISOString().slice(0, 10);
      slots.push([key, period === "week" || index % 3 === 0 ? key.slice(8) : ""]);
      cursor.setUTCDate(cursor.getUTCDate() + 1);
    }
  }
  const sources = [["", values, kind === "compare" ? t("HA-server") : ""]];
  if (kind === "compare") sources.push(["modem-", router, data.router_label], ["cellular-", modem, t(data.modem_label)]);
  const readings = sources.flatMap(([, series]) => [...series.values()]);
  const step = Math.max(1, ...readings.flatMap(row => [row.rx, row.tx])) / 5;
  const above = Math.max(1, Math.ceil(Math.max(...readings.map(row => row.rx)) / step));
  const below = Math.max(1, Math.ceil(Math.max(...readings.map(row => row.tx)) / step));
  const width = slots.length * 10;
  const y = value => 240 * (above - value / step) / (above + below);
  const graph = svg("svg", {viewBox: "0 0 " + width + " 240", preserveAspectRatio: "none", "aria-hidden": "true"});
  const axis = [];
  for (let tick = above; tick >= -below; tick--) {
    const value = tick * step;
    const label = document.createElement("span");
    label.textContent = (tick < 0 ? "−" : "") + bytes(Math.abs(value));
    label.style.top = (100 * y(value) / 240) + "%";
    axis.push(label);
    if (tick) graph.append(svg("line", {x1: 0, x2: width, y1: y(value), y2: y(value), class: "plot-grid"}));
  }
  el("axis").replaceChildren(...axis);
  const zero = y(0);
  const seriesOutlines = [];
  for (const [prefix, series] of sources) {
    for (const [direction, sign] of [["rx", 1], ["tx", -1]]) {
      const areas = [];
      const outlines = [];
      let run = [];
      // Close each uninterrupted run at zero so missing measurements stay open.
      const finish = () => {
        if (!run.length) return;
        const [firstX, firstY] = run[0];
        const [lastX, lastY] = run[run.length - 1];
        const profile = "M" + (firstX - 5) + "," + firstY + " L" + run.join(" ") + " " + (lastX + 5) + "," + lastY;
        outlines.push(profile);
        areas.push(profile + " V" + zero + " H" + (firstX - 5) + " Z");
        run = [];
      };
      slots.forEach(([key], index) => {
        const row = series.get(key);
        if (row) run.push([index * 10 + 5, y(sign * row[direction])]);
        else finish();
      });
      finish();
      const color = prefix + direction;
      graph.append(svg("path", {d: areas.join(" "), class: "plot-area " + color}));
      seriesOutlines.push(svg("path", {d: outlines.join(" "), class: "plot-outline " + color}));
    }
  }
  graph.append(...seriesOutlines);
  graph.append(svg("line", {x1: 0, x2: width, y1: zero, y2: zero, class: "plot-zero"}));
  const cursor = svg("line", {y1: 0, y2: 240, class: "plot-cursor", visibility: "hidden"});
  graph.append(cursor);
  const details = el("chart-details");
  const clear = () => {
    details.textContent = t("Wijs een tijdvak aan voor de waarden.");
    cursor.setAttribute("visibility", "hidden");
  };
  clear();
  const ticks = document.createElement("div");
  ticks.className = "plot-ticks";
  const targets = document.createElement("div");
  targets.className = "plot-targets";
  slots.forEach(([key, tick], index) => {
    const summary = sources.flatMap(([, series, label]) => {
      const row = series.get(key);
      return row ? [(label ? label + " " : "") + t("Download") + " " + bytes(row.rx) + " / " + t("Upload") + " " + bytes(row.tx)] : [];
    });
    const caption = key.replace("T", " ") + (period === "day" ? ":00" : "") + " · " +
      (summary.join(" · ") || t("Geen meting"));
    const target = document.createElement("button");
    target.type = "button";
    target.setAttribute("aria-label", caption);
    if (!summary.length) target.tabIndex = -1;
    const show = () => {
      const x = index * 10 + 5;
      cursor.setAttribute("x1", x);
      cursor.setAttribute("x2", x);
      cursor.setAttribute("visibility", "visible");
      details.textContent = caption;
    };
    for (const event of ["focus", "pointerenter", "click"]) target.addEventListener(event, show);
    target.addEventListener("blur", clear);
    target.addEventListener("pointerleave", () => { if (document.activeElement !== target) clear(); });
    targets.append(target);
    const label = document.createElement("span");
    label.textContent = tick;
    ticks.append(label);
  });
  el("chart").replaceChildren(graph, targets, ticks);
}

function table(rows) {
  const body = el("rows");
  body.replaceChildren();
  for (const row of rows) {
    const tr = body.insertRow();
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = row.label;
    button.title = row.source;
    button.setAttribute("aria-pressed", String(row.source === source));
    button.addEventListener("click", () => {
      source = row.source;
      sourceLabel = row.label;
      focusDestinations = kind === "app";
      refresh();
    });
    tr.dataset.search = row.source;
    const cell = tr.insertCell();
    cell.append(button);
    addRouterHost(cell, row.router_host);
    addIpLookup(cell, row.lookup_ip, row.ipinfo);
    countCells(tr, row.rx, row.tx);
  }
  updateTable("rows");
}

function showDestinations(data) {
  const section = el("destinations");
  section.hidden = kind !== "host" && (kind !== "app" || !source);
  if (section.hidden) {
    focusDestinations = false;
    return;
  }
  const title = el("destinations-title");
  title.textContent = kind === "host" ? t("Grootste bronnen en bestemmingen van de server") : t("Bestemmingen · ") + sourceLabel;
  const rows = data.destinations;
  const body = el("destination-rows");
  body.replaceChildren();
  el("destinations-table").hidden = rows.length === 0;
  let note = t("Waargenomen IP-verkeer. TLS geeft een zichtbare domeinnaam aan. DNS is een aanwijzing.");
  if (rows.length === 0) {
    const enabled = kind === "host" ? data.status.peers_enabled : data.status.app_destinations_enabled;
    note = enabled === false
      ? t("De bestemmingsmeting staat uit.")
      : kind === "host"
        ? t("Nog geen bronnen of bestemmingen gemeten voor deze periode. De serverdetails beginnen bij versie 0.5.0.")
        : t("Geen bestemmingen gemeten voor deze app en periode.");
  } else {
    if (kind === "host") note += t(" Bij download zie je het bron-IP. Bij upload zie je het doel-IP.");
    if (rows.some(row => row.router_host)) note += t(" Apparaatnamen en MAC-adressen komen uit de huidige OpenWrt-lijst.");
    if (data.destinations_truncated) note += t(" De tabel toont de 100 grootste regels.");
  }
  el("destinations-note").textContent = note;
  for (const row of rows) {
    const tr = body.insertRow();
    const domain = row.domain ? row.domain + " (" + row.evidence + ")" : "";
    const name = row.router_host?.name || "";
    tr.insertCell().textContent = [domain, name].filter(Boolean).join(" · ") || "—";
    const ipCell = tr.insertCell();
    ipCell.textContent = row.ip || t("Overige verbindingen");
    if (row.router_host?.mac) {
      const mac = document.createElement("span");
      mac.className = "ip-result";
      mac.textContent = row.router_host.mac;
      ipCell.append(mac);
    }
    addIpLookup(ipCell, row.lookup_ip, row.ipinfo);
    tr.insertCell().textContent = t(row.scope);
    tr.insertCell().textContent = row.protocol || "—";
    const port = tr.insertCell();
    port.textContent = row.port >= 0 ? row.port : "—";
    if (row.port >= 0) port.dataset.sortNumber = row.port;
    countCells(tr, row.rx, row.tx);
  }
  updateTable("destination-rows");
  if (focusDestinations) {
    focusDestinations = false;
    title.focus();
  }
}

function showComparison(data) {
  const body = el("comparison-rows");
  body.replaceChildren();
  el("router-download-legend").textContent = data.router_label + " " + t("Download");
  el("router-upload-legend").textContent = data.router_label + " " + t("Upload");
  el("cellular-download-legend").textContent = t(data.modem_label) + " " + t("Download");
  el("cellular-upload-legend").textContent = t(data.modem_label) + " " + t("Upload");
  for (const [label, values] of [["HA-server", data.buckets], [data.router_label, data.router_buckets], [t(data.modem_label), data.modem_buckets]]) {
    const row = body.insertRow();
    row.insertCell().textContent = label;
    const rx = values.reduce((total, item) => total + item.rx, 0);
    const tx = values.reduce((total, item) => total + item.tx, 0);
    countCells(row, rx, tx, values.length > 0);
  }
  updateTable("comparison-rows");
  const device = data.status.router_device ? t("OpenWrt-interface actief: ") + data.status.router_device + "." : "";
  const routerStatus = data.status.router_error || (data.status.router_configured
    ? device : t("OpenWrt is niet ingesteld."));
  const modemStatus = data.status.modem_error || (!data.status.modem_configured
    ? t("Vul modem_download_entity en modem_upload_entity in bij Configuratie.")
    : data.status.modem_phase ? t(data.modem_label) + ": " + t(data.status.modem_phase) + "."
      : data.modem_buckets.length ? "" : t("Nog geen modemmetingen voor deze periode."));
  el("modem-status").textContent = [routerStatus, modemStatus].filter(Boolean).join(" · ");
}

const map = el("topology-map");
const viewport = el("topology-viewport");
const positions = new Map();
const pointers = new Map();
const collapsedGroups = new Set();
let graphData, gesture, selectedDevice;
let nodes = [], edges = [];
let camera = {x: 480, y: 220, scale: 1};
let refit = true;

function svg(tag, attributes = {}) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, value);
  return element;
}

function paintMap() {
  viewport.setAttribute("transform", `translate(${camera.x} ${camera.y}) scale(${camera.scale})`);
  for (const {element, point} of nodes) element.setAttribute("transform", `translate(${point.x} ${point.y})`);
  for (const {line, from, to} of edges) {
    line.setAttribute("x1", from.x);
    line.setAttribute("y1", from.y);
    line.setAttribute("x2", to.x);
    line.setAttribute("y2", to.y);
  }
}

function zoomMap(factor, from, to = from) {
  const scale = Math.max(.12, Math.min(6, camera.scale * factor));
  const ratio = scale / camera.scale;
  camera = {x: to.x - (from.x - camera.x) * ratio, y: to.y - (from.y - camera.y) * ratio, scale};
  paintMap();
}

function fitMap() {
  if (!nodes.length) return;
  const xs = nodes.map(({point}) => point.x), ys = nodes.map(({point}) => point.y);
  const left = Math.min(...xs) - 35, right = Math.max(...xs) + 175;
  const top = Math.min(...ys) - 40, bottom = Math.max(...ys) + 45;
  const scale = Math.min(1.4, 900 / (right - left), 415 / (bottom - top));
  camera = {x: 480 - (left + right) * scale / 2, y: 240 - (top + bottom) * scale / 2, scale};
  paintMap();
}

function mapPoint(event) {
  return new DOMPoint(event.clientX, event.clientY).matrixTransform(map.getScreenCTM().inverse());
}

map.addEventListener("wheel", event => {
  event.preventDefault();
  zoomMap(Math.exp(-Math.max(-150, Math.min(150, event.deltaY)) * .003), mapPoint(event));
}, {passive: false});
map.addEventListener("pointerdown", event => {
  if (event.button !== 0) return;
  const point = mapPoint(event);
  if (!pointers.size) gesture = {id: event.target.closest("[data-node]")?.dataset.node, start: point, moved: false};
  else gesture.moved = true;
  pointers.set(event.pointerId, point);
  map.setPointerCapture(event.pointerId);
});
map.addEventListener("pointermove", event => {
  const last = pointers.get(event.pointerId);
  if (!last) return;
  const point = mapPoint(event);
  if (pointers.size === 2) {
    const other = [...pointers].find(([id]) => id !== event.pointerId)[1];
    const distance = Math.hypot(last.x - other.x, last.y - other.y);
    const middle = p => ({x: (p.x + other.x) / 2, y: (p.y + other.y) / 2});
    if (distance) zoomMap(Math.hypot(point.x - other.x, point.y - other.y) / distance, middle(last), middle(point));
  } else if (pointers.size === 1) {
    const {start} = gesture;
    if (gesture.moved || Math.hypot(point.x - start.x, point.y - start.y) > 4) {
      gesture.moved = true;
      const node = positions.get(gesture.id);
      if (node) {
        node.x += (point.x - last.x) / camera.scale;
        node.y += (point.y - last.y) / camera.scale;
      } else {
        camera.x += point.x - last.x;
        camera.y += point.y - last.y;
      }
      paintMap();
    }
  }
  pointers.set(event.pointerId, point);
});
function finishMapGesture(event) {
  if (!pointers.delete(event.pointerId)) return;
  if (pointers.size) {
    gesture.id = "";
    return;
  }
  const {id, moved} = gesture;
  gesture = null;
  if (!moved && event.type === "pointerup") nodes.find(node => node.id === id)?.action?.();
}
for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) map.addEventListener(type, finishMapGesture);
el("topology-zoom-in").onclick = () => zoomMap(1.25, {x: 480, y: 240});
el("topology-zoom-out").onclick = () => zoomMap(.8, {x: 480, y: 240});
el("topology-fit").onclick = fitMap;
el("topology-search").addEventListener("input", () => {
  refit = true;
  if (graphData) showTopology(graphData);
});

function showTopology(data) {
  el("topology-panel").hidden = kind !== "device";
  if (kind !== "device") return;
  graphData = data;
  if (pointers.size) return;

  const modem = data.upstream_modem;
  const modemIp = (modem?.ip || "").replace(/^https?:\/\//i, "").replace(/\/$/, "");
  const measured = new Map(data.rows.map(row => [row.source, row]));
  const devices = new Map(data.topology.map(device => [device.source, device]));
  for (const row of data.rows) {
    if (!devices.has(row.source)) devices.set(row.source, {source: row.source, name: row.label, ips: [], ssid: ""});
  }
  if (modem?.name && modemIp) {
    for (const [id, device] of devices) {
      if (id === modemIp || device.ips.includes(modemIp)) devices.delete(id);
    }
  }
  const search = el("topology-search").value.trim().toLocaleLowerCase(locale);
  const groups = new Map();
  for (const device of devices.values()) {
    if (search && ![device.name, device.source, device.ssid, device.connection, device.port, ...device.ips].join(" ").toLocaleLowerCase(locale).includes(search)) continue;
    const name = device.connection ? device.connection + " (OpenWrt)" : t("Aansluiting niet gemeten");
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(device);
  }
  el("topology-note").textContent = "Verbindingen zonder gemeten aansluiting zijn logisch weergegeven, niet fysiek bevestigd. · " + devices.size
    ? devices.size + t(" apparaten · Sleep een knooppunt of de achtergrond. Zoom met het muiswiel of twee vingers.")
    : t("Nog geen apparaten beschikbaar.");
  el("topology-cloud").hidden = !devices.size;
  el("topology-search").hidden = !devices.size;
  el("topology-no-match").hidden = groups.size > 0;
  map.toggleAttribute("hidden", !groups.size);

  const focused = document.activeElement?.dataset.node;
  const edgeLayer = svg("g", {"aria-hidden": "true"});
  const nodeLayer = svg("g");
  viewport.replaceChildren(edgeLayer, nodeLayer);
  nodes = [];
  edges = [];

  function select(id) {
    selectedDevice = id;
    const device = devices.get(id), row = measured.get(id);
    el("topology-detail").hidden = !device;
    for (const node of nodes) {
      if (node.type === "client") node.element.setAttribute("aria-pressed", String(node.id === "device:" + id));
    }
    if (!device) return;
    el("topology-device-name").textContent = device.name || device.ips[0] || id;
    el("topology-device-address").textContent = [...new Set([...device.ips, id])].join(" · ") + (device.connection ? " · " + [device.connection, device.ssid, device.port].filter(Boolean).join(" · ") : "");
    el("topology-device-traffic").textContent = row
      ? t("Download") + " " + bytes(row.rx) + " · " + t("Upload") + " " + bytes(row.tx) : t("Geen meting in deze periode.");
    const button = el("topology-graph");
    button.hidden = !row;
    button.onclick = row ? () => {
      source = id;
      sourceLabel = row.label;
      refresh();
      el("chart-title").scrollIntoView({block: "nearest"});
    } : null;
  }

  function add(id, name, type, x, y, parent, action) {
    if (!positions.has(id)) positions.set(id, {x, y});
    const point = positions.get(id);
    if (parent) {
      const line = svg("line", {class: "map-edge map-edge-" + type});
      edgeLayer.append(line);
      edges.push({line, from: parent, to: point});
    }
    const element = svg("g", {class: "map-node map-" + type, "data-node": id, "aria-label": name});
    if (action) {
      element.setAttribute("role", "button");
      element.setAttribute("tabindex", "0");
      element.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          action();
        }
      });
    }
    const title = svg("title");
    title.textContent = name;
    const marker = type === "client" ? svg("circle", {r: 8}) : svg("rect", {x: -12, y: -12, width: 24, height: 24, rx: 6});
    const label = svg("text", {x: 17, y: 4});
    label.textContent = name.length > 24 ? name.slice(0, 23) + "…" : name;
    element.append(title, marker, label);
    nodeLayer.append(element);
    nodes.push({id, type, element, point, action});
    return point;
  }

  if (groups.size) {
    const internet = add("internet", "Internet", "internet", 0, modem?.name ? -165 : -105);
    const upstream = modem?.name
      ? add("upstream-modem", [modem.name, modem.ip].filter(Boolean).join(" · "), "router", 0, -80, internet)
      : internet;
    const router = add("router", "OpenWrt", "router", 0, 0, upstream);
    const branches = [...groups].sort(([a], [b]) => tableCollator.compare(a, b));
    const sector = 2 * Math.PI / branches.length;
    branches.forEach(([name, clients], index) => {
      const id = "group:" + name;
      const open = Boolean(search) || !collapsedGroups.has(id);
      const center = Math.PI / 2 + index * sector;
      const radius = branches.length === 1 ? 105 : 195;
      const group = add(id, name + " (" + clients.length + ")", "group",
        Math.cos(center) * radius, Math.sin(center) * radius, router, search ? null : () => {
          if (collapsedGroups.has(id)) collapsedGroups.delete(id);
          else collapsedGroups.add(id);
          refit = true;
          showTopology(graphData);
        });
      if (!search) nodes.at(-1).element.setAttribute("aria-expanded", String(open));
      if (!open) return;
      clients.sort((a, b) => tableCollator.compare(a.name || a.source, b.name || b.source));
      let offset = 0;
      for (let ring = 0; offset < clients.length; ring++) {
        const distance = 330 + ring * 125;
        const span = sector * .82;
        const count = Math.min(clients.length - offset, Math.max(1, Math.floor(span * distance / 185)));
        for (let i = 0; i < count; i++) {
          const client = clients[offset + i];
          const angle = center + span * ((i + .5) / count - .5);
          add("device:" + client.source, client.name || client.ips[0] || client.source, "client",
            Math.cos(angle) * distance, Math.sin(angle) * distance, group, () => select(client.source));
        }
        offset += count;
      }
    });
  }
  select(selectedDevice);
  if (refit && nodes.length) {
    fitMap();
    refit = false;
  } else paintMap();
  if (focused) nodes.find(node => node.id === focused)?.element.focus({preventScroll: true});
}

function show(data) {
  const status = data.status;
  el("status").textContent = status.updated
    ? (status.interface || t("Interface onbekend")) + t(" · laatste meetronde ") +
      new Date(status.updated).toLocaleTimeString(locale, {timeZone: status.zone}) +
      (data.first ? t(" · historie vanaf ") + data.first.slice(0, 10) : "")
    : t("Wachten op de eerste meetronde");
  const warnings = [...(status.errors || [])];
  if (["host", "peer", "app"].includes(kind) && status.host_hints_error) {
    warnings.push(t("OpenWrt-apparaatnamen niet beschikbaar. ") + status.host_hints_error);
  }
  if (kind === "device") {
    if (status.device_error) warnings.push(status.device_error);
    else if (status.device_configured === false) warnings.push(t("Stel OpenWrt in onder HA-Bandwidth → Configuratie."));
  }
  if (kind === "peer" && status.peers_enabled === false) warnings.push(t("IP-meting staat uit."));
  el("warnings").hidden = warnings.length === 0;
  el("warnings").textContent = warnings.join(" · ");
  el("range").textContent = data.start === data.end ? dateFormat.format(new Date(data.start))
    : dateFormat.formatRange(new Date(data.start), new Date(data.end));
  const comparing = kind === "compare";
  el("comparison").hidden = !comparing;
  el("comparison-legend").hidden = !comparing;
  el("legend").hidden = comparing;
  el("totals").hidden = comparing;
  el("ranking-panel").hidden = comparing;
  if (comparing) showComparison(data);
  const rx = data.buckets.reduce((total, row) => total + row.rx, 0);
  const tx = data.buckets.reduce((total, row) => total + row.tx, 0);
  const hasData = data.buckets.length > 0 || Boolean(data.router_buckets?.length || data.modem_buckets?.length);
  el("download").textContent = hasData ? bytes(rx) : "—";
  el("upload").textContent = hasData ? bytes(tx) : "—";
  el("total").textContent = hasData ? bytes(rx + tx) : "—";
  el("chart-title").textContent = sourceLabel || t("Verkeer over tijd");
  el("clear").hidden = !source;
  el("empty").hidden = hasData;
  el("chart").parentElement.hidden = !hasData;
  el("chart-details").hidden = !hasData;
  if (hasData) timeline(data);
  if (!comparing) table(data.rows);
  showDestinations(data);
  showTopology(data);
  el("shared-section").hidden = kind !== "app" || !(status.shared?.length || status.unavailable?.length);
  el("shared").textContent = status.shared?.join(", ") || "";
  el("unavailable").textContent = status.unavailable?.length
    ? t("Actief zonder bruikbare tellers: ") + status.unavailable.join(", ") : "";
}

const scheduledBackups = document.createElement("section");
scheduledBackups.setAttribute("aria-label", t("Automatische back-ups"));
el("backup-panel").append(scheduledBackups);

function renderScheduledBackups(data) {
  const title = document.createElement("h3");
  title.textContent = t("Automatische back-ups");
  const schedule = document.createElement("p");
  const backups = data.scheduled || [];
  schedule.textContent = t("Dinsdag t/m zondag een dagback-up, maandag een weekback-up. {count} van {limit} opgeslagen.", {count: backups.length, limit: data.limit});
  const list = document.createElement("ul");
  for (const name of backups) {
    const item = document.createElement("li");
    const date = dateFormat.format(new Date(name.slice(0, 10)));
    const label = (name.endsWith("-weekly.sqlite3") ? t("Weekback-up") : t("Dagback-up")) + " " + date;
    item.append(label + " ");
    for (const [action, caption] of [["restore", t("Terugzetten")], ["delete", t("Verwijderen")]]) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = caption;
      button.setAttribute("aria-label", caption + " " + label);
      button.onclick = async () => {
        const question = action === "restore"
          ? t("Deze back-up terugzetten? De huidige meetgegevens worden vervangen.")
          : t("Deze back-up definitief verwijderen?");
        if (!window.confirm(label + "\n\n" + question)) return;
        button.disabled = true;
        const status = el("backup-status");
        try {
          const response = await fetch("./api/backup/scheduled/" + action + "/" + encodeURIComponent(name), {
            method: "POST",
            headers: {"X-HA-Bandwidth-Restore": "1"},
          });
          const result = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(result.error ? t(result.error) : "HTTP " + response.status);
          if (action === "restore") ipDetails.clear();
          status.textContent = action === "restore" ? t("De meetgegevens zijn teruggezet.") : t("Back-up verwijderd.");
          await backupStatus();
        } catch (error) {
          status.textContent = error.message;
        } finally {
          button.disabled = false;
        }
      };
      item.append(button, " ");
    }
    list.append(item);
  }
  scheduledBackups.replaceChildren(title, schedule, list);
}

async function backupStatus() {
  try {
    const response = await fetch("./api/backup/status");
    if (!response.ok) return;
    const data = await response.json();
    el("previous-backup").hidden = !data.previous;
    renderScheduledBackups(data);
  } catch {
    // Back-up download and restore remain available if this check fails.
  }
}

el("restore-form").addEventListener("submit", async event => {
  event.preventDefault();
  const file = el("restore-file").files[0];
  if (!file || !el("restore-confirm").checked) return;
  const status = el("backup-status");
  if (file.size > 256 * 1024 * 1024) {
    status.textContent = t("Het bestand is groter dan 256 MiB.");
    return;
  }
  const button = el("restore-button");
  button.disabled = true;
  status.textContent = t("Back-up terugzetten…");
  try {
    const response = await fetch("./api/backup/restore", {
      method: "POST",
      headers: {"Content-Type": "application/octet-stream", "X-HA-Bandwidth-Restore": "1"},
      body: file,
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error ? t(result.error) : "HTTP " + response.status);
    ipDetails.clear();
    event.target.reset();
    status.textContent = t("De meetgegevens zijn teruggezet.");
    await backupStatus();
  } catch (error) {
    status.textContent = t("Terugzetten mislukt. ") + error.message;
  } finally {
    button.disabled = false;
  }
});

async function load() {
  const id = ++request;
  const backup = kind === "backup";
  el("backup-panel").hidden = !backup;
  el("measurement-panel").hidden = backup;
  if (backup) {
    await backupStatus();
    return;
  }
  const params = new URLSearchParams({kind, period, source});
  if (el("date").value) params.set("date", el("date").value);
  el("explanation").textContent = views[kind][0];
  el("ranking").textContent = views[kind][1];
  try {
    const response = await fetch("./api/traffic?" + params);
    if (!response.ok) throw new Error("HTTP " + response.status);
    const data = await response.json();
    if (id === request) show(data);
  } catch (error) {
    if (id !== request) return;
    el("warnings").hidden = false;
    el("warnings").textContent = t("Dashboard kon de metingen niet ophalen (") + error.message + ").";
    el("destinations").hidden = true;
  }
}

for (const [key, change] of [
  ["kind", value => { kind = value; source = ""; sourceLabel = ""; }],
  ["period", value => { period = value; }],
]) {
  const buttons = document.querySelectorAll("[data-" + key + "]");
  for (const button of buttons) {
    button.addEventListener("click", () => {
      change(button.dataset[key]);
      for (const item of buttons) item.setAttribute("aria-pressed", String(item === button));
      refresh();
    });
  }
}
const setupDialog = el("ha-setup-dialog");
const setupMessages = {
  ready: "Gereed", missing: "Ontbreekt", pending: "Nog niet gereed",
  disabled: "Uitgeschakeld", unknown: "Niet te controleren",
};
const setupChecks = [
  ["broker", "MQTT-broker", "Installeer en start Mosquitto broker in de appstore, of start je bestaande MQTT-broker die bij Supervisor is geregistreerd.", "/hassio/store", "Open appstore"],
  ["integration", "MQTT-integratie", "Open Apparaten en diensten. Kies Configureren bij de gevonden MQTT-integratie, of kies Integratie toevoegen en zoek naar MQTT.", "/config/integrations", "Open Apparaten en diensten"],
  ["publisher", "Publicatie vanuit HA-Bandwidth", "Wacht ongeveer een minuut nadat de broker is gestart. Controleer het HA-Bandwidth-logboek als dit zo blijft."],
  ["entities", "HA-Bandwidth-entiteiten", "Controleer of MQTT verbonden is met dezelfde broker en of MQTT Discovery aanstaat. Als je de sensoren hebt hernoemd, kijk dan bij het apparaat HA-Bandwidth.", "/config/integrations", "Open Apparaten en diensten"],
];
let checkingSetup = false;

async function checkHASetup(showAlways = false) {
  if (showAlways && !setupDialog.open) setupDialog.showModal();
  if (checkingSetup) return;
  checkingSetup = true;
  const status = el("ha-setup-status");
  const steps = el("ha-setup-steps");
  const retry = el("retry-ha-setup");
  status.textContent = t("Installatie wordt gecontroleerd…");
  steps.replaceChildren();
  retry.disabled = true;
  try {
    const response = await fetch("./api/ha-setup", {signal: AbortSignal.timeout(15000)});
    if (!response.ok) throw new Error("HTTP " + response.status);
    const result = await response.json();
    const ready = setupChecks.every(([key]) => result[key] === "ready");
    status.textContent = t(ready ? "Alle controles zijn geslaagd." : "Volg de onderstaande stappen en controleer daarna opnieuw.");
    for (const [key, title, guidance, href, linkText] of setupChecks) {
      const value = result[key];
      const item = document.createElement("li");
      const heading = document.createElement("strong");
      heading.textContent = t(title) + " · " + t(setupMessages[value] || setupMessages.unknown);
      item.append(heading);
      if (value !== "ready") {
        const detail = document.createElement("p");
        detail.textContent = t(value === "unknown"
          ? "Home Assistant of Supervisor gaf geen bruikbaar antwoord. Probeer het opnieuw zodra Home Assistant volledig is gestart."
          : value === "disabled"
            ? "Zet publish_to_ha aan onder HA-Bandwidth → Configuratie en herstart de app."
            : guidance);
        item.append(detail);
        if (href && value !== "unknown") {
          const link = document.createElement("a");
          link.href = href;
          link.target = "_blank";
          link.rel = "noopener";
          link.textContent = t(linkText);
          item.append(link);
        }
      }
      steps.append(item);
    }
    if (!ready && !setupDialog.open && !showAlways) setupDialog.showModal();
  } catch {
    status.textContent = t("De installatiecheck kon niet worden geladen. Probeer het opnieuw.");
    if (!setupDialog.open && !showAlways) setupDialog.showModal();
  } finally {
    retry.disabled = false;
    checkingSetup = false;
  }
}

el("check-ha-setup").addEventListener("click", () => checkHASetup(true));
el("retry-ha-setup").addEventListener("click", () => checkHASetup(true));
if (!shared && !embeddedCard) {
  let checked = false;
  try {
    checked = sessionStorage.getItem("ha-bandwidth.setup-checked") === "1";
    sessionStorage.setItem("ha-bandwidth.setup-checked", "1");
  } catch {
    // The check still runs when browser storage is blocked.
  }
  if (!checked) checkHASetup();
}

el("download-ha-dashboard").addEventListener("click", async event => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const response = await fetch("./lovelace.json");
    if (!response.ok) throw new Error("HTTP " + response.status);
    const ingress = new URL("./", window.location.href).pathname.replace(/\/$/, "");
    const content = (await response.text()).replaceAll("__HA_BANDWIDTH_INGRESS__", ingress);
    const blob = new Blob([content], {type: "application/json"});
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "ha-bandwidth-dashboard.yaml";
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  } catch {
    window.alert(t("Dashboard downloaden mislukt."));
  } finally {
    button.disabled = false;
  }
});

el("date").addEventListener("change", refresh);
el("today").addEventListener("click", () => { el("date").value = ""; refresh(); });
el("clear").addEventListener("click", () => { source = ""; sourceLabel = ""; refresh(); });
function refresh() {
  if (shared) shared.update({period, source, sourceLabel, date: el("date").value});
  else load();
}

const unsubscribe = shared?.subscribe(state => {
  ({period, source, sourceLabel} = state);
  el("date").value = state.date;
  for (const button of document.querySelectorAll("[data-period]")) {
    button.setAttribute("aria-pressed", String(button.dataset.period === period));
  }
  load();
});
if (!shared) load();

// Independent polling avoids redrawing the topology and losing camera position.
function bitRate(value) {
  if (!Number.isFinite(value) || value < 0) return "—";
  return value >= 1e9 ? (value / 1e9).toFixed(2) + " Gbit/s"
       : value >= 1e6 ? (value / 1e6).toFixed(2) + " Mbit/s"
       : value >= 1e3 ? (value / 1e3).toFixed(1) + " kbit/s" : value + " bit/s";
}
let liveBusy = false;
async function loadLive() {
  if (liveBusy) return;
  liveBusy = true;
  try {
    const response = await fetch("./api/live");
    if (!response.ok) throw new Error("HTTP " + response.status);
    const data = await response.json();
    const age = data.updated ? Math.max(0, (Date.now() - Date.parse(data.updated)) / 1000) : Infinity;
    el("live-freshness").textContent = Number.isFinite(age)
      ? (age > 90 ? "Verouderde meting · " : "Laatste meting · ") + Math.round(age) + " s geleden"
      : "Wachten op tweede meetronde";
    const wan = (data.sources || []).find(s => s.kind === "openwrt")
      || (data.sources || []).find(s => s.kind === "modem");
    el("live-rx").textContent = wan ? bitRate(wan.rx_bps) : "—";
    el("live-tx").textContent = wan ? bitRate(wan.tx_bps) : "—";
    const leaders = (data.sources || []).filter(s => s.kind === "device" || s.kind === "app")
      .sort((a,b) => (b.rx_bps+b.tx_bps)-(a.rx_bps+a.tx_bps)).slice(0,10);
    const body = el("live-leaders");
    body.replaceChildren();
    for (const item of leaders) {
      const tr = document.createElement("tr");
      for (const value of [item.label || item.source, bitRate(item.rx_bps), bitRate(item.tx_bps)]) {
        const td = document.createElement("td");
        td.textContent = value;
        tr.append(td);
      }
      body.append(tr);
    }
    if (!leaders.length) {
      const tr = document.createElement("tr"), td = document.createElement("td");
      td.colSpan = 3;
      td.textContent = "Nog geen apparaat- of appmetingen beschikbaar.";
      tr.append(td);
      body.append(tr);
    }
    const alerts = el("live-alerts");
    alerts.replaceChildren();
    const recent = (data.alerts || []).slice(0, 8);
    if (!recent.length) alerts.textContent = "Nog geen afwijkingen vastgesteld (minimaal acht eerdere meetrondes nodig).";
    for (const item of recent) {
      const row = document.createElement("p");
      row.className = "live-alert";
      row.textContent = new Date(item.timestamp).toLocaleString(locale) + " · " +
        (item.label || item.source) + ": " + bitRate(item.bps) +
        " (normaal circa " + bitRate(item.baseline_bps) + ")";
      alerts.append(row);
    }
  } catch (error) {
    el("live-freshness").textContent = "Livestatus niet bereikbaar";
  } finally { liveBusy = false; }
}
loadLive();
const liveTimer = setInterval(loadLive, 5000);

const timer = setInterval(load, 30000);
return () => {
  clearInterval(timer);
  clearInterval(liveTimer);
  unsubscribe?.();
};
}

if (document.querySelector("main #download-ha-dashboard")) {
  mountDashboard(document, window.fetch.bind(window), new URL(window.location.href));
}

