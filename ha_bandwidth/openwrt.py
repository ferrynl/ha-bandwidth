"""Read OpenWrt WAN byte counters over authenticated ubus JSON-RPC."""

import ipaddress
import json
import re
from urllib.error import HTTPError, URLError
from datetime import date
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

NULL_SESSION = "0" * 32
INTERFACE = re.compile(r"[a-zA-Z0-9_-]{1,64}")
SESSION = re.compile(r"[0-9a-f]{32}")
MAC = re.compile(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}")


class AccessDenied(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def ubus_url(address):
    url = urlsplit(address.strip())
    if (url.scheme not in ("http", "https") or not url.hostname or url.username is not None
            or url.path not in ("", "/", "/ubus", "/ubus/") or url.query or url.fragment):
        raise ValueError("Gebruik het LAN-adres van OpenWrt, zoals http://192.168.1.1.")
    _ = url.port  # Reject invalid ports before attempting a request.
    return urlunsplit((url.scheme, url.netloc, "/ubus", "", ""))


class OpenWrt:
    def __init__(self, settings):
        self.settings = settings
        self.session = ""
        self.opener = build_opener(ProxyHandler({}), NoRedirect())
        self.device = ""
        self.uptime = None
        self.generation = 0

    def call(self, url, session, obj, method, params):
        payload = {"jsonrpc": "2.0", "id": 1, "method": "call", "params": [session, obj, method, params]}
        request = Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=4) as response:
                data = json.loads(response.read(65537))
        except HTTPError as error:
            if error.code == 404:
                raise ValueError("OpenWrt /ubus ontbreekt. Controleer uhttpd-mod-ubus op de router.") from None
            if 300 <= error.code < 400:
                raise ValueError("OpenWrt stuurt een omleiding. Gebruik het rechtstreekse http- of https-adres.") from None
            raise ValueError(f"OpenWrt /ubus antwoordt met HTTP {error.code}.") from None
        except (URLError, TimeoutError):
            raise ValueError("OpenWrt /ubus is niet bereikbaar. Controleer het LAN-adres en HTTPS-certificaat.") from None
        except (ValueError, UnicodeError):
            raise ValueError("OpenWrt /ubus gaf geen geldig JSON-antwoord.") from None
        if not isinstance(data, dict):
            raise ValueError("OpenWrt /ubus gaf een onverwacht antwoord.")
        error = data.get("error")
        result = data.get("result")
        if ((isinstance(error, dict) and error.get("code") in (-32002, -32006))
                or (isinstance(result, list) and result and result[0] == 6)):
            raise AccessDenied("OpenWrt weigert toegang. Controleer de inloggegevens en leesrechten voor ubus.")
        if not isinstance(result, list) or len(result) < 2 or result[0] != 0 or not isinstance(result[1], dict):
            code = result[0] if isinstance(result, list) and result and isinstance(result[0], int) else "onbekend"
            raise ValueError(f"OpenWrt kan {obj}.{method} niet uitlezen (ubus {code}). Controleer de WAN-interface.")
        return result[1]

    def login(self, url):
        user = self.settings.get("openwrt_username", "root").strip()
        password = self.settings.get("openwrt_password", "")
        if not user or not password:
            raise ValueError("Vul de gebruikersnaam en het wachtwoord van OpenWrt in.")
        result = self.call(url, NULL_SESSION, "session", "login", {"username": user, "password": password})
        session = result.get("ubus_rpc_session", "")
        if not isinstance(session, str) or not SESSION.fullmatch(session) or session == NULL_SESSION:
            raise ValueError("OpenWrt heeft geen geldige ubus-sessie teruggegeven.")
        self.session = session

    def counters(self, url, interface):
        status = self.call(url, self.session, f"network.interface.{interface}", "status", {})
        device = status.get("l3_device") or status.get("device")
        if not status.get("up") or not isinstance(device, str) or not device:
            raise ValueError(f"De OpenWrt-interface {interface} is niet actief.")
        details = self.call(url, self.session, "network.device", "status", {"name": device})
        statistics = details.get("statistics") or {}
        rx, tx = statistics.get("rx_bytes"), statistics.get("tx_bytes")
        if any(type(value) is not int or not 0 <= value < 2**63 for value in (rx, tx)):
            raise ValueError(f"OpenWrt geeft geen geldige bytetellers voor {device}.")
        uptime = status.get("uptime")
        if device != self.device or (type(uptime) is int and self.uptime is not None and uptime < self.uptime):
            self.generation += 1
        self.device = device
        self.uptime = uptime if type(uptime) is int else None
        source = f"{url}#{interface}"
        return str(self.generation), "openwrt", source, f"OpenWrt WAN ({interface})", rx, tx

    def nlbw_query(self, *arguments):
        url = ubus_url(self.settings.get("openwrt_url", ""))
        endpoint = urlsplit(url)._replace(path="/cgi-bin/cgi-exec").geturl()
        form = urlencode({
            "sessionid": self.session,
            "command": " ".join(("/usr/libexec/nlbwmon-action", *arguments)),
            "stderr": 0,
        })
        request = Request(endpoint, data=form.encode(), headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with self.opener.open(request, timeout=5) as response:
                data = json.loads(response.read(4 * 1024 * 1024 + 1))
        except HTTPError as error:
            if error.code == 403:
                raise ValueError("OpenWrt weigert toegang tot de Bandwidth Monitor. Controleer het pakket en de leesrechten.") from None
            raise ValueError("OpenWrt Bandwidth Monitor is niet beschikbaar. Controleer luci-app-nlbwmon.") from None
        except (OSError, ValueError):
            raise ValueError("Geen geldige meting van OpenWrt Bandwidth Monitor. Controleer of nlbwmon draait.") from None
        if not isinstance(data, dict):
            raise ValueError("OpenWrt Bandwidth Monitor gaf een onverwacht antwoord.")
        return data

    def host_hints(self):
        url = ubus_url(self.settings.get("openwrt_url", ""))
        return self.call(url, self.session, "luci-rpc", "getHostHints", {})

    def wireless_links(self, bridge_ports=None):
        url = ubus_url(self.settings.get("openwrt_url", ""))

        def optional(obj, method, params):
            try:
                return self.call(url, self.session, obj, method, params)
            except (OSError, ValueError):
                return {}

        radios = optional("network.wireless", "status", {})
        interfaces = {}
        for radio in radios.values():
            for interface in radio.get("interfaces", []):
                config = interface.get("config") or {}
                name = interface.get("ifname")
                if name and INTERFACE.fullmatch(name) and config.get("mode") in (None, "ap"):
                    interfaces[name] = (config.get("ssid"), (radio.get("config") or {}).get("band"))
        for name in set((bridge_ports or {}).values()):
            if re.fullmatch(r"(?:wl|wlan|phy)[a-zA-Z0-9_-]*-(?:ap|mesh)[0-9]+", name):
                interfaces.setdefault(name, (None, None))
        for name in optional("iwinfo", "devices", {}).get("devices", []):
            if isinstance(name, str) and INTERFACE.fullmatch(name):
                interfaces.setdefault(name, (None, None))

        bridge_ports = bridge_ports or {}
        links, direct = {}, {}
        for name, (ssid, band) in interfaces.items():
            params = {"device": name}
            info = optional("iwinfo", "info", params)
            mode = info.get("mode")
            mesh = mode in ("Mesh Point", "Mesh") or bool(re.search(r"-mesh[0-9]+$", name))
            if not mesh and mode not in (None, "Master", "AP"):
                continue
            hostapd = {} if mesh else optional(f"hostapd.{name}", "get_clients", {})
            freq = info.get("frequency") or hostapd.get("freq")
            if isinstance(freq, int):
                if 2400 <= freq < 2500:
                    band = "2g"
                elif 4900 <= freq < 5925:
                    band = "5g"
                elif 5925 <= freq < 7125:
                    band = "6g"
            label = {"2g": "Wifi 2,4 GHz", "5g": "Wifi 5 GHz", "6g": "Wifi 6 GHz"}.get(band, "Wifi · band onbekend")
            ssid = info.get("ssid") or ssid or ""
            if mesh:
                label = "Via mesh"
            details = {"connection": label, "ssid": ssid, "port": name}
            for mac, port in bridge_ports.items():
                if port == name:
                    links[mac] = details
            stations = [] if mesh else optional("iwinfo", "assoclist", params).get("results", [])
            macs = [station.get("mac", "") for station in stations if isinstance(station, dict)]
            macs.extend(mac for mac, client in hostapd.get("clients", {}).items() if client.get("assoc") is not False)
            for mac in macs:
                if isinstance(mac, str) and MAC.fullmatch(mac.lower()):
                    direct[mac.lower()] = details
        return {**links, **direct}

    def bridge_ports(self):
        url = ubus_url(self.settings.get("openwrt_url", ""))
        result = self.call(url, self.session, "file", "exec", {
            "command": "/usr/sbin/bridge", "params": ["-j", "fdb", "show"],
        })
        if result.get("code") != 0:
            raise ValueError("bridge fdb show kon niet worden uitgevoerd; controleer ip-bridge en rpcd-rechten.")
        ports = {}
        for row in json.loads(result.get("stdout", "[]")):
            mac = str(row.get("mac", "")).lower()
            port = str(row.get("ifname") or row.get("dev") or "")
            if (MAC.fullmatch(mac) and not (int(mac[:2], 16) & 1) and INTERFACE.fullmatch(port)
                    and row.get("master") and row.get("state") not in ("permanent", "static")
                    and "self" not in row.get("flags", [])):
                ports.setdefault(mac, set()).add(port)
        return {mac: next(iter(names)) for mac, names in ports.items() if len(names) == 1}

    def connection_links(self):
        bridge_error = ""
        try:
            ports = self.bridge_ports()
        except AccessDenied:
            ports = {}
            bridge_error = "Routeraccount mag file.exec voor /usr/sbin/bridge -j fdb show niet uitvoeren."
        except (OSError, ValueError) as error:
            ports = {}
            bridge_error = str(error)
        links = {mac: {"connection": "Via LAN-poort", "port": port}
                 for mac, port in ports.items() if re.fullmatch(r"lan[0-9]+", port)}
        links.update(self.wireless_links(ports))
        return links, bridge_error

    def device_readings(self, hints):
        periods = self.nlbw_query("periods").get("periods")
        if not isinstance(periods, list) or not periods:
            raise ValueError("OpenWrt Bandwidth Monitor heeft nog geen meetperiode.")
        period = max(date.fromisoformat(value).isoformat() for value in periods if isinstance(value, str))
        data = self.nlbw_query("download", "-g", "mac,ip")
        return device_counters(data, hints, period)

    def reading(self):
        url = ubus_url(self.settings.get("openwrt_url", ""))
        interface = self.settings.get("openwrt_interface", "wan").strip()
        if not INTERFACE.fullmatch(interface):
            raise ValueError("Vul de logische OpenWrt-interface in, meestal wan.")
        if not self.session:
            self.login(url)
            return self.counters(url, interface)
        try:
            return self.counters(url, interface)
        except AccessDenied:
            self.session = ""
            self.login(url)
            return self.counters(url, interface)



def hosts_by_ip(hints, router_url):
    addresses = {}
    conflicts = set()
    for raw_mac, info in hints.items():
        mac = raw_mac.lower()
        if not MAC.fullmatch(mac) or mac == "00:00:00:00:00:00" or not isinstance(info, dict):
            continue
        name = info.get("name")
        name = name.strip()[:120] if isinstance(name, str) else ""
        for field in ("ipaddrs", "ip6addrs"):
            values = info.get(field)
            if not isinstance(values, list):
                continue
            for value in values:
                if not isinstance(value, str):
                    continue
                try:
                    ip = ipaddress.ip_address(value)
                except ValueError:
                    continue
                if ip.is_unspecified or ip.is_multicast or getattr(ip, "scope_id", None):
                    continue
                key = str(ip)
                if key in addresses and addresses[key]["mac"] != mac:
                    conflicts.add(key)
                addresses[key] = {"name": name, "mac": mac}
    for key in conflicts:
        addresses.pop(key, None)
    try:
        router = str(ipaddress.ip_address(urlsplit(router_url.strip()).hostname))
    except ValueError:
        pass
    else:
        device = addresses.setdefault(router, {"name": "", "mac": ""})
        if not device["name"]:
            device["name"] = "OpenWrt-router"
    return addresses


def device_counters(data, hints, period):
    columns, rows = data.get("columns"), data.get("data")
    if not isinstance(columns, list) or not isinstance(rows, list):
        raise ValueError("OpenWrt Bandwidth Monitor gaf geen apparaattellers.")
    try:
        indices = [columns.index(key) for key in ("mac", "ip", "rx_bytes", "tx_bytes")]
    except ValueError:
        raise ValueError("OpenWrt Bandwidth Monitor mist de MAC-, IP- of bytetellers.") from None
    devices = {}
    hints = {key.lower(): value for key, value in hints.items()}
    for row in rows:
        if not isinstance(row, list) or len(row) <= max(indices):
            continue
        mac, ip, rx, tx = (row[index] for index in indices)
        if any(type(count) is not int or not 0 <= count < 2**63 for count in (rx, tx)):
            continue
        try:
            address = ipaddress.ip_address(ip) if isinstance(ip, str) else None
        except ValueError:
            address = None
        mac = mac.lower() if isinstance(mac, str) else ""
        if MAC.fullmatch(mac) and mac != "00:00:00:00:00:00":
            source = mac
        elif address and not address.is_unspecified:
            source = str(address)
        else:
            continue
        totals, addresses = devices.setdefault(source, ([0, 0], set()))
        totals[0] += rx
        totals[1] += tx
        if address and not address.is_unspecified:
            addresses.add(address)
    readings = []
    for source, ((rx, tx), addresses) in devices.items():
        hint = hints.get(source)
        name = hint.get("name") if isinstance(hint, dict) else None
        name = name.strip()[:120] if isinstance(name, str) and name.strip() else source
        ip = str(min(addresses, key=lambda address: (address.version, int(address)))) if addresses else ""
        label = f"{name} · {ip}" if ip and ip != name else name
        readings.append((period, "device", source, label, rx, tx))
    return readings
