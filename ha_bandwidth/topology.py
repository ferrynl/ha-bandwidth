"""De netwerkkaart van de router: apparaten en hun verbindingen."""

import ipaddress
from urllib.parse import urlsplit


def router_topology(hosts, links, router_url):
    devices = {}
    try:
        router = str(ipaddress.ip_address(urlsplit(router_url).hostname))
    except ValueError:
        router = ""
    router_mac = hosts.get(router, {}).get("mac")
    for ip, host in hosts.items():
        mac = host["mac"]
        if ip == router or (router_mac and mac == router_mac):
            continue
        device = devices.setdefault(mac or ip, {"name": host["name"], "ips": [], **links.get(mac, {})})
        device["ips"].append(ip)
    for mac, link in links.items():
        if mac != router_mac:
            devices.setdefault(mac, {"name": "", "ips": [], **link})
    return [dict(device, source=key) for key, device in devices.items()]
