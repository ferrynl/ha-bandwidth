"""Tests voor de bewaartijd, de CSV-export en de volgorde van de kaarten in het dashboard."""
import csv
import io
import re
import tempfile
import unittest
from contextlib import closing
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import monitor

ZONE = ZoneInfo("Europe/Amsterdam")
ROOT = Path(__file__).resolve().parent


class DatabaseCase(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patcher = patch.object(monitor, "DATA", Path(folder.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        monitor.initialize()

    def add(self, hour, rx, tx=0, kind="host", source="eth0", label=None):
        with closing(monitor.database()) as db, db:
            db.execute("INSERT OR REPLACE INTO traffic VALUES (?, ?, ?, ?, ?, ?)",
                       (hour, kind, source, source if label is None else label, rx, tx))

    def hours(self):
        with closing(monitor.database()) as db:
            return [row[0] for row in db.execute("SELECT hour FROM traffic ORDER BY hour")]


class RetentionTests(DatabaseCase):
    def test_option_is_clamped_and_defaults_to_400(self):
        self.assertEqual(monitor.retention_days({}), 400)
        self.assertEqual(monitor.retention_days({"retention_days": "x"}), 400)
        self.assertEqual(monitor.retention_days({"retention_days": None}), 400)
        self.assertEqual(monitor.retention_days({"retention_days": 5}), 30)
        self.assertEqual(monitor.retention_days({"retention_days": 99999}), 3650)
        self.assertEqual(monitor.retention_days({"retention_days": "90"}), 90)

    def prune_with(self, days):
        now = datetime(2026, 11, 22, 10, tzinfo=ZONE)
        self.add("2026-08-24T10", 1)  # 90 dagen geleden.
        self.add("2026-08-23T10", 1)  # 91 dagen geleden.
        self.add("2025-10-18T10", 1)  # 400 dagen geleden: valt buiten 400 kalenderdagen.
        self.add("2025-10-19T10", 1)  # 399 dagen geleden: de oudste dag die blijft.
        self.add("2026-11-22T09", 1)
        with patch.object(monitor, "RETENTION_DAYS", days):
            monitor.record(now, [], True)
        return self.hours()

    def test_default_keeps_exactly_400_calendar_days(self):
        self.assertEqual(self.prune_with(400), ["2025-10-19T10", "2026-08-23T10", "2026-08-24T10", "2026-11-22T09"])

    def test_shorter_retention_deletes_older_measurements(self):
        # 90 dagen: vandaag en de 89 dagen daarvoor, dus vanaf 2026-08-25.
        self.assertEqual(self.prune_with(90), ["2026-11-22T09"])
        self.assertEqual(self.prune_with(91), ["2026-08-24T10", "2026-11-22T09"])

    def test_alerts_and_destinations_follow_the_same_cutoff(self):
        with closing(monitor.database()) as db, db:
            db.execute("INSERT INTO traffic_alerts (timestamp, kind, source, bps, baseline_bps) VALUES "
                       "('2026-01-01T10:00:00+01:00', 'device', 'a', 1, 1), "
                       "('2026-11-20T10:00:00+01:00', 'device', 'b', 1, 1)")
        with patch.object(monitor, "RETENTION_DAYS", 60):
            monitor.record(datetime(2026, 11, 22, 10, tzinfo=ZONE), [], True)
        self.assertEqual([alert["source"] for alert in monitor.load_alerts()], ["b"])


class ExportTests(DatabaseCase):
    def parse(self, text):
        self.assertTrue(text.startswith("﻿"), "met BOM voor Excel")
        return list(csv.reader(io.StringIO(text[1:])))

    def test_header_and_buckets_follow_the_period(self):
        self.add("2026-11-22T09", 100, 10, source="aa", label="Telefoon")
        self.add("2026-11-22T10", 200, 20, source="aa", label="Telefoon")
        self.add("2026-11-22T10", 5, 1, source="bb", label="Laptop")
        self.add("2026-11-23T00", 999, kind="host", source="aa")  # Andere dag.
        self.add("2026-11-22T10", 777, kind="app", source="aa")   # Andere bron.
        rows = self.parse(monitor.export_csv(date(2026, 11, 22), "day", "host", None))
        self.assertEqual(rows[0], list(monitor.CSV_COLUMNS))
        self.assertEqual(rows[1:], [["2026-11-22T09", "host", "aa", "Telefoon", "100", "10", "110"],
                                    ["2026-11-22T10", "host", "aa", "Telefoon", "200", "20", "220"],
                                    ["2026-11-22T10", "host", "bb", "Laptop", "5", "1", "6"]])

    def test_week_is_aggregated_per_day_and_year_per_month(self):
        self.add("2026-11-22T09", 1, 1)
        self.add("2026-11-22T10", 2, 2)
        self.add("2026-11-16T10", 4, 4)
        week = self.parse(monitor.export_csv(date(2026, 11, 22), "week", "host", None))
        self.assertEqual([(row[0], row[6]) for row in week[1:]], [("2026-11-16", "8"), ("2026-11-22", "6")])
        year = self.parse(monitor.export_csv(date(2026, 11, 22), "year", "host", None))
        self.assertEqual([(row[0], row[6]) for row in year[1:]], [("2026-11", "14")])

    def test_source_filter_and_compare_kinds(self):
        self.add("2026-11-22T09", 1, kind="host", source="eth0")
        self.add("2026-11-22T09", 2, kind="openwrt", source="wan")
        self.add("2026-11-22T09", 4, kind="modem", source="cell")
        self.add("2026-11-22T09", 8, kind="app", source="x")
        compare = self.parse(monitor.export_csv(date(2026, 11, 22), "day", "compare", None))
        self.assertEqual([row[1] for row in compare[1:]], ["host", "modem", "openwrt"])
        only = self.parse(monitor.export_csv(date(2026, 11, 22), "day", "compare", "wan"))
        self.assertEqual([row[2] for row in only[1:]], ["wan"])

    def test_empty_period_gives_only_the_header(self):
        rows = self.parse(monitor.export_csv(date(2026, 11, 22), "day", "host", None))
        self.assertEqual(rows, [list(monitor.CSV_COLUMNS)])

    def test_names_cannot_inject_spreadsheet_formulas(self):
        for name in ('=HYPERLINK("http://x","klik")', "+1+1", "-2", "@SUM(A1)", "\tx"):
            self.assertTrue(monitor.csv_safe(name).startswith("'"), name)
        self.assertEqual(monitor.csv_safe("Telefoon van Jan"), "Telefoon van Jan")
        self.assertEqual(monitor.csv_safe(None), "")
        self.add("2026-11-22T09", 1, source="aa:bb", label='=cmd|" /C calc"!A0')
        rows = self.parse(monitor.export_csv(date(2026, 11, 22), "day", "host", None))
        self.assertEqual(rows[1][3], '\'=cmd|" /C calc"!A0')

    def test_commas_quotes_and_newlines_stay_in_one_cell(self):
        self.add("2026-11-22T09", 1, source="aa", label='Jan, "de" tv\nkamer')
        rows = self.parse(monitor.export_csv(date(2026, 11, 22), "day", "host", None))
        self.assertEqual(rows[1][3], 'Jan, "de" tv\nkamer')
        self.assertEqual(len(rows[1]), len(monitor.CSV_COLUMNS))


class Outline(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.links = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.append(attrs["id"])
        if tag == "section" and "history" in (attrs.get("class") or "").split():
            self.ids.append("history")
        if tag == "a" and attrs.get("id"):
            self.links[attrs["id"]] = attrs.get("href")


class LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.outline = Outline()
        cls.outline.feed((ROOT / "dashboard.html").read_text(encoding="utf-8"))

    def test_chart_comes_directly_after_the_totals(self):
        ids = self.outline.ids
        order = [ids.index(name) for name in ("totals", "history", "destinations", "ranking-panel")]
        self.assertEqual(order, sorted(order), "totalen, grafiek, bestemmingen, ranglijst")
        between = [name for name in ids[order[0] + 1:order[1]] if name in ("destinations", "ranking-panel", "topology-panel")]
        # Bewuste uitzondering: op het tabblad Apparaten kies je apparaten op de netwerkkaart.
        self.assertEqual(between, ["topology-panel"], "alleen de netwerkkaart staat nog tussen totalen en grafiek")

    def test_every_html_id_is_unique(self):
        ids = self.outline.ids
        self.assertEqual(sorted(name for name in set(ids) if ids.count(name) > 1), [])

    def test_export_link_points_at_the_endpoint(self):
        self.assertEqual(self.outline.links["export-csv"], "./api/export.csv")

    def test_script_only_uses_ids_that_exist(self):
        script = (ROOT / "dashboard.js").read_text(encoding="utf-8")
        used = set(re.findall(r'\bel\("([a-z0-9-]+)"\)', script))
        # Sommige elementen worden door het script zelf gemaakt.
        created = set(re.findall(r'\.id = "([a-z0-9-]+)"', script)) | set(re.findall(r'id="([a-z0-9-]+)"', script))
        missing = sorted(used - set(self.outline.ids) - created)
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
