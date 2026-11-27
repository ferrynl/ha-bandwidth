"""De uit monitor.py losgemaakte modules werken ook zonder monitor."""
import unittest
from datetime import date, datetime

import csv_export
import ipinfo
import periods
import topology


class ModuleTests(unittest.TestCase):
    def test_period_bounds(self):
        self.assertEqual(periods.period_bounds(date(2026, 11, 25), "week"), (date(2026, 11, 23), date(2026, 11, 30)))
        self.assertEqual(periods.period_bounds(date(2026, 12, 5), "month"), (date(2026, 12, 1), date(2027, 1, 1)))

    def test_previous_period_of_a_running_month_stops_at_the_same_moment(self):
        _, _, first, stop, partial = periods.previous_period(date(2026, 11, 1), "month", datetime(2026, 11, 10, 14, 30))
        self.assertTrue(partial)
        self.assertEqual((first, stop), (datetime(2026, 10, 1), datetime(2026, 10, 10, 15)))

    def test_csv_text_has_bom_header_and_safe_cells(self):
        text = csv_export.csv_text([{"bucket": "2026-11", "kind": "host", "source": "=cmd", "label": "ok", "rx": 1, "tx": 2}])
        self.assertTrue(text.startswith("﻿bucket,"))
        self.assertIn("'=cmd", text)
        self.assertTrue(text.rstrip().endswith("1,2,3"))

    def test_public_ip_only_accepts_global_addresses(self):
        self.assertEqual(ipinfo.public_ip("8.8.8.8"), "8.8.8.8")
        for value in ("192.168.1.5", "127.0.0.1", "fe80::1%eth0", "224.0.0.1", "nonsense"):
            self.assertIsNone(ipinfo.public_ip(value), value)

    def test_lookup_without_token_is_refused_before_any_request(self):
        for token in ("", "  ", None):
            with self.assertRaises(ValueError):
                ipinfo.fetch_ipinfo(token, "8.8.8.8")

    def test_router_topology_skips_the_router_and_merges_by_mac(self):
        hosts = {"10.0.0.1": {"mac": "r", "name": "router"}, "10.0.0.5": {"mac": "a", "name": "tv"},
                 "fd00::5": {"mac": "a", "name": "tv"}}
        result = topology.router_topology(hosts, {}, "http://10.0.0.1/")
        self.assertEqual([(d["source"], sorted(d["ips"])) for d in result], [("a", ["10.0.0.5", "fd00::5"])])


if __name__ == "__main__":
    unittest.main()
