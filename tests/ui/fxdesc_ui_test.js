// Funkcje automatyczne: opis każdej funkcji i każdego pola liczbowego, bez wstrzyknięcia HTML i bez przewijania w bok
const { openCard, chromium } = require('./ui_env');
const { tab } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
(async () => {
  const b = await chromium.launch();
  for (const w of [320, 390]) {
    const e = await openCard(b, { admin: true, mobile: true });
    await e.page.setViewportSize({ width: w, height: 800 });
    await e.q((w) => { document.getElementById('h').style.width = w + 'px'; }, w);
    await tab(e, 'log'); await sleep(600);
    const r = await e.q(() => { const R = __el.shadowRoot; const d = [...R.querySelectorAll('.fx-desc')], n = [...R.querySelectorAll('.fx-ndesc')];
      return { d: d.length, empty: d.filter(x => x.textContent.trim().length < 40).length, n: n.length, nEmpty: n.filter(x => x.textContent.trim().length < 20).length,
        toggles: R.querySelectorAll('.fx-help').length, doc: document.documentElement.scrollWidth,
        txt: (R.querySelector('.fx-desc[data-fx="full_charge"]') || {}).textContent || '' }; });
    ok(r.d >= 9 && r.empty === 0, `${w}px: opis przy każdej funkcji (${r.d})`);
    ok(r.n >= 6 && r.nEmpty === 0, `${w}px: opis przy każdym polu liczbowym (${r.n})`);
    ok(/100%/.test(r.txt) && /kalibrował SOC/.test(r.txt), `${w}px: opis pełnego ładowania`);
    ok(r.doc <= w, `${w}px: bez przewijania w bok (${r.doc})`);
    await e.page.context().close();
  }
  console.log(fails ? `FAILS ${fails}` : 'ALL OK');
  await b.close(); process.exit(fails ? 1 : 0);
})();
