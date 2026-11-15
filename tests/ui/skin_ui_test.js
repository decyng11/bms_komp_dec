// Styl wyglądu: Klasyczny / Material 3 — wybór w Diagnostyce → Wygląd, zapamiętany, działa z jasnym i ciemnym motywem
const { openCard, chromium } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  await e.q(() => __el._setTheme('dark'));
  await e.q(() => { __el.shadowRoot.querySelector('[data-tab="diag"]').click(); });
  await e.page.waitForFunction(() => typeof __el._dgSec_look === 'function', null, { timeout: 8000 });
  await e.q(() => __el.shadowRoot.querySelector('[data-tab="main"]').click());
  const cs = (v) => e.q((v) => getComputedStyle(__el).getPropertyValue(v).trim(), v);
  ok(await e.q(() => !__el.hasAttribute('data-skin')), 'domyślnie styl klasyczny (brak atrybutu)');
  const bgClassic = await cs('--card');
  const sec = await e.q(() => { __el._dgState && 0; return __el._dgSec_look ? __el._dgSec_look() : ''; });
  ok(/data-skin="classic"/.test(sec) && /data-skin="m3"/.test(sec) && /Material 3/.test(sec), 'Diagnostyka → Wygląd: dwa style do wyboru');
  ok(/class="dg-skin on" data-act="skin" data-skin="classic"/.test(sec), 'aktywny styl oznaczony');
  await e.q(() => __el._setSkin('m3'));
  ok(await e.q(() => __el.getAttribute('data-skin') === 'm3'), 'wybór Material 3 ustawia atrybut');
  ok(await e.q(() => localStorage.getItem('bms_panel_skin') === 'm3'), 'wybór zapamiętany w przeglądarce');
  const bgM3 = await cs('--card');
  ok(bgM3 && bgM3 !== bgClassic, 'zmienne kolorów się zmieniły: ' + bgClassic + ' → ' + bgM3);
  // jasny i ciemny motyw mają różne palety M3
  await e.q(() => __el._setTheme('light'));
  const light = await cs('--bg');
  await e.q(() => __el._setTheme('dark'));
  const dark = await cs('--bg');
  ok(light === '#f4fbf8' && dark === '#0f1513', 'M3: jasny ' + light + ', ciemny ' + dark);
  // aktywna zakładka ma wskaźnik-pigułkę, nie pełne tło
  await e.page.waitForTimeout(400);
  const nav = await e.q(() => { const t = __el.shadowRoot.querySelector('.tabs.bottom .tab.active'); const i = t.querySelector('.ti'); return { tab: getComputedStyle(t).backgroundColor, ti: getComputedStyle(i).backgroundColor }; });
  ok(/rgba\(0, 0, 0, 0\)|transparent/.test(nav.tab) && !/rgba\(0, 0, 0, 0\)/.test(nav.ti), 'M3: pigułka za ikoną aktywnej zakładki: ' + JSON.stringify(nav));
  // przeładowanie: styl wraca ze storage
  const e2 = await openCard(b, {});
  await e2.q(() => { localStorage.setItem('bms_panel_skin', 'm3'); __el._applySkin(); });
  ok(await e2.q(() => __el.getAttribute('data-skin') === 'm3'), 'odczyt zapisanego stylu');
  // wybór nieznanej wartości jest ignorowany; powrót do klasycznego
  await e.q(() => __el._setSkin('nieznany'));
  ok(await e.q(() => __el.getAttribute('data-skin') === 'm3'), 'nieznany styl ignorowany');
  await e.q(() => __el._setSkin('classic'));
  ok(await e.q(() => !__el.hasAttribute('data-skin')), 'powrót do klasycznego usuwa atrybut');
  ok((await cs('--card')) === bgClassic, 'kolory klasyczne przywrócone');
  // kliknięcie w karcie w Diagnostyce przełącza styl
  await b.close();
  console.log(fails ? `FAILS ${fails}` : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
