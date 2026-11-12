// Pasek zakładek na dole: same ikony (telefon), ikony z nazwami (komputer), przyklejony do dołu okna, przełącznik „na górze”
const { openCard, chromium } = require('./ui_env');
const { seed, curve } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
(async () => {
  const b = await chromium.launch();
  for (const mobile of [true, false]) {
    const tag = mobile ? 'telefon: ' : 'komputer: ';
    const e = await openCard(b, { mobile });
    await seed(e, { curve: curve() });
    await sleep(300);
    const info = await e.q(() => {
      const r = __el.shadowRoot, nav = r.getElementById('tabsNav'), app = r.querySelector('.app');
      const lbl = r.querySelector('.tab[data-tab="charts"] .tl');
      return { bottom: nav.classList.contains('bottom'), last: app.lastElementChild === nav,
               svgs: [...r.querySelectorAll('.tab .ti svg')].length, lblDisp: getComputedStyle(lbl).display,
               pos: getComputedStyle(nav).position, h: document.documentElement.scrollHeight, vh: innerHeight };
    });
    ok(info.bottom && info.last, tag + 'pasek jest na dole (ostatni element karty)');
    ok(info.svgs === 6, tag + 'każda zakładka ma ikonę SVG: ' + info.svgs);
    ok(info.pos === 'sticky', tag + 'pasek przyklejony (sticky)');
    ok(mobile ? info.lblDisp === 'none' : info.lblDisp !== 'none', tag + 'nazwy ' + (mobile ? 'ukryte' : 'widoczne') + ' (display=' + info.lblDisp + ')');
    if (info.h > info.vh + 300) {
      await e.q(() => window.scrollTo(0, 200)); await sleep(200);
      const r = await e.q(() => { const n = __el.shadowRoot.getElementById('tabsNav').getBoundingClientRect(); return { bottom: n.bottom, vh: innerHeight }; });
      ok(r.bottom <= r.vh + 1 && r.bottom > r.vh - 60, tag + 'przy przewinięciu pasek zostaje przy dolnej krawędzi okna (bottom=' + Math.round(r.bottom) + ', okno=' + r.vh + ')');
    } else ok(false, tag + 'strona za krótka, by sprawdzić przyklejenie');
    // zmiana zakładki działa także przez ikonę
    await e.q(() => __el.shadowRoot.querySelector('.tab[data-tab="charts"]').click()); await sleep(300);
    ok(await e.q(() => __el.shadowRoot.querySelector('.tab[data-tab="charts"]').classList.contains('active')), tag + 'kliknięcie ikony przełącza zakładkę');
    // przełącznik: na górze
    await e.q(() => { __states['switch.bms_tabs_top'] = { state: 'on', attributes: {}, last_updated: new Date().toISOString(), last_changed: new Date().toISOString() }; __el.hass = __mk(); });
    await sleep(400);
    const top = await e.q(() => { const r = __el.shadowRoot, nav = r.getElementById('tabsNav'); return { bottom: nav.classList.contains('bottom'), before: nav.nextElementSibling && nav.nextElementSibling.id, pos: getComputedStyle(nav).position }; });
    ok(!top.bottom && top.before === 'priceBar' && top.pos !== 'sticky', tag + 'przełącznik „na górze”: pasek wraca nad treść (' + JSON.stringify(top) + ')');
    await e.q(() => { __states['switch.bms_tabs_top'].state = 'off'; __el.hass = __mk(); }); await sleep(400);
    ok(await e.q(() => { const r = __el.shadowRoot; return r.getElementById('tabsNav').classList.contains('bottom') && r.querySelector('.app').lastElementChild === r.getElementById('tabsNav'); }), tag + 'wyłączony → pasek znów na dole');
  }
  await b.close();
  console.log(fails ? `FAILS ${fails}` : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
