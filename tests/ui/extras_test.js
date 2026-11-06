const { openCard, chromium, CARD } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

// ---- dane testowe: krzywa planu 24 h od 16:00 (wsz. tablice po 24 elementy)
function curve(opts = {}) {
  const n = 24, h0 = 16;
  const soc = [], floor = [], pv = [], load = [], buy = [], sell = [], peak = [], grid = [], sale = [], target = [];
  let s = 62;
  for (let i = 0; i < n; i++) {
    const h = (h0 + i) % 24;
    const isPeak = (h >= 6 && h < 13) || (h >= 15 && h < 22);
    const g = h >= 22 || h < 6;
    const sl = h === 18 || h === 19;
    if (sl) s -= 12; else if (g) s = Math.min(95, s + 18); else if (h >= 9 && h <= 15) s = Math.min(100, s + 9); else s -= 4;
    if (opts.low && i === 10) s = 26;
    s = Math.max(s, 5);
    soc.push(Math.round(s * 10) / 10); floor.push(25); pv.push(h >= 8 && h <= 16 ? 2.4 : 0); load.push(0.6 + (h === 19 ? 0.9 : 0));
    buy.push(isPeak ? 1.29 : 0.62); sell.push(opts.noSell ? null : (h === 19 ? 1.1 : (h === 13 ? -0.05 : 0.45)));
    peak.push(isPeak ? 1 : 0); grid.push(opts.noGrid ? 0 : (g ? 1 : 0)); sale.push(sl ? 1 : 0); target.push(g && !opts.noGrid ? 90 : null);
  }
  return { start: '2026-11-03T16:00:00+01:00', hours: n, soc_now: 62, soc, floor, pv, load, buy, sell, peak, grid, sale, target };
}
const REPORT = (o = {}) => Object.assign({
  year: 2026, month: 11, title: 'Listopad 2026', days_with_data: 3, days_in_month: 30, complete: false, revenue: 12.5, cost: 8.2, net: 4.3,
  export_kwh: 18.4, import_kwh: 14.1, neg_export_kwh: 0.6, avg_sell_price: 0.679, avg_buy_price: 0.58, pv_kwh: 52, load_kwh: 61,
  battery_charge_kwh: 24, battery_discharge_kwh: 21, self_consumption_pct: 65, self_sufficiency_pct: 77, saving_estimate: 35.7,
  best_day: { date: '2026-11-02', net: 2.4 }, worst_day: { date: '2026-11-01', net: -0.3 }, cycle_efficiency_pct: 88.5, cycle_efficiency_days: 2,
  days: [{ date: '2026-11-01', net: -0.3 }, { date: '2026-11-02', net: 2.4 }, { date: '2026-11-03', net: 2.2 }],
}, o);
const HEALTH = { eff_7d: 89.2, days_7d: 6, eff_30d: 88.1, days_30d: 20, eff_90d: 87.0, days_90d: 60, eff_trend_pp: 1.1, capacity_est_kwh: 9.6, capacity_samples: 11, capacity_configured_kwh: 10.0, soh_est_pct: 96 };

async function seed(e, o = {}) {
  await e.q((o) => {
    const S = (v, a) => ({ state: String(v), attributes: a || {}, last_updated: new Date().toISOString() });
    const st = window.__states;
    st['sensor.bms_reserve_soc'] = S(40, { inverter_floor: 25, capacity_kwh: 10, price_buy: 1.29, price_sell: 0.45, storm: !!o.storm });
    if (!o.noPlan) st['sensor.bms_plan_curve'] = S(o.planState || 'normal', { mode: o.mode || 'normal', generated_at: '2026-11-03T15:50:00+01:00', error: o.planError || null, curve: o.noCurve ? null : o.curve, proposals: o.proposals || { start_grid_charge: { label: 'Start ładowania z sieci 1', current: '22:00', proposed: '23:00', skip: false }, stop_grid_charge: { label: 'Stop ładowania z sieci 1', current: '06:00', proposed: '06:00', skip: false }, bateria_sprzedaz_start: { label: 'Start sprzedaży 1', current: '18:00', proposed: null, skip: true } } });
    if (!o.noReport) st['sensor.bms_monthly_report'] = S(4.3, o.report);
    st['sensor.bms_battery_health'] = S(88.1, o.health);
    st['sensor.bms_monitor_status'] = S(0, o.monitor || { alarms: [], low_soc_active: false, watches: [] });
    ['storm_mode', 'vacation_mode', 'notifications_enabled', 'auto_apply_dry_run'].forEach((k) => { st['switch.bms_' + k] = S(k === 'notifications_enabled' ? 'on' : (o[k] || 'off'), { friendly_name: k }); });
    st['number.bms_storm_mode_hours'] = S(24, { min: 1, max: 96, step: 1 });
    st['number.bms_vacation_load_w'] = S(250, { min: 0, max: 5000, step: 10 });
    window.__el.hass = window.__mk();
  }, o);
}
const tab = async (e, t) => { await e.q((t) => __el.shadowRoot.querySelector(`[data-tab="${t}"]`).click(), t); await sleep(300); };
const sr = (e, sel) => e.q((sel) => { const x = __el.shadowRoot.querySelector(sel); return x ? x.textContent.replace(/\s+/g, ' ').trim() : null; }, sel);
const blue = (e) => e.q(() => { const c = __el.shadowRoot.querySelector('#exPlanCv'); if (!c) return -1; const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let n = 0; for (let i = 0; i < d.length; i += 4) if (d[i + 3] > 200 && Math.abs(d[i] - 10) < 25 && Math.abs(d[i + 1] - 132) < 25 && d[i + 2] > 220) n++; return n; });

(async () => {
  const b = await chromium.launch();

  // ===== 1. ładowanie na żądanie + wykres planu (PC)
  let e = await openCard(b, {});
  await seed(e, { curve: curve() });
  await sleep(500);
  ok(!e.reqs.some((r) => /bms-extras\.js/.test(r)), 'moduł dodatków NIE jest pobierany na stronie głównej');
  await tab(e, 'ems');
  await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('#exPlanCv'), null, { timeout: 8000 });
  ok(e.reqs.filter((r) => /bms-extras\.js/.test(r)).length === 1 && e.reqs.some((r) => r === '/bms_komp_dec/bms-extras.js?v=' + CARD + '.1700000000'), 'moduł pobrany raz, z parametrem ?v=');
  ok(await e.q(() => !__el.shadowRoot.querySelector('#exPlanBox .chart-empty')), 'plan: brak komunikatu o błędzie');
  ok((await blue(e)) > 400, 'plan: krzywa SOC narysowana (niebieskie piksele: ' + await blue(e) + ')');
  const txt = await sr(e, '#exPlanBox');
  ok(/Najniższy SOC w planie: \d+% o \d\d:00/.test(txt), 'plan: najniższy SOC: ' + (txt.match(/Najniższy SOC[^.]*\./) || [''])[0]);
  ok(/Ładowanie z sieci: 22:00–06:00 \(do 90%\)/.test(txt), 'plan: okno ładowania 22:00–06:00 do 90%');
  ok(/Sprzedaż z baterii: 18:00–20:00/.test(txt), 'plan: sprzedaż 18:00–20:00');
  ok(/Najwyższa cena sprzedaży: 1,10 zł\/kWh o 19:00/.test(txt), 'plan: najwyższa cena sprzedaży');
  ok(/Najtańszy zakup: 0,62/.test(txt), 'plan: najtańszy zakup');
  ok(/Start ładowania z sieci 1/.test(txt) && /22:00 → 23:00/.test(txt) && !/Stop ładowania z sieci 1/.test(txt) && !/Start sprzedaży 1/.test(txt), 'plan: tylko faktyczne zmiany harmonogramu');
  ok(/szczyt taryfy/.test(txt) && /próg odcięcia falownika/.test(txt), 'plan: legenda');
  // podpowiedź po najechaniu
  await e.page.locator('#exPlanCv').scrollIntoViewIfNeeded();
  const bb = await e.page.locator('#exPlanCv').boundingBox();
  await e.page.mouse.move(bb.x + 34 + (bb.width - 42) * (3.5 / 24), bb.y + 60);
  await sleep(150);
  const tip = await e.q(() => { const t = __el.shadowRoot.querySelector('#exPlanTip'); return t && !t.hidden ? t.textContent : null; });
  ok(tip && /19:00–20:00/.test(tip) && /sprzedaż z baterii/.test(tip) && /kupno 1,29/.test(tip), 'plan: podpowiedź dla 19:00: ' + tip);
  ok(await e.q(() => { const t = __el.shadowRoot.querySelector('#exPlanTip'); const r = t.getBoundingClientRect(), c = __el.shadowRoot.querySelector('#exPlanCv').getBoundingClientRect(); return r.right <= c.right + 2 && r.left >= c.left - 2; }), 'plan: podpowiedź mieści się w wykresie');
  await e.page.mouse.move(bb.x + bb.width / 2, bb.y - 40);
  await sleep(150);
  ok(await e.q(() => __el.shadowRoot.querySelector('#exPlanTip').hidden), 'plan: podpowiedź znika po zjechaniu');
  ok(e.errs.length === 0, '1: brak błędów JS ' + JSON.stringify(e.errs));

  // ===== 2. przelicz teraz
  await e.q(() => { window.__svc = window.__svc || {}; window.__svc['bms_komp_dec.get_plan'] = (m) => { window.__planCall = m.service_data; return { response: { plan: { generated_at: '2026-11-03T16:30:00+01:00', mode: 'normal', error: null, curve: Object.assign({}, JSON.parse(JSON.stringify(__el._ex ? {} : {})), window.__newCurve), proposals: {} } } }; }; });
  await e.q((c) => { window.__newCurve = c; }, curve({ noGrid: true, low: true }));
  await e.q(() => __el.shadowRoot.querySelector('[data-ex="plan-refresh"]').click());
  await sleep(500);
  ok(await e.q(() => window.__planCall && window.__planCall.force === true), 'przelicz: usługa get_plan z force=true');
  const t2 = await sr(e, '#exPlanBox');
  ok(/nie jest potrzebne/.test(t2) && /zgodny z planem/.test(t2) && /Plan przeliczony/.test(t2), 'przelicz: nowy plan wyświetlony (bez ładowania, bez zmian harmonogramu)');
  ok(/⚠ Najniższy SOC w planie: \d+% o \d\d:00/.test(t2) && /blisko progu odcięcia/.test(t2), 'przelicz: ostrzeżenie o zbliżaniu się do progu');
  await e.ctx.close();

  // ===== 3. warianty danych planu
  const variants = [
    ['brak sensora', { noPlan: true }, /Brak sensora planu/],
    ['plan jeszcze nie policzony', { planState: 'brak', noCurve: true }, /jeszcze nie został policzony/],
    ['błąd planu', { planState: 'błąd', planError: 'SOC niedostępny <b>x</b>', noCurve: true }, /Plan niedostępny: SOC niedostępny &lt;b&gt;x&lt;\/b&gt;|Plan niedostępny: SOC niedostępny <b>x<\/b>/],
    ['brak krzywej', { noCurve: true }, /Plan niedostępny — brak danych/],
  ];
  for (const [name, o, re] of variants) {
    e = await openCard(b, {}); await seed(e, o); await tab(e, 'ems');
    await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('#exPlanBox') && !/Ładowanie planu/.test(__el.shadowRoot.querySelector('#exPlanBox').textContent), null, { timeout: 8000 });
    const t = await e.q(() => __el.shadowRoot.querySelector('#exPlanBox').innerHTML);
    ok(re.test(t), 'wariant „' + name + '”: ' + t.replace(/<[^>]+>/g, '').slice(0, 80));
    ok(await e.q(() => !__el.shadowRoot.querySelector('#exPlanBox b') || __el.shadowRoot.querySelector('#exPlanBox b').textContent !== 'x'), 'wariant „' + name + '”: tekst błędu zescape-owany');
    ok(e.errs.length === 0, 'wariant „' + name + '”: brak błędów JS ' + JSON.stringify(e.errs));
    await e.ctx.close();
  }
  // tryb burzowy i brak cen RCE
  e = await openCard(b, {}); await seed(e, { mode: 'storm', storm_mode: 'on', curve: Object.assign(curve({ noSell: true }), { sale: new Array(24).fill(0) }) }); await tab(e, 'ems');
  await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('#exPlanCv'), null, { timeout: 8000 });
  const ts = await sr(e, '#exPlanBox');
  ok(/tryb burzowy — cel 100%, bez sprzedaży/.test(ts) && /Sprzedaż z baterii: wyłączona \(tryb burzowy\)/.test(ts), 'plan: tryb burzowy oznaczony');
  ok(/Brak cen RCE w horyzoncie/.test(ts), 'plan: brak cen RCE opisany');
  await e.ctx.close();

  // ===== 4. telefon: plan mieści się w ekranie
  e = await openCard(b, { mobile: true }); await seed(e, { curve: curve() }); await tab(e, 'ems');
  await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('#exPlanCv'), null, { timeout: 8000 });
  ok((await blue(e)) > 200, 'telefon: krzywa narysowana');
  ok(await e.q(() => { const c = __el.shadowRoot.querySelector('#exPlanCv').getBoundingClientRect(); return c.left >= 0 && c.right <= window.innerWidth + 1; }), 'telefon: wykres mieści się w szerokości ekranu');
  ok(await e.q(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'telefon: brak poziomego przewijania strony (' + await e.q(() => document.documentElement.scrollWidth) + ')');
  await e.page.locator('#exPlanCv').scrollIntoViewIfNeeded();
  const bm = await e.page.locator('#exPlanCv').boundingBox();
  await e.page.mouse.click(bm.x + bm.width - 20, bm.y + 50);
  await sleep(150);
  ok(await e.q(() => { const t = __el.shadowRoot.querySelector('#exPlanTip'); if (t.hidden) return false; const r = t.getBoundingClientRect(); return r.left >= 0 && r.right <= window.innerWidth; }), 'telefon: podpowiedź przy prawej krawędzi mieści się w ekranie');
  ok(e.errs.length === 0, '4: brak błędów JS ' + JSON.stringify(e.errs));
  await e.ctx.close();

  console.log('FAILS', fails); await b.close(); process.exit(fails ? 1 : 0);
})();
