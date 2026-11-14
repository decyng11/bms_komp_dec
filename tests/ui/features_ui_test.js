// „Dlaczego?”, tabela planu, nadpisania, historia SOC, porównanie taryf, symulacja roczna, tryb prosty, test sterowania
const { openCard, chromium } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  const now = () => new Date().toISOString();
  const tableRows = [];
  for (let i = 0; i < 6; i++) tableRows.push({ t: now(), h: 22 + i > 23 ? i - 2 : 22 + i, day: i < 2 ? new Date().toISOString().slice(0, 10) : new Date(Date.now() + 86400000).toISOString().slice(0, 10),
    action: ['grid', 'grid', 'idle', 'pv', 'sell', 'home'][i], label: ['Ładuj z sieci', 'Ładuj z sieci', 'Bez zmian', 'Ładuj z PV', 'Sprzedaj z baterii', 'Bateria zasila dom'][i],
    peak: i > 3, buy: 0.7, sell: 0.4, pv: 0, load: 0.5, soc: 50 + i * 5, floor: 20, import_kwh: 1, export_kwh: 0, cost: i === 4 ? -1.35 : 1.05 });
  const hist = [];
  for (let d = 0; d < 3; d++) { const soc = [], grid = [], sale = []; for (let h = 0; h < 24; h++) { soc.push(d === 0 && h < 12 ? null : 40 + h); grid.push(h === 2 ? 1 : 0); sale.push(h === 18 ? 1 : 0); }
    hist.push({ date: new Date(Date.now() - (2 - d) * 86400000).toISOString().slice(0, 10), soc, grid, sale, plan: d === 2 ? Array(24).fill(55) : null, empty: false }); }
  const setPv = (attrs) => e.q((a) => {
    const t = new Date().toISOString();
    __states['sensor.bms_plan_view'] = { state: 'pv', attributes: a, last_updated: t, last_changed: t };
    __el.hass = __mk();
  }, attrs);
  const calls = [];
  await e.q(() => { window.__svc = window.__svc || {}; window.__wsCalls = [];
    window.__svc['bms_komp_dec.override_set'] = (m) => { window.__wsCalls.push(['override_set', m.service_data]); return { response: { overrides: [] } }; };
    window.__svc['bms_komp_dec.override_clear'] = (m) => { window.__wsCalls.push(['override_clear', m.service_data]); return { response: { overrides: [] } }; };
    window.__svc['bms_komp_dec.analysis_set'] = (m) => { window.__wsCalls.push(['analysis_set', m.service_data]); return { response: {} }; };
    window.__svc['bms_komp_dec.control_test'] = (m) => { window.__wsCalls.push(['control_test', m.service_data]); return { response: { ok: true, detail: 'działa' } }; };
    window.__svc['bms_komp_dec.analysis_get'] = () => ({ response: {
      tariff: { days: 12, import_kwh: 150, best: 'g11', cfg: { g11: 0.9 }, note: 'Szacunek: ten sam pobór.', rows: [
        { key: 'actual', name: 'Twoja obecna taryfa (rzeczywiste ceny)', cost: 120, per_month: 300, diff: 0, diff_month: 0 },
        { key: 'g11', name: 'Jedna stawka (G11) 0.90 zł/kWh', cost: 110, per_month: 275, diff: -10, diff_month: -25 }] },
      sim: { days: 40, extrapolated: true, note: 'Szacunek z danych godzinowych: 40 dób.', savings_year: { pv: 2000, battery: 800, ems: 300, total: 3100 }, payback: { pv_years: 10, battery_years: 12, total_years: 11 }, cfg: { invest_pv: 20000 },
        scenarios: [{ key: 'nopv', name: 'Bez PV i bez baterii', period: 400, year: 3650 }, { key: 'nobat', name: 'Samo PV (bez baterii)', period: 200, year: 1800 }, { key: 'simple', name: 'PV + bateria, prosta strategia (bez planera)', period: 150, year: 1400 }, { key: 'ems', name: 'PV + bateria + EMS (rzeczywiście)', period: 120, year: 1100 }] },
      cfg: { g11: 0.9 } } });
  });

  // ---- „Dlaczego?”
  await setPv({});
  await sleep(300);
  ok(await e.q(() => __el.shadowRoot.getElementById('whyBox').style.display === 'none'), 'dlaczego: bez danych ramka ukryta');
  await setPv({ why: { kind: 'grid', text: 'Ładuję baterię z sieci, bo teraz prąd jest tani — do 80%.', details: ['Najbliższe okno dziś: sprzedaż 18:00–20:00.'] }, table: tableRows, table_totals: { import_kwh: 6, export_kwh: 0, cost: 4.2 }, overrides: [], soc_history: hist, generated_at: now() });
  await sleep(400);
  const why = await e.q(() => { const w = __el.shadowRoot.getElementById('whyBox'); return { vis: w.style.display !== 'none', t: w.textContent, li: w.querySelectorAll('li').length }; });
  ok(why.vis && /do 80%/.test(why.t) && why.li === 1, 'dlaczego: zdanie i jeden powód poboczny: ' + why.t.slice(0, 80));

  // ---- zakładka EMS
  await e.q(() => __el.shadowRoot.querySelector('[data-tab="ems"]').click());
  await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('#exTblBox table'), null, { timeout: 8000 });
  await sleep(500);
  const tb = await e.q(() => { const t = __el.shadowRoot.querySelector('#exTblBox'); return { rows: t.querySelectorAll('tbody tr').length, days: t.querySelectorAll('tr.day').length, acts: Array.from(t.querySelectorAll('.px-act')).map(x => x.textContent), tot: t.querySelector('tr.tot').textContent, peak: t.querySelectorAll('tr.peak').length }; });
  ok(tb.days === 2 && tb.rows === 9 && /Sprzedaj z baterii/.test(tb.acts.join()) && /Ładuj z PV/.test(tb.acts.join()), 'tabela planu: 6 godzin + 2 nagłówki dni + suma: ' + JSON.stringify(tb.acts));
  ok(/pobór 6,0 kWh/.test(tb.tot) && /4,20 zł/.test(tb.tot) && tb.peak === 2, 'tabela planu: suma i godziny szczytu: ' + tb.tot);
  const hs = await e.q(() => { const h = __el.shadowRoot.querySelector('#exHistBox'); return { svg: !!h.querySelector('svg'), paths: h.querySelectorAll('path').length, bands: h.querySelectorAll('rect[fill^="rgba"]').length, tips: h.querySelectorAll('title').length }; });
  ok(hs.svg && hs.paths === 2 && hs.bands === 6 && hs.tips === 72, 'historia SOC: SVG z linią, planem i 6 pasami okien: ' + JSON.stringify(hs));

  // ---- nadpisania
  let ov = await e.q(() => __el.shadowRoot.querySelectorAll('#exOvrBox [data-px-set]').length);
  ok(ov === 3, 'nadpisania: trzy rodzaje do ustawienia');
  await e.q(() => { const s = __el.shadowRoot.querySelector('#exOvrBox [data-px-h="no_sell"]'); s.value = '8'; s.dispatchEvent(new Event('change', { bubbles: true })); });
  await e.q(() => __el.shadowRoot.querySelector('#exOvrBox [data-px-set="no_sell"]').click());
  await sleep(400);
  let wc = await e.q(() => window.__wsCalls);
  ok(wc.some(c => c[0] === 'override_set' && c[1].kind === 'no_sell' && c[1].hours === 8), 'nadpisanie „nie sprzedawaj” 8 h: usługa wywołana');
  await e.q(() => { const t = __el.shadowRoot.querySelector('#exOvrBox [data-px-t="charge"]'); t.value = '70'; t.dispatchEvent(new Event('change', { bubbles: true })); });
  await e.q(() => __el.shadowRoot.querySelector('#exOvrBox [data-px-set="charge"]').click());
  await sleep(400);
  wc = await e.q(() => window.__wsCalls);
  ok(wc.some(c => c[0] === 'override_set' && c[1].kind === 'charge' && c[1].target === 70 && c[1].hours === 2), 'nadpisanie „ładuj” do 70%: usługa z celem');
  await setPv({ why: { kind: 'idle', text: 'x', details: [] }, table: tableRows, overrides: [{ id: 'o1', kind: 'no_sell', text: 'Ręczne nadpisanie: nie sprzedaję do 19:00.' }], soc_history: hist, generated_at: now() });
  await sleep(1500);
  const ovl = await e.q(() => Array.from(__el.shadowRoot.querySelectorAll('#exOvrBox .px-ovr')).map(x => x.textContent));
  ok(ovl.length === 1 && /nie sprzedaję do 19:00/.test(ovl[0]), 'nadpisania: aktywne nadpisanie widoczne na liście');
  await e.q(() => __el.shadowRoot.querySelector('#exOvrBox [data-px-del="o1"]').click());
  await sleep(300);
  wc = await e.q(() => window.__wsCalls);
  ok(wc.some(c => c[0] === 'override_clear' && c[1].id === 'o1'), 'nadpisania: usunięcie po id');

  // ---- Zysk i log: taryfy i symulacja
  await e.q(() => __el.shadowRoot.querySelector('[data-tab="log"]').click());
  await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('#exTarBox table') && !!__el.shadowRoot.querySelector('#exSimBox table'), null, { timeout: 8000 });
  const an = await e.q(() => { const s = __el.shadowRoot; return { t: s.querySelector('#exTarBox').textContent, best: s.querySelectorAll('#exTarBox tr.px-best').length, sim: s.querySelector('#exSimBox').textContent, simRows: s.querySelectorAll('#exSimBox tbody tr').length }; });
  ok(/Jedna stawka \(G11\)/.test(an.t) && an.best === 1 && /−25,00 zł/.test(an.t), 'taryfy: tabela z podświetloną tańszą pozycją i różnicą miesięczną: ' + an.t.slice(0, 120));
  ok(an.simRows === 4 && /zwrot PV: 10,0 lat/.test(an.sim) && /ekstrapolacja/.test(an.sim), 'symulacja: 4 scenariusze, zwrot i ostrzeżenie o ekstrapolacji');
  await e.q(() => { const s = __el.shadowRoot; s.getElementById('pxG11').value = '0,95'; s.getElementById('pxDyn').value = '0,4'; s.querySelector('[data-px-an="tariff"]').click(); });
  await sleep(500);
  wc = await e.q(() => window.__wsCalls);
  ok(wc.some(c => c[0] === 'analysis_set' && c[1].g11 === 0.95 && c[1].dyn_markup === 0.4 && c[1].zone === null), 'taryfy: zapis cen wysyła liczby (przecinek → kropka)');
  await e.q(() => { const s = __el.shadowRoot; s.getElementById('pxIp').value = '25000'; s.getElementById('pxIb').value = '15000'; s.querySelector('[data-px-an="invest"]').click(); });
  await sleep(500);
  wc = await e.q(() => window.__wsCalls);
  ok(wc.some(c => c[0] === 'analysis_set' && c[1].invest_pv === 25000 && c[1].invest_batt === 15000), 'symulacja: zapis nakładów');

  // ---- tryb prosty
  await e.q(() => __el.shadowRoot.querySelector('[data-tab="main"]').click());
  const vis = () => e.q(() => { const s = __el.shadowRoot; const d = (sel) => { const x = s.querySelector(sel); return !!x && getComputedStyle(x).display !== 'none'; };
    return { charts: d('.tab[data-tab="charts"]'), log: d('.tab[data-tab="log"]'), dev: d('.tab[data-tab="dev"]'), ems: d('.tab[data-tab="ems"]'), simple: d('#simpleWrap'), plan: (() => { const x = s.querySelector('#exPlanBox'); const sec = x && x.closest('.section'); return !!sec && getComputedStyle(sec).display !== 'none'; })(), emsLabel: s.querySelector('.tab[data-tab="ems"] .tl').textContent, weather: d('.weather-global') }; });
  let v = await vis();
  ok(v.charts && v.log && v.ems && !v.simple && v.emsLabel === 'EMS', 'bez trybu prostego: pełny panel');
  await e.q(() => { const t = new Date().toISOString(); for (const k of ['simple_mode', 'sell_enabled', 'grid_charge_enabled', 'auto_apply', 'auto_enable_sets', 'profit_check', 'dynamic_reserve', 'pv_forecast_correction', 'live_load_correction']) __states['switch.bms_' + k] = { state: ['simple_mode', 'sell_enabled', 'auto_enable_sets', 'pv_forecast_correction', 'live_load_correction'].includes(k) ? 'on' : 'off', attributes: {}, last_updated: t, last_changed: t };
    __states['sensor.bms_reserve_soc'] = { state: '40', attributes: { tariff_mode: 'zone', tariff_label: '6–13, 15–22', price_buy: 0.9, price_sell: 0.4, inverter_floor: 25, capacity_kwh: 10 }, last_updated: t, last_changed: t };
    __el.hass = __mk(); });
  await sleep(500);
  v = await vis();
  ok(!v.charts && !v.log && !v.dev && !v.weather && v.ems && v.emsLabel === 'Ustawienia', 'tryb wyłączony: zakładki Wykresy/Zysk/Urządzenia i pogoda ukryte, EMS → „Ustawienia”: ' + JSON.stringify(v));
  await e.q(() => __el.shadowRoot.querySelector('[data-tab="ems"]').click());
  await sleep(600);
  v = await vis();
  const sm = await e.q(() => { const w = __el.shadowRoot.getElementById('simpleWrap'); return { t: w.textContent, seg: w.querySelectorAll('.sm-seg').length, act: Array.from(w.querySelectorAll('.sm-seg button.active')).map(x => x.dataset.simpleSw + ':' + x.dataset.v), auto: w.querySelectorAll('.sm-auto div').length, btn: (w.querySelector('[data-simple-auto]') || {}).textContent }; });
  ok(v.simple && !v.plan, 'tryb prosty: widoczny ekran prosty, zwykłe sekcje EMS schowane');
  ok(/strefowa — szczyt 6–13, 15–22/.test(sm.t) && /0,90 zł\/kWh/.test(sm.t), 'tryb prosty: wykryta taryfa i ceny: ' + sm.t.slice(0, 120));
  ok(sm.seg === 2 && sm.act.join() === 'sell_enabled:on,grid_charge_enabled:off', 'tryb prosty: odpowiedzi Tak/Nie zgodne ze stanem przełączników: ' + sm.act);
  ok(sm.auto === 6 && /\(3\)/.test(sm.btn || ''), 'tryb prosty: lista automatyki i przycisk dla 3 wyłączonych: ' + sm.btn);
  await e.q(() => { window.__calls.length = 0; __el.shadowRoot.querySelector('#simpleWrap [data-simple-sw="grid_charge_enabled"][data-v="on"]').click(); });
  await sleep(200);
  let sc = await e.q(() => window.__calls.filter(c => c[0] === 'switch'));
  ok(sc.length === 1 && sc[0][1] === 'turn_on' && /grid_charge_enabled/.test(sc[0][2].entity_id), 'tryb prosty: „Tak” włącza ładowanie z sieci');
  await e.q(() => { window.__calls.length = 0; __el.shadowRoot.querySelector('#simpleWrap [data-simple-auto]').click(); });
  await sleep(200);
  sc = await e.q(() => window.__calls.filter(c => c[0] === 'switch' && c[1] === 'turn_on').map(c => c[2].entity_id));
  ok(sc.length === 3 && sc.some(x => /auto_apply$/.test(x)) && sc.some(x => /profit_check$/.test(x)) && sc.some(x => /dynamic_reserve$/.test(x)) && !sc.some(x => /auto_enable_sets$/.test(x)), 'tryb prosty: zalecana automatyka włącza tylko wyłączone: ' + sc.join());
  // wyłączenie trybu przywraca pełny panel
  await e.q(() => { const t = new Date().toISOString(); __states['switch.bms_simple_mode'] = { state: 'off', attributes: {}, last_updated: t, last_changed: t }; __el.hass = __mk(); });
  await sleep(500);
  v = await vis();
  ok(v.charts && v.log && v.dev !== undefined && !v.simple && v.plan && v.emsLabel === 'EMS', 'po wyłączeniu trybu: pełny panel wrócił');

  // ---- diagnostyka: przełączniki i test sterowania
  await e.q(() => __el.shadowRoot.querySelector('[data-tab="diag"]').click());
  await e.page.waitForFunction(() => !!__el.shadowRoot.getElementById('dgPw'), null, { timeout: 8000 });
  await e.q(() => { const s = __el.shadowRoot; s.getElementById('dgPw').value = 'slonce'; s.querySelector('[data-act=unlock]').click(); });
  await e.page.waitForFunction(() => !!__el.shadowRoot.getElementById('dgBody'), null, { timeout: 5000 });
  await e.q(() => __el.shadowRoot.querySelector('[data-sec=modes]').click());
  await sleep(500);
  const modes = await e.q(() => Array.from(__el.shadowRoot.querySelectorAll('[data-act="mode-sw"]')).map(x => x.dataset.k));
  ok(['simple_mode', 'sell_enabled', 'grid_charge_enabled', 'grid_stop_at_target'].every(k => modes.includes(k)), 'diagnostyka: nowe przełączniki w Trybach: ' + modes.join());
  await e.q(() => __el.shadowRoot.querySelector('[data-sec=adv]').click());
  await e.page.waitForFunction(() => !!__el.shadowRoot.getElementById('dgCtlCard'), null, { timeout: 5000 });
  await setPv({ control_test: { ok: true, detail: 'działa: number.x 100 → 101 potwierdzone po 3 s', ts: now() } });
  await e.q(() => __el.shadowRoot.querySelector('[data-sec=modes]').click()); await e.q(() => __el.shadowRoot.querySelector('[data-sec=adv]').click());
  await sleep(400);
  ok(await e.q(() => /potwierdzone po 3 s/.test(__el.shadowRoot.getElementById('dgCtlCard').textContent)), 'diagnostyka: wynik ostatniego testu sterowania widoczny');
  await e.q(() => __el.shadowRoot.querySelector('[data-act=ctl-test]').click());
  await sleep(300);
  ok(await e.q(() => !!__el.shadowRoot.querySelector('.dg-modal')), 'test sterowania: okno potwierdzenia');
  await e.q(() => __el.shadowRoot.querySelector('.dg-modal [data-id=ok]').click());
  await sleep(800);
  wc = await e.q(() => window.__wsCalls);
  ok(wc.some(c => c[0] === 'control_test'), 'test sterowania: usługa wywołana po potwierdzeniu');

  ok(e.errs.length === 0, 'brak błędów w konsoli: ' + e.errs.slice(0, 3).join(' | '));
  await b.close();
  console.log(fails ? `FAILS ${fails}` : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
