// 0.8.1: „Do rozładowania do X%” — próg z falownika (atrybuty integracji), wynik główny przy obecnym poborze, prognoza jako druga linia
const { chromium } = require('playwright'); const fs = require('fs');
(async () => {
  const js = fs.readFileSync(require('path').resolve(__dirname, '../../custom_components/bms_komp_dec/frontend') + '/bms-panel.js', 'utf8');
  const b = await chromium.launch(); const errs = []; let fails = 0;
  const ok = (n, c, x) => { if (!c) { fails++; console.log('FAIL', n, x === undefined ? '' : JSON.stringify(x).slice(0, 400)); } };
  const p = await (await b.newContext({ viewport: { width: 420, height: 800 } })).newPage();
  p.on('pageerror', e => errs.push(e.message));
  await p.route('**/*', r => /^(data|about):/.test(r.request().url()) ? r.continue() : r.abort());
  await p.setContent('<html><body style="margin:0;background:#000"><div id="h" style="width:390px"></div></body></html>');
  await p.evaluate(() => { window.Chart = class { constructor() {} destroy() {} }; window.Chart._adapters = { _date: class { formats() { return {}; } } }; });
  await p.addScriptTag({ content: js });
  const run = (o) => p.evaluate((o) => {
    const S = (v, a) => ({ state: String(v), attributes: a || {}, last_updated: 'x' });
    let el = window.__el; if (!el) { el = document.createElement('bms-panel-card'); el.setConfig({}); document.getElementById('h').appendChild(el); window.__el = el; }
    const dk = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    const states = { 'sensor.bms_soc': S(o.soc ?? 64), 'sensor.bms_load_power': S(o.load ?? 631), 'sensor.bms_battery_power': S(o.batt ?? 708), 'sensor.bms_reserve_soc': S(25, o.attrs) };
    if (o.pv) {
      // słońce względem „teraz”: od pełnej godziny +3 h przez 9 h (test nie zależy od pory uruchomienia)
      const h0 = new Date(); h0.setMinutes(0, 0, 0);
      const arr = Array.from({ length: 48 }, (_, i) => ({ period_start: new Date(h0.getTime() + i * 36e5).toISOString(), pv_estimate: i >= 3 && i < 12 ? 4 : 0 }));
      states['sensor.solcast_pv_forecast_forecast_today'] = S(30, { detailedHourly: arr });
      states['sensor.bms_load_forecast'] = S(10, { hourly_forecast: Array.from({ length: 24 }, () => o.hl ?? 0.4) });
    }
    if (o.pvNow !== undefined) states['sensor.bms_pv_power'] = S(o.pvNow);
    if (o.sun) states['sun.sun'] = S(o.sun, {});
    el._lastEtaKey = null; el._hass = { states, entities: {}, language: 'pl', callService: async () => ({}), callWS: async () => ({}) };
    el._renderEta();
    const box = el.shadowRoot.getElementById('etaBox');
    const lab = box.querySelectorAll('.e-l')[1];
    return { text: box.innerText.replace(/\s+/g, ' '), label: lab ? lab.textContent : '', tip: lab ? lab.getAttribute('title') : '', imgs: box.querySelectorAll('img').length, html: box.innerHTML };
  }, o);
  // dodaj kontener etaBox jeśli karta go nie zbudowała przy samym setConfig
  await p.evaluate(() => { const el = document.createElement('bms-panel-card'); el.setConfig({}); document.getElementById('h').appendChild(el); window.__el = el; el.hass = { states: {}, entities: {}, language: 'pl', callService: async () => ({}), callWS: async () => ({}) }; });
  const has = await p.evaluate(() => !!__el.shadowRoot.getElementById('etaBox'));
  ok('karta ma etaBox', has);

  // 1. próg z falownika = 25%, pojemność 10 kWh, rozładowanie 708 W → (64−25)%·10 kWh / 0,708 kW = 5 h 31 min
  let r = await run({ attrs: { capacity_kwh: 10, inverter_floor: 25, inverter_floor_source: 'SOC wyłączenia 25%' } });
  ok('etykieta: próg 25%', r.label.includes('25%') && !r.label.includes('domyślnie'), r.label);
  ok('wynik główny 5 h 31 min przy obecnym rozładowaniu', r.text.includes('5 h 31 min') && r.text.includes('przy obecnym rozładowaniu 708 W'), r.text);
  ok('podpowiedź: źródło progu', r.tip.includes('SOC wyłączenia 25%'), r.tip);
  // 2. inny próg w falowniku (15%) → inna wartość: 49%·10/0,708 = 6 h 55 min
  r = await run({ attrs: { capacity_kwh: 10, inverter_floor: 15, inverter_floor_source: 'x' } });
  ok('próg 15%: etykieta i wartość', r.label.includes('15%') && r.text.includes('6 h 55 min'), r.text);
  // 3. brak progu w atrybutach → domyślne 20% z adnotacją
  r = await run({ attrs: { capacity_kwh: 10 } });
  ok('bez progu: 20% (domyślnie)', r.label.includes('20% (domyślnie)'), r.label);
  ok('bez progu: wartość z 20%: 44%·10/0,708 = 6 h 13 min', r.text.includes('6 h 13 min'), r.text);
  // 4. bateria się ładuje (PV) → liczymy przy zużyciu domu, bez PV
  r = await run({ batt: -1500, load: 631, attrs: { capacity_kwh: 10, inverter_floor: 25 } });
  ok('ładowanie: przy zużyciu domu 631 W (bez PV)', r.text.includes('przy obecnym zużyciu domu 631 W (bez PV)'), r.text);
  ok('ładowanie: 39%·10/0,631 = 6 h 11 min', r.text.includes('6 h 11 min'), r.text);
  // 5. prognoza jako druga linia, gdy różni się od wyniku głównego
  r = await run({ pv: true, attrs: { capacity_kwh: 10, inverter_floor: 25 } });
  const m5 = r.text.match(/Do słońca \(ok\. (\d\d):00\) zostanie ok\. (\d+)%/);
  const sunH = String((new Date().getHours() + 3) % 24).padStart(2, '0');
  ok('noc: „Do słońca (ok. HH:00) zostanie ok. X%” — godzina z prognozy PV, SOC z prognozy zużycia', m5 && m5[1] === sunH && +m5[2] >= 51 && +m5[2] <= 57, r.text);
  ok('stary tekst „wg prognozy z PV” zniknął', !/wg prognozy z PV|nie w 2 dni \(bateria/.test(r.text), r.text);
  r = await run({ pv: true, hl: 2.5, soc: 40, attrs: { capacity_kwh: 10, inverter_floor: 25 } });
  ok('noc: próg przed słońcem → „Przed słońcem (ok. …) dojdzie do 25% ok. …”', /Przed słońcem \(ok\. \d\d:00\) dojdzie do 25% ok\. \d\d:\d\d/.test(r.text), r.text);
  r = await run({ pv: true, pvNow: 3200, sun: 'above_horizon', attrs: { capacity_kwh: 10, inverter_floor: 25 } });
  ok('dzień (PV produkuje): bez linii o słońcu', !/słońc/.test(r.text), r.text);
  ok('główna wartość nadal z obecnego poboru', r.text.includes('5 h 31 min'), r.text);
  // 6. SOC ≤ próg
  r = await run({ soc: 24, attrs: { capacity_kwh: 10, inverter_floor: 25 } });
  ok('SOC poniżej progu: ≤ 25%', r.text.includes('≤ 25%') && r.text.includes('poziom już osiągnięty'), r.text);
  // 7. wstrzyknięcie HTML przez źródło progu
  r = await run({ attrs: { capacity_kwh: 10, inverter_floor: 25, inverter_floor_source: '"><img src=x onerror="window.__pwn=1">' } });
  ok('brak wstrzyknięcia HTML w podpowiedzi', r.imgs === 0 && !(await p.evaluate(() => window.__pwn)), r.html.slice(0, 200));
  // 8. śmieciowe wartości progu → domyślne 20%
  for (const bad of ['abc', -5, 0, 100, 250, null]) { r = await run({ attrs: { capacity_kwh: 10, inverter_floor: bad } }); ok('zły próg ' + bad + ' → 20% (domyślnie)', r.label.includes('20% (domyślnie)'), r.label); }
  // 9. symulacja z progiem zmiennym w ciągu doby: próg 60% od godziny 0 kończy natychmiast, liczba — jak dawniej
  const sim = await p.evaluate(() => {
    const e = window.__el; const pv = {}; const hl = Array.from({ length: 24 }, () => 1);
    const a = e._simulateSoc(64, 10, 25, false, hl, pv), c = e._simulateSoc(64, 10, () => 25, false, hl, pv);
    const hi = e._simulateSoc(64, 10, h => (h === (new Date().getHours() + 2) % 24 ? 60 : 25), false, hl, pv);
    return { a, c, hi };
  });
  ok('próg liczbą i funkcją dają to samo', Math.abs(sim.a - sim.c) < 1e-9, sim);
  ok('wyższy próg w jednej godzinie skraca czas', sim.hi < sim.a, sim);
  ok('bez błędów strony', errs.length === 0, errs);
  console.log(fails ? `FAILS ${fails}` : 'ALL OK'); await b.close();
})();
