// Zysk i log: prognoza kosztu dziś/jutro (Oszczędności) i tabela „Czy większa bateria się opłaca?” (symulacja) + zapis ceny za kWh
const { openCard, chromium } = require('./ui_env');
const { seed, curve, tab } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const BASE = () => ({ savings: { last30: { days: 0 } }, accuracy: { pv: {}, load: {}, soc: {}, pv_correction: {}, days: [], pv_by_horizon: [] }, reviews: [], reviews_tally: {}, arb_proof: [], pv_correction_on: true, wear_cost: 0 });
const SAV = { today: { actual: 1, nobat: 3, simple: 2, vs_nobat: 2, vs_simple: 1, days: 1 }, week: {}, month: { actual: 5, nobat: 9, simple: 7, vs_nobat: 4, vs_simple: 2, days: 3 }, total: { days: 3 }, since: '2026-11-01', daily: [], params: {} };
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, { admin: true, mobile: true });
  await e.page.setViewportSize({ width: 390, height: 900 });
  await seed(e, { curve: curve() });
  await e.q(([base, sav]) => {
    window.__svc = window.__svc || {};
    window.__svc['bms_komp_dec.insights_get'] = () => ({ response: Object.assign(base, { savings: Object.assign({ today: {}, week: {}, month: {}, total: {} }, sav),
      cost_forecast: { today: { so_far: 2.1, rest_plan: 3.4, total: 5.5, plan_hours: 9 }, tomorrow: { plan: -1.25, plan_hours: 24 }, note: 'Szacunek z planu.' } }) });
    window.__svc['bms_komp_dec.analysis_get'] = () => ({ response: { tariff: null, cfg: { batt_zl_kwh: 1500 }, sim: null,
      batt: { days: 40, cap_kwh: 10, extrapolated: true, note: 'Dolna granica: prosta strategia.', rows: [
        { extra_kwh: 5, cap_kwh: 15, saving_period: 12, saving_year: 110, payback_years: 68.2 }, { extra_kwh: 10, cap_kwh: 20, saving_period: 18, saving_year: 164, payback_years: null }] } } });
    window.__svc['bms_komp_dec.analysis_set'] = (m) => { window.__sent = m.service_data || m; return { response: {} }; };
    window.__el.hass = window.__mk();
  }, [BASE(), SAV]);
  await tab(e, 'log'); await sleep(1500);
  const r = await e.q(() => { const sh = __el.shadowRoot, c = sh.querySelector('#exCostFc'), t = sh.querySelector('#exBattTbl');
    return { cost: c ? c.parentElement.textContent.replace(/\s+/g, ' ').trim() : null, batt: t ? t.textContent.replace(/\s+/g, ' ').trim() : null, doc: document.documentElement.scrollWidth,
      fit: t ? t.parentElement.scrollWidth <= t.parentElement.clientWidth + 1 : null, ik: (sh.querySelector('#pxIk') || {}).value }; });
  ok(r.cost && /Dziś: dotąd 2,10 zł/.test(r.cost) && /razem ≈ 5,50 zł/.test(r.cost), 'koszt dziś: dotąd, plan, razem: ' + JSON.stringify(r.cost));
  ok(r.cost && /Jutro wg planu: ≈ −1,25 zł/.test(r.cost) && /Rachunek i cel/.test(r.cost), 'koszt jutro (zarobek ze znakiem minus) i odesłanie do „Rachunek i cel”');
  ok(r.batt && /teraz 10,0 kWh/.test(r.batt) && /\+5 kWh \(razem 15,0 kWh\)/.test(r.batt) && /\+110 zł/.test(r.batt) && /68,2 lat/.test(r.batt) && /\+164 zł/.test(r.batt), 'większa bateria: wiersze, zysk i zwrot: ' + JSON.stringify(r.batt));
  ok(r.fit && r.doc <= 390, 'tabela baterii mieści się na 390 px');
  ok(r.ik === '1500', 'pole ceny za kWh wypełnione z ustawień');
  await e.q(() => { const sh = __el.shadowRoot; sh.querySelector('#pxIk').value = '1800'; sh.querySelector('[data-px-an]').click(); });
  await sleep(400);
  const sent = await e.q(() => window.__sent);
  ok(sent && sent.batt_zl_kwh === 1800, 'zapis wysyła cenę za kWh: ' + JSON.stringify(sent));
  console.log(fails ? `FAILS ${fails}` : 'ALL OK');
  await b.close(); process.exit(fails ? 1 : 0);
})();
