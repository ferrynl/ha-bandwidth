"""app_settings werkt zonder monitor, database of klok."""
import json
import tempfile
import unittest
from pathlib import Path

import app_settings as store

GOOD = {"limit_gb": 100, "source": "host", "reset_day": 5, "warn_percent": 80}


class StoreTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "app-settings.json"

    def test_missing_or_corrupt_files_give_nothing(self):
        self.assertEqual(store.load(self.path), {})
        for text in ("", "{", "[]", "null", '"x"'):
            self.path.write_text(text)
            self.assertEqual(store.load(self.path), {}, text)

    def test_roundtrip_leaves_no_staging_file(self):
        settings = {"retention_days": 90, "budget": GOOD, "budget_calibration": {"cycle_start": "2026-11-05", "offset": -5}}
        store.save(self.path, settings)
        self.assertEqual(store.load(self.path), settings)
        self.assertEqual([p.name for p in self.path.parent.iterdir()], [self.path.name])

    def test_invalid_parts_are_dropped_and_valid_parts_kept(self):
        self.path.write_text(json.dumps({"retention_days": 5, "budget": dict(GOOD, reset_day=31),
                                         "budget_calibration": {"cycle_start": "x", "offset": 1}, "unknown": 1}))
        self.assertEqual(store.load(self.path), {})
        self.path.write_text(json.dumps({"retention_days": 90, "budget": dict(GOOD, reset_day=31)}))
        self.assertEqual(store.load(self.path), {"retention_days": 90})

    def test_retention_days_clamps_and_defaults(self):
        self.assertEqual([store.retention_days(o) for o in ({}, {"retention_days": "x"}, {"retention_days": 1}, {"retention_days": 10**6})],
                         [400, 400, 30, 3650])

    def test_clean_budget(self):
        self.assertEqual(store.clean_budget(GOOD), (GOOD, None))
        for bad in (None, [], {}, dict(GOOD, limit_gb=-1), dict(GOOD, limit_gb=True), dict(GOOD, limit_gb=float("inf")),
                    dict(GOOD, source="x"), dict(GOOD, reset_day=29), dict(GOOD, warn_percent=100)):
            self.assertIsNotNone(store.clean_budget(bad)[1], bad)

    def test_clean_used_gb(self):
        self.assertEqual(store.clean_used_gb({"used_gb": 3.5}), (3.5, None))
        self.assertEqual(store.clean_used_gb({"used_gb": None}), (None, None))
        for bad in ({}, None, {"used_gb": -1}, {"used_gb": "3"}, {"used_gb": True}, {"used_gb": float("nan")}):
            self.assertIsNotNone(store.clean_used_gb(bad)[1], bad)

    def test_saved_budget_overrides_options_without_mutating_them(self):
        options = {"data_budget_gb": 0, "other": 1}
        merged = store.budget_options(options, GOOD)
        self.assertEqual((merged["data_budget_gb"], merged["data_budget_source"], merged["other"]), (100, "host", 1))
        self.assertEqual(options, {"data_budget_gb": 0, "other": 1})
        self.assertIs(store.budget_options(options, None), options)


if __name__ == "__main__":
    unittest.main()
