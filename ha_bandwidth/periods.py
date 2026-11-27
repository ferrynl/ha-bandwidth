"""Periodegrenzen en de vergelijking met de vorige periode. Geen opslag en geen netwerk."""

from datetime import date, datetime, timedelta


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


def previous_period(day, period, now):
    """Bepaal de vorige periode. Loopt de gekozen periode nog, dan stopt de vorige op hetzelfde moment.

    De uren zijn lokale klokuren, zoals in de tabel `traffic`. Een zomertijdwissel
    verschuift de vergelijking hooguit een uur.
    """
    start, end = period_bounds(day, period)
    before_start, before_end = period_bounds(start - timedelta(days=1), period)
    midnight = datetime.min.time()
    first_hour = datetime.combine(before_start, midnight)
    stop = datetime.combine(before_end, midnight)
    partial = start <= now.date() < end
    if partial:
        this_hour = now.replace(tzinfo=None, minute=0, second=0, microsecond=0) + timedelta(hours=1)
        stop = min(stop, first_hour + (this_hour - datetime.combine(start, midnight)))
    return before_start, before_end, first_hour, stop, partial


def previous_totals(db, day, period, kind, source, now, first):
    before_start, before_end, first_hour, stop, partial = previous_period(day, period, now)
    sql = "SELECT COALESCE(SUM(rx), 0) AS rx, COALESCE(SUM(tx), 0) AS tx, COUNT(*) AS rows " \
          "FROM traffic WHERE hour >= ? AND hour < ? AND kind = ?"
    params = [first_hour.strftime("%Y-%m-%dT%H"), stop.strftime("%Y-%m-%dT%H"), kind]
    if source:
        sql += " AND source = ?"
        params.append(source)
    row = db.execute(sql, params).fetchone()
    # De vorige periode is alleen vergelijkbaar als de metingen er helemaal in vielen.
    comparable = bool(first) and first[:13] <= params[0] and row["rows"] > 0 and row["rx"] + row["tx"] > 0
    return {
        "start": before_start.isoformat(), "end": (before_end - timedelta(days=1)).isoformat(),
        "rx": row["rx"], "tx": row["tx"], "partial": partial, "comparable": comparable,
    }
