"""Read cumulative WAN sensors from Home Assistant Core."""

import json
import os
import re
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
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

