// Układ panelu (Ustawienia → Wygląd): przestawianie i ukrywanie kafelków, zapis w przeglądarce, przywracanie, alerty zawsze widoczne
const { openCard, chromium } = require('./ui_env');
const { openSec } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, { admin: true });
  await e.q(() => { try { localStorage.removeItem('bms_panel_layout'); } catch (x) {} });
  const ids = (tab) => e.q((tab) => { const s = __el.shadowRoot; const tc = s.querySelector(`[data-tab-content="${tab}"]`); const c = tab === 'log' ? tc.querySelector('#logTabBody') : tc; return [...c.children].filter(n => n.dataset && n.dataset.tile).map(n => n.dataset.tile); }, tab);
  const off = () => e.q(() => [...__el.shadowRoot.querySelectorAll('[data-tile-off]')].map(n => n.dataset.tile));
  const shown = (id) => e.q((id) => { const n = __el.shadowRoot.querySelector(`[data-tile="${id}"]`); return !!n && getComputedStyle(n).display !== 'none'; }, id);

  // rejestr zgodny z szablonem: każdy kafelek z rejestru istnieje w DOM i odwrotnie
  await e.q(() => __el.shadowRoot.querySelector('[data-tab="log"]').click());
  await e.page.waitForTimeout(500);
  const reg = await e.q(() => __el._layoutGroups().map(g => [g.tab, g.tiles.map(t => t[0])]));
  for (const [tab, list] of reg) {
    if (tab === '*') { ok(await e.q(() => !!__el.shadowRoot.querySelector('[data-tile="weather"]')), 'pogoda: kafelek istnieje'); continue; }
    const dom = await ids(tab);
    ok(JSON.stringify(dom) === JSON.stringify(list), `zakładka ${tab}: kafelki w DOM = rejestr (${dom.length}) ${dom.length === list.length ? '' : JSON.stringify(dom)}`);
  }
  await e.q(() => __el.shadowRoot.querySelector('[data-tab="main"]').click());
  ok((await off()).length === 0 && await e.q(() => localStorage.getItem('bms_panel_layout') === null), 'domyślnie: nic ukryte, brak zapisu');
  ok(await e.q(() => !__el.shadowRoot.querySelector('[data-custom]')), 'domyślnie: brak oznaczenia własnego układu (odstępy jak dotąd)');

  // interfejs w Wygląd
  await e.q(() => __el.shadowRoot.querySelector('[data-tab="diag"]').click());
  await e.page.waitForFunction(() => typeof __el._dgSec_look === 'function', null, { timeout: 8000 });
  const html = await e.q(() => __el._dgSec_look());
  ok(/id="dgLayout"/.test(html) && /Układ panelu/.test(html), 'Wygląd: karta „Układ panelu”');
  ok(['main', 'charts', 'ems', 'log', '\\*'].every(t => new RegExp('data-act="lay-tab" data-lt="' + t + '"').test(html)), 'Wygląd: zakładki do wyboru (Główny, Plan, EMS, Zysk i log, Wszystkie)');
  ok(/Ukryj/.test(html) && /Przesuń wyżej/.test(html) && /Przywróć/.test(html), 'Wygląd: przyciski przesuwania, ukrywania i przywracania');
  ok(/Alerty \(cena, próg falownika, status\) zawsze zostają widoczne/.test(html), 'Wygląd: informacja, że alerty zostają');

  // przesuwanie: Plan dnia o jedno miejsce wyżej (main: active, flow, plan → active, plan, flow)
  ok(await e.q(() => __el._layoutMove('main', 'main-plan', -1)), 'przesunięcie wyżej działa');
  ok(JSON.stringify(await ids('main')) === JSON.stringify(['main-active', 'main-plan', 'main-flow']), 'main: nowa kolejność w DOM: ' + JSON.stringify(await ids('main')));
  ok(await e.q(() => JSON.parse(localStorage.getItem('bms_panel_layout')).order.main.join() === 'main-active,main-plan,main-flow'), 'kolejność zapisana w przeglądarce');
  ok(await e.q(() => __el.shadowRoot.querySelector('[data-tab-content="main"]').hasAttribute('data-custom')) && await e.q(() => __el.shadowRoot.querySelector('[data-tab-content="main"] [data-tile]').hasAttribute('data-first')), 'własny układ: oznaczony pierwszy kafelek');
  ok(!(await e.q(() => __el._layoutMove('main', 'main-active', -1))), 'pierwszy kafelek nie przesuwa się wyżej');
  ok(!(await e.q(() => __el._layoutMove('main', 'main-flow', 1))), 'ostatni kafelek nie przesuwa się niżej');
  ok(!(await e.q(() => __el._layoutMove('*', 'weather', 1))), 'pogody (stała pozycja) nie przesuwamy');
  // powrót do domyślnej kolejności kasuje zapis
  await e.q(() => __el._layoutMove('main', 'main-plan', 1));
  ok(JSON.stringify(await ids('main')) === JSON.stringify(['main-active', 'main-flow', 'main-plan']) && await e.q(() => localStorage.getItem('bms_panel_layout') === null), 'powrót do domyślnej kolejności: zapis usunięty');
  ok(await e.q(() => !__el.shadowRoot.querySelector('[data-tab-content="main"]').hasAttribute('data-custom')), 'domyślna kolejność: znacznik własnego układu zdjęty');

  // ukrywanie
  await e.q(() => __el.shadowRoot.querySelector('[data-tab="main"]').click());
  ok(await e.q(() => __el._layoutToggle('main-active')) && JSON.stringify(await off()) === '["main-active"]', 'ukrycie „Aktywne funkcje”');
  ok(!(await shown('main-active')) && await shown('main-flow') && await shown('main-plan'), 'ukryty kafelek niewidoczny, pozostałe widoczne');
  ok(await e.q(() => JSON.parse(localStorage.getItem('bms_panel_layout')).hidden.join() === 'main-active'), 'ukrycie zapisane');
  // alerty i okno „dlaczego” nie są kafelkami
  ok(await e.q(() => ['priceBar', 'floorAlert', 'statusBanner', 'whyBox'].every(id => !__el.shadowRoot.getElementById(id).hasAttribute('data-tile') && !__el.shadowRoot.getElementById(id).hasAttribute('data-tile-off'))), 'alerty (cena, próg, status, „dlaczego”) nie są kafelkami i nie da się ich ukryć');
  // pogoda
  ok(await e.q(() => __el._layoutToggle('weather')) && !(await shown('weather')), 'pogodę można ukryć');
  await e.q(() => __el._layoutToggle('weather'));
  ok(await shown('weather'), 'pogodę można pokazać z powrotem');

  // wszystkie kafelki zakładki ukryte → komunikat
  for (const id of ['main-flow', 'main-plan']) await e.q((id) => __el._layoutToggle(id), id);
  ok(await e.q(() => __el.shadowRoot.querySelector('[data-tab-content="main"]').hasAttribute('data-all-hidden')), 'wszystko ukryte: tab oznaczony');
  const msg = await e.q(() => getComputedStyle(__el.shadowRoot.querySelector('[data-tab-content="main"]'), '::after').content);
  ok(/Układ panelu/.test(msg), 'wszystko ukryte: czytelny komunikat, jak przywrócić: ' + msg.slice(0, 60));

  // przywracanie jednej zakładki / całości
  await e.q(() => __el._layoutMove('charts', 'ch-prices', -1));
  await e.q(() => __el._layoutReset('main'));
  ok((await off()).length === 0 && (await ids('charts')).indexOf('ch-prices') === 9, 'reset zakładki Główny nie rusza układu zakładki Plan');
  await e.q(() => __el._layoutReset());
  ok((await ids('charts')).indexOf('ch-prices') === 10 && await e.q(() => localStorage.getItem('bms_panel_layout') === null), 'reset całości: wszystko domyślne, zapis usunięty');

  // zakładka Zysk i log: kafelki powstają od nowa przy rysowaniu — układ musi przetrwać
  await e.q(() => { __el._layoutMove('log', 'log-journal', -1); __el._layoutToggle('log-bilans'); });
  await e.q(() => __el.shadowRoot.querySelector('[data-tab="main"]').click());
  await e.q(() => { __el._lastLogKey = null; __el.shadowRoot.querySelector('[data-tab="log"]').click(); });
  await e.page.waitForTimeout(500);
  const lg = await ids('log');
  ok(lg.indexOf('log-journal') === lg.indexOf('log-auto') - 1 && (await off()).includes('log-bilans'), 'log: kolejność i ukrycie przetrwały ponowne rysowanie: ' + JSON.stringify(lg));
  await e.q(() => { __el._lastLogKey = null; __el._renderLogTab(); });
  ok((await off()).includes('log-bilans'), 'log: ukrycie po kolejnym odświeżeniu');
  await e.q(() => __el._layoutReset());

  // trwałość po przeładowaniu karty (nowy element czyta zapis) + odporność na uszkodzony zapis
  await e.q(() => { __el._layoutMove('ems', 'ems-gridcharge', -1); __el._layoutToggle('ch-hourly'); });
  const saved = await e.q(() => localStorage.getItem('bms_panel_layout'));
  const e2 = await openCard(b, { admin: true });
  await e2.q((v) => { localStorage.setItem('bms_panel_layout', v); __el._applyLayout(); }, saved);
  const emsIds = await e2.q(() => [...__el.shadowRoot.querySelector('[data-tab-content="ems"]').children].filter(n => n.dataset.tile).map(n => n.dataset.tile));
  ok(emsIds.indexOf('ems-gridcharge') === emsIds.length - 2 && await e2.q(() => __el.shadowRoot.querySelector('[data-tile="ch-hourly"]').hasAttribute('data-tile-off')), 'nowa instancja karty odtwarza zapisany układ');
  for (const bad of ['{', '[]', 'null', '{"order":"x","hidden":"y"}', '{"order":{"main":["zly","main-plan",5]},"hidden":["nie-ma",1]}', '{"order":{"main":["main-plan","main-plan"]},"hidden":[]}']) {
    const r = await e2.q((v) => { localStorage.setItem('bms_panel_layout', v); __el._applyLayout(); const c = __el.shadowRoot.querySelector('[data-tab-content="main"]'); return [...c.children].filter(n => n.dataset.tile).map(n => n.dataset.tile + (n.hasAttribute('data-tile-off') ? '!' : '')); }, bad);
    ok(r.length === 3 && new Set(r.map(x => x.replace('!', ''))).size === 3, 'uszkodzony zapis ' + bad.slice(0, 40) + ' → brak błędu, 3 kafelki: ' + JSON.stringify(r));
  }
  ok(e.errs.length === 0 && e2.errs.length === 0, 'brak błędów w konsoli: ' + JSON.stringify([...e.errs, ...e2.errs]));

  // interfejs: kliknięcia przycisków (jak użytkownik) — po odblokowaniu zakładki Ustawienia
  await e.q(() => { localStorage.removeItem('bms_panel_layout'); __el._applyLayout(); });
  await openSec(e, 'look');
  const render = () => e.q(() => !!__el.shadowRoot.getElementById('dgLayout'));
  ok(await render(), 'karta układu w sekcji Wygląd po odblokowaniu');
  await e.q(() => __el.shadowRoot.querySelector('#dgLayout [data-act="lay-tab"][data-lt="charts"]').click());
  ok(await e.q(() => __el.shadowRoot.querySelectorAll('#dgLayRows .dg-lay-row').length === 11), 'zakładka Plan: 11 wierszy');
  await e.q(() => __el.shadowRoot.querySelector('#dgLayout [data-act="lay-down"][data-id="ch-plan24"]').click());
  ok(JSON.stringify((await ids('charts')).slice(0, 2)) === '["ch-hourly","ch-plan24"]', 'klik ↓: kafelek przesunięty na panelu');
  ok(await e.q(() => document.activeElement === __el || __el.shadowRoot.activeElement && __el.shadowRoot.activeElement.dataset.id === 'ch-plan24'), 'fokus wraca na przycisk przesuniętego kafelka');
  await e.q(() => __el.shadowRoot.querySelector('#dgLayout [data-act="lay-eye"][data-id="ch-pvprod"]').click());
  ok((await off()).includes('ch-pvprod') && await e.q(() => __el.shadowRoot.querySelector('#dgLayout [data-tile-row="ch-pvprod"]').classList.contains('off')), 'klik „Ukryj”: kafelek znika z panelu, wiersz oznaczony');
  await e.q(() => __el.shadowRoot.querySelector('#dgLayout [data-act="lay-reset-tab"]').click());
  ok((await off()).length === 0 && (await ids('charts'))[0] === 'ch-plan24', 'klik „Przywróć tę zakładkę”');
  await e.q(() => __el.shadowRoot.querySelector('#dgLayout [data-act="lay-tab"][data-lt="*"]').click());
  ok(await e.q(() => !__el.shadowRoot.querySelector('#dgLayout [data-act="lay-up"]')), 'Wszystkie zakładki: bez przycisków przesuwania');
  await e.q(() => __el.shadowRoot.querySelector('#dgLayout [data-act="lay-eye"][data-id="weather"]').click());
  ok((await off()).includes('weather'), 'Wszystkie zakładki: ukrycie pogody z interfejsu');
  await e.q(() => __el.shadowRoot.querySelector('#dgLayout [data-act="lay-reset-all"]').click());
  ok((await off()).length === 0 && await e.q(() => localStorage.getItem('bms_panel_layout') === null), 'klik „Przywróć cały domyślny układ”');
  ok(e.errs.length === 0, 'brak błędów w konsoli (interfejs): ' + JSON.stringify(e.errs));
  await b.close();
  console.log(fails ? `\n${fails} niepowodzeń` : '\nOK'); process.exit(fails ? 1 : 0);
})();
