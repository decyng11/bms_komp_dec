const { chromium } = require('playwright');
const fs = require('fs');
const SC = require('path').join(__dirname, 'shots') + '/';
(async () => {
  const js = fs.readFileSync(require('path').resolve(__dirname, '../../custom_components/bms_komp_dec/frontend') + '/bms-panel.js', 'utf8');
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 390, height: 800 }, hasTouch: true, isMobile: true, deviceScaleFactor: 2 }); const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource|net::ERR/.test(m.text())) errors.push('console.error: ' + m.text()); });
  await page.route('**/*', r => r.request().url().startsWith('data:') || r.request().url().startsWith('about:') ? r.continue() : r.abort());
  await page.setContent('<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;background:#000"><div id="host" style="width:370px;margin:10px"></div></body></html>');
  await page.evaluate(() => { window.Chart = class { constructor() {} destroy() {} }; window.Chart._adapters = { _date: class { formats() { return {}; } } }; });
  await page.addScriptTag({ content: js });
  await page.evaluate(() => {
    const now = Date.now() / 1000;
    const gen = (fn) => { const a = []; for (let m = 24 * 60; m >= 0; m -= 5) { const ts = now - m * 60; const h = new Date(ts * 1000).getHours() + new Date(ts * 1000).getMinutes() / 60; a.push({ s: String(Math.round(fn(h))), lu: ts }); } return a; };
    const pv = h => Math.max(0, 4200 * Math.sin((h - 6) / 13 * Math.PI)) * (h > 6 && h < 19 ? 1 : 0);
    const load = h => 400 + 500 * Math.exp(-((h - 19) ** 2) / 4) + 300 * Math.exp(-((h - 7.5) ** 2) / 2);
    const grid = h => load(h) - pv(h) > 0 ? Math.min(2500, load(h) - pv(h)) : Math.max(-3500, load(h) - pv(h));
    const batt = h => -(load(h) - pv(h)) * 0.7;
    window.__series = { 'sensor.bms_pv_power': gen(pv), 'sensor.bms_load_power': gen(load), 'sensor.bms_grid_power': gen(grid), 'sensor.bms_battery_power': gen(batt), 'sensor.bms_soc': gen(h => 20 + 60 * Math.abs(Math.sin(h / 24 * Math.PI))) };
    const S = (state, attributes = {}) => ({ state: String(state), attributes, last_updated: 'x' + state });
    const states = { 'sensor.bms_soc': S(75), 'sensor.bms_pv_power': S(0), 'sensor.bms_load_power': S(153), 'sensor.bms_battery_power': S(223), 'sensor.bms_grid_power': S(69), 'sensor.bms_reserve_soc': S(48, { capacity_kwh: 10 }) };
    const hass = { states, entities: {}, language: 'pl', callService: () => Promise.resolve(), callWS: async (m) => { window.__ws = (window.__ws || 0) + 1; const o = {}; (m.entity_ids || []).forEach(e => { o[e] = window.__series[e] || []; }); return o; } };
    const el = document.createElement('bms-panel-card'); el.setConfig({ type: 'custom:bms-panel-card' });
    document.getElementById('host').appendChild(el); el.hass = hass; window.__el = el; window.__hass = hass;
  });


  await page.evaluate(() => {
    const S = (v) => ({ state: String(v), attributes: {}, last_updated: 'd' + v });
    const st = window.__hass.states;
    for (let i = 1; i <= 4; i++) { st['sensor.inverter_pv' + i + '_voltage'] = S(310 + i); st['sensor.inverter_pv' + i + '_current'] = S(5 + i / 10); }
    Object.assign(st, { 'sensor.inverter_load_l1_voltage': S(231), 'sensor.inverter_load_frequency': S(50), 'sensor.inverter_load_l1_current': S(1.2),
      'sensor.inverter_grid_l1_voltage': S(232), 'sensor.inverter_grid_frequency': S(50.01), 'sensor.inverter_grid_l1_current': S(0.3),
      'sensor.inverter_battery_voltage': S(52.1), 'sensor.inverter_battery_current': S(-3.2), 'sensor.inverter_battery_temperature': S(24) });
    window.__el.hass = Object.assign({}, window.__hass);
  });
  const res = {};
  for (const k of ['pv', 'grid', 'batt']) {
    const sel = `bms-panel-card >> .nf-hit[data-k="${k}"]`;
    await page.locator(sel).tap(); await page.waitForTimeout(300);
    res[k] = await page.evaluate(() => { const sr = window.__el.shadowRoot; const p = sr.getElementById('nodePop'); const w = p.parentElement; const pr = p.getBoundingClientRect(), wr = w.getBoundingClientRect();
      return { wrapH: Math.round(wr.height), popBottom: Math.round(pr.bottom - wr.top), popH: Math.round(pr.height), fits: pr.bottom <= wr.bottom + 0.5, det: p.querySelector('.np-det') ? p.querySelector('.np-det').children.length / 2 : 0 }; });
    await page.screenshot({ path: SC + `grow_${k}.png`, fullPage: false });
    await page.locator('bms-panel-card >> .np-x').tap(); await page.waitForTimeout(150);
    res[k].afterClose = await page.evaluate(() => Math.round(window.__el.shadowRoot.getElementById('nodePop').parentElement.getBoundingClientRect().height));
  }
  console.log(JSON.stringify(res)); console.log('ERRORS:', JSON.stringify(errors));
  await browser.close();
})();
