"use strict";

const el = id => document.getElementById(id);
const format = new Intl.NumberFormat("nl-NL", {maximumFractionDigits: 2});
const views = {
  device: ["Internetverkeer per wifi- of bekabeld apparaat via OpenWrt Bandwidth Monitor. Klik op een apparaat om alleen het verkeer daarvan te bekijken.", "Verkeer per apparaat"],
  compare: ["OpenWrt WAN telt het internetverkeer van alle apparaten die via de router online gaan. De HA-server telt op zijn eigen netwerkinterface ook lokaal verkeer mee.", ""],
  host: ["Netwerkinterface van de server. Lokaal verkeer en internetverkeer zitten in dit totaal.", "Verkeer per netwerkinterface"],
  app: ["Verkeer van containers met eigen tellers. Dit kan intern Docker-verkeer bevatten en overlapt deels met het servertotaal.", "Top 30 apps en containers"],
  peer: ["Bron-IP voor downloads en doel-IP voor uploads op de serverinterface. Dit zijn waargenomen IP-bytes.", "Top 30 IP-adressen"],
};
const months = ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"];
let kind = "host";
let period = "day";
let source = "";
let sourceLabel = "";
let request = 0;
let focusDestinations = false;
const tableControls = new Map();
const ipDetails = new Map();
const tableCollator = new Intl.Collator("nl-NL", {numeric: true, sensitivity: "base"});

function updateTable(id) {
  const body = el(id);
  const table = body.closest("table");
  let control = tableControls.get(id);
  if (!control) {
    const input = document.createElement("input");
    input.type = "search";
    input.className = "table-filter";
    input.placeholder = "Filter deze tabel…";
    input.setAttribute("aria-label", "Filter " + ({
      rows: "verkeer", "destination-rows": "bestemmingen", "comparison-rows": "vergelijking",
    })[id]);
    table.parentElement.before(input);
    control = {input, views: new Map(), headings: [...table.querySelectorAll("th")]};
    tableControls.set(id, control);
    input.addEventListener("input", () => {
      control.state.query = input.value;
      updateTable(id);
    });
    control.headings.forEach((heading, column) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "sort-header";
      button.textContent = heading.textContent;
      heading.replaceChildren(button);
      button.addEventListener("click", () => {
        const state = control.state;
        state.direction = state.column === column ? -state.direction
          : column >= control.headings.length - 3 ? -1 : 1;
        state.column = column;
        updateTable(id);
      });
    });
  }
  if (!control.views.has(kind)) {
    control.views.set(kind, {query: "", column: control.headings.length - 1, direction: -1});
  }
  const state = control.views.get(kind);
  control.state = state;
  if (control.input.value !== state.query) control.input.value = state.query;
  control.input.hidden = body.rows.length === 0;
  const tokens = state.query.toLocaleLowerCase("nl-NL").trim().split(/\s+/).filter(Boolean);
  const rows = [...body.rows];
  rows.sort((left, right) => {
    const a = left.cells[state.column];
    const b = right.cells[state.column];
    const an = a.dataset.sortNumber;
    const bn = b.dataset.sortNumber;
    if (an === undefined && bn !== undefined) return 1;
    if (an !== undefined && bn === undefined) return -1;
    const order = an !== undefined ? Number(an) - Number(bn) : tableCollator.compare(a.textContent, b.textContent);
    return state.direction * order;
  });
  for (const row of rows) {
    const searchable = (row.textContent + " " + (row.dataset.search || "")).toLocaleLowerCase("nl-NL");
    row.hidden = !tokens.every(token => searchable.includes(token));
    body.append(row);
  }
  control.headings.forEach((heading, column) => {
    if (column === state.column) heading.setAttribute("aria-sort", state.direction === 1 ? "ascending" : "descending");
    else heading.removeAttribute("aria-sort");
  });
}

function countCells(row, rx, tx, available = true) {
  for (const value of [rx, tx, rx + tx]) {
    const cell = row.insertCell();
    cell.textContent = available ? bytes(value) : "—";
    if (available) cell.dataset.sortNumber = value;
  }
}

function addRouterHost(cell, host) {
  if (!host) return;
  const label = document.createElement("span");
  label.className = "ip-result";
  label.textContent = [host.name || "Apparaat zonder naam", host.mac].filter(Boolean).join(" · ");
  label.title = "Huidige apparaatkoppeling uit OpenWrt";
  cell.append(label);
}

function addIpLookup(cell, ip, tableId) {
  if (!ip) return;
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "IPinfo";
  button.className = "ip-lookup";
  button.setAttribute("aria-label", "Zoek netwerk en domein op voor " + ip);
  const result = document.createElement("span");
  result.className = "ip-result";
  result.setAttribute("role", "status");
  const render = () => {
    const details = ipDetails.get(ip);
    button.disabled = details?.pending === true;
    result.textContent = details?.pending ? "Netwerk opzoeken…"
      : details?.error || (details && [details.asn, details.as_name, details.as_domain].filter(Boolean).join(" · "))
        || (details ? "Geen netwerkgegevens gevonden." : "");
    if (details && !details.pending) {
      const link = document.createElement("a");
      link.href = "https://ipinfo.io/" + encodeURIComponent(ip);
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "Bekijk op IPinfo";
      result.append(" ", link);
    }
    cell.parentElement.dataset.search = ip + " " + result.textContent;
  };
  button.addEventListener("click", async () => {
    if (!ipDetails.has(ip) || ipDetails.get(ip).error) {
      ipDetails.set(ip, {pending: true});
      render();
      try {
        const response = await fetch("./api/ipinfo?" + new URLSearchParams({ip}));
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "IPinfo ophalen mislukt.");
        ipDetails.set(ip, data);
      } catch (error) {
        ipDetails.set(ip, {error: error.message});
      }
    }
    for (const refresh of el(tableId).querySelectorAll(".ip-lookup")) {
      if (refresh.dataset.ip === ip) refresh.refreshIpDetails();
    }
    updateTable(tableId);
  });
  button.dataset.ip = ip;
  button.refreshIpDetails = render;
  cell.append(button, result);
  render();
}

function bytes(value) {
  let index = 0;
  const units = ["B", "kB", "MB", "GB", "TB", "PB"];
  while (value >= 1000 && index < units.length - 1) {
    value /= 1000;
    index += 1;
  }
  return format.format(value) + " " + units[index];
}

function timeline(data) {
  const values = new Map(data.buckets.map(row => [row.bucket, row]));
  const router = new Map((data.router_buckets || []).map(row => [row.bucket, row]));
  const modem = new Map((data.modem_buckets || []).map(row => [row.bucket, row]));
  const slots = [];
  if (period === "day") {
    for (let hour = 0; hour < 24; hour++) {
      const label = String(hour).padStart(2, "0");
      slots.push([data.start + "T" + label, hour % 3 === 0 ? label + "u" : ""]);
    }
  } else if (period === "year") {
    months.forEach((month, index) => {
      slots.push([data.start.slice(0, 4) + "-" + String(index + 1).padStart(2, "0"), month]);
    });
  } else {
    const cursor = new Date(data.start + "T00:00:00Z");
    for (let index = 0; cursor.toISOString().slice(0, 10) <= data.end; index++) {
      const key = cursor.toISOString().slice(0, 10);
      slots.push([key, period === "week" || index % 3 === 0 ? key.slice(8) : ""]);
      cursor.setUTCDate(cursor.getUTCDate() + 1);
    }
  }
  const peak = Math.max(1, ...[...values.values(), ...router.values(), ...modem.values()].flatMap(row => [row.rx, row.tx]));
  const axis = [1, .75, .5, .25, 0].map(fraction => {
    const label = document.createElement("span");
    label.textContent = bytes(peak * fraction);
    return label;
  });
  el("axis").replaceChildren(...axis);
  el("chart").replaceChildren(...slots.map(([key, tick]) => {
    const value = values.get(key);
    const wan = router.get(key);
    const cellular = modem.get(key);
    const group = document.createElement("div");
    group.className = "bucket";
    const summary = [];
    if (value) summary.push((kind === "compare" ? "HA " : "") + "Download " + bytes(value.rx) + " / Upload " + bytes(value.tx));
    if (wan) summary.push(data.router_label + " download " + bytes(wan.rx) + " / upload " + bytes(wan.tx));
    if (cellular) summary.push(data.modem_label + " download " + bytes(cellular.rx) + " / upload " + bytes(cellular.tx));
    group.title = key + " · " + (summary.join(" · ") || "Geen meting");
    if (summary.length) group.tabIndex = 0;
    group.setAttribute("aria-label", group.title);
    const columns = document.createElement("div");
    columns.className = "columns";
    const series = [["rx", value?.rx], ["tx", value?.tx]];
    if (kind === "compare") series.push(["modem-rx", wan?.rx], ["modem-tx", wan?.tx],
      ["cellular-rx", cellular?.rx], ["cellular-tx", cellular?.tx]);
    for (const [direction, count] of series) {
      const bar = document.createElement("span");
      bar.className = "bar " + direction;
      bar.style.height = (100 * (count ?? 0) / peak) + "%";
      columns.append(bar);
    }
    const label = document.createElement("span");
    label.className = "tick";
    label.textContent = tick;
    group.append(columns, label);
    return group;
  }));
}

function table(rows) {
  const body = el("rows");
  body.replaceChildren();
  for (const row of rows) {
    const tr = body.insertRow();
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = row.label;
    button.title = row.source;
    button.setAttribute("aria-pressed", String(row.source === source));
    button.addEventListener("click", () => {
      source = row.source;
      sourceLabel = row.label;
      focusDestinations = kind === "app";
      load();
    });
    tr.dataset.search = row.source;
    const cell = tr.insertCell();
    cell.append(button);
    addRouterHost(cell, row.router_host);
    addIpLookup(cell, row.lookup_ip, "rows");
    countCells(tr, row.rx, row.tx);
  }
  updateTable("rows");
}

function showDestinations(data) {
  const section = el("destinations");
  section.hidden = kind !== "host" && (kind !== "app" || !source);
  if (section.hidden) {
    focusDestinations = false;
    return;
  }
  const title = el("destinations-title");
  title.textContent = kind === "host" ? "Grootste bronnen en bestemmingen van de server" : "Bestemmingen · " + sourceLabel;
  const rows = data.destinations;
  const body = el("destination-rows");
  body.replaceChildren();
  el("destinations-table").hidden = rows.length === 0;
  let note = "Waargenomen IP-verkeer. TLS geeft een zichtbare domeinnaam aan. DNS is een aanwijzing.";
  if (rows.length === 0) {
    const enabled = kind === "host" ? data.status.peers_enabled : data.status.app_destinations_enabled;
    note = enabled === false
      ? "De bestemmingsmeting staat uit."
      : kind === "host"
        ? "Nog geen bronnen of bestemmingen gemeten voor deze periode. De serverdetails beginnen bij versie 0.5.0."
        : "Geen bestemmingen gemeten voor deze app en periode.";
  } else {
    if (kind === "host") note += " Bij download zie je het bron-IP. Bij upload zie je het doel-IP.";
    if (rows.some(row => row.router_host)) note += " Apparaatnamen en MAC-adressen komen uit de huidige OpenWrt-lijst.";
    if (data.destinations_truncated) note += " De tabel toont de 100 grootste regels.";
  }
  el("destinations-note").textContent = note;
  for (const row of rows) {
    const tr = body.insertRow();
    const domain = row.domain ? row.domain + " (" + row.evidence + ")" : "";
    const name = row.router_host?.name || "";
    tr.insertCell().textContent = [domain, name].filter(Boolean).join(" · ") || "—";
    const ipCell = tr.insertCell();
    ipCell.textContent = row.ip || "Overige verbindingen";
    if (row.router_host?.mac) {
      const mac = document.createElement("span");
      mac.className = "ip-result";
      mac.textContent = row.router_host.mac;
      ipCell.append(mac);
    }
    addIpLookup(ipCell, row.lookup_ip, "destination-rows");
    tr.insertCell().textContent = row.scope;
    tr.insertCell().textContent = row.protocol || "—";
    const port = tr.insertCell();
    port.textContent = row.port >= 0 ? row.port : "—";
    if (row.port >= 0) port.dataset.sortNumber = row.port;
    countCells(tr, row.rx, row.tx);
  }
  updateTable("destination-rows");
  if (focusDestinations) {
    focusDestinations = false;
    title.focus();
  }
}

function showComparison(data) {
  const body = el("comparison-rows");
  body.replaceChildren();
  el("router-download-legend").textContent = "● " + data.router_label + " download";
  el("router-upload-legend").textContent = "● " + data.router_label + " upload";
  el("cellular-download-legend").textContent = "● " + data.modem_label + " download";
  el("cellular-upload-legend").textContent = "● " + data.modem_label + " upload";
  for (const [label, values] of [["HA-server", data.buckets], [data.router_label, data.router_buckets], [data.modem_label, data.modem_buckets]]) {
    const row = body.insertRow();
    row.insertCell().textContent = label;
    const rx = values.reduce((total, item) => total + item.rx, 0);
    const tx = values.reduce((total, item) => total + item.tx, 0);
    countCells(row, rx, tx, values.length > 0);
  }
  updateTable("comparison-rows");
  const device = data.status.router_device ? "OpenWrt-interface actief: " + data.status.router_device + "." : "";
  const routerStatus = data.status.router_error || (data.status.router_configured
    ? device : "OpenWrt is niet ingesteld.");
  const modemStatus = data.status.modem_error || (!data.status.modem_configured
    ? "Vul modem_download_entity en modem_upload_entity in bij Configuratie."
    : data.modem_buckets.length ? "" : "Nog geen modemmetingen voor deze periode.");
  el("modem-status").textContent = [routerStatus, modemStatus].filter(Boolean).join(" · ");
}

const map = el("topology-map");
const viewport = el("topology-viewport");
const positions = new Map();
const pointers = new Map();
const collapsedGroups = new Set();
let graphData, gesture, selectedDevice;
let nodes = [], edges = [];
let camera = {x: 480, y: 220, scale: 1};
let refit = true;

function svg(tag, attributes = {}) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, value);
  return element;
}

function paintMap() {
  viewport.setAttribute("transform", `translate(${camera.x} ${camera.y}) scale(${camera.scale})`);
  for (const {element, point} of nodes) element.setAttribute("transform", `translate(${point.x} ${point.y})`);
  for (const {line, from, to} of edges) {
    line.setAttribute("x1", from.x);
    line.setAttribute("y1", from.y);
    line.setAttribute("x2", to.x);
    line.setAttribute("y2", to.y);
  }
}

function zoomMap(factor, from, to = from) {
  const scale = Math.max(.12, Math.min(6, camera.scale * factor));
  const ratio = scale / camera.scale;
  camera = {x: to.x - (from.x - camera.x) * ratio, y: to.y - (from.y - camera.y) * ratio, scale};
  paintMap();
}

function fitMap() {
  if (!nodes.length) return;
  const xs = nodes.map(({point}) => point.x), ys = nodes.map(({point}) => point.y);
  const left = Math.min(...xs) - 35, right = Math.max(...xs) + 175;
  const top = Math.min(...ys) - 40, bottom = Math.max(...ys) + 45;
  const scale = Math.min(1.4, 900 / (right - left), 415 / (bottom - top));
  camera = {x: 480 - (left + right) * scale / 2, y: 240 - (top + bottom) * scale / 2, scale};
  paintMap();
}

function mapPoint(event) {
  return new DOMPoint(event.clientX, event.clientY).matrixTransform(map.getScreenCTM().inverse());
}

map.addEventListener("wheel", event => {
  event.preventDefault();
  zoomMap(Math.exp(-Math.max(-150, Math.min(150, event.deltaY)) * .003), mapPoint(event));
}, {passive: false});
map.addEventListener("pointerdown", event => {
  if (event.button !== 0) return;
  const point = mapPoint(event);
  if (!pointers.size) gesture = {id: event.target.closest("[data-node]")?.dataset.node, start: point, moved: false};
  else gesture.moved = true;
  pointers.set(event.pointerId, point);
  map.setPointerCapture(event.pointerId);
});
map.addEventListener("pointermove", event => {
  const last = pointers.get(event.pointerId);
  if (!last) return;
  const point = mapPoint(event);
  if (pointers.size === 2) {
    const other = [...pointers].find(([id]) => id !== event.pointerId)[1];
    const distance = Math.hypot(last.x - other.x, last.y - other.y);
    const middle = p => ({x: (p.x + other.x) / 2, y: (p.y + other.y) / 2});
    if (distance) zoomMap(Math.hypot(point.x - other.x, point.y - other.y) / distance, middle(last), middle(point));
  } else if (pointers.size === 1) {
    const {start} = gesture;
    if (gesture.moved || Math.hypot(point.x - start.x, point.y - start.y) > 4) {
      gesture.moved = true;
      const node = positions.get(gesture.id);
      if (node) {
        node.x += (point.x - last.x) / camera.scale;
        node.y += (point.y - last.y) / camera.scale;
      } else {
        camera.x += point.x - last.x;
        camera.y += point.y - last.y;
      }
      paintMap();
    }
  }
  pointers.set(event.pointerId, point);
});
function finishMapGesture(event) {
  if (!pointers.delete(event.pointerId)) return;
  if (pointers.size) {
    gesture.id = "";
    return;
  }
  const {id, moved} = gesture;
  gesture = null;
  if (!moved && event.type === "pointerup") nodes.find(node => node.id === id)?.action?.();
}
for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) map.addEventListener(type, finishMapGesture);
el("topology-zoom-in").onclick = () => zoomMap(1.25, {x: 480, y: 240});
el("topology-zoom-out").onclick = () => zoomMap(.8, {x: 480, y: 240});
el("topology-fit").onclick = fitMap;
el("topology-search").addEventListener("input", () => {
  refit = true;
  if (graphData) showTopology(graphData);
});

function showTopology(data) {
  el("topology-panel").hidden = kind !== "device";
  if (kind !== "device") return;
  graphData = data;
  if (pointers.size) return;

  const measured = new Map(data.rows.map(row => [row.source, row]));
  const devices = new Map(data.topology.map(device => [device.source, device]));
  for (const row of data.rows) {
    if (!devices.has(row.source)) devices.set(row.source, {source: row.source, name: row.label, ips: [], ssid: ""});
  }
  const search = el("topology-search").value.trim().toLocaleLowerCase("nl-NL");
  const groups = new Map();
  for (const device of devices.values()) {
    if (search && ![device.name, device.source, device.ssid, device.connection, device.port, ...device.ips].join(" ").toLocaleLowerCase("nl-NL").includes(search)) continue;
    const name = device.connection || "Aansluiting niet gemeten";
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(device);
  }
  el("topology-note").textContent = devices.size
    ? devices.size + " apparaten · Sleep een knooppunt of de achtergrond. Zoom met het muiswiel of twee vingers."
    : "Nog geen apparaten beschikbaar.";
  el("topology-cloud").hidden = !devices.size;
  el("topology-search").hidden = !devices.size;
  el("topology-no-match").hidden = groups.size > 0;
  map.toggleAttribute("hidden", !groups.size);

  const focused = document.activeElement?.dataset.node;
  const edgeLayer = svg("g", {"aria-hidden": "true"});
  const nodeLayer = svg("g");
  viewport.replaceChildren(edgeLayer, nodeLayer);
  nodes = [];
  edges = [];

  function select(id) {
    selectedDevice = id;
    const device = devices.get(id), row = measured.get(id);
    el("topology-detail").hidden = !device;
    for (const node of nodes) {
      if (node.type === "client") node.element.setAttribute("aria-pressed", String(node.id === "device:" + id));
    }
    if (!device) return;
    el("topology-device-name").textContent = device.name || device.ips[0] || id;
    el("topology-device-address").textContent = [...new Set([...device.ips, id])].join(" · ") + (device.connection ? " · " + [device.connection, device.ssid, device.port].filter(Boolean).join(" · ") : "");
    el("topology-device-traffic").textContent = row
      ? "Download " + bytes(row.rx) + " · Upload " + bytes(row.tx) : "Geen meting in deze periode.";
    const button = el("topology-graph");
    button.hidden = !row;
    button.onclick = row ? () => {
      source = id;
      sourceLabel = row.label;
      load();
      el("chart-title").scrollIntoView({block: "nearest"});
    } : null;
  }

  function add(id, name, type, x, y, parent, action) {
    if (!positions.has(id)) positions.set(id, {x, y});
    const point = positions.get(id);
    if (parent) {
      const line = svg("line", {class: "map-edge map-edge-" + type});
      edgeLayer.append(line);
      edges.push({line, from: parent, to: point});
    }
    const element = svg("g", {class: "map-node map-" + type, "data-node": id, "aria-label": name});
    if (action) {
      element.setAttribute("role", "button");
      element.setAttribute("tabindex", "0");
      element.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          action();
        }
      });
    }
    const title = svg("title");
    title.textContent = name;
    const marker = type === "client" ? svg("circle", {r: 8}) : svg("rect", {x: -12, y: -12, width: 24, height: 24, rx: 6});
    const label = svg("text", {x: 17, y: 4});
    label.textContent = name.length > 24 ? name.slice(0, 23) + "…" : name;
    element.append(title, marker, label);
    nodeLayer.append(element);
    nodes.push({id, type, element, point, action});
    return point;
  }

  if (groups.size) {
    const modem = data.upstream_modem;
    const internet = add("internet", "Internet", "internet", 0, modem?.name ? -165 : -105);
    const upstream = modem?.name
      ? add("upstream-modem", [modem.name, modem.ip].filter(Boolean).join(" · "), "router", 0, -80, internet)
      : internet;
    const router = add("router", "OpenWrt", "router", 0, 0, upstream);
    const branches = [...groups].sort(([a], [b]) => tableCollator.compare(a, b));
    const sector = 2 * Math.PI / branches.length;
    branches.forEach(([name, clients], index) => {
      const id = "group:" + name;
      const open = Boolean(search) || !collapsedGroups.has(id);
      const center = Math.PI / 2 + index * sector;
      const radius = branches.length === 1 ? 105 : 195;
      const group = add(id, name + " (" + clients.length + ")", "group",
        Math.cos(center) * radius, Math.sin(center) * radius, router, search ? null : () => {
          if (collapsedGroups.has(id)) collapsedGroups.delete(id);
          else collapsedGroups.add(id);
          refit = true;
          showTopology(graphData);
        });
      if (!search) nodes.at(-1).element.setAttribute("aria-expanded", String(open));
      if (!open) return;
      clients.sort((a, b) => tableCollator.compare(a.name || a.source, b.name || b.source));
      let offset = 0;
      for (let ring = 0; offset < clients.length; ring++) {
        const distance = 330 + ring * 125;
        const span = sector * .82;
        const count = Math.min(clients.length - offset, Math.max(1, Math.floor(span * distance / 185)));
        for (let i = 0; i < count; i++) {
          const client = clients[offset + i];
          const angle = center + span * ((i + .5) / count - .5);
          add("device:" + client.source, client.name || client.ips[0] || client.source, "client",
            Math.cos(angle) * distance, Math.sin(angle) * distance, group, () => select(client.source));
        }
        offset += count;
      }
    });
  }
  select(selectedDevice);
  if (refit && nodes.length) {
    fitMap();
    refit = false;
  } else paintMap();
  if (focused) nodes.find(node => node.id === focused)?.element.focus({preventScroll: true});
}

function show(data) {
  const status = data.status;
  el("status").textContent = status.updated
    ? (status.interface || "Interface onbekend") + " · laatste meetronde " +
      new Date(status.updated).toLocaleTimeString("nl-NL", {timeZone: status.zone}) +
      (data.first ? " · historie vanaf " + data.first.slice(0, 10) : "")
    : "Wachten op de eerste meetronde";
  const warnings = [...(status.errors || [])];
  if (["host", "peer", "app"].includes(kind) && status.host_hints_error) {
    warnings.push("OpenWrt-apparaatnamen niet beschikbaar. " + status.host_hints_error);
  }
  if (kind === "device") {
    if (status.device_error) warnings.push(status.device_error);
    else if (status.device_configured === false) warnings.push("Stel OpenWrt in onder HA-Bandwidth → Configuratie.");
  }
  if (kind === "peer" && status.peers_enabled === false) warnings.push("IP-meting staat uit.");
  el("warnings").hidden = warnings.length === 0;
  el("warnings").textContent = warnings.join(" · ");
  el("range").textContent = data.start === data.end ? data.start : data.start + " t/m " + data.end;
  const comparing = kind === "compare";
  el("comparison").hidden = !comparing;
  el("comparison-legend").hidden = !comparing;
  el("legend").hidden = comparing;
  el("totals").hidden = comparing;
  el("ranking-panel").hidden = comparing;
  if (comparing) showComparison(data);
  const rx = data.buckets.reduce((total, row) => total + row.rx, 0);
  const tx = data.buckets.reduce((total, row) => total + row.tx, 0);
  const hasData = data.buckets.length > 0 || Boolean(data.router_buckets?.length || data.modem_buckets?.length);
  el("download").textContent = hasData ? bytes(rx) : "—";
  el("upload").textContent = hasData ? bytes(tx) : "—";
  el("total").textContent = hasData ? bytes(rx + tx) : "—";
  el("chart-title").textContent = sourceLabel || "Verkeer over tijd";
  el("clear").hidden = !source;
  el("empty").hidden = hasData;
  el("chart").parentElement.hidden = !hasData;
  if (hasData) timeline(data);
  if (!comparing) table(data.rows);
  showDestinations(data);
  showTopology(data);
  el("shared-section").hidden = kind !== "app" || !(status.shared?.length || status.unavailable?.length);
  el("shared").textContent = status.shared?.join(", ") || "";
  el("unavailable").textContent = status.unavailable?.length
    ? "Actief zonder bruikbare tellers: " + status.unavailable.join(", ") : "";
}

async function backupStatus() {
  try {
    const response = await fetch("./api/backup/status");
    if (!response.ok) return;
    const data = await response.json();
    el("previous-backup").hidden = !data.previous;
  } catch {
    // Back-up download and restore remain available if this check fails.
  }
}

el("restore-form").addEventListener("submit", async event => {
  event.preventDefault();
  const file = el("restore-file").files[0];
  if (!file || !el("restore-confirm").checked) return;
  const status = el("backup-status");
  if (file.size > 256 * 1024 * 1024) {
    status.textContent = "Het bestand is groter dan 256 MiB.";
    return;
  }
  const button = el("restore-button");
  button.disabled = true;
  status.textContent = "Back-up terugzetten…";
  try {
    const response = await fetch("./api/backup/restore", {
      method: "POST",
      headers: {"Content-Type": "application/octet-stream", "X-HA-Bandwidth-Restore": "1"},
      body: file,
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || "HTTP " + response.status);
    event.target.reset();
    status.textContent = "De meetgegevens zijn teruggezet.";
    await backupStatus();
  } catch (error) {
    status.textContent = "Terugzetten mislukt. " + error.message;
  } finally {
    button.disabled = false;
  }
});

async function load() {
  const id = ++request;
  const backup = kind === "backup";
  el("backup-panel").hidden = !backup;
  el("measurement-panel").hidden = backup;
  if (backup) {
    await backupStatus();
    return;
  }
  const params = new URLSearchParams({kind, period, source});
  if (el("date").value) params.set("date", el("date").value);
  el("explanation").textContent = views[kind][0];
  el("ranking").textContent = views[kind][1];
  try {
    const response = await fetch("./api/traffic?" + params);
    if (!response.ok) throw new Error("HTTP " + response.status);
    const data = await response.json();
    if (id === request) show(data);
  } catch (error) {
    if (id !== request) return;
    el("warnings").hidden = false;
    el("warnings").textContent = "Dashboard kon de metingen niet ophalen (" + error.message + ").";
    el("destinations").hidden = true;
  }
}

for (const [key, change] of [
  ["kind", value => { kind = value; source = ""; sourceLabel = ""; }],
  ["period", value => { period = value; }],
]) {
  const buttons = document.querySelectorAll("[data-" + key + "]");
  for (const button of buttons) {
    button.addEventListener("click", () => {
      change(button.dataset[key]);
      for (const item of buttons) item.setAttribute("aria-pressed", String(item === button));
      load();
    });
  }
}
el("date").addEventListener("change", load);
el("today").addEventListener("click", () => { el("date").value = ""; load(); });
el("clear").addEventListener("click", () => { source = ""; sourceLabel = ""; load(); });
load();
setInterval(load, 30000);

