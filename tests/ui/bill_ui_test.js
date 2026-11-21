// „Rachunek i cel” (Zysk i log): cel miesięczny z paskiem, prognoza, rozbicie, skarbonka, brak danych, XSS
const { openCard, chromium } = require('./ui_env');
const { seed, curve, tab, sr } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

const BASE = () => ({ savings: { last30: { days: 0 } }, accuracy: { pv: {}, load: {}, soc: {}, pv_correction: {}, days: [], pv_by_horizon: [] }, reviews: [], reviews_tally: {}, arb_proof: [], pv_correction_on: true, wear_cost: 0 });
const BILL = () => ({
  forecast: { mtd: -57, avg_day: -3, remaining_days: 11, days_used: 14, projected: -90, low: -95, high: -85 },
  goal: { goal: 100, spent: 57, projected_spent: 90, worst_spent: 95, status: 'warn', pct: 90, text: 'Prognoza 90 zł jest blisko celu 100 zł (na razie 57 zł).' },
  goal_value: 100,
  breakdown: [{ k: 'Kupiłeś z sieci', v: '120,5 kWh za 80,10 zł (śr. 0,66 zł/kWh)' }, { k: 'Bilans z siecią', v: '-70,15 zł' }, { k: 'Oszczędność (szacunek)', v: '336,10 zł' }],
  month_title: 'Listopad 2026',
  piggy: { saved: 1200, days: 100, per_day: 12, invest: 20000, pct: 6, payback_date: '2044-03-01', years_left: 3.5 },
});

async function mk(b, bill) {
  const e = await openCard(b, {});
  await seed(e, { curve: curve() });
  await e.q(([base, bill]) => {
    window.__svc = window.__svc || {};
    window.__svc['bms_komp_dec.insights_get'] = () => ({ response: Object.assign(JSON.parse(JSON.stringify(base)), bill === undefined ? {} : { bill: JSON.parse(JSON.stringify(bill)) }) });
    window.__el.hass = window.__mk();
  }, [BASE(), bill]);
  await tab(e, 'log'); await sleep(1200);
  return e;
}
const q = (e, sel) => e.q((sel) => { const x = __el.shadowRoot.querySelector('#exAccBox ' + sel); return x ? { t: x.textContent.replace(/\s+/g, ' ').trim(), s: x.getAttribute('data-status'), w: (x.querySelector('[data-role="bar"]') || {}).style ? x.querySelector('[data-role="bar"]').style.width : null } : null; }, sel);

(async () => {
  const b = await chromium.launch();

  let e = await mk(b, BILL());
  let g = await q(e, '[data-role="bill-goal"]');
  ok(g && g.s === 'warn' && /Cel miesięczny: Prognoza 90 zł jest blisko celu 100 zł/.test(g.t) && /Wydano 57,00 zł z 100,00 zł/.test(g.t), 'cel: tekst i wydano/z celu: ' + JSON.stringify(g));
  ok(g && g.w === '90%', 'cel: pasek 90%');
  let f = await q(e, '[data-role="bill-forecast"]');
  ok(f && /-90,00 zł/.test(f.t) && /-95,00 zł … -85,00 zł/.test(f.t) && /na razie -57,00 zł/.test(f.t) && /14 dób/.test(f.t), 'prognoza: wartość, przedział, na razie: ' + JSON.stringify(f));
  let r = await q(e, '[data-role="bill-breakdown"]');
  ok(r && /Listopad 2026/.test(r.t) && /Kupiłeś z sieci/.test(r.t) && /120,5 kWh za 80,10 zł/.test(r.t) && /bez opłat stałych/.test(r.t), 'rozbicie: pozycje i zastrzeżenie: ' + JSON.stringify(r));
  let p = await q(e, '[data-role="bill-piggy"]');
  ok(p && /zaoszczędzono 1200,00 zł z nakładu 20000,00 zł/.test(p.t) && /2044-03-01/.test(p.t) && p.w === '6%', 'skarbonka: kwota, nakład, data zwrotu, pasek: ' + JSON.stringify(p));
  ok(e.errs.length === 0, 'brak błędów JS ' + JSON.stringify(e.errs));

  // statusy celu: kolory
  for (const [st, colorRe] of [['ok', /green/], ['over', /red/], ['over_now', /red/]]) {
    const bill = BILL(); bill.goal.status = st; bill.goal.pct = st === 'ok' ? 40 : 120;
    e = await mk(b, bill);
    const bg = await e.q(() => { const x = __el.shadowRoot.querySelector('#exAccBox [data-role="bill-goal"] [data-role="bar"]'); return x ? x.getAttribute('style') : ''; });
    ok(colorRe.test(bg), `cel ${st}: kolor paska (${bg})`);
    if (st !== 'ok') ok((await q(e, '[data-role="bill-goal"]')).w === '100%', `cel ${st}: pasek przycięty do 100%`);
  }

  // brak celu i brak prognozy: podpowiedzi
  const none = BILL(); none.goal = null; none.forecast = null; none.piggy = null; none.breakdown = [];
  e = await mk(b, none);
  g = await q(e, '[data-role="bill-goal"]'); f = await q(e, '[data-role="bill-forecast"]');
  ok(g && /number\.bms_monthly_goal_pln/.test(g.t) && g.s === null, 'bez celu: podpowiedź, gdzie go ustawić');
  ok(f && /po 3 pełnych dobach/.test(f.t), 'bez prognozy: wyjaśnienie');
  ok(!(await q(e, '[data-role="bill-piggy"]')) && !(await q(e, '[data-role="bill-breakdown"]')), 'bez skarbonki i rozbicia: bez pustych sekcji');

  // skarbonka bez nakładu i zwrócona
  const noinv = BILL(); noinv.piggy = { saved: 500, days: 30, per_day: 16.67, invest: null, pct: null, payback_date: null, years_left: null };
  e = await mk(b, noinv);
  p = await q(e, '[data-role="bill-piggy"]');
  ok(p && /podaj nakład/.test(p.t) && p.w === null, 'skarbonka bez nakładu: prośba o nakład, bez paska: ' + JSON.stringify(p));
  const done = BILL(); done.piggy = { saved: 25000, days: 900, per_day: 27, invest: 20000, pct: 125, payback_date: 'zwrócone', years_left: 0 };
  e = await mk(b, done);
  p = await q(e, '[data-role="bill-piggy"]');
  ok(p && /już się zwróciła/.test(p.t) && p.w === '100%', 'skarbonka zwrócona: komunikat i pełny pasek');

  // starszy backend (bez bill) → blok się nie pojawia
  e = await mk(b, undefined);
  ok(!(await q(e, '[data-role="bill"]')), 'starszy backend bez pola bill: brak bloku, bez błędów ' + JSON.stringify(e.errs));

  // śmieci i XSS
  const evil = BILL(); evil.goal.text = '<img src=x onerror=window.__pwn9=1>'; evil.breakdown = [{ k: '<b onmouseover=1>k</b>', v: '<img src=x onerror=window.__pwn9=1>' }, null, 5, { k: 3 }];
  evil.piggy.payback_date = '<img src=x onerror=window.__pwn9=1>'; evil.forecast.projected = 'abc'; evil.goal.pct = 'x'; evil.goal.spent = NaN;
  e = await mk(b, evil);
  ok(await e.q(() => !__el.shadowRoot.querySelector('#exAccBox img') && !__el.shadowRoot.querySelector('#exAccBox b[onmouseover]') && !window.__pwn9), 'XSS: treści zescape-owane');
  ok(/Cel miesięczny:/.test((await q(e, '[data-role="bill-goal"]')).t) && /—/.test((await q(e, '[data-role="bill-forecast"]')).t), 'śmieci liczbowe: myślniki zamiast NaN');
  ok(!/NaN|undefined|null/.test((await q(e, '[data-role="bill"]')).t), 'brak „NaN/undefined/null” w tekście');
  ok(e.errs.length === 0, 'śmieci: brak błędów JS ' + JSON.stringify(e.errs));

  await b.close();
  console.log(fails ? `FAILS ${fails}` : 'ALL OK');
  process.exit(fails ? 1 : 0);
})();
