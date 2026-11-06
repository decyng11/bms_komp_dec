const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const js = fs.readFileSync(require('path').resolve(__dirname, '../../custom_components/bms_komp_dec/frontend') + '/bms-panel.js', 'utf8');
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource|net::ERR/.test(m.text())) errors.push('console.error: ' + m.text()); });
  await page.route('**/*', r => r.request().url().startsWith('data:') || r.request().url().startsWith('about:') ? r.continue() : r.abort());
  await page.setContent('<html><body><div id="host"></div></body></html>');
  // sztuczny Chart.js, żeby zweryfikować ścieżkę danych historii
  await page.evaluate(() => {
    window.Chart = class { constructor(ctx, cfg) { window.__cfgs = (window.__cfgs || []).concat([cfg]); } destroy() {} };
    window.Chart._adapters = { _date: class { formats() { return {}; } } };
  });
  await page.addScriptTag({ content: js });
  await page.addScriptTag({ content: js });   // podwójne załadowanie — nie może rzucać
  const out = await page.evaluate(async () => {
    const res = {};
    res.defined = !!customElements.get('bms-panel-card');
    res.cards = (window.customCards || []).filter(c => c.type === 'bms-panel-card').length;
    const now = Date.now() / 1000;
    const mkHist = (v) => [{ s: String(v), lu: now - 3600 * 5 }, { s: String(v + 1), lu: now - 3600 * 3 }, { s: String(v + 2), lu: now - 3600 }];
    const entries = [
      { ts: new Date().toISOString(), kind: 'command', level: 'ok', msg: 'Sprzedaż 6000W (harmonogram <b>x</b>)' },
      { ts: new Date().toISOString(), kind: 'guard', level: 'warn', msg: 'Zatrzymuję sprzedaż: import 3000 W' },
    ];
    const S = (state, attributes = {}) => ({ state: String(state), attributes, last_updated: 'x' + state });
    const states = {
      'sensor.bms_soc': S(55), 'sensor.bms_pv_power': S(1500), 'sensor.bms_load_power': S(600),
      'sensor.bms_battery_power': S(-200), 'sensor.bms_grid_power': S(-100),
      'sensor.inverter_pv_power': S(1500), 'sensor.inverter_load_power': S(600), 'sensor.inverter_battery': S(55), 'sensor.inverter_grid_power': S(-100),
      'sensor.rce_pse_cena': S(0.5),
      'sensor.bms_decision_log': S('Sprzedaż 6000W', { entries, count: 2 }),
      'sensor.bms_profit_today': S(3.21, { history: [{ date: '2026-10-27', net: 2.1 }, { date: '2026-10-28', net: -0.4 }, { date: '2026-10-29', net: 3.21 }], export_kwh: 5, import_kwh: 1 }),
      'sensor.bms_profit_month': S(12.5), 'sensor.bms_profit_total': S(-3.2), 'sensor.bms_reserve_soc': S(48.5, { enabled: true, need_kwh: 3.2, until_hour: 8 }),
      'switch.bms_negative_price_reaction': S('on'), 'switch.bms_profit_check': S('off'), 'switch.bms_dzien_pn': S('on'), 'switch.bms_dzien_nd': S('off'),
      'number.bms_low_price_threshold': S(0),
    };
    const calls = [];
    const hass = {
      states, entities: {}, language: 'pl',
      callService: (d, s, data) => { calls.push([d, s, data]); return Promise.resolve(); },
      callWS: async (msg) => {
        if (msg.type === 'history/history_during_period') {
          const o = {};
          msg.entity_ids.forEach((e, i) => { o[e] = mkHist(10 * (i + 1)); });
          return o;
        }
        return {};
      },
    };
    const el = document.createElement('bms-panel-card');
    el.setConfig({ type: 'custom:bms-panel-card' });
    document.getElementById('host').appendChild(el);
    el.hass = hass;
    res.shell = !!el.shadowRoot.querySelector('.tabs');
    res.tabs = [...el.shadowRoot.querySelectorAll('.tab')].map(t => t.dataset.tab);
    el.shadowRoot.querySelector('.tab[data-tab="log"]').click();
    el.hass = hass;
    const body = el.shadowRoot.getElementById('logTabBody');
    res.logText = body.innerText;
    res.escaped = !body.innerHTML.includes('<b>x</b>');
    // przełącznik + usługa
    const sw = body.querySelector('[data-switch="switch.bms_profit_check"]');
    sw.click();
    body.querySelector('[data-service="undo_auto_apply"]').click();
    const inp = body.querySelector('input[data-number="number.bms_low_price_threshold"]');
    inp.value = '0.05'; inp.dispatchEvent(new Event('change', { bubbles: true }));
    await new Promise(r => setTimeout(r, 50));
    res.calls = calls;
    // wykres historii: lu-timestamps
    await el._fetchHistoryData('1D');
    const cfg = (window.__cfgs || []).slice(-1)[0];
    res.chartPoints = cfg ? cfg.data.datasets.map(d => [d.label, (d.data || []).length]) : null;
    return res;
  });
  console.log(JSON.stringify(out, null, 1));
  console.log('ERRORS:', JSON.stringify(errors));
  await browser.close();
})();
