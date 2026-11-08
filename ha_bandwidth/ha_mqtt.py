"""Publish recorded traffic as Home Assistant MQTT discovery sensors."""

import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from paho.mqtt import client as mqtt

PERIODS = ("day", "week", "month", "year")
SOURCES = {"host": "Server", "openwrt": "OpenWrt WAN", "modem": "Modem",
           "app": "Apps", "device": "Apparaten", "peer": "IP-adressen"}
PERIOD_NAMES = {"day": "Vandaag", "week": "Deze week", "month": "Deze maand", "year": "Dit jaar"}
DIRECTIONS = {"rx": "Download", "tx": "Upload", "total": "Totaal"}
PREFIX = "ha_bandwidth"
LAST_PUBLISH = None


def groups(db, starts, end, include_ips):
    kinds = tuple(SOURCES) if include_ips else tuple(kind for kind in SOURCES if kind != "peer")
    placeholders = ", ".join("?" for _ in kinds)
    sums = ", ".join(
        f"SUM(CASE WHEN hour >= ? THEN {direction} END) AS {period}_{direction}"
        for period in PERIODS for direction in ("rx", "tx")
    )
    arguments = [starts[period] for period in PERIODS for _ in range(2)]
    columns = f"{sums}, MAX(label) AS label"
    where = "hour >= ? AND hour < ?"
    rows = db.execute(
        f"SELECT kind, {columns} FROM traffic WHERE {where} GROUP BY kind",
        (*arguments, min(starts.values()), end),
    )
    empty = dict.fromkeys(f"{period}_{direction}" for period in PERIODS for direction in ("rx", "tx"))
    result = {key: (label, empty) for key, label in SOURCES.items()}
    result.update({row["kind"]: (SOURCES[row["kind"]], row) for row in rows if row["kind"] in SOURCES})
    rows = db.execute(
        f"SELECT kind, source, {columns} FROM traffic WHERE {where} AND kind IN ({placeholders}) GROUP BY kind, source",
        (*arguments, min(starts.values()), end, *kinds),
    )
    for row in rows:
        if row["kind"] not in {"app", "device", "peer"}:
            continue
        key = row["kind"] + "_" + hashlib.sha256(row["source"].encode()).hexdigest()[:16]
        result[key] = (SOURCES[row["kind"]] + " · " + (row["label"] or row["source"]), row)
    return result


def sensor_payloads(values):
    for key, (label, row) in values.items():
        state = {}
        for period in PERIODS:
            rx, tx = row[period + "_rx"], row[period + "_tx"]
            state[period + "_rx"] = rx
            state[period + "_tx"] = tx
            state[period + "_total"] = rx + tx if rx is not None and tx is not None else None
        yield key, label, state


def discovery(key, label, field):
    suffix = f"{key}_{field}"
    entity = f"{PREFIX}_{suffix}"
    period, direction = field.split("_")
    return {
        "unique_id": entity,
        "default_entity_id": f"sensor.{entity}",
        "name": f"{label} · {PERIOD_NAMES[period]} · {DIRECTIONS[direction]}",
        "device": {"identifiers": [PREFIX], "name": "HA-Bandwidth"},
        "device_class": "data_size",
        "unit_of_measurement": "B",
        "state_topic": f"{PREFIX}/traffic/{key}",
        "value_template": "{{ value_json." + field + " }}",
        "expire_after": 240,
        "availability_topic": f"{PREFIX}/availability",
    }


def supervisor_get(path, timeout=4):
    request = Request("http://supervisor" + path, headers={
        "Authorization": "Bearer " + os.environ["SUPERVISOR_TOKEN"],
    })
    with build_opener(ProxyHandler({})).open(request, timeout=timeout) as response:
        return json.load(response)


def supervisor_mqtt():
    return supervisor_get("/services/mqtt")["data"]


def setup_status(enabled):
    broker = integration = entities = "unknown"
    try:
        service = supervisor_mqtt()
        broker = "ready" if service.get("host") and service.get("port") else "missing"
    except HTTPError as error:
        if error.code in (400, 404):
            broker = "missing"
    except (OSError, ValueError, KeyError):
        pass

    try:
        config = supervisor_get("/core/api/config")
        components = config.get("components")
        if isinstance(components, list):
            integration = "ready" if "mqtt" in components else "missing"
        if integration == "ready":
            state = supervisor_get("/core/api/states/sensor.ha_bandwidth_host_day_rx")
            entities = "pending" if state.get("state") == "unavailable" else "ready"
    except HTTPError as error:
        if integration == "ready" and error.code == 404:
            entities = "pending"
    except (OSError, ValueError, KeyError):
        pass
    publishing = LAST_PUBLISH is not None and time.monotonic() - LAST_PUBLISH < 180
    return {"broker": broker, "integration": integration, "entities": entities,
            "publisher": "disabled" if not enabled else "ready" if publishing else "pending"}


def send(client, topic, payload):
    result = client.publish(topic, payload, qos=1, retain=True)
    result.wait_for_publish(timeout=8)
    if not result.is_published():
        raise RuntimeError("MQTT-publicatie niet bevestigd")


def publish(database, zone, period_bounds, include_ips, registry_path):
    global LAST_PUBLISH
    registry = {}
    if registry_path.exists():
        try:
            registry = dict.fromkeys(json.loads(registry_path.read_text()))
        except (OSError, ValueError, TypeError):
            logging.warning("Home Assistant MQTT: sensorlijst kon niet worden gelezen")
    while True:
        client = None
        try:
            service = supervisor_mqtt()
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, reconnect_on_failure=False)
            if service.get("username"):
                client.username_pw_set(service["username"], service.get("password"))
            if service.get("ssl"):
                client.tls_set()
            client.will_set(f"{PREFIX}/availability", "offline", qos=1, retain=True)
            connected = threading.Event()

            def on_connect(_client, _userdata, _flags, reason, _properties):
                if not reason.is_failure:
                    connected.set()

            client.on_connect = on_connect
            client.connect(service["host"], int(service["port"]), keepalive=30)
            client.loop_start()
            if not connected.wait(10):
                raise RuntimeError("MQTT-verbinding niet bevestigd")
            sent = {}
            while client.is_connected():
                today = datetime.now(zone).date()
                starts = {period: period_bounds(today, period)[0].isoformat() for period in PERIODS}
                end = period_bounds(today, "day")[1].isoformat()
                with closing(database()) as db:
                    values = groups(db, starts, end, include_ips)
                current = {}
                for key, label, state in sensor_payloads(values):
                    for field in state:
                        topic = f"homeassistant/sensor/{PREFIX}/{key}_{field}/config"
                        payload = json.dumps(discovery(key, label, field), ensure_ascii=False)
                        if sent.get(topic) != payload:
                            send(client, topic, payload)
                        current[topic] = payload
                    send(client, f"{PREFIX}/traffic/{key}", json.dumps(state))
                for topic in registry.keys() - current.keys():
                    send(client, topic, "")
                if registry.keys() != current.keys():
                    temporary = registry_path.with_suffix(".tmp")
                    temporary.write_text(json.dumps(list(current)))
                    temporary.replace(registry_path)
                registry = dict.fromkeys(current)
                if not sent:
                    send(client, f"{PREFIX}/availability", "online")
                    logging.info("Home Assistant MQTT: %s verkeerssensoren aangeboden", len(current))
                LAST_PUBLISH = time.monotonic()
                sent = current
                time.sleep(60)
        except (OSError, KeyError, ValueError, RuntimeError, sqlite3.Error) as error:
            logging.warning("Home Assistant MQTT niet beschikbaar (%s)", type(error).__name__)
        finally:
            LAST_PUBLISH = None
            if client is not None:
                if client.is_connected():
                    try:
                        send(client, f"{PREFIX}/availability", "offline")
                    except (OSError, RuntimeError, ValueError):
                        pass
                client.disconnect()
                client.loop_stop()
        time.sleep(60)
