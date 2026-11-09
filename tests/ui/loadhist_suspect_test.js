// Tabela „Ostatnie 14 dni”: podejrzane sumy dnia (przepisany wynik wczoraj / niepełne dane) oznaczone ⚠ i pominięte w podsumowaniu
const { chromium } = require('playwright'); const fs = require('fs');
const js = fs.readFileSync(require('path').resolve(__dirname, '../../custom_components/bms_komp_dec/frontend') + '/bms-panel.js', 'utf8');
(async () => {
  const b = await chromium.launch(); const errs = []; let fails = 0;
  const ok = (n, c, x) => { if (!c) { fails++; console.log('FAIL', n, x === undefined ? '' : JSON.stringify(x).slice(0, 400)); } };
  const p = await (await b.newContext({ viewport: { width: 420, height: 800 } })).newPage();
  p.on('pageerror', e => errs.push(e.message));
  await p.route('**/*', r => /^(data|about):/.test(r.request().url()) ? r.continue() : r.abort());
  await p.setContent('<html><body style="margin:0;background:#000"><div id="h" style="width:390px"></div></body></html>');
  await p.evaluate(() => { window.Chart = class { constructor() {} destroy() {} }; window.Chart._adapters = { _date: class { formats() { return {}; } } }; });
  await p.addScriptTag({ content: js });
  await p.evaluate(() => { const el = document.createElement('bms-panel-card'); el.setConfig({}); document.getElementById('h').appendChild(el); window.__el = el; el.hass = { states: {}, entities: {}, language: 'pl', callService: async () => ({}), callWS: async () => ({}) }; });
  const render = (rows, tune) => p.evaluate(([rows, tune]) => {
    const el = window.__el; const box = document.createElement('div'); box.id = 'loadHistTable';
    const old = el.shadowRoot.getElementById('loadHistTable'); if (old) old.remove();
    el.shadowRoot.appendChild(box);
    el._renderLoadHistTable(rows, 1.0, tune);
    return { text: box.innerText.replace(/\s+/g, ' '), html: box.innerHTML, sus: box.querySelectorAll('tr.lh-sus').length, trs: box.querySelectorAll('tbody tr').length };
  }, [rows, tune]);
  // wiersze jak u znajomego: 2.11 niepełny (2,5 przy ~25), 5.11 przepisany wynik z 4.11 (32,9); część z prognozą „wydaną” (issued)
  const R = [
    { date: '2026-11-06', weekday: 4, actual: 25.8, issued: 28.0, model: 28.0, suspect: null },
    { date: '2026-11-05', weekday: 3, actual: 32.9, issued: 25.1, model: 25.1, suspect: 'duplicate' },
    { date: '2026-11-04', weekday: 2, actual: 32.9, issued: 30.0, model: 30.0, suspect: null },
    { date: '2026-11-03', weekday: 1, actual: 25.4, issued: null, model: 24.6, suspect: null },
    { date: '2026-11-02', weekday: 0, actual: 2.5, issued: 23.3, model: 23.3, suspect: 'partial' },
  ];
  let r = await render(R);
  ok('wiersze podejrzane: 2 oznaczone', r.sus === 2 && r.trs === 5, [r.sus, r.trs]);
  ok('bez absurdalnego „+830%”', !/83\d%/.test(r.text), r.text);
  ok('⚠ przy obu podejrzanych sumach', (r.text.match(/⚠/g) || []).length >= 2, r.text);
  ok('„pominięte” w kolumnie różnicy', (r.text.match(/pominięte/g) || []).length === 2, r.text);
  ok('przekreślona wartość zachowana (2,5)', /<s>2,5<\/s>/.test(r.html), r.html.slice(0, 300));
  ok('objaśnienie ⚠ pod tabelą', /⚠ = podejrzana suma dnia/.test(r.text), r.text.slice(-300));
  // podsumowanie liczy tylko wiersze z prognozą wydaną i bez znacznika: 6.11 (28,0 vs 25,8) i 4.11 (30,0 vs 32,9) → n = 2
  ok('podsumowanie z 2 wierszy (bez podejrzanych)', /Trafione ±20%: 2\/2/.test(r.text), r.text.slice(0, 200));
  // bez podejrzanych: brak objaśnienia i brak klasy
  r = await render(R.filter(x => !x.suspect));
  ok('bez podejrzanych: brak objaśnienia ⚠', !/⚠/.test(r.text) && r.sus === 0, r.text);
  // zgodność wstecz: wiersze bez pola suspect (stary atrybut)
  r = await render(R.map(({ suspect, ...x }) => x));
  ok('stary atrybut bez „suspect”: zwykłe wiersze', r.sus === 0 && /\+83\d%/.test(r.text), r.text.slice(0, 200));
  // samostrojenie prognozy zużycia: notatka pod tabelą
  r = await render(R, { at: '2026-11-09', n: 30, tried: 60, variant: 'szybsza korekta błędu (7 dni, waga 1, do ±50%)', mae: 2.1, mae_default: 3.3, hit: 40, hit_default: 25 });
  ok('notatka: wybrany wariant i błędy', /Samostrojenie \(9\.11\)/.test(r.text) && /szybsza korekta błędu/.test(r.text) && /2,1 kWh zamiast 3,3 kWh/.test(r.text) && /40% zamiast 25%/.test(r.text), r.text.slice(-420));
  r = await render(R, { at: '2026-11-09', n: 30, tried: 60, variant: 'standardowy', mae: 3.3, mae_default: 3.3, hit: 25, hit_default: 25 });
  ok('notatka: zostaje standardowy', /zostaje wariant standardowy/.test(r.text) && /60 sprawdzonych/.test(r.text), r.text.slice(-300));
  r = await render(R, { at: '2026-11-09', n: 0, note: 'za mało dni historii (min. 10 dni oceny)' });
  ok('notatka: za mało historii', /za mało dni historii/.test(r.text), r.text.slice(-200));
  r = await render(R, null);
  ok('bez strojenia (stary backend): brak notatki', !/Samostrojenie/.test(r.text));
  ok('bez błędów strony', errs.length === 0, errs);
  console.log(fails ? `FAILS ${fails}` : 'ALL OK'); await b.close();
})();
