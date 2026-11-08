"""Create an editable Home Assistant dashboard through the Supervisor proxy."""

import itertools
import json
import logging
import os
import re
import time
from pathlib import Path

from websocket import WebSocketException, create_connection

from ha_mqtt import supervisor_get

DASHBOARD_PATH = "ha-bandwidth"
TEMPLATE = Path(__file__).with_name("lovelace.json")
INGRESS_MARKER = "__HA_BANDWIDTH_INGRESS__"


class CommandRejected(RuntimeError):
    """Home Assistant rejected the command explicitly."""


def dashboard_config(ingress):
    ingress = ingress.rstrip("/")
    if not re.fullmatch(r"/api/hassio_ingress/[A-Za-z0-9_-]+", ingress):
        raise ValueError("Ongeldig Home Assistant Ingress-pad")
    return json.loads(TEMPLATE.read_text(encoding="utf-8").replace(INGRESS_MARKER, ingress))


def create_dashboard(socket, config):
    ids = itertools.count(1)

    def command(kind, **data):
        request_id = next(ids)
        socket.send(json.dumps({"type": kind, "id": request_id, **data}))
        reply = json.loads(socket.recv())
        if reply.get("type") != "result" or reply.get("id") != request_id:
            raise RuntimeError("Onverwacht antwoord van Home Assistant")
        if not reply.get("success"):
            raise CommandRejected(kind)
        return reply.get("result")

    dashboards = command("lovelace/dashboards/list")
    existing = next((item for item in dashboards if item.get("url_path") == DASHBOARD_PATH), None)
    if existing is None:
        existing = next((item for item in dashboards if item.get("title") == config["title"]), None)
    if existing is not None:
        if existing.get("mode") != "storage" or not existing.get("url_path"):
            return "existing"
        path = existing["url_path"]
        current = command("lovelace/config", url_path=path, force=True)
        views = current.get("views", [])
        overview = config["views"][0]
        if any(view.get("path") == overview["path"] for view in views):
            return "existing"
        # Recognize the earlier HA-Bandwidth layout before touching a dashboard.
        card_urls = {card["url"] for view in config["views"][1:] for card in view["cards"]
                     if card["type"] == "iframe"}
        if not any(card.get("url") in card_urls for view in views for card in view.get("cards", [])):
            return "existing"
        command("lovelace/config/save", url_path=path, config={**current, "views": [overview, *views]})
        return "updated"

    created = command("lovelace/dashboards/create", url_path=DASHBOARD_PATH,
                      title=config["title"], icon="mdi:chart-timeline-variant",
                      show_in_sidebar=True, require_admin=True)
    try:
        command("lovelace/config/save", url_path=DASHBOARD_PATH, config=config)
    except CommandRejected:
        # Remove our new empty dashboard only after an explicit rejection.
        # A lost response could mean the save actually succeeded.
        command("lovelace/dashboards/delete", dashboard_id=created["id"])
        raise
    return "created"


def provision_dashboard():
    for attempt in range(3):
        socket = None
        try:
            app = supervisor_get("/addons/self/info")["data"]
            config = dashboard_config(app["ingress_url"])
            socket = create_connection("ws://supervisor/core/websocket", timeout=8)
            greeting = json.loads(socket.recv())
            if greeting.get("type") != "auth_required":
                raise RuntimeError("Home Assistant vroeg niet om WebSocket-authenticatie")
            socket.send(json.dumps({"type": "auth", "access_token": os.environ["SUPERVISOR_TOKEN"]}))
            if json.loads(socket.recv()).get("type") != "auth_ok":
                raise RuntimeError("Home Assistant WebSocket-authenticatie mislukt")
            result = create_dashboard(socket, config)
            if result == "created":
                logging.info("Home Assistant-dashboard aangemaakt: /%s", DASHBOARD_PATH)
            elif result == "updated":
                logging.info("Schermvullend overzicht toegevoegd aan het Home Assistant-dashboard")
            else:
                logging.info("Home Assistant-dashboard met dezelfde naam of hetzelfde pad bestaat al")
            return
        except (OSError, KeyError, TypeError, ValueError, RuntimeError, WebSocketException) as error:
            logging.warning("Home Assistant-dashboard aanmaken mislukt (%s)", type(error).__name__)
        finally:
            if socket is not None:
                socket.close()
        if attempt < 2:
            time.sleep(15)
