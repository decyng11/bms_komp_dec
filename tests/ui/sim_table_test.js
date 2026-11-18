// Zakładka Zysk → „Symulacja roczna i zwrot z inwestycji”: tabela scenariuszy mieści się w karcie na wąskich telefonach
// (wcześniej miała min. 380 px i kolumna „Rocznie” była ucięta), chipy nie pokazują „~−”, a gdy „Samo PV” wychodzi drożej niż
// „Bez PV” (ujemne ceny / błędne dane) panel to mówi zamiast pisać zielone „PV oszczędza −2513 zł”.
// Liczby pochodzą z prawdziwego zrzutu ekranu (10 dób).
const { openCard, chromium } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const BAD = { days: 10, extrapolated: true, note: 'Szacunek.', savings_year: { pv: -2513.89, battery: 969.48, ems: 1304.55, total: -239.87 }, cfg: {},
  scenarios: [{ key: 'nopv', name: 'Bez PV i bez baterii', period: 497.08, year: 18143.42 }, { key: 'nobat', name: 'Samo PV (bez baterii)', period: 565.96, year: 20657.54 },
    { key: 'simple', name: 'PV + bateria, prosta strategia (bez planera)', period: 539.39, year: 19687.74 }, { key: 'ems', name: 'PV + bateria + EMS (rzeczywiście)', period: 503.65, year: 18383.22 }] };
const GOOD = { days: 40, extrapolated: false, note: 'Szacunek.', savings_year: { pv: 2000, battery: 800, ems: 300, total: 3100 }, payback: { pv_years: 10, battery_years: 12, total_years: 11 }, cfg: {},
  scenarios: [{ key: 'nopv', name: 'Bez PV i bez baterii', period: 400, year: 3650 }, { key: 'nobat', name: 'Samo PV (bez baterii)', period: 200, year: 1800 },
    { key: 'simple', name: 'PV + bateria, prosta strategia (bez planera)', period: 150, year: 1400 }, { key: 'ems', name: 'PV + bateria + EMS (rzeczywiście)', period: 120, year: 1100 }] };
(async () => {
  const b = await chromium.launch();
  for (const sk of ['classic', 'm3', 'glass', 'matrix', 'space', 'comfort']) for (const w of [320, 360, 390]) for (const [nm, sim] of [['bad', BAD], ['good', GOOD]]) {
    if (nm === 'good' && w !== 360) continue;
    const e = await openCard(b, { admin: false, mobile: true });
    await e.page.setViewportSize({ width: w, height: 800 });
    await e.q(([w, sk, sim]) => { document.getElementById('h').style.width = w + 'px'; window.__svc = window.__svc || {};
      window.__svc['bms_komp_dec.analysis_get'] = () => ({ response: { tariff: null, cfg: {}, sim } }); __el._setSkin(sk); }, [w, sk, sim]);
    await e.q(() => __el.shadowRoot.querySelector('.tab[data-tab="log"]').click());
    await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('#exSimBox table'), null, { timeout: 10000 }); await sleep(350);
    const r = await e.q(() => { const sh = __el.shadowRoot, box = sh.querySelector('#exSimBox'), wrap = box.querySelector('.px-tbl-wrap'), t = wrap.querySelector('table'), wr = wrap.getBoundingClientRect();
      const cells = [...t.querySelectorAll('th, td')].map(c => c.getBoundingClientRect()), chips = [...box.querySelectorAll('.ex-chip')];
      return { fit: wrap.scrollWidth <= wrap.clientWidth + 1, inside: cells.every(c => c.left >= wr.left - 1 && c.right <= wr.right + 1), doc: document.documentElement.scrollWidth,
        heads: [...t.querySelectorAll('thead th')].map(h => h.textContent.trim()), txt: chips.map(c => c.textContent.trim()), cls: chips.map(c => c.className),
        chipsIn: chips.every(c => c.getBoundingClientRect().right <= wr.right + 2) };
    });
    const tag = `${sk} ${w}px ${nm}`;
    ok(r.fit && r.inside && r.doc <= w, `${tag}: tabela symulacji mieści się w karcie bez przewijania w bok`);
    ok(r.heads.length === 3 && r.heads[2] === 'Rocznie', `${tag}: widać kolumnę „Rocznie” (${r.heads.join(' | ')})`);
    ok(!r.txt.some(t => /~/.test(t)) && !r.txt.some(t => /−\s*~|~\s*−/.test(t)), `${tag}: chipy bez „~−”`);
    ok(r.chipsIn, `${tag}: chipy mieszczą się w karcie`);
    if (nm === 'bad') {
      ok(r.txt.some(t => /Samo PV.*drożej/.test(t)), `${tag}: ostrzeżenie, że „Samo PV” wychodzi drożej niż „Bez PV”`);
      ok(/warn/.test(r.cls[0]) && /ok/.test(r.cls[1]), `${tag}: ujemne PV na żółto, dodatnia bateria na zielono`);
    } else {
      ok(!r.txt.some(t => /drożej/.test(t)) && /ok/.test(r.cls[0]), `${tag}: poprawne dane → bez ostrzeżenia, PV na zielono`);
    }
    await e.page.context().close();
  }
  console.log(fails ? `FAILS ${fails}` : 'OK');
  await b.close();
  process.exit(fails ? 1 : 0);
})();
