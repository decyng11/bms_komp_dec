// Ukrywanie zakładki Urządzenia (switch.bms_hide_devices_tab) i pole progu oszczędzania energii
const { openCard, chromium } = require('./ui_env');
const { seed, curve, tab } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  await seed(e, { curve: curve() });
  const vis = () => e.q(() => { const t = __el.shadowRoot.getElementById('tabDev'); return !!t && t.style.display !== 'none'; });
  ok(await vis(), 'zakładka Urządzenia domyślnie widoczna');
  await e.q(() => {
    const S = (v, a) => ({ state: String(v), attributes: a || {}, last_updated: new Date().toISOString(), last_changed: new Date().toISOString() });
    __states['switch.bms_hide_devices_tab'] = S('on');
    __states['number.bms_device_shed_soc'] = S(30, { min: 0, max: 100, step: 1 });
    __el.hass = __mk();
  });
  await sleep(400);
  ok(!(await vis()), 'przełącznik włączony → zakładka ukryta');
  await tab(e, 'ems'); await sleep(400);
  const v = await e.q(() => { const i = __el.shadowRoot.querySelector('input[data-num-key="device_shed_soc"]'); return i && i.value; });
  ok(v === '30', 'pole progu oszczędzania pokazuje 30%: ' + v);
  await e.q(() => { __states['switch.bms_hide_devices_tab'].state = 'off'; __el.hass = __mk(); });
  await sleep(400);
  ok(await vis(), 'przełącznik wyłączony → zakładka wraca');
  await b.close();
  console.log(fails ? `FAILS ${fails}` : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
