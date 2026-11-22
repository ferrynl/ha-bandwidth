"""Tests voor het databudget, de vergelijking met de vorige periode en bewaarde verkeerspieken."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import budget
import ha_mqtt
import monitor
from live_monitor import LiveMonitor

ZONE = ZoneInfo("Europe/Amsterdam")


class BudgetTests(unittest.TestCase):
    def test_cycle_bounds_cross_month_and_year(self):
        self.assertEqual(budget.cycle_bounds(date(2026, 11, 22), 1), (date(2026, 11, 1), date(2026, 12, 1)))
        self.assertEqual(budget.cycle_bounds(date(2026, 11, 22), 22), (date(2026, 11, 22), date(2026, 12, 22)))
        self.assertEqual(budget.cycle_bounds(date(2026, 1, 5), 15), (date(2025, 12, 15), date(2026, 1, 15)))
        self.assertEqual(budget.cycle_bounds(date(2026, 12, 20), 15), (date(2026, 12, 15), date(2027, 1, 15)))
        self.assertEqual(budget.cycle_bounds(date(2026, 3, 10), 28), (date(2026, 2, 28), date(2026, 3, 28)))

    def test_settings_are_off_unless_a_valid_limit_is_set(self):
        for value in (0, None, "", "abc", -5, float("nan"), float("inf")):
            self.assertIsNone(budget.settings({"data_budget_gb": value}), value)
        config = budget.settings({"data_budget_gb": 2.5, "data_budget_source": "bogus",
                                  "data_budget_reset_day": 99, "data_budget_warn_percent": 0})
        self.assertEqual(config, {"limit": 2_500_000_000, "source": "modem", "reset_day": 28, "warn_percent": 1})
        config = budget.settings({"data_budget_gb": 10, "data_budget_source": "openwrt",
                                  "data_budget_reset_day": "7", "data_budget_warn_percent": 90})
        self.assertEqual((config["source"], config["reset_day"], config["warn_percent"]), ("openwrt", 7, 90))

    def test_status_thresholds(self):
        config = budget.settings({"data_budget_gb": 100, "data_budget_warn_percent": 80})
        now = datetime(2026, 11, 22, 10, tzinfo=ZONE)
        low = budget.status(config, 10 * budget.BYTES_PER_GB, now)
        warning = budget.status(config, 80 * budget.BYTES_PER_GB, now)
        exceeded = budget.status(config, 100 * budget.BYTES_PER_GB, now)
        self.assertEqual((low["state"], warning["state"], exceeded["state"]), ("ok", "warning", "exceeded"))
        self.assertEqual(low["percent"], 10.0)
        self.assertEqual(exceeded["remaining"], 0)
        over = budget.status(config, 120 * budget.BYTES_PER_GB, now)
        self.assertEqual((over["remaining"], over["percent"]), (0, 120.0))

    def test_status_cycle_dates_and_projection(self):
        config = budget.settings({"data_budget_gb": 100, "data_budget_reset_day": 1})
        start_of_cycle = budget.status(config, 5, datetime(2026, 11, 1, 12, tzinfo=ZONE))
        self.assertIsNone(start_of_cycle["projected"], "minder dan een dag aan metingen")
        later = budget.status(config, 15 * budget.BYTES_PER_GB, datetime(2026, 11, 11, 0, tzinfo=ZONE))
        self.assertEqual((later["cycle_start"], later["cycle_end"]), ("2026-11-01", "2026-11-30"))
        self.assertEqual(later["days_left"], 20)
        self.assertEqual(later["projected"], 45 * budget.BYTES_PER_GB)  # 10 dagen voor 15 GB, cyclus van 30 dagen.
        self.assertEqual(later["projected_percent"], 45.0)
        last_day = budget.status(config, 1, datetime(2026, 11, 30, 23, tzinfo=ZONE))
        self.assertEqual(last_day["days_left"], 1)


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


class PreviousPeriodTests(DatabaseCase):
    def previous(self, day, period, now, source=None, kind="host"):
        with closing(monitor.database()) as db:
            first = db.execute("SELECT MIN(hour) FROM traffic").fetchone()[0]
            return monitor.previous_totals(db, day, period, kind, source, now, first)

    def test_running_day_is_compared_up_to_the_same_hour(self):
        self.add("2026-11-01T00", 1)
        self.add("2026-11-21T09", 100)
        self.add("2026-11-21T10", 20)
        self.add("2026-11-21T11", 900)  # Na het huidige uur, telt niet mee.
        self.add("2026-11-22T09", 150)
        result = self.previous(date(2026, 11, 22), "day", datetime(2026, 11, 22, 10, 30))
        self.assertEqual((result["rx"], result["partial"], result["comparable"]), (120, True, True))
        self.assertEqual((result["start"], result["end"]), ("2026-11-21", "2026-11-21"))

    def test_finished_day_is_compared_with_the_whole_previous_day(self):
        self.add("2026-11-01T00", 1)
        self.add("2026-11-19T05", 40)
        self.add("2026-11-19T23", 60)
        self.add("2026-11-20T08", 7)
        result = self.previous(date(2026, 11, 20), "day", datetime(2026, 11, 22, 10))
        self.assertEqual((result["rx"], result["partial"], result["comparable"]), (100, False, True))

    def test_running_week_stops_at_the_same_moment(self):
        self.add("2026-11-01T00", 1)
        self.add("2026-11-15T10", 5)  # Zondag 10:00 van de vorige week.
        self.add("2026-11-15T12", 500)  # Pas daarna.
        result = self.previous(date(2026, 11, 22), "week", datetime(2026, 11, 22, 10, 30))
        self.assertEqual((result["rx"], result["start"], result["end"]), (5, "2026-11-09", "2026-11-15"))

    def test_running_month_is_clamped_to_a_shorter_previous_month(self):
        self.add("2026-01-01T00", 1)
        self.add("2026-02-28T23", 70)
        result = self.previous(date(2026, 3, 31), "month", datetime(2026, 3, 31, 12))
        self.assertEqual((result["rx"], result["partial"], result["comparable"]), (70, True, True))

    def test_not_comparable_when_history_starts_inside_the_previous_period(self):
        self.add("2026-11-21T05", 100)
        self.add("2026-11-22T09", 150)
        result = self.previous(date(2026, 11, 22), "day", datetime(2026, 11, 22, 10))
        self.assertFalse(result["comparable"])

    def test_not_comparable_without_measurements_in_the_previous_period(self):
        self.add("2026-11-01T00", 1)
        self.add("2026-11-22T09", 150)
        self.assertFalse(self.previous(date(2026, 11, 22), "day", datetime(2026, 11, 22, 10))["comparable"])
        self.assertFalse(self.previous(date(2026, 11, 22), "day", datetime(2026, 11, 22, 10),
                                       source="onbekend")["comparable"])

    def test_source_filter_and_year(self):
        self.add("2025-01-01T00", 1)
        self.add("2025-06-01T00", 10, source="a")
        self.add("2025-06-01T00", 30, source="b")
        result = self.previous(date(2026, 11, 22), "year", datetime(2026, 11, 22, 10), source="a")
        self.assertEqual((result["rx"], result["comparable"]), (10, True))

    def test_report_contains_previous_totals(self):
        self.add("2026-11-01T00", 1)
        self.add("2026-11-21T09", 100, 20)
        self.add("2026-11-22T09", 150)
        data = monitor.report(date(2026, 11, 22), "day", "host", None, now=datetime(2026, 11, 22, 10, 30))
        self.assertEqual((data["previous"]["rx"], data["previous"]["tx"]), (100, 20))
        self.assertEqual(sum(row["rx"] for row in data["buckets"]), 150)


class BudgetStatusTests(DatabaseCase):
    def test_disabled_by_default(self):
        with patch.dict(monitor.SETTINGS, {}, clear=True):
            self.assertIsNone(monitor.budget_status(datetime(2026, 11, 22, 10, tzinfo=ZONE)))

    def test_counts_only_the_chosen_source_within_the_cycle(self):
        self.add("2026-10-31T23", 5_000_000_000, kind="modem", source="wan")  # Vóór de cyclus.
        self.add("2026-11-03T10", 2_000_000_000, 1_000_000_000, kind="modem", source="wan")
        self.add("2026-11-10T10", 4_000_000_000, kind="host")  # Andere bron.
        settings = {"data_budget_gb": 10, "data_budget_source": "modem", "upstream_modem_name": "Zyxel"}
        with patch.dict(monitor.SETTINGS, settings, clear=True):
            status = monitor.budget_status(datetime(2026, 11, 22, 10, tzinfo=ZONE))
        self.assertEqual((status["used"], status["percent"], status["state"]), (3_000_000_000, 30.0, "ok"))
        self.assertEqual((status["source_label"], status["measured"]), ("Zyxel", True))

    def test_reports_when_the_source_has_no_measurements(self):
        with patch.dict(monitor.SETTINGS, {"data_budget_gb": 10, "data_budget_source": "openwrt"}, clear=True):
            status = monitor.budget_status(datetime(2026, 11, 22, 10, tzinfo=ZONE))
        self.assertEqual((status["used"], status["measured"], status["source_label"]), (0, False, "OpenWrt WAN"))


class StoredAlertTests(DatabaseCase):
    def alert(self, timestamp, **extra):
        return {"timestamp": timestamp, "kind": "device", "source": "aa:bb", "label": "Telefoon",
                "bps": 30_000_000, "baseline_bps": 1_000_000, "reason": "piek",
                "interval_start": "2026-11-22T09:59:30+01:00",
                "leaders": {"app": [], "device": [{"source": "aa:bb"}]}, **extra}

    def test_round_trip_ignores_duplicates_and_keeps_leaders(self):
        first = self.alert("2026-11-22T10:00:00+01:00")
        monitor.store_alerts([first, first])
        monitor.store_alerts([self.alert("2026-11-22T11:00:00+01:00", label="")])
        monitor.store_alerts([])
        stored = monitor.load_alerts()
        self.assertEqual([alert["timestamp"] for alert in stored],
                         ["2026-11-22T11:00:00+01:00", "2026-11-22T10:00:00+01:00"])
        self.assertEqual(stored[1]["leaders"]["device"][0]["source"], "aa:bb")
        self.assertEqual(monitor.load_alerts(1)[0]["label"], "")

    def test_counts_today_and_returns_the_latest(self):
        monitor.store_alerts([self.alert("2026-11-21T23:50:00+01:00"), self.alert("2026-11-22T08:00:00+01:00"),
                              self.alert("2026-11-22T09:00:00+01:00", source="x")])
        count, last = monitor.alerts_today(datetime(2026, 11, 22, 10, tzinfo=ZONE))
        self.assertEqual((count, last["source"]), (2, "x"))
        self.assertEqual(monitor.alerts_today(datetime(2026, 12, 1, tzinfo=ZONE))[0], 0)
        self.assertEqual(monitor.alerts_today(datetime(2026, 12, 1, tzinfo=ZONE))[1]["source"], "x")

    def test_old_alerts_are_pruned_with_the_measurements(self):
        monitor.store_alerts([self.alert("2025-01-01T10:00:00+01:00"), self.alert("2026-11-22T08:00:00+01:00")])
        monitor.record(datetime(2026, 11, 22, 10, tzinfo=ZONE), [], True)
        self.assertEqual([alert["timestamp"] for alert in monitor.load_alerts()], ["2026-11-22T08:00:00+01:00"])

    def test_corrupt_leaders_do_not_break_loading(self):
        monitor.store_alerts([self.alert("2026-11-22T08:00:00+01:00")])
        with closing(monitor.database()) as db, db:
            db.execute("UPDATE traffic_alerts SET leaders = 'kapot'")
        self.assertEqual(monitor.load_alerts()[0]["leaders"], {})


class LiveMonitorAlertTests(unittest.TestCase):
    def spike(self, live, start):
        live.update([], start, 0)
        returned = []
        for i in range(1, 10):
            returned += live.update([("device", "one", "One", 2000, 2000)], start + timedelta(seconds=i * 30), i * 30)
        return returned

    def test_update_returns_only_new_alerts(self):
        live = LiveMonitor()
        start = datetime(2026, 11, 10, tzinfo=timezone.utc)
        self.assertEqual(self.spike(live, start), [])
        new = live.update([("device", "one", "One", 30_000_000, 30_000_000)], start + timedelta(seconds=300), 300)
        self.assertEqual([alert["source"] for alert in new], ["one"])
        self.assertIn("leaders", new[0])
        again = live.update([("device", "one", "One", 30_000_000, 30_000_000)], start + timedelta(seconds=330), 330)
        self.assertEqual(again, [])

    def sequence(self, live, base):
        """Acht rustige rondes en daarna een piek, vijf minuten na `base`."""
        live.update([], base, 0)
        for i in range(1, 10):
            live.update([("device", "one", "One", 2000, 2000)], base + timedelta(seconds=i * 30), i * 30)
        return live.update([("device", "one", "One", 30_000_000, 30_000_000)], base + timedelta(seconds=300), 300)

    def test_restored_alerts_survive_a_restart_and_keep_suppressing_duplicates(self):
        start = datetime(2026, 11, 10, tzinfo=timezone.utc)
        first = self.sequence(LiveMonitor(), start)
        self.assertEqual(len(first), 1)

        # Controle: zonder terugzetten geeft dezelfde reeks na een herstart wel weer een melding.
        control = self.sequence(LiveMonitor(), start + timedelta(seconds=1))
        self.assertEqual(len(control), 1)

        restarted = LiveMonitor()
        restarted.restore([first[0], dict(first[0], timestamp="2026-11-09T00:00:00+00:00")])
        self.assertEqual(restarted.snapshot()["alerts"][0]["timestamp"], first[0]["timestamp"])
        self.assertEqual(len(restarted.snapshot()["alerts"]), 2)
        self.assertEqual(self.sequence(restarted, start + timedelta(seconds=1)), [],
                         "binnen een kwartier na de bewaarde piek")
        # Ruim na het kwartier meldt de monitor weer.
        later = self.sequence(restarted, start + timedelta(hours=1))
        self.assertEqual(len(later), 1)


class HomeAssistantEntityTests(unittest.TestCase):
    def status(self, state, percent):
        config = budget.settings({"data_budget_gb": 100, "data_budget_warn_percent": 80})
        result = budget.status(config, percent * budget.BYTES_PER_GB, datetime(2026, 11, 22, 10, tzinfo=ZONE))
        result["source_label"] = "Zyxel"
        self.assertEqual(result["state"], state)
        return {entity["id"]: entity for entity in ha_mqtt.budget_entities(result)}

    def test_no_budget_means_no_entities(self):
        self.assertEqual(ha_mqtt.budget_entities(None), [])

    def test_budget_entities_follow_the_thresholds(self):
        ok = self.status("ok", 10)
        warning = self.status("warning", 85)
        exceeded = self.status("exceeded", 120)
        self.assertEqual(set(ok), {"budget_percent", "budget_used", "budget_remaining",
                                   "budget_warning", "budget_exceeded"})
        self.assertEqual([entity["state"] for entity in (ok["budget_warning"], warning["budget_warning"],
                                                         exceeded["budget_warning"])], ["OFF", "ON", "ON"])
        self.assertEqual([entity["state"] for entity in (ok["budget_exceeded"], warning["budget_exceeded"],
                                                         exceeded["budget_exceeded"])], ["OFF", "OFF", "ON"])
        self.assertEqual(warning["budget_percent"]["state"], 85.0)
        self.assertEqual(warning["budget_percent"]["attributes"]["source"], "Zyxel")
        self.assertEqual(exceeded["budget_remaining"]["state"], 0)

    def test_spike_is_active_for_a_quarter_of_an_hour(self):
        now = datetime(2026, 11, 22, 10, 0, tzinfo=ZONE)
        last = {"timestamp": (now - timedelta(minutes=10)).isoformat(), "kind": "device", "source": "aa",
                "label": "", "bps": 12_345_000, "baseline_bps": 1_000_000}
        active, count = ha_mqtt.spike_entities(last, 3, now)
        self.assertEqual((active["state"], count["state"]), ("ON", 3))
        self.assertEqual(active["attributes"]["label"], "aa")
        self.assertEqual(active["attributes"]["mbit_s"], 12.3)
        late, _ = ha_mqtt.spike_entities(last, 3, now + timedelta(minutes=10))
        self.assertEqual(late["state"], "OFF")
        none, zero = ha_mqtt.spike_entities(None, 0, now)
        self.assertEqual((none["state"], none["attributes"], zero["state"]), ("OFF", {}, 0))

    def test_entity_config_topics_and_attributes(self):
        entity = {"component": "sensor", "id": "budget_percent", "name": "Naam", "state": 1,
                  "attributes": {}, "config": {"unit_of_measurement": "%"}}
        config = ha_mqtt.entity_config(entity)
        self.assertEqual(config["unique_id"], "ha_bandwidth_budget_percent")
        self.assertEqual(config["default_entity_id"], "sensor.ha_bandwidth_budget_percent")
        self.assertEqual(config["json_attributes_topic"], "ha_bandwidth/budget_percent/attributes")
        self.assertEqual(config["unit_of_measurement"], "%")
        self.assertNotIn("json_attributes_topic", ha_mqtt.entity_config(dict(entity, attributes=None)))


class PublishTests(DatabaseCase):
    class Stop(BaseException):
        pass

    def run_publish(self, extras, rounds):
        client = Mock()
        client.is_connected.return_value = True
        client.publish.return_value.is_published.return_value = True
        client.connect.side_effect = lambda *args, **kwargs: client.on_connect(
            client, None, None, Mock(is_failure=False), None)
        sleeps = []

        def sleep(_seconds):
            sleeps.append(1)
            if len(sleeps) >= rounds:
                raise self.Stop

        with patch.object(ha_mqtt, "supervisor_mqtt", return_value={"host": "broker", "port": 1883}), \
                patch.object(ha_mqtt.mqtt, "Client", return_value=client), \
                patch.object(ha_mqtt.time, "sleep", sleep):
            with self.assertRaises(self.Stop):
                ha_mqtt.publish(monitor.database, ZONE, monitor.period_bounds, False,
                                self.root / "mqtt-sensors.json", extras)
        return [(call.args[0], call.args[1]) for call in client.publish.call_args_list]

    def test_extra_entities_are_published_and_survive_a_failing_round(self):
        now = datetime(2026, 11, 22, 10, tzinfo=ZONE)
        config = budget.settings({"data_budget_gb": 100})
        status = dict(budget.status(config, 90 * budget.BYTES_PER_GB, now), source_label="Zyxel")
        calls = []

        def extras():
            calls.append(1)
            if len(calls) > 1:
                raise sqlite3.OperationalError("database is locked")
            return ha_mqtt.budget_entities(status) + ha_mqtt.spike_entities(None, 0, now)

        published = self.run_publish(extras, rounds=2)
        topics = dict(published)
        self.assertEqual(len(calls), 2)
        self.assertEqual(topics["ha_bandwidth/budget_warning/state"], "ON")
        self.assertEqual(topics["ha_bandwidth/spike_active/state"], "OFF")
        self.assertEqual(json.loads(topics["ha_bandwidth/budget_percent/attributes"])["source"], "Zyxel")
        self.assertIn("homeassistant/binary_sensor/ha_bandwidth/budget_warning/config", topics)
        removed = [topic for topic, payload in published if payload == "" and topic.endswith("/config")]
        self.assertEqual(removed, [], "een mislukte ronde mag de entiteiten niet verwijderen")

    def test_entities_disappear_when_they_are_no_longer_offered(self):
        now = datetime(2026, 11, 22, 10, tzinfo=ZONE)
        offered = [ha_mqtt.spike_entities(None, 0, now), []]
        published = self.run_publish(lambda: offered.pop(0), rounds=2)
        removed = {topic for topic, payload in published if payload == ""}
        self.assertEqual(removed, {"homeassistant/binary_sensor/ha_bandwidth/spike_active/config",
                                   "homeassistant/sensor/ha_bandwidth/spikes_today/config"})


if __name__ == "__main__":
    unittest.main()
