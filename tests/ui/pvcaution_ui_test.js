// Autokorekta ostrożności prognozy PV (Zysk i log → Trafność prognoz): propozycja, zastosuj, cofnij, odrzuć, brak uprawnień, błędy usług, XSS
const { openCard, chromium } = require('./ui_env');
const { seed, curve, tab, sr } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

const BASE = () => ({ savings: { last30: { days: 0 } }, accuracy: { pv: {}, load: {}, soc: {}, pv_correction: {}, days: [], pv_by_horizon: [] }, reviews: [], reviews_tally: {}, arb_proof: [], pv_correction_on: true });
const PROP = { dir: 'raise', from: 0, to: 20, days: 7, bad_days: 6, bias: 25, lo: 0.7, need: 66.7,
  text: 'W 6 z ostatnich 7 dób prognoza PV była zawyżona (średnio o 25%) <img src=x onerror=window.__pwn7=1>. Proponuję zwiększyć ostrożność z 0% do 20%.' };

async function mk(b, pcState, opts = {}) {
  const e = await openCard(b, {});
  await seed(e, { curve: curve() });
  await e.q(([base, pc, opts]) => {
    window.__svc = window.__svc || {}; window.__cauCalls = [];
    window.__cau = JSON.parse(JSON.stringify(pc));
    const ins = () => Object.assign(JSON.parse(JSON.stringify(base)), { pv_caution: JSON.parse(JSON.stringify(window.__cau)) });
    window.__svc['bms_komp_dec.insights_get'] = () => ({ response: ins() });
    window.__svc['bms_komp_dec.pv_caution_apply'] = () => {
      window.__cauCalls.push('apply'); if (opts.fail) throw new Error('Nie udało się ustawić ostrożności <b>x</b>');
      window.__cau = { current: 20, proposal: null, last: { date: '2026-11-20', from: 0, to: 20, reverted: false }, can_revert: true };
      return { response: { ok: true, from: 0, to: 20, pv_caution: JSON.parse(JSON.stringify(window.__cau)) } };
    };
    window.__svc['bms_komp_dec.pv_caution_revert'] = () => {
      window.__cauCalls.push('revert');
      window.__cau = { current: 0, proposal: null, last: { date: '2026-11-20', from: 0, to: 20, reverted: true }, can_revert: false };
      return { response: { ok: true, from: 20, to: 0, pv_caution: JSON.parse(JSON.stringify(window.__cau)) } };
    };
    window.__svc['bms_komp_dec.pv_caution_dismiss'] = () => {
      window.__cauCalls.push('dismiss'); window.__cau = { current: 0, proposal: null, last: null, can_revert: false };
      return { response: { ok: true, pv_caution: JSON.parse(JSON.stringify(window.__cau)) } };
    };
    if (opts.user) window.__admin = false;
    window.__el.hass = window.__mk();
  }, [BASE(), pcState, opts]);
  await tab(e, 'log'); await sleep(1200);
  return e;
}
const box = (e) => sr(e, '#exAccBox');
const click = (e, a) => e.q((a) => __el.shadowRoot.querySelector(`#exAccBox [data-exi="${a}"]`).click(), a);

(async () => {
  const b = await chromium.launch();

  // ---------- propozycja podwyżki
  let e = await mk(b, { current: 0, proposal: PROP, last: null, can_revert: false });
  let t = await box(e);
  ok(/Propozycja: ostrożność prognozy PV 0% → 20%/.test(t) && /W 6 z ostatnich 7 dób/.test(t) && /średnio o 25%/.test(t), 'propozycja: tytuł i uzasadnienie: ' + t.slice(0, 200));
  ok(await e.q(() => !__el.shadowRoot.querySelector('#exAccBox img') && !window.__pwn7), 'treść propozycji zescape-owana (XSS)');
  ok(await e.q(() => !!__el.shadowRoot.querySelector('#exAccBox [data-exi="cau-apply"]') && !!__el.shadowRoot.querySelector('#exAccBox [data-exi="cau-dismiss"]')), 'admin: przyciski Zastosuj i Nie teraz');
  ok(/Zastosuj \(20%\)/.test(t), 'przycisk z docelową wartością');
  await click(e, 'cau-apply'); await sleep(500);
  t = await box(e);
  ok(await e.q(() => JSON.stringify(window.__cauCalls) === '["apply"]'), 'zastosowanie: wywołana usługa pv_caution_apply');
  ok(/Ostrożność prognozy PV ustawiona na 20%/.test(t) && /możesz to cofnąć/.test(t), 'komunikat po zastosowaniu');
  ok(/zmieniona z 0% dnia 20\.11/.test(t) && await e.q(() => !!__el.shadowRoot.querySelector('#exAccBox [data-exi="cau-revert"]')) && /Cofnij do 0%/.test(t), 'po zmianie: informacja i przycisk Cofnij');
  ok(await e.q(() => !__el.shadowRoot.querySelector('#exAccBox [data-exi="cau-apply"]')), 'po zmianie: przycisku Zastosuj już nie ma');
  await click(e, 'cau-revert'); await sleep(500);
  t = await box(e);
  ok(await e.q(() => JSON.stringify(window.__cauCalls) === '["apply","revert"]') && /Przywrócono ostrożność 0%/.test(t), 'cofnięcie: usługa i komunikat');
  ok(await e.q(() => !__el.shadowRoot.querySelector('#exAccBox [data-exi="cau-revert"]')) && /Ostrożność prognozy PV w planie: 0%/.test(t), 'po cofnięciu: zwykła informacja o ostrożności');
  ok(e.errs.length === 0, 'brak błędów JS ' + JSON.stringify(e.errs));

  // ---------- odrzucenie
  e = await mk(b, { current: 0, proposal: PROP, last: null, can_revert: false });
  await click(e, 'cau-dismiss'); await sleep(500);
  t = await box(e);
  ok(await e.q(() => JSON.stringify(window.__cauCalls) === '["dismiss"]') && /Propozycja odrzucona/.test(t) && !/Propozycja: ostrożność/.test(t), 'odrzucenie: usługa, komunikat, propozycja znika');

  // ---------- błąd usługi
  e = await mk(b, { current: 0, proposal: PROP, last: null, can_revert: false }, { fail: true });
  await click(e, 'cau-apply'); await sleep(500);
  t = await box(e);
  ok(/Nie udało się: .*Nie udało się ustawić ostrożności/.test(t) && await e.q(() => !__el.shadowRoot.querySelector('#exAccBox [data-role="pv-caution-msg"] b')), 'błąd usługi: komunikat bez interpretacji HTML');
  ok(await e.q(() => !!__el.shadowRoot.querySelector('#exAccBox [data-exi="cau-apply"]')), 'po błędzie propozycja zostaje (można spróbować ponownie)');

  // ---------- zwykły użytkownik: widzi, nie zatwierdza
  e = await mk(b, { current: 0, proposal: PROP, last: null, can_revert: false }, { user: true });
  t = await box(e);
  ok(/Propozycja: ostrożność prognozy PV 0% → 20%/.test(t) && /Zatwierdzić może administrator/.test(t) && await e.q(() => !__el.shadowRoot.querySelector('#exAccBox [data-exi^="cau-"]')), 'użytkownik bez uprawnień: bez przycisków');
  e = await mk(b, { current: 20, proposal: null, last: { date: '2026-11-20', from: 0, to: 20, reverted: false }, can_revert: true }, { user: true });
  ok(await e.q(() => !__el.shadowRoot.querySelector('#exAccBox [data-exi="cau-revert"]')) && /zmieniona z 0%/.test(await box(e)), 'użytkownik bez uprawnień: bez przycisku Cofnij');

  // ---------- obniżka
  e = await mk(b, { current: 40, proposal: { dir: 'lower', from: 40, to: 20, days: 6, bad_days: 5, bias: -35, lo: 0.7, need: 0, text: 'Słońca było więcej, niż zakładała prognoza.' }, last: null, can_revert: false });
  ok(/ostrożność prognozy PV 40% → 20%/.test(await box(e)) && /Zastosuj \(20%\)/.test(await box(e)), 'obniżka: 40% → 20%');

  // ---------- bez propozycji i bez zmiany: tylko informacja
  e = await mk(b, { current: 15, proposal: null, last: null, can_revert: false });
  t = await box(e);
  ok(/Ostrożność prognozy PV w planie: 15%/.test(t) && !/Propozycja:/.test(t) && await e.q(() => !__el.shadowRoot.querySelector('#exAccBox [data-exi^="cau-"]')), 'bez propozycji: informacja o aktualnej ostrożności');

  // ---------- odporność na śmieci i stary backend
  for (const [name, pc] of [['null', null], ['napis', 'x'], ['liczba', 5], ['tablica', []], ['proposal bez tekstu', { current: 0, proposal: { to: 20 }, last: null }],
                            ['to = napis', { current: 0, proposal: { text: 'x', to: 'abc', from: 0 }, last: null }], ['current = napis', { current: 'abc', proposal: null, last: { to: 'x' }, can_revert: true }]]) {
    e = await mk(b, pc);
    t = await box(e);
    ok(typeof t === 'string' && /Ocena planu po dobie|Dowód/.test(t) && e.errs.length === 0, `śmieci (${name}): sekcja trafności działa, bez błędów JS ${JSON.stringify(e.errs)}`);
  }
  e = await openCard(b, {});
  await seed(e, { curve: curve() });
  await e.q((base) => { window.__svc = { 'bms_komp_dec.insights_get': () => ({ response: JSON.parse(JSON.stringify(base)) }) }; window.__el.hass = window.__mk(); }, BASE());
  await tab(e, 'log'); await sleep(1200);
  ok(!/ostrożność prognozy PV/i.test(await box(e)) && e.errs.length === 0, 'stary backend bez pv_caution: bez bloku i bez błędów');

  await b.close();
  console.log(fails ? 'FAILS ' + fails : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
