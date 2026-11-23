// notatka o własnych cenach z PSE pod tabelą cen: stan „uczy się”, dopasowanie i podpowiedź, znika po wyłączeniu, brak wstrzyknięcia HTML
const { chromium } = require('playwright'); const fs = require('fs');
(async () => {
  const js = fs.readFileSync(require('path').resolve(__dirname, '../../custom_components/bms_komp_dec/frontend') + '/bms-panel.js', 'utf8');
  const b = await chromium.launch(); const errs = []; let fails = 0;
  const ok = (name, cond, extra) => { if (!cond) { fails++; console.log('FAIL', name, extra === undefined ? '' : JSON.stringify(extra).slice(0, 300)); } else console.log('ok  ', name); };
  const p = await (await b.newContext({ viewport: { width: 760, height: 900 } })).newPage();
  p.on('pageerror', e => errs.push(e.message));
  await p.route('**/*', r => /^(data|about):/.test(r.request().url()) ? r.continue() : r.abort());
  await p.setContent('<html><body style="margin:0;background:#000"><div id="h" style="width:720px;margin:10px"></div></body></html>');
  await p.evaluate(() => { window.Chart = class { constructor() {} destroy() {} }; window.Chart._adapters = { _date: class { formats() { return {}; } } }; });
  await p.addScriptTag({ content: js });
  const render = (feed) => p.evaluate((feed) => {
    const S = (v, a) => ({ state: String(v), attributes: a || {}, last_updated: 'x' });
    let el = window.__el;
    if (!el) { el = document.createElement('bms-panel-card'); el.setConfig({ type: 'custom:bms-panel-card' }); document.getElementById('h').appendChild(el); window.__el = el; }
    el._lastPriceTableKey = null;
    const sell = Array.from({ length: 24 }, (_, h) => 0.3 + h * 0.01);
    const st = { 'sensor.bms_reserve_soc': S(30, { prices_sell_today: sell, prices_sell_tomorrow: sell, prices_buy_today: sell, prices_buy_tomorrow: sell }) };
    if (feed) st['sensor.bms_buy_rce'] = S(0.8, feed);
    el.hass = { states: st, entities: {}, language: 'pl', callService: async () => {}, callWS: async () => ({}) };
    el._renderPriceTable();
    const n = el.shadowRoot.getElementById('priceFeedNote');
    return n ? { text: n.innerText.replace(/\s+/g, ' ').trim(), imgs: n.querySelectorAll('img').length } : null;
  }, feed);
  ok('wyłączone: brak notatki', (await render({ enabled: false, fit: null })) === null);
  let r = await render({ enabled: true, fit: null, note: 'Brak dopasowania do Twojej taryfy: potrzeba co najmniej 3 dób.' });
  ok('włączone bez dopasowania: pokazuje powód', r && /Brak dopasowania/.test(r.text), r);
  r = await render({ enabled: true, fit: { quality: 'dobre', rmse: 0.0123, days: 9, a: 1.23, pairs: 200 }, is_buy_source: false, tomorrow_available: true });
  ok('dopasowanie: jakość, błąd, liczba dób i wskazówka o sensorze', r && /dobre/.test(r.text) && /0\.012/.test(r.text) && /9 dób/.test(r.text) && /sensor\.bms_buy_rce/.test(r.text), r);
  r = await render({ enabled: true, fit: { quality: 'idealne', rmse: 0.004, days: 12, a: 1.23, pairs: 280, exact: 0.987, max_err: 0.02 }, is_buy_source: false, tomorrow_available: true });
  ok('odsetek godzin trafionych co do grosza i największy błąd', r && /idealne/.test(r.text) && /99% godzin/.test(r.text) && /0\.02 zł/.test(r.text), r);
  r = await render({ enabled: true, fit: { quality: 'średnie', rmse: 0.09, days: 5, a: 1.2, pairs: 100 }, is_buy_source: true, tomorrow_available: false });
  ok('jako źródło zakupu, jutra jeszcze brak: informacja o publikacji PSE', r && /nie opublikowało/.test(r.text), r);
  r = await render({ enabled: true, fit: null, note: '<img src=x onerror=alert(1)>' });
  ok('brak wstrzyknięcia HTML', r && r.imgs === 0, r);
  // klucz API Pstryka: pole, stan „ustawiony”, zapis wywołuje usługę z kluczem, a pusty zapis nic nie wysyła
  await render({ enabled: true, fit: null, token_set: false, note: 'x' });
  let tk = await p.evaluate(() => { const sh = window.__el.shadowRoot; const i = sh.getElementById('pfToken');
    return { has: !!i, type: i && i.type, clear: !!sh.querySelector('[data-pf-token="clear"]'), txt: sh.getElementById('priceFeedToken').innerText }; });
  ok('bez klucza: pole hasła, bez przycisku „Usuń”', tk.has && tk.type === 'password' && !tk.clear, tk);
  await p.evaluate(() => { window.__calls = []; window.__el._hass.callService = async (d, s, data) => { window.__calls.push([d, s, data]); }; });
  await p.evaluate(() => window.__el.shadowRoot.querySelector('[data-pf-token="save"]').click());
  ok('pusty klucz: nic nie wysyła', (await p.evaluate(() => window.__calls.length)) === 0);
  await p.evaluate(() => { window.__el.shadowRoot.getElementById('pfToken').value = '  sk-123  '; window.__el.shadowRoot.querySelector('[data-pf-token="save"]').click(); });
  await p.waitForTimeout(100);
  const c1 = await p.evaluate(() => window.__calls);
  ok('zapis: usługa pricefeed_token_set z przyciętym kluczem', c1.length === 1 && c1[0][1] === 'pricefeed_token_set' && c1[0][2].token === 'sk-123', c1);
  r = await render({ enabled: true, fit: null, token_set: true, exact_today: true, exact_tomorrow: true, note: 'Ceny dokładnie z API Pstryka (price_gross, jak w aplikacji)' });
  ok('klucz ustawiony: notatka o dokładnych cenach i oznaczenie', r && /dokładnie z API Pstryka/.test(r.text), r);
  tk = await p.evaluate(() => { const sh = window.__el.shadowRoot; return { clear: !!sh.querySelector('[data-pf-token="clear"]'), txt: sh.getElementById('priceFeedToken').innerText }; });
  ok('klucz ustawiony: widać „ustawiony” i przycisk „Usuń”', tk.clear && /ustawiony/.test(tk.txt), tk);
  ok('bez błędów strony', errs.length === 0, errs);
  console.log(fails ? `FAILS ${fails}` : 'ALL OK');
  await b.close(); process.exit(fails ? 1 : 0);
})();
