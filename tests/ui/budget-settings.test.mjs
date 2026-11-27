import test from "node:test";
import assert from "node:assert/strict";
import {mountPage, submit, budgetReply, trafficReply} from "./helper.mjs";

const SAVED = "Opgeslagen. Het databudget is bijgewerkt.";

function server() {
  const state = {cfg: {limit_gb: 0, source: "modem", reset_day: 1, warn_percent: 80, from_settings_page: false}, fail: false};
  state.routes = path => {
    if (path.startsWith("./api/settings/budget-config")) return state.fail ? false : state.cfg;
    if (path.startsWith("./api/settings/budget")) return state.cfg;
    if (path.startsWith("./api/budget")) return state.cfg.limit_gb > 0 ? budgetReply({limit: state.cfg.limit_gb * 1e9}) : {enabled: false};
    if (path.startsWith("./api/settings")) return {retention_days: 400, configured: 400, from_settings_page: false, stored_days: 5, min: 30, max: 3650};
    if (path.startsWith("./api/traffic")) return trafficReply;
  };
  return state;
}

async function fill(page, values) {
  const ids = {limit: "budget-limit", day: "budget-reset-day", warn: "budget-warn", source: "budget-source"};
  for (const [key, value] of Object.entries(values)) page.get(ids[key]).value = value;
  await submit(page.window, page.get("budget-config-form"));
}

test("het formulier toont de huidige instellingen", async () => {
  const page = await mountPage("nl", server().routes);
  assert.equal(page.get("budget-limit").value, "0");
  assert.equal(page.get("budget-reset-day").value, "1");
  assert.equal(page.get("budget").hidden, true, "budget uit: geen voortgangsbalk");
  assert.equal(page.get("calibration-card").hidden, true, "budget uit: geen kalibratieformulier");
});

test("ongeldige invoer wordt niet verstuurd", async () => {
  const page = await mountPage("nl", server().routes);
  await fill(page, {limit: ""});
  assert.match(page.get("budget-config-status").textContent, /limiet/);
  await fill(page, {limit: "150", day: "40"});
  assert.match(page.get("budget-config-status").textContent, /dag van 1 tot en met 28/);
  await fill(page, {day: "5", warn: "100"});
  assert.match(page.get("budget-config-status").textContent, /percentage/);
  assert.equal(page.posts.length, 0);
});

test("opslaan verstuurt de waarden met de beschermende header en toont de budgetkaart", async () => {
  const state = server();
  const page = await mountPage("nl", (path, options) => {
    if (path.startsWith("./api/settings/budget-config")) {
      const body = JSON.parse(options.body);
      state.cfg = {...body, from_settings_page: true};
    }
    return state.routes(path);
  });
  await fill(page, {limit: "150", source: "openwrt", day: "5", warn: "85"});
  assert.deepEqual(page.posts[0].body, {limit_gb: 150, source: "openwrt", reset_day: 5, warn_percent: 85});
  assert.equal(page.posts[0].path, "./api/settings/budget-config");
  assert.equal(page.posts[0].headers["X-HA-Bandwidth-Settings"], "1");
  assert.equal(page.get("budget-config-status").textContent, SAVED);
  assert.equal(page.get("budget").hidden, false);
  assert.equal(page.get("calibration-card").hidden, false);
});

test("limiet 0 zet het budget uit en een serverfout wordt gemeld", async () => {
  const state = server();
  const page = await mountPage("nl", (path, options) => {
    if (path.startsWith("./api/settings/budget-config") && !state.fail) state.cfg = {...JSON.parse(options.body), from_settings_page: true};
    return state.routes(path);
  });
  state.fail = true;
  await fill(page, {limit: "100", day: "1", warn: "80"});
  assert.equal(page.get("budget-config-status").textContent, "Opslaan is mislukt. Probeer het opnieuw.");
  state.fail = false;
  await fill(page, {limit: "0"});
  assert.equal(page.get("budget-config-status").textContent, "Opgeslagen. Het databudget staat uit.");
  assert.equal(page.get("budget").hidden, true);
});

for (const [lang, title, label, error] of [
  ["en", "Set up data budget", "Limit (GB)", "Enter a limit from 0 to 1,000,000 gigabytes."],
  ["de", "Datenbudget einrichten", "Limit (GB)", "Gib ein Limit von 0 bis 1.000.000 Gigabyte ein."],
  ["es", "Configurar presupuesto de datos", "Límite (GB)", "Introduce un límite de 0 a 1.000.000 gigabytes."],
]) {
  test(`vertaling ${lang}`, async () => {
    const page = await mountPage(lang, server().routes);
    assert.equal(page.get("budget-settings-title").textContent, title);
    assert.equal(page.window.document.querySelector("label[for=budget-limit]").textContent, label);
    await fill(page, {limit: ""});
    assert.equal(page.get("budget-config-status").textContent, error);
  });
}
