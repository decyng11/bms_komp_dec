// Napis „Ładowanie modułu…” nie może zostać sam, a stara kopia modułu z pamięci podręcznej musi zostać wykryta i wyleczona.
const { openCard, readFile, chromium, CARD } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const FRESH = readFile('bms-diag.js');
const NOVER = FRESH.replace("install.version = '" + CARD + "';", '');                   // moduł sprzed 0.6.5 (bez numeru wersji)
const STALE = NOVER.replace("root.textContent = '';", '');                                 // jak 0.6.0/0.6.1: nie zdejmuje napisu
const js = (r, body) => r.fulfill({ contentType: 'application/javascript', body });
const root = (e) => e.q(() => (__el.shadowRoot.getElementById('diagRoot') || {}).innerText || '');
const click = (e) => e.q(() => __el.shadowRoot.querySelector('[data-tab="diag"]').click());
const hasGate = (e) => e.q(() => !!__el.shadowRoot.querySelector('.dg-gate, #dgBody'));
const NOBUF = '<script>performance.setResourceTimingBufferSize(0)</script>';          // rdzeń nie ustali własnego adresu
const onlyPlaceholder = (t) => /^\s*Ładowanie modułu Diagnostyki…\s*$/.test(t);

(async () => {
  const b = await chromium.launch();
  let e, t;

  // 1. cache podaje starą kopię pod adresem bez nc= → wykrycie niezgodności + automatyczne pobranie z unikalnym adresem
  e = await openCard(b, { loadAs: 'import', head: NOBUF, override: { 'bms-diag.js': (r) => js(r, /[?&]nc=/.test(r.request().url()) ? FRESH : STALE) } });
  ok(await e.q(() => !performance.getEntriesByType('resource').some(x => /bms-panel\.js/.test(x.name))), 'warunek: rdzeń nie widzi własnego adresu (pełny bufor zasobów)');
  await click(e);
  await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('.dg-gate, #dgBody'), null, { timeout: 8000 }).catch(() => {});
  const dreq = e.reqs.filter(r => /bms-diag/.test(r));
  ok(dreq[0] === '/bms_komp_dec/bms-diag.js?v=' + CARD, 'adres modułu ZAWSZE niesie wersję, nawet gdy rdzeń nie zna własnego adresu: ' + JSON.stringify(dreq));
  ok(dreq.length === 2 && /[?&]nc=\d+/.test(dreq[1]), 'niezgodna wersja → jedno ponowne pobranie z unikalnym adresem: ' + JSON.stringify(dreq));
  ok(await hasGate(e), 'stara kopia wyleczona: Diagnostyka się wyświetla');
  t = await root(e);
  ok(!/Ładowanie modułu/.test(t), 'po wyleczeniu nie zostaje napis „Ładowanie modułu…”');
  ok(new RegExp('Karta ' + CARD.replace(/\./g, '\\.')).test(t), 'ekran Diagnostyki pokazuje wersję karty: ' + JSON.stringify(t.slice(-120)));
  await e.ctx.close();

  // 2. stara kopia pod KAŻDYM adresem → czytelny błąd z wersjami zamiast samego napisu; po naprawie „Spróbuj ponownie”
  let stale = true;
  e = await openCard(b, { loadAs: 'import', head: NOBUF, override: { 'bms-diag.js': (r) => js(r, stale ? STALE : FRESH) } });
  await click(e);
  await e.page.waitForFunction(() => /Nie udało się wczytać modułu/.test((__el.shadowRoot.getElementById('diagRoot') || {}).innerHTML || ''), null, { timeout: 8000 }).catch(() => {});
  t = await root(e);
  ok(/Nie udało się wczytać modułu Diagnostyki/.test(t) && /starą kopię/.test(t) && /Ctrl\+F5/.test(t), 'stara kopia wszędzie: komunikat o starej kopii i Ctrl+F5');
  ok(t.indexOf(CARD) >= 0 && /moduł —/.test(t), 'komunikat zawiera wersje: karta ' + CARD + ', moduł nieznany: ' + JSON.stringify(t.slice(-80)));
  ok(!onlyPlaceholder(t) && !/Ładowanie modułu/.test(t), 'nie zostaje napis „Ładowanie modułu…”');
  stale = false;
  await e.q(() => __el.shadowRoot.querySelector('[data-mod-retry="diag"]').click());
  await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('.dg-gate, #dgBody'), null, { timeout: 8000 }).catch(() => {});
  ok(await hasGate(e), 'po wgraniu poprawnego pliku „Spróbuj ponownie” ładuje Diagnostykę');
  await e.ctx.close();

  // 3. wyjątek w _dgOpen modułu (wersja zgodna) → komunikat z przyczyną, nie sam napis
  e = await openCard(b, { override: { 'bms-diag.js': (r) => js(r, FRESH.replace("_dgOpen() {\n      const s = this._dgS();", "_dgOpen() {\n      throw new Error('boom-open');\n      const s = this._dgS();")) } });
  await click(e);
  await e.page.waitForFunction(() => /boom-open/.test((__el.shadowRoot.getElementById('diagRoot') || {}).innerHTML || ''), null, { timeout: 8000 }).catch(() => {});
  t = await root(e);
  ok(/błąd przy otwieraniu Diagnostyki: boom-open/.test(t) && !/Ładowanie modułu/.test(t), 'wyjątek w _dgOpen: widoczny komunikat z przyczyną: ' + JSON.stringify(t.slice(0, 120)));
  await e.ctx.close();

  // 4. moduł nic nie rysuje → komunikat
  e = await openCard(b, { override: { 'bms-diag.js': (r) => js(r, FRESH.replace("_dgOpen() {\n      const s = this._dgS();", "_dgOpen() { return;\n      const s = this._dgS();")) } });
  await click(e);
  await e.page.waitForFunction(() => /nie wyświetlił/.test((__el.shadowRoot.getElementById('diagRoot') || {}).innerHTML || ''), null, { timeout: 8000 }).catch(() => {});
  t = await root(e);
  ok(/moduł nie wyświetlił Diagnostyki/.test(t) && !/Ładowanie modułu/.test(t), 'moduł bez widoku: komunikat zamiast samego napisu');
  await e.ctx.close();

  // 5. pobieranie wisi → po limicie czasu komunikat i przycisk
  e = await openCard(b, { override: { 'bms-diag.js': () => { /* nigdy nie odpowiada */ } } });
  await click(e);
  await e.page.waitForTimeout(1500);
  ok(onlyPlaceholder(await root(e)), 'w trakcie pobierania widać napis „Ładowanie…”');
  await e.page.waitForFunction(() => /trwa zbyt długo/.test((__el.shadowRoot.getElementById('diagRoot') || {}).innerHTML || ''), null, { timeout: 30000 }).catch(() => {});
  t = await root(e);
  ok(/pobieranie bms-diag\.js trwa zbyt długo/.test(t), 'zawieszone pobieranie: po 20 s komunikat z nazwą pliku: ' + JSON.stringify(t.slice(0, 140)));
  ok(await e.q(() => !!__el.shadowRoot.querySelector('[data-mod-retry="diag"]')), 'zawieszone pobieranie: jest przycisk ponowienia');
  await e.ctx.close();

  // 6. uruchomiona integracja ma inną wersję niż pliki karty → ostrzeżenie w Diagnostyce; zgodna → bez ostrzeżenia
  for (const [ver, warn] of [['0.0.1.5', true], [CARD + '.99', false]]) {
    e = await openCard(b, { ver });
    await click(e);
    await e.page.waitForFunction(() => !!__el.shadowRoot.getElementById('dgVer'), null, { timeout: 8000 }).catch(() => {});
    t = await root(e);
    ok(/zrestartuj Home Assistanta/.test(t) === warn, `integracja ${ver} vs karta ${CARD}: ostrzeżenie ${warn ? 'jest' : 'nie występuje'}`);
    if (warn) ok(e.reqs.some(r => r === '/bms_komp_dec/bms-diag.js?v=' + CARD), 'niezgodny adres rdzenia: moduł pobrany z wersją karty, nie z cudzym ?v=');
    await e.ctx.close();
  }

  // 7. moduł dodatków (EMS: plan 24 h) — stara kopia wszędzie → błąd z wersjami, nie pusty box
  e = await openCard(b, { override: { 'bms-extras.js': (r) => js(r, readFile('bms-extras.js').replace("install.version = '" + CARD + "';", '')) } });
  await e.q(() => __el.shadowRoot.querySelector('[data-tab="ems"]').click());
  await e.page.waitForFunction(() => /Nie udało się wczytać modułu/.test((__el.shadowRoot.getElementById('exPlanBox') || {}).innerHTML || ''), null, { timeout: 8000 }).catch(() => {});
  t = await e.q(() => (__el.shadowRoot.getElementById('exPlanBox') || {}).innerText || '');
  ok(/Nie udało się wczytać modułu dodatków/.test(t) && /starą kopię/.test(t), 'dodatki: stara kopia → czytelny komunikat w boxie planu');
  ok(e.reqs.filter(r => /bms-extras/.test(r)).length === 2, 'dodatki: jedna ponowna próba z unikalnym adresem: ' + JSON.stringify(e.reqs.filter(r => /bms-extras/.test(r))));
  await e.ctx.close();

  ok(true, '— koniec —');
  console.log(fails ? 'FAILS ' + fails : 'ALL OK');
  await b.close();
})().catch((x) => { console.log('ERR', x); process.exit(1); });
