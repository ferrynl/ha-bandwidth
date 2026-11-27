import test from "node:test";
import assert from "node:assert/strict";
import {JSDOM} from "jsdom";
import {root, html, css, wait, stubDialogs, budgetReply, trafficReply} from "./helper.mjs";

const dom = new JSDOM("<!doctype html><html><body></body></html>", {url: "https://ha.example/ha-bandwidth/host", pretendToBeVisual: true});
const {window} = dom;
for (const name of ["window", "document", "HTMLElement", "customElements", "DOMParser", "CustomEvent", "Option", "NodeFilter", "location"]) {
  globalThis[name] = name === "window" ? window : window[name];
}
stubDialogs(window);
let budget = budgetReply({state: "warning", used: 85e9, counted: 60e9, offset: 25e9, percent: 85});
const calls = [];
globalThis.fetch = async url => {
  const path = String(url).replace("file://" + root, "./");
  calls.push(path);
  const json = body => ({ok: true, json: async () => body, text: async () => JSON.stringify(body), clone() { return this; }});
  if (path === "./") return {ok: true, text: async () => html, clone() { return this; }};
  if (path === "./dashboard.css") return {ok: true, text: async () => css, clone() { return this; }};
  if (path.startsWith("./api/budget")) return json(budget);
  if (path.startsWith("./api/traffic")) return json({...trafficReply, buckets: [{bucket: "2026-11-22T09", rx: 1e6, tx: 1e6}], first: "2026-11-01T00"});
  return json({});
};
await import(root + "lovelace-card.js");

async function mount(config) {
  calls.length = 0;
  const card = window.document.createElement("ha-bandwidth-card");
  card.setConfig(config);
  window.document.body.append(card);
  await wait(250);
  const shadow = card.shadowRoot;
  const visible = selector => {
    const node = shadow.querySelector(selector);
    return Boolean(node) && !node.hidden && window.getComputedStyle(node).display !== "none";
  };
  return {shadow, visible, fetched: prefix => calls.some(call => call.startsWith(prefix))};
}

test("het budgetdeel toont alleen het budget, met correctie", async () => {
  const card = await mount({part: "budget", kind: "host"});
  assert.equal(card.visible("#budget"), true);
  assert.equal(card.visible(".history"), false);
  assert.equal(card.visible("#totals"), false);
  assert.match(card.shadow.querySelector("#budget-note").textContent, /25 GB/);
});

test("het budgetdeel meldt wat er ontbreekt als het budget uit staat", async () => {
  const before = budget;
  budget = {enabled: false};
  const card = await mount({part: "budget", kind: "host"});
  assert.match(card.shadow.querySelector("#budget-used").textContent, /Instellingen/);
  assert.equal(card.shadow.querySelector("#budget-progress").hidden, true);
  budget = before;
});

test("andere delen halen het budget en de instellingen niet op", async () => {
  for (const part of ["history", "totals", "controls", "ranking", "live"]) {
    const card = await mount({part, kind: "host"});
    assert.equal(card.fetched("./api/budget"), false, part);
    assert.equal(card.fetched("./api/settings"), false, part);
    assert.equal(card.visible("#budget"), false, part);
  }
});

test("de CSV-link wijst naar de app en niet naar de Home Assistant-pagina", async () => {
  const card = await mount({part: "history", kind: "host"});
  const href = card.shadow.querySelector("#export-csv").href;
  assert.ok(href.startsWith("file://" + root + "api/export.csv"), "de link hoort bij de app, niet bij de HA-pagina: " + href);
});
