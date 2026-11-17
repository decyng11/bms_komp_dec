// Przenoszenie kafelków na inne zakładki: lista „⇄ Przenieś…” w trybie edycji i w Ustawieniach → Wygląd.
// Przeniesiony kafelek ląduje na KOŃCU zakładki docelowej, nadal się rysuje (przepływ mocy, wykresy, dziennik, sekcje EMS),
// układ przeżywa odświeżenie, „Przywróć” cofa przeniesienia, a uszkodzony zapis nie psuje panelu.
const { openCard, chromium } = require('./ui_env');
const { openSec } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const ids = (e, tab) => e.q((tab) => { const s = __el.shadowRoot; const tc = s.querySelector(`[data-tab-content="${tab}"]`); const c = tab === 'log' ? tc.querySelector('#logTabBody') : tc; return [...c.children].filter(n => n.dataset && n.dataset.tile).map(n => n.dataset.tile); }, tab);
const count = (e, id) => e.q((id) => __el.shadowRoot.querySelectorAll(`[data-tile="${id}"]`).length, id);
const goto = async (e, tab) => { await e.q((t) => __el.shadowRoot.querySelector(`.tab[data-tab="${t}"]`).click(), tab); await sleep(450); };
const mv = (e, id, to) => e.q((a) => { const s = __el.shadowRoot.querySelector(`[data-tile="${a[0]}"] > .tile-ctl select[data-lay="move"]`); if (!s) return false; s.value = a[1]; s.dispatchEvent(new Event('change', { bubbles: true })); return true; }, [id, to]);
const visible = (e, id) => e.q((id) => { const n = __el.shadowRoot.querySelector(`[data-tile="${id}"]`); if (!n) return false; const r = n.getBoundingClientRect(); return getComputedStyle(n).display !== 'none' && r.width > 100 && r.height > 20; }, id);
const clean = (e) => e.q(() => { try { ['bms_panel_layout', 'bms_panel_skin', 'bms_panel_theme', 'bms_panel_prefs_meta'].forEach(k => localStorage.removeItem(k)); } catch (x) {} __el._applyLayout(); });
const stored = (e) => e.q(() => { try { return JSON.parse(localStorage.getItem('bms_panel_layout') || 'null'); } catch (x) { return 'ERR'; } });

(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, { admin: false });
  await clean(e);
  const MAIN = ['main-active', 'main-flow', 'main-plan'];

  // ---- lista „Przenieś…” w trybie edycji
  await e.q(() => __el._layEditOn());
  ok(await e.q(() => __el.shadowRoot.querySelectorAll('[data-tab-content="main"] .tile-ctl select[data-lay="move"]').length === 3), 'edycja (Główny): lista „Przenieś…” na każdym z 3 kafelków');
  ok(await e.q(() => [...__el.shadowRoot.querySelectorAll('[data-tile="main-active"] select[data-lay="move"] option')].map(o => o.value).join() === ',charts,ems,log'), 'lista: Plan, EMS, Zysk i log (bez bieżącej zakładki)');
  ok(await e.q(() => /Przenieś na zakładkę: Aktywne funkcje/.test(__el.shadowRoot.querySelector('[data-tile="main-active"] select[data-lay="move"]').getAttribute('aria-label'))), 'lista ma nazwę dostępną dla czytnika ekranu');
  ok(await e.q(() => !__el.shadowRoot.querySelector('[data-tile="weather"] select[data-lay="move"]')), 'pogoda (kafelek stały) nie ma listy przenoszenia');
  ok(await e.q(() => /Przenieś…/.test(__el.shadowRoot.getElementById('editBar').textContent)), 'pasek edycji podpowiada przenoszenie');

  // ---- Główny → Plan: ląduje na końcu
  ok(await mv(e, 'main-active', 'charts'), 'przeniesienie „Aktywne funkcje” na Plan');
  const ch = await ids(e, 'charts'), mn = await ids(e, 'main');
  ok(ch.length === 12 && ch[11] === 'main-active' && ch[0] === 'ch-plan24', 'Plan: kafelek jest na końcu (12 kafelków): ' + ch.slice(-2));
  ok(JSON.stringify(mn) === '["main-flow","main-plan"]', 'Główny: został przepływ i plan dnia: ' + mn);
  ok(await count(e, 'main-active') === 1, 'kafelek istnieje dokładnie raz');
  ok(await e.q(() => /Przeniesiono „Aktywne funkcje” na zakładkę Plan/.test(__el.shadowRoot.getElementById('ebNote').textContent)), 'pasek edycji: komunikat o przeniesieniu (aria-live)');
  const L1 = await stored(e);
  ok(L1 && L1.v === 2 && JSON.stringify(L1.order.charts.slice(-1)) === '["main-active"]' && L1.order.main === undefined, 'zapis v2 (lista Głównego równa domyślnej po wyjęciu kafelka nie jest zapisywana): ' + JSON.stringify(L1 && L1.order).slice(0, 160));
  await e.q(() => __el._layEditOff());

  // ---- na zakładce docelowej kafelek działa: plakietki funkcji rysują się z danymi
  await goto(e, 'charts');
  ok(await visible(e, 'main-active'), 'Plan: przeniesiony kafelek widoczny');
  ok(await e.q(() => { const n = __el.shadowRoot.querySelector('[data-tile="main-active"]'); return n.parentElement.dataset.tabContent === 'charts' && n.querySelectorAll('.badge').length >= 7; }), 'Plan: kafelek ma plakietki funkcji');
  ok(await e.q(() => __el.shadowRoot.querySelector('[data-tab-content="charts"][data-custom]') !== null && __el.shadowRoot.querySelector('[data-tab-content="main"][data-custom]') !== null), 'obie zmienione zakładki oznaczone jako własny układ (odstępy)');
  ok(await e.q(() => { const t = [...__el.shadowRoot.querySelector('[data-tab-content="charts"]').children].filter(n => n.dataset.tile); return t[0].hasAttribute('data-first') && !t[11].hasAttribute('data-first'); }), 'tylko pierwszy kafelek zakładki ma data-first');

  // ---- przepływ mocy na innej zakładce: rysuje się i jest klikalny; na Głównym nie ma co rysować
  await goto(e, 'main');
  await e.q(() => { __el._layEditOn(); });
  ok(await mv(e, 'main-flow', 'ems'), 'przeniesienie przepływu mocy na EMS');
  await e.q(() => __el._layEditOff());
  await goto(e, 'ems');
  ok(await visible(e, 'main-flow') && (await ids(e, 'ems')).slice(-1)[0] === 'main-flow', 'EMS: przepływ mocy na końcu zakładki i widoczny');
  ok(await e.q(() => ['pv', 'home', 'grid', 'batt'].every(k => __el.shadowRoot.querySelectorAll(`#nodesBox .nf-hit[data-k="${k}"]`).length === 1)), 'EMS: schemat przepływu narysowany (4 klikalne węzły)');
  ok(await e.q(() => { const sv = __el.shadowRoot.querySelector('#nodesBox svg'); return !!sv && sv.getBoundingClientRect().width > 200; }), 'EMS: schemat ma sensowną szerokość');
  ok(await e.q(() => !!__el._flowRaf), 'EMS: pętla animacji przepływu działa');
  await goto(e, 'main');
  ok(await e.q(() => !__el._flowRaf), 'Główny (bez przepływu): pętla animacji zatrzymana');
  await e.q(() => { window.__states['sensor.bms_pv_power'] = { state: '1234', attributes: {}, last_updated: new Date().toISOString(), last_changed: new Date().toISOString() }; __el.hass = __mk(); });
  await goto(e, 'ems');
  ok(await e.q(() => /1[ ,.]?234|1,23/.test(__el.shadowRoot.querySelector('#nodesBox').textContent + [...__el.shadowRoot.querySelectorAll('#nodesBox svg[aria-label],#nodesBox [aria-label]')].map(n => n.getAttribute('aria-label')).join(' '))), 'EMS: po powrocie schemat pokazuje świeże dane');

  // ---- sekcje EMS przeniesione na Główny dalej się zwijają
  await goto(e, 'main');
  await e.q(() => __el._layEditOn());
  ok(await mv(e, 'ems-sell', 'main'), 'przeniesienie sekcji EMS „Przełączniki sprzedaży” na Główny');
  await e.q(() => __el._layEditOff());
  ok((await ids(e, 'main')).slice(-1)[0] === 'ems-sell', 'Główny: sekcja EMS na końcu: ' + (await ids(e, 'main')));
  const t0 = await e.q(() => { const sec = __el.shadowRoot.querySelector('[data-tile="ems-sell"]'); const body = [...sec.children].find(n => !n.classList.contains('section-title') && !n.classList.contains('tile-ctl')); return { col: sec.classList.contains('collapsed'), disp: body && getComputedStyle(body).display, cursor: getComputedStyle(sec.querySelector('.section-title')).cursor }; });
  ok(!t0.col && t0.disp !== 'none' && t0.cursor === 'pointer', 'sekcja EMS na Głównym: rozwinięta, tytuł klikalny: ' + JSON.stringify(t0));
  await e.q(() => __el.shadowRoot.querySelector('[data-tile="ems-sell"] .section-title').click());
  const t1 = await e.q(() => { const sec = __el.shadowRoot.querySelector('[data-tile="ems-sell"]'); const body = [...sec.children].find(n => !n.classList.contains('section-title') && !n.classList.contains('tile-ctl')); return { col: sec.classList.contains('collapsed'), disp: body && getComputedStyle(body).display }; });
  ok(t1.col && t1.disp === 'none', 'sekcja EMS na Głównym: klik w tytuł ją zwija: ' + JSON.stringify(t1));
  await e.q(() => __el.shadowRoot.querySelector('[data-tile="ems-sell"] .section-title').click());
  await e.q(() => { try { localStorage.removeItem('bms_ems_collapsed'); } catch (x) {} });

  // ---- wykres z Planu na Głównym; kafelek Zysku i logu na Głównym (odbudowywany przy każdej zmianie danych)
  await e.q(() => __el._layEditOn());
  ok(await mv(e, 'ch-pvprod', 'main'), 'przeniesienie wykresu produkcji PV na Główny');
  await e.q(() => __el._layEditOff()); await sleep(500);
  ok(await visible(e, 'ch-pvprod'), 'Główny: wykres produkcji PV widoczny');
  ok(await e.q(() => { const n = __el.shadowRoot.querySelector('[data-tile="ch-pvprod"]'); const c = n.querySelector('canvas, svg, .chart-empty'); return !!c && c.getBoundingClientRect().width > 100; }), 'Główny: wykres ma szerokość (nie narysowany w ukryciu)');
  await goto(e, 'log');   // kafelki dziennika powstają przy pierwszym wejściu na zakładkę
  await e.q(() => __el._layEditOn());
  ok(await mv(e, 'log-bilans', 'main'), 'przeniesienie „Bilans w PLN” (Zysk i log) na Główny');
  await e.q(() => __el._layEditOff()); await goto(e, 'main'); await sleep(500);
  ok(await count(e, 'log-bilans') === 1 && (await ids(e, 'main')).slice(-1)[0] === 'log-bilans', 'Główny: bilans jest raz i na końcu: ' + (await ids(e, 'main')));
  ok(await visible(e, 'log-bilans') && await e.q(() => /Dziś/.test(__el.shadowRoot.querySelector('[data-tile="log-bilans"]').textContent)), 'Główny: bilans narysowany z danymi');
  ok(await e.q(() => __el.shadowRoot.querySelector('#logTabBody').querySelectorAll('[data-tile]').length === 8), 'w zakładce Zysk i log zostało 8 kafelków');
  // zmiana danych → dziennik przebudowany → kafelek nadal jest raz, nadal na Głównym, ze świeżą wartością
  await e.q(() => { window.__states['sensor.bms_profit_today'] = { state: '7.77', attributes: {}, last_updated: new Date().toISOString(), last_changed: new Date().toISOString() }; __el.hass = __mk(); });
  await sleep(700);
  ok(await count(e, 'log-bilans') === 1 && await e.q(() => __el.shadowRoot.querySelector('[data-tile="log-bilans"]').parentElement.dataset.tabContent === 'main'), 'po odświeżeniu danych: bilans nadal jeden i na Głównym');
  ok(await e.q(() => /7[,.]77/.test(__el.shadowRoot.querySelector('[data-tile="log-bilans"]').textContent)), 'po odświeżeniu danych: bilans ma nową wartość');
  await goto(e, 'log');
  ok(await count(e, 'log-bilans') === 1 && (await ids(e, 'log')).length === 8 && (await ids(e, 'log'))[0] === 'log-today', 'zakładka Zysk i log: 8 kafelków bez bilansu, bez duplikatów');
  await goto(e, 'main');

  // ---- odświeżenie strony: układ odtworzony; reset zakładki cofa przeniesienia
  const e2 = await openCard(b, { admin: false });
  const saved = await stored(e);
  await e2.q((v) => { localStorage.setItem('bms_panel_layout', JSON.stringify(v)); __el._applyLayout(); __el._layRefreshTab(); }, saved);
  await sleep(700);
  const m2 = await ids(e2, 'main');
  ok(m2.includes('ems-sell') && m2.includes('ch-pvprod') && m2.includes('log-bilans') && !m2.includes('main-active') && !m2.includes('main-flow'), 'nowa instancja: układ z przeniesieniami odtworzony: ' + m2);
  ok(await count(e2, 'log-bilans') === 1 && await visible(e2, 'log-bilans'), 'nowa instancja: kafelek z dziennika narysowany na Głównym od razu');
  await e2.page.context().close();

  await e.q(() => __el._layEditOn());
  await e.q(() => __el.shadowRoot.querySelector('#editBar [data-lay="reset-tab"]').click());
  ok(JSON.stringify(await ids(e, 'main')) === JSON.stringify(MAIN), 'reset zakładki Główny: obce kafelki wróciły do siebie, własne wróciły: ' + (await ids(e, 'main')));
  const emsIds = await ids(e, 'ems'), chIds = await ids(e, 'charts');
  ok(emsIds.includes('ems-sell') === false ? false : (emsIds.length === 6 && !emsIds.includes('main-flow')), 'reset zakładki Główny: EMS ma znów 6 własnych sekcji: ' + emsIds);
  ok(chIds.length === 11 && chIds.includes('ch-pvprod') && !chIds.includes('main-active'), 'reset zakładki Główny: Plan ma znów 11 własnych kafelków: ' + chIds.length);
  ok(await e.q(() => localStorage.getItem('bms_panel_layout') === null || JSON.parse(localStorage.getItem('bms_panel_layout')).order === undefined || !Object.keys(JSON.parse(localStorage.getItem('bms_panel_layout')).order).length), 'po resecie nie zostaje zapis przeniesień');
  await e.q(() => __el._layEditOff());
  ok(await e.q(() => !__el.shadowRoot.querySelector('[data-custom]')), 'po resecie: brak oznaczenia własnego układu');

  // ---- przeniesienie tam i z powrotem (do domu) oraz resetowanie całości
  await e.q(() => { __el._layoutMoveTo('ch-fc7d', 'log'); });
  ok((await ids(e, 'log')).slice(-1)[0] === 'ch-fc7d' || await e.q(() => __el._layTabOf('ch-fc7d') === 'log'), 'ch-fc7d przeniesiony na Zysk i log');
  await e.q(() => { __el._layoutMoveTo('ch-fc7d', 'charts'); });
  const ch2 = await ids(e, 'charts');
  ok(ch2[ch2.length - 1] === 'ch-fc7d' && await e.q(() => __el._layTabOf('ch-fc7d') === 'charts'), 'powrót na własną zakładkę: ląduje na końcu');
  await e.q(() => __el._layoutMoveTo('ch-fc7d', 'ems'));
  await e.q(() => __el._layoutReset());
  ok(JSON.stringify(await ids(e, 'charts')) === JSON.stringify(['ch-plan24', 'ch-hourly', 'ch-override', 'ch-history7', 'ch-energy', 'ch-loadcons', 'ch-fc7d', 'ch-hourly-today', 'ch-hourly-tomorrow', 'ch-pvprod', 'ch-prices']) && await e.q(() => localStorage.getItem('bms_panel_layout') === null), 'przywróć domyślny: wszystko wraca, zapis usunięty');
  ok(await e.q(() => __el._layoutMoveTo('weather', 'main') === false && __el._layoutMoveTo('main-plan', '*') === false && __el._layoutMoveTo('main-plan', 'main') === false && __el._layoutMoveTo('nie-ma', 'main') === false), 'niedozwolone przeniesienia (pogoda, zakładka „*”, ta sama zakładka, nieznany kafelek) odrzucone');

  // ---- wszystkie kafelki zakładki przeniesione: pusta zakładka podpowiada, co zrobić
  await e.q(() => { ['main-active', 'main-flow', 'main-plan'].forEach(id => __el._layoutMoveTo(id, 'charts')); });
  await goto(e, 'main');
  ok(await e.q(() => __el.shadowRoot.querySelector('[data-tab-content="main"]').hasAttribute('data-empty') && !__el.shadowRoot.querySelector('[data-tab-content="main"]').hasAttribute('data-all-hidden')), 'pusta zakładka: oznaczona jako pusta (nie „wszystkie ukryte”)');
  ok(await e.q(() => /nie ma teraz kafelków/.test(getComputedStyle(__el.shadowRoot.querySelector('[data-tab-content="main"]'), '::after').content)), 'pusta zakładka: podpowiedź jak przenieść kafelki');
  ok(await e.q(() => !__el._flowRaf), 'Główny pusty: animacja przepływu zatrzymana');
  await goto(e, 'charts');
  ok(await visible(e, 'main-flow') && await e.q(() => __el.shadowRoot.querySelectorAll('#nodesBox .nf-hit').length === 4), 'przepływ mocy na Planie: narysowany');
  await e.q(() => __el._layoutReset());

  // ---- uszkodzone i sprzeczne zapisy
  for (const bad of [
    '{"v":2,"order":{"main":["ch-plan24","main-flow"],"charts":["ch-plan24"]}}',        // ten sam kafelek pod dwiema zakładkami
    '{"v":2,"order":{"main":["weather","zly",5],"*":["main-plan"]}}',                    // pogoda, nieznane, zakładka „*”
    '{"v":2,"order":{"charts":"x","ems":null,"log":{}},"hidden":"y"}',
    '{"v":2,"order":{"main":["main-flow"],"charts":["main-flow"],"ems":["main-flow"]}}', // trzy zakładki naraz
  ]) {
    await e.q((v) => { localStorage.setItem('bms_panel_layout', v); __el._applyLayout(); __el._layRefreshTab(); }, bad);
    await sleep(300);
    const all = [];
    for (const t of ['main', 'charts', 'ems', 'log']) all.push(...await ids(e, t));
    const dup = all.filter((x, i) => all.indexOf(x) !== i);
    ok(!dup.length && all.length >= 28, 'zapis ' + bad.slice(0, 44) + '… → brak duplikatów, ' + all.length + ' kafelków');
  }
  ok(await e.q(() => { localStorage.setItem('bms_panel_layout', '{"v":2,"order":{"main":["ch-plan24","main-flow"],"charts":["ch-plan24"]}}'); __el._applyLayout(); return __el._layTabOf('ch-plan24'); }) === 'main', 'sprzeczny zapis: wygrywa przeniesienie (kafelek na Głównym, nie na Planie)');
  await e.q(() => { localStorage.removeItem('bms_panel_layout'); __el._applyLayout(); __el._layRefreshTab(); });

  // ---- ukryty i przeniesiony; tryb prosty ignoruje przeniesienia
  await e.q(() => { __el._layoutMoveTo('main-plan', 'ems'); __el._layoutToggle('main-plan'); });
  ok(await e.q(() => __el.shadowRoot.querySelector('[data-tile="main-plan"]').hasAttribute('data-tile-off') && __el._layTabOf('main-plan') === 'ems'), 'kafelek przeniesiony i ukryty: oba ustawienia działają');
  await e.q(() => { __el._layoutToggle('main-plan'); });
  await e.q(() => { window.__states['switch.bms_simple_mode'] = { state: 'on', attributes: {}, last_updated: new Date().toISOString(), last_changed: new Date().toISOString() }; __el.hass = __mk(); });
  await sleep(600);
  ok(await e.q(() => __el.shadowRoot.querySelector('.app').classList.contains('simple') && __el._layTabOf('main-plan') === 'main'), 'tryb prosty: przeniesienia ignorowane (plan dnia wraca na Główny)');
  ok((await ids(e, 'main')).join() === MAIN.join(), 'tryb prosty: Główny ma 3 własne kafelki');
  await e.q(() => __el._layEditOn());
  ok(await e.q(() => !__el.shadowRoot.querySelector('.tile-ctl select[data-lay="move"]')), 'tryb prosty: w edycji nie ma listy przenoszenia');
  await e.q(() => __el._layEditOff());
  await e.q(() => { window.__states['switch.bms_simple_mode'].state = 'off'; __el.hass = __mk(); });
  await sleep(600);
  ok(await e.q(() => !__el.shadowRoot.querySelector('.app').classList.contains('simple') && __el._layTabOf('main-plan') === 'ems'), 'po wyłączeniu trybu prostego przeniesienia wracają');
  await e.q(() => __el._layoutReset());

  // ---- przeciąganie / API kolejności z obcym kafelkiem
  await e.q(() => { __el._layoutMoveTo('ems-sell', 'charts'); });
  await e.q(() => { const o = __el._layoutState().orders.charts; __el._layoutSetOrder('charts', ['ems-sell', ...o.filter(x => x !== 'ems-sell')]); });
  ok((await ids(e, 'charts'))[0] === 'ems-sell', 'kolejność: obcy kafelek można przestawić na początek zakładki');
  ok(await e.q(() => __el._layoutMove('charts', 'ems-sell', 1) === true) && (await ids(e, 'charts'))[1] === 'ems-sell', '↓ działa także dla przeniesionego kafelka');
  await e.q(() => __el._layoutReset());

  // ---- Ustawienia → Wygląd: ta sama możliwość z listy (administrator)
  const a = await openCard(b, { admin: true });
  await a.q(() => { try { localStorage.removeItem('bms_panel_layout'); } catch (x) {} __el._applyLayout(); });
  await openSec(a, 'look');
  await a.q(() => __el.shadowRoot.querySelector('#dgLayout [data-act="lay-tab"][data-lt="charts"]').click());
  ok(await a.q(() => __el.shadowRoot.querySelectorAll('#dgLayRows select[data-lay-move]').length === 11), 'Ustawienia: lista „Przenieś…” w każdym z 11 wierszy Planu');
  await a.q(() => { const s = __el.shadowRoot.querySelector('#dgLayRows select[data-lay-move="ch-prices"]'); s.value = 'main'; s.dispatchEvent(new Event('change', { bubbles: true })); });
  ok(await a.q(() => __el.shadowRoot.querySelectorAll('#dgLayRows .dg-lay-row').length === 10 && /Przeniesiono „Ceny sprzedaży prądu/.test(__el.shadowRoot.getElementById('dgLayNote').textContent)), 'Ustawienia: po przeniesieniu wiersz znika z listy Planu i jest komunikat');
  ok(await ids(a, 'main').then(m => m.slice(-1)[0] === 'ch-prices'), 'Ustawienia: kafelek wylądował na końcu Głównego');
  await a.q(() => __el.shadowRoot.querySelector('#dgLayout [data-act="lay-tab"][data-lt="main"]').click());
  ok(await a.q(() => { const r = __el.shadowRoot.querySelector('#dgLayRows [data-tile-row="ch-prices"]'); return !!r && /z: Plan/.test(r.textContent) && [...r.querySelectorAll('select option')].map(o => o.value).includes('charts'); }), 'Ustawienia: na Głównym wiersz z dopiskiem „z: Plan” i możliwością odesłania');
  await a.q(() => { const s = __el.shadowRoot.querySelector('#dgLayRows select[data-lay-move="ch-prices"]'); s.value = 'charts'; s.dispatchEvent(new Event('change', { bubbles: true })); });
  ok(await a.q(() => __el._layTabOf('ch-prices') === 'charts'), 'Ustawienia: odesłanie kafelka na własną zakładkę');
  await a.q(() => __el.shadowRoot.querySelector('#dgLayout [data-act="lay-tab"][data-lt="*"]').click());
  ok(await a.q(() => !__el.shadowRoot.querySelector('#dgLayRows select[data-lay-move]')), 'Ustawienia: pogoda bez listy przenoszenia');
  ok(a.errs.length === 0, 'brak błędów w konsoli (Ustawienia): ' + JSON.stringify(a.errs));

  ok(e.errs.length === 0, 'brak błędów w konsoli: ' + JSON.stringify(e.errs));
  await b.close();
  console.log(fails ? `\n${fails} niepowodzeń` : '\nOK'); process.exit(fails ? 1 : 0);
})();
