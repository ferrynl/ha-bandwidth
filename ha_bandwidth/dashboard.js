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
  const peak = Math.max(1, ...[...values.values(), ...modem.values()].flatMap(row => [row.rx, row.tx]));
  const axis = [1, .75, .5, .25, 0].map(fraction => {
    const label = document.createElement("span");
    label.textContent = bytes(peak * fraction);
    return label;
  });
  el("axis").replaceChildren(...axis);
  el("chart").replaceChildren(...slots.map(([key, tick]) => {
    const value = values.get(key);
    const wan = modem.get(key);
    const group = document.createElement("div");
    group.className = "bucket";
    const summary = [];
    if (value) summary.push((kind === "compare" ? "HA " : "") + "Download " + bytes(value.rx) + " / Upload " + bytes(value.tx));
    if (wan) summary.push(data.router_label + " download " + bytes(wan.rx) + " / upload " + bytes(wan.tx));
    group.title = key + " · " + (summary.join(" · ") || "Geen meting");
    if (summary.length) group.tabIndex = 0;
    group.setAttribute("aria-label", group.title);
    const columns = document.createElement("div");
    columns.className = "columns";
    const series = [["rx", value?.rx], ["tx", value?.tx]];
    if (kind === "compare") series.push(["modem-rx", wan?.rx], ["modem-tx", wan?.tx]);
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
    if (data.destinations_truncated) note += " De tabel toont de 100 grootste regels.";
  }
  el("destinations-note").textContent = note;
  for (const row of rows) {
    const tr = body.insertRow();
    const domain = row.domain ? row.domain + " (" + row.evidence + ")" : "Onbekend";
    tr.insertCell().textContent = domain;
    const ipCell = tr.insertCell();
    ipCell.textContent = row.ip || "Overige verbindingen";
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
  for (const [label, values] of [["HA-server", data.buckets], [data.router_label, data.modem_buckets]]) {
    const row = body.insertRow();
    row.insertCell().textContent = label;
    const rx = values.reduce((total, item) => total + item.rx, 0);
    const tx = values.reduce((total, item) => total + item.tx, 0);
    countCells(row, rx, tx, values.length > 0);
  }
  updateTable("comparison-rows");
  const device = data.status.router_device ? "OpenWrt-interface actief: " + data.status.router_device + "." : "";
  el("modem-status").textContent = data.status.router_error || (!data.status.router_configured
    ? "Stel openwrt_url, openwrt_username en openwrt_password in onder HA-Bandwidth → Configuratie."
    : data.modem_buckets.length ? device : [device, "Nog geen WAN-metingen voor deze periode."].filter(Boolean).join(" "));
}

function show(data) {
  const status = data.status;
  el("status").textContent = status.updated
    ? (status.interface || "Interface onbekend") + " · laatste meetronde " +
      new Date(status.updated).toLocaleTimeString("nl-NL", {timeZone: status.zone}) +
      (data.first ? " · historie vanaf " + data.first.slice(0, 10) : "")
    : "Wachten op de eerste meetronde";
  const warnings = [...(status.errors || [])];
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
  const hasData = data.buckets.length > 0 || Boolean(data.modem_buckets?.length);
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

