"""Tests voor kalibratie van het databudget, back-up van verkeerspieken en de kaartdelen in Home Assistant."""
import json
import re
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import closing
from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import budget
import ha_mqtt
import monitor
from storage_backup import restore, snapshot

ZONE = ZoneInfo("Europe/Amsterdam")
ROOT = Path(__file__).resolve().parent
NOW = datetime(2026, 11, 22, 10, tzinfo=ZONE)
BUDGET = {"data_budget_gb": 100, "data_budget_source": "host", "data_budget_reset_day": 1, "data_budget_warn_percent": 80}


class DatabaseCase(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        patcher = patch.object(monitor, "DATA", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        monitor.initialize()

    def add(self, hour, rx, tx=0, kind="host", source="eth0"):
        with closing(monitor.database()) as db, db:
            db.execute("INSERT OR REPLACE INTO traffic VALUES (?, ?, ?, ?, ?, ?)", (hour, kind, source, source, rx, tx))


class CalibrationTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        patcher = patch.dict(monitor.SETTINGS, BUDGET)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.add("2026-11-05T10", 10 * budget.BYTES_PER_GB)

    def test_uncalibrated_status_counts_only_measurements(self):
        status = monitor.budget_status(NOW)
        self.assertEqual((status["used"], status["counted"], status["offset"]), (10e9, 10e9, 0))

    def test_calibration_sets_usage_to_the_provider_reading(self):
        code, status = monitor.calibrate_budget({"used_gb": 37.5}, NOW)
        self.assertEqual(code, 200)
        self.assertEqual((status["used"], status["counted"], status["offset"], status["enabled"]),
                         (37.5e9, 10e9, 27.5e9, True))
        self.assertEqual((status["percent"], status["state"]), (37.5, "ok"))
        self.assertEqual(monitor.budget_status(NOW)["used"], 37.5e9)
        # Nieuwe metingen tellen er gewoon bij op.
        self.add("2026-11-21T10", 2 * budget.BYTES_PER_GB)
        self.assertEqual(monitor.budget_status(NOW)["used"], 39.5e9)

    def test_calibration_can_raise_the_state(self):
        self.assertEqual(monitor.calibrate_budget({"used_gb": 85}, NOW)[1]["state"], "warning")
        self.assertEqual(monitor.calibrate_budget({"used_gb": 100}, NOW)[1]["state"], "exceeded")

    def test_calibration_expires_with_the_cycle(self):
        monitor.calibrate_budget({"used_gb": 37.5}, NOW)
        self.add("2026-12-02T08", 1 * budget.BYTES_PER_GB)
        later = monitor.budget_status(datetime(2026, 12, 2, 10, tzinfo=ZONE))
        self.assertEqual((later["used"], later["offset"]), (1e9, 0))
        # Terug in dezelfde cyclus geldt de correctie nog wel.
        self.assertEqual(monitor.budget_status(NOW)["offset"], 27.5e9)

    def test_provider_below_measured_gives_a_negative_offset_and_never_negative_usage(self):
        status = monitor.calibrate_budget({"used_gb": 4}, NOW)[1]
        self.assertEqual((status["used"], status["offset"]), (4e9, -6e9))
        zero = monitor.calibrate_budget({"used_gb": 0}, NOW)[1]
        self.assertEqual((zero["used"], zero["percent"]), (0, 0.0))
        with patch.object(monitor, "load_app_settings", return_value={"budget_calibration": {
                "cycle_start": "2026-11-01", "offset": -50 * budget.BYTES_PER_GB}}):
            self.assertEqual(monitor.budget_status(NOW)["used"], 0)

    def test_clearing_restores_the_measured_usage(self):
        monitor.calibrate_budget({"used_gb": 37.5}, NOW)
        code, status = monitor.calibrate_budget({"used_gb": None}, NOW)
        self.assertEqual((code, status["used"], status["offset"]), (200, 10e9, 0))
        self.assertNotIn("budget_calibration", monitor.load_app_settings())

    def test_projection_uses_the_calibrated_usage(self):
        now = datetime(2026, 11, 11, 0, tzinfo=ZONE)  # Tien volle dagen van een cyclus van dertig.
        status = monitor.calibrate_budget({"used_gb": 30}, now)[1]
        self.assertEqual((status["projected"], status["projected_percent"]), (90e9, 90.0))

    def test_invalid_values_are_refused_and_change_nothing(self):
        for body in ({"used_gb": float("nan")}, {"used_gb": float("inf")}, {"used_gb": -1}, {"used_gb": True},
                     {"used_gb": "5"}, {"used_gb": [5]}, {"used_gb": 1_000_001}, {}, None, [], "5"):
            code, answer = monitor.calibrate_budget(body, NOW)
            self.assertEqual(code, 400, body)
            self.assertIn("error", answer)
        self.assertFalse(monitor.app_settings_file().exists())
        self.assertEqual(monitor.budget_status(NOW)["offset"], 0)

    def test_refused_while_the_budget_is_off(self):
        with patch.dict(monitor.SETTINGS, {"data_budget_gb": 0}):
            code, answer = monitor.calibrate_budget({"used_gb": 5}, NOW)
        self.assertEqual(code, 400)
        self.assertIn("data_budget_gb", answer["error"])

    def test_calibration_and_retention_do_not_overwrite_each_other(self):
        monitor.calibrate_budget({"used_gb": 37.5}, NOW)
        original = monitor.RETENTION_DAYS
        self.addCleanup(setattr, monitor, "RETENTION_DAYS", original)
        self.assertEqual(monitor.change_retention({"retention_days": 500})[0], 200)
        self.assertEqual(monitor.load_app_settings()["budget_calibration"]["offset"], 27.5e9)
        monitor.calibrate_budget({"used_gb": 40}, NOW)
        self.assertEqual(monitor.load_app_settings()["retention_days"], 500)

    def test_corrupt_calibration_is_ignored(self):
        for calibration in ({"cycle_start": "kapot", "offset": 5}, {"cycle_start": "2026-11-01", "offset": "5"},
                            {"cycle_start": "2026-11-01", "offset": True}, {"cycle_start": "2026-11-01", "offset": 10**16},
                            {"cycle_start": 5, "offset": 5}, {"offset": 5}, "tekst", [1]):
            monitor.app_settings_file().write_text(json.dumps({"budget_calibration": calibration}), encoding="utf-8")
            self.assertNotIn("budget_calibration", monitor.load_app_settings(), calibration)
            self.assertEqual(monitor.budget_status(NOW)["used"], 10e9)

    def test_home_assistant_entity_reports_the_adjustment(self):
        status = monitor.calibrate_budget({"used_gb": 37.5}, NOW)[1]
        entities = {entity["id"]: entity for entity in ha_mqtt.budget_entities(status)}
        self.assertEqual(entities["budget_percent"]["attributes"]["adjustment"], 27.5e9)
        self.assertEqual(entities["budget_percent"]["state"], 37.5)


class CalibrationHttpTests(DatabaseCase):
    GOOD = {"Content-Type": "application/json", "X-HA-Bandwidth-Settings": "1"}

    def setUp(self):
        super().setUp()
        patcher = patch.dict(monitor.SETTINGS, BUDGET)
        patcher.start()
        self.addCleanup(patcher.stop)

        class ViaProxy(monitor.Dashboard):
            client_address = property(lambda self: ("172.30.32.2", 0), lambda self, value: None)

        self.direct = ThreadingHTTPServer(("127.0.0.1", 0), monitor.Dashboard)
        self.proxied = ThreadingHTTPServer(("127.0.0.1", 0), ViaProxy)
        for server in (self.direct, self.proxied):
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)

    def post(self, server, body, headers):
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/api/settings/budget",
                                         data=json.dumps(body).encode(), method="POST", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, None

    def test_calibration_over_http_is_guarded(self):
        self.assertEqual(self.post(self.direct, {"used_gb": 5}, self.GOOD)[0], 403)
        self.assertEqual(self.post(self.proxied, {"used_gb": 5}, {"Content-Type": "application/json"})[0], 403)
        restore_header = {"Content-Type": "application/json", "X-HA-Bandwidth-Restore": "1"}
        self.assertEqual(self.post(self.proxied, {"used_gb": 5}, restore_header)[0], 403)
        self.assertEqual(self.post(self.proxied, {"used_gb": -5}, self.GOOD)[0], 400)
        code, status = self.post(self.proxied, {"used_gb": 5}, self.GOOD)
        self.assertEqual((code, status["used"], status["offset"]), (200, 5e9, 5e9))
        self.assertEqual(self.post(self.proxied, {"used_gb": None}, self.GOOD)[1]["offset"], 0)


class AlertBackupTests(DatabaseCase):
    SCHEMA = ("CREATE TABLE traffic_alerts (timestamp TEXT NOT NULL, kind TEXT NOT NULL, source TEXT NOT NULL, "
              "label TEXT NOT NULL DEFAULT '', bps INTEGER NOT NULL, baseline_bps INTEGER NOT NULL, "
              "reason TEXT NOT NULL DEFAULT '', interval_start TEXT, leaders TEXT NOT NULL DEFAULT '{}')")

    def alert(self, timestamp, source="aa", **extra):
        return {"timestamp": timestamp, "kind": "device", "source": source, "label": "Telefoon", "bps": 30_000_000,
                "baseline_bps": 1_000_000, "reason": "piek", "interval_start": "2026-11-22T09:59:30+01:00",
                "leaders": {"device": [{"source": source}]}, **extra}

    def incoming(self, name, rows=(), schema=None, traffic=True):
        path = self.root / name
        with closing(sqlite3.connect(path)) as db, db:
            if traffic:
                db.execute("CREATE TABLE traffic (hour, kind, source, label, rx, tx)")
                db.execute("INSERT INTO traffic VALUES ('2026-11-14T12', 'host', 'old', 'Old', 1, 2)")
            db.execute(schema or self.SCHEMA)
            for row in rows:
                db.execute("INSERT INTO traffic_alerts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", row)
        return path

    def restore(self, path):
        with closing(monitor.database()) as db:
            restore(db, path, self.root / "rescue.sqlite3", self.root / "previous.sqlite3")

    def test_alerts_round_trip_through_a_backup(self):
        monitor.store_alerts([self.alert("2026-11-22T10:00:00+01:00"), self.alert("2026-11-22T11:00:00+01:00", "bb")])
        with closing(monitor.database()) as db:
            snapshot(db, self.root / "backup.sqlite3")
        monitor.store_alerts([self.alert("2026-11-23T09:00:00+01:00", "later")])
        self.restore(self.root / "backup.sqlite3")
        alerts = monitor.load_alerts()
        self.assertEqual([a["source"] for a in alerts], ["bb", "aa"], "de latere piek hoort niet in de back-up")
        self.assertEqual(alerts[1]["leaders"]["device"][0]["source"], "aa")
        self.assertEqual(alerts[1]["interval_start"], "2026-11-22T09:59:30+01:00")

    def test_null_interval_start_is_accepted(self):
        row = ("2026-11-22T10:00:00+01:00", "device", "aa", "", 5, 1, "", None, "{}")
        self.restore(self.incoming("null.sqlite3", [row]))
        self.assertIsNone(monitor.load_alerts()[0]["interval_start"])

    def test_old_backup_without_the_table_keeps_current_alerts(self):
        monitor.store_alerts([self.alert("2026-11-22T10:00:00+01:00")])
        legacy = self.root / "legacy.sqlite3"
        with closing(sqlite3.connect(legacy)) as db, db:
            db.execute("CREATE TABLE traffic (hour, kind, source, label, rx, tx)")
            db.execute("INSERT INTO traffic VALUES ('2026-11-14T12', 'host', 'old', 'Old', 1, 2)")
        self.restore(legacy)
        self.assertEqual([a["source"] for a in monitor.load_alerts()], ["aa"])
        with closing(monitor.database()) as db:
            self.assertEqual(db.execute("SELECT source FROM traffic").fetchone()[0], "old")

    def test_invalid_alert_rows_are_refused_and_nothing_changes(self):
        monitor.store_alerts([self.alert("2026-11-22T10:00:00+01:00")])
        good = ("2026-11-22T10:00:00+01:00", "device", "zz", "", 5, 1, "", None, "{}")
        bad_rows = {
            "negatief": good[:4] + (-5, 1) + good[6:],
            "tekst als getal": good[:4] + ("snel", 1) + good[6:],
            "kommagetal": good[:4] + (5.5, 1) + good[6:],  # Een getal in een tekstkolom wordt door SQLite tekst.
            "te lang": good[:3] + ("x" * 251,) + good[4:],
            "leaders te groot": good[:8] + ("x" * 100_001,),
            "leeg veld": good[:1] + (None,) + good[2:],
        }
        for number, (name, row) in enumerate(bad_rows.items()):
            schema = self.SCHEMA.replace(" NOT NULL", "")  # Laat ook NULL-waarden toe om die te kunnen controleren.
            path = self.incoming(f"bad{number}.sqlite3", [row], schema=schema)
            with self.assertRaises(ValueError, msg=name):
                self.restore(path)
        self.assertEqual([a["source"] for a in monitor.load_alerts()], ["aa"])
        with closing(monitor.database()) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM traffic").fetchone()[0], 0)

    def test_unexpected_columns_are_refused(self):
        schema = self.SCHEMA.replace("leaders TEXT NOT NULL DEFAULT '{}'", "leaders TEXT NOT NULL DEFAULT '{}', extra TEXT")
        path = self.root / "extra.sqlite3"
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE traffic (hour, kind, source, label, rx, tx)")
            db.execute(schema)
        with self.assertRaises(ValueError):
            self.restore(path)

    def test_duplicate_alerts_in_a_file_without_a_primary_key_roll_back(self):
        row = ("2026-11-22T10:00:00+01:00", "device", "aa", "", 5, 1, "", None, "{}")
        path = self.incoming("dup.sqlite3", [row, row])
        monitor.store_alerts([self.alert("2026-11-21T10:00:00+01:00", "keep")])
        with self.assertRaises(sqlite3.DatabaseError):
            self.restore(path)
        self.assertEqual([a["source"] for a in monitor.load_alerts()], ["keep"])


class CardPartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.card = (ROOT / "lovelace-card.js").read_text(encoding="utf-8")
        cls.html = (ROOT / "dashboard.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "dashboard.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "dashboard.css").read_text(encoding="utf-8")

    def block_keys(self, start):
        block = self.card.split(start, 1)[1].split("\n};", 1)[0]
        return set(re.findall(r"^\s*([a-z-]+): ", block, re.M)) | set(re.findall(r"\b([a-z-]+): \"", block))

    def test_every_card_in_the_templates_is_known_to_the_card_element(self):
        parts, kinds = self.block_keys("const sections = {"), self.block_keys("const kinds = {")
        for name in ("lovelace.json", "lovelace-legacy.json"):
            config = json.loads((ROOT / name).read_text(encoding="utf-8"))
            for view in config["views"]:
                for card in view.get("cards", []) + [c for s in view.get("sections", []) for c in s["cards"]]:
                    if card.get("type") != "custom:ha-bandwidth-card":
                        continue  # Het oude sjabloon bevat gewone Home Assistant-kaarten.
                    self.assertIn(card["part"], parts, f"{name}: {card}")
                    self.assertIn(card["kind"], kinds, f"{name}: {card}")

    def test_every_selector_of_a_card_part_exists_in_the_page(self):
        ids = set(re.findall(r'\bid="([^"]+)"', self.html))
        classes = {c for value in re.findall(r'\bclass="([^"]+)"', self.html) for c in value.split()}
        block = self.card.split("const selected = {", 1)[1].split("\n};", 1)[0]
        for selector in re.findall(r'"([^"]+)"', block):
            if selector.startswith("#"):
                self.assertIn(selector[1:], ids, selector)
            elif selector.startswith("."):
                self.assertIn(selector[1:], classes, selector)
            else:
                self.assertIn(f"<{selector}", self.html, selector)

    def test_the_budget_has_its_own_card_part(self):
        self.assertIn("budget", self.block_keys("const sections = {"))
        self.assertIn('budget: ["#budget"]', self.card)
        self.assertIn('"budget"]);', self.js.split("const embeddedCards = new Set([", 1)[1].split("\n", 1)[0] + "]);")
        self.assertIn('[data-dashboard-card="budget"]', self.css)
        template = json.loads((ROOT / "lovelace.json").read_text(encoding="utf-8"))
        parts = [c["part"] for v in template["views"] for s in v.get("sections", []) for c in s["cards"]]
        self.assertIn("budget", parts)

    def test_links_set_by_script_are_resolved_against_the_app_address(self):
        """In een Home Assistant-kaart verschilt het paginaadres van het adres van de app."""
        for line in self.js.splitlines():
            if ".href =" in line and "./api/" in line:
                self.assertIn("pageUrl", line, line.strip())


if __name__ == "__main__":
    unittest.main()
