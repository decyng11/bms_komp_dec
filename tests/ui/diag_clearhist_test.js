const { openCard, chromium } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  await e.q(() => {
    window.__states['button.bms_wyczysc_historie_zuzycia'] = { state: 'unknown', attributes: { friendly_name: 'Wyczyść historię zużycia' }, last_updated: new Date().toISOString(), last_changed: new Date().toISOString() };
    __el.hass = __mk();
  });
  await e.q(() => __el.shadowRoot.querySelector('[data-tab="diag"]').click());
  await e.page.waitForFunction(() => !!__el.shadowRoot.getElementById('dgPw'), null, { timeout: 8000 });
  await e.q(() => { const s = __el.shadowRoot; s.getElementById('dgPw').value = 'slonce'; s.querySelector('[data-act=unlock]').click(); });
  await e.page.waitForFunction(() => !!__el.shadowRoot.getElementById('dgBody'), null, { timeout: 5000 });
  await e.q(() => __el.shadowRoot.querySelector('[data-sec=adv]').click());
  await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('[data-act=clear-load-hist]'), null, { timeout: 5000 });
  ok(true, 'przycisk jest w Diagnostyka → Zaawansowane');
  const pressed = () => e.q(() => window.__calls.filter(c => c[0] === 'button' && c[1] === 'press' && c[2].entity_id === 'button.bms_wyczysc_historie_zuzycia').length);

  // anuluj → bez wywołania
  await e.q(() => __el.shadowRoot.querySelector('[data-act=clear-load-hist]').click());
  await sleep(200);
  ok(await e.q(() => !!__el.shadowRoot.querySelector('.dg-modal')), 'klik otwiera okno potwierdzenia');
  ok(await e.q(() => /nie da się cofnąć/.test(__el.shadowRoot.querySelector('.dg-modal').textContent)), 'okno ostrzega, że operacji nie da się cofnąć');
  await e.q(() => __el.shadowRoot.querySelector('.dg-modal [data-id=cancel]').click());
  await sleep(300);
  ok(await pressed() === 0, 'anuluj: przycisk NIE został wciśnięty');

  // bez zaznaczenia zgody OK jest zablokowane
  await e.q(() => __el.shadowRoot.querySelector('[data-act=clear-load-hist]').click());
  await sleep(200);
  ok(await e.q(() => __el.shadowRoot.querySelector('.dg-modal [data-id=ok]').disabled), 'bez zaznaczenia zgody „Wyczyść historię” jest nieaktywne');
  await e.q(() => { __el.shadowRoot.querySelector('.dg-modal [data-id=ok]').click(); });
  await sleep(300);
  ok(await pressed() === 0, 'zablokowane OK nie wciska przycisku');

  // zgoda + OK → press
  await e.q(() => { const m = __el.shadowRoot.querySelector('.dg-modal'); m.querySelector('#dgNeed').click(); m.querySelector('[data-id=ok]').click(); });
  await sleep(600);
  ok(await pressed() === 1, 'po potwierdzeniu wywołano button.press na button.bms_wyczysc_historie_zuzycia');
  await b.close();
  console.log(fails ? `FAILS ${fails}` : 'FAILS 0'); process.exit(fails ? 1 : 0);
})();
