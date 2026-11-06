const { chromium } = require('playwright');
const fs = require('fs');
const SC = require('path').join(__dirname, 'shots') + '/';
(async () => {
  const js = fs.readFileSync(require('path').resolve(__dirname, '../../custom_components/bms_komp_dec/frontend') + '/bms-panel.js', 'utf8');
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 820, height: 1100 } });
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource|net::ERR/.test(m.text())) errors.push('console.error: ' + m.text()); });
  await page.route('**/*', r => r.request().url().startsWith('data:') || r.request().url().startsWith('about:') ? r.continue() : r.abort());
  await page.setContent('<html><body style="margin:0;background:#000"><div id="host" style="width:780px;margin:10px"></div></body></html>');
  await page.evaluate(() => { window.Chart = class { constructor() {} destroy() {} }; window.Chart._adapters = { _date: class { formats() { return {}; } } }; });
  await page.addScriptTag({ content: js });
  const res = await page.evaluate(async () => {
    const P = (label, cur, prop, reason, conf = 'high', skip = false) => ({ label, current: cur, proposed: prop, reason, confidence: conf, skip });
    const skipR1 = 'Pomiń — okno nocne (do 06:00) już się kończy; propozycja pojawi się po południu.';
    const data = { generated_at: new Date().toISOString(), soc: 74, rce_today_avg: 0.925, rce_tomorrow_avg: null, g12w_peak: 1.292, g12w_off_peak: 0.676, pv_today_kwh: 7.9, pv_tomorrow_kwh: 6.1, load_tomorrow_kwh: 11.2, sunrise_today: '06:29', sunset_today: '16:08',
      proposals: {
        start_grid_charge: P('x', '00:00', null, skipR1, 'high', true), stop_grid_charge: P('x', '00:00', null, skipR1, 'high', true),
        start_grid_charge_2: P('x', '00:00', null, 'Pomiń — okno nocne wystarcza.', 'high', true), stop_grid_charge_2: P('x', '00:00', null, 'Pomiń — okno nocne wystarcza.', 'high', true),
        bateria_sprzedaz_start: P('x', '00:00', null, 'Pomiń — najlepsze okno dziś (0.715 zł/kWh) jest poniżej średniej dnia (0.925).', 'high', true), bateria_sprzedaz_stop: P('x', '00:00', null, 'Pomiń — najlepsze okno dziś (0.715 zł/kWh) jest poniżej średniej dnia (0.925).', 'high', true),
        bateria_sprzedaz_start_2: P('x', '00:00', '18:00', 'Najlepsze okno dziś w szczycie wieczornym: 18–19, śr. 1.350 zł/kWh (dzień śr. 0.925). Przewidywany SOC o 18:00 ~100%, sprzedaż ~3.5 kWh, zysk netto ~+1.98 zł. Do świtu (PV pokryje dom ok. 09:00) SOC nie spadnie poniżej ~31%.'), bateria_sprzedaz_stop_2: P('x', '00:00', '19:00', 'Najlepsze okno dziś w szczycie wieczornym: 18–19, śr. 1.350 zł/kWh (dzień śr. 0.925). Przewidywany SOC o 18:00 ~100%, sprzedaż ~3.5 kWh, zysk netto ~+1.98 zł. Do świtu (PV pokryje dom ok. 09:00) SOC nie spadnie poniżej ~31%.'),
        pv_export_start: P('x', '00:00', null, 'Pomiń — dziś brak godzin, w których cena przewyższa średnią cenę godzin PV (0.624) o min. marżę 0.15 zł/kWh.', 'high', true), pv_export_stop: P('x', '00:00', null, 'Pomiń — dziś brak godzin, w których cena przewyższa średnią cenę godzin PV (0.624) o min. marżę 0.15 zł/kWh.', 'high', true),
      } };
    const calls = [];
    const S = (state, attributes = {}) => ({ state: String(state), attributes, last_updated: 'x' });
    const hass = { states: { 'sensor.bms_soc': S(74) }, entities: {}, language: 'pl',
      callService: async (d, s, data2) => { calls.push([d, s, data2]); if (s === 'suggest_schedule') return { response: data }; return {}; }, callWS: async () => ({}) };
    const el = document.createElement('bms-panel-card'); el.setConfig({ type: 'custom:bms-panel-card' });
    document.getElementById('host').appendChild(el); el.hass = hass; window.__el = el;
    el.shadowRoot.querySelector('.tab[data-tab="ems"]').click();
    const out = {};
    out.placeholder = el.shadowRoot.getElementById('suggestResults').innerText.slice(0, 120);
    out.rulesBefore = !!el.shadowRoot.querySelector('.sg-rules');
    el.shadowRoot.getElementById('btn-suggest').click();
    await new Promise(r => setTimeout(r, 200));
    const root = el.shadowRoot;
    out.cards = [...root.querySelectorAll('.sg')].map(c => c.className + ' | ' + c.querySelector('.sg-title').innerText + ' | ' + c.querySelector('.sg-badge').innerText);
    out.summary = root.querySelector('.sg-sum').innerText;
    out.why = root.querySelectorAll('.sg-why').length;
    root.getElementById('btn-apply-suggest').click();
    await new Promise(r => setTimeout(r, 200));
    out.applied = calls.filter(c => c[1] === 'apply_schedule_times').map(c => c[2]);
    return out;
  });
  console.log(JSON.stringify(res, null, 1));
  await page.evaluate(() => { window.__el.shadowRoot.getElementById('btn-suggest').click(); });
  await page.waitForTimeout(300);
  const el = page.locator('bms-panel-card >> #suggestResults');
  await el.scrollIntoViewIfNeeded();
  await page.screenshot({ path: SC + 'sug_explain.png', fullPage: true });
  console.log('ERRORS:', JSON.stringify(errors));
  await browser.close();
})();
