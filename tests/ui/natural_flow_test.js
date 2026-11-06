// Naturalna ścieżka: karta ładowana jak w HA (moduł po http), stany przychodzą przez hass, zakładka Wykresy klikana jak przez użytkownika.
const { chromium, openCard } = require('./ui_env.js');
const F = [0.31,0.47,0.43,0.33,0.29,0.28,0.27,0.30,0.30,0.30,0.28,0.36,0.36,0.29,0.30,0.36,0.43,0.61,0.58,0.50,0.51,0.46,0.48,0.40];
const A = [0.29,0.52,0.38,0.30,0.28,0.31,0.26,0.35,0.41,0.33,0.30,0.39,0.44,0.31,0.27].concat(Array(9).fill(null));
let PASS = 0, FAILS = 0; const check = (n, c, x) => { if (c) PASS++; else { FAILS++; console.log('FAIL:', n, x === undefined ? '' : JSON.stringify(x)); } };
const scenarios = {
  nowy_backend: { hourly_forecast: F, hourly_forecast_today: F, hourly_today: A, hourly_today_hour: 15, profiles_days: 16, history_days: 41 },
  stary_backend_bez_restartu: { hourly_forecast: F, profiles_days: 16, history_days: 41 },           // HA nie zrestartowany po wgraniu 0.6.7
  brak_atrybutow: { profiles_days: 0, history_days: 0 },                                              // as_dict() rzuciło wyjątek → pusty słownik
  profil_za_krotki: { hourly_forecast: null, hourly_forecast_today: null, profiles_days: 2, history_days: 9 },
};
(async () => {
  const browser = await chromium.launch();
  for (const [name, attrs] of Object.entries(scenarios)) {
    for (const mobile of [false, true]) {
      const { page, errs, q } = await openCard(browser, { admin: true, mobile });
      await page.waitForTimeout(400);
      // jak HA: nowy obiekt hass z dodatkowym stanem, kilka razy; potem klik w zakładkę
      await q((attrs) => { window.__states['sensor.bms_load_forecast'] = { state: '10.3', attributes: attrs, last_updated: new Date().toISOString() }; window.__el.hass = window.__mk(); }, attrs);
      await q(() => { window.__el.shadowRoot.querySelector('[data-tab=charts]').click(); });
      await page.waitForTimeout(500);
      for (let i = 0; i < 3; i++) { await q(() => { window.__el.hass = window.__mk(); }); await page.waitForTimeout(150); }
      const r = await q(() => {
        const sr = window.__el.shadowRoot; const out = {};
        for (const [k, id] of [['today', 'chartHourlyToday'], ['tomorrow', 'chartHourlyFc']]) {
          const c = sr.getElementById(id); if (!c) { out[k] = null; continue; }
          const box = c.getBoundingClientRect(); const cs = getComputedStyle(c);
          let drawn = 0; if (c.width && c.height) { const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; for (let i = 3; i < d.length; i += 4 * 17) if (d[i] > 0) drawn++; }
          const card = c.closest('.chart-card'); const title = card.querySelector('.chart-head span').textContent;
          const empty = card.querySelector('.chart-empty'); const tbl = card.querySelector('.hfc-wrap');
          out[k] = { title, w: Math.round(box.width), h: Math.round(box.height), display: cs.display, drawnPx: drawn, emptyMsg: empty ? empty.textContent.replace(/\s+/g, ' ').trim().slice(0, 110) : null,
            tblVisible: !!tbl && getComputedStyle(tbl).display !== 'none' && tbl.querySelectorAll('.hfc-tbl').length > 0, inView: card.getBoundingClientRect().height > 50 };
        }
        out.sections = [...sr.querySelectorAll('.section-title')].map(e => e.textContent).filter(t => /godzinow/i.test(t));
        out.tab = sr.querySelector('.tab.active') && sr.querySelector('.tab.active').dataset.tab;
        return out; });
      const tag = `${name}/${mobile ? 'tel' : 'pc'}`;
      console.log(tag, JSON.stringify(r));
      check(`${tag}: brak błędów JS`, errs.filter(e => !/Chart|history|net::/.test(e)).length === 0, errs);
      check(`${tag}: oba bloki istnieją w DOM`, r.today && r.tomorrow && r.sections.length === 2, r.sections);
      if (name === 'nowy_backend') {
        check(`${tag}: dziś — narysowany, widoczny`, r.today.display === 'block' && r.today.drawnPx > 200 && r.today.h > 100 && r.today.tblVisible, r.today);
        check(`${tag}: jutro — narysowany, widoczny`, r.tomorrow.display === 'block' && r.tomorrow.drawnPx > 200 && r.tomorrow.h > 100 && r.tomorrow.tblVisible, r.tomorrow);
      }
      if (name === 'stary_backend_bez_restartu') {
        check(`${tag}: jutro działa mimo starego backendu`, r.tomorrow.display === 'block' && r.tomorrow.drawnPx > 200, r.tomorrow);
        check(`${tag}: dziś pokazuje komunikat o brakującym atrybucie (nie pustkę)`, r.today.display === 'none' && /hourly_forecast_today/.test(r.today.emptyMsg || ''), r.today);
      }
      await page.context().close();
    }
  }
  await browser.close();
  console.log(`NATURAL-FLOW PASS=${PASS} FAIL=${FAILS}`); console.log(FAILS ? 'FAILS' : 'ALL OK');
})();
