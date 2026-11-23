// Ustawienia: wyszukiwarka opcji, porady z „Zastosuj/Cofnij”, zużycie baterii i oś decyzji planu
const { openCard, chromium } = require('./ui_env');
const { tab } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, { admin: true, mobile: true });
  await sleep(600);
  await e.q(() => __el.shadowRoot.querySelector('.tab[data-tab="settings"]').click()); await sleep(300);
  await e.q(() => { const i = __el.shadowRoot.getElementById('setSearch'); i.value = 'ładowanie'; i.dispatchEvent(new Event('input')); }); await sleep(200);
  const r = await e.q(() => { const R = __el.shadowRoot; return { n: R.querySelectorAll('#setFound [data-found]').length, hubHidden: R.getElementById('setHub').hidden, txt: R.getElementById('setFound').textContent }; });
  ok(r.n > 0 && r.hubHidden, `wyszukiwanie „ładowanie”: ${r.n} wyników, lista ukryta`);
  await e.q(() => __el.shadowRoot.querySelector('#setFound [data-found]').click()); await sleep(500);
  ok(await e.q(() => __el.shadowRoot.querySelector('[data-tab-content="ems"]').style.display !== 'none'), 'kliknięcie wyniku otwiera podstronę EMS');
  await e.q(() => __el.shadowRoot.querySelector('.tab[data-tab="settings"]').click()); await sleep(200);
  await e.q(() => { const i = __el.shadowRoot.getElementById('setSearch'); i.value = 'zzzzqq'; i.dispatchEvent(new Event('input')); });
  ok(await e.q(() => /Nic nie znaleziono/.test(__el.shadowRoot.getElementById('setFound').textContent)), 'brak wyników: komunikat');
  await e.q(() => { const i = __el.shadowRoot.getElementById('setSearch'); i.value = ''; i.dispatchEvent(new Event('input')); });
  ok(await e.q(() => !__el.shadowRoot.getElementById('setHub').hidden), 'puste pole: lista wraca');
  ok(e.errs.length === 0, 'brak błędów JS ' + JSON.stringify(e.errs));
  await e.page.context().close();
  console.log(fails ? `FAILS ${fails}` : 'ALL OK');
  await b.close(); process.exit(fails ? 1 : 0);
})();
