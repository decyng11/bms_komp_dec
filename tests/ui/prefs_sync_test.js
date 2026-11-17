// Wygląd per użytkownik Home Assistant: styl, motyw i układ panelu zapisują się na koncie (dane użytkownika HA:
// frontend/get_user_data i frontend/set_user_data), podążają za kontem na inne urządzenie i nie przeciekają do innego użytkownika
// tej samej przeglądarki. Przy awarii zapisu na konto wygląd dalej działa lokalnie, bez błędów w konsoli.
const { openCard, chromium } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const KEY = 'bms_komp_dec_prefs';
// zamontuj nową kartę dla użytkownika (stara znika) — tak jak po odświeżeniu strony / wejściu na dashboard
const mount = (e, uid, tag) => e.q((a) => { const old = window.__el; if (old) old.remove(); window.__uid = a[0]; const el = document.createElement(a[1] || 'bms-panel-card'); el.setConfig({ type: 'custom:' + (a[1] || 'bms-panel-card') }); document.getElementById('h').appendChild(el); el.hass = __mk(); window.__el = el; }, [uid, tag]);
const sets = (e) => e.q(() => (window.__udSets || []).map(s => ({ uid: s.uid, v: s.value })));
const server = (e, uid) => e.q((a) => { const v = (window.__ud || {})[a[0] + '|' + a[1]]; return v === undefined ? null : v; }, [uid, KEY]);
const gets = (e) => e.q(() => window.__ws.filter(t => t === 'frontend/get_user_data').length);
const skin = (e) => e.q(() => __el.getAttribute('data-skin'));
const theme = (e) => e.q(() => __el.getAttribute('data-theme'));
const ids = (e, tab) => e.q((tab) => { const tc = __el.shadowRoot.querySelector(`[data-tab-content="${tab}"]`); return [...tc.children].filter(n => n.dataset && n.dataset.tile).map(n => n.dataset.tile); }, tab);
const ls = (e, k) => e.q((k) => { try { return localStorage.getItem(k); } catch (x) { return 'ERR'; } }, k);

(async () => {
  const b = await chromium.launch();
  const A = await openCard(b, { admin: false });

  // ---- pierwszy kontakt: dotychczasowe ustawienia z przeglądarki trafiają na konto użytkownika
  await A.q(() => { localStorage.setItem('bms_panel_skin', 'glass'); localStorage.setItem('bms_panel_theme', 'light'); localStorage.removeItem('bms_panel_layout'); localStorage.removeItem('bms_panel_prefs_meta'); });
  await mount(A, 'u1'); await sleep(500);
  let s1 = await sets(A);
  ok(s1.length === 1 && s1[0].uid === 'u1' && s1[0].v.skin === 'glass' && s1[0].v.theme === 'light' && s1[0].v.v === 1 && s1[0].v.t > 0, 'pierwszy kontakt: istniejące ustawienia wysłane na konto u1: ' + JSON.stringify(s1).slice(0, 140));
  ok(await skin(A) === 'glass' && await theme(A) === 'light', 'po wysłaniu wygląd bez zmian');
  ok(JSON.parse(await ls(A, 'bms_panel_prefs_meta')).u === 'u1', 'przeglądarka zapamiętała, czyje ustawienia trzyma');

  // ---- zmiany: seria kliknięć = jeden zapis (opóźnienie), potem motyw i układ
  await A.q(() => { __el._setSkin('matrix'); __el._setSkin('space'); __el._setSkin('comfort'); });
  await sleep(300);
  ok((await sets(A)).length === 1, 'seria zmian stylu: jeszcze nie wysłana (zapis z opóźnieniem)');
  await sleep(1500);
  s1 = await sets(A);
  ok(s1.length === 2 && s1[1].v.skin === 'comfort', 'seria zmian stylu: jeden zapis z ostatnim stylem (comfort): ' + s1.length);
  await A.q(() => __el._setTheme('dark', true)); await sleep(1700);
  s1 = await sets(A);
  ok(s1.length === 3 && s1[2].v.theme === 'dark' && s1[2].v.skin === 'comfort', 'motyw: zapisany na koncie razem z pozostałymi ustawieniami');
  await A.q(() => { __el._layoutMoveTo('ch-prices', 'main'); __el._layoutToggle('main-plan'); }); await sleep(1700);
  s1 = await sets(A);
  const lay = s1[s1.length - 1].v.layout;
  ok(lay && lay.v === 2 && lay.order.main.slice(-1)[0] === 'ch-prices' && lay.hidden.join() === 'main-plan', 'układ (przeniesienie + ukrycie): zapisany na koncie: ' + JSON.stringify(lay).slice(0, 150));
  const srvA = await server(A, 'u1');
  ok(srvA && srvA.skin === 'comfort' && srvA.theme === 'dark' && srvA.layout.v === 2, 'serwer trzyma komplet ustawień użytkownika u1');
  ok(await server(A, 'u2') === null, 'inny użytkownik nic nie dostał');

  // ---- nowe urządzenie tego samego użytkownika: pusty localStorage, ustawienia przychodzą z konta
  const B = await openCard(b, { admin: false });
  await B.q((ud) => { window.__ud = ud; try { localStorage.clear(); } catch (x) {} }, await A.q(() => window.__ud));
  await mount(B, 'u1'); await sleep(900);
  ok(await skin(B) === 'comfort' && await theme(B) === 'dark', 'nowe urządzenie: styl i motyw z konta (comfort, dark)');
  ok((await ids(B, 'main')).slice(-1)[0] === 'ch-prices' && await B.q(() => __el.shadowRoot.querySelector('[data-tile="main-plan"]').hasAttribute('data-tile-off')), 'nowe urządzenie: układ z konta (kafelek przeniesiony i ukryty)');
  ok(await ls(B, 'bms_panel_skin') === 'comfort' && await ls(B, 'bms_panel_theme') === 'dark' && !!await ls(B, 'bms_panel_layout'), 'nowe urządzenie: ustawienia zapisane też lokalnie (szybki start następnym razem)');
  ok((await sets(B)).length === 0, 'nowe urządzenie: nic nie wysyła z powrotem (nic się nie zmieniło)');
  ok(/na Twoim koncie Home Assistant/.test(await B.q(() => __el._prefsNote())), 'okno 🎨 mówi, że wygląd jest na koncie');
  await B.q(() => __el.shadowRoot.getElementById('lookBtn').click());
  ok(await B.q(() => /na Twoim koncie Home Assistant/.test(__el.shadowRoot.getElementById('lookOv').textContent) && !/w tej przeglądarce — każdy/.test(__el.shadowRoot.getElementById('lookOv').textContent)), 'okno 🎨: tekst o koncie');
  await B.q(() => __el._lookClose());

  // ---- inny użytkownik w tej samej przeglądarce nie dziedziczy wyglądu poprzedniego
  await mount(B, 'u2'); await sleep(800);
  ok(await skin(B) === null && await ls(B, 'bms_panel_skin') === null && await ls(B, 'bms_panel_layout') === null, 'u2 w tej samej przeglądarce: styl klasyczny, lokalny cache wyczyszczony');
  ok((await ids(B, 'main')).join() === 'main-active,main-flow,main-plan' && await B.q(() => !__el.shadowRoot.querySelector('[data-tile-off]')), 'u2: domyślny układ, bez ukrytych kafelków');
  ok((await sets(B)).length === 0, 'u2: nic nie wysłano na konto (nie ma czego)');
  await B.q(() => __el._setSkin('m3')); await sleep(1700);
  const srvU2 = await server(B, 'u2');
  ok(srvU2 && srvU2.skin === 'm3' && (await server(B, 'u1')).skin === 'comfort', 'u2 zapisał własny styl, dane u1 nietknięte');
  await mount(B, 'u1'); await sleep(900);
  ok(await skin(B) === 'comfort' && await theme(B) === 'dark' && (await ids(B, 'main')).slice(-1)[0] === 'ch-prices', 'powrót u1: jego wygląd przywrócony z konta');

  // ---- który zapis nowszy, ten wygrywa: lokalny nowszy od serwera idzie na serwer
  const C = await openCard(b, { admin: false });
  await C.q((ud) => { window.__ud = ud; localStorage.clear(); localStorage.setItem('bms_panel_skin', 'space'); localStorage.setItem('bms_panel_prefs_meta', JSON.stringify({ u: 'u1', t: Date.now() + 60000 })); }, await A.q(() => window.__ud));
  await mount(C, 'u1'); await sleep(700);
  const sC = await sets(C);
  ok(await skin(C) === 'space' && sC.length === 1 && sC[0].v.skin === 'space', 'nowszy zapis lokalny wygrywa z serwerem i jest wysłany');
  // serwer nowszy od lokalnego: wygrywa serwer
  await C.q(() => { window.__udSets = []; localStorage.setItem('bms_panel_prefs_meta', JSON.stringify({ u: 'u1', t: 1000 })); localStorage.setItem('bms_panel_skin', 'matrix'); });
  await mount(C, 'u1'); await C.q(() => __el._prefsPull(true)); await sleep(700);
  ok(await skin(C) === 'space' && (await sets(C)).length === 0, 'starszy zapis lokalny przegrywa z serwerem (styl z konta: space), bez wysyłania');

  // ---- ponowne pobranie po powrocie do karty (inne urządzenie zmieniło wygląd), z ochroną przed zalewem zapytań
  await C.q((ud) => { window.__ud['u1|bms_komp_dec_prefs'] = Object.assign({}, window.__ud['u1|bms_komp_dec_prefs'], { skin: 'glass', theme: 'light', t: Date.now() + 120000 }); }, null);
  const g0 = await gets(C);
  await C.q(() => { Object.defineProperty(document, 'hidden', { configurable: true, get: () => false }); document.dispatchEvent(new Event('visibilitychange')); });
  await sleep(300);
  ok(await gets(C) === g0 && await skin(C) === 'space', 'powrót do karty zaraz po pobraniu: bez nowego zapytania (ochrona przed zalewem)');
  await C.q(() => __el._prefsPull(true)); await sleep(500);
  ok(await skin(C) === 'glass' && await theme(C) === 'light', 'wymuszone pobranie: nowy wygląd z konta zastosowany bez odświeżania strony');

  // ---- mała karta bierze styl i motyw z konta
  const M = await openCard(b, { admin: false });
  await M.q((ud) => { window.__ud = ud; localStorage.clear(); }, await A.q(() => window.__ud));
  await M.q(() => { document.getElementById('h').innerHTML = ''; window.__uid = 'u1'; const el = document.createElement('bms-mini-card'); el.setConfig({ type: 'custom:bms-mini-card' }); document.getElementById('h').appendChild(el); el.hass = __mk(); window.__el = el; });
  await sleep(900);
  ok(await skin(M) === 'comfort' && await theme(M) === 'dark', 'mała karta: styl i motyw z konta');
  ok(await M.q(() => !!__el.shadowRoot.getElementById('miniBox') && __el.shadowRoot.querySelectorAll('[data-tile]').length === 0), 'mała karta: bez układu panelu (brak kafelków)');

  // ---- awaria zapisu na konto: wygląd działa lokalnie, brak błędów, informacja o zapisie tylko w przeglądarce
  const F = await openCard(b, { admin: false });
  await F.q(() => { window.__udFail = true; localStorage.clear(); });
  await mount(F, 'u9'); await sleep(500);
  await F.q(() => { __el._setSkin('matrix'); __el._setTheme('light', true); __el._layoutMoveTo('ch-prices', 'main'); }); await sleep(1700);
  ok(await skin(F) === 'matrix' && await theme(F) === 'light' && (await ids(F, 'main')).slice(-1)[0] === 'ch-prices', 'awaria konta: styl, motyw i układ nadal działają lokalnie');
  ok(await ls(F, 'bms_panel_skin') === 'matrix' && !!await ls(F, 'bms_panel_layout'), 'awaria konta: ustawienia zapisane lokalnie');
  ok(/w tej przeglądarce/.test(await F.q(() => __el._prefsNote())) && !/na Twoim koncie/.test(await F.q(() => __el._prefsNote())), 'awaria konta: komunikat uczciwie mówi, że zapis jest tylko lokalny');
  ok(F.errs.length === 0, 'awaria konta: brak błędów w konsoli: ' + JSON.stringify(F.errs));
  // powrót serwera: kolejna zmiana trafia na konto, a komunikat wraca
  await F.q(() => { window.__udFail = false; __el._setSkin('space'); }); await sleep(1800);
  ok((await sets(F)).length >= 1 && (await server(F, 'u9')).skin === 'space' && /na Twoim koncie/.test(await F.q(() => __el._prefsNote())), 'po powrocie serwera: zmiana trafia na konto, komunikat wraca');

  // starszy HA bez komend danych użytkownika: cicho wyłącza synchronizację
  const O = await openCard(b, { admin: false });
  await O.q(() => { window.__udFail = { code: 'unknown_command', message: 'Unknown command.' }; localStorage.clear(); });
  await mount(O, 'u7'); await sleep(500);
  await O.q(() => { __el._setSkin('glass'); }); await sleep(1700);
  ok(await skin(O) === 'glass' && O.errs.length === 0, 'starszy HA (unknown_command): wygląd działa lokalnie, brak błędów');
  const g1 = await gets(O);
  await O.q(() => { __el._setSkin('space'); }); await sleep(1700);
  ok((await sets(O)).length === 0 && await gets(O) === g1, 'starszy HA: synchronizacja wyłączona — nie ponawia zapytań');

  // ---- brak id użytkownika (np. podgląd w edytorze): tylko lokalnie, bez zapytań
  const N = await openCard(b, { admin: false });
  await N.q(() => { localStorage.clear(); });
  await N.q(() => { __el._setSkin('glass'); }); await sleep(1700);
  ok(await skin(N) === 'glass' && await N.q(() => !window.__ws.some(t => /user_data/.test(t))), 'bez user.id: tylko zapis lokalny, żadnych zapytań o dane użytkownika');

  ok(A.errs.length === 0 && B.errs.length === 0 && C.errs.length === 0 && M.errs.length === 0, 'brak błędów w konsoli: ' + JSON.stringify([...A.errs, ...B.errs, ...C.errs, ...M.errs]));
  await b.close();
  console.log(fails ? `\n${fails} niepowodzeń` : '\nOK'); process.exit(fails ? 1 : 0);
})();
