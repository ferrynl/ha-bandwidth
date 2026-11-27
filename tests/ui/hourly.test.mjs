import test from "node:test";
import assert from "node:assert/strict";
import {mountPage, submit, type, trafficReply} from "./helper.mjs";

function server(initial = 0, affected = 3) {
  const state = {days: initial, fail: false};
  const reply = () => ({hourly_days: state.days, min: 30, max: 3650, retention_days: 400, stored_days: 200, pending_days: state.days ? affected : 0});
  state.routes = (path, options = {}) => {
    if (path.startsWith("./api/settings/hourly")) {
      if (options.method !== "POST") return reply();
      const body = JSON.parse(options.body);
      if (state.fail) return false;
      if (body.hourly_days && affected && !body.confirm && state.days !== body.hourly_days) return {http: 409, body: {error: "x", affected_days: affected}};
      state.days = body.hourly_days;
      return reply();
    }
    if (path.startsWith("./api/settings/budget")) return {limit_gb: 0, source: "modem", reset_day: 1, warn_percent: 80};
    if (path.startsWith("./api/budget")) return {enabled: false};
    if (path.startsWith("./api/settings")) return {retention_days: 400, configured: 400, from_settings_page: false, stored_days: 5, min: 30, max: 3650};
    if (path.startsWith("./api/traffic")) return trafficReply;
  };
  return state;
}

test("toont de huidige instelling en uit-tekst", async () => {
  const page = await mountPage("nl", server(0).routes);
  assert.equal(page.get("hourly-days").value, "0");
  assert.equal(page.get("hourly-hint").textContent, "Het uurdetail wordt altijd bewaard.");
  assert.equal(page.get("hourly-confirm-row").hidden, true);
});

test("ongeldige invoer wordt niet verstuurd", async () => {
  const page = await mountPage("nl", server(0).routes);
  for (const value of ["", "10", "90.5", "99999", "-1"]) {
    type(page.window, page.get("hourly-days"), value);
    await submit(page.window, page.get("hourly-form"));
    assert.equal(page.get("hourly-days").getAttribute("aria-invalid"), "true", value);
  }
  assert.equal(page.posts.length, 0);
});

test("opslaan zonder oud uurdetail werkt direct", async () => {
  const state = server(0, 0);
  const page = await mountPage("nl", state.routes);
  type(page.window, page.get("hourly-days"), "90");
  await submit(page.window, page.get("hourly-form"));
  assert.deepEqual(page.posts[0].body, {hourly_days: 90, confirm: false});
  assert.equal(page.posts[0].headers["X-HA-Bandwidth-Settings"], "1");
  assert.equal(page.get("hourly-status").textContent, "Opgeslagen. Oude dagen worden bij de eerstvolgende opruiming samengevat.");
});

test("uit zetten (0) werkt direct", async () => {
  const page = await mountPage("nl", server(90).routes);
  type(page.window, page.get("hourly-days"), "0");
  await submit(page.window, page.get("hourly-form"));
  assert.equal(page.get("hourly-status").textContent, "Opgeslagen. Het uurdetail wordt altijd bewaard.");
});

test("serverfout wordt gemeld", async () => {
  const state = server(0, 0);
  const page = await mountPage("nl", state.routes);
  state.fail = true;
  type(page.window, page.get("hourly-days"), "90");
  await submit(page.window, page.get("hourly-form"));
  assert.equal(page.get("hourly-status").textContent, "Opslaan is mislukt. Probeer het opnieuw.");
});

for (const [lang, title] of [["en", "Hourly detail"], ["de", "Stundendetail"], ["es", "Detalle por hora"]]) {
  test(`vertaling ${lang}`, async () => {
    const page = await mountPage(lang, server(0).routes);
    assert.equal(page.get("hourly-title").textContent, title);
    assert.ok(!/[{}]/.test(page.get("hourly-hint").textContent));
  });
}

test("oud uurdetail: eerst bevestigen, dan pas opslaan", async () => {
  const state = server(0, 3);
  const page = await mountPage("nl", state.routes);
  type(page.window, page.get("hourly-days"), "90");
  await submit(page.window, page.get("hourly-form"));
  assert.equal(page.get("hourly-confirm-row").hidden, false);
  assert.match(page.get("hourly-confirm-text").textContent, /3 dagen/);
  assert.equal(state.days, 0, "nog niets opgeslagen");
  await submit(page.window, page.get("hourly-form"));
  assert.equal(page.posts.length, 1, "zonder vinkje wordt er niets verstuurd");
  assert.equal(page.get("hourly-status").textContent, "Bevestig eerst dat je het uurdetail wilt samenvatten.");
  page.get("hourly-confirm").checked = true;
  await submit(page.window, page.get("hourly-form"));
  assert.deepEqual(page.posts[1].body, {hourly_days: 90, confirm: true});
  assert.equal(state.days, 90);
  assert.equal(page.get("hourly-confirm-row").hidden, true);
});

test("het vinkje verdwijnt weer als je de waarde wijzigt", async () => {
  const page = await mountPage("nl", server(0, 3).routes);
  type(page.window, page.get("hourly-days"), "90");
  await submit(page.window, page.get("hourly-form"));
  type(page.window, page.get("hourly-days"), "120");
  assert.equal(page.get("hourly-confirm-row").hidden, true);
});
