// Gedeelde hulpmiddelen: laad dashboard.html in jsdom en voer dashboard.js uit met een nagebootste server.
import {JSDOM} from "jsdom";
import {readFileSync} from "node:fs";
import {fileURLToPath} from "node:url";

export const root = fileURLToPath(new URL("../../ha_bandwidth/", import.meta.url));
export const html = readFileSync(root + "dashboard.html", "utf8");
export const css = readFileSync(root + "dashboard.css", "utf8");
export const wait = (ms = 60) => new Promise(resolve => setTimeout(resolve, ms));

export const trafficReply = {
  start: "2026-11-22", end: "2026-11-22", buckets: [], destinations: [], topology: [], rows: [],
  status: {updated: "2026-11-22T10:00:00+01:00", zone: "Europe/Amsterdam", interface: "eth0", errors: []},
};

export function budgetReply(overrides = {}) {
  return {enabled: true, state: "ok", source_label: "Zyxel", limit: 100e9, used: 10e9, counted: 10e9, offset: 0, remaining: 90e9,
    percent: 10, warn_percent: 80, cycle_start: "2026-11-01", cycle_end: "2026-11-30", days_left: 8, measured: true,
    projected: null, projected_percent: null, ...overrides};
}

export function stubDialogs(window) {
  window.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  window.HTMLDialogElement.prototype.close = function () { this.open = false; };
}

/** Start het dashboard. `routes` is een functie (pad, opties) => antwoord of undefined. */
export async function mountPage(lang, routes) {
  const dom = new JSDOM(html, {url: "http://localhost/?lang=" + lang, pretendToBeVisual: true});
  const {window} = dom;
  stubDialogs(window);
  globalThis.window = window;
  globalThis.NodeFilter = window.NodeFilter;
  globalThis.document = {querySelector: () => null};
  const posts = [];
  const fetch = async (url, options = {}) => {
    const path = String(url);
    if (options.method === "POST") posts.push({path, headers: options.headers, body: JSON.parse(options.body)});
    const reply = routes(path, options);
    if (reply === undefined) return {ok: true, json: async () => ({})};
    if (reply === false) return {ok: false, json: async () => ({})};
    return {ok: true, json: async () => reply};
  };
  const module = await import(root + "dashboard.js?" + Math.random());
  module.mountDashboard(window.document, fetch, new URL(window.location.href));
  await wait();
  const get = id => window.document.getElementById(id);
  return {window, get, posts};
}

export async function submit(window, form) {
  form.dispatchEvent(new window.Event("submit", {cancelable: true, bubbles: true}));
  await wait();
}

export function type(window, input, value) {
  input.value = value;
  input.dispatchEvent(new window.Event("input", {bubbles: true}));
}
