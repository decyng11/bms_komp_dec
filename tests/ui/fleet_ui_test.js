// Flota (etap 1): sekcja z sumami, zwijane klastry, edytor (dodawanie/usuwanie/limity), zapis do fleet_set, XSS
const { openCard, chromium } = require('./ui_env');
const { tab } = require('./extras_helpers');
const fs = require('fs');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const PAY = JSON.parse(fs.readFileSync('devices_payload.json', 'utf8'));
const CFG = { clusters: [{ id: 'k1', name: 'Dom <img src=x onerror=window.__pwn=1>' }], inverters: [{ id: 'f1', name: 'F1', cluster: 'k1', role: 'master', pv_eid: 'sensor.pv1', power_eid: '', temp_eid: '', mode_eid: '' }],
  batteries: [{ id: 'b1', name: 'B1', cluster: 'k1', capacity_kwh: 10, type: 'LV', soc_eid: 'sensor.s1', power_eid: '', temp_eid: '' }] };
const FLEET = { config: CFG, limits: { inverters: 10, batteries: 30, clusters: 10 }, issues: [{ level: 'warn', cluster: 'k1', id: 'k1:x', text: 'Uwaga <b>x</b>' }],
  totals: { clusters: 1, inverters: 1, batteries: 1, pv_kw: 3.2, capacity_kwh: 10, soc: 55, soc_spread: null },
  clusters: [{ id: 'k1', name: CFG.clusters[0].name, pv_kw: 3.2, capacity_kwh: 10, soc: 55, status: 'warn',
    inverters: [{ id: 'f1', name: 'F1', role: 'master', power_kw: 3.2, temp_c: 40, mode: 'Zero export', online: true }],
    batteries: [{ id: 'b1', name: 'B1', type: 'LV', capacity_kwh: 10, soc: 55, power_kw: -1, temp_c: 25 }] }] };
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  await e.q(({ pay, fleet }) => {
    window.__svc = window.__svc || {}; window.__fl = [];
    window.__svc['bms_komp_dec.devices_get'] = () => ({ response: JSON.parse(JSON.stringify(pay)) });
    window.__svc['bms_komp_dec.fleet_get'] = () => ({ response: JSON.parse(JSON.stringify(fleet)) });
    window.__svc['bms_komp_dec.fleet_set'] = (m) => { window.__fl.push((m.service_data || m).fleet); return { response: JSON.parse(JSON.stringify(fleet)) }; };
    window.__el.hass = window.__mk();
  }, { pay: PAY, fleet: FLEET });
  await tab(e, 'dev'); await sleep(1200);
  const R = (f, a) => e.q(f, a);
  ok(await R(() => __el.shadowRoot.textContent.includes('🏭 Flota')), 'sekcja Flota widoczna');
  ok(await R(() => __el.shadowRoot.textContent.includes('55 %') || __el.shadowRoot.textContent.includes('55%')), 'sumy: SOC floty');
  ok(await R(() => !window.__pwn && !__el.shadowRoot.querySelector('img[src="x"]')), 'XSS: nazwa klastra jest zakodowana');
  ok(await R(() => !__el.shadowRoot.textContent.includes('F1: ')), 'klaster zwinięty — falowniki ukryte');
  await R(() => __el.shadowRoot.querySelector('[data-dv="fl-toggle"]').click()); await sleep(150);
  ok(await R(() => __el.shadowRoot.textContent.includes('F1') && __el.shadowRoot.textContent.includes('B1')), 'rozwinięcie klastra pokazuje falownik i baterię');
  await R(() => __el.shadowRoot.querySelector('[data-dv="fl-edit"]').click()); await sleep(200);
  ok(await R(() => !!__el.shadowRoot.querySelector('[data-flf="inverters.0.pv_eid"]')), 'edytor otwarty');
  await R(() => __el.shadowRoot.querySelector('[data-dv="fl-add-bat"]').click()); await sleep(150);
  await R(() => { const n = __el.shadowRoot.querySelector('[data-flf="batteries.1.capacity_kwh"]'); n.value = '7,5'; });
  await R(() => __el.shadowRoot.querySelector('[data-dv="fl-add-inv"]').click()); await sleep(150);
  ok(await R(() => __el.shadowRoot.querySelectorAll('[data-flf$=".capacity_kwh"]').length === 2 && __el.shadowRoot.querySelector('[data-flf="batteries.1.capacity_kwh"]').value === '7.5'), 'dodanie baterii/falownika zachowuje wpisane wartości');
  await R(() => __el.shadowRoot.querySelector('[data-dv="fl-add-cl"]').click()); await sleep(150);
  await R(() => __el.shadowRoot.querySelector('[data-dv="fl-save"]').click()); await sleep(500);
  const sent = await R(() => window.__fl[window.__fl.length - 1]);
  ok(sent && sent.clusters.length === 2 && sent.inverters.length === 2 && sent.batteries.length === 2 && sent.batteries[1].capacity_kwh === 7.5, 'fleet_set dostaje pełną konfigurację: ' + JSON.stringify(sent && [sent.clusters.length, sent.inverters.length, sent.batteries.length]));
  ok(await R(() => !__el.shadowRoot.querySelector('[data-dv="fl-save"]')), 'po zapisie wraca widok floty');
  // limity
  await R(() => __el.shadowRoot.querySelector('[data-dv="fl-edit"]').click()); await sleep(150);
  for (let i = 0; i < 12; i++) await R(() => { const x = __el.shadowRoot.querySelector('[data-dv="fl-add-inv"]'); if (x && !x.disabled) x.click(); });
  ok(await R(() => __el.shadowRoot.querySelectorAll('[data-flf$=".role"]').length === 10 && __el.shadowRoot.querySelector('[data-dv="fl-add-inv"]').disabled), 'limit 10 falowników');
  await R(() => __el.shadowRoot.querySelector('[data-dv="fl-del"][data-k="inverters"]').click()); await sleep(100);
  ok(await R(() => __el.shadowRoot.querySelectorAll('[data-flf$=".role"]').length === 9), 'usuwanie falownika');
  await R(() => __el.shadowRoot.querySelector('[data-dv="fl-cancel"]').click()); await sleep(100);
  ok(await R(() => !!__el.shadowRoot.querySelector('[data-dv="fl-edit"]')), 'anuluj wraca do widoku');
  await b.close();
  console.log(fails ? 'FAILS ' + fails : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
