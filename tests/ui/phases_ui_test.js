// 0.8.1: okno szczegółów sieci i domu pokazuje wszystkie fazy (L1–L3), jedna faza wygląda jak dotąd
const { chromium } = require('playwright'); const fs = require('fs');
(async () => {
  const js = fs.readFileSync(require('path').resolve(__dirname, '../../custom_components/bms_komp_dec/frontend') + '/bms-panel.js', 'utf8');
  const b = await chromium.launch(); const errs = []; let fails = 0;
  const ok = (n, c, x) => { if (!c) { fails++; console.log('FAIL', n, x === undefined ? '' : JSON.stringify(x).slice(0, 400)); } };
  const p = await (await b.newContext({ viewport: { width: 420, height: 800 } })).newPage();
  p.on('pageerror', e => errs.push(e.message));
  await p.route('**/*', r => /^(data|about):/.test(r.request().url()) ? r.continue() : r.abort());
  await p.setContent('<html><body><div id="h"></div></body></html>');
  await p.evaluate(() => { window.Chart = class { constructor() {} destroy() {} }; window.Chart._adapters = { _date: class { formats() { return {}; } } }; });
  await p.addScriptTag({ content: js });
  await p.evaluate(() => { const el = document.createElement('bms-panel-card'); el.setConfig({}); document.getElementById('h').appendChild(el); window.__el = el; });
  const details = (vals) => p.evaluate((vals) => {
    const el = window.__el; const states = {};
    for (const [k, v] of Object.entries(vals)) states['sensor.inverter_' + k] = { state: String(v), attributes: {}, last_updated: 'x' };
    el._xCache = {}; el._hass = { states, entities: {}, language: 'pl' };
    return el._nodeDetails();
  }, vals);
  const txt = (rows) => rows.map(r => r.join(': ')).join(' | ');

  // 1. trzy fazy (Deye P3): napięcia Grid, prądy z External CT, moce, Output dla domu
  let d = await details({ grid_l1_voltage: 230.4, grid_l2_voltage: 231.2, grid_l3_voltage: 229.9, external_ct1_current: 1.2, external_ct2_current: 0.8, external_ct3_current: 2.5,
    grid_l1_power: 120, grid_l2_power: -80, grid_l3_power: 95, grid_frequency: 50.01,
    output_l1_voltage: 230, output_l2_voltage: 231, output_l3_voltage: 229, output_l1_current: 3.1, output_l2_current: 2.2, output_l3_current: 1.4, load_l1_power: 700, load_l2_power: 500, load_l3_power: 300 });
  ok('3 fazy: napięcie sieci L1 · L2 · L3', txt(d.grid).includes('Napięcie L1 · L2 · L3: 230 · 231 · 230 V'), txt(d.grid));
  ok('3 fazy: prąd sieci z External CT', txt(d.grid).includes('Prąd L1 · L2 · L3: 1,2 · 0,8 · 2,5 A'), txt(d.grid));
  ok('3 fazy: moc sieci ze znakiem', txt(d.grid).includes('Moc L1 · L2 · L3: 120 · −80 · 95 W'), txt(d.grid));
  ok('3 fazy: częstotliwość', txt(d.grid).includes('Częstotliwość: 50,01 Hz'), txt(d.grid));
  ok('3 fazy: dom — napięcia, prądy, moce', txt(d.home).includes('Napięcie L1 · L2 · L3: 230 · 231 · 229 V') && txt(d.home).includes('Prąd L1 · L2 · L3: 3,1 · 2,2 · 1,4 A') && txt(d.home).includes('Moc L1 · L2 · L3: 700 · 500 · 300 W'), txt(d.home));
  // 2. dwie fazy (Deye hybrid): bez pustej trzeciej
  d = await details({ grid_l1_voltage: 120.1, grid_l2_voltage: 119.8, grid_l1_current: 4, grid_l2_current: 3 });
  ok('2 fazy: etykieta bez L3', txt(d.grid).includes('Napięcie L1 · L2: 120 · 120 V') && !txt(d.grid).includes('L3'), txt(d.grid));
  // 3. jedna faza: układ jak dotąd
  d = await details({ grid_voltage: 231, grid_frequency: 50, load_voltage: 230, load_current: 2.5 });
  ok('1 faza: stary układ sieci', txt(d.grid) === 'Napięcie · częstotliwość: 231 V · 50,00 Hz', txt(d.grid));
  ok('1 faza: stary układ domu', txt(d.home) === 'Napięcie · częstotliwość: 230 V | Prąd: 2,5 A', txt(d.home));
  // 4. brak jakichkolwiek danych
  d = await details({});
  ok('brak danych: puste listy', d.grid.length === 0 && d.home.length === 0, d);
  // 5. śmieci
  d = await details({ grid_l1_voltage: 'unavailable', grid_l2_voltage: 'abc', grid_l3_voltage: 230 });
  ok('śmieci: bez wyjątku, tylko ważne fazy', Array.isArray(d.grid), d);
  ok('bez błędów strony', errs.length === 0, errs);
  console.log(fails ? `FAILS ${fails}` : 'ALL OK'); await b.close();
})();
