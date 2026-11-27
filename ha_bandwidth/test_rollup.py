import unittest
from contextlib import closing
from datetime import date, datetime
from unittest.mock import patch

import monitor
import rollup
from test_calibration_backup_cards import DatabaseCase

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=monitor.ZONE)


class RollupTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        for hour in ("2026-10-01T03", "2026-10-01T09", "2026-10-01T23"):
            self.add(hour, 10, 1)
        self.add("2026-10-01T09", 5, 5, kind="openwrt", source="wan")
        self.add("2026-11-19T10", 7, 7)  # recent: blijft per uur
        self.add("2026-09-30T00", 3, 3)  # al samengevat

    def rows(self):
        with closing(monitor.database()) as db:
            return db.execute("SELECT hour, kind, source, rx, tx FROM traffic ORDER BY hour, kind").fetchall()

    def totals(self):
        with closing(monitor.database()) as db:
            return tuple(db.execute("SELECT SUM(rx), SUM(tx) FROM traffic").fetchone())

    def test_old_hours_become_one_row_per_day_and_source_with_equal_totals(self):
        before = self.totals()
        with closing(monitor.database()) as db, db:
            self.assertEqual(rollup.summarize(db, "2026-11-01"), 2)
        self.assertEqual(self.totals(), before)
        self.assertEqual([tuple(r) for r in self.rows()], [
            ("2026-09-30T00", "host", "eth0", 3, 3), ("2026-10-01T00", "host", "eth0", 30, 3),
            ("2026-10-01T00", "openwrt", "wan", 5, 5), ("2026-11-19T10", "host", "eth0", 7, 7)])

    def test_repeating_changes_nothing_and_recent_days_stay_hourly(self):
        with closing(monitor.database()) as db, db:
            rollup.summarize(db, "2026-11-01")
        first = [tuple(r) for r in self.rows()]
        with closing(monitor.database()) as db, db:
            self.assertEqual(rollup.summarize(db, "2026-11-01"), 0)
        self.assertEqual([tuple(r) for r in self.rows()], first)
        self.assertIn("2026-11-19T10", [r[0] for r in first])

    def test_the_cutoff_day_itself_is_kept_hourly(self):
        with closing(monitor.database()) as db, db:
            rollup.summarize(db, "2026-10-01")
        self.assertEqual(len([r for r in self.rows() if r["hour"].startswith("2026-10-01")]), 4)

    def test_detail_days_counts_only_what_would_change(self):
        with closing(monitor.database()) as db:
            self.assertEqual(rollup.detail_days(db, "2026-11-01"), 1)
            self.assertEqual(rollup.detail_days(db, "2026-09-30"), 0)

    def test_chart_buckets_and_csv_keep_their_totals(self):
        day = date(2026, 10, 1)
        before = monitor.export_csv(day, "month", "host", "")
        with closing(monitor.database()) as db, db:
            rollup.summarize(db, "2026-11-01")
        after = monitor.export_csv(day, "month", "host", "")
        self.assertEqual(before, after, "per dag gegroepeerd verandert er niets")


class HourlySettingTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        patcher = patch.object(monitor, "HOURLY_DAYS", 0)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.add("2026-06-01T05", 1, 1)
        self.add("2026-06-01T06", 1, 1)

    def test_validation(self):
        for bad in ({}, None, {"hourly_days": 5}, {"hourly_days": True}, {"hourly_days": False}, {"hourly_days": "90"}, {"hourly_days": 99999}):
            with self.subTest(bad=bad):
                self.assertEqual(monitor.change_hourly(bad)[0], 400)

    def test_enabling_over_old_detail_needs_confirmation_and_saves_nothing_without_it(self):
        code, answer = monitor.change_hourly({"hourly_days": 90})
        self.assertEqual((code, answer["affected_days"]), (409, 1))
        self.assertNotIn("hourly_days", monitor.load_app_settings())
        code, state = monitor.change_hourly({"hourly_days": 90, "confirm": True})
        self.assertEqual((code, state["hourly_days"], state["pending_days"]), (200, 90, 1))
        self.assertEqual(monitor.load_app_settings()["hourly_days"], 90)

    def test_zero_turns_it_off_without_confirmation(self):
        monitor.change_hourly({"hourly_days": 90, "confirm": True})
        self.assertEqual(monitor.change_hourly({"hourly_days": 0})[1]["hourly_days"], 0)

    def test_nothing_is_summarized_until_the_cleanup_runs_and_it_is_off_by_default(self):
        monitor.record(NOW, [], prune=True)
        with closing(monitor.database()) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM traffic WHERE hour LIKE '2026-06%'").fetchone()[0], 2)
        monitor.change_hourly({"hourly_days": 90, "confirm": True})
        monitor.record(NOW, [], prune=True)
        with closing(monitor.database()) as db:
            self.assertEqual(db.execute("SELECT COUNT(*), SUM(rx) FROM traffic WHERE hour LIKE '2026-06%'").fetchone()[:], (1, 2))

    def test_saving_keeps_other_settings(self):
        monitor.change_retention({"retention_days": 500})
        monitor.change_hourly({"hourly_days": 90, "confirm": True})
        saved = monitor.load_app_settings()
        self.assertEqual((saved["retention_days"], saved["hourly_days"]), (500, 90))


if __name__ == "__main__":
    unittest.main()
