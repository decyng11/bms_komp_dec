// Diagnostyka → Dziennik zmian: karta „Zmiany ustawień EMS” (kto, kiedy, było → jest, Przywróć)
const { openCard, chromium } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  await e.q(() => {
    window.__svc = { 'bms_komp_dec.settings_log_get': () => ({ response: { items: [] } }) };
    __el.shadowRoot.querySelector('[data-tab="diag"]').click();
  });
  await e.page.waitForFunction(() => typeof __el._dgSetLogCard === 'function', null, { timeout: 8000 });
  const html = await e.q(() => {
    __el._dgSetLogBusy = true;                       // bez wywołania usługi — dane wstawiamy ręcznie
    __states['number.bms_x'] = { entity_id: 'number.bms_x', state: '30', attributes: { friendly_name: 'Min SOC' } };
    __el.hass = __mk();
    __el._dgSetLog = [{ id: 2, ts: 1700000000, eid: 'number.bms_x', from: '20', to: '30', who: 'Jan <b>x</b>' }];
    return __el._dgSetLogCard();
  });
  ok(/Zmiany ustawień EMS/.test(html), 'karta jest');
  ok(/Min SOC/.test(html) && />30</.test(html) && /20/.test(html), 'nazwa encji i zmiana było → jest');
  ok(/data-act="setlog-undo"/.test(html), 'przycisk Przywróć');
  ok(!/<b>x<\/b>/.test(html) && /&lt;b&gt;x/.test(html), 'nazwa użytkownika jest escapowana (XSS)');
  const empty = await e.q(() => { __el._dgSetLog = []; return __el._dgSetLogCard(); });
  ok(/Brak zmian ustawień EMS/.test(empty), 'pusty dziennik: komunikat');
  await b.close();
  console.log(fails ? `FAILS ${fails}` : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
