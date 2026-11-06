const { chromium } = require('playwright');
const fs = require('fs');
const SC = require('path').join(__dirname, 'shots') + '/';
(async () => {
  const js = fs.readFileSync(require('path').resolve(__dirname, '../../custom_components/bms_komp_dec/frontend') + '/bms-panel.js', 'utf8');
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 900, height: 760 } });
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource|net::ERR/.test(m.text())) errors.push('console.error: ' + m.text()); });
  await page.route('**/*', r => r.request().url().startsWith('data:') || r.request().url().startsWith('about:') ? r.continue() : r.abort());
  await page.setContent('<html><body style="margin:0;background:#000"><div id="host" style="width:880px;margin:10px"></div></body></html>');
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
    const states = { 'sensor.bms_soc': S(75), 'sensor.bms_pv_power': S(0), 'sensor.bms_load_power': S(153), 'sensor.bms_battery_power': S(223), 'sensor.bms_grid_power': S(69), 'sensor.bms_reserve_soc': S(48, { capacity_kwh: 10 }), 'sensor.inverter_pv1_voltage': S(312.4), 'sensor.inverter_pv1_current': S(5.2), 'sensor.inverter_pv2_voltage': S(298.1), 'sensor.inverter_pv2_current': S(3.1), 'sensor.inverter_pv3_voltage': S(0), 'sensor.inverter_load_l1_voltage': S(230.6), 'sensor.inverter_load_frequency': S(50.01), 'sensor.inverter_load_l1_current': S(0.6), 'sensor.inverter_grid_l1_voltage': S(232.2), 'sensor.inverter_grid_frequency': S(49.98), 'sensor.inverter_grid_l1_current': S(0.3), 'sensor.inverter_battery_voltage': S(52.3), 'sensor.inverter_battery_current': S(4.1), 'sensor.inverter_battery_temperature': S(24) };
    const hass = { states, entities: {}, language: 'pl', callService: () => Promise.resolve(), callWS: async (m) => { window.__ws = (window.__ws || 0) + 1; const o = {}; (m.entity_ids || []).forEach(e => { o[e] = window.__series[e] || []; }); return o; } };
    const el = document.createElement('bms-panel-card'); el.setConfig({ type: 'custom:bms-panel-card' });
    document.getElementById('host').appendChild(el); el.hass = hass; window.__el = el; window.__hass = hass;
  });
  const sh = () => page.evaluateHandle(() => window.__el.shadowRoot);
  const res = {};
  const hit = k => page.locator(`bms-panel-card >> .nf-hit[data-k="${k}"]`);
  // hover PV
  for (const k of ['pv', 'grid', 'batt']) {
    await hit(k).hover();
    await page.waitForTimeout(250);
    res[k] = await page.evaluate(() => { const p = window.__el.shadowRoot.getElementById('nodePop'); return { hidden: p.hidden, head: p.querySelector('.np-head')?.innerText, stats: p.querySelector('.np-stats')?.innerText, paths: p.querySelectorAll('path').length, msg: p.querySelector('.np-msg')?.innerText }; });
    await page.screenshot({ path: SC + `pop_hover_${k}.png`, clip: { x: 0, y: 0, width: 900, height: 700 } });
  }
  res.bounds = {};
  for (const k of ['pv', 'home', 'grid', 'batt']) {
    await hit(k).hover(); await page.waitForTimeout(250);
    res.bounds[k] = await page.evaluate(() => { const p = window.__el.shadowRoot.getElementById('nodePop'); const c = p.parentElement.getBoundingClientRect(), r = p.getBoundingClientRect(); return { inside: r.top >= c.top - 0.5 && r.bottom <= c.bottom + 0.5 && r.left >= c.left - 0.5 && r.right <= c.right + 0.5, top: Math.round(r.top - c.top), bottom: Math.round(c.bottom - r.bottom) }; });
    await page.screenshot({ path: SC + `pop2_${k}.png`, clip: { x: 0, y: 0, width: 900, height: 760 } });
  }
  res.details = await page.evaluate(() => ({ onTiles: window.__el.shadowRoot.querySelectorAll('.nf-d').length, inPop: window.__el.shadowRoot.getElementById('nodePop').querySelector('.np-det')?.innerText }));
  // pin + pointermove
  await hit('grid').click();
  await page.waitForTimeout(150);
  const box = await page.locator('bms-panel-card >> #npTouch').boundingBox();
  await page.mouse.move(box.x + box.width * 0.55, box.y + box.height / 2);
  await page.waitForTimeout(100);
  res.pinned = await page.evaluate(() => { const p = window.__el.shadowRoot.getElementById('nodePop'); return { pin: p.classList.contains('pin'), head: p.querySelector('.np-head b').innerText, curVisible: p.querySelector('#npCur').style.display !== 'none' }; });
  await page.screenshot({ path: SC + 'pop_pinned_grid.png', clip: { x: 0, y: 0, width: 900, height: 700 } });
  // przerysowanie węzłów nie zabija popovera
  await page.evaluate(() => { window.__hass.states['sensor.bms_load_power'] = { state: '900', attributes: {}, last_updated: 'z' }; window.__el.hass = Object.assign({}, window.__hass); });
  await page.waitForTimeout(100);
  res.survivesRedraw = await page.evaluate(() => !window.__el.shadowRoot.getElementById('nodePop').hidden);
  // zamknięcie przez ×
  await page.locator('bms-panel-card >> .np-x').click();
  res.closedByX = await page.evaluate(() => window.__el.shadowRoot.getElementById('nodePop').hidden);
  // cache: drugi hover nie woła WS
  const before = await page.evaluate(() => window.__ws);
  await hit('grid').hover(); await page.waitForTimeout(150);
  res.cacheNoNewWS = (await page.evaluate(() => window.__ws)) === before;
  // Escape
  await hit('grid').click(); await page.keyboard.press('Escape');
  res.closedByEsc = await page.evaluate(() => window.__el.shadowRoot.getElementById('nodePop').hidden);
  // jasny motyw
  await page.evaluate(() => window.__el._setTheme('light', false));
  await hit('batt').click(); await page.waitForTimeout(200);
  await page.screenshot({ path: SC + 'pop_light_batt.png', clip: { x: 0, y: 0, width: 900, height: 700 } });
  // brak historii
  await page.evaluate(() => { window.__series = {}; window.__el._nodeHist = {}; });
  await page.keyboard.press('Escape');
  await hit('pv').click(); await page.waitForTimeout(200);
  res.empty = await page.evaluate(() => window.__el.shadowRoot.getElementById('nodePop').innerText);
  // wąski ekran
  await page.setViewportSize({ width: 380, height: 700 });
  await page.evaluate(() => { document.getElementById('host').style.width = '360px'; window.__series = {}; });
  console.log(JSON.stringify(res, null, 1));
  console.log('ERRORS:', JSON.stringify(errors));
  await browser.close();
})();
