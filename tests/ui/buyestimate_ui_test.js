// szacunek cen zakupu na jutro: kolumna „Jutro szac.” z oznaczeniem „~”, podpis, znika po prawdziwych cenach, brak wstrzyknięcia HTML
const { chromium } = require('playwright'); const fs = require('fs');
(async () => {
  const js = fs.readFileSync(require('path').resolve(__dirname, '../../custom_components/bms_komp_dec/frontend') + '/bms-panel.js', 'utf8');
  const b = await chromium.launch(); const errs = []; let fails = 0;
  const ok = (name, cond, extra) => { if (!cond) { fails++; console.log('FAIL', name, extra === undefined ? '' : JSON.stringify(extra).slice(0, 300)); } };
  const p = await (await b.newContext({ viewport: { width: 760, height: 900 } })).newPage();
  p.on('pageerror', e => errs.push(e.message));
  await p.route('**/*', r => /^(data|about):/.test(r.request().url()) ? r.continue() : r.abort());
  await p.setContent('<html><body style="margin:0;background:#000"><div id="h" style="width:720px;margin:10px"></div></body></html>');
  await p.evaluate(() => { window.Chart = class { constructor() {} destroy() {} }; window.Chart._adapters = { _date: class { formats() { return {}; } } }; });
  await p.addScriptTag({ content: js });
  const render = (attrs) => p.evaluate((attrs) => {
    const S = (v, a) => ({ state: String(v), attributes: a || {}, last_updated: 'x' });
    let el = window.__el;
    if (!el) { el = document.createElement('bms-panel-card'); el.setConfig({ type: 'custom:bms-panel-card' }); document.getElementById('h').appendChild(el); window.__el = el; }
    el._lastPriceTableKey = null;
    el.hass = { states: { 'sensor.bms_reserve_soc': S(30, attrs) }, entities: {}, language: 'pl', callService: async () => {}, callWS: async () => ({}) };
    el._renderPriceTable();
    const sh = el.shadowRoot, c = sh.getElementById('priceTableContainer'), n = sh.getElementById('priceBuyEstNote');
    const th = Array.from(c.querySelectorAll('th')).map(x => x.textContent.trim());
    return { html: c.innerHTML, text: c.innerText, tables: c.querySelectorAll('table').length, th, imgs: c.querySelectorAll('img').length,
             est: c.querySelectorAll('.price-est').length, note: n ? n.innerText.replace(/\s+/g, ' ').trim() : null, noteImgs: n ? n.querySelectorAll('img').length : 0,
             noteInside: n ? n.getBoundingClientRect().right <= c.getBoundingClientRect().right + 1 : null };
  }, attrs);
  const sell = Array.from({ length: 24 }, (_, h) => 0.3 + h * 0.01), sellJ = Array.from({ length: 24 }, () => 0.5);
  const buy = Array.from({ length: 24 }, (_, h) => (h === 18 ? 1.55 : 0.8));
  const est = Array.from({ length: 24 }, (_, h) => (h === 3 ? 0.41 : (h === 17 ? 1.75 : 0.9)));
  const note = 'Szacunek (nie ceny z rynku): mediana godzinowa z 6 ostatnich dób (weekendów). Plan z niego nie korzysta — po publikacji prawdziwych cen tabela pokaże je zamiast szacunku.';
  const base = { prices_sell_today: sell, prices_sell_tomorrow: sellJ, prices_buy_today: buy, price_buy_source: 'sensor.pstryk_current_buy_price', tariff_dynamic: true,
                 price_buy_tomorrow_state: 'waiting', price_buy_tomorrow_note: 'Ceny zakupu na jutro nie zostały jeszcze opublikowane.' };

  // 1. brak cen jutra + szacunek: kolumna „Jutro szac.”, wartości z „~”, podpis, a notatka „czekamy” nadal jest
  let r = await render({ ...base, prices_buy_tomorrow: null, prices_buy_tomorrow_est: est, price_buy_tomorrow_est_note: note });
  const buyHtml = r.html.slice(r.html.indexOf('Ceny zakupu'));
  ok('szacunek: dwie tabele', r.tables === 2, r.tables);
  ok('szacunek: nagłówek kolumny „Jutro szac.” w tabeli zakupu (2×), sprzedaż zostaje „Jutro”', r.th.filter(x => x === 'Jutro szac.').length === 2 && r.th.filter(x => x === 'Jutro').length === 2, r.th);
  ok('szacunek: wartości z tyldą i klasą price-est (24)', r.est === 24 && /~0\.41</.test(buyHtml) && /~1\.75</.test(buyHtml), r.est);
  ok('szacunek: wartości szacowane nie są kolorowane jak ceny z rynku', !/price-(min|max)">~?(0\.41|1\.75)</.test(buyHtml));
  ok('szacunek: dzisiejsze ceny zakupu nadal kolorowane (1.55 czerwone)', /price-min">1\.55</.test(buyHtml));
  ok('szacunek: podpis „nie ceny z rynku”', r.note && /nie ceny z rynku/.test(r.note) && /Plan z niego nie korzysta/.test(r.note), r.note);
  ok('szacunek: podpis mieści się w karcie', r.noteInside === true);
  ok('szacunek: notatka „czekamy na publikację” nadal jest', /nie zostały jeszcze opublikowane/.test(r.text), r.text.slice(-200));
  ok('szacunek: tabela sprzedaży bez zmian (bez tyldy)', !/~0\.5/.test(r.html.slice(0, r.html.indexOf('Ceny zakupu'))));

  // 2. prawdziwe ceny jutra → szacunek znika (nawet gdy backend zostawił stary atrybut)
  r = await render({ ...base, prices_buy_tomorrow: est, price_buy_tomorrow_state: 'ok', price_buy_tomorrow_note: null, prices_buy_tomorrow_est: est, price_buy_tomorrow_est_note: note });
  ok('prawdziwe ceny: bez „szac.”, bez tyldy, bez podpisu', r.est === 0 && !r.th.includes('Jutro szac.') && r.note === null && !/~/.test(r.text), { est: r.est, th: r.th, note: r.note });

  // 3. bez szacunku w atrybutach → jak dotąd
  r = await render({ ...base, prices_buy_tomorrow: null });
  ok('bez szacunku: brak kolumny szac. i podpisu', r.est === 0 && r.note === null && r.tables === 2 && !r.th.includes('Jutro szac.'), r.th);

  // 4. szacunek bez dzisiejszych cen zakupu → nie pokazujemy samego szacunku
  r = await render({ prices_sell_today: sell, prices_sell_tomorrow: sellJ, prices_buy_today: null, prices_buy_tomorrow: null, prices_buy_tomorrow_est: est, price_buy_tomorrow_est_note: note, tariff_dynamic: true });
  ok('szacunek bez cen dziś: tylko tabela sprzedaży, bez podpisu', r.tables === 1 && r.est === 0 && r.note === null, { t: r.tables, e: r.est });

  // 5. śmieci w szacunku: zły typ, za krótka lista, NaN-y
  for (const [name, bad] of [['napis', 'x'], ['liczba', 5], ['pusta lista', []], ['same null', Array(24).fill(null)], ['same napisy', Array(24).fill('abc')]]) {
    r = await render({ ...base, prices_buy_tomorrow: null, prices_buy_tomorrow_est: bad, price_buy_tomorrow_est_note: note });
    ok(`śmieci (${name}): bez szacunku i bez wyjątku`, r.est === 0 && r.note === null && r.tables === 2, { e: r.est, n: r.note });
  }
  r = await render({ ...base, prices_buy_tomorrow: null, prices_buy_tomorrow_est: est.slice(0, 5) });
  ok('krótka lista: uzupełniona do 24 pustymi („--”)', r.est === 5 && /--/.test(r.text), r.est);
  r = await render({ ...base, prices_buy_tomorrow: null, prices_buy_tomorrow_est: est, price_buy_tomorrow_est_note: 123 });
  ok('podpis nie-tekst: pomijany, tabela szacunku jest', r.note === null && r.est === 24);

  // 6. wstrzyknięcie HTML przez podpis
  r = await render({ ...base, prices_buy_tomorrow: null, prices_buy_tomorrow_est: est, price_buy_tomorrow_est_note: '<img src=x onerror="window.__pwn=1">' });
  ok('podpis szacunku: tekst, nie HTML', r.noteImgs === 0 && r.note.includes('<img'), r.note);
  ok('brak wykonania skryptu', await p.evaluate(() => window.__pwn === undefined));
  ok('brak błędów strony', errs.length === 0, errs);
  await b.close();
  console.log(fails ? `FAILS ${fails}` : 'ALL OK');
  process.exit(fails ? 1 : 0);
})();
