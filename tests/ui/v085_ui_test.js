// 0.8.5: oszczędności i trafność prognoz (Zysk i log), „Plan zakłada” z korektą PV i kosztem zużycia,
// sterowanie urządzeniami (edytor, kafelek, główny przełącznik), Autotest w Diagnostyce.
const { openCard, chromium } = require('./ui_env');
const { seed, curve, REPORT, HEALTH, tab, sr, openSec } = require('./extras_helpers');
const fs = require('fs');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const DEV = JSON.parse(fs.readFileSync('devices_payload.json', 'utf8'));
const day = (i) => { const d = new Date(2026, 10, 6 - i); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
const INS = {
  pv_correction_on: true, wear_cost: 0,
  savings: {
    today: { days: 1, actual: 2.1, nobat: 5.4, simple: 3.9, vs_nobat: 3.3, vs_simple: 1.8 },
    last30: { days: 12, actual: 40.0, nobat: 95.5, simple: 70.2, vs_nobat: 55.5, vs_simple: 30.2 },
    month: { days: 6, actual: 20.0, nobat: 45.0, simple: 33.0, vs_nobat: 25.0, vs_simple: 13.0 },
    year: { days: 12, actual: 40.0, nobat: 95.5, simple: 70.2, vs_nobat: 55.5, vs_simple: 30.2 },
    total: { days: 0, actual: 0, nobat: 0, simple: 0, vs_nobat: 0, vs_simple: 0 },
    daily: Array.from({ length: 12 }, (_, i) => ({ date: day(11 - i), actual: 3, nobat: i === 4 ? 2 : 8, simple: 6, complete: i < 11, partial: i === 11 })),
    months: [], since: day(11), params: { cap: 10, eff: 0.9, floor: 15 },
  },
  accuracy: {
    days: Array.from({ length: 10 }, (_, i) => ({ date: day(10 - i), pv_fc: 10, pv_act: 8 + (i % 3), load_fc: 12, load_act: 10, soc_mae: 4.5 })),
    pv: { mape: 18.5, bias: 12.0, n: 10 }, load: { mape: 20.0, bias: 20.0, n: 10 }, soc: { mae: 4.5, n: 10 },
    pv_correction: { factor: 0.88, days: 10, ratio: 0.88 }, today: null,
  },
};
const ST = {
  version: '0.8.5', time: '2026-11-06T12:00:00+01:00', summary: { errors: 1, warnings: 1, ok: 2 }, commands: [],
  groups: [
    { name: 'Falownik i połączenie', checks: [{ id: 'live_soc', title: 'SOC baterii', status: 'ok', detail: 'sensor.inverter_battery = 80', fix: '' },
      { id: 'grid_v', title: 'Wykrywanie zaniku sieci', status: 'warn', detail: '0 V <img src=x onerror=window.__pwn=1>', fix: 'wskaż inną encję' }] },
    { name: 'Prognoza PV', checks: [{ id: 'pv_dziś', title: 'Prognoza PV godzinowa — dziś', status: 'error', detail: 'brak', fix: 'Zainstaluj Solcast' },
      { id: 'pv_corr', title: 'Korekta', status: 'ok', detail: '× 1.0', fix: '' }] },
  ],
};
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  const c = curve();
  await seed(e, { curve: c, report: REPORT(), health: HEALTH });
  await e.q(([ins, st, dev]) => {
    window.__svc = window.__svc || {}; window.__insN = 0; window.__stN = 0; window.__dvSet = [];
    window.__svc['bms_komp_dec.insights_get'] = () => { window.__insN++; return { response: JSON.parse(JSON.stringify(ins)) }; };
    window.__svc['bms_komp_dec.self_test'] = () => { window.__stN++; return { response: JSON.parse(JSON.stringify(st)) }; };
    window.__svc['bms_komp_dec.devices_get'] = () => ({ response: JSON.parse(JSON.stringify(dev)) });
    window.__svc['bms_komp_dec.devices_set'] = (m) => { const d = (m.service_data || m).devices; window.__dvSet.push(d); return { response: { devices: d, dropped: 0 } }; };
    const S = (v, a) => ({ state: String(v), attributes: a || {}, last_updated: 'x' });
    window.__states['switch.bms_device_control'] = S('off');
    window.__states['switch.bojler'] = S('off', { friendly_name: 'Bojler' });
    window.__states['input_boolean.pompa'] = S('off');
    const pc = window.__states['sensor.bms_plan_curve'];
    pc.attributes.assumptions = { load_rest_today_kwh: 4.2, load_today_source: 'tempo dnia', load_tomorrow_kwh: 11, pv_tomorrow_kwh: 6.3, pv_source: 'Solcast', pv_hourly_tomorrow: true, pv_factor: 0.88, wear_cost: 0.2 };
    window.__el.hass = window.__mk();
  }, [INS, ST, DEV]);

  // ---------- Zysk i log: oszczędności i trafność
  await tab(e, 'log'); await sleep(1200);
  const sv = await sr(e, '#exSavBox');
  ok(sv && /Koszt energii/.test(sv) && /40,00 zł/.test(sv) && /95,50 zł/.test(sv) && /70,20 zł/.test(sv) && /\+55,50 zł/.test(sv) && /\+30,20 zł/.test(sv), 'oszczędności: 30 dni, trzy warianty i różnice');
  ok(await e.q(() => window.__insN === 1), 'jedno wywołanie insights_get');
  await e.q(() => __el.shadowRoot.querySelector('#exSavBox [data-exi="period"][data-p="month"]').click()); await sleep(200);
  ok(/\+25,00 zł/.test(await sr(e, '#exSavBox')), 'zmiana okresu: ten miesiąc');
  await e.q(() => __el.shadowRoot.querySelector('#exSavBox [data-exi="period"][data-p="total"]').click()); await sleep(200);
  ok(/Brak danych za ten okres/.test(await sr(e, '#exSavBox')), 'okres bez danych → komunikat');
  await e.q(() => __el.shadowRoot.querySelector('#exSavBox [data-exi="period"][data-p="last30"]').click()); await sleep(200);
  ok(await e.q(() => __el.shadowRoot.querySelectorAll('#exSavBox div[title*="bez baterii"]').length === 12), 'wykres dzienny: 12 dni');
  ok(await e.q(() => Array.from(__el.shadowRoot.querySelectorAll('#exSavBox div[title]')).some((x) => /−1,00 zł|-1,00 zł|−1,00/.test(x.title))), 'dzień ze stratą widoczny na wykresie');
  const acc = await sr(e, '#exAccBox');
  ok(acc && /18,5%/.test(acc) && /zawyżona o 12%/.test(acc) && /20,0%/.test(acc) && /4,5 pp/.test(acc) && /× 0,88/.test(acc), 'trafność: błąd PV, zużycia, SOC i korekta');
  ok(await e.q(() => __el.shadowRoot.querySelectorAll('#exAccBox div[title*="prognoza"]').length === 20), 'wykresy prognoza/wykonanie: PV i zużycie po 10 dni');
  // błąd usługi
  const e2 = await openCard(b, {});
  await seed(e2, { curve: c, report: REPORT(), health: HEALTH });
  await e2.q(() => { window.__svc = { 'bms_komp_dec.insights_get': () => { throw new Error('Unknown service'); } }; window.__el.hass = window.__mk(); });
  await tab(e2, 'log'); await sleep(900);
  ok(/Nie udało się wczytać/.test(await sr(e2, '#exSavBox')) && /0\.8\.5/.test(await sr(e2, '#exSavBox')), 'starsza integracja → czytelny komunikat');
  ok(e2.errs.length === 0, 'brak błędów JS (błąd usługi) ' + JSON.stringify(e2.errs));

  // ---------- EMS: „Plan zakłada”
  await tab(e, 'ems'); await sleep(900);
  const pl = await sr(e, '#exPlanBox');
  ok(pl && /prognoza PV × 0,88/.test(pl) && /zużycie baterii 0,20 zł\/kWh/.test(pl), '„Plan zakłada”: korekta PV i koszt zużycia');

  // ---------- Urządzenia: sterowanie
  await tab(e, 'dev'); await sleep(900);
  ok(/Sterowanie urządzeniami wyłączone/.test(await sr(e, '#devRoot')), 'główny przełącznik widoczny (wyłączony)');
  await e.q(() => __el.shadowRoot.querySelector('[data-dv="edit"]').click()); await sleep(200);
  ok(await e.q(() => Array.from(__el.shadowRoot.querySelectorAll('#dvSw option')).map((o) => o.value).join(',') === 'input_boolean.pompa,switch.bojler'), 'podpowiedzi przełączników (bez switch.bms_*)');
  await e.q(() => { const R = __el.shadowRoot; const m = R.querySelector('[data-dvf="ctl_mode"]'); m.value = 'pv'; m.dispatchEvent(new Event('change', { bubbles: true })); });
  await e.q(() => __el.shadowRoot.querySelector('[data-dv="save"]').click()); await sleep(200);
  ok(/wskaż jego przełącznik/.test(await sr(e, '#dvMsg')), 'tryb bez przełącznika → komunikat');
  await e.q(() => { const R = __el.shadowRoot; R.querySelector('[data-dvf="switch_eid"]').value = 'light.lampa'; });
  await e.q(() => __el.shadowRoot.querySelector('[data-dv="save"]').click()); await sleep(200);
  ok(/switch\.nazwa albo input_boolean/.test(await sr(e, '#dvMsg')), 'zły przełącznik → komunikat');
  await e.q(() => { const R = __el.shadowRoot; R.querySelector('[data-dvf="switch_eid"]').value = 'switch.bojler'; R.querySelector('[data-dvf="ctl_power_w"]').value = '2500'; R.querySelector('[data-dvf="ctl_max_h"]').value = '3'; });
  await e.q(() => __el.shadowRoot.querySelector('[data-dv="save"]').click()); await sleep(600);
  const saved = await e.q(() => window.__dvSet[0]);
  const d0 = saved && saved[0];
  ok(d0 && d0.switch_eid === 'switch.bojler' && d0.ctl_mode === 'pv' && d0.ctl_power_w === 2500 && d0.ctl_max_h === 3, 'zapis: przełącznik, tryb, moc, limit ' + JSON.stringify(d0 && [d0.switch_eid, d0.ctl_mode, d0.ctl_power_w, d0.ctl_max_h]));
  // kafelek ze stanem sterowania + główny przełącznik
  await e.q((dev) => {
    const p = JSON.parse(JSON.stringify(dev)); p.devices[0].switch_eid = 'switch.bojler'; p.devices[0].ctl_mode = 'pv';
    p.control = { enabled: true, devices: { [p.devices[0].id]: { mode: 'pv', reason: 'nadwyżka PV 3.1 kW', manual: false } } };
    window.__svc['bms_komp_dec.devices_get'] = () => ({ response: p });
    window.__states['switch.bms_device_control'] = { state: 'on', attributes: {}, last_updated: 'x' }; window.__el.hass = window.__mk();
  }, DEV);
  await e.q(() => __el.shadowRoot.querySelector('[data-dv="reload"]').click()); await sleep(700);
  const live = await sr(e, '#dvLive');
  ok(/nadwyżka PV · wył\. · nadwyżka PV 3\.1 kW/.test(live), 'kafelek: tryb, stan i powód');
  ok(/Sterowanie urządzeniami włączone \(1 urządzenie/.test(await sr(e, '#devRoot')), 'główny przełącznik: włączony, 1 urządzenie');
  await e.q(() => { const c = __el.shadowRoot.querySelector('[data-dv="ctl-master"]'); c.checked = false; c.dispatchEvent(new Event('change', { bubbles: true })); }); await sleep(300);
  ok(await e.q(() => (window.__calls || []).some((c) => c[0] === 'switch' && c[1] === 'turn_off' && /device_control/.test(JSON.stringify(c[2])))), 'wyłączenie sterowania: switch.turn_off');

  // ---------- Diagnostyka → Autotest
  await openSec(e, 'selftest'); await sleep(700);
  const t = await sr(e, '#dgSt');
  ok(await e.q(() => window.__stN === 1), 'autotest uruchomiony automatycznie raz');
  ok(t && /1 błąd/.test(t) && /Falownik i połączenie/.test(t) && /Zainstaluj Solcast/.test(t), 'autotest: podsumowanie, grupy, podpowiedzi');
  ok(await e.q(() => !__el.shadowRoot.querySelector('#dgSt img') && !window.__pwn), 'autotest: treść zescape-owana');
  ok(await e.q(() => { const d = __el.shadowRoot.querySelectorAll('#dgSt details'); return d.length === 2 && d[0].open && d[1].open; }), 'grupy z uwagami rozwinięte');
  await e.q(() => { window.__clip = null; try { Object.defineProperty(navigator, 'clipboard', { value: { writeText: async (x) => { window.__clip = x; } }, configurable: true }); } catch (err) { /* */ } });
  await e.q(() => __el.shadowRoot.querySelector('[data-act="st-copy"]').click()); await sleep(300);
  const clip = await e.q(() => window.__clip || (__el.shadowRoot.getElementById('dgStTxt') || {}).value);
  ok(clip && /EMS komp-dec 0\.8\.5 — autotest/.test(clip) && /\[BŁĄD\] Prognoza PV godzinowa — dziś: brak → Zainstaluj Solcast/.test(clip) && /\[OK\] SOC baterii/.test(clip), 'raport tekstowy do skopiowania');
  await e.q(() => __el.shadowRoot.querySelector('[data-act="st-run"]').click()); await sleep(400);
  ok(await e.q(() => window.__stN === 2), 'ponowne uruchomienie');
  ok(e.errs.length === 0, 'brak błędów JS ' + JSON.stringify(e.errs));
  await e.page.setViewportSize({ width: 420, height: 1600 }); await tab(e, 'log'); await sleep(500);
  const el = await e.page.evaluateHandle(() => __el.shadowRoot.querySelector('#exSavBox').closest('.section'));
  await el.screenshot({ path: 'v085_savings.png' });
  const el2 = await e.page.evaluateHandle(() => __el.shadowRoot.querySelector('#exAccBox').closest('.section'));
  await el2.screenshot({ path: 'v085_accuracy.png' });
  await b.close(); console.log(fails ? `FAILS ${fails}` : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
