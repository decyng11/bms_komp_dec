// najlepsze okno dla urządzenia (pasek 48 h, najtańszy/najdroższy blok 1–4 h) i ostrzeżenia o ujemnych cenach jutro
const { chromium } = require('playwright'); const fs = require('fs');
(async () => {
  const js = fs.readFileSync(require('path').resolve(__dirname, '../../custom_components/bms_komp_dec/frontend') + '/bms-panel.js', 'utf8');
  const b = await chromium.launch(); const errs = []; let fails = 0;
  const ok = (name, cond, extra) => { if (!cond) { fails++; console.log('FAIL', name, extra === undefined ? '' : JSON.stringify(extra).slice(0, 400)); } else console.log('ok  ', name); };
  const p = await (await b.newContext({ viewport: { width: 420, height: 900 } })).newPage();
  p.on('pageerror', e => errs.push(e.message));
  await p.route('**/*', r => /^(data|about):/.test(r.request().url()) ? r.continue() : r.abort());
  await p.setContent('<html><body style="margin:0;background:#000"><div id="h" style="width:400px;margin:10px"></div></body></html>');
  await p.evaluate(() => { window.Chart = class { constructor() {} destroy() {} }; window.Chart._adapters = { _date: class { formats() { return {}; } } }; });
  await p.addScriptTag({ content: js });
  const render = (attrs, react) => p.evaluate(([attrs, react]) => {
    const S = (v, a) => ({ state: String(v), attributes: a || {}, last_updated: 'x' });
    let el = window.__el;
    if (!el) { el = document.createElement('bms-panel-card'); el.setConfig({ type: 'custom:bms-panel-card' }); document.getElementById('h').appendChild(el); window.__el = el; }
    el._lastPriceTableKey = null;
    const st = { 'sensor.bms_reserve_soc': S(30, attrs) };
    if (react !== undefined) st['switch.bms_negative_price_reaction'] = S(react ? 'on' : 'off');
    el.hass = { states: st, entities: {}, language: 'pl', callService: async () => {}, callWS: async () => ({}) };
    el._renderPriceTable();
    const sh = el.shadowRoot, c = sh.getElementById('priceTableContainer');
    const txt = (id) => { const n = sh.getElementById(id); return n ? n.innerText.replace(/\s+/g, ' ').trim() : null; };
    return { text: c.innerText.replace(/\s+/g, ' '), bars: sh.querySelectorAll('#priceFinderBars > div').length, btns: sh.querySelectorAll('[data-pf-dur]').length,
      active: (sh.querySelector('[data-pf-dur].active') || {}).dataset ? sh.querySelector('[data-pf-dur].active').dataset.pfDur : null,
      negS: txt('priceNegSell'), negB: txt('priceNegBuy'), imgs: c.querySelectorAll('img').length };
  }, [attrs, react]);
  const flat = Array.from({ length: 24 }, () => 1.0);
  const tom = flat.map((_, h) => (h >= 12 && h < 14 ? 0.3 : (h >= 18 && h < 20 ? 1.9 : 1.0)));
  const sell = Array.from({ length: 24 }, () => 0.5);
  const base = { prices_sell_today: sell, prices_sell_tomorrow: sell, prices_buy_today: flat, prices_buy_tomorrow: tom, tariff_dynamic: true };
  let r = await render(base, false);
  ok('pasek: dziś od teraz + cały jutrzejszy dzień (24 + do 24 słupków)', r.bars >= 25 && r.bars <= 48, r.bars);
  ok('cztery przyciski czasu pracy, domyślnie 2 h', r.btns === 4 && r.active === '2', [r.btns, r.active]);
  ok('najtaniej: jutro 12:00–14:00, średnio 0,30', /Najtaniej: jutro 12:00–14:00, średnio 0,30 zł\/kWh/.test(r.text), r.text.slice(-400));
  ok('najdrożej: jutro 18:00–20:00, średnio 1,90', /Najdrożej: jutro 18:00–20:00, średnio 1,90 zł\/kWh/.test(r.text), r.text.slice(-400));
  ok('bez ujemnych cen: brak ostrzeżeń', r.negS === null && r.negB === null);
  // zmiana czasu pracy: kliknięcie przycisku 3 h
  await p.evaluate(() => __el.shadowRoot.querySelector('[data-pf-dur="3"]').click());
  r = await render(base, false);
  ok('3 h: najtaniej nadal w okolicy 12:00 (blok 3 h obejmuje dwie najtańsze godziny)', /Najtaniej: jutro 1[12]:00–1[45]:00/.test(r.text) && r.active === '3', [r.active, r.text.slice(-420)]);
  await p.evaluate(() => { __el._pfDur = 2; });
  // ujemna cena sprzedaży jutro
  const sellNeg = sell.map((v, h) => (h >= 11 && h < 13 ? -0.1 : v));
  r = await render({ ...base, prices_sell_tomorrow: sellNeg }, false);
  ok('ujemna sprzedaż: ostrzeżenie z godzinami 11–13 i radą o włączeniu reakcji', r.negS && /11–13/.test(r.negS) && /Włącz/.test(r.negS), r.negS);
  r = await render({ ...base, prices_sell_tomorrow: sellNeg }, true);
  ok('ujemna sprzedaż, reakcja włączona: informacja o wstrzymaniu sprzedaży', r.negS && /wstrzyma sprzedaż/.test(r.negS) && !/Włącz/.test(r.negS), r.negS);
  // ujemna cena zakupu jutro
  const buyNeg = tom.map((v, h) => (h >= 3 && h < 5 ? -0.1 : v));
  r = await render({ ...base, prices_buy_tomorrow: buyNeg }, false);
  ok('ujemny zakup: ostrzeżenie 03–05 i podpowiedź o pralce', r.negB && /03–05/.test(r.negB) && /pralk/.test(r.negB), r.negB);
  // brak cen zakupu: bez wyszukiwarki
  r = await render({ prices_sell_today: sell, prices_sell_tomorrow: sell }, false);
  ok('bez cen zakupu: brak paska i przycisków', r.bars === 0 && r.btns === 0);
  // tylko dziś (jutro nieopublikowane)
  r = await render({ ...base, prices_buy_tomorrow: null }, false);
  ok('bez cen na jutro: pasek tylko z dzisiejszych godzin (≤ 24)', r.bars <= 24 && !/jutro 1[0-9]/.test(r.text.slice(r.text.indexOf('Najtaniej'))), r.bars);
  ok('bez błędów strony i bez wstrzyknięcia HTML', errs.length === 0 && r.imgs === 0, errs);
  console.log(fails ? `FAILS ${fails}` : 'ALL OK');
  await b.close(); process.exit(fails ? 1 : 0);
})();
