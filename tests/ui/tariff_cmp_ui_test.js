// Zysk i log → porównanie taryf: tabela z kosztem, różnicą i przeliczeniem na miesiąc; wiersze „gdyby” opisane; pola stawek zapisują się.
const { openCard, chromium } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const TARIFF = { days: 30, import_kwh: 400, note: 'Szacunek.', best: 'g11', rows: [
  { key: 'actual', name: 'Twoja obecna taryfa (rzeczywiste ceny)', cost: 360, diff: 0, per_month: 360, diff_month: 0 },
  { key: 'g11', name: 'Jedna stawka (G11) 0.90 zł/kWh', cost: 340, diff: -20, per_month: 340, diff_month: -20 },
  { key: 'top', name: 'Gdyby cały pobór wypadał w 6 najdroższych godzinach doby', cost: 440, diff: 80, per_month: 440, diff_month: 80, what_if: true },
  { key: 'low', name: 'Gdyby cały pobór wypadał w 6 najtańszych godzinach doby', cost: 300, diff: -60, per_month: 300, diff_month: -60, what_if: true }] };
(async () => {
  const b = await chromium.launch();
  for (const w of [320, 390]) {
    const e = await openCard(b, { admin: true, mobile: true });
    await e.page.setViewportSize({ width: w, height: 800 });
    await e.q((t) => { document.getElementById('h').style.width = t.w + 'px'; window.__svc = window.__svc || {};
      window.__svc['bms_komp_dec.analysis_get'] = () => ({ response: { tariff: t.tariff, cfg: { g11: 0.9 }, sim: null } });
      window.__svc['bms_komp_dec.analysis_set'] = (m) => { window.__sent = m.service_data || m; return { response: {} }; }; }, { w, tariff: TARIFF });
    await e.q(() => __el.shadowRoot.querySelector('.tab[data-tab="log"]').click());
    await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('#exSimBox table'), null, { timeout: 10000 }); await sleep(300);
    const r = await e.q(() => { const box = __el.shadowRoot.querySelector('#exSimBox'), wrap = box.querySelector('.px-tbl-wrap');
      return { rows: box.querySelectorAll('table tbody tr').length, fit: wrap.scrollWidth <= wrap.clientWidth + 1, doc: document.documentElement.scrollWidth,
        whatif: (box.textContent.match(/scenariusz, nie taryfa/g) || []).length, best: !!box.querySelector('tr.px-best'), g11: box.querySelector('#pxTg').value }; });
    ok(r.rows === 4 && r.whatif === 2 && r.best, `${w}px: 4 wiersze, 2 oznaczone jako scenariusz, najlepsza podświetlona (${JSON.stringify(r)})`);
    ok(r.fit && r.doc <= w, `${w}px: tabela mieści się bez przewijania w bok`);
    ok(r.g11 === '0.9', `${w}px: pole G11 wypełnione z ustawień`);
    if (w === 390) {
      await e.q(() => { const sh = __el.shadowRoot; sh.querySelector('#pxTzp').value = '1,2'; sh.querySelector('#pxTzo').value = '0.6'; sh.querySelector('#pxTzw').value = '6-13'; sh.querySelector('[data-px-an]').click(); });
      await sleep(400);
      const sent = await e.q(() => window.__sent);
      ok(sent && sent.zone && sent.zone.peak === 1.2 && sent.zone.off === 0.6 && sent.zone.windows === '6-13' && sent.g11 === 0.9, 'zapis wysyła taryfę strefową i G11 ' + JSON.stringify(sent));
    }
    await e.page.context().close();
  }
  console.log(fails ? `FAILS ${fails}` : 'ALL OK');
  await b.close(); process.exit(fails ? 1 : 0);
})();
