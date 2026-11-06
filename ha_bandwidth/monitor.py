import concurrent.futures
import http.client
import json
import logging
import os
import socket
import sqlite3
import subprocess
import threading
import time
from contextlib import closing
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from destinations import AppDestinations, PROTOCOLS, bridge_apps

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("BANDWIDTH_DATA", "/data"))
INTERVAL = 30
OPTIONS = DATA / "options.json"
SETTINGS = json.loads(OPTIONS.read_text(encoding="utf-8")) if OPTIONS.exists() else {}
ZONE = ZoneInfo(SETTINGS.get("timezone", "Europe/Amsterdam"))
STATUS = {}
PERIODS = {"day": 13, "week": 10, "month": 10, "year": 7}
KINDS = {"host", "app", "peer"}


def database():
    connection = sqlite3.connect(DATA / "bandwidth.sqlite3", timeout=10)
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


def peer_packet(frame, packet_type):
    # AF_PACKET delivers an Ethernet header and Linux's packet direction.
    if len(frame) < 14 or packet_type == 3:  # PACKET_OTHERHOST
        return None
    protocol = int.from_bytes(frame[12:14], "big")
    offset = 14
    while protocol in (0x8100, 0x88A8) and len(frame) >= offset + 4:
        protocol = int.from_bytes(frame[offset + 2:offset + 4], "big")
        offset += 4
    outgoing = packet_type == 4  # PACKET_OUTGOING
    if protocol == 0x0800 and len(frame) >= offset + 20:
        address = offset + (16 if outgoing else 12)
        peer = socket.inet_ntop(socket.AF_INET, frame[address:address + 4])
        size = int.from_bytes(frame[offset + 2:offset + 4], "big")
    elif protocol == 0x86DD and len(frame) >= offset + 40:
        address = offset + (24 if outgoing else 8)
        peer = socket.inet_ntop(socket.AF_INET6, frame[address:address + 16])
        size = 40 + int.from_bytes(frame[offset + 4:offset + 6], "big")
    else:
        return None
    return peer, size, outgoing


class PeerCapture:
    def __init__(self, interface):
        self.interface = interface
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.peers = {}
        self.error = None
        self.worker = threading.Thread(target=self.capture, daemon=True)
        self.worker.start()

    def capture(self):
        try:
            with socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3)) as sock:
                sock.bind((self.interface, 3))
                sock.settimeout(0.5)
                while not self.stop.is_set():
                    try:
                        frame, address = sock.recvfrom(96)
                    except TimeoutError:
                        continue
                    result = peer_packet(frame, address[2])
                    if result:
                        peer, size, outgoing = result
                        with self.lock:
                            if len(self.peers) >= 512 and peer not in self.peers:
                                peer = "Overige IP-adressen"
                            self.peers.setdefault(peer, [0, 0])[outgoing] += size
        except OSError as error:
            self.error = str(error)
            logging.warning("IP-meting op %s: %s", self.interface, error)

    def drain(self):
        with self.lock:
            rows = [("peer", peer, peer, *counts) for peer, counts in self.peers.items()]
            self.peers.clear()
        return rows

    def close(self):
        self.stop.set()
        self.worker.join(timeout=1)


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
    global STATUS
    previous, capture, last_day = {}, None, None
    app_destinations = AppDestinations()
    track_apps = SETTINGS.get("track_app_destinations", True)
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
            if capture and (interface != capture.interface or capture.error):
                capture.close()
                capture = None
            if interface and capture is None and SETTINGS.get("track_peers", True):
                capture = PeerCapture(interface)
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
            now = datetime.now(ZONE)
            current, rows = deltas(readings, previous)
            previous = current
            if capture:
                rows.extend(capture.drain())
                if capture.error:
                    errors.append(f"IP-meting: {capture.error}")
            try:
                record(now, rows, now.date() != last_day, destinations)
                last_day = now.date()
            except sqlite3.Error as error:
                logging.exception("Meting kon niet worden opgeslagen")
                errors.append(f"Opslag: {error}")
            STATUS = {
                "interface": interface, "updated": now.isoformat(), "errors": errors,
                "shared": shared, "unavailable": unavailable, "zone": ZONE.key,
                "peers_enabled": SETTINGS.get("track_peers", True),
                "app_destinations_enabled": track_apps,
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


def report(day, period, kind, source):
    start, end = period_bounds(day, period)
    bounds = (start.isoformat(), end.isoformat(), kind)
    with closing(database()) as db, db:
        leaders = db.execute("""
            SELECT source, MAX(label) AS label, SUM(rx) AS rx, SUM(tx) AS tx
            FROM traffic WHERE hour >= ? AND hour < ? AND kind = ?
            GROUP BY source ORDER BY SUM(rx + tx) DESC LIMIT 30
        """, bounds).fetchall()
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
        destinations = []
        if kind == "app" and source:
            matching = db.execute("""
                SELECT ip, protocol, port, domain, evidence, SUM(rx) AS rx, SUM(tx) AS tx
                FROM app_destinations WHERE app = ? AND day >= ? AND day < ?
                GROUP BY ip, protocol, port, domain, evidence
                ORDER BY SUM(rx + tx) DESC, ip, protocol, port, domain, evidence LIMIT 101
            """, (source, *bounds[:2])).fetchall()
            for row in matching[:100]:
                item = dict(row)
                number = item["protocol"]
                item["protocol"] = PROTOCOLS.get(number, f"IP-protocol {number}" if number >= 0 else "")
                destinations.append(item)
    return {
        "start": start.isoformat(), "end": (end - timedelta(days=1)).isoformat(),
        "rows": [dict(row) for row in leaders], "buckets": [dict(row) for row in buckets],
        "status": STATUS, "first": first, "destinations": destinations,
        "destinations_truncated": kind == "app" and bool(source) and len(matching) > 100,
    }


class Dashboard(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.client_address[0] != "172.30.32.2":
            self.send_error(403)
            return
        url = urlsplit(self.path)
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

    def reply(self, content, content_type):
        self.send_response(200)
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

