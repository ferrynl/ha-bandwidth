"""Passive destination accounting on Docker's Linux bridges."""

import ipaddress
import socket
import struct
import threading
import time
from collections import OrderedDict

TCP, UDP = 6, 17
PROTOCOLS = {1: "ICMP", TCP: "TCP", UDP: "UDP", 50: "ESP", 58: "ICMPv6"}


def u16(data, offset):
    return struct.unpack_from("!H", data, offset)[0]


def packet(frame):
    try:
        ethertype = u16(frame, 12)
        offset = 14
        while ethertype in (0x8100, 0x88A8):
            ethertype = u16(frame, offset + 2)
            offset += 4
        ip = frame[offset:]
        if ethertype == 0x0800 and len(ip) >= 20:
            src, dst = (socket.inet_ntop(socket.AF_INET, ip[i:i + 4]) for i in (12, 16))
            size, protocol = u16(ip, 2), ip[9]
            header = (ip[0] & 15) * 4
            fragment = bool(u16(ip, 6) & 0x1fff)
            if header < 20 or size < header:
                return None
        elif ethertype == 0x86dd and len(ip) >= 40:
            src, dst = (socket.inet_ntop(socket.AF_INET6, ip[i:i + 16]) for i in (8, 24))
            size, protocol, header, fragment = 40 + u16(ip, 4), ip[6], 40, False
            while protocol in (0, 43, 44, 51, 60) and not fragment:
                next_protocol, length = ip[header], ip[header + 1]
                if protocol == 44:
                    fragment = bool(u16(ip, header + 2) & 0xfff8)
                    header += 8
                elif protocol == 51:
                    header += (length + 2) * 4
                else:
                    header += (length + 1) * 8
                protocol = next_protocol
            if size < header:
                return None
        else:
            return None
        transport = ip[header:size]
        sport = dport = -1
        payload = b""
        syn = False
        if not fragment and protocol in (TCP, UDP) and len(transport) >= (20 if protocol == TCP else 8):
            sport, dport = struct.unpack_from("!HH", transport)
            if protocol == TCP:
                tcp_header = (transport[12] >> 4) * 4
                syn = (transport[13] & 0x12) == 0x02
                if tcp_header >= 20:
                    payload = transport[tcp_header:]
            else:
                payload = transport[8:u16(transport, 4)]
        return src, dst, size, protocol, sport, dport, syn, payload
    except (IndexError, struct.error):
        return None


def domain_name(value):
    value = value.decode("ascii").lower().rstrip(".")
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789-_."
    if 0 < len(value) <= 253 and all(c in allowed for c in value):
        return value
    return ""


def tls_name(payload):
    """Extract SNI from a complete, visible TLS ClientHello in this packet."""
    if not payload.startswith(b"\x16\x03") or len(payload) < 9 or payload[5] != 1:
        return ""
    try:
        record_end = 5 + u16(payload, 3)
        end = 9 + int.from_bytes(payload[6:9], "big")
        if end > min(len(payload), record_end):
            return ""
        cursor = 43
        cursor += 1 + payload[cursor]  # Session ID
        cursor += 2 + u16(payload, cursor)  # Cipher suites
        cursor += 1 + payload[cursor]  # Compression methods
        limit = cursor + 2 + u16(payload, cursor)
        cursor += 2
        if limit > end:
            return ""
        name = ""
        while cursor + 4 <= limit:
            extension, length = struct.unpack_from("!HH", payload, cursor)
            cursor += 4
            if cursor + length > limit or extension == 0xfe0d:  # Encrypted ClientHello
                return ""
            if extension == 0 and length >= 5 and payload[cursor + 2] == 0:
                count = u16(payload, cursor + 3)
                if count <= length - 5 and count + 3 <= u16(payload, cursor):
                    name = domain_name(payload[cursor + 5:cursor + 5 + count])
            cursor += length
        return name
    except (IndexError, UnicodeError, struct.error):
        return ""


def dns_name(message, offset):
    labels, end = [], None
    for _ in range(128):
        size = message[offset]
        if size >= 192:
            pointer = u16(message, offset) & 0x3fff
            if pointer >= offset:
                raise ValueError("Invalid DNS pointer")
            if end is None:
                end = offset + 2
            offset = pointer
        elif size == 0:
            return domain_name(b".".join(labels)), end if end is not None else offset + 1
        elif size <= 63 and offset + 1 + size < len(message):
            labels.append(message[offset + 1:offset + 1 + size])
            offset += 1 + size
        else:
            break
    raise ValueError("Invalid DNS name")


def dns_addresses(message):
    """Yield addresses in successful single-question DNS responses."""
    try:
        flags, questions, answers = struct.unpack_from("!HHH", message, 2)
        if flags & 0xfa0f != 0x8000 or questions != 1:
            return []
        name, offset = dns_name(message, 12)
        if not name:
            return []
        offset += 4
        records, aliases = [], {}
        for _ in range(min(answers, 128)):
            owner, offset = dns_name(message, offset)
            kind, cls, ttl, size = struct.unpack_from("!HHIH", message, offset)
            offset += 10
            value = message[offset:offset + size]
            if len(value) != size:
                return []
            if cls == 1 and (kind, size) in ((1, 4), (28, 16)):
                family = socket.AF_INET if kind == 1 else socket.AF_INET6
                records.append((owner, socket.inet_ntop(family, value), ttl))
            elif cls == 1 and kind == 5:
                alias, end = dns_name(message, offset)
                if end <= offset + size:
                    aliases[owner] = (alias, ttl)
            offset += size
        chain = {name: 3600}
        owner = name
        while owner in aliases:
            alias, ttl = aliases[owner]
            if alias in chain:
                break
            chain[alias] = min(chain[owner], ttl)
            owner = alias
        return [(ip, name, min(ttl, chain[owner])) for owner, ip, ttl in records if owner in chain]
    except (IndexError, ValueError, struct.error):
        return []


def bridge_apps(networks, containers):
    bridges = {
        network["Id"]: (network.get("Options") or {}).get("com.docker.network.bridge.name")
        or ("docker0" if network["Name"] == "bridge" else "br-" + network["Id"][:12])
        for network in networks if network["Driver"] == "bridge"
    }
    groups = {}
    for container in containers:
        mode = container["HostConfig"]["NetworkMode"]
        if mode in ("host", "none") or mode.startswith("container:"):
            continue
        owner = (container["Names"][0].lstrip("/"), container["Id"])
        for endpoint in (container.get("NetworkSettings") or {}).get("Networks", {}).values():
            bridge = bridges.get(endpoint.get("NetworkID"))
            if bridge:
                for field in ("IPAddress", "GlobalIPv6Address"):
                    address = endpoint.get(field)
                    if address:
                        groups.setdefault(bridge, {})[str(ipaddress.ip_address(address))] = owner
    return groups


class BridgeCapture:
    def __init__(self, interface, owners):
        self.interface = interface
        self.owners = owners
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.error = None
        self.totals = {}
        self.tls = OrderedDict()
        self.dns = OrderedDict()
        self.worker = threading.Thread(target=self.run, daemon=True)
        self.worker.start()

    def run(self):
        try:
            with socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3)) as sock:
                sock.bind((self.interface, 3))
                index = socket.if_nametoindex(self.interface)
                # SOL_PACKET / PACKET_ADD_MEMBERSHIP / PACKET_MR_PROMISC.
                # Membership ends automatically when this socket closes.
                sock.setsockopt(263, 1, struct.pack("=iHH8s", index, 1, 0, b""))
                sock.settimeout(0.5)
                while not self.stop.is_set():
                    try:
                        frame, _ = sock.recvfrom(8192)
                    except TimeoutError:
                        continue
                    parsed = packet(frame)
                    if parsed:
                        with self.lock:
                            self.observe(parsed)
        except OSError as error:
            self.error = str(error)

    def observe(self, parsed):
        src, dst, size, protocol, sport, dport, syn, payload = parsed
        sender, receiver = self.owners.get(src), self.owners.get(dst)
        if not sender and not receiver:
            return
        now = time.monotonic()
        for owner, outgoing, local, local_port, peer, remote_port in (
            (sender, True, src, sport, dst, dport),
            (receiver, False, dst, dport, src, sport),
        ):
            if owner is None or sender == receiver:
                continue
            flow = (owner, local, local_port, peer, remote_port, protocol)
            if syn:
                self.tls.pop(flow, None)
            name = tls_name(payload) if protocol == TCP and outgoing else ""
            if name:
                self.tls[flow] = name
                self.tls.move_to_end(flow)
                if len(self.tls) > 8192:
                    self.tls.popitem(last=False)
            if not outgoing and remote_port == 53 and protocol in (TCP, UDP):
                message = payload
                if protocol == TCP:
                    message = payload[2:2 + u16(payload, 0)] if len(payload) >= 2 else b""
                for address, domain, ttl in dns_addresses(message):
                    key = (owner, address, domain)
                    self.dns[key] = now + ttl
                    self.dns.move_to_end(key)
                    if len(self.dns) > 8192:
                        self.dns.popitem(last=False)
            if len(self.totals) >= 4096 and flow not in self.totals:
                flow = (owner, "", -1, "", -1, -1)
            self.totals.setdefault(flow, [0, 0])[outgoing] += size

    def drain(self):
        with self.lock:
            now = time.monotonic()
            hints = {}
            for (owner, peer, domain), expiry in self.dns.items():
                if expiry > now:
                    hints.setdefault((owner, peer), set()).add(domain)
            rows = []
            for flow, (rx, tx) in self.totals.items():
                owner, _, _, peer, port, protocol = flow
                name = self.tls.get(flow, "")
                candidates = hints.get((owner, peer), set())
                evidence = "TLS" if name else ""
                if not name and len(candidates) == 1:
                    name = next(iter(candidates))
                    evidence = "DNS"
                rows.append((owner[0], peer, protocol, port, name, evidence, rx, tx))
            self.totals.clear()
            return rows

    def close(self):
        self.stop.set()
        self.worker.join(timeout=1)


class AppDestinations:
    def __init__(self):
        self.captures = {}

    def collect(self, owners):
        rows, errors = [], []
        for bridge, capture in list(self.captures.items()):
            if bridge not in owners or capture.error:
                capture.close()
                rows.extend(capture.drain())
                if capture.error:
                    errors.append(f"{bridge}: {capture.error}")
                del self.captures[bridge]
        for bridge, endpoints in owners.items():
            if bridge in self.captures:
                capture = self.captures[bridge]
                with capture.lock:
                    capture.owners = endpoints
            else:
                self.captures[bridge] = BridgeCapture(bridge, endpoints)
            rows.extend(self.captures[bridge].drain())
        return rows, errors

