// Dymki na własnych wykresach canvas (zużycie domu, prognoza 7 dni, godzinowe, produkcja PV)
const { openCard, chromium } = require('./ui_env');
const { tab } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  await tab(e, 'charts'); await sleep(500);
  await e.q(() => { ['chartLoadCons', 'chartForecast7d', 'chartHourlyToday', 'chartPvProd24h'].forEach((id) => { const c = __el.shadowRoot.getElementById(id); c.style.display = 'block'; let p = c.parentElement; while (p && p !== __el.shadowRoot) { if (getComputedStyle(p).display === 'none') p.style.display = 'block'; p = p.parentElement; } }); });
  await e.q(() => {
    const el = __el; const R = el.shadowRoot;
    const hrs = Array.from({ length: 24 }, (_, i) => (i >= 8 && i <= 15 ? 1.2 + i / 20 : 0));
    el._drawLoadConsumptionChart(R.getElementById('chartLoadCons'), [
      { label: 'Wczoraj', date: '2026-11-21', actual: 14.2, forecast: 11.4 },
      { label: 'Dziś', date: '2026-11-22', actual: 13.8, forecast: 10.4, nowcast: 16.2 },
      { label: 'Jutro', date: '2026-11-23', forecast: 12.0 }], { low: 8.1, high: 15.8 });
    el._drawForecast7dChart(R.getElementById('chartForecast7d'), [1, 2, 3, 4, 5, 6, 7].map((n) => ({ date: '2026-11-' + String(22 + n).padStart(2, '0'), forecast: n * 1.5 })));
    el._drawHourlyForecastChart(R.getElementById('chartHourlyToday'), hrs, hrs.map((v) => v * 0.8), 12);
    el._drawPvProductionChart(R.getElementById('chartPvProd24h'), hrs.map((v) => v * 0.9), hrs);
  });
  const hover = async (id, fx, fy) => {
    await e.q((id) => __el.shadowRoot.getElementById(id).scrollIntoView({ block: 'center' }), id);
    const r = await e.q((id) => { const q = __el.shadowRoot.getElementById(id).getBoundingClientRect(); return { l: q.left, t: q.top, w: q.width, h: q.height }; }, id);
    await e.page.mouse.move(r.l + r.w * fx, r.t + r.h * fy); await e.page.mouse.move(r.l + r.w * fx + 1, r.t + r.h * fy + 1); await sleep(120);
    return e.q(() => { const t = __el.shadowRoot.querySelector('.bms-tip'); return t && getComputedStyle(t).display !== 'none' ? t.textContent : null; });
  };
  const a = await hover('chartLoadCons', 0.55, 0.5);
  ok(a && /Dziś/.test(a) && /Rzeczywiste: 13,8 kWh/.test(a) && /Prognoza: 10,4 kWh/.test(a) && /Tempo dnia/.test(a), 'zużycie domu: dymek dla „Dziś”: ' + JSON.stringify(a));
  const j = await hover('chartLoadCons', 0.88, 0.5);
  ok(j && /Jutro/.test(j) && /Zakres: 8,1 kWh – 15,8 kWh/.test(j), 'zużycie domu: „Jutro” z zakresem: ' + JSON.stringify(j));
  const f = await hover('chartForecast7d', 0.3, 0.5);
  ok(f && /Prognoza: \d/.test(f) && /\d\d\.11/.test(f), 'prognoza 7 dni: dymek: ' + JSON.stringify(f));
  const h = await hover('chartHourlyToday', 0.5, 0.5);
  ok(h && /\d\d:00–\d\d:00/.test(h) && /Prognoza: \d+ Wh/.test(h) && /Rzeczywiste: \d+ Wh/.test(h), 'godzinowe: dymek: ' + JSON.stringify(h));
  const p = await hover('chartPvProd24h', 0.5, 0.5);
  ok(p && /Wykonanie: /.test(p) && /Prognoza: /.test(p), 'produkcja PV: dymek: ' + JSON.stringify(p));
  const off = await e.q(() => { const R = __el.shadowRoot; R.getElementById('chartLoadCons').scrollIntoView({ block: 'center' }); const q = R.getElementById('chartLoadCons').getBoundingClientRect(); return { x: q.left + 2, y: q.top + 2 }; });
  await e.page.mouse.move(off.x, off.y); await e.page.mouse.move(off.x + 1, off.y + 1); await sleep(120);
  ok(await e.q(() => getComputedStyle(__el.shadowRoot.querySelector('.bms-tip')).display === 'none'), 'poza obszarem słupków dymek znika');
  await b.close(); console.log(fails ? 'FAILS ' + fails : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
