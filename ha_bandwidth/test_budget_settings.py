"""De budgetinstellingen op de pagina Instellingen."""
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import monitor
from test_calibration_backup_cards import DatabaseCase, NOW

GOOD = {"Content-Type": "application/json", "X-HA-Bandwidth-Settings": "1"}
FORM = {"limit_gb": 200, "source": "openwrt", "reset_day": 15, "warn_percent": 90}


class BudgetSettingsTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        patcher = patch.dict(monitor.SETTINGS, {"data_budget_gb": 100, "data_budget_source": "host",
                                                "data_budget_reset_day": 1, "data_budget_warn_percent": 80})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_configuration_is_the_starting_point(self):
        state = monitor.budget_state()
        self.assertEqual((state["limit_gb"], state["source"], state["reset_day"], state["warn_percent"], state["from_settings_page"]),
                         (100, "host", 1, 80, False))

    def test_saved_values_override_configuration(self):
        code, state = monitor.change_budget(dict(FORM))
        self.assertEqual((code, state["limit_gb"], state["source"], state["from_settings_page"]), (200, 200, "openwrt", True))
        status = monitor.budget_status(NOW)
        self.assertEqual((status["limit"], status["source"], status["warn_percent"], status["cycle_start"]),
                         (200e9, "openwrt", 90, "2026-11-15"))

    def test_limit_zero_turns_the_budget_off_even_if_configuration_has_one(self):
        self.assertEqual(monitor.change_budget(dict(FORM, limit_gb=0))[0], 200)
        self.assertIsNone(monitor.budget_status(NOW))
        self.assertEqual(monitor.budget_state()["limit_gb"], 0)

    def test_budget_can_be_enabled_when_configuration_has_none(self):
        with patch.dict(monitor.SETTINGS, {"data_budget_gb": 0}):
            self.assertIsNone(monitor.budget_status(NOW))
            self.assertEqual(monitor.change_budget(dict(FORM))[0], 200)
            self.assertEqual(monitor.budget_status(NOW)["limit"], 200e9)

    def test_invalid_input_is_rejected_and_nothing_is_saved(self):
        for bad in (dict(FORM, limit_gb=-1), dict(FORM, limit_gb=True), dict(FORM, limit_gb="5"), dict(FORM, limit_gb=float("nan")),
                    dict(FORM, limit_gb=2_000_000), dict(FORM, source="x"), dict(FORM, reset_day=29), dict(FORM, reset_day=0),
                    dict(FORM, reset_day=1.5), dict(FORM, warn_percent=100), dict(FORM, warn_percent=0), dict(FORM, warn_percent=True),
                    {}, [], None):
            with self.subTest(bad=bad):
                self.assertEqual(monitor.change_budget(bad)[0], 400)
        self.assertNotIn("budget", monitor.load_app_settings())

    def test_corrupt_saved_budget_is_ignored(self):
        monitor.save_app_settings({"budget": {"limit_gb": "x", "source": "host", "reset_day": 1, "warn_percent": 80}})
        self.assertNotIn("budget", monitor.load_app_settings())
        self.assertEqual(monitor.budget_state()["limit_gb"], 100)

    def test_saving_keeps_retention_and_calibration(self):
        monitor.change_retention({"retention_days": 500})
        monitor.calibrate_budget({"used_gb": 3}, NOW)
        monitor.change_budget(dict(FORM, reset_day=1))
        saved = monitor.load_app_settings()
        self.assertEqual(saved["retention_days"], 500)
        self.assertIn("budget_calibration", saved)
        self.assertIn("budget", saved)

    def test_changing_the_reset_day_drops_the_calibration_of_the_old_cycle(self):
        monitor.calibrate_budget({"used_gb": 3}, NOW)
        self.assertEqual(monitor.budget_status(NOW)["offset"], 3e9)
        monitor.change_budget(dict(FORM, source="host"))
        self.assertEqual(monitor.budget_status(NOW)["offset"], 0)


class BudgetSettingsHttpTests(DatabaseCase):
    def setUp(self):
        super().setUp()

        class ViaProxy(monitor.Dashboard):
            client_address = property(lambda self: ("172.30.32.2", 0), lambda self, value: None)

        self.direct = ThreadingHTTPServer(("127.0.0.1", 0), monitor.Dashboard)
        self.proxied = ThreadingHTTPServer(("127.0.0.1", 0), ViaProxy)
        for server in (self.direct, self.proxied):
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)

    def call(self, server, path, body=None, headers=None):
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}{path}",
                                         data=None if body is None else json.dumps(body).encode(),
                                         method="GET" if body is None else "POST", headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, None

    def test_post_is_guarded_and_get_works(self):
        path = "/api/settings/budget-config"
        self.assertEqual(self.call(self.direct, path, FORM, GOOD)[0], 403)
        self.assertEqual(self.call(self.proxied, path, FORM, {"Content-Type": "application/json"})[0], 403)
        self.assertEqual(self.call(self.proxied, path, dict(FORM, source="x"), GOOD)[0], 400)
        code, state = self.call(self.proxied, path, FORM, GOOD)
        self.assertEqual((code, state["limit_gb"]), (200, 200))
        self.assertEqual(self.call(self.proxied, "/api/settings/budget")[1]["reset_day"], 15)
        self.assertEqual(self.call(self.proxied, "/api/budget")[1]["limit"], 200e9)


if __name__ == "__main__":
    unittest.main()
