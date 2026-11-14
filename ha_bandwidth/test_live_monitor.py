"""Regression tests for rolling bandwidth rates and warnings."""
import unittest
from datetime import datetime, timedelta, timezone

from live_monitor import LiveMonitor


class LiveMonitorTests(unittest.TestCase):
    def test_first_sample_establishes_baseline(self):
        live = LiveMonitor()
        now = datetime(2026, 11, 10, tzinfo=timezone.utc)
        live.update([("openwrt", "wan", "WAN", 100, 200)], now, 10)
        self.assertEqual(live.snapshot()["sources"], [])
        live.update([("openwrt", "wan", "WAN", 125, 250)], now + timedelta(seconds=5), 15)
        self.assertEqual(live.snapshot()["sources"][0]["rx_bps"], 200)
        self.assertEqual(live.snapshot()["sources"][0]["tx_bps"], 400)

    def test_ignores_long_gaps(self):
        live = LiveMonitor()
        now = datetime(2026, 11, 10, tzinfo=timezone.utc)
        live.update([], now, 1)
        live.update([("device", "one", "One", 999, 999)], now + timedelta(minutes=5), 301)
        self.assertEqual(live.snapshot()["sources"], [])

    def test_sustained_spike_alert_is_deduplicated(self):
        live = LiveMonitor()
        now = datetime(2026, 11, 10, tzinfo=timezone.utc)
        live.update([], now, 0)
        for i in range(1, 10):
            live.update([("device", "one", "One", 2000, 2000)], now + timedelta(seconds=i*30), i*30)
        live.update([("device", "one", "One", 30_000_000, 30_000_000)],
                    now + timedelta(seconds=300), 300)
        self.assertEqual(len(live.snapshot()["alerts"]), 1)
        alert = live.snapshot()["alerts"][0]
        self.assertEqual(alert["interval_start"], (now + timedelta(seconds=270)).isoformat())
        self.assertEqual(alert["leaders"]["device"][0]["source"], "one")
        self.assertEqual(alert["leaders"]["app"], [])
        live.update([("device", "one", "One", 30_000_000, 30_000_000)],
                    now + timedelta(seconds=330), 330)
        self.assertEqual(len(live.snapshot()["alerts"]), 1)

    def test_does_not_count_peers_in_live_sources(self):
        live = LiveMonitor()
        now = datetime(2026, 11, 10, tzinfo=timezone.utc)
        live.update([], now, 0)
        live.update([("peer", "8.8.8.8", "IP", 1000, 1000)], now + timedelta(seconds=30), 30)
        self.assertEqual(live.snapshot()["sources"], [])


if __name__ == "__main__":
    unittest.main()
