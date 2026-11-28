import concurrent.futures
import ipaddress
import http.client
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
from contextlib import closing
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

from zoneinfo import ZoneInfo

import app_settings
from app_settings import retention_days
import rollup
from migrations import migrate
from csv_export import CSV_COLUMNS, csv_safe, csv_text
from ipinfo import fetch_ipinfo as lookup_ipinfo, public_ip, stored_ipinfo
from periods import period_bounds, previous_period, previous_totals
from topology import router_topology
from budget import BYTES_PER_GB, cycle_bounds, settings as budget_settings, status as evaluate_budget
from live_monitor import LiveMonitor
from destinations import AppDestinations, NetworkCapture, PROTOCOLS, bridge_apps
from modem import DirectZyxel, modem_reading
from openwrt import OpenWrt, hosts_by_ip
from ha_dashboard import provision_dashboard
from ha_mqtt import budget_entities, publish as publish_to_ha, setup_status, spike_entities
from storage_backup import MAX_BACKUP_SIZE, restore, snapshot

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("BANDWIDTH_DATA", "/data"))
INTERVAL = 30
LIVE = LiveMonitor()
OPTIONS = DATA / "options.json"
SETTINGS = json.loads(OPTIONS.read_text(encoding="utf-8")) if OPTIONS.exists() else {}
ZONE = ZoneInfo(SETTINGS.get("timezone", "Europe/Amsterdam"))
STATUS = {}
ROUTER_HOSTS = {}
ROUTER_LINKS = {}
# De bestanden van het dashboard staan vast. Ze worden één keer gelezen, zodat een verzoek nooit een pad
# kiest: de URL is alleen een sleutel in deze tabel.
STATIC_FILES = {
    "/": ("dashboard.html", "text/html; charset=utf-8"),
    "/lovelace.json": ("lovelace.json", "application/json"),
    "/lovelace-card.js": ("lovelace-card.js", "text/javascript; charset=utf-8"),
    "/dashboard.js": ("dashboard.js", "text/javascript; charset=utf-8"),
    "/dashboard.css": ("dashboard.css", "text/css; charset=utf-8"),
}
STATIC_ASSETS = {route: ((ROOT / name).read_bytes(), kind) for route, (name, kind) in STATIC_FILES.items()}
PERIODS = {"day": 13, "week": 10, "month": 10, "year": 7}





RETENTION_DAYS = retention_days(SETTINGS)
HOURLY_DAYS = 0
RETENTION_RANGE = app_settings.RETENTION_RANGE
SETTINGS_LOCK = threading.Lock()


def app_settings_file():
    return DATA / "app-settings.json"


def load_app_settings():
    """Instellingen die op de pagina Instellingen zijn opgeslagen."""
    return app_settings.load(app_settings_file())


def apply_app_settings():
    """Laat de pagina Instellingen voorgaan op de optie in Configuratie."""
    global RETENTION_DAYS, HOURLY_DAYS
    saved = load_app_settings()
    RETENTION_DAYS = retention_days({**SETTINGS, **saved})
    HOURLY_DAYS = app_settings.hourly_days(saved)


def save_app_settings(settings):
    app_settings.save(app_settings_file(), settings)


def stored_days():
    """Het aantal kalenderdagen sinds de oudste meting, of 0 zonder metingen."""
    with closing(database()) as db:
        first = db.execute("SELECT MIN(hour) FROM traffic").fetchone()[0]
    if not first:
        return 0
    return (datetime.now(ZONE).date() - date.fromisoformat(first[:10])).days + 1


def retention_state():
    return {
        "retention_days": RETENTION_DAYS, "configured": retention_days(SETTINGS),
        "from_settings_page": "retention_days" in load_app_settings(),
        "stored_days": stored_days(), "min": RETENTION_RANGE[0], "max": RETENTION_RANGE[1],
    }


def change_retention(body):
    """Valideer en bewaar een nieuwe bewaartijd. Geeft (status, antwoord) terug."""
    days = body.get("retention_days") if isinstance(body, dict) else None
    low, high = RETENTION_RANGE
    if not isinstance(days, int) or isinstance(days, bool) or not low <= days <= high:
        return 400, {"error": f"Kies een heel aantal dagen van {low} tot en met {high}."}
    with SETTINGS_LOCK:
        # Alleen een verlaging van de huidige bewaartijd kan nieuwe metingen kosten.
        if days < RETENTION_DAYS and days < stored_days() and body.get("confirm") is not True:
            return 409, {"error": "Oudere metingen worden verwijderd. Bevestig dat je dat wilt.",
                         "stored_days": stored_days()}
        save_app_settings({**load_app_settings(), "retention_days": days})
        apply_app_settings()
    logging.info("Bewaartijd ingesteld op %s dagen", days)
    return 200, retention_state()
KINDS = {"host", "app", "peer", "compare", "device"}
PREVIOUS_BACKUP = DATA / "pre-restore.sqlite3"
BACKUP_LOCK = threading.Lock()
IPINFO_LOCK = threading.Lock()
OPENWRT_ENABLED = bool(SETTINGS.get("openwrt_url", "").strip())


BACKUP_DIR = DATA / "scheduled-backups"
BACKUP_LIMIT = 25
BACKUP_NAME = re.compile(r"\d{4}-\d{2}-\d{2}-(daily|weekly)\.sqlite3")


def saved_backups():
    return sorted((path for path in BACKUP_DIR.glob("*.sqlite3")
                   if BACKUP_NAME.fullmatch(path.name) and path.is_file()), reverse=True)


def save_daily_backup(today):
    with BACKUP_LOCK:
        BACKUP_DIR.mkdir(exist_ok=True)
        marker = BACKUP_DIR / "last-date"
        day = today.isoformat()
        if not marker.exists() or marker.read_text() != day:
            kind = "weekly" if today.weekday() == 0 else "daily"
            target = BACKUP_DIR / f"{day}-{kind}.sqlite3"
            with tempfile.TemporaryDirectory(dir=BACKUP_DIR) as directory:
                staging = Path(directory)
                if not target.exists():
                    with closing(database()) as connection:
                        snapshot(connection, staging / "backup.sqlite3")
                    (staging / "backup.sqlite3").replace(target)
                (staging / "date").write_text(day)
                (staging / "date").replace(marker)
            logging.info("Automatische back-up opgeslagen: %s", target.name)
        for expired in saved_backups()[BACKUP_LIMIT:]:
            expired.unlink()


def backup_scheduler():
    while True:
        try:
            save_daily_backup(datetime.now(ZONE).date())
        except (OSError, sqlite3.Error):
            logging.exception("Automatische back-up of opschoning mislukt")
        time.sleep(60)


def database():
    connection = sqlite3.connect(DATA / "bandwidth.sqlite3", timeout=10, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def initialize():
    DATA.mkdir(parents=True, exist_ok=True)
    with closing(database()) as db:
        db.execute("PRAGMA journal_mode = WAL")
        migrate(db)


def choose_interface():
    manual = SETTINGS.get("interface", "auto")
    if manual != "auto":
        return manual
    for family in ("-4", "-6"):
        routes = json.loads(subprocess.check_output(
            ["ip", "-j", family, "route", "show", "default"], timeout=4
        ))
        candidates = [route for route in routes if route.get("dev")]
        if candidates:
            return min(candidates, key=lambda route: route.get("metric", 0))["dev"]
    raise OSError("Geen standaardroute gevonden. Stel interface handmatig in.")


def host_counters(interface):
    for line in Path("/proc/net/dev").read_text().splitlines()[2:]:
        name, _, values = line.partition(":")
        if name.strip() == interface:
            counters = values.split()
            index = socket.if_nametoindex(interface)
            return [(str(index), "host", interface, interface, int(counters[0]), int(counters[8]))]
    raise OSError(f"Interface {interface} niet gevonden")


class DockerConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect("/var/run/docker.sock")


def docker_get(path):
    connection = DockerConnection("localhost", timeout=4)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        if response.status != 200:
            raise OSError(f"Docker HTTP {response.status}")
        return json.load(response)
    finally:
        connection.close()


def app_counters(container):
    identifier = container["Id"]
    details = docker_get(f"/containers/{identifier}/json")
    stats = docker_get(f"/containers/{identifier}/stats?stream=false&one-shot=true")
    name = details["Name"].lstrip("/")
    labels = details["Config"].get("Labels") or {}
    label = labels.get("io.hass.name") or name
    generation = identifier + details["State"]["StartedAt"]
    return [
        (generation + ":" + interface, "app", name, label, data["rx_bytes"], data["tx_bytes"])
        for interface, data in (stats.get("networks") or {}).items()
    ]


def read_apps(pool, containers):
    counters, shared, unavailable = [], [], []
    pending = {}
    for container in containers:
        name = container["Names"][0].lstrip("/")
        mode = container["HostConfig"]["NetworkMode"]
        if mode == "host" or mode.startswith("container:"):
            shared.append(name)
        elif mode != "none":
            pending[pool.submit(app_counters, container)] = name
    for job in concurrent.futures.as_completed(pending):
        try:
            readings = job.result()
        except (OSError, http.client.HTTPException, ValueError) as error:
            logging.debug("Docker-statistieken voor %s: %s", pending[job], error)
            readings = []
        if readings:
            counters.extend(readings)
        else:
            unavailable.append(pending[job])
    return counters, sorted(shared), sorted(unavailable)


def deltas(readings, previous):
    current = {}
    labels = {}
    for generation, kind, source, label, rx, tx in readings:
        key = (kind, source, generation)
        current[key] = (rx, tx)
        labels[key] = label
    rows = []
    for key, (rx, tx) in current.items():
        old = previous.get(key)
        if old is not None and rx >= old[0] and tx >= old[1]:
            kind, source, _ = key
            rows.append((kind, source, labels[key], rx - old[0], tx - old[1]))
    return current, rows


def record(now, rows, prune, destinations=()):
    hour = now.strftime("%Y-%m-%dT%H")
    with closing(database()) as db, db:
        db.executemany("""
            INSERT INTO traffic VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(hour, kind, source) DO UPDATE SET
                label = excluded.label, rx = rx + excluded.rx, tx = tx + excluded.tx
        """, [(hour, *row) for row in rows])
        if destinations:
            day = now.date().isoformat()
            db.executemany("""
                INSERT INTO app_destinations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(app, day, ip, protocol, port, domain, evidence) DO UPDATE SET
                    rx = rx + excluded.rx, tx = tx + excluded.tx
            """, [(app, day, *details) for app, *details in destinations])
        if prune:
            cutoff = (now.date() - timedelta(days=RETENTION_DAYS - 1)).isoformat()
            db.execute("DELETE FROM traffic WHERE hour < ?", (cutoff,))
            db.execute("DELETE FROM app_destinations WHERE day < ?", (cutoff,))
            db.execute("DELETE FROM traffic_alerts WHERE timestamp < ?", (cutoff,))
            if HOURLY_DAYS:
                rollup.summarize(db, (now.date() - timedelta(days=HOURLY_DAYS)).isoformat())


def export_csv(day, period, kind, source):
    """De getoonde periode als CSV, in dezelfde indeling als de grafiek: uur, dag of maand per bron."""
    start, end = period_bounds(day, period)
    kinds = ("host", "openwrt", "modem") if kind == "compare" else (kind,)
    sql = (f"SELECT substr(hour, 1, ?) AS bucket, kind, source, MAX(label) AS label, SUM(rx) AS rx, SUM(tx) AS tx "
           f"FROM traffic WHERE hour >= ? AND hour < ? AND kind IN ({','.join('?' * len(kinds))})")
    params = [PERIODS[period], start.isoformat(), end.isoformat(), *kinds]
    if source:
        sql += " AND source = ?"
        params.append(source)
    with closing(database()) as db:
        # De SQL-tekst bestaat uit vaste stukken; alle waarden gaan als parameters mee.
        # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        rows = db.execute(sql + " GROUP BY bucket, kind, source ORDER BY bucket, kind, source", params).fetchall()
    return csv_text(rows)


def store_alerts(alerts):
    """Bewaar nieuwe verkeerspieken, zodat ze een herstart van de app overleven."""
    if not alerts:
        return
    with closing(database()) as db, db:
        db.executemany("""
            INSERT OR IGNORE INTO traffic_alerts
                (timestamp, kind, source, label, bps, baseline_bps, reason, interval_start, leaders)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [(alert["timestamp"], alert["kind"], alert["source"], alert.get("label") or "",
               alert["bps"], alert["baseline_bps"], alert.get("reason", ""),
               alert.get("interval_start"), json.dumps(alert.get("leaders", {})))
              for alert in alerts])


def alert_from_row(row):
    alert = dict(row)
    try:
        alert["leaders"] = json.loads(alert["leaders"])
    except ValueError:
        alert["leaders"] = {}
    return alert


def load_alerts(limit=40):
    with closing(database()) as db:
        rows = db.execute("SELECT * FROM traffic_alerts ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
    return [alert_from_row(row) for row in rows]


def alerts_today(now):
    """Het aantal pieken van vandaag en de laatste piek (of None)."""
    with closing(database()) as db:
        count = db.execute("SELECT COUNT(*) FROM traffic_alerts WHERE timestamp >= ?",
                           (now.date().isoformat(),)).fetchone()[0]
        last = db.execute("SELECT * FROM traffic_alerts ORDER BY timestamp DESC LIMIT 1").fetchone()
    return count, alert_from_row(last) if last else None


BUDGET_LABELS = {"openwrt": "OpenWrt WAN", "host": "Server"}


def hourly_cutoff(days=None, now=None):
    days = HOURLY_DAYS if days is None else days
    return ((now or datetime.now(ZONE)).date() - timedelta(days=days)).isoformat()


def hourly_state():
    with closing(database()) as db:
        pending = rollup.detail_days(db, hourly_cutoff()) if HOURLY_DAYS else 0
    return {"hourly_days": HOURLY_DAYS, "min": app_settings.HOURLY_RANGE[0], "max": app_settings.HOURLY_RANGE[1],
            "retention_days": RETENTION_DAYS, "stored_days": stored_days(), "pending_days": pending}


def change_hourly(body):
    """Stel in na hoeveel dagen uurmetingen tot dagtotalen worden samengevat (0 = nooit)."""
    days = body.get("hourly_days") if isinstance(body, dict) else None
    low, high = app_settings.HOURLY_RANGE
    if days != 0 and not app_settings.whole(days, low, high) or isinstance(days, bool):
        return 400, {"error": f"Kies 0 of een heel aantal dagen van {low} tot en met {high}."}
    with SETTINGS_LOCK:
        if days:
            with closing(database()) as db:
                affected = rollup.detail_days(db, hourly_cutoff(days))
            if affected and body.get("confirm") is not True:
                return 409, {"error": "Het uurdetail van oudere dagen verdwijnt. Bevestig dat je dat wilt.",
                             "affected_days": affected}
        save_app_settings({**load_app_settings(), "hourly_days": days})
        apply_app_settings()
    logging.info("Uurdetail ingesteld op %s dagen", days)
    return 200, hourly_state()


def budget_options():
    """De budgetopties: de pagina Instellingen gaat voor op Configuratie."""
    return app_settings.budget_options(SETTINGS, load_app_settings().get("budget"))


def budget_state():
    """De geldende budgetinstellingen voor het formulier. Een limiet van 0 betekent uit."""
    config = budget_settings(budget_options())
    return {"limit_gb": config["limit"] / BYTES_PER_GB if config else 0,
            "source": config["source"] if config else "modem",
            "reset_day": config["reset_day"] if config else 1,
            "warn_percent": config["warn_percent"] if config else 80,
            "from_settings_page": "budget" in load_app_settings()}


def change_budget(body):
    """Valideer en bewaar de budgetinstellingen. Een limiet van 0 zet het budget uit."""
    values, error = app_settings.clean_budget(body)
    if error:
        return 400, {"error": error}
    with SETTINGS_LOCK:
        save_app_settings({**load_app_settings(), "budget": values})
    logging.info("Databudget ingesteld: %s GB, bron %s", values["limit_gb"], values["source"])
    return 200, budget_state()


def measured_budget_bytes(config, start, end):
    """De gemeten bytes en het aantal meetrijen van de gekozen bron in een cyclus."""
    with closing(database()) as db:
        return tuple(db.execute(
            "SELECT COALESCE(SUM(rx + tx), 0), COUNT(*) FROM traffic WHERE kind = ? AND hour >= ? AND hour < ?",
            (config["source"], start.isoformat(), end.isoformat())).fetchone())


def calibrate_budget(body, now=None):
    """Zet het verbruik van de lopende cyclus gelijk aan de stand van de provider, of wis de correctie.

    Body: {"used_gb": 37.5} stelt in, {"used_gb": null} wist. Geeft (status, antwoord) terug.
    """
    now = now or datetime.now(ZONE)
    config = budget_settings(budget_options())
    if config is None:
        return 400, {"error": "Het databudget staat uit. Stel eerst een limiet in."}
    value, error = app_settings.clean_used_gb(body)
    if error:
        return 400, {"error": error}
    clear = value is None
    with SETTINGS_LOCK:
        settings = load_app_settings()
        if clear:
            settings.pop("budget_calibration", None)
        else:
            start, end = cycle_bounds(now.date(), config["reset_day"])
            counted, _ = measured_budget_bytes(config, start, end)
            settings["budget_calibration"] = {"cycle_start": start.isoformat(),
                                              "offset": round(value * BYTES_PER_GB) - counted}
        save_app_settings(settings)
    logging.info("Databudget gekalibreerd" if not clear else "Databudgetcorrectie gewist")
    return 200, dict(budget_status(now), enabled=True)


def budget_status(now=None):
    """Het huidige databudget, of None als het budget is uitgeschakeld."""
    config = budget_settings(budget_options())
    if config is None:
        return None
    now = now or datetime.now(ZONE)
    start, end = cycle_bounds(now.date(), config["reset_day"])
    counted, rows = measured_budget_bytes(config, start, end)
    # Een kalibratie geldt alleen in de cyclus waarin ze is ingesteld. Daarna zijn de metingen compleet.
    calibration = load_app_settings().get("budget_calibration")
    offset = calibration["offset"] if calibration and calibration["cycle_start"] == start.isoformat() else 0
    result = evaluate_budget(config, max(0, counted + offset), now, measured=rows > 0 or offset != 0)
    result["counted"] = counted
    result["offset"] = offset
    result["source_label"] = (SETTINGS.get("upstream_modem_name", "").strip() or "Modem") \
        if config["source"] == "modem" else BUDGET_LABELS[config["source"]]
    return result


def home_assistant_entities():
    """Extra entiteiten voor Home Assistant: databudget en verkeerspieken."""
    now = datetime.now(ZONE)
    count, last = alerts_today(now)
    return budget_entities(budget_status(now)) + spike_entities(last, count, now)


def log_health(history, name, error="", success="verbinding en uitlezing werken"):
    if name in history and history[name] == error:
        return
    history[name] = error
    if error:
        logging.warning("%s: %s", name, error)
    else:
        logging.info("%s: %s", name, success)


def collect():
    global STATUS, ROUTER_HOSTS, ROUTER_LINKS
    previous, capture, last_day, last_round = {}, None, None, None
    health = {}
    modem_phase = ""
    app_destinations = AppDestinations()
    track_apps = SETTINGS.get("track_app_destinations", True)
    openwrt = OpenWrt(SETTINGS) if OPENWRT_ENABLED else None
    zyxel = DirectZyxel(SETTINGS) if SETTINGS.get("zyxel_direct", False) else None
    modem_source = "Zyxel direct" if zyxel else "Zyxel via Home Assistant"
    modem_configured = bool(zyxel) or any(SETTINGS.get(key, "").strip() for key in
                           ("modem_download_entity", "modem_upload_entity"))
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        while True:
            started = time.monotonic()
            readings, errors, shared, unavailable = [], [], [], []
            interface = None
            try:
                interface = choose_interface()
                readings.extend(host_counters(interface))
            except (OSError, subprocess.SubprocessError, ValueError) as error:
                errors.append(f"Servermeting: {error}")
            host_destinations = []
            if capture and (interface != capture.interface or capture.error):
                capture.close()
                host_destinations.extend(capture.drain())
                if capture.error:
                    errors.append(f"IP-meting: {capture.error}")
                capture = None
            if interface and capture is None and SETTINGS.get("track_peers", True):
                capture = NetworkCapture(interface)
            containers = None
            try:
                containers = docker_get("/containers/json")
                apps, shared, unavailable = read_apps(pool, containers)
                readings.extend(apps)
            except (OSError, http.client.HTTPException, ValueError) as error:
                errors.append(f"Docker-statistieken ontbreken ({error}). Controleer Beveiligde modus.")
            destinations = []
            if track_apps:
                try:
                    owners = bridge_apps(docker_get("/networks"), containers) if containers is not None else {}
                    destinations, capture_errors = app_destinations.collect(owners)
                    errors.extend(f"App-bestemmingen · {error}" for error in capture_errors)
                except (OSError, http.client.HTTPException, ValueError) as error:
                    destinations, _ = app_destinations.collect({})
                    errors.append(f"App-bestemmingen: {error}")
            router_error, modem_error = "", ""
            if openwrt:
                try:
                    readings.append(openwrt.reading())
                except (OSError, URLError, ValueError, http.client.HTTPException) as error:
                    router_error = str(error)
            if modem_configured:
                try:
                    if zyxel:
                        readings.extend(zyxel.readings())
                    else:
                        readings.append(modem_reading(SETTINGS))
                except (OSError, URLError, ValueError, http.client.HTTPException) as error:
                    modem_error = str(error)
            if openwrt:
                log_health(health, "OpenWrt WAN", router_error, f"verbinding actief op {openwrt.device}")
            if modem_configured:
                log_health(health, modem_source, modem_error)
            log_health(health, "Docker", "" if containers is not None else "statistieken niet bereikbaar")
            device_error, host_hints_error = "", ""
            hints = {}
            if openwrt:
                if openwrt.session:
                    try:
                        hints = openwrt.host_hints()
                    except (OSError, ValueError, http.client.HTTPException) as error:
                        host_hints_error = str(error)
                    try:
                        readings.extend(openwrt.device_readings(hints))
                    except (OSError, ValueError, http.client.HTTPException) as error:
                        device_error = str(error)
                else:
                    device_error = host_hints_error = router_error
            if openwrt:
                log_health(health, "OpenWrt apparaatmetingen", device_error)
                log_health(health, "OpenWrt apparaatnamen", host_hints_error)
            ROUTER_HOSTS = hosts_by_ip(hints, SETTINGS.get("openwrt_url", "")) if openwrt else {}
            links = {}
            if openwrt and openwrt.session:
                try:
                    links, bridge_error = openwrt.connection_links()
                except (OSError, ValueError, http.client.HTTPException) as error:
                    log_health(health, "OpenWrt aansluitingen", str(error))
                else:
                    log_health(health, "OpenWrt bridge-tabel", bridge_error, "uitlezing geslaagd")
                    log_health(health, "OpenWrt aansluitingen",
                               "" if links else "geen LAN- of wifi-aansluitingen gevonden via dit routeraccount",
                               f"{len(links)} LAN-, wifi- of mesh-aansluitingen gevonden")
            ROUTER_LINKS = links
            now = datetime.now(ZONE)
            if last_round is not None and started - last_round > 180:
                previous = {}
            last_round = started
            current, rows = deltas(readings, previous)
            previous = current
            if capture:
                host_destinations.extend(capture.drain())
                if capture.error:
                    errors.append(f"IP-meting: {capture.error}")
            peer_totals = {}
            for _, peer, _, _, _, _, rx, tx in host_destinations:
                label = peer or "Overige IP-adressen"
                totals = peer_totals.setdefault(label, [0, 0])
                totals[0] += rx
                totals[1] += tx
            rows.extend(("peer", peer, peer, *totals) for peer, totals in peer_totals.items())
            expected = {"host", "app"}
            if openwrt:
                expected.update(("openwrt", "device"))
            if modem_configured:
                expected.add("modem")
            new_alerts = LIVE.update(rows, now, observed={key[0] for key in current}, expected=expected)
            try:
                store_alerts(new_alerts)
            except sqlite3.Error:
                logging.exception("Verkeerspiek kon niet worden bewaard")
            try:
                record(now, rows, now.date() != last_day, destinations + host_destinations)
                last_day = now.date()
                log_health(health, "Opslag", success="metingen worden opgeslagen")
                if modem_configured and not modem_error:
                    modem_deltas = [row for row in rows if row[0] == "modem"]
                    if not modem_deltas:
                        phase = "beginstand gelezen, wacht op volgende meting"
                    elif not any(rx or tx for _, _, _, rx, tx in modem_deltas):
                        phase = "tellers uitgelezen, maar deze zijn sinds de vorige meting niet veranderd"
                    else:
                        phase = "verkeer gemeten"
                    if modem_phase != phase:
                        for _, kind, source, _, rx, tx in readings:
                            if kind == "modem":
                                logging.info("Zyxel: %s; tellerstand %s: ontvangen=%s B verzonden=%s B",
                                             phase, source, rx, tx)
                    modem_phase = phase
                else:
                    modem_phase = ""
            except sqlite3.Error as error:
                log_health(health, "Opslag", str(error))
                errors.append(f"Opslag: {error}")
            STATUS = {
                "interface": interface, "updated": now.isoformat(), "errors": errors,
                "shared": shared, "unavailable": unavailable, "zone": ZONE.key,
                "peers_enabled": SETTINGS.get("track_peers", True),
                "app_destinations_enabled": track_apps,
                "router_configured": OPENWRT_ENABLED, "router_error": router_error,
                "modem_configured": modem_configured, "modem_error": modem_error, "modem_phase": modem_phase,
                "router_device": openwrt.device if openwrt and not router_error else "",
                "device_configured": OPENWRT_ENABLED, "device_error": device_error,
                "host_hints_error": host_hints_error,
            }
            time.sleep(max(0, INTERVAL - (time.monotonic() - started)))


def report(day, period, kind, source, now=None):
    router_hosts = ROUTER_HOSTS
    now = now or datetime.now(ZONE)
    start, end = period_bounds(day, period)
    bounds = (start.isoformat(), end.isoformat(), kind)
    if kind == "compare":
        with closing(database()) as db:
            rows = db.execute("""
                SELECT substr(hour, 1, ?) AS bucket, kind, SUM(rx) AS rx, SUM(tx) AS tx
                FROM traffic WHERE hour >= ? AND hour < ? AND kind IN ('host', 'openwrt', 'modem')
                GROUP BY bucket, kind ORDER BY bucket
            """, (PERIODS[period], *bounds[:2])).fetchall()
            first = db.execute("SELECT MIN(hour) FROM traffic").fetchone()[0]
        return {
            "start": start.isoformat(), "end": (end - timedelta(days=1)).isoformat(),
            "buckets": [dict(row) for row in rows if row["kind"] == "host"],
            "router_buckets": [dict(row) for row in rows if row["kind"] == "openwrt"],
            "modem_buckets": [dict(row) for row in rows if row["kind"] == "modem"],
            "router_label": "OpenWrt WAN",
            "modem_label": SETTINGS.get("upstream_modem_name", "").strip() or "5G-modem via HA",
            "status": STATUS, "first": first,
        }
    with closing(database()) as db, db:
        leaders = db.execute("""
            SELECT source, MAX(label) AS label, SUM(rx) AS rx, SUM(tx) AS tx
            FROM traffic WHERE hour >= ? AND hour < ? AND kind = ?
            GROUP BY source ORDER BY SUM(rx + tx) DESC, source LIMIT ?
        """, (*bounds, -1 if kind == "device" else 30)).fetchall()
        params = (PERIODS[period], *bounds)
        sql = """
            SELECT substr(hour, 1, ?) AS bucket, SUM(rx) AS rx, SUM(tx) AS tx
            FROM traffic WHERE hour >= ? AND hour < ? AND kind = ?
        """
        if source:
            sql += " AND source = ?"
            params += (source,)
        # De SQL-tekst bestaat uit vaste stukken; alle waarden gaan als parameters mee.
        # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        buckets = db.execute(sql + " GROUP BY bucket ORDER BY bucket", params).fetchall()
        first = db.execute("SELECT MIN(hour) FROM traffic").fetchone()[0]
        previous = previous_totals(db, day, period, kind, source, now, first)
        destinations, matching = [], []
        if kind == "host" or (kind == "app" and source):
            if kind == "host":
                clause = "app = ?" if source else "app GLOB ?"
                owner = "@host:" + (source or "*")
            else:
                clause = "app = ?"
                owner = source
            # De SQL-tekst bestaat uit vaste stukken; alle waarden gaan als parameters mee.
            # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            matching = db.execute(f"""
                SELECT ip, protocol, port, domain, evidence, SUM(rx) AS rx, SUM(tx) AS tx
                FROM app_destinations WHERE {clause} AND day >= ? AND day < ?
                GROUP BY ip, protocol, port, domain, evidence
                ORDER BY SUM(rx + tx) DESC, ip, protocol, port, domain, evidence LIMIT 101
            """, (owner, *bounds[:2])).fetchall()
            for row in matching[:100]:
                item = dict(row)
                number = item["protocol"]
                item["protocol"] = PROTOCOLS.get(number, f"IP-protocol {number}" if number >= 0 else "")
                try:
                    address = ipaddress.ip_address(item["ip"])
                except ValueError:
                    item["scope"] = "—"
                else:
                    item["scope"] = "Publiek IP" if address.is_global and not address.is_multicast else "Lokaal / speciaal IP"
                item["lookup_ip"] = public_ip(item["ip"])
                item["router_host"] = router_hosts.get(item["ip"])
                destinations.append(item)
        rows = [
            dict(row, lookup_ip=public_ip(row["source"]), router_host=router_hosts.get(row["source"]))
            if kind == "peer" else dict(row)
            for row in leaders
        ]
        details = stored_ipinfo(db, {row["lookup_ip"] for row in rows + destinations if row.get("lookup_ip")})
        for row in rows + destinations:
            if row.get("lookup_ip") in details:
                row["ipinfo"] = details[row["lookup_ip"]]
    return {
        "start": start.isoformat(), "end": (end - timedelta(days=1)).isoformat(),
        "rows": rows,
        "buckets": [dict(row) for row in buckets],
        "status": STATUS, "first": first, "previous": previous, "destinations": destinations,
        "destinations_truncated": len(matching) > 100,
        "upstream_modem": {
            "name": SETTINGS.get("upstream_modem_name", "").strip(),
            "ip": SETTINGS.get("upstream_modem_ip", "").strip(),
        } if kind == "device" else None,
        "topology": router_topology(router_hosts, ROUTER_LINKS, SETTINGS.get("openwrt_url", ""))
                    if kind == "device" else [],
    }


def ipinfo_lookup(address):
    # Recheck under the lock so simultaneous clicks only make one request.
    with IPINFO_LOCK, closing(database()) as db:
        cached = stored_ipinfo(db, (address,)).get(address)
        if cached is not None:
            return cached
        details = lookup_ipinfo(SETTINGS.get("ipinfo_token", ""), address)
        if any(details.values()):
            with db:
                db.execute("INSERT INTO ipinfo_cache VALUES (?, ?, ?, ?)", (
                    address, *(details.get(key, "") for key in ("asn", "as_name", "as_domain"))
                ))
        return details


class Dashboard(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.client_address[0] != "172.30.32.2":
            self.send_error(403)
            return
        url = urlsplit(self.path)
        if url.path == "/api/ipinfo":
            address = public_ip(parse_qs(url.query).get("ip", [""])[0])
            if not address:
                self.send_json_error(400, "IPinfo ondersteunt hier alleen publieke IP-adressen.")
                return
            try:
                data = ipinfo_lookup(address)
            except ValueError as error:
                self.send_json_error(400, str(error))
                return
            except sqlite3.Error:
                logging.exception("IPinfo-opslag is mislukt")
                self.send_json_error(500, "IPinfo kon niet worden opgeslagen of gelezen.")
                return
            self.reply(json.dumps(data).encode(), "application/json")
            return
        if url.path == "/api/budget":
            try:
                status = budget_status()
            except sqlite3.Error:
                logging.exception("Databudget kon niet worden berekend")
                self.send_json_error(500, "Het databudget kon niet worden berekend.")
                return
            payload = {"enabled": False} if status is None else dict(status, enabled=True)
            self.reply(json.dumps(payload).encode(), "application/json")
            return
        if url.path == "/api/settings/hourly":
            self.reply(json.dumps(hourly_state()).encode(), "application/json")
            return
        if url.path == "/api/settings/budget":
            self.reply(json.dumps(budget_state()).encode(), "application/json")
            return
        if url.path == "/api/live":
            self.reply(json.dumps(LIVE.snapshot()).encode(), "application/json")
            return
        if url.path == "/api/ha-setup":
            status = setup_status(SETTINGS.get("publish_to_ha", True))
            self.reply(json.dumps(status).encode(), "application/json")
            return
        if url.path == "/api/backup/status":
            with BACKUP_LOCK:
                status = {
                    "previous": PREVIOUS_BACKUP.exists(),
                    "scheduled": [path.name for path in saved_backups()],
                    "limit": BACKUP_LIMIT,
                }
            self.reply(json.dumps(status).encode(), "application/json")
            return
        if url.path in ("/api/backup", "/api/backup/previous"):
            self.download_backup(url.path.endswith("/previous"))
            return
        if url.path == "/api/settings":
            try:
                state = retention_state()
            except sqlite3.Error:
                logging.exception("Instellingen konden niet worden gelezen")
                self.send_json_error(500, "De instellingen konden niet worden gelezen.")
                return
            self.reply(json.dumps(state).encode(), "application/json")
            return
        if url.path == "/api/export.csv":
            query = {key: values[0] for key, values in parse_qs(url.query).items()}
            period = query.get("period", "day")
            kind = query.get("kind", "host")
            try:
                day = date.fromisoformat(query.get("date", datetime.now(ZONE).date().isoformat()))
                if period not in PERIODS or kind not in KINDS:
                    raise ValueError
                body = export_csv(day, period, kind, query.get("source")).encode("utf-8")
            except (ValueError, OverflowError):
                self.send_error(400)
                return
            except sqlite3.Error:
                logging.exception("CSV-export is mislukt")
                self.send_error(500, "Export failed")
                return
            self.reply(body, "text/csv; charset=utf-8",
                       filename=f"ha-bandwidth-{kind}-{period}-{day.isoformat()}.csv")
            return
        if url.path == "/api/traffic":
            query = {key: values[0] for key, values in parse_qs(url.query).items()}
            period = query.get("period", "day")
            kind = query.get("kind", "host")
            try:
                day = date.fromisoformat(query.get("date", datetime.now(ZONE).date().isoformat()))
                if period not in PERIODS or kind not in KINDS:
                    raise ValueError
                data = report(day, period, kind, query.get("source"))
            except (ValueError, OverflowError):
                self.send_error(400)
                return
            self.reply(json.dumps(data).encode(), "application/json")
            return
        asset = STATIC_ASSETS.get(url.path)
        if asset is None:
            self.send_error(404)
            return
        self.reply(*asset)

    def download_backup(self, previous):
        logging.info("Back-up: download aangevraagd (%s)", "herstelkopie" if previous else "nieuwe back-up")
        with tempfile.TemporaryDirectory(dir=DATA) as directory:
            target = Path(directory) / "bandwidth.sqlite3"
            try:
                if previous:
                    with BACKUP_LOCK:
                        if not PREVIOUS_BACKUP.exists():
                            logging.warning("Back-up: geen herstelkopie beschikbaar")
                            self.send_error(404, "No previous backup")
                            return
                        shutil.copyfile(PREVIOUS_BACKUP, target)
                else:
                    with closing(database()) as connection:
                        snapshot(connection, target)
            except (OSError, sqlite3.Error):
                logging.exception("Back-up maken is mislukt")
                self.send_error(500, "Backup failed")
                return
            tag = "voor-herstel" if previous else datetime.now(ZONE).strftime("%Y-%m-%d-%H%M%S")
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(target.stat().st_size))
            self.send_header("Content-Disposition", f'attachment; filename="ha-bandwidth-{tag}.sqlite3"')
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            with target.open("rb") as source:
                try:
                    while chunk := source.read(64 * 1024):
                        self.wfile.write(chunk)
                except OSError:
                    logging.warning("Back-up: download afgebroken")
                    return
            logging.info("Back-up: %s verzonden (%s bytes)", tag, target.stat().st_size)

    def do_POST(self):
        path = urlsplit(self.path).path
        # Een eigen header dwingt een CORS-preflight af, zodat andere websites hier niet naartoe kunnen posten.
        change = {"/api/settings": change_retention, "/api/settings/budget": calibrate_budget,
                  "/api/settings/budget-config": change_budget,
                  "/api/settings/hourly": change_hourly}.get(path)
        header = "X-HA-Bandwidth-Settings" if change else "X-HA-Bandwidth-Restore"
        if self.client_address[0] != "172.30.32.2" or self.headers.get(header) != "1":
            self.send_error(403)
            return
        if change:
            self.save_settings(change)
            return
        action = re.fullmatch(r"/api/backup/scheduled/(restore|delete)/([^/]+)", path)
        if action and BACKUP_NAME.fullmatch(action[2]):
            self.manage_backup(action[1], action[2])
            return
        if path != "/api/backup/restore":
            self.send_error(404)
            return
        self.connection.settimeout(30)
        logging.info("Herstel: upload gestart")
        try:
            with tempfile.TemporaryDirectory(dir=DATA) as directory:
                target = Path(directory) / "upload.sqlite3"
                with target.open("wb") as file:
                    self.receive_backup(file)
                with BACKUP_LOCK, closing(database()) as connection:
                    rescue = Path(directory) / "pre-restore.sqlite3"
                    restore(connection, target, rescue, PREVIOUS_BACKUP)
        except (ValueError, sqlite3.DatabaseError) as error:
            logging.warning("Back-up niet hersteld: %s", error)
            message = str(error) if isinstance(error, ValueError) else "Dit bestand kon niet worden teruggezet als SQLite-back-up."
            self.send_json_error(400, message)
            return
        except OSError:
            logging.exception("Back-up terugzetten is mislukt")
            self.send_json_error(500, "Het terugzetten of opslaan van de herstelkopie is mislukt.")
            return
        logging.info("Herstel: database teruggezet; eerdere database bewaard als herstelkopie")
        self.reply(b'{"ok":true}', "application/json")

    def save_settings(self, change):
        try:
            length = int(self.headers.get("Content-Length", ""))
            if not 0 < length <= 1024 or self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                raise ValueError
            self.connection.settimeout(10)
            body = json.loads(self.rfile.read(length))
        except (ValueError, OSError):
            self.send_json_error(400, "Ongeldig verzoek.")
            return
        try:
            status, answer = change(body)
        except (OSError, sqlite3.Error):
            logging.exception("Instellingen konden niet worden opgeslagen")
            self.send_json_error(500, "De instelling kon niet worden opgeslagen. Bekijk het app-logboek.")
            return
        self.reply(json.dumps(answer).encode(), "application/json", code=status)

    def manage_backup(self, action, name):
        target = BACKUP_DIR / name
        try:
            with BACKUP_LOCK:
                if not target.is_file():
                    self.send_json_error(404, "Deze back-up is niet meer beschikbaar.")
                    return
                if action == "delete":
                    target.unlink()
                else:
                    with tempfile.TemporaryDirectory(dir=DATA) as directory, closing(database()) as connection:
                        restore(connection, target, Path(directory) / "pre-restore.sqlite3", PREVIOUS_BACKUP)
        except (ValueError, sqlite3.Error, OSError):
            logging.exception("Bewerking van automatische back-up mislukt: %s", name)
            self.send_json_error(500, "De bewerking is mislukt. Bekijk het app-logboek.")
            return
        self.reply(b'{"ok":true}', "application/json")

    def receive_backup(self, file):
        chunked = self.headers.get("Transfer-Encoding", "").lower() == "chunked"
        if not chunked and self.headers.get("Content-Length") is None:
            raise ValueError("Geen back-up ontvangen.")
        remaining = MAX_BACKUP_SIZE

        def copy(count):
            nonlocal remaining
            if count < 0 or count > remaining:
                raise ValueError("De back-up mag maximaal 256 MiB groot zijn.")
            remaining -= count
            while count:
                data = self.rfile.read(min(count, 65536))
                if not data:
                    raise ValueError("De upload is voortijdig afgebroken.")
                file.write(data)
                count -= len(data)

        if chunked:
            while True:
                header = self.rfile.readline(128)
                if not header.endswith(b"\r\n"):
                    raise ValueError("De upload is onvolledig.")
                count = int(header.split(b";", 1)[0], 16)
                if count == 0:
                    break
                copy(count)
                if self.rfile.read(2) != b"\r\n":
                    raise ValueError("De upload is onvolledig.")
        else:
            copy(int(self.headers["Content-Length"]))
        if remaining == MAX_BACKUP_SIZE:
            raise ValueError("Het back-upbestand is leeg.")

    def send_json_error(self, code, message):
        self.reply(json.dumps({"error": message}).encode(), "application/json", code)

    def reply(self, content, content_type, code=200, filename=None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    DATA.mkdir(parents=True, exist_ok=True)
    handlers = [logging.StreamHandler()]
    try:
        handlers.append(RotatingFileHandler(DATA / "ha-bandwidth.log", maxBytes=1024 * 1024, backupCount=3, encoding="utf-8"))
    except OSError:
        pass
    logging.Formatter.converter = time.gmtime
    logging.basicConfig(level=logging.INFO, format="%(asctime)sZ %(levelname)s %(message)s",
                        datefmt="%Y-%m-%dT%H:%M:%S", handlers=handlers)
    if len(handlers) == 1:
        logging.warning("Logbestand niet beschikbaar; Home Assistant Logboek blijft actief")
    version_line = next(line for line in (ROOT / "config.yaml").read_text().splitlines() if line.startswith("version:"))
    version = version_line.partition(":")[2].strip().strip('"')
    marker = DATA / "last-version"
    try:
        previous_version = marker.read_text().strip() if marker.exists() else ""
        if previous_version and previous_version != version:
            logging.info("Versiewissel: %s → %s", previous_version, version)
        marker.write_text(version)
    except OSError:
        logging.warning("Kon de vorige appversie niet lezen of bijwerken")
    initialize()
    apply_app_settings()
    try:
        LIVE.restore(load_alerts())
    except sqlite3.Error:
        logging.exception("Bewaarde verkeerspieken konden niet worden gelezen")
    logging.info("HA-Bandwidth %s gestart op poort 63187", version)
    threading.Thread(target=backup_scheduler, daemon=True).start()
    threading.Thread(target=collect, daemon=True).start()
    if SETTINGS.get("create_ha_dashboard", True):
        threading.Thread(target=provision_dashboard, daemon=True).start()
    if SETTINGS.get("publish_to_ha", True):
        threading.Thread(
            target=publish_to_ha,
            args=(database, ZONE, period_bounds, SETTINGS.get("publish_ip_entities", False), DATA / "mqtt-sensors.json",
                  home_assistant_entities),
            daemon=True,
        ).start()
    ThreadingHTTPServer(("0.0.0.0", 63187), Dashboard).serve_forever()

