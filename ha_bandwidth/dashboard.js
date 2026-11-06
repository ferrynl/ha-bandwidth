"use strict";

const el = id => document.getElementById(id);
const format = new Intl.NumberFormat("nl-NL", {maximumFractionDigits: 2});
const views = {
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
  const peak = Math.max(1, ...data.buckets.flatMap(row => [row.rx, row.tx]));
  const axis = [1, .75, .5, .25, 0].map(fraction => {
    const label = document.createElement("span");
    label.textContent = bytes(peak * fraction);
    return label;
  });
  el("axis").replaceChildren(...axis);
  el("chart").replaceChildren(...slots.map(([key, tick]) => {
    const value = values.get(key);
    const group = document.createElement("div");
    group.className = "bucket";
    group.title = value
      ? key + " · Download " + bytes(value.rx) + " · Upload " + bytes(value.tx)
      : key + " · Geen meting";
    if (value) group.tabIndex = 0;
    group.setAttribute("aria-label", group.title);
    const columns = document.createElement("div");
    columns.className = "columns";
    if (value) {
      for (const [direction, count] of [["rx", value.rx], ["tx", value.tx]]) {
        const bar = document.createElement("span");
        bar.className = "bar " + direction;
        bar.style.height = (100 * count / peak) + "%";
        columns.append(bar);
      }
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
    tr.insertCell().append(button);
    for (const count of [row.rx, row.tx, row.rx + row.tx]) tr.insertCell().textContent = bytes(count);
  }
}

function showDestinations(data) {
  const section = el("destinations");
  section.hidden = kind !== "app" || !source;
  if (section.hidden) {
    focusDestinations = false;
    return;
  }
  const title = el("destinations-title");
  title.textContent = "Bestemmingen · " + sourceLabel;
  const rows = data.destinations;
  const body = el("destination-rows");
  body.replaceChildren();
  el("destinations-table").hidden = rows.length === 0;
  let note = "Waargenomen IP-verkeer. TLS geeft een zichtbare domeinnaam aan. DNS is een aanwijzing.";
  if (rows.length === 0) {
    note = data.status.app_destinations_enabled === false
      ? "De meting van app-bestemmingen staat uit."
      : "Geen bestemmingen gemeten voor deze app en periode.";
  } else if (data.destinations_truncated) {
    note += " De tabel toont de 100 grootste regels.";
  }
  el("destinations-note").textContent = note;
  for (const row of rows) {
    const tr = body.insertRow();
    const domain = row.domain ? row.domain + " (" + row.evidence + ")" : "Onbekend";
    for (const value of [
      domain, row.ip || "Overige verbindingen", row.protocol || "—",
      row.port >= 0 ? row.port : "—", bytes(row.rx), bytes(row.tx), bytes(row.rx + row.tx),
    ]) tr.insertCell().textContent = value;
  }
  if (focusDestinations) {
    focusDestinations = false;
    title.focus();
  }
}

function show(data) {
  const status = data.status;
  el("status").textContent = status.updated
    ? (status.interface || "Interface onbekend") + " · laatste meetronde " +
      new Date(status.updated).toLocaleTimeString("nl-NL", {timeZone: status.zone}) +
      (data.first ? " · historie vanaf " + data.first.slice(0, 10) : "")
    : "Wachten op de eerste meetronde";
  const warnings = [...(status.errors || [])];
  if (kind === "peer" && status.peers_enabled === false) warnings.push("IP-meting staat uit.");
  el("warnings").hidden = warnings.length === 0;
  el("warnings").textContent = warnings.join(" · ");
  el("range").textContent = data.start === data.end ? data.start : data.start + " t/m " + data.end;
  const rx = data.buckets.reduce((total, row) => total + row.rx, 0);
  const tx = data.buckets.reduce((total, row) => total + row.tx, 0);
  const hasData = data.buckets.length > 0;
  el("download").textContent = hasData ? bytes(rx) : "—";
  el("upload").textContent = hasData ? bytes(tx) : "—";
  el("total").textContent = hasData ? bytes(rx + tx) : "—";
  el("chart-title").textContent = sourceLabel || "Verkeer over tijd";
  el("clear").hidden = !source;
  el("empty").hidden = hasData;
  el("chart").parentElement.hidden = !hasData;
  if (hasData) timeline(data);
  table(data.rows);
  showDestinations(data);
  el("shared-section").hidden = kind !== "app" || !(status.shared?.length || status.unavailable?.length);
  el("shared").textContent = status.shared?.join(", ") || "";
  el("unavailable").textContent = status.unavailable?.length
    ? "Actief zonder bruikbare tellers: " + status.unavailable.join(", ") : "";
}

async function load() {
  const id = ++request;
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

