// 0.8.6: niskie kafelki pogody, jeden rząd „Aktywne funkcje”, ostrzeżenie o blokadzie sprzedaży osobno
const { chromium } = require('playwright'); const fs = require('fs'); const path = require('path');
(async () => {
  const js = fs.readFileSync(path.resolve(__dirname, '../../custom_components/bms_komp_dec/frontend/bms-panel.js'), 'utf8');
  const b = await chromium.launch(); let fail = 0; const ok = (n, c, x) => { console.log((c ? 'ok   ' : 'FAIL ') + n + (c ? '' : ' ' + JSON.stringify(x))); if (!c) fail++; };
  const ctx = await b.newContext({ viewport: { width: 390, height: 800 } }); const p = await ctx.newPage(); const errs = [];
  p.on('pageerror', e => errs.push(e.message));
  await p.route('**/*', r => /^(data|about):/.test(r.request().url()) ? r.continue() : r.abort());
  await p.setContent('<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0"><div id="h" style="width:370px;margin:10px"></div></body></html>');
  await p.evaluate(() => { window.Chart = class { constructor() {} destroy() {} }; window.Chart._adapters = { _date: class { formats() { return {}; } } }; });
  await p.addScriptTag({ content: js });
  const r = await p.evaluate(() => {
    const S = v => ({ state: String(v), attributes: {}, last_updated: 'x' + v });
    const el = document.createElement('bms-panel-card'); el.setConfig({ type: 'custom:bms-panel-card' }); document.getElementById('h').appendChild(el);
    el.hass = { states: { 'sensor.bms_soc': S(50), 'sensor.solcast_pv_forecast_forecast_today': S(33), 'sensor.solcast_pv_forecast_forecast_tomorrow': S(32.7) }, entities: {}, language: 'pl', callService: async () => {}, callWS: async () => ({}) };
    const base = new Date(); el._weatherError = null;
    el._weatherForecast = ['partlycloudy', 'sunny', 'rainy'].map((c, i) => ({ datetime: new Date(base.getTime() + i * 86400000).toISOString(), condition: c, temperature: 6, templow: -1 }));
    el._lastWeatherKey = null; el._renderWeather();
    const sr = el.shadowRoot; const q = s => sr.querySelector(s);
    const tile = q('.weather-tile'); const pv = q('.weather-tile .pv'); const row = q('.weather-tile .wt-row');
    const warn = q('#warn-sprzedaz-zablokowana'); const hidden0 = getComputedStyle(warn).display;
    warn.classList.add('on'); const shown = getComputedStyle(warn).display;
    const bx = q('.active-badges'); const vis = () => [...bx.children].filter(c => getComputedStyle(c).display !== 'none').map(c => c.id);
    el._syncBadges(); const none0 = vis();
    const st = { 'switch.bms_ladowanie_z_sieci_1': S('on'), 'time.bms_start_grid_charge': S('05:00:00'), 'time.bms_stop_grid_charge': S('06:00:00'), 'switch.bms_bateria_sprzedaz_2': S('on'), 'time.bms_bateria_sprzedaz_start_2': S('00:00:00'), 'time.bms_bateria_sprzedaz_stop_2': S('23:59:00') };
    const eidOrig = el._eid.bind(el); el._eid = (d, k) => (d + '.bms_' + k); const stOrig = el._st.bind(el); el._st = (e) => (st[e] ? st[e].state : 'off');
    el._updateBadge('switch', 'ladowanie_z_sieci_1', 'badge-laduj-1', ['start_grid_charge', 'stop_grid_charge']);
    el._updateBadge('switch', 'bateria_sprzedaz_2', 'badge-sprzedaz-2', ['bateria_sprzedaz_start_2', 'bateria_sprzedaz_stop_2']);
    el._syncBadges();
    const hrs = new Date().getHours(); const l1 = sr.getElementById('badge-laduj-1'), s2 = sr.getElementById('badge-sprzedaz-2');
    return { h: tile.getBoundingClientRect().height, pvH: pv.getBoundingClientRect().height, pvTxt: pv.textContent.trim(), rowOk: !!row && !!row.querySelector('svg.wx') && !!row.querySelector('.temp-max'),
      hidden0, shown, nowrap: getComputedStyle(bx).flexWrap, ovx: getComputedStyle(bx).overflowX, none0, vis: vis(), l1txt: l1.textContent, l1soon: l1.classList.contains('soon'), s2txt: s2.textContent, s2soon: s2.classList.contains('soon'),
      warnInRow: !!bx.querySelector('#badge-sprzedaz-zablokowana'), dot: getComputedStyle(s2, '::before').content, hrs };
  });
  ok('kafelek pogody niższy niż 100 px', r.h < 100, r.h);
  ok('kWh w jednej linii, bez emoji', r.pvH < 20 && r.pvTxt === '33.0 kWh', [r.pvH, r.pvTxt]);
  ok('ikona (animowane SVG) i temperatura w jednym wierszu', r.rowOk);
  ok('ostrzeżenie o blokadzie ukryte, gdy brak blokady, widoczne po włączeniu', r.hidden0 === 'none' && r.shown === 'block', [r.hidden0, r.shown]);
  ok('ostrzeżenie poza rzędem chipów', !r.warnInRow);
  ok('chipy w jednym przewijanym rzędzie', r.nowrap === 'nowrap' && r.ovx === 'auto', r);
  ok('bez włączonych funkcji widać tylko informację', JSON.stringify(r.none0) === '["badge-none"]', r.none0);
  ok('widoczne tylko włączone funkcje (bez wyłączonych)', JSON.stringify(r.vis.sort()) === '["badge-laduj-1","badge-sprzedaz-2"]', r.vis);
  ok('zaplanowana funkcja pokazuje okno godzin i jest „soon”, o ile teraz poza oknem', /Ładowanie \(1\) 05:00–06:00/.test(r.l1txt) && r.l1soon === (r.hrs < 5 || r.hrs >= 6), [r.l1txt, r.l1soon, r.hrs]);
  ok('funkcja w trakcie okna (cała doba) jest aktywna teraz, z kropką', /Sprzedaż \(2\) 00:00–23:59/.test(r.s2txt) && !r.s2soon && r.dot !== 'none', [r.s2txt, r.s2soon, r.dot]);
  ok('brak błędów strony', errs.length === 0, errs);
  await b.close(); process.exit(fail ? 1 : 0);
})();
