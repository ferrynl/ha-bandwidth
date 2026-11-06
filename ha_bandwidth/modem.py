"""Read cumulative WAN sensors from Home Assistant Core."""

import json
import os
import re
from decimal import Decimal, InvalidOperation
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


def read_counter(entity):
    if not ENTITY.fullmatch(entity):
        raise ValueError("Gebruik een sensor-entiteits-ID zoals sensor.modem_bytes_received.")
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        raise ValueError("De Home Assistant API is niet beschikbaar.")
    request = Request(f"http://supervisor/core/api/states/{entity}", headers={"Authorization": f"Bearer {token}"})
    with urlopen(request, timeout=4) as response:
        return counter_bytes(json.load(response), entity)


def modem_reading(settings):
    download = settings.get("modem_download_entity", "").strip()
    upload = settings.get("modem_upload_entity", "").strip()
    if not download or not upload or download == upload:
        raise ValueError("Stel twee verschillende cumulatieve tellers voor modemdownload en modemupload in.")
    source = f"{download}/{upload}"
    return source, "modem", source, "Modem/router WAN", read_counter(download), read_counter(upload)

