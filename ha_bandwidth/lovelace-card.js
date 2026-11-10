import {mountDashboard} from "./dashboard.js";

const base = new URL("./", import.meta.url);
const sections = {
  overview: "Volledig dashboard", live: "Realtime verkeer en afwijkingen", controls: "Kop en periodekeuze", totals: "Totalen",
  history: "Verkeersgrafiek", ranking: "Verkeerstabel", destinations: "Bestemmingen",
  shared: "Gedeeld netwerk", topology: "Netwerkdiagram", comparison: "Vergelijking", backup: "Back-up",
};
const kinds = {host: "Server", app: "Apps", peer: "IP-adressen", device: "Apparaten", compare: "OpenWrt en modem", backup: "Back-up"};
const groups = new Map();
const selected = {
  live: ["#live-panel"],
  controls: ["header", "#explanation", "#warnings", ".controls", "#range"],
  totals: ["#totals"],
  history: [".history"],
  ranking: ["#ranking-panel"],
  destinations: ["#destinations"],
  shared: ["#shared-section"],
  topology: ["#topology-panel"],
  comparison: ["#comparison"],
  backup: ["#backup-panel"],
};

function trafficGroup(key) {
  if (!groups.has(key)) {
    const listeners = new Set();
    let state = {period: "day", source: "", sourceLabel: "", date: ""};
    groups.set(key, {
      subscribe(listener) {
        listeners.add(listener);
        listener(state);
        return () => {
          listeners.delete(listener);
          if (!listeners.size) groups.delete(key);
        };
      },
      update(next) {
        state = next;
        for (const listener of listeners) listener(state);
      },
    });
  }
  return groups.get(key);
}

const trafficRequests = new Map();

async function request(path, options) {
  const url = new URL(path, base);
  if (!path.startsWith("./api/traffic?")) return fetch(url, options);
  if (!trafficRequests.has(url.href)) {
    const pending = fetch(url, options).finally(() => trafficRequests.delete(url.href));
    trafficRequests.set(url.href, pending);
  }
  return (await trafficRequests.get(url.href)).clone();
}

async function readAsset(path) {
  const response = await request(path);
  if (!response.ok) throw new Error("HTTP " + response.status);
  return response.text();
}

let assets;
function loadAssets() {
  assets ??= Promise.all([readAsset("./"), readAsset("./dashboard.css")]).catch(error => {
    assets = undefined;
    throw error;
  });
  return assets;
}

class HABandwidthCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("ha-bandwidth-card-editor");
  }

  static getStubConfig() {
    return {part: "history", kind: "host"};
  }

  constructor() {
    super();
    this.attachShadow({mode: "open"});
    this.generation = 0;
  }

  setConfig(config) {
    if (!Object.hasOwn(sections, config.part) || !Object.hasOwn(kinds, config.kind)) {
      throw new Error("Kies een HA-Bandwidth-onderdeel en meetbron.");
    }
    this.config = config;
    if (this.isConnected) this.render();
  }

  connectedCallback() {
    if (this.config) this.render();
  }

  disconnectedCallback() {
    this.generation++;
    this.cleanup?.();
  }

  getCardSize() {
    return this.config?.part === "overview" ? 14 : 4;
  }

  async render() {
    this.cleanup?.();
    const generation = ++this.generation;
    const {part, kind, sync} = this.config;
    this.shadowRoot.textContent = "HA-Bandwidth…";
    try {
      const [html, css] = await loadAssets();
      if (generation !== this.generation) return;
      const parsed = new DOMParser().parseFromString(html, "text/html");
      const surface = document.createElement("div");
      surface.className = "bandwidth-surface";
      const main = parsed.querySelector("main");
      for (const link of main.querySelectorAll("a[href^='./']")) {
        link.href = new URL(link.getAttribute("href"), base);
      }
      surface.append(main);
      const style = document.createElement("style");
      const only = selected[part];
      const hide = only ? [...new Set(Object.values(selected).flat().concat("main > nav"))]
        .filter(selector => !only.includes(selector)).map(selector => ".bandwidth-surface " + selector)
        .join(",") + "{display:none!important}" : "";
      style.textContent = css.replaceAll(":root", ":host").replace(/\bbody(?=[\s{\[])/g, ".bandwidth-surface") + hide + `
        :host{display:block;min-width:0}
        .bandwidth-surface{
          container:bandwidth / inline-size;
          min-height:0;
          border-radius:var(--ha-card-border-radius,12px);
        }
        .bandwidth-surface main{
          max-width:none;
          padding:clamp(.65rem,2cqi,1.5rem);
          overflow-wrap:anywhere;
        }
        .bandwidth-surface .card{padding:clamp(.65rem,2cqi,1.5rem)}
        .bandwidth-surface main > .card:last-child,
        .bandwidth-surface .totals .card{margin-bottom:0}
        .bandwidth-surface .controls{justify-content:flex-start;gap:.5rem 1rem}
        .bandwidth-surface :is(input,select,button){max-width:100%}
        .bandwidth-surface #chart{min-width:0}
        .bandwidth-surface .totals strong{
          font-size:clamp(1rem,4cqi,2.25rem);
          white-space:normal;
        }
        @container bandwidth (max-width:480px){
          .language-bar{float:none;justify-content:flex-start;margin-inline-start:0}
          .totals{gap:.35rem}
          .plot-shell{--plot-height:180px;gap:.35rem}
          #axis{flex-basis:3.6rem;font-size:.65rem}
          #topology-map{height:20rem}
        }
        @container bandwidth (max-width:330px){
          .totals{grid-template-columns:1fr}
        }
      `;
      this.shadowRoot.replaceChildren(style, surface);
      const root = this.shadowRoot;
      const scopedDocument = {
        documentElement: surface,
        body: surface,
        get activeElement() { return root.activeElement; },
        getElementById: root.getElementById.bind(root),
        querySelector: root.querySelector.bind(root),
        querySelectorAll: root.querySelectorAll.bind(root),
        createElement: document.createElement.bind(document),
        createElementNS: document.createElementNS.bind(document),
        createTreeWalker: document.createTreeWalker.bind(document),
      };
      const url = new URL(base);
      url.searchParams.set("kind", kind);
      // Suppress the automatic setup popup inside a standalone card.
      if (part !== "overview") url.searchParams.set("card", part);
      this.cleanup = mountDashboard(scopedDocument, request, url,
        sync ? trafficGroup(location.pathname + ":" + kind) : undefined);
    } catch {
      if (generation === this.generation) this.shadowRoot.textContent =
        "Open de HA-Bandwidth-app vanuit de zijbalk en laad dit dashboard opnieuw.";
    }
  }
}

class HABandwidthCardEditor extends HTMLElement {
  setConfig(config) {
    this.replaceChildren();
    for (const [key, title, options] of [["part", "Onderdeel", sections], ["kind", "Meetbron", kinds]]) {
      const label = document.createElement("label");
      label.style.display = "block";
      label.style.marginBlock = "8px";
      const select = document.createElement("select");
      for (const [value, text] of Object.entries(options)) select.add(new Option(text, value));
      select.value = config[key];
      select.addEventListener("change", () => this.dispatchEvent(new CustomEvent("config-changed", {
        detail: {config: {...config, [key]: select.value}}, bubbles: true, composed: true,
      })));
      label.append(title + " ", select);
      this.append(label);
    }
  }
}

if (!customElements.get("ha-bandwidth-card")) {
  customElements.define("ha-bandwidth-card", HABandwidthCard);
  customElements.define("ha-bandwidth-card-editor", HABandwidthCardEditor);
  window.customCards ??= [];
  window.customCards.push({type: "ha-bandwidth-card", name: "HA-Bandwidth", description: "Herbruikbaar HA-Bandwidth-onderdeel", preview: true});
}
