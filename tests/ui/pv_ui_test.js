// 0.8.1: karta bierze prognozę PV z integracji (Solcast albo Forecast.Solar), linia założeń pod planem
const { openCard, chromium } = require('./ui_env');
const { seed, curve, REPORT, HEALTH, tab, sr } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  await seed(e, { curve: curve(), report: REPORT(), health: HEALTH });
  const dk = await e.q(() => { const d = new Date(); const f = (x) => `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`; const t = new Date(d); t.setDate(d.getDate() + 1); return [f(d), f(t)]; });
  const HT = Array.from({ length: 24 }, (_, h) => (h >= 8 && h <= 15 ? 0.9 : 0));
  const HM = Array.from({ length: 24 }, (_, h) => (h >= 8 && h <= 15 ? 1.4 : 0));
  await e.q(([dk, HT, HM]) => {
    const r = window.__states['sensor.bms_reserve_soc'];
    Object.assign(r.attributes, { pv_forecast_source: 'Forecast.Solar', pv_hourly_today: HT, pv_hourly_tomorrow: HM,
      pv_daily: [{ date: dk[0], kwh: 7.2 }, { date: dk[1], kwh: 11.2 }, { date: 'x', kwh: null }, { date: 'x', kwh: null }, { date: 'x', kwh: null }, { date: 'x', kwh: null }, { date: 'x', kwh: null }] });
    delete window.__states['sensor.solcast_pv_forecast_forecast_today'];
    window.__el.hass = window.__mk();
  }, [dk, HT, HM]);
  const r = await e.q(() => ({ d0: __el._pvDayKwh(0), d1: __el._pvDayKwh(1), d3: __el._pvDayKwh(3), h: __el._getPvForecastHourly(), m: __el._pvHourlyMap(), src: __el._pvSourceLabel() }));
  ok(r.d0 === 7.2 && r.d1 === 11.2 && r.d3 === null, 'sumy dzienne z integracji (dziś 7,2, jutro 11,2, dzień 4 brak)');
  ok(Array.isArray(r.h) && r.h[10] === 0.9 && r.h[2] === 0, 'prognoza godzinowa dziś z integracji');
  ok(r.m[`${dk[1]}|10`] === 1.4 && r.m[`${dk[0]}|10`] === 0.9, 'mapa godzinowa dziś i jutro (do ETA)');
  ok(r.src === 'Forecast.Solar', 'źródło prognozy');
  // stara integracja bez atrybutów → dawne encje Solcast
  const old = await e.q(() => { const r = window.__states['sensor.bms_reserve_soc']; const keep = r.attributes.pv_daily; delete r.attributes.pv_daily;
    window.__states['sensor.solcast_pv_forecast_forecast_today'] = { state: '5.5', attributes: {} }; window.__el.hass = window.__mk();
    const v = __el._pvDayKwh(0); r.attributes.pv_daily = keep; delete window.__states['sensor.solcast_pv_forecast_forecast_today']; window.__el.hass = window.__mk(); return v; });
  ok(old === 5.5, 'bez atrybutów integracji: dawne encje Solcast (zgodność wstecz)');
  // zakładka EMS: linia założeń planu
  await e.q(() => { const p = window.__states['sensor.bms_plan_curve']; p.attributes.assumptions = { load_rest_today_kwh: 2.1, load_today_source: 'tempo dnia', load_tomorrow_kwh: 6.0, pv_tomorrow_kwh: 11.2, pv_source: 'Forecast.Solar', pv_hourly_tomorrow: true }; p.attributes.generated_at = '2026-11-03T15:55:00+01:00'; window.__el.hass = window.__mk(); });
  await tab(e, 'ems'); await sleep(900);
  let t = await sr(e, '#exPlanBox');
  ok(/Plan zakłada: zużycie do północy ~2,1 kWh \(z dzisiejszego zużycia\) · jutro 6,0 kWh · PV jutro 11,2 kWh \(Forecast\.Solar\)/.test(t), 'plan: linia założeń: ' + (t.match(/Plan zakłada[^.]*\./) || [''])[0]);
  ok(!/Brak godzinowej prognozy PV/.test(t), 'plan: bez ostrzeżenia, gdy prognoza godzinowa jest');
  await e.q(() => { const p = window.__states['sensor.bms_plan_curve']; p.attributes.assumptions = { load_rest_today_kwh: 2.1, load_today_source: 'profil', load_tomorrow_kwh: 6.0, pv_tomorrow_kwh: 8, pv_source: null, pv_hourly_tomorrow: false }; p.attributes.generated_at = '2026-11-03T15:58:00+01:00'; window.__el.hass = window.__mk(); });
  await tab(e, 'main'); await tab(e, 'ems'); await sleep(900);
  t = await sr(e, '#exPlanBox');
  ok(/Brak godzinowej prognozy PV na jutro/.test(t) && /\(z profilu\)/.test(t), 'plan: ostrzeżenie o braku prognozy godzinowej');
  await e.q(() => { const p = window.__states['sensor.bms_plan_curve']; p.attributes.assumptions = { load_rest_today_kwh: '<img src=x onerror=window.__pwn=1>', pv_source: '<img src=x onerror=window.__pwn=1>', pv_tomorrow_kwh: 1, pv_hourly_tomorrow: true }; p.attributes.generated_at = '2026-11-03T15:59:00+01:00'; window.__el.hass = window.__mk(); });
  await tab(e, 'main'); await tab(e, 'ems'); await sleep(900);
  ok(await e.q(() => !__el.shadowRoot.querySelector('#exPlanBox img') && !window.__pwn), 'plan: brak wstrzyknięcia HTML z założeń');
  ok(e.errs.length === 0, 'brak błędów JS ' + JSON.stringify(e.errs));
  await b.close();
  console.log(fails ? `FAILS ${fails}` : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
