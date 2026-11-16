// Okno „Wygląd” (🎨) dla każdego użytkownika + tryb edycji układu na panelu (↑ ↓, ukryj/pokaż, przeciąganie)
const { openCard, chromium } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, { admin: false });          // zwykły użytkownik, nie administrator
  const sr = (f, a) => e.q(f, a);
  const ids = (tab) => sr((tab) => { const s = __el.shadowRoot; const tc = s.querySelector(`[data-tab-content="${tab}"]`); const c = tab === 'log' ? tc.querySelector('#logTabBody') : tc; return [...c.children].filter(n => n.dataset && n.dataset.tile).map(n => n.dataset.tile); }, tab);
  const off = () => sr(() => [...__el.shadowRoot.querySelectorAll('[data-tile-off]')].map(n => n.dataset.tile));
  const ctlN = () => sr(() => __el.shadowRoot.querySelectorAll('.tile-ctl').length);
  await sr(() => { try { localStorage.removeItem('bms_panel_layout'); localStorage.removeItem('bms_panel_skin'); } catch (x) {} });

  // ---- okno Wygląd: dostępne bez uprawnień administratora i bez modułu Ustawień
  ok(await sr(() => !!__el.shadowRoot.getElementById('lookBtn')), 'przycisk 🎨 jest w nagłówku');
  ok(await sr(() => getComputedStyle(__el.shadowRoot.getElementById('tabDiag')).display === 'none'), 'to nie administrator: zakładka Ustawienia ukryta');
  await sr(() => __el.shadowRoot.getElementById('lookBtn').click());
  ok(await sr(() => !__el.shadowRoot.getElementById('lookOv').hidden && __el.shadowRoot.getElementById('lookBtn').getAttribute('aria-expanded') === 'true'), 'klik 🎨 otwiera okno');
  ok(await sr(() => __el.shadowRoot.querySelectorAll('#lookOv [data-look="skin"]').length === 6), 'okno: sześć stylów do wyboru');
  ok(await sr(() => __el.shadowRoot.querySelector('#lookOv [data-look="skin"][data-skin="classic"]').getAttribute('aria-pressed') === 'true'), 'okno: aktywny styl klasyczny');
  ok(await sr(() => __el.shadowRoot.querySelector('#lookOv [data-look="reset-all"]').disabled), 'okno: „Przywróć domyślny” nieaktywne przy układzie domyślnym');
  ok(await sr(() => __el.shadowRoot.activeElement && __el.shadowRoot.activeElement.dataset.look === 'close'), 'okno: fokus na przycisku zamknięcia');
  await sr(() => __el.shadowRoot.querySelector('#lookOv [data-look="skin"][data-skin="glass"]').click());
  ok(await sr(() => __el.getAttribute('data-skin') === 'glass' && localStorage.getItem('bms_panel_skin') === 'glass'), 'wybór stylu z okna: zastosowany i zapamiętany');
  ok(await sr(() => __el.shadowRoot.querySelector('#lookOv [data-look="skin"][data-skin="glass"]').getAttribute('aria-pressed') === 'true' && !__el.shadowRoot.getElementById('lookOv').hidden), 'okno zostaje otwarte, zaznaczenie przeniesione');
  await sr(() => __el.shadowRoot.querySelector('#lookOv [data-look="theme"][data-m="light"]').click());
  ok(await sr(() => __el.getAttribute('data-theme') === 'light'), 'wybór motywu z okna');
  await sr(() => __el.shadowRoot.querySelector('#lookOv [data-look="skin"][data-skin="classic"]').click());
  await sr(() => __el.shadowRoot.getElementById('lookOv').dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
  ok(await sr(() => __el.shadowRoot.getElementById('lookOv').hidden), 'Esc zamyka okno');
  ok(!e.reqs.some(r => r.includes('bms-diag.js')), 'okno Wygląd nie pobiera modułu Ustawień');

  // ---- tryb edycji
  await sr(() => __el.shadowRoot.getElementById('lookBtn').click());
  await sr(() => __el.shadowRoot.querySelector('#lookOv [data-look="edit"]').click());
  ok(await sr(() => __el.shadowRoot.getElementById('lookOv').hidden && __el.shadowRoot.querySelector('.app').hasAttribute('data-edit') && !__el.shadowRoot.getElementById('editBar').hidden), 'edycja: okno zamknięte, pasek edycji widoczny');
  ok(await ctlN() === 3 + 11 + 6 + 1, 'edycja: sterowanie na kafelkach (3 + 11 + 6 + pogoda) = ' + await ctlN());
  ok(await sr(() => getComputedStyle(__el.shadowRoot.querySelector('[data-tile="main-plan"] .section-title')).pointerEvents === 'none'), 'edycja: zawartość kafelków nieklikalna (nic nie przełączysz przez pomyłkę)');
  ok(await sr(() => __el.shadowRoot.querySelector('[data-tile="main-active"] [data-lay="up"]').disabled && !__el.shadowRoot.querySelector('[data-tile="main-active"] [data-lay="down"]').disabled), 'edycja: pierwszy kafelek bez ↑');
  // ↓ na pierwszym
  await sr(() => __el.shadowRoot.querySelector('[data-tile="main-active"] [data-lay="down"]').click());
  ok(JSON.stringify(await ids('main')) === JSON.stringify(['main-flow', 'main-active', 'main-plan']), 'klik ↓: kolejność w DOM ' + JSON.stringify(await ids('main')));
  ok(await sr(() => JSON.parse(localStorage.getItem('bms_panel_layout')).order.main.join() === 'main-flow,main-active,main-plan'), 'kolejność zapisana');
  ok(await sr(() => __el.shadowRoot.activeElement && __el.shadowRoot.activeElement.dataset.lay === 'down' && __el.shadowRoot.activeElement.closest('[data-tile]').dataset.tile === 'main-active'), 'fokus wrócił na ↓ przesuniętego kafelka (klawiatura)');
  // ukryj → szary pasek z „Pokaż”
  await sr(() => __el.shadowRoot.querySelector('[data-tile="main-plan"] [data-lay="eye"]').click());
  ok((await off()).join() === 'main-plan' && await sr(() => { const t = __el.shadowRoot.querySelector('[data-tile="main-plan"]'); return getComputedStyle(t).display !== 'none' && /Pokaż/.test(t.querySelector('.tile-ctl').textContent) && getComputedStyle(t.querySelector('.section-title')).display === 'none'; }), 'ukryty kafelek zostaje jako pasek z „Pokaż”, treść schowana');
  await sr(() => __el.shadowRoot.querySelector('[data-tile="main-plan"] [data-lay="eye"]').click());
  ok((await off()).length === 0, '„Pokaż” przywraca kafelek');
  // przeciąganie na zakładce Plan
  await sr(() => __el.shadowRoot.querySelector('.tab[data-tab="charts"]').click());
  await sleep(600);
  ok(await sr(() => /Zakładka: <b>Plan<\/b>|Zakładka: Plan/.test(__el.shadowRoot.getElementById('editBar').innerHTML.replace(/<[^>]+>/g, m => m)) || /Plan/.test(__el.shadowRoot.getElementById('editBar').textContent)), 'pasek edycji pokazuje bieżącą zakładkę');
  // przewiń jawnie (bez scrollIntoView/scroll-margin, które w różnych wersjach Chromium działają różnie): kafelek 140 px od góry, pod paskiem edycji
  await sr(() => { const t = __el.shadowRoot.querySelector('[data-tile="ch-plan24"]'); window.scrollBy(0, t.getBoundingClientRect().top - 140); });
  const snap = () => sr(() => { const t = __el.shadowRoot.querySelector('[data-tile="ch-plan24"]').getBoundingClientRect(); return Math.round(t.top) + ':' + Math.round(window.scrollY); });
  let prevSnap = '', stable = 0; for (let i = 0; i < 40 && stable < 3; i++) { await sleep(100); const cur = await snap(); stable = cur === prevSnap ? stable + 1 : 0; prevSnap = cur; }
  ok(stable >= 3, 'układ strony ustabilizowany przed przeciąganiem: ' + prevSnap);
  const geo = await sr(() => { const g = (id) => { const r = __el.shadowRoot.querySelector(`[data-tile="${id}"]`).getBoundingClientRect(); return { top: r.top, bottom: r.bottom, h: r.height }; };
    const h = __el.shadowRoot.querySelector('[data-tile="ch-plan24"] .tc-h').getBoundingClientRect(); return { handle: [h.left + h.width / 2, h.top + h.height / 2], t3: g('ch-override'), t4: g('ch-history7') }; });
  ok(geo.t4.bottom < 880, 'kafelki w edycji są niskie (przycięte), cztery mieszczą się na ekranie: ' + JSON.stringify(geo.t4));
  ok(await sr((p) => { const n = __el.shadowRoot.elementFromPoint(p[0], p[1]); return !!(n && n.closest && n.closest('.tc-h')); }, geo.handle), 'uchwyt ⠿ jest na wierzchu (nie zasłania go pasek edycji): ' + JSON.stringify(geo.handle));
  await e.page.mouse.move(geo.handle[0], geo.handle[1]); await e.page.mouse.down();
  const ty = geo.t3.top + geo.t3.h * 0.75;
  for (let i = 1; i <= 12; i++) { await e.page.mouse.move(geo.handle[0], geo.handle[1] + (ty - geo.handle[1]) * i / 12); await sleep(30); }
  await e.page.mouse.up(); await sleep(200);
  const ch = await ids('charts');
  ok(ch.indexOf('ch-plan24') === 2 && ch.slice(0, 2).join() === 'ch-hourly,ch-override', 'przeciągnięcie ⠿ przestawia kafelek: ' + ch.slice(0, 4).join());
  ok(await sr(() => { const o = (JSON.parse(localStorage.getItem('bms_panel_layout') || '{}').order || {}).charts || []; return o.slice(0, 3).join() === 'ch-hourly,ch-override,ch-plan24'; }), 'po przeciągnięciu układ zapisany');
  ok(await sr(() => !__el.shadowRoot.querySelector('.tile-drag')), 'po puszczeniu znacznik przeciągania zdjęty');
  // _layReveal: kafelek schowany pod paskiem edycji albo pod dolną krawędzią wraca w pole widzenia (bez scroll-margin)
  const rv = await sr(() => { const s = __el.shadowRoot, tiles = [...s.querySelectorAll('[data-tab-content="charts"] > [data-tile]')], t = tiles[4], bar = s.getElementById('editBar');
    window.scrollBy(0, t.getBoundingClientRect().top + 30); const before = t.getBoundingClientRect().top;
    const barB = bar.getBoundingClientRect().bottom;
    __el._layReveal(t); const a1 = t.getBoundingClientRect().top;
    window.scrollTo(0, 0); const before2 = t.getBoundingClientRect().bottom;
    __el._layReveal(t); const a2 = t.getBoundingClientRect();
    return { before, a1, barB, before2, a2b: a2.bottom, vh: innerHeight }; });
  ok(rv.before < rv.barB && rv.a1 >= rv.barB, '_layReveal: kafelek spod paska edycji wraca na widok ' + JSON.stringify(rv));
  ok(rv.before2 > rv.vh - 90 && rv.a2b <= rv.vh - 90 + 1, '_layReveal: kafelek spod dolnej krawędzi wraca na widok');
  // „Ta zakładka” cofa tylko bieżącą
  await sr(() => __el.shadowRoot.querySelector('#editBar [data-lay="reset-tab"]').click());
  ok((await ids('charts'))[0] === 'ch-plan24' && await sr(() => localStorage.getItem('bms_panel_layout') === null || !JSON.parse(localStorage.getItem('bms_panel_layout')).order.charts), 'reset zakładki w pasku edycji');
  // Zysk i log: kontrolki po narysowaniu
  await sr(() => __el.shadowRoot.querySelector('.tab[data-tab="log"]').click());
  await sleep(700);
  ok(await sr(() => __el.shadowRoot.querySelectorAll('#logTabBody [data-tile] > .tile-ctl').length === 9), 'Zysk i log: kontrolki na wszystkich 9 kafelkach');
  // wyjście: Gotowe usuwa wszystko, co dołożone
  await sr(() => __el.shadowRoot.querySelector('#editBar [data-lay="done"]').click());
  ok(await ctlN() === 0 && await sr(() => !__el.shadowRoot.querySelector('.app').hasAttribute('data-edit') && __el.shadowRoot.getElementById('editBar').hidden), 'Gotowe: kontrolki usunięte, pasek schowany');
  // Esc również kończy edycję
  await sr(() => __el.shadowRoot.getElementById('lookBtn').click());
  await sr(() => __el.shadowRoot.querySelector('#lookOv [data-look="edit"]').click());
  ok(await ctlN() > 0, 'ponowne wejście w edycję');
  await sr(() => __el.shadowRoot.querySelector('#editBar [data-lay="done"]').focus());
  await sr(() => __el.shadowRoot.querySelector('#editBar [data-lay="done"]').dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, composed: true })));
  ok(await ctlN() === 0, 'Esc kończy edycję');
  // zakładka bez kafelków: edycja przenosi na Główny
  await sr(() => __el.shadowRoot.querySelector('.tab[data-tab="dev"]').click());
  await sr(() => __el.shadowRoot.getElementById('lookBtn').click());
  await sr(() => __el.shadowRoot.querySelector('#lookOv [data-look="edit"]').click());
  ok(await sr(() => __el._activeTab === 'main'), 'edycja z zakładki bez kafelków przenosi na Główny');
  await sr(() => __el._layEditOff());
  // reset z okna
  await sr(() => __el._layoutMove('main', 'main-plan', -1));
  await sr(() => __el.shadowRoot.getElementById('lookBtn').click());
  ok(await sr(() => !__el.shadowRoot.querySelector('#lookOv [data-look="reset-all"]').disabled), 'własny układ: „Przywróć domyślny” aktywne');
  await sr(() => __el.shadowRoot.querySelector('#lookOv [data-look="reset-all"]').click());
  ok(JSON.stringify(await ids('main')) === JSON.stringify(['main-active', 'main-flow', 'main-plan']) && await sr(() => localStorage.getItem('bms_panel_layout') === null), 'reset z okna: układ domyślny, zapis usunięty');
  ok(e.errs.length === 0, 'brak błędów w konsoli: ' + JSON.stringify(e.errs));
  await b.close();
  console.log(fails ? `\n${fails} niepowodzeń` : '\nOK'); process.exit(fails ? 1 : 0);
})();
