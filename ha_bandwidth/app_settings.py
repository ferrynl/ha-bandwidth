"""Instellingen van de pagina Instellingen: lezen, valideren en opslaan.

Geen globale toestand: elke functie krijgt het pad of de opties mee. De database en de klok
zitten er bewust niet in, zodat dit los te testen is.
"""

import json
import math
from datetime import date

from budget import SOURCES

RETENTION_RANGE = (30, 3650)
HOURLY_RANGE = (30, 3650)  # 0 betekent: uurdetail altijd bewaren
BUDGET_LIMIT_MAX = 1_000_000  # gigabyte


def retention_days(options):
    """Het aantal lokale kalenderdagen dat metingen bewaard blijven (30 tot en met 3650, standaard 400)."""
    try:
        days = int(options.get("retention_days", 400))
    except (TypeError, ValueError):
        return 400
    return min(RETENTION_RANGE[1], max(RETENTION_RANGE[0], days))


def whole(value, low, high):
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def number(value, low, high):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and low <= value <= high)


def load(path):
    """Lees de opgeslagen instellingen. Ongeldig of afwezig geeft een lege lijst; ongeldige delen verdwijnen."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    settings = {}
    if whole(data.get("retention_days"), *RETENTION_RANGE):
        settings["retention_days"] = data["retention_days"]
    if data.get("hourly_days") == 0 or whole(data.get("hourly_days"), *HOURLY_RANGE):
        settings["hourly_days"] = data["hourly_days"]
    saved = data.get("budget")
    if isinstance(saved, dict) and clean_budget(saved)[1] is None:
        settings["budget"] = clean_budget(saved)[0]
    calibration = data.get("budget_calibration")
    if isinstance(calibration, dict):
        offset = calibration.get("offset")
        try:
            cycle = date.fromisoformat(calibration["cycle_start"]).isoformat()
        except (KeyError, TypeError, ValueError):
            cycle = None
        if cycle and isinstance(offset, int) and not isinstance(offset, bool) and abs(offset) <= 10**15:
            settings["budget_calibration"] = {"cycle_start": cycle, "offset": offset}
    return settings


def save(path, settings):
    """Schrijf atomair, zodat een onderbreking nooit een half bestand achterlaat."""
    staging = path.with_suffix(".tmp")
    staging.write_text(json.dumps(settings), encoding="utf-8")
    staging.replace(path)


def clean_budget(body):
    """Valideer het budgetformulier. Geeft (waarden, None) of (None, foutmelding) terug."""
    if not isinstance(body, dict):
        return None, "Ongeldige instellingen."
    limit, source = body.get("limit_gb"), body.get("source")
    day, warn = body.get("reset_day"), body.get("warn_percent")
    if not number(limit, 0, BUDGET_LIMIT_MAX):
        return None, "Vul een limiet in van 0 tot en met 1.000.000 gigabyte."
    if source not in SOURCES:
        return None, "Kies een geldige bron."
    if not whole(day, 1, 28):
        return None, "Kies een dag van 1 tot en met 28."
    if not whole(warn, 1, 99):
        return None, "Kies een percentage van 1 tot en met 99."
    return {"limit_gb": limit, "source": source, "reset_day": day, "warn_percent": warn}, None


def clean_used_gb(body):
    """Valideer de kalibratie. Geeft (gigabytes of None om te wissen, foutmelding of None) terug."""
    if not isinstance(body, dict) or "used_gb" not in body:
        return None, "Vul het verbruik in gigabytes in."
    value = body["used_gb"]
    if value is not None and not number(value, 0, BUDGET_LIMIT_MAX):
        return None, "Vul een getal in van 0 tot en met 1.000.000 gigabyte."
    return value, None


def hourly_days(options):
    """Het aantal dagen uurdetail, of 0 om het altijd te bewaren."""
    value = options.get("hourly_days", 0)
    return value if value == 0 or whole(value, *HOURLY_RANGE) else 0


def budget_options(options, saved):
    """De budgetopties: het opgeslagen budget gaat voor op Configuratie."""
    if not saved:
        return options
    return {**options, "data_budget_gb": saved["limit_gb"], "data_budget_source": saved["source"],
            "data_budget_reset_day": saved["reset_day"], "data_budget_warn_percent": saved["warn_percent"]}
