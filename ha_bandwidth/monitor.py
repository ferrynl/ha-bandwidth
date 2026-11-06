import concurrent.futures
import functools
import ipaddress
import http.client
import json
import logging
import os
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
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import ProxyHandler, Request, build_opener
from zoneinfo import ZoneInfo

from destinations import AppDestinations, NetworkCapture, PROTOCOLS, bridge_apps
from modem import modem_reading
from openwrt import NoRedirect, OpenWrt, hosts_by_ip
from storage_backup import MAX_BACKUP_SIZE, restore, snapshot

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("BANDWIDTH_DATA", "/data"))
INTERVAL = 30
OPTIONS = DATA / "options.json"
SETTINGS = json.loads(OPTIONS.read_text(encoding="utf-8")) if OPTIONS.exists() else {}
ZONE = ZoneInfo(SETTINGS.get("timezone", "Europe/Amsterdam"))
STATUS = {}
ROUTER_HOSTS = {}
ROUTER_WIFI = {}
PERIODS = {"day": 13, "week": 10, "month": 10, "year": 7}
KINDS = {"host", "app", "peer", "compare", "device"}
PREVIOUS_BACKUP = DATA / "pre-restore.sqlite3"
BACKUP_LOCK = threading.Lock()
OPENWRT_ENABLED = bool(SETTINGS.get("openwrt_url", "").strip())


def database():
    connection = sqlite3.connect(DATA / "bandwidth.sqlite3", timeout=10, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def initialize():
    DATA.mkdir(parents=True, exist_ok=True)
    with closing(database()) as db, db:
        db.executescript("""
            PRAGMA journal_mode = WAL;
            CREATE TABLE IF NOT EXISTS traffic (
                hour TEXT, kind TEXT, source TEXT, label TEXT,
                rx INTEGER NOT NULL, tx INTEGER NOT NULL,
                PRIMARY KEY (hour, kind, source)
            ) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS app_destinations (
                app TEXT, day TEXT, ip TEXT, protocol INTEGER, port INTEGER, domain TEXT,
                evidence TEXT, rx INTEGER NOT NULL, tx INTEGER NOT NULL,
                PRIMARY KEY (app, day, ip, protocol, port, domain, evidence)
            ) WITHOUT ROWID;
            CREATE INDEX IF NOT EXISTS app_destinations_day ON app_destinations(day);
        """)


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
    rows = []
    for generation, kind, source, label, rx, tx in readings:
        key = (kind, source, generation)
        current[key] = (rx, tx)
        old = previous.get(key)
        if old is not None and rx >= old[0] and tx >= old[1]:
            rows.append((kind, source, label, rx - old[0], tx - old[1]))
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
            cutoff = (now.date() - timedelta(days=399)).isoformat()
            db.execute("DELETE FROM traffic WHERE hour < ?", (cutoff,))
            db.execute("DELETE FROM app_destinations WHERE day < ?", (cutoff,))


def collect():
    global STATUS, ROUTER_HOSTS, ROUTER_WIFI
    previous, capture, last_day = {}, None, None
    app_destinations = AppDestinations()
    track_apps = SETTINGS.get("track_app_destinations", True)
    openwrt = OpenWrt(SETTINGS) if OPENWRT_ENABLED else None
    modem_configured = any(SETTINGS.get(key, "").strip() for key in
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
            router_error = ""
            try:
                if openwrt:
                    readings.append(openwrt.reading())
                elif modem_configured:
                    readings.append(modem_reading(SETTINGS))
            except (OSError, URLError, ValueError, http.client.HTTPException) as error:
                router_error = str(error)
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
            ROUTER_HOSTS = hosts_by_ip(hints, SETTINGS.get("openwrt_url", "")) if openwrt else {}
            wifi = {}
            if openwrt and openwrt.session:
                try:
                    wifi = openwrt.wireless_links()
                except (OSError, ValueError, http.client.HTTPException):
                    pass
            ROUTER_WIFI = wifi
            now = datetime.now(ZONE)
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
            try:
                record(now, rows, now.date() != last_day, destinations + host_destinations)
                last_day = now.date()
            except sqlite3.Error as error:
                logging.exception("Meting kon niet worden opgeslagen")
                errors.append(f"Opslag: {error}")
            STATUS = {
                "interface": interface, "updated": now.isoformat(), "errors": errors,
                "shared": shared, "unavailable": unavailable, "zone": ZONE.key,
                "peers_enabled": SETTINGS.get("track_peers", True),
                "app_destinations_enabled": track_apps,
                "router_configured": OPENWRT_ENABLED or modem_configured, "router_error": router_error,
                "router_device": openwrt.device if openwrt and not router_error else "",
                "device_configured": OPENWRT_ENABLED, "device_error": device_error,
                "host_hints_error": host_hints_error,
            }
            time.sleep(max(0, INTERVAL - (time.monotonic() - started)))


def period_bounds(day, period):
    if period == "day":
        return day, day + timedelta(days=1)
    if period == "week":
        start = day - timedelta(days=day.weekday())
        return start, start + timedelta(days=7)
    if period == "month":
        start = day.replace(day=1)
        return start, (start + timedelta(days=32)).replace(day=1)
    return day.replace(month=1, day=1), date(day.year + 1, 1, 1)


def router_topology(hosts, wifi, router_url):
    devices = {}
    try:
        router = str(ipaddress.ip_address(urlsplit(router_url).hostname))
    except ValueError:
        router = ""
    router_mac = hosts.get(router, {}).get("mac")
    for ip, host in hosts.items():
        mac = host["mac"]
        if ip == router or (router_mac and mac == router_mac):
            continue
        device = devices.setdefault(mac or ip, {"name": host["name"], "ips": [], "ssid": wifi.get(mac, "")})
        device["ips"].append(ip)
    for mac, ssid in wifi.items():
        if mac != router_mac:
            devices.setdefault(mac, {"name": "", "ips": [], "ssid": ssid})
    return [dict(device, source=key) for key, device in devices.items()]


def report(day, period, kind, source):
    router_hosts = ROUTER_HOSTS
    start, end = period_bounds(day, period)
    bounds = (start.isoformat(), end.isoformat(), kind)
    if kind == "compare":
        router_kind = "openwrt" if OPENWRT_ENABLED else "modem"
        with closing(database()) as db:
            rows = db.execute("""
                SELECT substr(hour, 1, ?) AS bucket, kind, SUM(rx) AS rx, SUM(tx) AS tx
                FROM traffic WHERE hour >= ? AND hour < ? AND kind IN ('host', ?)
                GROUP BY bucket, kind ORDER BY bucket
            """, (PERIODS[period], *bounds[:2], router_kind)).fetchall()
            first = db.execute("SELECT MIN(hour) FROM traffic").fetchone()[0]
        return {
            "start": start.isoformat(), "end": (end - timedelta(days=1)).isoformat(),
            "buckets": [dict(row) for row in rows if row["kind"] == "host"],
            "modem_buckets": [dict(row) for row in rows if row["kind"] == router_kind],
            "router_label": "OpenWrt WAN" if OPENWRT_ENABLED or not any(
                SETTINGS.get(key, "").strip() for key in ("modem_download_entity", "modem_upload_entity")
            ) else "WAN via HA-sensoren",
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
        buckets = db.execute(sql + " GROUP BY bucket ORDER BY bucket", params).fetchall()
        first = db.execute("SELECT MIN(hour) FROM traffic").fetchone()[0]
        destinations, matching = [], []
        if kind == "host" or (kind == "app" and source):
            if kind == "host":
                clause = "app = ?" if source else "app GLOB ?"
                owner = "@host:" + (source or "*")
            else:
                clause = "app = ?"
                owner = source
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
    return {
        "start": start.isoformat(), "end": (end - timedelta(days=1)).isoformat(),
        "rows": [
            dict(row, lookup_ip=public_ip(row["source"]), router_host=router_hosts.get(row["source"]))
            if kind == "peer" else dict(row)
            for row in leaders
        ],
        "buckets": [dict(row) for row in buckets],
        "status": STATUS, "first": first, "destinations": destinations,
        "destinations_truncated": len(matching) > 100,
        "topology": router_topology(router_hosts, ROUTER_WIFI, SETTINGS.get("openwrt_url", ""))
                    if kind == "device" else [],
    }


def public_ip(value):
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return None
    if getattr(address, "scope_id", None) or not address.is_global or address.is_multicast or address.is_reserved:
        return None
    return str(address)


@functools.lru_cache(maxsize=512)
def ipinfo_lookup(address, day):
    token = SETTINGS.get("ipinfo_token", "").strip()
    if not token:
        raise ValueError("Vul ipinfo_token in bij HA-Bandwidth → Configuratie.")
    query = urlencode({"token": token})
    opener = build_opener(ProxyHandler({}), NoRedirect())
    request = Request(f"https://api.ipinfo.io/lite/{address}?{query}", headers={"Accept": "application/json"})
    try:
        with opener.open(request, timeout=5) as response:
            data = json.loads(response.read(16384))
    except HTTPError as error:
        if error.code in (401, 403):
            raise ValueError("IPinfo accepteert het ingestelde token niet.") from None
        raise ValueError(f"IPinfo gaf HTTP {error.code}.") from None
    except (OSError, ValueError, http.client.HTTPException):
        raise ValueError("IPinfo is tijdelijk niet bereikbaar.") from None
    if not isinstance(data, dict):
        raise ValueError("IPinfo gaf een onverwacht antwoord.")
    return {key: data[key][:250] for key in ("asn", "as_name", "as_domain")
            if isinstance(data.get(key), str)}


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
                data = ipinfo_lookup(address, datetime.now(ZONE).date())
            except ValueError as error:
                self.send_json_error(400, str(error))
                return
            self.reply(json.dumps(data).encode(), "application/json")
            return
        if url.path == "/api/backup/status":
            self.reply(json.dumps({"previous": PREVIOUS_BACKUP.exists()}).encode(), "application/json")
            return
        if url.path in ("/api/backup", "/api/backup/previous"):
            self.download_backup(url.path.endswith("/previous"))
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
        assets = {
            "/": ("dashboard.html", "text/html; charset=utf-8"),
            "/dashboard.js": ("dashboard.js", "text/javascript; charset=utf-8"),
            "/dashboard.css": ("dashboard.css", "text/css; charset=utf-8"),
        }
        if url.path not in assets:
            self.send_error(404)
            return
        file, content_type = assets[url.path]
        self.reply((ROOT / file).read_bytes(), content_type)

    def download_backup(self, previous):
        with tempfile.TemporaryDirectory(dir=DATA) as directory:
            target = Path(directory) / "bandwidth.sqlite3"
            try:
                if previous:
                    with BACKUP_LOCK:
                        if not PREVIOUS_BACKUP.exists():
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
                shutil.copyfileobj(source, self.wfile)

    def do_POST(self):
        if self.client_address[0] != "172.30.32.2" or self.headers.get("X-HA-Bandwidth-Restore") != "1":
            self.send_error(403)
            return
        if urlsplit(self.path).path != "/api/backup/restore":
            self.send_error(404)
            return
        self.connection.settimeout(30)
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

    def reply(self, content, content_type, code=200):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    initialize()
    threading.Thread(target=collect, daemon=True).start()
    logging.info("HA-Bandwidth gestart op poort 63187")
    ThreadingHTTPServer(("0.0.0.0", 63187), Dashboard).serve_forever()

