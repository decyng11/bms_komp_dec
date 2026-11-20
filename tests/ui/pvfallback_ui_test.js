// Zapasowa prognoza PV: kafelki pogody z oznaczeniem „szac.”, podpowiedź i podpis źródła w „Plan zakłada”
const { openCard, chromium } = require('./ui_env');
const { seed, curve, tab, sr } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  await seed(e, { curve: curve() });
  await e.q(() => {
    const day = (o, v) => { const d = new Date(); d.setDate(d.getDate() + o); const k = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); return Object.assign({ date: k }, v); };
    const st = __states['sensor.bms_reserve_soc'];
    st.attributes.pv_forecast_source = 'zapasowa: szacunek z ostatnich 5 dni × 0,8';
    st.attributes.pv_fallback = { offsets: [0, 1], days: 5, caution: 0.8, label: 'szacunek z ostatnich 5 dni × 0,8' };
    st.attributes.pv_hourly_today = Array.from({ length: 24 }, (_, h) => (h >= 9 && h < 15 ? 0.4 : 0));
    st.attributes.pv_hourly_tomorrow = Array.from({ length: 24 }, (_, h) => (h >= 9 && h < 15 ? 0.4 : 0));
    st.attributes.pv_daily = [day(0, { kwh: 2.4, est: true }), day(1, { kwh: 2.4, est: true }), day(2, { kwh: 8.1, raw: 9.0, factor: 0.9, n: 12 }),
      day(3, { kwh: null }), day(4, { kwh: 5.0 }), day(5, { kwh: 5.0 }), day(6, { kwh: 5.0 })];
    const pc = __states['sensor.bms_plan_curve'];
    pc.attributes.assumptions = { load_rest_today_kwh: 4.2, load_today_source: 'tempo dnia', load_tomorrow_kwh: 11, pv_tomorrow_kwh: 2.4, pv_source: 'zapasowa: szacunek z ostatnich 5 dni × 0,8', pv_fallback: true, pv_hourly_tomorrow: true, pv_factor: 1, wear_cost: 0 };
    __el.hass = __mk();
  });
  ok(await e.q(() => __el._pvRange(0)) === '<div class="pv-rng" data-role="pv-est">szac.</div>', 'zakres zastąpiony napisem „szac.”');
  ok(await e.q(() => __el._pvRange(2)) === '', 'prawdziwa prognoza bez zakresu → bez zmian');
  const tip = await e.q(() => __el._pvTip(0));
  ok(/Brak prognozy PV — szacunek/.test(tip) && /ostatnich 5 dni/.test(tip) && /0,8/.test(tip) && /nie jest prognoza pogody/.test(tip), 'podpowiedź: skąd szacunek: ' + tip);
  ok(/korekta|surowa/.test(await e.q(() => __el._pvTip(2))), 'prawdziwa prognoza zachowuje dawną podpowiedź');
  await e.q(() => {
    const base = new Date();
    __el._weatherError = null;
    __el._weatherForecast = [0, 1, 2].map((i) => ({ datetime: new Date(base.getTime() + i * 86400000).toISOString(), condition: 'sunny', temperature: 8, templow: 2 }));
    __el._lastWeatherKey = null; __el._renderWeather();
  });
  const wx = await e.q(() => __el.shadowRoot.getElementById('weatherContainer').innerText.replace(/\s+/g, ' '));
  ok(/~2\.4 kWh szac\./.test(wx) && /8\.1 kWh/.test(wx) && !/~8\.1/.test(wx), 'kafelki: ~2.4 kWh szac. dla szacunku, zwykła wartość dla prognozy: ' + wx);
  ok(/zapasowa: szacunek z ostatnich 5 dni/.test(await e.q(() => __el._pvSourceLabel())), 'podpis źródła prognozy');
  // „Plan zakłada” pokazuje źródło
  await tab(e, 'ems'); await sleep(900);
  ok(/PV jutro 2,4 kWh \(zapasowa: szacunek z ostatnich 5 dni × 0,8\)/.test(await sr(e, '#exPlanBox')), 'plan zakłada: PV jutro z podpisem „zapasowa”');
  // znika, gdy prognoza wraca
  await e.q(() => { const a = __states['sensor.bms_reserve_soc'].attributes; delete a.pv_fallback; a.pv_daily.forEach((d) => { delete d.est; }); __el.hass = __mk(); });
  ok(await e.q(() => __el._pvRange(0)) === '' && !/title="Brak prognozy/.test(await e.q(() => __el._pvTip(0))), 'po powrocie prognozy brak oznaczenia szacunku');
  ok(e.errs.length === 0, 'brak błędów JS ' + JSON.stringify(e.errs));
  await b.close();
  console.log(fails ? 'FAILS ' + fails : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
