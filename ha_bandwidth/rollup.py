"""Oude uurmetingen samenvatten tot één meting per dag.

De dagtotalen blijven kloppen: de samenvatting staat op uur 00 van die dag, dus de weergave per dag,
week, maand en jaar en de CSV-export veranderen niet. Alleen de uurweergave van oude dagen toont één blok.
"""

GROUPS = ("SELECT substr(hour, 1, 10) AS day, kind, source, MAX(label) AS label, SUM(rx) AS rx, SUM(tx) AS tx "
          "FROM traffic WHERE hour < ? GROUP BY day, kind, source "
          "HAVING COUNT(*) > 1 OR MIN(hour) != substr(hour, 1, 10) || 'T00'")


def detail_days(db, cutoff_day):
    """Het aantal kalenderdagen vóór `cutoff_day` dat nog uurdetail heeft."""
    return len({row[0] for row in db.execute(GROUPS, (cutoff_day,))})


def summarize(db, cutoff_day):
    """Vat alle uurmetingen van vóór `cutoff_day` (ISO-datum) samen. Geeft het aantal samengevatte dagreeksen terug.

    Binnen de transactie van de aanroeper. Herhalen verandert niets.
    """
    groups = db.execute(GROUPS, (cutoff_day,)).fetchall()
    for day, kind, source, label, rx, tx in groups:
        db.execute("DELETE FROM traffic WHERE hour >= ? AND hour < ? AND kind = ? AND source = ?",
                   (day, day + "U", kind, source))  # "U" sorteert na elk uur ("T..")
        db.execute("INSERT INTO traffic VALUES (?, ?, ?, ?, ?, ?)", (day + "T00", kind, source, label, rx, tx))
    return len(groups)
