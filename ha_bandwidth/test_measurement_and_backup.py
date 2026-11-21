import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from email.message import Message
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.response import addinfourl

import ha_dashboard
import ha_mqtt
import modem
import monitor
from storage_backup import restore, snapshot


class MeasurementTests(unittest.TestCase):
    def test_duplicate_reset_and_recovery(self):
        def reading(value):
            return ("generation", "openwrt", "wan", "WAN", value, value)

        previous, _ = monitor.deltas([reading(100)], {})
        previous, rows = monitor.deltas([reading(110), reading(110)], previous)
        self.assertEqual(rows, [("openwrt", "wan", "WAN", 10, 10)])
        previous, rows = monitor.deltas([reading(5)], previous)
        self.assertEqual(rows, [])
        previous, rows = monitor.deltas([], previous)
        self.assertEqual(rows, [])
        previous, rows = monitor.deltas([reading(6)], previous)
        self.assertEqual(rows, [])
        _, rows = monitor.deltas([reading(6)], previous)
        self.assertEqual(rows, [("openwrt", "wan", "WAN", 0, 0)])

    def test_live_quality_distinguishes_zero_missing_and_expired(self):
        live = monitor.LiveMonitor()
        now = datetime.now(timezone.utc)
        live.update([], now, 0, observed={"openwrt"}, expected={"openwrt"})
        self.assertEqual(live.snapshot()["quality"]["openwrt"]["state"], "baseline")
        live.update([("openwrt", "wan", "WAN", 0, 0)], now + timedelta(seconds=30),
                    30, observed={"openwrt"}, expected={"openwrt"})
        current = live.snapshot()
        self.assertEqual(current["sources"][0]["rx_bps"], 0)
        self.assertEqual(current["quality"]["openwrt"]["state"], "measured")
        live.update([], now + timedelta(minutes=5), 300, expected={"openwrt"})
        self.assertEqual(live.snapshot()["sources"], [])
        self.assertEqual(live.snapshot()["quality"]["openwrt"], {
            "state": "missing", "last_read": current["updated"],
        })


class BackupTests(unittest.TestCase):
    def test_legacy_backup_restore_and_rescue_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "legacy.sqlite3"
            rescue, previous = root / "rescue.sqlite3", root / "previous.sqlite3"
            with closing(sqlite3.connect(legacy)) as db, db:
                db.execute("CREATE TABLE traffic (hour, kind, source, label, rx, tx)")
                db.execute("INSERT INTO traffic VALUES ('2026-11-14T12', 'host', 'old', 'Old', 123, 456)")
            with patch.object(monitor, "DATA", root):
                monitor.initialize()
                with closing(monitor.database()) as db:
                    with db:
                        db.execute("INSERT INTO traffic VALUES ('2026-11-14T12', 'host', 'new', 'New', 1, 2)")
                    restore(db, legacy, rescue, previous)
                    self.assertEqual(tuple(db.execute("SELECT source, rx, tx FROM traffic").fetchone()),
                                     ("old", 123, 456))
                    snapshot(db, root / "export.sqlite3")
            for path, source in [(previous, "new"), (root / "export.sqlite3", "old")]:
                with closing(sqlite3.connect(path)) as db:
                    self.assertEqual(db.execute("SELECT source FROM traffic").fetchone()[0], source)



class SupervisorConnectionTests(unittest.TestCase):
    def test_modem_reads_a_single_sensor_from_the_supervisor(self):
        with patch.dict(os.environ, {"SUPERVISOR_TOKEN": "test-token"}):
            with patch.object(modem, "supervisor_get", return_value={
                "state": "12", "attributes": {"unit_of_measurement": "B"},
            }) as get:
                self.assertEqual(modem.read_counter("sensor.wan_download"), 12)
                get.assert_called_once_with("/core/api/states/sensor.wan_download")

    def test_supervisor_http_redirect_is_rejected(self):
        headers = Message()
        headers["Location"] = "/core/api/config"
        url = "http://supervisor/services/mqtt"
        with addinfourl(BytesIO(), headers, url, 302) as redirect:
            redirect.msg = "Found"
            with patch.dict(os.environ, {"SUPERVISOR_TOKEN": "test-token"}):
                with patch("urllib.request.HTTPHandler.http_open", return_value=redirect) as open_http:
                    with self.assertRaises(HTTPError) as raised:
                        ha_mqtt.supervisor_get("/services/mqtt")
                    self.assertEqual(raised.exception.code, 302)
                    open_http.assert_called_once()
                    request = open_http.call_args.args[0]
                    self.assertEqual(request.full_url, url)
                    self.assertEqual(request.get_header("Authorization"), "Bearer test-token")

    def test_dashboard_keeps_websocket_credentials_on_the_supervisor(self):
        websocket = Mock()
        websocket.getstatus.return_value = 302
        ingress = "/api/hassio_ingress/test"
        with patch.object(ha_dashboard, "supervisor_get", return_value={"data": {"ingress_url": ingress}}):
            with patch.object(ha_dashboard, "create_connection", return_value=websocket) as connect:
                with patch.object(ha_dashboard.time, "sleep"):
                    ha_dashboard.provision_dashboard()
        self.assertEqual(connect.call_count, 3)
        for call in connect.call_args_list:
            self.assertEqual(call.args, ("ws://supervisor/core/websocket",))
            self.assertEqual(call.kwargs["http_no_proxy"], ["supervisor"])
            self.assertEqual(call.kwargs["redirect_limit"], 0)
        websocket.send.assert_not_called()
        websocket.close.assert_called()
