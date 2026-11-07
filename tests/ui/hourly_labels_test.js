// Wartości (Wh) nad słupkami wykresów godzinowych: 24 napisy, zgodne z tabelą; poziomo na szerokim ekranie, pionowo (obrót) na wąskim
const { chromium } = require('playwright'); const fs = require('fs');
const js = fs.readFileSync(require('path').resolve(__dirname, '../../custom_components/bms_komp_dec/frontend') + '/bms-panel.js', 'utf8');
const F = [0.23, 0.40, 0.33, 0.25, 0.24, 0.25, 0.31, 0.43, 0.38, 0.37, 0.29, 0.22, 0.28, 0.22, 0.27, 0.22, 0.33, 0.55, 0.44, 0.32, 0.31, 0.26, 0.18, 0.18];
(async () => {
  const b = await chromium.launch(); let fails = 0; const errs = [];
  const ok = (n, c, x) => { if (!c) { fails++; console.log('FAIL', n, x === undefined ? '' : JSON.stringify(x).slice(0, 400)); } };
  for (const [width, horiz] of [[1170, true], [390, false]]) {
    const page = await (await b.newContext({ viewport: { width: width + 20, height: 900 } })).newPage();
    page.on('pageerror', e => errs.push(e.message));
    await page.route('**/*', r => /^(data|about):/.test(r.request().url()) ? r.continue() : r.abort());
    await page.setContent(`<body style="margin:0;background:#000"><div id="host" style="width:${width}px;margin:10px"></div></body>`);
    await page.evaluate(() => { window.Chart = class { constructor() {} destroy() {} }; window.Chart._adapters = { _date: class { formats() { return {}; } } }; });
    await page.addScriptTag({ content: js });
    const r = await page.evaluate(([F]) => {
      const S = (s, a = {}) => ({ state: String(s), attributes: a, last_updated: 'x' });
      const hass = { states: { 'sensor.bms_soc': S(75), 'sensor.bms_reserve_soc': S(48, { capacity_kwh: 10 }),
        'sensor.bms_load_forecast': S(9, { profiles_days: 16, history_days: 41, hourly_forecast_today: F, hourly_forecast: F }) }, entities: {}, language: 'pl', callService: () => Promise.resolve(), callWS: async () => ({}) };
      const el = document.createElement('bms-panel-card'); el.setConfig({ type: 'custom:bms-panel-card' }); document.getElementById('host').appendChild(el);
      el.hass = hass; el.shadowRoot.querySelector('[data-tab=charts]').click();
      const P = CanvasRenderingContext2D.prototype; const texts = []; let rot = 0; const of = P.fillText, or = P.rotate;
      P.fillText = function (t, ...a) { texts.push(String(t)); return of.call(this, t, ...a); };
      P.rotate = function (...a) { rot++; return or.apply(this, a); };
      el._lastHourlyFcKey = null; el._renderHourlyForecastChart();
      P.fillText = of; P.rotate = or;
      return { texts, rot };
    }, [F]);
    const wh = F.map(v => String(Math.round(v * 100) * 10));
    // dwa wykresy (dziś i jutro) → każda z 24 wartości pojawia się co najmniej dwa razy
    const count = (t) => r.texts.filter(x => x === t).length;
    ok(`${width}px: wszystkie 24 wartości narysowane na obu wykresach`, wh.every(t => count(t) >= 2), wh.filter(t => count(t) < 2));
    ok(`${width}px: 230 (godz. 00) z poprawnego Wh`, r.texts.includes('230'));
    if (horiz) ok('szeroko: napisy poziomo (bez obrotu)', r.rot === 0, r.rot);
    else ok('wąsko: napisy pionowo (48 obrotów = 2 wykresy × 24)', r.rot === 48, r.rot);
  }
  ok('bez błędów strony', errs.length === 0, errs);
  console.log(fails ? `FAILS ${fails}` : 'ALL OK'); await b.close();
})();
