// Ekran główny: alerty, znaczniki rezerwy/celu na pierścieniu baterii, linia PV bez przecinania napisów, rachunek dnia, wykres SOC, przyciski nadpisań
const { openCard, chromium } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  const today = new Date().toISOString().slice(0, 10);
  const rows = []; for (let h = 0; h < 24; h++) rows.push({ t: new Date().toISOString(), h, day: today, action: 'idle', label: 'Bez zmian', peak: false, buy: 0.7, sell: 0.4, pv: 0, load: 0.5, soc: h === 23 ? 55 : 60, floor: 20, import_kwh: 0, export_kwh: 0, cost: 0 });
  const soc = []; for (let h = 0; h < 24; h++) soc.push(h <= new Date().getHours() ? 70 - h : null);
  await e.q((a) => {
    const t = new Date().toISOString();
    __states['sensor.bms_plan_view'] = { state: 'pv', attributes: a.pv, last_updated: t, last_changed: t };
    __states['sensor.bms_profit_today'] = { state: '1', attributes: { sums: { day: { revenue: 1.1, cost: 2.5, net: -1.4 } }, extras: { day: { savings: { saving: 4.2, without_cost: 6.05 } } } }, last_updated: t, last_changed: t };
    const rs = __states['sensor.bms_reserve_soc'] || (__states['sensor.bms_reserve_soc'] = { state: '20', attributes: {}, last_updated: t, last_changed: t });
    rs.attributes = Object.assign({}, rs.attributes, { inverter_floor: 20 });
    window.__svc = window.__svc || {}; window.__wsCalls = [];
    window.__svc['bms_komp_dec.override_set'] = (m) => { window.__wsCalls.push(['override_set', m.service_data]); return { response: { overrides: [] } }; };
    window.__svc['bms_komp_dec.override_clear'] = (m) => { window.__wsCalls.push(['override_clear', m.service_data]); return { response: { overrides: [] } }; };
    __el.hass = __mk();
  }, { pv: { why: { kind: 'idle', text: 'ok', details: [] }, table: rows, overrides: [{ id: 'x1', kind: 'no_sell', text: 'Nie sprzedawaj do 18:00' }], soc_history: [{ date: today, soc, grid: Array(24).fill(0), sale: Array(24).fill(0), plan: Array(24).fill(60), empty: false }], generated_at: new Date().toISOString() } });
  await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('#exMainBox .mp-bill'), null, { timeout: 10000 });
  await sleep(300);
  const m = await e.q(() => { const b = __el.shadowRoot.getElementById('exMainBox'); return { bill: b.querySelector('.mp-bill').textContent, svg: !!b.querySelector('.mp-chart svg'), paths: b.querySelectorAll('.mp-chart path').length, chips: b.querySelectorAll('.mp-chip').length, btns: b.querySelectorAll('[data-mp]').length }; });
  ok(/4,20 zł/.test(m.bill) && /1,10 zł/.test(m.bill) && /6,05 zł/.test(m.bill), 'rachunek dnia: oszczędzone, sprzedałem, bez PV: ' + m.bill);
  ok(m.svg && m.paths === 2, 'wykres SOC: linia rzeczywista i plan');
  ok(m.chips === 1 && m.btns === 0, 'ekran główny: bez przycisków, aktywne nadpisanie jako znacznik');
  await sleep(2500);
  const fm = await e.q(() => { const s = __el.shadowRoot.getElementById('nodesBox'); return { tick: !!s.querySelector('line[stroke="#ff3b30"]'), tgt: !!s.querySelector('rect[fill="#af52de"]') }; });
  ok(fm.tick && fm.tgt, 'pierścień baterii: kreska rezerwy i znacznik celu dnia');
  // linia PV nie przecina napisów pod słońcem
  const geo = await e.q(() => { const s = __el.shadowRoot.getElementById('nodesBox'); const lines = Array.from(s.querySelectorAll('path.nf-line')); const txt = Array.from(s.querySelectorAll('text')).filter(t => /produkcja PV|dziś/.test(t.textContent)); const pv = lines.find(l => /^M300/.test(l.getAttribute('d'))); const y0 = pv ? Math.min(...pv.getAttribute('d').match(/[\d.]+ ([\d.]+)/g).map(x => parseFloat(x.split(' ')[1]))) : null; const ys = txt.map(t => parseFloat(t.getAttribute('y'))); return { y0, maxTxt: ys.length ? Math.max(...ys) : null }; });
  ok(geo.y0 === null || geo.maxTxt === null || geo.y0 > geo.maxTxt, 'linia PV zaczyna się pod napisami: ' + JSON.stringify(geo));
  await e.q(() => __el.shadowRoot.querySelector('#exMainBox [data-mp-del="x1"]').click()); await sleep(300);
  const calls = await e.q(() => window.__wsCalls);
  ok(calls.some(c => c[0] === 'override_clear' && c[1].id === 'x1'), 'krzyżyk usuwa nadpisanie: ' + JSON.stringify(calls));
  // alert: brak danych z falownika
  await e.q(() => { for (const k of ['sensor.bms_soc', 'sensor.inverter_battery', 'sensor.inverter_battery_soc']) if (__states[k]) __states[k].state = 'unavailable'; __el.hass = __mk(); });
  await sleep(400);
  const al = await e.q(() => { const s = __el.shadowRoot.getElementById('statusBanner'); return { vis: s.style.display !== 'none', t: s.textContent }; });
  ok(al.vis && /Brak danych z falownika/.test(al.t), 'alert: brak danych z falownika: ' + al.t.slice(0, 60));
  await e.page.screenshot({ path: process.env.SHOT || '/tmp/main_ui.png', fullPage: true });
  await b.close();
  console.log(fails ? 'FAILED ' + fails : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
