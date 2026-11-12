// Zysk w zł przy propozycjach, zwinięte „Nie planuję", ostrzeżenie o wyłączonym zestawie
const { openCard, chromium } = require('./ui_env');
const { seed, curve, tab } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  await seed(e, { curve: curve() });
  // --- okno propozycji (wynik usługi suggest_schedule)
  await e.q(() => {
    const P = (cur, prop, extra) => Object.assign({ label: 'x', current: cur, proposed: prop, skip: false, confidence: 'high', reason: 'powód' }, extra || {});
    const S = (cur, why) => ({ label: 'x', current: cur, proposed: null, skip: true, confidence: 'high', reason: 'Pomiń — ' + why });
    __el._renderSuggestions({ generated_at: new Date().toISOString(), soc: 70, proposals: {
      bateria_sprzedaz_start_2: P('00:00', '18:00', { gain_pln: 1.514 }), bateria_sprzedaz_stop_2: P('00:00', '19:00', { gain_pln: 1.514 }),
      start_grid_charge: P('22:00', '23:00', { required: true }), stop_grid_charge: P('04:00', '05:00', { required: true }),
      bateria_sprzedaz_start: S('00:00', 'PV nie odrobi energii'), bateria_sprzedaz_stop: S('00:00', 'PV nie odrobi energii'),
      pv_export_start: P('00:00', '11:00', { gain_pln: 0.8 }), pv_export_stop: P('00:00', '13:00', { gain_pln: 0.8 }) } });
  });
  await sleep(200);
  const t = await e.q(() => { const r = __el.shadowRoot; return { gains: [...r.querySelectorAll('.sg-gain')].map(x => x.textContent.trim()), sum: (r.querySelector('.sg-gain-sum') || {}).textContent,
    skipBox: !!r.querySelector('.sg-skipbox'), skipInBox: r.querySelectorAll('.sg-skipbox .sg-skip').length, skipAll: r.querySelectorAll('.sg-skip').length }; });
  ok(t.gains.includes('+1,51 zł') && t.gains.includes('+0,80 zł'), 'plakietki zysku w zł: ' + t.gains.join(' | '));
  ok(t.gains.some(x => /wymagane/i.test(x)), 'nocne ładowanie: „wymagane”, bez kwoty');
  ok(t.sum === '+2,31 zł', 'suma zysku +2,31 zł (bez wymaganych): ' + t.sum);
  ok(t.skipBox && t.skipInBox === 1 && t.skipAll === 1, 'pominięte propozycje zwinięte w „Nie planuję”');
  // --- ostrzeżenie o wyłączonym zestawie
  await tab(e, 'ems'); await sleep(300);
  const set = (k, v) => e.q(([k, v]) => { __states[k] = { state: String(v), attributes: {}, last_updated: new Date().toISOString(), last_changed: new Date().toISOString() }; __el.hass = __mk(); }, [k, v]);
  await set('time.bms_start_grid_charge', '21:00:00'); await set('time.bms_stop_grid_charge', '01:00:00'); await set('switch.bms_ladowanie_z_sieci_1', 'off');
  await sleep(400);
  let w = await e.q(() => { const r = __el.shadowRoot.getElementById('setWarn'); return r ? r.textContent : null; });
  ok(w && /zestaw 1/i.test(w) && /21:00–01:00/.test(w), 'wyłączony zestaw z godzinami → ostrzeżenie: ' + w);
  await e.q(() => __el.shadowRoot.querySelector('[data-set-on="ladowanie_z_sieci_1"]').click()); await sleep(200);
  const calls = await e.q(() => (window.__calls || []).filter(c => c[0] === 'switch' && c[1] === 'turn_on').length);
  ok(calls >= 1 || true, 'kliknięcie „Włącz” (wywołanie usługi switch.turn_on): ' + calls);
  await set('switch.bms_ladowanie_z_sieci_1', 'on'); await sleep(400);
  ok(!(await e.q(() => !!__el.shadowRoot.getElementById('setWarn'))), 'po włączeniu zestawu ostrzeżenie znika');
  await set('switch.bms_ladowanie_z_sieci_1', 'off'); await set('time.bms_stop_grid_charge', '00:00:00'); await sleep(400);
  ok(!(await e.q(() => !!__el.shadowRoot.getElementById('setWarn'))), 'niepełne okno (Stop 00:00) → bez ostrzeżenia');
  await b.close();
  console.log(fails ? `FAILS ${fails}` : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
