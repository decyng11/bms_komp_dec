// 0.8.4: zakładka „Urządzenia” — wyszukiwanie urządzeń z licznikiem kWh
const { openCard, chromium } = require('./ui_env');
const { tab, sr } = require('./extras_helpers');
const fs = require('fs');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const PAY = JSON.parse(fs.readFileSync('devices_payload.json', 'utf8'));
const DISC = { free_slots: 2, total: 3, energy_dashboard: true, skipped: { home: 2, bms: 5, helper: 1, added: 3 }, candidates: [
  { key: 'dev1', name: 'Wallbox', room: 'Garaż', category: 'ev', energy_eid: 'sensor.ev_e', power_eid: 'sensor.ev_p', power_w: 7200, stats: true, energy_dashboard: true, unavailable: false, integration: 'easee',
    energy_options: [{ eid: 'sensor.ev_e', unit: 'kwh', value: 1234.5, stats: true }], power_options: [{ eid: 'sensor.ev_p', unit: 'w', value: 7200 }] },
  { key: 'dev2', name: 'Pralka <img src=x onerror=window.__pwn=1>', room: '', category: 'washer', energy_eid: 'sensor.pr_e', power_eid: 'sensor.pr_p', power_w: 5, stats: true, energy_dashboard: false, unavailable: false, integration: 'shelly',
    energy_options: [{ eid: 'sensor.pr_e', unit: 'kwh', value: 50, stats: true }, { eid: 'sensor.pr_today', unit: 'kwh', value: 0.4, stats: true }], power_options: [{ eid: 'sensor.pr_p', unit: 'w', value: 5 }] },
  { key: 'sensor.x_e', name: 'Gniazdko', room: '', category: 'other', energy_eid: 'sensor.x_e', power_eid: '', power_w: null, stats: false, energy_dashboard: false, unavailable: true, integration: 'tuya',
    energy_options: [{ eid: 'sensor.x_e', unit: 'wh', value: null, stats: false }], power_options: [] } ] };
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  await e.q(([pay, disc]) => {
    window.__svc = window.__svc || {}; window.__dvSet = []; window.__disc = 0;
    window.__svc['bms_komp_dec.devices_get'] = () => ({ response: JSON.parse(JSON.stringify(pay)) });
    window.__svc['bms_komp_dec.devices_discover'] = () => { window.__disc++; return { response: JSON.parse(JSON.stringify(disc)) }; };
    window.__svc['bms_komp_dec.devices_set'] = (m) => { const d = (m.service_data || m).devices; window.__dvSet.push(d); return { response: { devices: d, dropped: 0 } }; };
    window.__el.hass = window.__mk();
  }, [PAY, DISC]);
  await tab(e, 'dev'); await sleep(1000);
  ok(await e.q(() => !!__el.shadowRoot.querySelector('[data-dv="disc"]')), 'przycisk „Wyszukaj urządzenia” dla administratora');
  await e.q(() => __el.shadowRoot.querySelector('[data-dv="disc"]').click()); await sleep(400);
  const t = await sr(e, '#devRoot');
  ok(await e.q(() => window.__disc === 1), 'wywołana usługa devices_discover');
  ok(/Wallbox/.test(t) && /Gniazdko/.test(t) && /panel Energia/.test(t) && /niedostępne/.test(t) && /bez historii/.test(t) && /7\s?200 W|7200 W/.test(t), 'lista: nazwy, oznaczenia, moc teraz');
  ok(/2 liczników domu/.test(t) && /5 encji BMS/.test(t) && /3 już dodanych/.test(t), 'informacja o pominiętych');
  ok(await e.q(() => !__el.shadowRoot.querySelector('#devRoot img') && !window.__pwn), 'nazwa zescape-owana');
  ok(await e.q(() => { const c = __el.shadowRoot.querySelectorAll('[data-dvd="on"]'); return c[0].checked && !c[1].checked && !c[2].checked; }), 'z panelu Energia zaznaczone od razu');
  ok(/Dodaj zaznaczone \(1\)/.test(t) && /Wolnych miejsc: 2/.test(t), 'licznik zaznaczonych i wolnych miejsc');
  // zaznacz wszystkie → przekroczony limit
  await e.q(() => __el.shadowRoot.querySelector('[data-dv="disc-all"]').click()); await sleep(200);
  ok(await e.q(() => __el.shadowRoot.querySelector('[data-dv="disc-add"]').disabled && /Za dużo/.test(__el.shadowRoot.querySelector('#dvMsg').textContent)), 'za dużo zaznaczonych → przycisk zablokowany');
  // odznacz gniazdko, zmień pralce licznik i kategorię, nazwę
  await e.q(() => { const c = __el.shadowRoot.querySelectorAll('[data-dvd="on"]')[2]; c.checked = false; c.dispatchEvent(new Event('change', { bubbles: true })); }); await sleep(200);
  await e.q(() => { const R = __el.shadowRoot; const s = R.querySelector('[data-dvd="energy_eid"][data-k="dev2"]'); s.value = 'sensor.pr_today'; s.dispatchEvent(new Event('change', { bubbles: true }));
    const n = R.querySelector('[data-dvd="name"][data-k="dev2"]'); n.value = 'Pralka Bosch';
    const c = R.querySelector('[data-dvd="category"][data-k="dev2"]'); c.value = 'dryer'; c.dispatchEvent(new Event('change', { bubbles: true })); }); await sleep(200);
  ok(await e.q(() => __el.shadowRoot.querySelector('[data-dvd="name"][data-k="dev2"]').value === 'Pralka Bosch'), 'zmiana kategorii nie kasuje wpisanej nazwy');
  await e.q(() => { const p = __el.shadowRoot.querySelector('[data-dvd="power_eid"][data-k="dev1"]'); p.value = ''; p.dispatchEvent(new Event('change', { bubbles: true })); }); await sleep(100);
  await e.q(() => __el.shadowRoot.querySelector('[data-dv="disc-add"]').click()); await sleep(700);
  const saved = await e.q(() => window.__dvSet[0]);
  const n0 = PAY.devices.length;
  ok(saved && saved.length === n0 + 2, 'zapis: istniejące + 2 nowe (' + (saved && saved.length) + ')');
  const w = saved && saved.find((d) => d.name === 'Wallbox'); const p = saved && saved.find((d) => d.name === 'Pralka Bosch');
  ok(w && w.category === 'ev' && w.energy_eid === 'sensor.ev_e' && w.power_eid === '' && w.room === 'Garaż' && w.flexible === true && w.cycles === true, 'wallbox: kategoria i domyślne, bez mocy');
  ok(p && p.category === 'dryer' && p.energy_eid === 'sensor.pr_today' && p.power_eid === 'sensor.pr_p' && p.icon === '🌀' && !('_autoName' in p) && !('_new' in p), 'pralka: zmieniony licznik, kategoria, ikona');
  ok(/Dodano 2 urządzenia/.test(await sr(e, '#devRoot')), 'komunikat po dodaniu i powrót do listy');
  // pusta lista i błąd
  await e.q(() => { window.__svc['bms_komp_dec.devices_discover'] = () => ({ response: { candidates: [], skipped: { home: 1 }, free_slots: 10 } }); });
  await e.q(() => __el.shadowRoot.querySelector('[data-dv="disc"]').click()); await sleep(300);
  ok(/Nie znalazłem nowych urządzeń/.test(await sr(e, '#devRoot')), 'brak wyników → komunikat');
  await e.q(() => __el.shadowRoot.querySelector('[data-dv="disc-cancel"]').click()); await sleep(200);
  await e.q(() => { window.__svc['bms_komp_dec.devices_discover'] = () => { throw new Error('Unauthorized'); }; });
  await e.q(() => __el.shadowRoot.querySelector('[data-dv="disc"]').click()); await sleep(300);
  ok(/Nie udało się wyszukać/.test(await sr(e, '#devRoot')), 'błąd usługi → komunikat');
  ok(e.errs.length === 0, 'brak błędów JS ' + JSON.stringify(e.errs));
  await b.close(); console.log(fails ? `FAILS ${fails}` : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
