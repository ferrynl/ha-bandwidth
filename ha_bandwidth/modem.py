"""Read cumulative WAN sensors from Home Assistant Core."""

import json
import os
import re
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

UNITS = {"B": 1, "kB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4,
         "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3, "TiB": 1024**4}
ENTITY = re.compile(r"sensor\.[a-z0-9_]+")


def counter_bytes(state, entity):
    attributes = state.get("attributes") or {}
    unit = attributes.get("unit_of_measurement")
    if unit not in UNITS or attributes.get("state_class") == "measurement":
        raise ValueError(f"{entity} moet een cumulatieve datateller zijn met een eenheid zoals B, MB of GiB.")
    try:
        value = Decimal(state.get("state", "unavailable"))
        if not value.is_finite() or not 0 <= value < Decimal(2**63) / UNITS[unit]:
            raise ValueError
        return int(value * UNITS[unit])
    except (InvalidOperation, ValueError):
        raise ValueError(f"{entity} is tijdelijk niet beschikbaar.") from None


def normalize_entity(value, field):
    entity = value.strip().lower()
    if entity and "." not in entity:
        entity = "sensor." + entity
    if not ENTITY.fullmatch(entity):
        raise ValueError(f"{field}: vul alleen het sensor-ID in, bijvoorbeeld sensor.modem_bytes_received.")
    return entity


def read_counter(entity):
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        raise ValueError("De Home Assistant API is niet beschikbaar.")
    request = Request(f"http://supervisor/core/api/states/{entity}", headers={"Authorization": f"Bearer {token}"})
    try:
        with urlopen(request, timeout=4) as response:
            state = json.load(response)
    except HTTPError as error:
        if error.code == 404:
            raise ValueError(f"Sensor {entity} bestaat niet in Home Assistant.") from None
        if error.code in (401, 403):
            raise ValueError(f"Home Assistant weigert toegang tot {entity} (HTTP {error.code}).") from None
        raise ValueError(f"Home Assistant kan {entity} niet uitlezen (HTTP {error.code}).") from None
    except (URLError, TimeoutError):
        raise ValueError(f"Home Assistant API is niet bereikbaar bij uitlezen van {entity}.") from None
    return counter_bytes(state, entity)


def modem_reading(settings):
    download = normalize_entity(settings.get("modem_download_entity", ""), "modem_download_entity")
    upload = normalize_entity(settings.get("modem_upload_entity", ""), "modem_upload_entity")
    if download == upload:
        raise ValueError("Stel twee verschillende cumulatieve tellers voor modemdownload en modemupload in.")
    source = f"{download}/{upload}"
    return source, "modem", source, "Modem/router WAN", read_counter(download), read_counter(upload)



CELLULAR_INTERFACES = {"Cellular WAN 1", "Cellular WAN 2"}


def cellular_counters(data):
    if not isinstance(data, dict):
        raise ValueError("Zyxel gaf geen geldige Traffic_Status-gegevens.")
    interfaces, statistics = data.get("ipIface"), data.get("ipIfaceSt")
    if not isinstance(interfaces, list) or not isinstance(statistics, list) or len(interfaces) != len(statistics):
        raise ValueError("Zyxel-interfacegegevens en tellers komen niet overeen.")
    counters = {}
    for interface, stats in zip(interfaces, statistics):
        if not isinstance(interface, dict):
            continue
        name = interface.get("X_ZYXEL_SrvName")
        if name not in CELLULAR_INTERFACES or interface.get("Name") != "WAN":
            continue
        if name in counters or not isinstance(stats, dict):
            raise ValueError(f"Zyxel geeft ongeldige of dubbele gegevens voor {name}.")
        rx, tx = stats.get("BytesReceived"), stats.get("BytesSent")
        if any(type(value) is not int or not 0 <= value < 2**63 for value in (rx, tx)):
            raise ValueError(f"Zyxel geeft geen geldige bytetellers voor {name}.")
        counters[name] = rx, tx
    if counters.keys() != CELLULAR_INTERFACES:
        raise ValueError("Zyxel Traffic_Status bevat niet beide Cellular WAN-tellers.")
    return counters


class VerifiedRequestOptions(dict):
    def __setitem__(self, key, value):
        # nr7101 sets verify=False before its first request. Retain the app's setting.
        if key != "verify":
            super().__setitem__(key, value)


class DirectZyxel:
    def __init__(self, settings):
        self.settings = settings
        self.router = None

    def readings(self):
        from nr7101 import nr7101
        from requests.exceptions import SSLError, Timeout

        address = self.settings.get("upstream_modem_ip", "").strip()
        if "://" not in address:
            address = "https://" + address
        url = urlsplit(address)
        if (url.scheme != "https" or not url.hostname or url.username is not None
                or url.path not in ("", "/") or url.query or url.fragment):
            raise ValueError("Vul bij upstream_modem_ip het HTTPS-beheeradres van de Zyxel in.")
        username = self.settings.get("zyxel_username", "").strip()
        password = self.settings.get("zyxel_password", "")
        if not username or not password:
            raise ValueError("Vul zyxel_username en zyxel_password in bij de app-configuratie.")
        verify = not self.settings.get("zyxel_allow_unverified_tls", False)
        for attempt in range(2):
            try:
                if self.router is None:
                    options = VerifiedRequestOptions(verify=verify, timeout=5, allow_redirects=False)
                    self.router = nr7101.NR7101(address.rstrip("/"), username, password, options)
                    if not self.router.login() or not self.router.sessionkey:
                        self.router = None
                        raise PermissionError
                data = self.router.get_json_object("Traffic_Status")
                if data is not None:
                    break
            except SSLError:
                self.router = None
                raise ValueError("Het HTTPS-certificaat van de Zyxel wordt niet vertrouwd.") from None
            except Timeout:
                self.router = None
                raise ValueError("De Zyxel-API reageert niet op tijd.") from None
            except PermissionError:
                self.router = None
                raise ValueError("Zyxel-inloggen mislukt. Controleer de modem-inloggegevens.") from None
            except Exception:
                if attempt:
                    self.router = None
                    raise ValueError("De Zyxel-API kon Traffic_Status niet uitlezen.") from None
            self.router = None
        else:
            raise ValueError("De Zyxel-API gaf na opnieuw inloggen geen Traffic_Status terug.")

        return [(name, "modem", f"zyxel:{url.netloc}/{name}", name, rx, tx)
                for name, (rx, tx) in cellular_counters(data).items()]
