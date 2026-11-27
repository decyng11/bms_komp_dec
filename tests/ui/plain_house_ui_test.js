// Zysk i log → „Zwykły dom bez PV i baterii” (G11 / G12 / G12w / Twoja taryfa) obok kosztu z EMS + ostrzeżenie o cenach orientacyjnych.
const { openCard, chromium } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const PLAIN = { days: 30, load_kwh: 450, actual: 190, actual_month: 190, best_plain: 'g12w', note: 'Szacunek.', rows: [
  { key: 'g11', name: 'Taryfa jednostrefowa G11 (0.65 zł/kWh)', cost: 292.5, per_month: 292.5, saving: 102.5, saving_month: 102.5 },
  { key: 'g12', name: 'G12: szczyt 0.80 / poza 0.50 zł/kWh', cost: 280, per_month: 280, saving: 90, saving_month: 90 },
  { key: 'g12w', name: 'G12w: to samo, weekendy i święta tanie', cost: 270, per_month: 270, saving: 80, saving_month: 80 },
  { key: 'real', name: 'Twoja obecna taryfa (rzeczywiste ceny)', cost: 300, per_month: 300, saving: 110, saving_month: 110 }] };
const TARIFF = { days: 30, import_kwh: 400, note: 'Szacunek.', best: null, rows: [
  { key: 'actual', name: 'Twoja obecna taryfa (rzeczywiste ceny)', cost: 360, diff: 0, per_month: 360, diff_month: 0 },
  { key: 'g11', name: 'Jedna stawka (G11) 0.65 zł/kWh', cost: 260, diff: -100, per_month: 260, diff_month: -100 }] };
(async () => {
  const b = await chromium.launch();
  for (const w of [320, 390]) {
    const e = await openCard(b, { admin: true, mobile: true });
    await e.page.setViewportSize({ width: w, height: 800 });
    await e.q((t) => { document.getElementById('h').style.width = t.w + 'px'; window.__svc = window.__svc || {};
      window.__svc['bms_komp_dec.analysis_get'] = () => ({ response: { tariff: t.tariff, plain: t.plain, assumed: ['g11', 'zone'], defaults: { g11: 0.65 }, cfg: {}, auto: {}, sim: null } });
      window.__svc['bms_komp_dec.analysis_set'] = () => ({ response: {} }); }, { w, tariff: TARIFF, plain: PLAIN });
    await e.q(() => __el.shadowRoot.querySelector('.tab[data-tab="log"]').click());
    await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('#exPlainTbl'), null, { timeout: 10000 }); await sleep(300);
    const r = await e.q(() => { const box = __el.shadowRoot.querySelector('#exSimBox'), t = box.querySelector('#exPlainTbl'), wrap = t.parentElement;
      return { rows: t.querySelectorAll('tbody tr').length, txt: t.textContent, fit: wrap.scrollWidth <= wrap.clientWidth + 1, doc: document.documentElement.scrollWidth,
        best: !!t.querySelector('tr.px-best'), warn: box.textContent, ph: box.querySelector('#pxTg').placeholder }; });
    ok(r.rows === 5 && /G11/.test(r.txt) && /G12w/.test(r.txt) && /Twoja obecna taryfa/.test(r.txt) && /Ty: z PV, baterią i EMS/.test(r.txt), `${w}px: wiersze G11, G12, G12w, Twoja taryfa i „Ty” (${r.rows})`);
    ok(/102,50 zł/.test(r.txt) && /190,00 zł/.test(r.txt), `${w}px: zysk wobec G11 i koszt z EMS widoczne`);
    ok(r.best, `${w}px: najtańsza taryfa dla zwykłego domu podświetlona`);
    ok(/Ceny G11 i strefowe \(G12\/G12w\) są orientacyjne/.test(r.warn), `${w}px: ostrzeżenie o cenach orientacyjnych`);
    ok(/orientacyjnie 0,65/.test(r.ph), `${w}px: pole G11 pokazuje cenę orientacyjną (${r.ph})`);
    ok(r.fit && r.doc <= w, `${w}px: tabela mieści się bez przewijania w bok`);
    ok(e.errs.length === 0, `${w}px: brak błędów JS ` + JSON.stringify(e.errs));
    await e.page.context().close();
  }
  console.log(fails ? `FAILS ${fails}` : 'ALL OK');
  await b.close(); process.exit(fails ? 1 : 0);
})();
