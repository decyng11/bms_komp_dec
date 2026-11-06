const { openCard, readFile, chromium, CARD } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const gate = (q) => q(() => !!__el.shadowRoot.querySelector('.dg-gate, #dgBody, .dg-bar'));
const diagBox = (q) => q(() => (__el.shadowRoot.getElementById('diagRoot') || {}).innerHTML || '');
(async () => {
  const b = await chromium.launch();
  // 1. admin: moduł dopiero po otwarciu zakładki, z parametrem wersji
  let e = await openCard(b, { ver: CARD + '.777' });
  let { page: p, q, reqs, errs } = e;
  ok(!reqs.some(r => r.includes('bms-diag.js')), 'rdzeń nie pobiera Diagnostyki przy starcie');
  ok(await q(() => getComputedStyle(__el.shadowRoot.getElementById('tabDiag')).display !== 'none'), 'zakładka Diagnostyka widoczna dla admina (zaślepka, bez modułu)');
  ok(typeof await q(() => window.__bmsDiagInstall) === 'undefined', 'moduł nie jest jeszcze załadowany');
  await q(() => __el.shadowRoot.querySelector('[data-tab="diag"]').click());
  await p.waitForFunction(() => !!__el.shadowRoot.querySelector('.dg-gate, #dgBody'), null, { timeout: 8000 }).catch(() => {});
  ok(await gate(q), 'po kliknięciu zakładki moduł się ładuje i pojawia się ekran Diagnostyki');
  ok(reqs.filter(r => r.includes('bms-diag.js')).length === 1 && reqs.some(r => r === '/bms_komp_dec/bms-diag.js?v=' + CARD + '.777'), 'moduł pobrany raz, z tym samym parametrem ?v= co rdzeń: ' + JSON.stringify(reqs.filter(r => r.includes('diag'))));
  await q(() => __el.shadowRoot.querySelector('[data-tab="main"]').click());
  await q(() => __el.shadowRoot.querySelector('[data-tab="diag"]').click());
  await p.waitForTimeout(300);
  ok(reqs.filter(r => r.includes('bms-diag.js')).length === 1, 'ponowne otwarcie zakładki nie pobiera modułu drugi raz');
  ok(errs.length === 0, 'brak błędów JS: ' + JSON.stringify(errs));
  await e.ctx.close();

  // 2. nie-admin: nigdy nie pobiera modułu, zakładka ukryta
  e = await openCard(b, { admin: false });
  ok(await e.q(() => getComputedStyle(__el.shadowRoot.getElementById('tabDiag')).display === 'none'), 'nie-admin: zakładka ukryta');
  await e.page.waitForTimeout(500);
  ok(!e.reqs.some(r => r.includes('bms-diag.js')), 'nie-admin: moduł Diagnostyki nie jest pobierany');
  await e.ctx.close();

  // 3. brak pliku (404) → komunikat + ponowienie po naprawie
  let broken = true;
  e = await openCard(b, { override: { 'bms-diag.js': (r) => broken ? r.fulfill({ status: 404, body: 'x' }) : r.fulfill({ contentType: 'application/javascript', body: readFile('bms-diag.js') }) } });
  await e.q(() => __el.shadowRoot.querySelector('[data-tab="diag"]').click());
  await e.page.waitForFunction(() => /Nie udało się wczytać modułu/.test((__el.shadowRoot.getElementById('diagRoot') || {}).innerHTML || ''), null, { timeout: 8000 }).catch(() => {});
  let html = await diagBox(e.q);
  ok(/Nie udało się wczytać modułu Diagnostyki/.test(html) && /bms-diag\.js/.test(html) && /data-mod-retry="diag"/.test(html), '404: czytelny komunikat z nazwą pliku i przyciskiem ponowienia');
  broken = false;
  await e.q(() => __el.shadowRoot.querySelector('[data-mod-retry="diag"]').click());
  await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('.dg-gate, #dgBody'), null, { timeout: 8000 }).catch(() => {});
  ok(await gate(e.q), '404: po naprawie „Spróbuj ponownie” ładuje Diagnostykę');
  await e.ctx.close();

  // 4. niezgodny kontrakt
  e = await openCard(b, { override: { 'bms-diag.js': (r) => r.fulfill({ contentType: 'application/javascript', body: readFile('bms-diag.js').replace('install.contract = 1;', 'install.contract = 99;') }) } });
  await e.q(() => __el.shadowRoot.querySelector('[data-tab="diag"]').click());
  await e.page.waitForFunction(() => /niezgodna/.test((__el.shadowRoot.getElementById('diagRoot') || {}).innerHTML || ''), null, { timeout: 8000 }).catch(() => {});
  html = await diagBox(e.q);
  ok(/niezgodna wersja modułu \(jest 99, wymagana 1\)/.test(html) && /Ctrl\+F5/.test(html), 'kontrakt 99: komunikat o niezgodnej wersji');
  ok(!(await e.q(() => !!__el.shadowRoot.querySelector('.dg-gate'))), 'kontrakt 99: moduł nie został zainstalowany');
  await e.ctx.close();

  // 5. moduł rzuca wyjątek przy instalacji
  e = await openCard(b, { override: { 'bms-diag.js': (r) => r.fulfill({ contentType: 'application/javascript', body: readFile('bms-diag.js').replace("const TC = shared.TC;", "const TC = shared.TC; throw new Error('boom');") }) } });
  await e.q(() => __el.shadowRoot.querySelector('[data-tab="diag"]').click());
  await e.page.waitForFunction(() => /błąd modułu/.test((__el.shadowRoot.getElementById('diagRoot') || {}).innerHTML || ''), null, { timeout: 8000 }).catch(() => {});
  ok(/błąd modułu: boom/.test(await diagBox(e.q)), 'wyjątek instalacji: komunikat z przyczyną, karta nadal działa');
  ok(await e.q(() => !!__el.shadowRoot.querySelector('[data-tab="main"]')), 'wyjątek instalacji: reszta karty działa');
  await e.ctx.close();

  // 6. moduł już na stronie (pakiet) → bez pobierania
  e = await openCard(b, { preload: ['bms-diag.js'] });
  await e.q(() => __el.shadowRoot.querySelector('[data-tab="diag"]').click());
  await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('.dg-gate, #dgBody'), null, { timeout: 8000 }).catch(() => {});
  ok(await gate(e.q) && !e.reqs.some(r => r.includes('bms-diag.js')), 'moduł dołączony wcześniej: instalacja bez pobierania');
  await e.ctx.close();

  // 7. mobilnie
  e = await openCard(b, { mobile: true });
  await e.q(() => __el.shadowRoot.querySelector('[data-tab="diag"]').click());
  await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('.dg-gate, #dgBody'), null, { timeout: 8000 }).catch(() => {});
  ok(await gate(e.q) && e.errs.length === 0, 'telefon: Diagnostyka ładuje się bez błędów: ' + JSON.stringify(e.errs));
  await e.ctx.close();
  // 8. sposoby ładowania rdzenia w HA: <script type=module> oraz dynamiczny import() — parametr ?v= musi być wykryty
  for (const mode of ['module', 'import']) {
    e = await openCard(b, { ver: CARD + '.555', loadAs: mode });
    await e.q(() => __el.shadowRoot.querySelector('[data-tab="diag"]').click());
    await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('.dg-gate, #dgBody'), null, { timeout: 8000 }).catch(() => {});
    ok(await gate(e.q) && e.reqs.includes('/bms_komp_dec/bms-diag.js?v=' + CARD + '.555'), 'ładowanie rdzenia jako ' + mode + ': moduł z ?v=: ' + JSON.stringify(e.reqs.filter(r => r.includes('diag'))));
    await e.ctx.close();
  }
  await b.close();
  console.log('FAILS', fails); process.exit(fails ? 1 : 0);
})();
