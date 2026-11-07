// 0.8.8: „Trafność prognoz” pod wykresem planu (z atrybutu accuracy sensora monitor_status)
const { openCard, chromium } = require('./ui_env');
const { seed, curve, tab, sr } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
(async () => {
  const b = await chromium.launch();
  const open = async (acc) => {
    const e = await openCard(b, {});
    await seed(e, { curve: curve(), monitor: { alarms: [], low_soc_active: false, watches: [], accuracy: acc } });
    await e.q(() => { __states['sensor.bms_plan_curve'].attributes.assumptions = { load_rest_today_kwh: 6, load_today_source: 'tempo dnia', pv_hourly_tomorrow: true }; __el.hass = __mk(); });
    await tab(e, 'ems');
    await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('#exPlanCv'), null, { timeout: 8000 });
    return (await sr(e, '#exPlanBox')).match(/Trafność prognoz[^.]*\./)?.[0] || null;
  };
  let t = await open({ load: { n: 5, mae_pct: 8.2, bias_pct: 5.1 }, pv: { n: 4, mae_pct: 22.6, bias_pct: -18.0 }, days: [] });
  ok(t && /zużycie ±8%/.test(t) && /zwykle zawyżona o 5%/.test(t) && /PV ±23%/.test(t) && /zwykle zaniżona o 18%/.test(t) && /dni: 5/.test(t), 'linia z obiema prognozami: ' + t);
  t = await open({ load: { n: 3, mae_pct: 4, bias_pct: 1.0 }, pv: null, days: [] });
  ok(t && /zużycie ±4%/.test(t) && !/zwykle/.test(t) && !/PV/.test(t), 'małe odchylenie bez dopisku, bez PV: ' + t);
  t = await open({ load: null, pv: null, days: [] });
  ok(t === null, 'brak danych: linii nie ma: ' + t);
  t = await open(undefined);
  ok(t === null, 'starszy backend (bez atrybutu): linii nie ma: ' + t);
  console.log(fails ? `FAILS ${fails}` : 'ALL OK'); await b.close(); process.exit(fails ? 1 : 0);
})();
