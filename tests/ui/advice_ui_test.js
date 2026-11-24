// Porady do ustawień z „Zastosuj/Cofnij”, zużycie baterii w zł i oś decyzji planu (Zysk i log)
const { openCard, chromium } = require('./ui_env');
const { seed, curve, tab, sr } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const BASE = () => ({ savings: { last30: { days: 0 } }, accuracy: { pv: {}, load: {}, soc: {}, pv_correction: {}, days: [], pv_by_horizon: [] }, reviews: [], reviews_tally: {}, arb_proof: [], pv_correction_on: true,
  advice: [{ id: 'cycle_eff_100', level: 'warn', title: 'Sprawność cyklu <i>100%</i>', text: 'Opis', apply: { key: 'cycle_efficiency', to: 90, from: 100, label: 'Sprawność cyklu baterii' } }],
  advice_done: [],
  yoy: { available: true, window: 30, cur: { revenue: 40, cost: 10, net: 30, import_kwh: 100, export_kwh: 150 }, prev: { revenue: 20, cost: 30, net: -10, import_kwh: 160, export_kwh: 60 }, diff: { revenue: 20, cost: -20, net: 40, import_kwh: -60, export_kwh: 90 }, pct: { revenue: 100, cost: -66.7, net: null, import_kwh: -37.5, export_kwh: 150 }, note: 'Okres porównywany: test.' },
  wear_view: { wear_per_kwh: 0.2, total_wear: 2, days: [{ date: '2026-11-24', dis_kwh: 10, wear_pln: 2, net: 5, net_after: 3 }] },
  plan_story: { text: 'Plan jest stabilny: w ciągu doby zmieniał 0% decyzji.', rows: [{ date: '2026-11-24', slots: { 6: { 'ładowanie': '02:00–04:00' }, 12: { 'ładowanie': '02:00–04:00' }, 18: { 'ładowanie': 'pomijam' } } }] } });
(async () => {
  const b = await chromium.launch();
  for (const admin of [true, false]) {
    const e = await openCard(b, {});
    await seed(e, { curve: curve() });
    await e.q(([base, admin]) => {
      window.__svc = window.__svc || {}; window.__calls2 = []; window.__ad = JSON.parse(JSON.stringify(base));
      window.__svc['bms_komp_dec.insights_get'] = () => ({ response: JSON.parse(JSON.stringify(window.__ad)) });
      window.__svc['bms_komp_dec.advice_apply'] = (d) => { window.__calls2.push('apply:' + (d.service_data || d).id);
        window.__ad.advice = []; window.__ad.advice_done = [{ id: 'cycle_eff_100', label: 'Sprawność cyklu baterii', from: 100, to: 90 }];
        return { response: { ok: true, from: 100, to: 90, advice: [], advice_done: window.__ad.advice_done } }; };
      window.__svc['bms_komp_dec.advice_revert'] = (d) => { window.__calls2.push('revert:' + (d.service_data || d).id);
        window.__ad.advice_done = []; return { response: { ok: true, from: 90, to: 100, advice: [], advice_done: [] } }; };
      if (!admin) window.__admin = false;
      window.__el.hass = window.__mk();
    }, [BASE(), admin]);
    await tab(e, 'log'); await sleep(1200);
    const t = await sr(e, '#exAccBox'); const t2 = await sr(e, '#exSavBox');
    ok(/Sprawność cyklu/.test(t) && await e.q(() => !__el.shadowRoot.querySelector('#exAccBox [data-role="advice-item"] i')), `${admin ? 'admin' : 'zwykły'}: porada widoczna, HTML zescape-owany`);
    const has = await e.q(() => !!__el.shadowRoot.querySelector('#exAccBox [data-exi="adv-apply"]'));
    ok(has === admin, `${admin ? 'admin ma' : 'zwykły nie ma'} przycisk Zastosuj`);
    ok(/Rok do roku/.test(t2) && /Rok temu/.test(t2) && /−37%|−38%/.test(t2) && /\+40,00 zł/.test(t2), 'rok do roku: tabela i różnice');
    ok(/Zużycie baterii w złotówkach/.test(t2) && /Po zużyciu/.test(t2), 'tabela zużycia baterii');
    ok(/Decyzje planu w ciągu doby/.test(t2) && /Plan jest stabilny/.test(t2) && /pomijam/.test(t2), 'oś decyzji planu');
    if (admin) {
      await e.q(() => __el.shadowRoot.querySelector('#exAccBox [data-exi="adv-apply"]').click()); await sleep(500);
      ok(await e.q(() => JSON.stringify(window.__calls2) === '["apply:cycle_eff_100"]'), 'zastosowanie: wywołana usługa z id');
      ok(await e.q(() => !!__el.shadowRoot.querySelector('#exAccBox [data-exi="adv-revert"]') && !__el.shadowRoot.querySelector('#exAccBox [data-exi="adv-apply"]')), 'po zastosowaniu: jest Cofnij, nie ma Zastosuj');
      await e.q(() => __el.shadowRoot.querySelector('#exAccBox [data-exi="adv-revert"]').click()); await sleep(500);
      ok(await e.q(() => JSON.stringify(window.__calls2) === '["apply:cycle_eff_100","revert:cycle_eff_100"]'), 'cofnięcie: wywołana usługa');
    }
    ok(e.errs.length === 0, 'brak błędów JS ' + JSON.stringify(e.errs));
    await e.page.context().close();
  }
  console.log(fails ? `FAILS ${fails}` : 'ALL OK');
  await b.close(); process.exit(fails ? 1 : 0);
})();
