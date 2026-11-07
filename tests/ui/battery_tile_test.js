// Kafelka „Bateria” (wariant A): jedna kafelka, 4 stany + plan ładowania z sieci z sensora plan_curve
const { chromium } = require('playwright'); const fs = require('fs');
(async () => {
  const js = fs.readFileSync(require('path').resolve(__dirname, '../../custom_components/bms_komp_dec/frontend') + '/bms-panel.js', 'utf8');
  const b = await chromium.launch(); const errs = []; let fails = 0;
  const ok = (n, c, x) => { if (!c) { fails++; console.log('FAIL', n, x === undefined ? '' : JSON.stringify(x).slice(0, 500)); } };
  const p = await (await b.newContext({ viewport: { width: 420, height: 800 } })).newPage();
  p.on('pageerror', e => errs.push(e.message));
  await p.route('**/*', r => /^(data|about):/.test(r.request().url()) ? r.continue() : r.abort());
  await p.setContent('<html><body style="margin:0;background:#000"><div id="h" style="width:390px"></div></body></html>');
  await p.evaluate(() => { window.Chart = class { constructor() {} destroy() {} }; window.Chart._adapters = { _date: class { formats() { return {}; } } }; });
  await p.addScriptTag({ content: js });
  await p.evaluate(() => { const el = document.createElement('bms-panel-card'); el.setConfig({}); document.getElementById('h').appendChild(el); window.__el = el; el.hass = { states: {}, entities: {}, language: 'pl', callService: async () => ({}), callWS: async () => ({}) }; });

  // o = { soc, batt (W surowe: >0 rozładowanie, <0 ładowanie), load, plan: {start, stop, skip, start2, stop2}|'none'|undefined, planErr }
  const run = (o) => p.evaluate((o) => {
    const S = (v, a) => ({ state: String(v), attributes: a || {}, last_updated: 'x' });
    const el = window.__el;
    const states = { 'sensor.bms_soc': S(o.soc ?? 23), 'sensor.bms_load_power': S(o.load ?? 860), 'sensor.bms_battery_power': S(o.batt ?? 443),
      'sensor.bms_reserve_soc': S(25, { capacity_kwh: 10, inverter_floor: 20 }) };
    if (o.plan !== undefined) {
      const pr = {};
      if (o.plan && o.plan !== 'none') {
        pr.start_grid_charge = { proposed: o.plan.start, current: '—', skip: !!o.plan.skip };
        pr.stop_grid_charge = { proposed: o.plan.stop, current: '—', skip: !!o.plan.skip };
      } else {
        pr.start_grid_charge = { proposed: null, skip: true }; pr.stop_grid_charge = { proposed: null, skip: true };
      }
      states['sensor.bms_plan_curve'] = S('ok', { proposals: pr, error: o.planErr || null });
    }
    el._lastEtaKey = null; el._hass = { states, entities: {}, language: 'pl', callService: async () => ({}), callWS: async () => ({}) };
    el._renderEta();
    const box = el.shadowRoot.getElementById('etaBox');
    return { n: box.querySelectorAll('.eta').length, label: (box.querySelector('.e-l') || {}).textContent || '', text: box.innerText.replace(/\s+/g, ' '), html: box.innerHTML };
  }, o);
  const hh = (d) => String(d.getHours()).padStart(2, '0') + ':00';
  const now = new Date();
  const inH = (n) => hh(new Date(now.getTime() + n * 3600000));

  // 1. zawsze jedna kafelka
  let r = await run({ batt: 443 });
  ok('jedna kafelka zamiast dwóch', r.n === 1, r.n);

  // 2. rozładowanie, brak sensora planu → stary opis „Do rozładowania”, bez komunikatu o planie
  ok('rozładowanie bez sensora planu: etykieta', /Do rozładowania do 20%/.test(r.label), r.label);
  ok('rozładowanie bez sensora planu: bez „Brak zaplanowanego”', !/Brak zaplanowanego/.test(r.text), r.text);

  // 3. rozładowanie, plan jest, ale bez ładowania z sieci → komunikat
  r = await run({ batt: 443, plan: 'none' });
  ok('plan bez ładowania z sieci: komunikat', /Brak zaplanowanego ładowania z sieci/.test(r.text), r.text);

  // 4. zaplanowane ładowanie za kilka godzin → „start …”, liczba godzin do startu, godziny planu
  const s4 = inH(14), e4 = inH(22);
  r = await run({ batt: 443, plan: { start: s4, stop: e4 } });
  ok('plan: etykieta „ładowanie z sieci”', /ładowanie z sieci/.test(r.label), r.label);
  ok('plan: „start” z godziną', r.text.includes('start') && r.text.includes(s4), r.text);
  ok('plan: godziny okna', r.text.includes(`${s4}–${e4}`), r.text);
  ok('plan: czas do startu 13–14 h', /za 1[34] h/.test(r.text), r.text);

  // 5. bateria zejdzie do progu przed startem → ostrzeżenie
  //    (23−20)%·10 kWh / 0,443 kW ≈ 41 min, a start za 3 h
  r = await run({ batt: 443, plan: { start: inH(3), stop: inH(9) } });
  ok('ostrzeżenie: próg przed startem ładowania', /Uwaga: bateria dojdzie do 20%/.test(r.text) && /przed startem ładowania/.test(r.text), r.text);
  // ... a gdy starczy do startu — bez ostrzeżenia
  r = await run({ soc: 60, batt: 300, plan: { start: inH(3), stop: inH(9) } });
  ok('bez ostrzeżenia, gdy bateria dotrwa do startu', !/Uwaga/.test(r.text), r.text);

  // 6. okno trwa teraz (start 1 h temu, koniec za 5 h), ładowanie jeszcze nie ruszyło
  r = await run({ batt: 100, plan: { start: inH(-1), stop: inH(5) } });
  ok('okno trwa: „okno do …”', r.text.includes('okno do') && r.text.includes('trwa'), r.text);
  ok('okno trwa: bez „start”', !/\bstart\b/.test(r.label + r.text.split('plan ładowania')[0]), r.text);

  // 7. okno przez północ (22:00–06:00), godzina 23:00 → trwa; liczone od zegara, nie od dnia
  const fake = (hh_) => p.evaluate((h) => { const R = Date; const fixed = new R(); fixed.setHours(h, 10, 0, 0); window.__realDate = R;
    window.Date = class extends R { constructor(...a) { if (a.length) super(...a); else super(fixed.getTime()); } static now() { return fixed.getTime(); } }; }, hh_);
  const unfake = () => p.evaluate(() => { window.Date = window.__realDate || Date; });
  await fake(23);
  r = await run({ batt: 100, plan: { start: '22:00', stop: '06:00' } });
  ok('przez północ o 23:10: okno trwa', r.text.includes('okno do 06:00'), r.text);
  await fake(7);
  r = await run({ batt: 100, plan: { start: '22:00', stop: '06:00' } });
  ok('o 07:10: start dziś o 22:00 (za ok. 14 h)', r.text.includes('start 22:00') && /za 14 h/.test(r.text), r.text);
  await fake(21);
  r = await run({ batt: 100, plan: { start: '22:00', stop: '06:00' } });
  ok('o 21:10: start za 50 min', r.text.includes('start 22:00') && /za 50 min/.test(r.text), r.text);
  await unfake();

  // 8. pominięta propozycja (skip) = brak planu; plan z błędem = jak brak sensora
  r = await run({ batt: 443, plan: { start: inH(5), stop: inH(9), skip: true } });
  ok('skip: traktowane jak brak planu', /Brak zaplanowanego/.test(r.text) && !/\bstart\b/.test(r.text), r.text);
  r = await run({ batt: 443, plan: { start: inH(5), stop: inH(9) }, planErr: 'błąd' });
  ok('błąd planu: bez planu i bez komunikatu', !/\bstart\b/.test(r.text) && !/Brak zaplanowanego/.test(r.text), r.text);

  // 9. ładuje się: „pełna ok. …”, SOC → 100%, moc; ma pierwszeństwo przed planem
  r = await run({ soc: 40, batt: -1500, plan: { start: inH(5), stop: inH(9) } });
  ok('ładuje się: etykieta', /ładuje się/.test(r.label), r.label);
  ok('ładuje się: „pełna ok.” i „40% → 100%”', r.text.includes('pełna ok.') && r.text.includes('40% → 100%'), r.text);
  ok('ładuje się: moc 1,50 kW', r.text.includes('1,50 kW'), r.text);
  ok('ładuje się: czas 40 min–4 h (6 kWh / 1,5 kW = 4 h)', r.text.includes('jeszcze 4 h 00 min'), r.text);

  // 10. naładowana
  r = await run({ soc: 100, batt: 0, load: 500 });
  ok('naładowana: etykieta', /naładowana/.test(r.label), r.label);
  ok('naładowana: „wystarczy na …”', /wystarczy na/.test(r.text), r.text);

  // 11. SOC poniżej progu: czerwony, bez komunikatu o braku planu
  r = await run({ soc: 18, batt: 300, plan: 'none' });
  ok('poniżej progu: „≤ 20%”', r.text.includes('≤ 20%'), r.text);
  ok('poniżej progu: czerwony', r.html.includes('var(--red)'), r.html.slice(0, 300));

  // 12. pasek SOC odpowiada stanowi baterii
  r = await run({ soc: 23, batt: 443 });
  ok('pasek: szerokość 23%', /width:23%/.test(r.html), r.html.slice(0, 600));

  ok('bez błędów strony', errs.length === 0, errs);
  console.log(fails ? `FAILS ${fails}` : 'ALL OK'); await b.close();
})();
