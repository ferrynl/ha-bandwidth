"""IPinfo Lite: publieke adressen herkennen en opzoeken."""

import http.client
import ipaddress
import json
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

from openwrt import NoRedirect


def public_ip(value):
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return None
    if getattr(address, "scope_id", None) or not address.is_global or address.is_multicast or address.is_reserved:
        return None
    return str(address)


def stored_ipinfo(db, addresses):
    if not addresses:
        return {}
    placeholders = ", ".join("?" for _ in addresses)
    # De SQL-tekst bestaat uit vaste stukken en één rij vraagtekens; de adressen gaan als parameters mee.
    # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
    rows = db.execute(
        f"SELECT ip, asn, as_name, as_domain FROM ipinfo_cache WHERE ip IN ({placeholders})",
        tuple(addresses),
    )
    return {row["ip"]: {key: row[key] for key in ("asn", "as_name", "as_domain")} for row in rows}


def fetch_ipinfo(token, address):
    """Vraag IPinfo Lite om het ASN van een publiek adres. Raakt de database niet aan."""
    token = (token or "").strip()
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
