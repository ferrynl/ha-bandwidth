"""Regressietests bij de Semgrep-bevindingen: namen in SQL, statische bestanden en de back-up-download."""
import threading
import unittest
from http.server import ThreadingHTTPServer

import monitor
import storage_backup
from local_http import local_request
from test_calibration_backup_cards import DatabaseCase


class IdentifierTests(unittest.TestCase):
    def test_only_names_from_the_schema_pass(self):
        for name in list(storage_backup.TABLES) + ["hour", "rx", "leaders"]:
            self.assertEqual(storage_backup.identifier(name), name)
        for name in ("evil; DROP TABLE traffic", "traffic--", "sqlite_master", "", "main.traffic", "rx, tx"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                storage_backup.identifier(name)


class ServerTests(DatabaseCase):
    def setUp(self):
        super().setUp()

        class ViaProxy(monitor.Dashboard):
            client_address = property(lambda self: ("172.30.32.2", 0), lambda self, value: None)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ViaProxy)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def get(self, path):
        return local_request(self.server.server_port, "GET", path)

    def test_static_files_are_served_from_the_fixed_table(self):
        for route, (name, _) in monitor.STATIC_FILES.items():
            status, body = self.get(route)
            self.assertEqual((status, body), (200, (monitor.ROOT / name).read_bytes()), route)

    def test_a_url_can_never_pick_another_file(self):
        for path in ("/config.yaml", "/../config.yaml", "/%2e%2e/config.yaml", "/dashboard.js/../monitor.py", "/monitor.py",
                     "/..%2fconfig.yaml", "//etc/passwd"):
            with self.subTest(path=path):
                self.assertIn(self.get(path)[0], (400, 404))

    def test_a_backup_download_is_complete(self):
        self.add("2026-11-05T10", 7, 8)
        status, body = self.get("/api/backup")
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b"SQLite format 3\x00"))
        self.assertGreater(len(body), 4096)


if __name__ == "__main__":
    unittest.main()
