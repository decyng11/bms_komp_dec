// „Co dziś nie działa” w Ustawienia → Diagnostyka → Przegląd: lista z monitor_status.issues, XSS, ⚠ na zakładce, brak w banerze
const { openCard, chromium } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, { admin: true, mobile: false });
  const nowS = Math.floor(Date.now() / 1000);
  await e.q((nowS) => {
    const k = Object.keys(window.__states).find((x) => /monitor_status/.test(x)) || 'sensor.bms_monitor_status';
    window.__states[k] = { state: 'ok', attributes: { alarms: [], watches: [], issues: [
      { id: 'a', level: 'warn', title: 'Brak cen <img src=x onerror=window.__xss=1>', detail: '0/24 godzin.', fix: 'Sprawdź integrację cen.', since: nowS - 600 },
      { id: 'data_repaired', level: 'info', title: 'Przy starcie naprawiono uszkodzone dane', detail: 'księga zysków', fix: '' }] }, last_updated: 'x' };
    window.__el.hass = window.__mk();
  }, nowS);
  await e.q(() => __el.shadowRoot.querySelector('[data-tab="diag"]').click());
  await e.page.waitForFunction(() => !!__el.shadowRoot.getElementById('dgBody'));
  await sleep(400);
  const t = await e.q(() => { const d = __el.shadowRoot.getElementById('dgIssues'); return d ? { txt: d.textContent, open: d.open, rows: d.querySelectorAll('b').length - 0 } : null; });
  ok(t && /Co dziś nie działa/.test(t.txt) && /Przy starcie naprawiono uszkodzone dane/.test(t.txt), 'Przegląd: lista z „Przy starcie naprawiono…”');
  ok(t && t.open && /od \d{1,2}:\d{2}/.test(t.txt) && /Sprawdź integrację cen\./.test(t.txt), 'ostrzeżenie: lista otwarta, „od kiedy” i wskazówka');
  ok(await e.q(() => window.__xss === undefined && !__el.shadowRoot.querySelector('#dgIssues img')), 'tytuł z HTML nie jest wykonywany');
  await e.q(() => { __el.hass = __mk(); }); await sleep(300);
  ok(await e.q(() => /⚠/.test(__el.shadowRoot.getElementById('tabDiag').textContent)), 'zakładka Ustawienia: ⚠ od ostrzeżenia');
  // sama informacja: lista zwinięta, bez ⚠
  await e.q(() => { const k = Object.keys(window.__states).find((x) => /monitor_status/.test(x)); window.__states[k].attributes.issues = [{ id: 'data_repaired', level: 'info', title: 'Przy starcie naprawiono uszkodzone dane', detail: 'x', fix: '' }]; __el.hass = __mk(); });
  await sleep(300);
  await e.q(() => __el.shadowRoot.querySelector('[data-act="sec"][data-sec="selftest"]').click()); await sleep(200);
  await e.q(() => __el.shadowRoot.querySelector('[data-act="sec"][data-sec="overview"]').click()); await sleep(300);
  ok(await e.q(() => { const d = __el.shadowRoot.getElementById('dgIssues'); return !!d && !d.open; }), 'tylko informacja: lista zwinięta');
  ok(await e.q(() => !/⚠/.test(__el.shadowRoot.getElementById('tabDiag').textContent)), 'tylko informacja: bez ⚠ na zakładce');
  await b.close(); console.log(fails ? 'FAILS ' + fails : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
