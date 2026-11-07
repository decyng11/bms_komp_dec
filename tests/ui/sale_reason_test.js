// 0.8.8: „Sprzedaż z baterii” w planie pokazuje konkretną przyczynę z planera zamiast ogólnego „brak opłacalnych godzin”
const { openCard, chromium } = require('./ui_env');
const { seed, curve, tab, sr } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
(async () => {
  const b = await chromium.launch();
  const noSale = () => { const c = curve(); c.sale = c.sale.map(() => 0); return c; };
  const sale = (e) => sr(e, '#exPlanBox').then((t) => (t.match(/Sprzedaż z baterii:[^📈]*/) || [''])[0]);
  const REASON = 'Pomiń — okno 1 h: po sprzedaży 18–19 (~5.0 kWh przy 5.0 kW) bateria spadłaby do ~12% przed świtem (PV pokryje dom dopiero ok. 09:00; min. 20%) — brakuje ~0.8 kWh';

  // 1. przyczyna z planera widoczna
  let e = await openCard(b, {});
  await seed(e, { curve: noSale(), proposals: { bateria_sprzedaz_start_2: { label: 'Start sprzedaży 2', current: '18:00', proposed: null, skip: true, reason: REASON } } });
  await tab(e, 'ems');
  await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('#exPlanCv'), null, { timeout: 8000 });
  let t = await sale(e);
  ok(/nie planuję/.test(t) && /okno 1 h: po sprzedaży 18–19/.test(t) && /brakuje ~0\.8 kWh/.test(t), 'przyczyna z liczbami: ' + t);
  ok(!/brak opłacalnych godzin/.test(t), 'stary ogólny opis zniknął');

  // 2. dwie różne przyczyny → obie; takie same → raz
  e = await openCard(b, {});
  await seed(e, { curve: noSale(), proposals: {
    bateria_sprzedaz_start: { skip: true, proposed: null, reason: 'Pomiń — brak cen RCE dziś.' },
    bateria_sprzedaz_start_2: { skip: true, proposed: null, reason: 'Pomiń — brak cen RCE dziś.' } } });
  await tab(e, 'ems');
  await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('#exPlanCv'), null, { timeout: 8000 });
  t = await sale(e);
  ok((t.match(/brak cen RCE dziś/g) || []).length === 1, 'identyczne przyczyny nie dublują się: ' + t);

  // 3. bez przyczyn (starszy backend) → stary opis
  e = await openCard(b, {});
  await seed(e, { curve: noSale(), proposals: { bateria_sprzedaz_start_2: { skip: true, proposed: null } } });
  await tab(e, 'ems');
  await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('#exPlanCv'), null, { timeout: 8000 });
  t = await sale(e);
  ok(/brak opłacalnych godzin/.test(t), 'bez przyczyny: stary opis: ' + t);

  // 4. HTML w przyczynie jest escapowany
  e = await openCard(b, {});
  await seed(e, { curve: noSale(), proposals: { bateria_sprzedaz_start_2: { skip: true, proposed: null, reason: 'Pomiń — <img src=x onerror="window.__pwn=1">' } } });
  await tab(e, 'ems');
  await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('#exPlanCv'), null, { timeout: 8000 });
  ok(await e.q(() => !__el.shadowRoot.querySelector('#exPlanBox img') && !window.__pwn), 'przyczyna jest escapowana (brak wstrzyknięcia HTML)');

  // 5. gdy sprzedaż jest zaplanowana → bez zmian (godziny, nie przyczyna)
  e = await openCard(b, {});
  await seed(e, { curve: curve(), proposals: { bateria_sprzedaz_start_2: { skip: true, proposed: null, reason: 'Pomiń — coś' } } });
  await tab(e, 'ems');
  await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('#exPlanCv'), null, { timeout: 8000 });
  t = await sale(e);
  ok(/\d\d:00–\d\d:00/.test(t) && !/nie planuję/.test(t), 'zaplanowana sprzedaż: godziny: ' + t);

  // 6. obniżona moc widoczna przy oknie sprzedaży (okno 18:00 z krzywej curve())
  e = await openCard(b, {});
  await seed(e, { curve: curve() });
  await e.q(() => { __states['sensor.bms_plan_curve'].attributes.assumptions = { sale_windows: [{ day: 0, start: 18, stop: 20, power_w: 1600 }] }; __el.hass = __mk(); });
  await tab(e, 'ems');
  await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('#exPlanCv'), null, { timeout: 8000 });
  t = await sale(e);
  ok(/18:00–20:00/.test(t) && /moc obniżona do 1,6 kW/.test(t), 'obniżona moc przy oknie: ' + t);
  e = await openCard(b, {});
  await seed(e, { curve: curve() });
  await e.q(() => { __states['sensor.bms_plan_curve'].attributes.assumptions = { sale_windows: [{ day: 0, start: 18, stop: 20, power_w: null }] }; __el.hass = __mk(); });
  await tab(e, 'ems');
  await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('#exPlanCv'), null, { timeout: 8000 });
  t = await sale(e);
  ok(/18:00–20:00/.test(t) && !/obniżona/.test(t), 'pełna moc: bez dopisku: ' + t);

  console.log(fails ? `FAILS ${fails}` : 'ALL OK'); await b.close(); process.exit(fails ? 1 : 0);
})();
