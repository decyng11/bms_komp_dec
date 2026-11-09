// Zakładka EMS: moc ładowania z sieci i limit poboru (ochrona przyłącza) — wiersze ustawień
const { openCard, chromium } = require('./ui_env');
const { seed, curve, tab } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  await seed(e, { curve: curve() });
  await e.q(() => {
    const S = (v, a) => ({ state: String(v), attributes: a || {}, last_updated: new Date().toISOString(), last_changed: new Date().toISOString() });
    __states['number.bms_grid_import_limit_kw'] = S(11, { min: 0, max: 60, step: 0.1 });
    __states['number.bms_grid_charge_power_kw'] = S(0, { min: 0, max: 30, step: 0.1 });
    __el.hass = __mk();
  });
  await tab(e, 'ems'); await sleep(500);
  const v = await e.q(() => [...__el.shadowRoot.querySelectorAll('input[data-num-key]')].filter(i => /^grid_(import_limit|charge_power)_kw$/.test(i.dataset.numKey)).map(i => [i.dataset.numKey, i.value, i.step]));
  ok(v.length === 2, 'są dwa pola: moc ładowania i limit poboru: ' + JSON.stringify(v));
  ok(v.some(x => x[0] === 'grid_import_limit_kw' && x[1] === '11'), 'limit poboru pokazuje 11 kW z encji');
  ok(v.every(x => x[2] === '0.1'), 'krok 0,1 kW');
  const hint = await e.q(() => __el.shadowRoot.getElementById('eid-grid_import_limit_kw').textContent);
  ok(/Twojego przyłącza/.test(hint) && /0 = wyłączone/.test(hint), 'podpowiedź przy limicie: ' + hint.slice(0, 60));
  ok(/prąd/.test(await e.q(() => __el.shadowRoot.getElementById('eid-grid_charge_power_kw').textContent)), 'podpowiedź przy mocy ładowania');
  await e.q(() => { window.__calls.length = 0; const i = __el.shadowRoot.querySelector('input[data-num-key="grid_import_limit_kw"]'); i.value = '9.5'; i.dispatchEvent(new Event('change')); });
  await sleep(900);
  const c = await e.q(() => window.__calls.filter(x => x[1] === 'set_value'));
  ok(c.length === 1 && c[0][2].entity_id === 'number.bms_grid_import_limit_kw' && c[0][2].value === 9.5, 'zmiana limitu → number.set_value 9,5: ' + JSON.stringify(c));
  await b.close();
  console.log(fails ? `FAILS ${fails}` : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
