import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import migrations
import monitor
from test_calibration_backup_cards import DatabaseCase


def tables(db):
    return {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


class MigrationTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "test.sqlite3"

    def connect(self):
        return sqlite3.connect(self.path)

    def test_a_fresh_database_gets_every_table_at_the_latest_version(self):
        with closing(self.connect()) as db:
            self.assertEqual(migrations.migrate(db), migrations.latest())
            self.assertTrue({"traffic", "app_destinations", "ipinfo_cache", "traffic_alerts"} <= tables(db))

    def test_an_existing_unversioned_database_keeps_its_data(self):
        with closing(self.connect()) as db, db:
            db.execute("CREATE TABLE traffic (hour TEXT, kind TEXT, source TEXT, label TEXT, rx INTEGER NOT NULL, tx INTEGER NOT NULL, PRIMARY KEY (hour, kind, source)) WITHOUT ROWID")
            db.execute("INSERT INTO traffic VALUES ('2026-11-01T10', 'host', 'eth0', 'eth0', 5, 6)")
        with closing(self.connect()) as db:
            self.assertEqual(migrations.current_version(db), 0)
            migrations.migrate(db)
            self.assertEqual(db.execute("SELECT rx, tx FROM traffic").fetchall(), [(5, 6)])
            self.assertEqual(migrations.current_version(db), migrations.latest())

    def test_running_twice_changes_nothing(self):
        with closing(self.connect()) as db:
            migrations.migrate(db)
            before = db.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall()
            migrations.migrate(db)
            self.assertEqual(db.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall(), before)

    def test_later_migrations_run_in_order_on_top_of_earlier_ones(self):
        plan = {**migrations.MIGRATIONS, 2: ["ALTER TABLE traffic ADD COLUMN note TEXT"], 3: ["CREATE TABLE extra (x INTEGER)"]}
        with closing(self.connect()) as db:
            migrations.migrate(db)
            self.assertEqual(migrations.migrate(db, plan), 3)
            self.assertIn("extra", tables(db))
            self.assertIn("note", [row[1] for row in db.execute("PRAGMA table_info(traffic)")])

    def test_a_failing_migration_changes_nothing(self):
        plan = {**migrations.MIGRATIONS, 2: ["CREATE TABLE half (x INTEGER)", "THIS IS NOT SQL"]}
        with closing(self.connect()) as db:
            migrations.migrate(db)
            with self.assertRaises(sqlite3.Error):
                migrations.migrate(db, plan)
            self.assertNotIn("half", tables(db))
            self.assertEqual(migrations.current_version(db), 1)
            self.assertEqual(migrations.migrate(db), 1, "de database blijft bruikbaar")

    def test_a_newer_database_is_refused_and_left_alone(self):
        with closing(self.connect()) as db:
            db.execute("PRAGMA user_version = 99")
            with self.assertRaises(RuntimeError) as raised:
                migrations.migrate(db)
            self.assertIn("99", str(raised.exception))
            self.assertNotIn("traffic", tables(db))


class InitializeTests(DatabaseCase):
    def test_initialize_stamps_the_version_and_is_repeatable(self):
        monitor.initialize()
        with closing(monitor.database()) as db:
            self.assertEqual(migrations.current_version(db), migrations.latest())

    def test_a_backup_keeps_working_across_versions(self):
        self.add("2026-11-05T10", 7, 8)
        with closing(monitor.database()) as db:
            copy = self.root / "copy.sqlite3"
            from storage_backup import snapshot
            snapshot(db, copy)
        with closing(sqlite3.connect(copy)) as db:
            self.assertEqual(migrations.current_version(db), migrations.latest())
            self.assertEqual(db.execute("SELECT SUM(rx) FROM traffic").fetchone()[0], 7)


if __name__ == "__main__":
    unittest.main()
