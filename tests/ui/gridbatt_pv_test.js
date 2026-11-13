// Znacznik „energia z sieci w baterii”, karta „Prognoza PV” w diagnostyce (źródła, wariant encji, zerowanie nauki), ostrzeżenie o 00:00
const { openCard, chromium } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  const setRs = (attrs) => e.q((attrs) => {
    const now = new Date().toISOString();
    __states['sensor.bms_reserve_soc'] = { state: '40', attributes: Object.assign({ inverter_floor: 25, capacity_kwh: 10 }, attrs), last_updated: now, last_changed: now };
    __states['button.bms_wyzeruj_korekte_pv'] = { state: 'unknown', attributes: { friendly_name: 'Wyzeruj naukę korekty prognozy PV' }, last_updated: now, last_changed: now };
    __el.hass = __mk();
  }, attrs);
  const badge = () => e.q(() => { const w = __el.shadowRoot.getElementById('warn-grid-batt'), g = __el.shadowRoot.getElementById('badge-grid-batt'); return { on: w.classList.contains('on'), t: g.textContent, danger: g.classList.contains('danger') }; });

  await setRs({ grid_batt_kwh: 0, grid_batt_block: null }); await sleep(400);
  ok(!(await badge()).on, 'licznik 0: znacznik ukryty');
  await setRs({ grid_batt_kwh: 2.4, grid_batt_block: 'w baterii jest ~2,4 kWh energii naładowanej z sieci' }); await sleep(400);
  let r = await badge();
  ok(r.on && /2,4 kWh energii z sieci/.test(r.t) && /sprzedaż zablokowana/.test(r.t) && r.danger, 'licznik 2,4 kWh z blokadą: czerwony znacznik z opisem: ' + r.t);
  await setRs({ grid_batt_kwh: 0.3, grid_batt_block: null }); await sleep(400);
  r = await badge();
  ok(r.on && !/zablokowana/.test(r.t) && !r.danger, 'poniżej tolerancji: informacja bez blokady: ' + r.t);

  // 00:00 w polu godziny → ostrzeżenie zamiast „Zapisano”
  await e.q(() => { __el.shadowRoot.querySelector('[data-tab="ems"]').click(); });
  await sleep(300);
  await e.q(() => { const i = __el.shadowRoot.querySelector('[data-time-key="stop_grid_charge"]'); i.value = '00:00'; i.dispatchEvent(new Event('change', { bubbles: true })); });
  await sleep(1500);
  const toast = await e.q(() => Array.from(document.body.children).map((x) => x.textContent || '').filter((t) => /00:00/.test(t)).join(' '));
  ok(/00:00 oznacza/.test(toast), 'wpisanie 00:00: ostrzeżenie, że okno nie zadziała: ' + toast.slice(0, 80));

  // diagnostyka → Zaawansowane → karta „Prognoza PV”
  await setRs({ pv_forecast_source: 'Solcast', pv_entity_variant: 'estimate10',
    pv_daily: [{ kwh: 4.3, raw: 3.6, factor: 1.2, n: 9 }],
    pv_sources: [{ name: 'Solcast', today: 3.6, tomorrow: 5.1 }, { name: 'Forecast.Solar', today: 4.4, tomorrow: null }] });
  await e.q(() => __el.shadowRoot.querySelector('[data-tab="diag"]').click());
  await e.page.waitForFunction(() => !!__el.shadowRoot.getElementById('dgPw'), null, { timeout: 8000 });
  await e.q(() => { const s = __el.shadowRoot; s.getElementById('dgPw').value = 'slonce'; s.querySelector('[data-act=unlock]').click(); });
  await e.page.waitForFunction(() => !!__el.shadowRoot.getElementById('dgBody'), null, { timeout: 5000 });
  await e.q(() => __el.shadowRoot.querySelector('[data-sec=adv]').click());
  await e.page.waitForFunction(() => !!__el.shadowRoot.getElementById('dgPvCard'), null, { timeout: 5000 });
  const card = await e.q(() => { const c = __el.shadowRoot.getElementById('dgPvCard'); return { t: c.textContent, rows: c.querySelectorAll('#dgPvSrc tbody tr').length, v: !!c.querySelector('#dgPvVariant') }; });
  ok(card.rows === 2 && /Solcast\s*\(używane\)/.test(card.t) && /Forecast\.Solar/.test(card.t) && /3,6 kWh/.test(card.t) && /4,4 kWh/.test(card.t), 'porównanie źródeł: 2 wiersze z wartościami na dziś');
  ok(card.v && /pesymistyczny/.test(card.t), 'ostrzeżenie: encja Solcast pokazuje wariant pesymistyczny');
  ok(/korekta ×1,20 z 9 dni/.test(card.t), 'opis bieżącej korekty: ' + card.t.slice(0, 140));
  const pressed = () => e.q(() => window.__calls.filter(c => c[0] === 'button' && c[1] === 'press' && c[2].entity_id === 'button.bms_wyzeruj_korekte_pv').length);
  await e.q(() => __el.shadowRoot.querySelector('[data-act=reset-pv-learn]').click());
  await sleep(250);
  ok(await e.q(() => !!__el.shadowRoot.querySelector('.dg-modal') && __el.shadowRoot.querySelector('.dg-modal [data-id=ok]').disabled), 'zerowanie nauki: okno potwierdzenia, OK zablokowane bez zgody');
  await e.q(() => __el.shadowRoot.querySelector('.dg-modal [data-id=cancel]').click());
  await sleep(300);
  ok(await pressed() === 0, 'anuluj: nic nie wciśnięto');
  await e.q(() => __el.shadowRoot.querySelector('[data-act=reset-pv-learn]').click());
  await sleep(250);
  await e.q(() => { const m = __el.shadowRoot.querySelector('.dg-modal'); m.querySelector('#dgNeed').click(); m.querySelector('[data-id=ok]').click(); });
  await sleep(700);
  ok(await pressed() === 1, 'po potwierdzeniu: button.press na button.bms_wyzeruj_korekte_pv');
  await b.close();
  console.log(fails ? `FAILS ${fails}` : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
