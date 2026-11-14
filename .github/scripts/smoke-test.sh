#!/usr/bin/env bash
set -euo pipefail

docker build -t bandwidth-smoke ha_bandwidth
trap 'docker logs bandwidth-smoke 2>&1 || true; docker rm -f bandwidth-smoke || true; docker network rm bandwidth-smoke || true; docker volume rm bandwidth-smoke || true' EXIT
docker network create --subnet 172.30.32.0/24 bandwidth-smoke
docker volume create bandwidth-smoke
docker run --rm -i -v bandwidth-smoke:/data bandwidth-smoke python - <<'PY'
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

Path("/data/options.json").write_text(json.dumps({
    "publish_to_ha": False, "create_ha_dashboard": False,
    "track_peers": False, "track_app_destinations": False,
}))
with sqlite3.connect("/data/bandwidth.sqlite3") as db:
    db.executescript("""
        CREATE TABLE traffic (
            hour TEXT, kind TEXT, source TEXT, label TEXT,
            rx INTEGER NOT NULL, tx INTEGER NOT NULL,
            PRIMARY KEY (hour, kind, source)
        ) WITHOUT ROWID;
    """)
    hour = datetime.now(ZoneInfo("Europe/Amsterdam")).strftime("%Y-%m-%dT%H")
    db.execute("INSERT INTO traffic VALUES (?, 'host', 'legacy', 'Legacy', 123, 456)", (hour,))
Path("/data/test-date").write_text(hour[:10])
PY
docker run -d --name bandwidth-smoke --network bandwidth-smoke \
  --ip 172.30.32.3 -v bandwidth-smoke:/data bandwidth-smoke
docker run --rm -i --network bandwidth-smoke --ip 172.30.32.2 \
  -v bandwidth-smoke:/data:ro bandwidth-smoke python - <<'PY'
import json
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

def get(path):
    with urlopen("http://172.30.32.3:63187" + path, timeout=2) as response:
        return response.read()

for attempt in range(30):
    try:
        assert b"HA-Bandwidth" in get("/")
        break
    except (URLError, TimeoutError):
        if attempt == 29:
            raise
        time.sleep(1)

assert b"loadLive" in get("/dashboard.js")
assert "quality" in json.loads(get("/api/live"))
day = Path("/data/test-date").read_text()
report = json.loads(get(f"/api/traffic?kind=host&period=day&date={day}"))
assert any(b["rx"] == 123 and b["tx"] == 456 for b in report["buckets"]), report
assert get("/api/backup").startswith(b"SQLite format 3\x00")

from urllib.error import HTTPError
from urllib.request import Request

try:
    urlopen(Request("http://172.30.32.3:63187/api/backup/restore", data=b""), timeout=2)
except HTTPError as error:
    assert error.code == 403
else:
    raise AssertionError("Restore accepted without the required request header")
PY
docker run --rm -i --network bandwidth-smoke bandwidth-smoke python - <<'PY'
from urllib.error import HTTPError
from urllib.request import Request, urlopen

base = "http://172.30.32.3:63187"
for request in (
    Request(base + "/api/live", headers={"X-Forwarded-For": "172.30.32.2"}),
    Request(base + "/api/backup"),
    Request(base + "/api/backup/restore", data=b"",
            headers={"X-HA-Bandwidth-Restore": "1", "X-Forwarded-For": "172.30.32.2"}),
):
    try:
        urlopen(request, timeout=2)
    except HTTPError as error:
        assert error.code == 403
    else:
        raise AssertionError("Direct access accepted outside ingress: " + request.full_url)
PY
