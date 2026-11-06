// 0.8.1: konfigurator powiadomień w Diagnostyce (za hasłem)
const { openCard, chromium } = require('./ui_env');
const { seed, curve, REPORT, HEALTH, tab, sr, openSec } = require('./extras_helpers');
const fs = require('fs');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const PAY = JSON.parse(fs.readFileSync('notify_payload.json', 'utf8'));
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  await seed(e, { curve: curve(), report: REPORT(), health: HEALTH });
  await e.q((pay) => {
    window.__svc = window.__svc || {}; window.__ntSet = []; window.__ntTest = 0;
    window.__svc['bms_komp_dec.notify_settings_get'] = () => ({ response: JSON.parse(JSON.stringify(pay)) });
    window.__svc['bms_komp_dec.notify_settings_set'] = (m) => { const st = (m.service_data || m).settings; window.__ntSet.push(st); return { response: { settings: st } }; };
    window.__svc['bms_komp_dec.notify_test'] = () => { window.__ntTest++; return { response: { phone: true, notify_service: 'notify.mobile_app_tel' } }; };
  }, PAY);
  await tab(e, 'diag'); await sleep(400);
  ok(await e.q(() => !__el.shadowRoot.querySelector('#dgNt')), 'przed hasłem: konfiguratora nie widać');
  await openSec(e, 'notify'); await sleep(600);
  const t = await sr(e, '#dgNt');
  ok(t && /notify\.mobile_app_tel/.test(t) && /Cisza nocna/.test(t), 'konfigurator: usługa telefonu i cisza nocna');
  const nRows = await e.q(() => __el.shadowRoot.querySelectorAll('#dgNt [data-nt-row]').length);
  ok(nRows === PAY.catalog.length, `wszystkie rodzaje (${nRows}/${PAY.catalog.length})`);
  ok(await e.q(() => __el.shadowRoot.querySelector('#dgNt [data-act="nt-save"]').disabled), 'zapis nieaktywny bez zmian');
  // zmiany: włącz sprzedaż, tylko HA dla low_soc, odstęp 1 h, próg weak_pv, cisza 23–6, tygodniowe w sobotę
  await e.q(() => {
    const R = __el.shadowRoot; const fire = (el, v) => { if (el.type === 'checkbox') el.checked = v; else el.value = v; el.dispatchEvent(new Event('change', { bubbles: true })); };
    fire(R.querySelector('[data-nk="sale"][data-nf="on"]'), true);
    fire(R.querySelector('[data-nk="low_soc"][data-nf="phone"]'), '0');
    fire(R.querySelector('[data-nk="low_soc"][data-nf="cooldown"]'), '60');
    fire(R.querySelector('[data-nk="weak_pv"][data-nf="thr"]'), '5.5');
    fire(R.querySelector('[data-nk="_sched"][data-nf="quiet.on"]'), true);
    fire(R.querySelector('[data-nk="_sched"][data-nf="quiet.start"]'), '23:00');
    fire(R.querySelector('[data-nk="_sched"][data-nf="weekly.weekday"]'), '5');
  });
  ok(await e.q(() => !__el.shadowRoot.querySelector('#dgNt [data-act="nt-save"]').disabled) && /niezapisane/.test(await sr(e, '#dgNtMsg')), 'po zmianie: zapis aktywny i ostrzeżenie');
  await e.q(() => __el.shadowRoot.querySelector('#dgNt [data-act="nt-save"]').click()); await sleep(400);
  const sent = await e.q(() => window.__ntSet[0]);
  ok(sent && sent.kinds.sale.on === true && sent.kinds.low_soc.phone === false && sent.kinds.low_soc.cooldown === 60 && sent.kinds.weak_pv.thr === 5.5, 'zapis: rodzaje ' + JSON.stringify(sent && [sent.kinds.sale, sent.kinds.low_soc, sent.kinds.weak_pv]));
  ok(sent && sent.sched.quiet.on === true && sent.sched.quiet.start === '23:00' && sent.sched.weekly.weekday === 5, 'zapis: harmonogram ' + JSON.stringify(sent && sent.sched));
  ok(await e.q(() => __el.shadowRoot.querySelector('#dgNt [data-act="nt-save"]').disabled), 'po zapisie: brak niezapisanych zmian');
  // grupa: wszystkie / żadne
  await e.q(() => __el.shadowRoot.querySelector('#dgNt [data-act="nt-all"][data-g="Działanie"][data-v="1"]').click()); await sleep(200);
  ok(await e.q(() => ['sale', 'grid_charge', 'price_reaction', 'storm'].every((k) => __el.shadowRoot.querySelector(`[data-nk="${k}"][data-nf="on"]`).checked)), 'grupa „Działanie”: wszystkie włączone');
  await e.q(() => __el.shadowRoot.querySelector('#dgNt [data-act="nt-test"]').click()); await sleep(300);
  ok(await e.q(() => window.__ntTest === 1), 'przycisk testowy wywołuje usługę');
  ok(/Wysłano na notify\.mobile_app_tel/.test(await sr(e, '#dgToast')), 'komunikat po teście');
  // wstrzyknięcie HTML przez nazwę usługi
  await e.q((pay) => { const p = JSON.parse(JSON.stringify(pay)); p.notify_service = '<img src=x onerror=window.__pwn=1>'; p.catalog[0].name = '<img src=x onerror=window.__pwn=1>'; window.__svc['bms_komp_dec.notify_settings_get'] = () => ({ response: p }); }, PAY);
  await e.q(() => { window.confirm = () => true; __el.shadowRoot.querySelector('#dgNt [data-act="nt-reload"]').click(); }); await sleep(500);
  ok(await e.q(() => !__el.shadowRoot.querySelector('#dgNt img') && !window.__pwn), 'brak wstrzyknięcia HTML');
  const el = await e.page.evaluateHandle(() => __el.shadowRoot.querySelector('#dgNt'));
  await e.page.setViewportSize({ width: 1100, height: 1400 }); await sleep(200);
  await el.screenshot({ path: 'notify_cfg.png' });
  ok(e.errs.length === 0, 'brak błędów JS ' + JSON.stringify(e.errs));
  await b.close(); console.log(fails ? `FAILS ${fails}` : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
