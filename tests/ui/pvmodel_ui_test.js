// 0.9.1: prognoza PV po korekcie — kafelki pogody (suma, zakres, podpowiedź), godzinowa mapa i tabela trafności per horyzont
const { openCard, chromium } = require('./ui_env');
const { seed, curve, tab } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  await seed(e, { curve: curve() });
  const iso = (o) => { const d = new Date(); d.setDate(d.getDate() + o); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };
  await e.q((iso0) => {
    const day = (o, v) => { const d = new Date(); d.setDate(d.getDate() + o); const k = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); return Object.assign({ date: k }, v); };
    const st = __states['sensor.bms_reserve_soc'];
    st.attributes.pv_forecast_source = 'Solcast';
    st.attributes.pv_hourly_today = Array.from({ length: 24 }, (_, h) => (h >= 9 && h < 15 ? 1.0 : 0));
    st.attributes.pv_hourly_today_adj = Array.from({ length: 24 }, (_, h) => (h >= 9 && h < 15 ? 0.7 : 0));
    st.attributes.pv_hourly_tomorrow = Array.from({ length: 24 }, (_, h) => (h >= 9 && h < 15 ? 1.0 : 0));
    st.attributes.pv_daily = [day(0, { kwh: 4.2, raw: 6.0, factor: 0.7, n: 12, lo: 3.6, hi: 4.8, range: 'historia' }),
      day(1, { kwh: 9.0, raw: 10.0, factor: 0.9, n: 12, lo: 7.4, hi: 10.6, range: 'szac.' }),
      day(2, { kwh: 8.1, raw: 9.0, factor: 0.9, n: 12 }), day(3, { kwh: null, raw: null }), day(4, { kwh: 5.0 }), day(5, { kwh: 5.0 }), day(6, { kwh: 5.0 })];
    __el.hass = __mk();
  }, iso(0));
  const info = await e.q(() => [0, 1, 2, 3].map((i) => __el._pvDayInfo(i)));
  ok(info[1] && info[1].kwh === 9 && info[1].raw === 10, 'karta czyta sumy po korekcie (kwh) i surową (raw)');
  ok(await e.q(() => __el._pvDayKwh(1)) === 9, 'pasek planu bierze wartość po korekcie');
  const hm = await e.q(() => { const m = __el._pvHourlyMap(); const k = Object.keys(m).find((x) => /\|10$/.test(x)); return [k, m[k]]; });
  ok(hm[1] === 0.7, 'mapa godzinowa dziś używa prognozy po korekcie (0,7 zamiast 1,0): ' + hm);
  ok(await e.q(() => __el._pvRange(1)) === '<div class="pv-rng">7,4–10,6</div>', 'zakres jutro: 7,4–10,6');
  ok(await e.q(() => __el._pvRange(2)) === '', 'bez zakresu — brak linii');
  const tip = await e.q(() => __el._pvTip(1));
  ok(/surowa prognoza 10,0 kWh/.test(tip) && /×0,90 z 12 dni/.test(tip) && /szacunkowy/.test(tip), 'podpowiedź: surowa, współczynnik, źródło zakresu: ' + tip);
  ok(/z historii błędów/.test(await e.q(() => __el._pvTip(0))), 'podpowiedź dla zakresu z historii');
  // kafelki pogody
  await e.q(() => {
    const base = new Date();
    __el._weatherError = null;
    __el._weatherForecast = [0, 1, 2, 3].map((i) => ({ datetime: new Date(base.getTime() + i * 86400000).toISOString(), condition: 'sunny', temperature: 8, templow: 2 }));
    __el._lastWeatherKey = null; __el._renderWeather();
  });
  const wx = await e.q(() => __el.shadowRoot.getElementById('weatherContainer').innerText.replace(/\s+/g, ' '));
  ok(/4\.2 kWh/.test(wx) && /9\.0 kWh/.test(wx) && /7,4–10,6/.test(wx), 'kafelki: suma po korekcie i zakres: ' + wx);
  // starsza integracja (bez pv_daily): bez błędu
  await e.q(() => { delete __states['sensor.bms_reserve_soc'].attributes.pv_daily; __el.hass = __mk(); });
  ok(await e.q(() => __el._pvDayInfo(1)) === null && await e.q(() => __el._pvRange(1)) === '', 'bez pv_daily: brak błędu, brak zakresu');

  // tabela trafności per horyzont (zakładka „Zysk i log”)
  const ac = {
    days: [], pv: { mape: 20, bias: 5, n: 10 }, load: { mape: 10, bias: 0, n: 10 }, soc: { mae: 4, n: 10 }, pv_correction: { factor: 0.85, days: 12, ratio: 0.84 },
    pv_by_horizon: [0, 1, 2, 3, 4, 5, 6].map((h) => ({ h, n: h < 3 ? 12 : 0, mape: h < 3 ? 20 + h * 5 : null, bias: 3, n_adj: h < 3 ? 8 : 0, mape_adj: h < 3 ? 14 + h * 4 : null, factor: 0.85, ratio: 0.84, spread: 0.12 + 0.06 * h })),
  };
  await tab(e, 'log'); await sleep(800);
  await e.page.waitForFunction(() => typeof __el._exAccHtml === 'function', null, { timeout: 8000 });
  const html = await e.q((ac) => { const ex = __el; ex._exS().ins.data = { accuracy: ac, pv_correction_on: true, savings: {} }; return ex._exAccHtml(); }, ac);
  ok(/data-role="pv-horizon"/.test(html), 'tabela horyzontów jest');
  ok(/dziś/.test(html) && /jutro/.test(html) && /za 6 dni/.test(html), 'wiersze: dziś, jutro, za N dni');
  ok(/× 0,85/.test(html) && /± 12%/.test(html) && /± 48%/.test(html), 'korekta i zakres w tabeli');
  ok((html.match(/>—</g) || []).length >= 4, 'horyzonty bez danych po korekcie mają myślnik');
  const html0 = await e.q((ac) => { const x = Object.assign({}, ac); delete x.pv_by_horizon; __el._exS().ins.data = { accuracy: x, pv_correction_on: true, savings: {} }; return __el._exAccHtml(); }, ac);
  ok(!/pv-horizon/.test(html0), 'starszy backend (bez pv_by_horizon): brak tabeli, brak błędu');
  await b.close();
  console.log(fails ? `FAILS ${fails}` : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
