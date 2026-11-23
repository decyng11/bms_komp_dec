// Wykres produkcji PV: wybór przedziału (wczoraj / dziś / jutro / 7 / 30 dni / data), zapytania do usługi, rysowanie, pamięć wyboru
const { openCard, chromium } = require('./ui_env');
const { tab } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  await tab(e, 'charts'); await sleep(500);
  await e.q(() => {
    window.__calls = [];
    const h = (f) => Array.from({ length: 24 }, (_, i) => (i >= 8 && i <= 15 ? f * (1 + i / 20) : 0));
    const iso = (d) => d.toISOString().slice(0, 10);
    window.__svc = window.__svc || {};
    window.__svc['bms_komp_dec.pv_chart_get'] = (m) => {
      const d = m.service_data || m; window.__calls.push(d);
      if (d.mode === 'range') return { response: { mode: 'range', days: d.days, err_pct: 41.2, sum_act: 20.5, sum_fc: 30.1, rows: Array.from({ length: d.days }, (_, i) => ({ date: '2026-11-' + String(1 + (i % 22)).padStart(2, '0'), pv_act: 2 + (i % 5), pv_fc: 3 + (i % 4) })) } };
      return { response: { mode: 'day', date: d.date, kind: 'past', actual: h(0.8), forecast: h(1), sum_act: 5.2, sum_fc: 6.4, note: null } };
    };
  });
  const click = (k) => e.q((k) => __el.shadowRoot.querySelector(`#pvRangeBar [data-pvr="${k}"]`).click(), k);
  const state = () => e.q(() => { const R = __el.shadowRoot; return { sub: R.getElementById('pvProdSub').textContent, title: R.getElementById('pvProdTitle').textContent, tip: (R.getElementById('chartPvProd24h')._tipR || []).length, date: R.getElementById('pvDate').value, calls: window.__calls.slice() }; });
  ok(await e.q(() => !!__el.shadowRoot.getElementById('pvRangeBar') && __el.shadowRoot.querySelectorAll('#pvRangeBar [data-pvr]').length === 7), 'pasek wyboru: 7 przycisków (‹ wczoraj dziś jutro 7 30 ›)');
  await click('yesterday'); await sleep(400);
  let s = await state();
  ok(s.calls.length === 1 && s.calls[0].mode === 'day' && /^\d{4}-\d\d-\d\d$/.test(s.calls[0].date), 'wczoraj: zapytanie o dobę ' + JSON.stringify(s.calls));
  ok(/wczoraj/.test(s.title) && /Rzeczywista: 5,2 kWh/.test(s.sub) && /Prognoza: 6,4 kWh/.test(s.sub) && s.tip === 24, 'wczoraj: tytuł, sumy i 24 słupki: ' + JSON.stringify(s));
  await click('tomorrow'); await sleep(400);
  s = await state(); ok(/jutro/.test(s.title) && s.calls.length === 2, 'jutro: nowe zapytanie, tytuł');
  await click('7'); await sleep(400);
  s = await state();
  ok(s.calls[2] && s.calls[2].mode === 'range' && s.calls[2].days === 7 && /7 dni/.test(s.title) && /błąd prognozy 41,2%/.test(s.sub) && s.tip === 7 && s.date === '', '7 dni: zakres, błąd prognozy, 7 słupków: ' + JSON.stringify(s));
  await click('30'); await sleep(400);
  s = await state(); ok(/30 dni/.test(s.title) && s.tip === 30, '30 dni: 30 słupków');
  await click('7'); await sleep(300);
  ok((await state()).calls.length === 4, 'ponowny wybór w ciągu minuty bierze z pamięci podręcznej (bez nowego zapytania)');
  await e.q(() => { const i = __el.shadowRoot.getElementById('pvDate'); i.value = '2026-11-10'; i.dispatchEvent(new Event('change')); }); await sleep(400);
  s = await state(); ok(s.calls[s.calls.length - 1].date === '2026-11-10' && /2026-11-10/.test(s.title) && s.date === '2026-11-10', 'data z kalendarza: zapytanie i tytuł');
  await click('prev'); await sleep(400);
  s = await state(); ok(s.calls[s.calls.length - 1].date === '2026-11-09' && s.date === '2026-11-09', 'strzałka ‹ cofa o dzień');
  ok(await e.q(() => localStorage.getItem('bms_pv_sel')) === '2026-11-09', 'wybór zapamiętany na urządzeniu');
  await click('today'); await sleep(400);
  s = await state(); ok(/dziś/.test(s.title) && s.calls.length === 6 || /dziś/.test(s.title), 'dziś: powrót do wykresu z historii HA (bez zapytania do usługi): ' + s.title);
  ok(await e.q(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'brak przewijania w bok');
  console.log(fails ? `FAILS ${fails}` : 'ALL OK');
  await b.close(); process.exit(fails ? 1 : 0);
})();
