// Ustawienia: dolny pasek tylko Główny/Plan/Zysk/Ustawienia; EMS, Urządzenia i Serwis wewnątrz; Serwis tylko admin
const { openCard, chromium } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
(async () => {
  const b = await chromium.launch();
  for (const admin of [true, false]) {
    const e = await openCard(b, { admin, mobile: true });
    await sleep(600);
    const vis = await e.q(() => [...__el.shadowRoot.querySelectorAll('.tabs .tab')].filter((x) => getComputedStyle(x).display !== 'none').map((x) => x.dataset.tab));
    ok(JSON.stringify(vis) === JSON.stringify(['main', 'charts', 'log', 'settings']), `pasek (${admin ? 'admin' : 'zwykły'}): ${JSON.stringify(vis)}`);
    await e.q(() => __el.shadowRoot.querySelector('.tab[data-tab="settings"]').click()); await sleep(300);
    const hub = await e.q(() => [...__el.shadowRoot.querySelectorAll('#setHub .hub-item')].filter((x) => x.style.display !== 'none').map((x) => x.dataset.hub));
    ok(hub.includes('ems') && hub.includes('dev') && hub.includes('look'), 'lista: EMS, Urządzenia, Wygląd ' + hub);
    ok(hub.includes('diag') === admin, `Serwis ${admin ? 'widoczny' : 'ukryty'} (${hub})`);
    await e.q(() => __el.shadowRoot.querySelector('[data-hub="ems"]').click()); await sleep(300);
    ok(await e.q(() => __el.shadowRoot.querySelector('[data-tab-content="ems"]').style.display !== 'none' && __el.shadowRoot.querySelector('.tab[data-tab="settings"]').classList.contains('active')), 'podstrona EMS otwarta, Ustawienia podświetlone');
    await e.q(() => __el.shadowRoot.querySelector('[data-tab-content="ems"] [data-hub-back]').click()); await sleep(200);
    ok(await e.q(() => __el.shadowRoot.querySelector('[data-tab-content="settings"]').style.display !== 'none'), 'powrót do listy');
    ok(e.errs.length === 0, 'brak błędów JS ' + JSON.stringify(e.errs));
    await e.page.context().close();
  }
  console.log(fails ? `FAILS ${fails}` : 'ALL OK');
  await b.close(); process.exit(fails ? 1 : 0);
})();
