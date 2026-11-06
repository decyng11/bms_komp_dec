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

  const res = {};
  for (const k of ['pv','load','grid','batt']) {
    const sel = `bms-panel-card >> .nf-hit[data-k="${k}"]`;
    const ok = await page.locator(sel).count();
    if (!ok) { res[k] = 'brak .nf-hit'; continue; }
    await page.locator(sel).tap(); await page.waitForTimeout(300);
    res[k] = await page.evaluate(() => { const p = window.__el.shadowRoot.getElementById('nodePop'); const r = p.getBoundingClientRect(); const c = window.__el.shadowRoot.querySelector('ha-card, .card, .wrap') || window.__el; const cr = c.getBoundingClientRect(); return { hidden: p.hidden, box: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)], vw: innerWidth, card: [Math.round(cr.left), Math.round(cr.width)], det: p.querySelector('.np-det')?.innerText || null, clippedRight: r.right > innerWidth + 1, clippedLeft: r.left < -1 }; });
    await page.screenshot({ path: SC + `mob_pop_${k}.png` });
    await page.keyboard.press('Escape'); await page.waitForTimeout(100);
  }
  console.log(JSON.stringify(res, null, 1)); console.log('ERRORS:', JSON.stringify(errors));
  await browser.close();
})();
