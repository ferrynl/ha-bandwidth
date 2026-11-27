import test from "node:test";
import assert from "node:assert/strict";
import {mountPage, submit, type, wait, budgetReply, trafficReply} from "./helper.mjs";

function server({enabled = true, stored = 200} = {}) {
  const base = budgetReply();
  const state = {status: enabled ? base : {enabled: false}, fail: false, retention: {retention_days: 400, configured: 400, from_settings_page: false, stored_days: stored, min: 30, max: 3650}};
  state.routes = (path, options = {}) => {
    if (path.startsWith("./api/settings/budget")) {
      if (options.method !== "POST") return {limit_gb: 100, source: "modem", reset_day: 1, warn_percent: 80, from_settings_page: false};
      if (state.fail) return false;
      const gb = JSON.parse(options.body).used_gb;
      state.status = gb === null ? base : budgetReply({used: gb * 1e9, offset: gb * 1e9 - base.counted});
      return state.status;
    }
    if (path.startsWith("./api/budget")) return state.status;
    if (path.startsWith("./api/settings")) {
      if (options.method === "POST") {
        if (state.fail) return false;
        state.retention = {...state.retention, retention_days: JSON.parse(options.body).retention_days, from_settings_page: true};
      }
      return state.retention;
    }
    if (path.startsWith("./api/traffic")) return trafficReply;
  };
  return state;
}

test("kalibratie: ongeldig, opslaan, fout en wissen", async () => {
  const state = server();
  const page = await mountPage("nl", state.routes);
  const form = page.get("calibration-form");
  assert.equal(page.get("calibration-card").hidden, false);
  type(page.window, page.get("calibration-used"), "");
  await submit(page.window, form);
  assert.equal(page.get("calibration-used").getAttribute("aria-invalid"), "true");
  type(page.window, page.get("calibration-used"), "-3");
  await submit(page.window, form);
  assert.equal(page.posts.length, 0);
  type(page.window, page.get("calibration-used"), "37.5");
  await submit(page.window, form);
  assert.deepEqual(page.posts[0].body, {used_gb: 37.5});
  assert.equal(page.posts[0].headers["X-HA-Bandwidth-Settings"], "1");
  assert.match(page.get("budget-note").textContent, /\+27,5 GB|\+27\.5 GB/);
  state.fail = true;
  type(page.window, page.get("calibration-used"), "40");
  await submit(page.window, form);
  assert.equal(page.get("calibration-status").textContent, "Opslaan is mislukt. Probeer het opnieuw.");
  state.fail = false;
  page.get("calibration-clear").click();
  await wait();
  assert.deepEqual(page.posts.at(-1).body, {used_gb: null});
});

test("kalibratie: kaart verborgen als het budget uit staat", async () => {
  const page = await mountPage("nl", server({enabled: false}).routes);
  assert.equal(page.get("calibration-card").hidden, true);
});

test("bewaartijd: verlaging vraagt om bevestiging, verhoging niet", async () => {
  const page = await mountPage("nl", server().routes);
  const form = page.get("retention-form");
  type(page.window, page.get("retention-days"), "100");
  assert.equal(page.get("retention-confirm-row").hidden, false);
  await submit(page.window, form);
  assert.equal(page.posts.length, 0, "zonder vinkje niets versturen");
  page.get("retention-confirm").checked = true;
  await submit(page.window, form);
  assert.deepEqual(page.posts[0].body, {retention_days: 100, confirm: true});
  type(page.window, page.get("retention-days"), "500");
  await submit(page.window, form);
  assert.deepEqual(page.posts[1].body, {retention_days: 500, confirm: false});
});

test("bewaartijd: ongeldige invoer wordt niet verstuurd", async () => {
  const page = await mountPage("nl", server().routes);
  for (const value of ["10", "90.5", ""]) {
    type(page.window, page.get("retention-days"), value);
    await submit(page.window, page.get("retention-form"));
    assert.equal(page.get("retention-days").getAttribute("aria-invalid"), "true", value);
  }
  assert.equal(page.posts.length, 0);
});
