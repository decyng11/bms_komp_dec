// EV i CWU w edytorze urządzeń: pola zależne od kategorii, zapis do devices_set, kafelek (sesja, prąd, temperatura), XSS
const { openCard, chromium } = require('./ui_env');
const { tab } = require('./extras_helpers');
const fs = require('fs');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const PAY = JSON.parse(fs.readFileSync('devices_payload.json', 'utf8'));
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  await e.q((pay) => {
    window.__svc = window.__svc || {}; window.__dvSet = [];
    window.__svc['bms_komp_dec.devices_get'] = () => ({ response: JSON.parse(JSON.stringify(pay)) });
    window.__svc['bms_komp_dec.devices_set'] = (m) => { const d = (m.service_data || m).devices; window.__dvSet.push(d); return { response: { devices: d, dropped: 0 } }; };
    const S = (v, a) => ({ state: String(v), attributes: a || {}, last_updated: 'x' });
    window.__states['sensor.bms_devices'] = S(3, { devices: pay.live, power_total: 1660 });
    window.__states['sensor.wallbox_moc'] = S(0, { unit_of_measurement: 'W' });
    window.__states['sensor.cwu_t'] = S(48, { unit_of_measurement: '°C' });
    window.__states['number.wallbox_prad'] = S(6);
    window.__states['number.bms_x'] = S(1);
    window.__el.hass = window.__mk();
  }, PAY);
  await tab(e, 'dev'); await sleep(1200);
  const setCat = async (c) => { await e.q((c) => { const R = __el.shadowRoot; const s = R.querySelector('[data-dvf="category"]'); s.value = c; s.dispatchEvent(new Event('change', { bubbles: true })); }, c); await sleep(200); };
  await e.q(() => __el.shadowRoot.querySelector('[data-dv="add"]').click()); await sleep(200);
  await setCat('ev');
  ok(await e.q(() => !!__el.shadowRoot.querySelector('[data-role="ev-form"]') && !__el.shadowRoot.querySelector('[data-role="dhw-form"]')), 'EV: widać formularz ładowarki, bez formularza CWU');
  ok(await e.q(() => !!__el.shadowRoot.querySelector('[data-dvf="ctl_mode"] option[value="now"]')), 'tryb „natychmiast” dostępny');
  ok(await e.q(() => Array.from(__el.shadowRoot.querySelectorAll('#dvNum option')).some((o) => o.value === 'number.wallbox_prad') && !Array.from(__el.shadowRoot.querySelectorAll('#dvNum option')).some((o) => o.value === 'number.bms_x')), 'lista encji prądu: number.*, bez własnych bms_');
  await e.q(() => {
    const R = __el.shadowRoot; const set = (k, v) => { const el = R.querySelector(`[data-dvf="${k}"]`); el.value = v; el.dispatchEvent(new Event('change', { bubbles: true })); };
    set('name', 'Wallbox <img src=x onerror=window.__pwn=1>'); set('power_eid', 'sensor.wallbox_moc'); set('switch_eid', 'switch.wallbox'); set('ctl_mode', 'now');
    set('ev_current_eid', 'number.wallbox_prad'); set('ev_max_a', '10'); set('ev_phases', '3'); set('ev_target_kwh', '20'); set('ev_grid_limit_w', '8000');
  });
  await e.q(() => __el.shadowRoot.querySelector('[data-dv="save"]').click()); await sleep(600);
  const sent = await e.q(() => window.__dvSet[window.__dvSet.length - 1]);
  const w = sent && sent.find((d) => d.category === 'ev');
  ok(w && w.ctl_mode === 'now' && w.ev_current_eid === 'number.wallbox_prad' && Number(w.ev_max_a) === 10 && Number(w.ev_phases) === 3 && Number(w.ev_target_kwh) === 20 && Number(w.ev_grid_limit_w) === 8000, 'zapis: pola EV trafiają do devices_set: ' + JSON.stringify(w && { m: w.ctl_mode, a: w.ev_max_a, p: w.ev_phases }));
  ok(await e.q(() => !window.__pwn), 'nazwa z HTML nie wykonuje kodu');
  // CWU
  await e.q(() => __el.shadowRoot.querySelector('[data-dv="add"]').click()); await sleep(200);
  await setCat('boiler');
  ok(await e.q(() => !!__el.shadowRoot.querySelector('[data-role="dhw-form"]') && !__el.shadowRoot.querySelector('[data-role="ev-form"]')), 'bojler: formularz CWU, bez formularza EV');
  ok(await e.q(() => __el.shadowRoot.querySelectorAll('[data-dvf="dhw_leg_dow"] option').length === 7 && __el.shadowRoot.querySelector('[data-dvf="dhw_leg_dow"]').value === '6'), 'antylegionella: 7 dni, domyślnie niedziela');
  ok(await e.q(() => Array.from(__el.shadowRoot.querySelectorAll('#dvTemp option')).some((o) => o.value === 'sensor.cwu_t')), 'lista czujników temperatury: sensory w °C');
  await e.q(() => {
    const R = __el.shadowRoot; const set = (k, v) => { const el = R.querySelector(`[data-dvf="${k}"]`); el.value = v; el.dispatchEvent(new Event('change', { bubbles: true })); };
    set('name', 'Bojler'); set('power_eid', 'sensor.wallbox_moc'); set('switch_eid', 'switch.bojler'); set('ctl_mode', 'pv');
    set('dhw_temp_eid', 'sensor.cwu_t'); set('dhw_max_c', '60'); set('dhw_boost_c', '55'); set('dhw_comfort_c', '45'); set('dhw_comfort_h', '6');
    R.querySelector('[data-dvf="dhw_leg"]').checked = true; R.querySelector('[data-dvf="dhw_leg"]').dispatchEvent(new Event('change', { bubbles: true }));
  });
  await e.q(() => __el.shadowRoot.querySelector('[data-dv="save"]').click()); await sleep(600);
  const sent2 = await e.q(() => window.__dvSet[window.__dvSet.length - 1]);
  const j = sent2 && sent2.find((d) => d.category === 'boiler');
  ok(j && j.dhw_temp_eid === 'sensor.cwu_t' && Number(j.dhw_max_c) === 60 && Number(j.dhw_boost_c) === 55 && Number(j.dhw_comfort_c) === 45 && j.dhw_leg === true, 'zapis: pola CWU trafiają do devices_set');
  // kafelek: sesja, prąd, temperatura
  const chip = await e.q(() => {
    window.__states['switch.wallbox'] = { state: 'on', attributes: {}, last_updated: 'x' };
    __el._dvS().data.control = { enabled: true, devices: { wb: { reason: 'natychmiast', sess: { kwh: 7.25, cost: 5.8 }, amps: 10, temp: 48 } } };
    __el.hass = __el._hass;
    return __el._dvCtlChip({ id: 'wb', category: 'ev', switch_eid: 'switch.wallbox', ctl_mode: 'now' });
  });
  ok(/natychmiast/.test(chip) && /sesja 7,3 kWh/.test(chip) && /5,80 zł/.test(chip) && /10 A/.test(chip) && /CWU 48 °C/.test(chip), 'kafelek: tryb, sesja, koszt, prąd, temperatura: ' + chip);
  ok(e.errs.length === 0, 'brak błędów JS ' + JSON.stringify(e.errs));
  await b.close();
  console.log(fails ? 'FAILS ' + fails : 'ALL OK');
  process.exit(fails ? 1 : 0);
})();
