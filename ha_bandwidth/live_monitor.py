"""Near-realtime rate snapshots and cautious, local anomaly detection.

All rates derive from counter deltas; they are not packet-level instantaneous
measurements. Do not combine different traffic scopes into a network total.
"""
from collections import defaultdict, deque
from datetime import datetime
from threading import Lock
import time


class LiveMonitor:
    def __init__(self):
        self.lock = Lock()
        self.samples = deque(maxlen=120)
        self.baselines = defaultdict(lambda: deque(maxlen=60))
        self.alerts = deque(maxlen=40)
        self.last_monotonic = None
        self.last_time = None
        self.last_observed = {}
        self.quality = {}

    def update(self, rows, timestamp, monotonic=None, *, observed=(), expected=()):
        """Consume deduplicated readings from a completed collection round."""
        monotonic = time.monotonic() if monotonic is None else monotonic
        with self.lock:
            elapsed = None if self.last_monotonic is None else monotonic - self.last_monotonic
            self.last_monotonic = monotonic
            self.last_time = timestamp.isoformat()
            valid_interval = elapsed is not None and 0 < elapsed <= 180
            measured = {row[0] for row in rows} if valid_interval else set()
            for kind in observed:
                self.last_observed[kind] = self.last_time
            self.quality = {
                kind: {"state": "measured" if kind in measured else
                       "baseline" if kind in observed else "missing",
                       "last_read": self.last_observed.get(kind)}
                for kind in sorted(expected)
            }
            if not valid_interval:
                return
            by_source = defaultdict(lambda: [0, 0, ""])
            for kind, source, label, rx, tx in rows:
                if kind not in ("host", "app", "device", "openwrt", "modem"):
                    continue
                item = by_source[(kind, source)]
                item[0] += max(0, rx)
                item[1] += max(0, tx)
                item[2] = label
            current = []
            for (kind, source), (rx, tx, label) in by_source.items():
                row = {"kind": kind, "source": source, "label": label,
                       "rx_bps": round(rx * 8 / elapsed),
                       "tx_bps": round(tx * 8 / elapsed)}
                current.append(row)
                key = (kind, source)
                history = self.baselines[key]
                total = row["rx_bps"] + row["tx_bps"]
                # A short rolling baseline is only a first warning, not a diagnosis.
                if len(history) >= 8:
                    ordered = sorted(history)
                    median = (ordered[(len(ordered)-1)//2] + ordered[len(ordered)//2]) / 2
                    # Minimum 5 Mbps and at least 4x a non-trivial median.
                    if total >= 5_000_000 and total > max(5_000_000, median * 4):
                        if not any(a["kind"] == kind and a["source"] == source
                                   and (timestamp - datetime.fromisoformat(a["timestamp"])).total_seconds() < 900
                                   for a in self.alerts):
                            self.alerts.appendleft({
                                "timestamp": timestamp.isoformat(), "kind": kind,
                                "source": source, "label": label,
                                "bps": total, "baseline_bps": round(median),
                                "reason": "Traffic spike compared to recent samples",
                            })
                history.append(total)
            self.samples.append({"timestamp": self.last_time, "elapsed_seconds": round(elapsed, 2),
                                 "sources": sorted(current, key=lambda r: r["rx_bps"] + r["tx_bps"], reverse=True)})

    def snapshot(self):
        with self.lock:
            sample = self.samples[-1] if self.samples and self.samples[-1]["timestamp"] == self.last_time else None
            history = []
            for entry in self.samples:
                wan = next((row for row in entry["sources"] if row["kind"] == "openwrt"), None)
                history.append({"timestamp": entry["timestamp"],
                                "rx_bps": wan["rx_bps"] if wan else None,
                                "tx_bps": wan["tx_bps"] if wan else None})
            return {"updated": self.last_time, "interval_seconds": sample["elapsed_seconds"] if sample else None,
                    "sources": sample["sources"] if sample else [],
                    "quality": self.quality,
                    "history": history,
                    "alerts": list(self.alerts), "note": "Rates are averages over the previous collection interval. WAN, host, apps and devices overlap; do not add them together."}
