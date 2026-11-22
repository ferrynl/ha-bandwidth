"""Databudget: instellingen, telcyclus en drempels. Geen opslag en geen netwerk."""

from datetime import date, datetime, timedelta

SOURCES = ("modem", "openwrt", "host")
BYTES_PER_GB = 1_000_000_000  # Providers en het dashboard rekenen decimaal.


def _whole(value, default, low, high):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return min(high, max(low, number))


def settings(options):
    """Geef de geldige budgetinstellingen, of None als het budget uit staat."""
    try:
        limit = float(options.get("data_budget_gb") or 0)
    except (TypeError, ValueError):
        return None
    if not 0 < limit < 1e9:  # Sluit 0, negatieve waarden, NaN en oneindig uit.
        return None
    source = options.get("data_budget_source")
    return {
        "limit": round(limit * BYTES_PER_GB),
        "source": source if source in SOURCES else "modem",
        "reset_day": _whole(options.get("data_budget_reset_day"), 1, 1, 28),
        "warn_percent": _whole(options.get("data_budget_warn_percent"), 80, 1, 99),
    }


def cycle_bounds(today, reset_day):
    """Eerste dag van de huidige cyclus en eerste dag van de volgende (exclusief)."""
    year, month = today.year, today.month
    if today.day < reset_day:
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    start = date(year, month, reset_day)
    end = date(year + 1, 1, reset_day) if month == 12 else date(year, month + 1, reset_day)
    return start, end


def status(config, used, now, measured=True):
    """Beoordeel het verbruik in de lopende cyclus. `now` is de lokale tijd."""
    start, end = cycle_bounds(now.date(), config["reset_day"])
    limit = config["limit"]
    percent = used / limit * 100
    state = ("exceeded" if used >= limit
             else "warning" if percent >= config["warn_percent"] else "ok")
    cycle_hours = (end - start).days * 24
    elapsed = (now.replace(tzinfo=None) - datetime.combine(start, datetime.min.time())).total_seconds() / 3600
    # Een verwachting op minder dan een dag aan metingen schommelt te veel om iets te zeggen.
    projected = round(used / elapsed * cycle_hours) if elapsed >= 24 else None
    return {
        "source": config["source"], "limit": limit, "used": used,
        "remaining": max(0, limit - used), "percent": round(percent, 1),
        "warn_percent": config["warn_percent"], "state": state,
        "cycle_start": start.isoformat(), "cycle_end": (end - timedelta(days=1)).isoformat(),
        "days_left": (end - now.date()).days, "measured": measured,
        "projected": projected,
        "projected_percent": None if projected is None else round(projected / limit * 100, 1),
    }
