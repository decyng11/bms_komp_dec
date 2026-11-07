// 0.8.0: tabela cen na karcie = ceny planera (sprzedaż + zakup przy taryfie dynamicznej); zgodność wstecz; brak wstrzyknięcia HTML
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
  const render = (attrs, extraStates) => p.evaluate(([attrs, extraStates]) => {
    const S = (v, a) => ({ state: String(v), attributes: a || {}, last_updated: 'x' });
    let el = window.__el;
    if (!el) { el = document.createElement('bms-panel-card'); el.setConfig({ type: 'custom:bms-panel-card' }); document.getElementById('h').appendChild(el); window.__el = el; }
    const states = { 'sensor.bms_reserve_soc': S(30, attrs) };
    for (const [k, v] of Object.entries(extraStates || {})) states[k] = S(v[0], v[1]);
    el._lastPriceTableKey = null;
    el.hass = { states, entities: {}, language: 'pl', callService: async () => {}, callWS: async () => ({}) };
    el._renderPriceTable();
    const c = el.shadowRoot.getElementById('priceTableContainer'), h = el.shadowRoot.getElementById('priceTableHeader');
    return { html: c.innerHTML, text: c.innerText, header: h.textContent, tables: c.querySelectorAll('table').length, imgs: c.querySelectorAll('img').length,
             rules: el._sugRulesHtml() };
  }, [attrs, extraStates]);
  const sell = Array.from({ length: 24 }, (_, h) => 0.3 + h * 0.01), sellJ = Array.from({ length: 24 }, (_, h) => 0.5);
  const buy = Array.from({ length: 24 }, (_, h) => (h === 18 ? 1.55 : 0.8)), buyJ = Array.from({ length: 24 }, (_, h) => (h === 3 ? 0.41 : 0.9));

  // 1. taryfa dynamiczna: dwie tabele (sprzedaż + zakup), ceny planera
  let r = await render({ price_sell: 0.47, prices_sell_today: sell, prices_sell_tomorrow: sellJ, prices_buy_today: buy, prices_buy_tomorrow: buyJ,
                         price_buy_source: 'sensor.pstryk_json_buy.prices_today', tariff_dynamic: true, tariff_peaks: '6-11,15-23' });
  ok('dynamiczna: dwie tabele', r.tables === 2, r.tables);
  ok('dynamiczna: nagłówek z bieżącą ceną sprzedaży', r.header.includes('0.47'), r.header);
  // zakup: kolory odwrócone względem sprzedaży — najdroższa godzina czerwona, najtańsza zielona
  const buyHtml = r.html.slice(r.html.indexOf('Ceny zakupu'));
  const sellHtml = r.html.slice(0, r.html.indexOf('Ceny zakupu'));
  ok('dynamiczna: najdroższy zakup 1.55 = czerwony', /price-min">1\.55</.test(buyHtml), buyHtml.slice(0, 200));
  ok('dynamiczna: najtańszy zakup jutro 0.41 = zielony', /price-max">0\.41</.test(buyHtml));
  ok('dynamiczna: sprzedaż bez zmian (najwyższa zielona)', /price-max">0\.53</.test(sellHtml) && /price-min">0\.30</.test(sellHtml), sellHtml.slice(0, 300));
  ok('dynamiczna: w zakupie nie ma zielonej 1.55 ani czerwonej 0.41', !/price-max">1\.55</.test(buyHtml) && !/price-min">0\.41</.test(buyHtml));
  ok('dynamiczna: podpis źródła cen zakupu', r.text.includes('Ceny zakupu') && r.text.includes('pstryk_json_buy'), r.text.slice(0, 200));
  ok('dynamiczna: opis zasad wspomina taryfę dynamiczną', r.rules.includes('taryfie dynamicznej'));

  // 2. strefowa: tylko tabela sprzedaży
  r = await render({ price_sell: 0.33, prices_sell_today: sell, prices_sell_tomorrow: null, tariff_dynamic: false });
  ok('strefowa: jedna tabela', r.tables === 1 && !r.text.includes('Ceny zakupu'), r.tables);
  ok('strefowa: brak cen jutro → „--”', (r.text.match(/--/g) || []).length >= 24, r.text.slice(0, 120));
  ok('strefowa: opis zasad bez taryfy dynamicznej', !r.rules.includes('taryfie dynamicznej'));

  // 3. starszy backend (bez list w atrybutach) → dotychczasowy odczyt encji RCE
  r = await render({ price_sell: 0.33 }, { 'sensor.rce_pse_cena': [0.6, { prices: sell.map((v, h) => ({ start: `2026-11-04T${String(h).padStart(2, '0')}:00:00+01:00`, rce_pln: v })) }] });
  ok('zgodność wstecz: tabela z encji RCE', r.tables === 1 && r.text.includes('0.53'), r.text.slice(0, 120));

  // 4. wstrzyknięcie HTML przez nazwę źródła (atrybut z innej integracji) — musi zostać tekstem
  r = await render({ prices_sell_today: sell, prices_buy_today: buy, price_buy_source: '<img src=x onerror="window.__pwn=1">', tariff_dynamic: true });
  ok('brak wstrzyknięcia HTML w podpisie źródła', r.imgs === 0 && r.text.includes('<img'), r.html.slice(0, 200));
  ok('brak wykonania skryptu', await p.evaluate(() => window.__pwn === undefined));
  // 5. śmieci w listach (NaN, tekst, za krótkie) — bez błędów
  r = await render({ prices_sell_today: [null, 'x', 0.5], prices_buy_today: [NaN, 1], tariff_dynamic: true });
  ok('śmieci w listach: tabele bez wyjątku', r.tables >= 1, r.tables);
  ok('bez błędów strony', errs.length === 0, errs);
  console.log(fails ? `FAILS ${fails}` : 'ALL OK');
  await b.close();
})();
