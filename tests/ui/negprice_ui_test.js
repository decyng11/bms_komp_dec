// Zakładka Zysk → symulacja: licznik godzin z ujemną ceną sprzedaży/zakupu, ich koszt, konkretne ostrzeżenie „Samo PV drożej niż Bez PV”
// oraz podpowiedź o istniejącej opcji „Reakcja na niskie/ujemne ceny RCE”. Wszystko ma mieścić się w karcie na telefonie (320 px).
const { openCard, chromium } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const SC = (a, b, c, d) => [{ key: 'nopv', name: 'Bez PV i bez baterii', period: a, year: a * 36 }, { key: 'nobat', name: 'Samo PV (bez baterii)', period: b, year: b * 36 },
  { key: 'simple', name: 'PV + bateria, prosta strategia (bez planera)', period: c, year: c * 36 }, { key: 'ems', name: 'PV + bateria + EMS (rzeczywiście)', period: d, year: d * 36 }];
const BAD = { days: 10, extrapolated: true, note: 'Szacunek.', savings_year: { pv: -2513.89, battery: 969.48, ems: 1304.55, total: -239.87 }, cfg: {}, scenarios: SC(497.08, 565.96, 539.39, 503.65) };
const GOOD = { days: 40, extrapolated: false, note: 'Szacunek.', savings_year: { pv: 2000, battery: 800, ems: 300, total: 3100 }, cfg: {}, scenarios: SC(400, 200, 150, 120) };
const NEG = { days: 10, sell_days: 4, buy_days: 2, sell_h: 11, sell_kwh: 38.4, sell_cost: 7.93, buy_h: 5, buy_kwh: 6.2, buy_gain: 0.84, nobat_sell_cost: 9.1, nopv_buy_gain: 1.1, sell_cost_year: 289.45, extrapolated: true };
const NEG0 = { days: 10, sell_days: 0, buy_days: 0, sell_h: 0, sell_kwh: 0, sell_cost: 0, buy_h: 0, buy_kwh: 0, buy_gain: 0, nobat_sell_cost: 0, nopv_buy_gain: 0, sell_cost_year: 0, extrapolated: true };
const CASES = [
  ['A: ujemna sprzedaż, reakcja wyłączona', BAD, NEG, false, 0],
  ['B: ujemna sprzedaż, reakcja włączona', BAD, NEG, true, 0.05],
  ['C: „Samo PV” drożej, ale brak ujemnych cen', BAD, NEG0, false, 0],
  ['D: tylko ujemny zakup', GOOD, Object.assign({}, NEG, { sell_h: 0, sell_days: 0, sell_kwh: 0, sell_cost: 0, sell_cost_year: 0 }), false, 0],
  ['E: dane bez liczników', GOOD, null, false, 0],
];
(async () => {
  const b = await chromium.launch();
  for (const sk of ['classic', 'glass']) for (const w of [320, 390]) for (const [nm, sim, neg, react, thr] of CASES) {
    if (sk === 'glass' && w === 390 && nm[0] !== 'A') continue;
    const e = await openCard(b, { admin: false, mobile: true });
    await e.page.setViewportSize({ width: w, height: 800 });
    await e.q(([w, sk, sim, neg, react, thr]) => { document.getElementById('h').style.width = w + 'px'; window.__svc = window.__svc || {};
      window.__svc['bms_komp_dec.analysis_get'] = () => ({ response: { tariff: null, cfg: {}, sim, neg, neg_reaction: react, neg_threshold: thr } }); __el._setSkin(sk); }, [w, sk, sim, neg, react, thr]);
    await e.q(() => __el.shadowRoot.querySelector('.tab[data-tab="log"]').click());
    await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('#exSimBox table'), null, { timeout: 10000 }); await sleep(300);
    const r = await e.q(() => { const sh = __el.shadowRoot, box = sh.querySelector('#exSimBox'), wr = box.querySelector('.px-tbl-wrap').getBoundingClientRect();
      const chips = [...box.querySelectorAll('.ex-chip')], notes = [...box.querySelectorAll('.px-note')];
      return { chips: chips.map(c => c.textContent.replace(/\s+/g, ' ').trim()), cls: chips.map(c => c.className), notes: notes.map(n => n.textContent.replace(/\s+/g, ' ').trim()),
        inside: chips.every(c => { const x = c.getBoundingClientRect(); return x.right <= wr.right + 2 && x.left >= wr.left - 2; }), doc: document.documentElement.scrollWidth,
        notesIn: notes.every(n => n.getBoundingClientRect().right <= wr.right + 2) }; });
    const tag = `${sk} ${w}px ${nm}`, all = r.chips.join(' | '), notes = r.notes.join(' | ');
    ok(r.inside && r.notesIn && r.doc <= w, `${tag}: chipy i podpowiedzi mieszczą się w karcie, bez przewijania w bok`);
    if (nm[0] === 'A' || nm[0] === 'B') {
      ok(/ujemna cena SPRZEDAŻY: 11 h w 4 z 10 dób/.test(all) && /38,4 kWh/.test(all) && /dopłata 7,93 zł/.test(all), `${tag}: licznik sprzedaży (godziny, kWh, dopłata)`);
      ok(/≈ 289 zł \/ rok, ekstrapolacja/.test(all), `${tag}: dopłata przeliczona na rok`);
      ok(/ujemna cena ZAKUPU: 5 h w 2 z 10 dób/.test(all) && /przychód 0,84 zł/.test(all), `${tag}: licznik zakupu`);
      ok(/Samo PV.*drożej.*godziny z ujemną ceną \(11 h sprzedaży, 5 h zakupu\).*nie błąd obliczeń/.test(all), `${tag}: ostrzeżenie wskazuje ujemne ceny jako przyczynę`);
      ok(!/błędne ceny/.test(all), `${tag}: nie straszy błędnymi cenami, gdy przyczyna jest znana`);
    }
    if (nm[0] === 'A') ok(/Włącz „Reakcja na niskie\/ujemne ceny RCE”/.test(notes), `${tag}: podpowiedź o opcji, gdy reakcja jest wyłączona`);
    if (nm[0] === 'B') ok(/jest włączona \(próg 0,05 zł\/kWh\)/.test(notes) && !/Włącz „Reakcja/.test(notes), `${tag}: reakcja włączona → bez namawiania, z progiem`);
    if (nm[0] === 'C') {
      ok(/Samo PV.*drożej.*nie widzę godzin z ujemną ceną.*błędne ceny/.test(all), `${tag}: brak ujemnych cen → wskazuje błędne ceny w danych`);
      ok(/✓ ceny ujemne: brak w ostatnich 10 dobach/.test(all), `${tag}: zielony chip „brak ujemnych cen”`);
      ok(!/Włącz „Reakcja/.test(notes), `${tag}: bez podpowiedzi o reakcji (nie ma po co)`);
    }
    if (nm[0] === 'D') {
      ok(/ujemna cena ZAKUPU/.test(all) && !/ujemna cena SPRZEDAŻY/.test(all), `${tag}: tylko licznik zakupu`);
      ok(!/Włącz „Reakcja/.test(notes) && !/drożej/.test(all), `${tag}: zakup po ujemnej cenie nie wymaga reakcji i nie ma paradoksu`);
    }
    if (nm[0] === 'E') ok(!/ujemn/.test(all + notes), `${tag}: bez liczników → żadnych chipów o ujemnych cenach`);
    await e.page.context().close();
  }
  console.log(fails ? `FAILS ${fails}` : 'OK');
  await b.close();
  process.exit(fails ? 1 : 0);
})();
