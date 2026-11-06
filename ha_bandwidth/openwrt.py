"""Read OpenWrt WAN byte counters over authenticated ubus JSON-RPC."""

import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

NULL_SESSION = "0" * 32
INTERFACE = re.compile(r"[a-zA-Z0-9_-]{1,64}")
SESSION = re.compile(r"[0-9a-f]{32}")


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

