// 0.8.1: zakładka „Urządzenia” — kafelki, wykresy 1d–12m, ranking, porównanie, pomieszczenia, mapa godzin, plan, edytor, CSV
const { openCard, chromium } = require('./ui_env');
const { tab, sr } = require('./extras_helpers');
const fs = require('fs');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const PAY = JSON.parse(fs.readFileSync('devices_payload.json', 'utf8'));
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  await e.q((pay) => {
    window.__svc = window.__svc || {}; window.__dvSet = []; window.__dvGet = 0;
    window.__svc['bms_komp_dec.devices_get'] = () => { window.__dvGet++; return { response: JSON.parse(JSON.stringify(pay)) }; };
    window.__svc['bms_komp_dec.devices_set'] = (m) => { const d = (m.service_data || m).devices; window.__dvSet.push(d); return { response: { devices: d, dropped: 0 } }; };
    const S = (v, a) => ({ state: String(v), attributes: a || {}, last_updated: 'x' });
    window.__states['sensor.bms_devices'] = S(3, { devices: pay.live, power_total: 1660 });
    window.__states['sensor.pralka_moc'] = S(1500, { unit_of_measurement: 'W' });
    window.__states['sensor.pralka_energia'] = S(120.5, { unit_of_measurement: 'kWh' });
    window.__states['sensor.zmywarka_moc'] = S(0, { unit_of_measurement: 'W' });
    // statystyki HA: pompa ciepła ma dane sprzed roku (change kWh dziennie)
    const mk0 = window.__mk;
    window.__mk = () => { const h = mk0(); const cw = h.callWS; h.callWS = async (m) => {
      if (m.type === 'recorder/statistics_during_period') { const out = {}; const t0 = new Date(m.start_time).getTime();
        m.statistic_ids.forEach((id) => { out[id] = []; for (let i = 0; i < 400; i++) out[id].push({ start: t0 + i * 86400000, change: id === 'sensor.pc_energia' ? 20 : null, mean: id === 'sensor.tv' ? 50 : null }); });
        window.__statReq = m; return out; }
      return cw(m); }; return h; };
    window.__el.hass = window.__mk();
  }, PAY);
  await tab(e, 'dev'); await sleep(1200);
  const t = await sr(e, '#devRoot');
  ok(t && /Pralka/.test(t) && /Pompa ciepła/.test(t) && /pracuje/.test(t), 'kafelki: urządzenia, „pracuje”');
  ok(await e.q(() => !__el.shadowRoot.querySelector('#devRoot img') && !window.__pwn), 'nazwa z HTML zescape-owana');
  ok(await e.q(() => window.__statReq && window.__statReq.period === 'day' && window.__statReq.statistic_ids.includes('sensor.pc_energia') && window.__statReq.statistic_ids.includes('sensor.tv')), 'statystyki HA: energia albo moc dla każdego urządzenia');
  for (const r of ['1d', '7d', '30d', '3m', '6m', '12m']) {
    await e.q((r) => __el.shadowRoot.querySelector(`[data-dv="range"][data-r="${r}"]`).click(), r); await sleep(150);
    const info = await e.q(() => { const R = __el.shadowRoot.querySelector('#devRoot'); return { bars: R.querySelectorAll('.chart-card div[title*="kWh"]').length, note: (R.textContent.match(/Jednostka: ([^.]+)/) || [])[1] }; });
    const unit = { '1d': 'kWh/h', '7d': 'kWh/dzień', '30d': 'kWh/dzień', '3m': 'kWh/tydzień', '6m': 'kWh/tydzień', '12m': 'kWh/miesiąc' }[r];
    ok(info.bars > 0 && info.note === unit, `zakres ${r}: wykres (${info.bars} elementów, ${info.note})`);
  }
  // 12 mies.: pompa ciepła — dni sprzed danych integracji ze statystyk (20 kWh/dzień)
  const leg = await sr(e, '.dv-leg');
  const m = (leg || '').match(/Pompa ciepła ([\d\s,]+) kWh/);
  const hpTotal = m ? Number(m[1].replace(/\s/g, '').replace(',', '.')) : 0;
  ok(hpTotal > 6000, '12 mies.: historia pompy uzupełniona ze statystyk HA (' + hpTotal + ' kWh)');
  ok(/reszta domu/.test(leg), 'wszystkie: „reszta domu” w legendzie');
  // filtr: jedno urządzenie, pomieszczenie
  await e.q(() => { const s = __el.shadowRoot.querySelector('[data-dv="filter"]'); s.value = 'room:Łazienka'; s.dispatchEvent(new Event('change', { bubbles: true })); }); await sleep(200);
  let lg = await sr(e, '.dv-leg');
  ok(/Pralka/.test(lg) && !/Pompa/.test(lg) && !/reszta/.test(lg), 'filtr pomieszczenia');
  await e.q(() => __el.shadowRoot.querySelector('[data-dv="range"][data-r="30d"]').click()); await sleep(150);
  await e.q(() => { const s = __el.shadowRoot.querySelector('[data-dv="filter"]'); s.value = 'w'; s.dispatchEvent(new Event('change', { bubbles: true })); }); await sleep(200);
  const heat = await e.q(() => __el.shadowRoot.querySelectorAll('.dv-heat .c').length);
  ok(heat === 14 * 24, 'mapa godzin dla jednego urządzenia (14 × 24)');
  const tbl = await sr(e, '.dv-tbl');
  ok(/1,5 W/.test(tbl) && /12 × śr\. 0,90 kWh/.test(tbl) && /PV 30%/.test(tbl) && /7,50 zł/.test(tbl), 'ranking: czuwanie, cykle, źródła, oszczędność');
  const all = await sr(e, '#devRoot');
  ok(/Ten sam miesiąc rok temu/.test(all), 'porównanie miesięcy');
  ok(/najlepiej 13:00–14:00/.test(all) && /Nierozpoznany odbiornik/.test(all) && /używana/.test(all), 'plan, nierozpoznany odbiornik, prognoza z podziałem');
  // CSV
  await e.q(() => { window.__dl = null; const o = HTMLAnchorElement.prototype.click; HTMLAnchorElement.prototype.click = function () { window.__dl = this.download; }; });
  await e.q(() => __el.shadowRoot.querySelector('[data-dv="csv"]').click()); await sleep(200);
  ok(await e.q(() => /^bms-urzadzenia-30d-/.test(window.__dl || '')), 'CSV: plik do pobrania');
  // edytor: nowe urządzenie
  await e.q(() => { const s = __el.shadowRoot.querySelector('[data-dv="filter"]'); s.value = 'all'; s.dispatchEvent(new Event('change', { bubbles: true })); });
  await e.q(() => __el.shadowRoot.querySelector('[data-dv="add"]').click()); await sleep(200);
  ok(await e.q(() => __el.shadowRoot.querySelectorAll('[data-dvf="category"] optgroup').length >= 9), 'edytor: kategorie w grupach');
  await e.q(() => { const R = __el.shadowRoot; const c = R.querySelector('[data-dvf="category"]'); c.value = 'dishwasher'; c.dispatchEvent(new Event('change', { bubbles: true })); });
  await sleep(150);
  ok(await e.q(() => { const R = __el.shadowRoot; return R.querySelector('[data-dvf="name"]').value === 'Zmywarka' && R.querySelector('[data-dvf="cycles"]').checked && R.querySelector('[data-dvf="flexible"]').checked && R.querySelector('[data-dvf="cycle_end_min"]').value === '15'; }), 'kategoria ustawia domyślne (Zmywarka: cykle, elastyczna, 15 min)');
  ok(await e.q(() => Array.from(__el.shadowRoot.querySelectorAll('#dvPw option')).some((o) => o.value === 'sensor.zmywarka_moc') && !Array.from(__el.shadowRoot.querySelectorAll('#dvPw option')).some((o) => o.value === 'sensor.pralka_energia')), 'podpowiedzi encji: W osobno, kWh osobno');
  await e.q(() => __el.shadowRoot.querySelector('[data-dv="save"]').click()); await sleep(150);
  ok(/Wskaż encję/.test(await sr(e, '#dvMsg')), 'zapis bez encji → komunikat');
  await e.q(() => { const R = __el.shadowRoot; R.querySelector('[data-dvf="power_eid"]').value = 'light.lampa'; });
  await e.q(() => __el.shadowRoot.querySelector('[data-dv="save"]').click()); await sleep(150);
  ok(/sensor\.nazwa_encji/.test(await sr(e, '#dvMsg')), 'zła encja → komunikat');
  await e.q(() => { const R = __el.shadowRoot; R.querySelector('[data-dvf="power_eid"]').value = 'sensor.zmywarka_moc'; R.querySelector('[data-dvf="room"]').value = 'Kuchnia'; R.querySelector('[data-dvf="name"]').value = 'Zmywarka Bosch'; });
  await e.q(() => __el.shadowRoot.querySelector('[data-dv="save"]').click()); await sleep(600);
  const saved = await e.q(() => window.__dvSet[0]);
  ok(saved && saved.length === 4 && saved[3].name === 'Zmywarka Bosch' && saved[3].power_eid === 'sensor.zmywarka_moc' && saved[3].room === 'Kuchnia' && saved[3].category === 'dishwasher' && !('_new' in saved[3]), 'zapis: lista z nowym urządzeniem');
  // edycja i usunięcie
  await e.q(() => __el.shadowRoot.querySelector('[data-dv="edit"][data-id="tv"]').click()); await sleep(150);
  await e.q(() => { window.confirm = () => true; __el.shadowRoot.querySelector('[data-dv="del"]').click(); }); await sleep(500);
  const del = await e.q(() => window.__dvSet[1]);
  ok(del && del.length === 2 && !del.some((d) => d.id === 'tv'), 'usunięcie urządzenia');
  ok(e.errs.length === 0, 'brak błędów JS ' + JSON.stringify(e.errs));
  const el = await e.page.evaluateHandle(() => __el.shadowRoot.querySelector('#devRoot'));
  await e.page.setViewportSize({ width: 1100, height: 1600 }); await sleep(200);
  await e.q(() => __el.shadowRoot.querySelector('[data-dv="range"][data-r="30d"]').click()); await sleep(300);
  await el.screenshot({ path: 'devices.png' });
  // użytkownik bez uprawnień: bez dodawania i edycji
  const e2 = await openCard(b, {});
  await e2.q((pay) => { window.__admin = false; window.__svc = { 'bms_komp_dec.devices_get': () => ({ response: pay }) }; window.__el.hass = window.__mk(); }, PAY);
  await tab(e2, 'dev'); await sleep(900);
  ok(await e2.q(() => !__el.shadowRoot.querySelector('[data-dv="add"]') && !__el.shadowRoot.querySelector('[data-dv="edit"]') && /Pralka/.test(__el.shadowRoot.querySelector('#devRoot').textContent)), 'zwykły użytkownik: podgląd bez dodawania i edycji');
  await b.close(); console.log(fails ? `FAILS ${fails}` : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
