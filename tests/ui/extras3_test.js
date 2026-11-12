const { openCard, chromium, readFile, CARD } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const { seed, curve, REPORT, HEALTH, tab, sr, blue, openModes, openSec } = require('./extras_helpers');
const js = (body) => (r) => r.fulfill({ contentType: 'application/javascript', body });

(async () => {
  const b = await chromium.launch();
  const reqCount = (e) => e.reqs.filter((r) => /bms-extras\.js/.test(r)).length;

  // 1. plik niedostępny (404) → komunikat z przyciskiem; ponowienie po naprawie
  let mode = 'fail';
  let e = await openCard(b, { override: { 'bms-extras.js': (r) => mode === 'fail' ? r.fulfill({ status: 404, body: 'nie ma' }) : r.fulfill({ contentType: 'application/javascript', body: readFile('bms-extras.js') }) } });
  await seed(e, { curve: curve(), report: REPORT(), health: HEALTH });
  await tab(e, 'ems'); await sleep(700);
  const t1 = await sr(e, '#exPlanBox');
  ok(/Nie udało się wczytać modułu dodatków/.test(t1) && /nie udało się pobrać bms-extras\.js/.test(t1), 'awaria 404: czytelny komunikat w planie: ' + t1.slice(0, 120));
  ok(await e.q(() => !!__el.shadowRoot.querySelector('#exPlanBox [data-mod-retry="extras"]')), 'awaria 404: przycisk ponowienia w panelu planu');
  await openModes(e);
  ok(await e.q(() => __el.shadowRoot.querySelectorAll('#dgBody [data-act="mode-sw"]').length === 6), 'awaria 404 dodatków: Diagnostyka → Tryby działa (osobny moduł)');
  await tab(e, 'ems'); await sleep(300);
  await tab(e, 'log'); await sleep(600);
  ok(/Nie udało się wczytać modułu dodatków/.test(await sr(e, '#exReportBox')) && /Nie udało się wczytać modułu dodatków/.test(await sr(e, '#exHealthBox')), 'awaria 404: panele raportu i zdrowia pokazują błąd');
  ok(/Bilans w PLN/.test(await sr(e, '#logTabBody')) && /Dziennik decyzji/.test(await sr(e, '#logTabBody')), 'awaria 404: reszta zakładki „Zysk i log” działa');
  ok(reqCount(e) <= 2, 'awaria 404: brak pętli pobierania (żądań: ' + reqCount(e) + ')');
  await sleep(11000);
  ok(reqCount(e) <= 2, 'awaria 404: po 11 s nadal brak pętli (żądań: ' + reqCount(e) + ')');
  mode = 'ok';
  await tab(e, 'ems');
  await e.q(() => __el.shadowRoot.querySelector('#exPlanBox [data-mod-retry="extras"]').click());
  await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('#exPlanCv'), null, { timeout: 8000 });
  await openSec(e, 'wizard'); await sleep(600);
  ok(await e.q(() => !!__el.shadowRoot.querySelector('#exWizBox [data-ex="wiz-run"]')), 'ponowienie po naprawie: plan i kreator (Diagnostyka) działają');
  await tab(e, 'log'); await sleep(500);
  ok(/Bilans z siecią/.test(await sr(e, '#exReportBox')) && /Sprawność cyklu/.test(await sr(e, '#exHealthBox')), 'ponowienie po naprawie: raport i zdrowie działają');
  ok(e.errs.filter((x) => !/404|Failed to load resource/.test(x)).length === 0, '1: brak błędów JS ' + JSON.stringify(e.errs));
  await e.ctx.close();

  // 2. niezgodny kontrakt
  e = await openCard(b, { override: { 'bms-extras.js': js("window.__bmsExtrasInstall = function(){}; window.__bmsExtrasInstall.contract = 99; window.__bmsExtrasInstall.version = '" + CARD + "';") } });
  await seed(e, { curve: curve() }); await tab(e, 'ems'); await sleep(700);
  ok(/niezgodna wersja modułu \(jest 99, wymagana 1\)/.test(await sr(e, '#exPlanBox')), 'kontrakt: komunikat o niezgodnej wersji');
  await e.ctx.close();

  // 3. moduł rzuca wyjątek przy instalacji
  e = await openCard(b, { override: { 'bms-extras.js': js('window.__bmsExtrasInstall = function(){ throw new Error("boom"); }; window.__bmsExtrasInstall.contract = 1; window.__bmsExtrasInstall.version = "' + CARD + '";') } });
  await seed(e, { curve: curve() }); await tab(e, 'ems'); await sleep(700);
  ok(/błąd modułu: boom/.test(await sr(e, '#exPlanBox')), 'wyjątek: komunikat „błąd modułu: boom”');
  await e.ctx.close();

  // 4. moduł się ładuje, ale nic nie instaluje
  e = await openCard(b, { override: { 'bms-extras.js': js('window.__bmsExtrasInstall = function(){}; window.__bmsExtrasInstall.contract = 1; window.__bmsExtrasInstall.version = "' + CARD + '";') } });
  await seed(e, { curve: curve() }); await tab(e, 'ems'); await sleep(700);
  ok(/nie zainstalował dodatków/.test(await sr(e, '#exPlanBox')), 'pusty moduł: komunikat o braku instalacji');
  await e.ctx.close();

  // 5. moduł wstępnie załadowany (np. pakiet) → brak pobierania
  e = await openCard(b, { preload: ['bms-extras.js'] });
  await seed(e, { curve: curve() }); await tab(e, 'ems');
  await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('#exPlanCv'), null, { timeout: 8000 });
  ok(reqCount(e) === 0, 'pakiet: moduł wstępnie załadowany nie jest pobierany ponownie');
  // 6. motyw jasny
  const before = await e.q(() => { const c = __el.shadowRoot.querySelector('#exPlanCv'); const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let s = 0; for (let i = 0; i < d.length; i += 4) s += d[i]; return s; });
  await e.q(() => __el._setTheme(__el.getAttribute('data-theme') === 'light' ? 'dark' : 'light', false)); await sleep(300);
  await e.q(() => __el._exRender()); await sleep(200);
  const after = await e.q(() => { const c = __el.shadowRoot.querySelector('#exPlanCv'); const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let s = 0; for (let i = 0; i < d.length; i += 4) s += d[i]; return s; });
  ok(before !== after && (await blue(e)) > 400, 'zmiana motywu: wykres przerysowany (suma R ' + before + ' → ' + after + ')');
  // 7. zmiana szerokości okna → przerysowanie
  await e.page.setViewportSize({ width: 700, height: 900 }); await sleep(200);
  await e.q(() => { document.getElementById('h').style.width = '600px'; __el._exRender(); }); await sleep(200);
  ok(await e.q(() => { const c = __el.shadowRoot.querySelector('#exPlanCv'); return c.width >= 500 && c.width <= 700; }), 'zmiana szerokości: płótno dopasowane');
  ok(e.errs.length === 0, '5-7: brak błędów JS ' + JSON.stringify(e.errs));
  await e.ctx.close();

  // 8. HA przysyła aktualizacje co kilka sekund — wykres nie migocze (płótno nie jest tworzone od nowa)
  e = await openCard(b, {});
  await seed(e, { curve: curve() }); await tab(e, 'ems');
  await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('#exPlanCv'), null, { timeout: 8000 });
  await e.q(() => { window.__cv0 = __el.shadowRoot.querySelector('#exPlanCv'); });
  for (let i = 0; i < 5; i++) { await e.q(() => { window.__states['sensor.inverter_battery'].last_updated = new Date().toISOString(); __el.hass = __mk(); }); await sleep(150); }
  ok(await e.q(() => window.__cv0 === __el.shadowRoot.querySelector('#exPlanCv')), 'odświeżenia stanu HA nie odtwarzają wykresu (brak migotania)');
  await e.ctx.close();

  console.log('FAILS', fails); await b.close(); process.exit(fails ? 1 : 0);
})().catch((err) => { console.log('WYJĄTEK TESTU', err.message); process.exit(2); });
