// „Narzędzia” (Zysk i log): co EMS zrobił, porady, kalendarz i mapa cieplna cen, test zaniku sieci, ocena rozbudowy, XSS
const { openCard, chromium } = require('./ui_env');
const { seed, curve, tab } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

const BASE = () => ({ savings: { last30: { days: 0 } }, accuracy: { pv: {}, load: {}, soc: {}, pv_correction: {}, days: [], pv_by_horizon: [] }, reviews: [], reviews_tally: {}, arb_proof: [], pv_correction_on: true, wear_cost: 0 });
const cal = () => Array.from({ length: 10 }, (_, i) => ({ date: `2026-11-${String(10 + i).padStart(2, '0')}`, avg: 0.6 + i * 0.05, max: 1, level: i === 9 ? 'high' : (i === 0 ? 'low' : 'mid') }));
const heat = () => Array.from({ length: 4 }, (_, i) => ({ date: `2026-11-${String(10 + i).padStart(2, '0')}`, h: Array.from({ length: 24 }, (_, h) => (h === 3 ? null : 0.5 + h / 40)) }));
const TOOLS = () => ({
  deeds: { text: 'W tym miesiącu EMS: 3× zablokował ładowanie z sieci.' },
  advice: [{ id: 'x', level: 'info', title: 'Rezerwa <b>x</b>', text: 'Możesz obniżyć rezerwę.' }],
  price_views: { calendar: cal(), median: 0.7, heat: heat() },
});

async function mk(b, extra) {
  const e = await openCard(b, {});
  await seed(e, { curve: curve() });
  await e.q(([base, extra]) => {
    window.__svc = window.__svc || {};
    window.__svc['bms_komp_dec.insights_get'] = () => ({ response: Object.assign(JSON.parse(JSON.stringify(base)), extra) });
    window.__svc['bms_komp_dec.grid_outage_test'] = () => ({ response: { ok: true, soc: 60, floor: 15, load_w: 500, usable_kwh: 4, scenarios: [{ id: 'now', label: 'Teraz <i>', load_w: 500, hours: 7, text: '7 h' }], note: 'Szacunek.' } });
    window.__svc['bms_komp_dec.expand_estimate'] = (d) => { window.__lastExp = d.service_data || d; return { response: { ok: true, days: 60, avg_buy: 0.67, avg_sell: 0.33, battery: { cost: 10000, annual: 900, payback_years: 11.1, note: null }, pv: null, note: 'Orientacyjnie.' } }; };
    window.__el.hass = window.__mk();
  }, [BASE(), extra]);
  await tab(e, 'log'); await sleep(1200);
  return e;
}
const txt = (e, sel) => e.q((sel) => { const x = __el.shadowRoot.querySelector('#exAccBox ' + sel); return x ? x.textContent.replace(/\s+/g, ' ').trim() : null; }, sel);

(async () => {
  const b = await chromium.launch();
  let e = await mk(b, TOOLS());
  ok(/Co EMS zrobił za Ciebie: W tym miesiącu EMS: 3× zablokował/.test(await txt(e, '[data-role="deeds"]') || ''), 'deeds: linia');
  const ai = await txt(e, '[data-role="advice-item"]');
  ok(ai && /Rezerwa <b>x<\/b>/.test(ai) && /Możesz obniżyć/.test(ai), 'porady: tekst, HTML zescapowany: ' + ai);
  const nb = await e.q(() => __el.shadowRoot.querySelectorAll('#exAccBox [data-role="advice-item"] b b').length);
  ok(nb === 0, 'porady: brak wstrzykniętego znacznika');
  const nc = await e.q(() => __el.shadowRoot.querySelectorAll('#exAccBox [data-role="price-calendar"] [data-level]').length);
  const hi = await e.q(() => __el.shadowRoot.querySelectorAll('#exAccBox [data-role="price-calendar"] [data-level="high"]').length);
  ok(nc === 10 && hi === 1, `kalendarz: 10 dni, 1 drogi (${nc}/${hi})`);
  const hr = await e.q(() => __el.shadowRoot.querySelectorAll('#exAccBox [data-role="price-heat"] tr').length);
  ok(hr === 4, 'mapa cieplna: 4 wiersze ' + hr);
  // test zaniku sieci
  await e.q(() => __el.shadowRoot.querySelector('#exAccBox [data-exi="outage"]').click()); await sleep(600);
  const o = await txt(e, '[data-role="outage-result"]');
  ok(o && /Start: 60% \(próg 15%\)/.test(o) && /Teraz <i>/.test(o) && /7 h/.test(o), 'zanik sieci: wynik i escape: ' + o);
  // rozbudowa: formularz → parametry usługi
  await e.q(() => { const i = __el.shadowRoot.querySelector('#exAccBox [data-exf="batt_kwh"]'); i.value = '5'; i.dispatchEvent(new Event('input', { bubbles: true })); const j = __el.shadowRoot.querySelector('#exAccBox [data-exf="batt_cost_per_kwh"]'); j.value = '2000.5'; j.dispatchEvent(new Event('input', { bubbles: true })); });
  await e.q(() => __el.shadowRoot.querySelector('#exAccBox [data-exi="expand"]').click()); await sleep(600);
  const sent = await e.q(() => window.__lastExp);
  ok(sent && sent.batt_kwh === 5 && sent.batt_cost_per_kwh === 2000.5 && sent.pv_kwp === undefined, 'rozbudowa: parametry usługi ' + JSON.stringify(sent));
  const x = await txt(e, '[data-role="expand-result"]');
  ok(x && /zwrot 11,1 lat/.test(x) && /0,67 zł\/kWh/.test(x) && /koszt 10000 zł/.test(x), 'rozbudowa: wynik ' + x);
  const kept = await e.q(() => __el.shadowRoot.querySelector('#exAccBox [data-exf="batt_kwh"]').value);
  ok(kept === '5', 'formularz zachowuje wpisane wartości po odświeżeniu');
  ok(e.errs.length === 0, 'brak błędów JS ' + JSON.stringify(e.errs));
  // brak danych: tylko test i formularz
  e = await mk(b, {});
  ok(await txt(e, '[data-role="deeds"]') === null && await txt(e, '[data-role="advice"]') === null && await txt(e, '[data-role="price-calendar"]') === null && await txt(e, '[data-role="price-heat"]') === null, 'brak danych: bez linii, porad, kalendarza i mapy');
  ok(await txt(e, '[data-role="outage"]') !== null && await txt(e, '[data-role="expand"]') !== null, 'brak danych: test i formularz nadal są');
  // błąd usługi
  await e.q(() => { window.__svc['bms_komp_dec.grid_outage_test'] = () => { throw new Error('boom'); }; });
  await e.q(() => __el.shadowRoot.querySelector('#exAccBox [data-exi="outage"]').click()); await sleep(600);
  ok(/Nie udało się/.test(await txt(e, '[data-role="tools-err"]') || ''), 'błąd usługi: komunikat');
  await b.close();
  console.log(fails ? 'FAILS ' + fails : 'ALL OK');
  process.exit(fails ? 1 : 0);
})();
