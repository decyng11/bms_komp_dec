// Wykres godzinowy jutra + linia „dziś” + tabela (wersja C z linią z B)
const { chromium } = require('playwright'); const fs = require('fs');
const FR = require('path').resolve(__dirname, '../../custom_components/bms_komp_dec/frontend') + '/';
const js = fs.readFileSync(FR + 'bms-panel.js', 'utf8');
const SC = require('path').join(__dirname, 'shots') + '/';
const F = [0.31,0.47,0.43,0.33,0.29,0.28,0.27,0.30,0.30,0.30,0.28,0.36,0.36,0.29,0.30,0.36,0.43,0.61,0.58,0.50,0.51,0.46,0.48,0.40];
const G = F.map((v, i) => Math.round(v * 1.1 * 100) / 100 + (i === 6 ? 0.2 : 0));   // jutro — inny kształt niż dziś
const A15 = [0.29,0.52,0.38,0.30,0.28,0.31,0.26,0.35,0.41,0.33,0.30,0.39,0.44,0.31,0.27];
const pad24 = (a) => a.concat(Array(24 - a.length).fill(null));
let PASS = 0, FAILS = 0;
const check = (n, c, x) => { if (c) PASS++; else { FAILS++; console.log('FAIL:', n, x === undefined ? '' : JSON.stringify(x)); } };

async function open(browser, width, light) {
  const ctx = await browser.newContext({ viewport: { width: width + 20, height: 900 }, deviceScaleFactor: 2, colorScheme: light ? 'light' : 'dark' });
  const page = await ctx.newPage(); const errs = [];
  page.on('pageerror', e => errs.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource|net::ERR/.test(m.text())) errs.push('console.error: ' + m.text()); });
  await page.route('**/*', r => /^(data|about):/.test(r.request().url()) ? r.continue() : r.abort());
  await page.setContent(`<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;background:${light ? '#e4e4e9' : '#000'}"><div id="host" style="width:${width}px;margin:10px"></div></body></html>`);
  await page.evaluate(() => { window.Chart = class { constructor() {} destroy() {} }; window.Chart._adapters = { _date: class { formats() { return {}; } } }; });
  await page.addScriptTag({ content: js });
  await page.evaluate((light) => {
    const S = (state, attributes = {}) => ({ state: String(state), attributes, last_updated: 'x' + state });
    const hass = { states: { 'sensor.bms_soc': S(75), 'sensor.bms_pv_power': S(0), 'sensor.bms_load_power': S(153), 'sensor.bms_battery_power': S(223), 'sensor.bms_grid_power': S(69), 'sensor.bms_reserve_soc': S(48, { capacity_kwh: 10 }) },
      entities: {}, language: 'pl', callService: () => Promise.resolve(), callWS: async () => ({}) };
    const el = document.createElement('bms-panel-card'); el.setConfig({ type: 'custom:bms-panel-card' });
    document.getElementById('host').appendChild(el); el.hass = hass; window.__el = el; window.__hass = hass;
        el.shadowRoot.querySelector('[data-tab=charts]').click();
  }, !!light);
  await page.waitForTimeout(200);
  return { page, ctx, errs };
}
// ustaw atrybuty sensora i narysuj
const setFc = (page, attrs) => page.evaluate((attrs) => {
  const el = window.__el;
  window.__hass.states['sensor.bms_load_forecast'] = { state: '9.2', attributes: Object.assign({ profiles_days: 16, history_days: 41 }, attrs), last_updated: 'q' + Math.random() };
  el.hass = Object.assign({}, window.__hass);
  window.__draws = 0; if (!el.__wrapped) { const o = el._drawHourlyForecastChart.bind(el); el._drawHourlyForecastChart = (...a) => { window.__draws++; return o(...a); }; el.__wrapped = true; }
  el._lastHourlyFcKey = null; el._renderHourlyForecastChart();
}, attrs);
const IDS = { today: ['chartHourlyToday', 'hourlyTodayTable', 'hourlyTodaySub', 'hfcLegActual'], tomorrow: ['chartHourlyFc', 'hourlyFcTable', 'hourlyFcSub', null] };
const info = (page, kind = 'today') => page.evaluate((ids) => {
  const sr = window.__el.shadowRoot; const c = sr.getElementById(ids[0]); const t = sr.getElementById(ids[1]);
  const cr = c.getBoundingClientRect();
  const blocks = [...t.querySelectorAll('.hfc-tbl')];
  const rowsTxt = blocks.map(b => { const kids = [...b.children]; const n = (kids.length / 1); return kids.map(k => k.textContent); });
  return {
    sub: sr.getElementById(ids[2]).textContent, legToday: ids[3] ? getComputedStyle(sr.getElementById(ids[3])).display : 'brak',
    canvasDisplay: c.style.display, tblDisplay: t.style.display, blocks: blocks.length, rowsTxt,
    cols: blocks.map(b => b.style.gridTemplateColumns), aria: c.getAttribute('aria-label'),
    cw: c.clientWidth, ch: c.clientHeight, cl: cr.left, ct: cr.top, emptyMsg: !!c.parentElement.querySelector('.chart-empty'),
    firstCell: blocks[0] ? (() => { const r = blocks[0].children[1].getBoundingClientRect(); return { x: r.left + r.width / 2, w: r.width }; })() : null,
    cell23: blocks[0] && blocks[0].children.length >= 25 ? (() => { const r = blocks[0].children[24].getBoundingClientRect(); return { x: r.left + r.width / 2 }; })() : null,
    html: t.innerHTML.length,
  };
}, IDS[kind]);
// kolor piksela na canvasie (px CSS)
const px = (page, x, y, kind = 'today') => page.evaluate(([x, y, id]) => { const c = window.__el.shadowRoot.getElementById(id); const d = window.devicePixelRatio || 1; const g = c.getContext('2d').getImageData(Math.round(x * d), Math.round(y * d), 1, 1).data; return [g[0], g[1], g[2], g[3]]; }, [x, y, IDS[kind][0]]);
// etykiety Wh nad słupkami rysują się na wierzchu i bywają nad środkiem kropki → szukamy koloru kropki w jej otoczeniu (±4 px)
const mint = (page, x, y, kind = 'today', col = [110, 231, 183]) => page.evaluate(([x, y, id, col]) => {
  const c = window.__el.shadowRoot.getElementById(id); const d = window.devicePixelRatio || 1; const R = 4;
  const g = c.getContext('2d').getImageData(Math.round((x - R) * d), Math.round((y - R) * d), Math.round(2 * R * d) + 1, Math.round(2 * R * d) + 1).data;
  for (let i = 0; i < g.length; i += 4) if (Math.abs(g[i] - col[0]) <= 26 && Math.abs(g[i + 1] - col[1]) <= 26 && Math.abs(g[i + 2] - col[2]) <= 26 && g[i + 3] > 200) return true;
  return false; }, [x, y, IDS[kind][0], col]);
const near = (a, b, t = 26) => Math.abs(a[0] - b[0]) <= t && Math.abs(a[1] - b[1]) <= t && Math.abs(a[2] - b[2]) <= t;
// geometria taka jak w kodzie rysującym
let LBL_W = 17;   // szerokość „000” czcionką napisów nad słupkami — mierzona w przeglądarce na starcie
const geo = (w, h, vals) => { const padL = 46, padR = 12, padB = 22; const padT = 18 + (LBL_W + 3 <= (w - padL - padR) / 24 ? 14 : Math.ceil(LBL_W) + 6); const plotW = w - padL - padR, plotH = h - padT - padB, baseY = padT + plotH, gW = plotW / 24;
  const raw = Math.max(...vals, 0.01); const x = raw * 1.06 / 4; const p = Math.pow(10, Math.floor(Math.log10(x))); const f = x / p; const step = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
  const nT = Math.max(1, Math.ceil(raw * 1.02 / step - 1e-9)); const ax = step * nT;
  return { cx: (i) => padL + (i + 0.5) * gW, y: (v) => baseY - Math.min(1, v / ax) * plotH, gW, baseY, step, ax, nT }; };

(async () => {
  const browser = await chromium.launch();
  { const mp = await browser.newPage(); LBL_W = await mp.evaluate(() => { const c = document.createElement('canvas').getContext('2d'); c.font = 'bold 10px -apple-system, sans-serif'; return c.measureText('000').width; }); await mp.close(); }

  // ===== A. szeroki, ciemny, pełne dane =====
  { const { page, errs } = await open(browser, 880);
    await setFc(page, { hourly_forecast_today: F, hourly_forecast: G, hourly_today: pad24(A15), hourly_today_hour: 15 });
    await page.waitForTimeout(100);
    const I = await info(page);
    check('A: nagłówek z sumami', I.sub === 'Dziś do 15:00: 5.1 kWh (prognoza 4.9) · cały dzień: prognoza 9.2 kWh', I.sub);
    check('A: legenda „dziś” widoczna', I.legToday !== 'none', I.legToday);
    check('A: jeden blok tabeli po 24 kolumny', I.blocks === 1 && /repeat\(24/.test(I.cols[0]), I.cols);
    const rows = I.rowsTxt[0]; // 1 blok × 4 wiersze × 25 komórek
    check('A: 4 wiersze × 25 komórek', rows.length === 100, rows.length);
    check('A: wiersz Godz. 00..23', rows.slice(1, 25).join(',') === Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0')).join(','), rows.slice(0, 25));
    check('A: wiersz Prog. w Wh (zaokr. do 10)', rows[25] === 'Prog.' && rows.slice(26, 50).join(',') === F.map(v => Math.round(v * 100) * 10).join(','), rows.slice(25, 50));
    check('A: wiersz Rzecz. — wartości i kropki dla reszty', rows[50] === 'Rzecz.' && rows[51] === '290' && rows[65] === '270' && rows[66] === '·' && rows[74] === '·', [rows[51], rows[65], rows[66]]);
    check('A: wiersz Różn. ze znakami', rows[75] === 'Różn.' && rows[76] === '−20' && rows[77] === '+50' && rows[78] === '−50' && rows[91] === '', rows.slice(75, 80));
    check('A: aria-label ze szczytem 17:00 (610 Wh) i linią', /na dziś/.test(I.aria) && /szczyt o 17:00 \(610 Wh\)/.test(I.aria) && /rzeczywiste zużycie dziś/.test(I.aria), I.aria);
    // wyrównanie tabeli z słupkami
    const g = geo(I.cw, I.ch, F.concat(A15));
    check('A: kolumna 00 w tabeli pod słupkiem 00 (±1.5 px)', Math.abs((I.firstCell.x - I.cl) - g.cx(0)) <= 1.5, [I.firstCell.x - I.cl, g.cx(0)]);
    check('A: kolumna 23 w tabeli pod słupkiem 23 (±1.5 px)', Math.abs((I.cell23.x - I.cl) - g.cx(23)) <= 1.5, [I.cell23.x - I.cl, g.cx(23)]);
    // piksele: kropki linii „dziś” w kolorze mięty w środku każdej godziny 0–14
    let ok = 0; const bad = [];
    for (let i = 0; i < 15; i++) { if (await mint(page, g.cx(i) + I.cl * 0, g.y(A15[i]))) ok++; else bad.push([i, await px(page, g.cx(i), g.y(A15[i]))]); }
    check('A: 15 kropek „dziś” w kolorze mięty', ok === 15, bad);
    // brak kropek dla przyszłych godzin: piksel w miejscu hipotetycznej kropki nie jest miętowy
    const futureBad = []; for (let i = 15; i < 24; i++) { const c = await px(page, g.cx(i), g.y(0.45)); if (near(c, [110, 231, 183])) futureBad.push(i); }
    check('A: brak linii dla godzin od 15', futureBad.length === 0, futureBad);
    // odcinek między kropkami (środek między godz. 1 i 2) w kolorze linii
    const mx = (g.cx(1) + g.cx(2)) / 2, my = (g.y(A15[1]) + g.y(A15[2])) / 2; const mc = await px(page, mx, my);
    check('A: linia łączy sąsiednie godziny', near(mc, [110, 231, 183], 30), mc);
    // słupek szczytu bursztynowy, zwykły niebieski
    const pk = await px(page, g.cx(17), g.baseY - 8), nb = await px(page, g.cx(5), g.baseY - 8);
    check('A: szczyt (17:00) bursztynowy', pk[0] > 190 && pk[1] > 100 && pk[2] < 60, pk);
    check('A: zwykła godzina (05:00) niebieska', nb[2] > 180 && nb[0] < 90, nb);
    await page.locator('bms-panel-card >> #chartHourlyToday').locator('xpath=..').screenshot({ path: SC + 'hfc_desktop_dark.png' });
    // --- wykres jutra na tej samej stronie: sama prognoza, bez linii „dziś”
    const T = await info(page, 'tomorrow'); const gT = geo(T.cw, T.ch, G);
    const gs = G.reduce((a, c) => a + c, 0).toFixed(1);
    check('A2: jutro — nagłówek bez „dziś”', T.sub === `Jutro: ${gs} kWh`, T.sub);
    check('A2: jutro — brak legendy linii', T.legToday === 'brak');
    check('A2: jutro — tabela tylko Godz. + Jutro (2 × 25), bez Rzecz./Różn.', T.rowsTxt[0].length === 50 && T.rowsTxt[0][25] === 'Jutro' && !T.rowsTxt[0].includes('Rzecz.') && !T.rowsTxt[0].includes('Różn.'), T.rowsTxt[0].slice(0, 28));
    check('A2: jutro — wartości z hourly_forecast (nie z „dziś”)', T.rowsTxt[0].slice(26, 50).join(',') === G.map(v => Math.round(v * 100) * 10).join(','), T.rowsTxt[0].slice(26, 50));
    let lineOnT = 0; for (let i = 0; i < 15; i++) { if (near(await px(page, gT.cx(i), gT.y(A15[i]), 'tomorrow'), [110, 231, 183])) lineOnT++; }
    check('A2: jutro — na wykresie nie ma miętowej linii „dziś”', lineOnT === 0, lineOnT);
    check('A2: jutro — aria „na jutro” bez wzmianki o linii', /na jutro/.test(T.aria) && !/linia/.test(T.aria), T.aria);
    check('A2: jutro — kolumna 00 tabeli pod słupkiem 00', Math.abs((T.firstCell.x - T.cl) - gT.cx(0)) <= 1.5, [T.firstCell.x - T.cl, gT.cx(0)]);
    await page.locator('bms-panel-card >> #chartHourlyFc').locator('xpath=..').screenshot({ path: SC + 'hfc_tomorrow_dark.png' });
    check('A: bez błędów JS', errs.length === 0, errs);
    await page.context().close(); }

  // ===== B. telefon, ciemny =====
  { const { page, errs } = await open(browser, 390);
    await setFc(page, { hourly_forecast_today: F, hourly_forecast: G, hourly_today: pad24(A15), hourly_today_hour: 15 });
    await page.waitForTimeout(100);
    const I = await info(page);
    check('B: typowe dane (4-znakowe różnice) na telefonie → 3 bloki po 8', I.blocks === 3 && I.cols.every(c => /repeat\(8/.test(c)), I.cols);
    check('B: bloki 1–2: 4 × 9 komórek; blok 3 (bez danych z dziś): tylko Godz. i Jutro (2 × 9)', I.rowsTxt[0].length === 36 && I.rowsTxt[1].length === 36 && I.rowsTxt[2].length === 18 && I.rowsTxt[2][9] === 'Prog.', I.rowsTxt.map(r => r.length));
    check('B: trzeci blok zaczyna od 16 i kończy na 23', I.rowsTxt[2][1] === '16' && I.rowsTxt[2][8] === '23', I.rowsTxt[2].slice(0, 9));
    check('B: tabela nie wystaje poza kartę', await page.evaluate(() => { const sr = window.__el.shadowRoot; const card = sr.getElementById('chartHourlyFc').closest('.chart-card').getBoundingClientRect(); return [...sr.querySelectorAll('.hfc-tbl > div')].every(d => { const r = d.getBoundingClientRect(); return r.right <= card.right + 0.5 && r.left >= card.left - 0.5; }); }));
    check('B: brak poziomego przewijania strony', await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
    check('B: komórki nie są ucinane (scrollWidth ≤ szerokość+1)', await page.evaluate(() => [...window.__el.shadowRoot.querySelectorAll('.hfc-tbl > div:not(.l)')].every(d => d.scrollWidth <= d.clientWidth + 1)));
    const g = geo(I.cw, I.ch, F.concat(A15)); let ok = 0;
    for (let i = 0; i < 15; i++) { if (await mint(page, g.cx(i), g.y(A15[i]))) ok++; }
    check('B: kropki „dziś” widoczne na wąskim ekranie', ok === 15, ok);
    await page.locator('bms-panel-card >> #chartHourlyToday').locator('xpath=..').screenshot({ path: SC + 'hfc_phone_dark.png' });
    check('B: bez błędów JS', errs.length === 0, errs);
    await page.context().close(); }


  // ===== B2. telefon, krótkie liczby (≤3 znaki) → 2 bloki po 12 =====
  { const { page, errs } = await open(browser, 390);
    const small = F.map(v => v * 0.8);   // maks. ≈ 490 Wh
    await setFc(page, { hourly_forecast_today: small, hourly_forecast: small, hourly_today: pad24(small.slice(0, 15).map(v => v * 0.9)), hourly_today_hour: 15 });
    const I = await info(page);
    check('B2: krótkie liczby na telefonie → 2 bloki po 12', I.blocks === 2 && I.cols.every(c => /repeat\(12/.test(c)), I.cols);
    check('B2: nic nie jest ucinane', await page.evaluate(() => [...window.__el.shadowRoot.querySelectorAll('.hfc-tbl > div:not(.l)')].every(d => d.scrollWidth <= d.clientWidth + 1)));
    await page.locator('bms-panel-card >> #chartHourlyToday').locator('xpath=..').screenshot({ path: SC + 'hfc_phone_dark_short.png' });
    check('B2: bez błędów JS', errs.length === 0, errs);
    await page.context().close(); }

  // ===== F. macierz szerokości z wartościami 4-cyfrowymi (dom z dużym zużyciem) — nic nie może być ucinane =====
  { const big = F.map((v, i) => (i >= 17 && i <= 20 ? 2.31 + i / 100 : v * 2));   // do 2.5 kWh/h
    const bigToday = pad24(big.slice(0, 15).map((v, i) => (i % 2 ? v * 0.5 : v * 1.4)));
    for (const w of [300, 330, 360, 390, 430, 520, 640, 760, 880, 1100]) {
      const { page, errs } = await open(browser, w);
      await setFc(page, { hourly_forecast_today: big, hourly_forecast: big, hourly_today: bigToday, hourly_today_hour: 15 });
      const r = await page.evaluate(() => { const sr = window.__el.shadowRoot; const cells = [...sr.querySelectorAll('.hfc-tbl > div:not(.l)')];
        const card = sr.getElementById('chartHourlyFc').closest('.chart-card').getBoundingClientRect();
        return { clipped: cells.filter(d => d.scrollWidth > d.clientWidth + 1).map(d => d.textContent + ':' + d.scrollWidth + '/' + d.clientWidth).slice(0, 4),
          outside: cells.filter(d => { const b = d.getBoundingClientRect(); return b.right > card.right + 0.5 || b.left < card.left - 0.5; }).length,
          blocks: sr.querySelectorAll('.hfc-tbl').length, fs: getComputedStyle(cells[0]).fontSize, hs: document.documentElement.scrollWidth > window.innerWidth + 1 }; });
      check(`F: ${w}px — brak ucinania (${r.blocks} bloków, ${r.fs})`, r.clipped.length === 0 && r.outside === 0 && !r.hs, r);
      check(`F: ${w}px — bez błędów JS`, errs.length === 0, errs);
      if (w === 390) await page.locator('bms-panel-card >> #chartHourlyToday').locator('xpath=..').screenshot({ path: SC + 'hfc_phone_dark_big.png' });
      await page.context().close();
    } }

  // ===== C. jasny motyw =====
  { const { page, errs } = await open(browser, 880, true);
    await setFc(page, { hourly_forecast_today: F, hourly_forecast: G, hourly_today: pad24(A15), hourly_today_hour: 15 });
    await page.waitForTimeout(100);
    const I = await info(page); const g = geo(I.cw, I.ch, F.concat(A15));
    const c = await px(page, g.cx(4), g.y(A15[4]));
    check('C: w jasnym motywie kropka ciemniejsza (#059669)', near(c, [5, 150, 105], 30), c);
    const css = await page.evaluate(() => getComputedStyle(window.__el).getPropertyValue('--hfc-today-t').trim());
    check('C: kolor tekstu „dziś” z motywu jasnego', css === '#047857', css);
    await page.locator('bms-panel-card >> #chartHourlyToday').locator('xpath=..').screenshot({ path: SC + 'hfc_desktop_light.png' });
    check('C: bez błędów JS', errs.length === 0, errs);
    await page.context().close(); }

  // ===== D. przypadki brzegowe =====
  { const { page, errs } = await open(browser, 880);
    // D1: brak danych „dziś”
    await setFc(page, { hourly_forecast_today: F, hourly_forecast: G });
    let I = await info(page);
    check('D1: sama prognoza → nagłówek bez zużycia', I.sub === 'Dziś: prognoza 9.2 kWh', I.sub);
    check('D1: legenda „rzeczywiste” ukryta', I.legToday === 'none', I.legToday);
    check('D1: tabela tylko Godz. + Prog. (2 × 25)', I.rowsTxt[0].length === 50 && I.rowsTxt[0][25] === 'Prog.', I.rowsTxt[0].length);
    // D2: luka (restart) — godz. 7 brak; nagłówek mówi o godzinach z pomiarem, linia przerwana
    const gap = A15.slice(); gap[7] = null; gap[8] = null;
    await setFc(page, { hourly_forecast_today: F, hourly_forecast: G, hourly_today: pad24(gap), hourly_today_hour: 15 });
    I = await info(page); const g = geo(I.cw, I.ch, F.concat(A15));
    check('D2: przy lukach nagłówek liczy godziny z pomiarem', /Dziś \(13 godz\. z pomiarem\): 4\.4 kWh \(prognoza /.test(I.sub), I.sub);
    const mx = (g.cx(7) + g.cx(8)) / 2, my = (g.y(A15[6]) + g.y(A15[9])) / 2; const mc = await px(page, mx, my);
    check('D2: w luce linia nie jest rysowana', !near(mc, [110, 231, 183], 30), mc);
    check('D2: kropka przed luką (godz. 6) i po (godz. 9) jest', await mint(page, g.cx(6), g.y(A15[6])) && await mint(page, g.cx(9), g.y(A15[9])));
    check('D2: tabela — luka pokazana kropką „·”', I.rowsTxt[0][50 + 1 + 7] === '·' && I.rowsTxt[0][50 + 1 + 8] === '·', I.rowsTxt[0].slice(50, 62));
    // D3: pojedynczy punkt (bez odcinka) też widoczny
    const one = Array(24).fill(null); one[3] = 0.4;
    await setFc(page, { hourly_forecast_today: F, hourly_forecast: G, hourly_today: one, hourly_today_hour: 4 });
    I = await info(page);
    check('D3: pojedynczy punkt rysowany', await mint(page, g.cx(3), g.y(0.4)));
    check('D3: nagłówek „dziś do 04:00” gdy brak luk? (1 z 4 → z pomiarem)', /Dziś \(1 godz\. z pomiarem\): 0\.4 kWh \(prognoza 0\.3\)/.test(I.sub), I.sub);
    // D4: śmieci w danych (tekst, NaN, ujemne, Infinity, HTML) → traktowane jak brak, bez wyjątku i bez wstrzyknięcia
    const junk = ['<img src=x onerror=alert(1)>', NaN, -5, Infinity, null, undefined, '0.3', {}, [], true].concat(Array(14).fill(0.3));
    await setFc(page, { hourly_forecast_today: junk.slice(0, 24).map((v, i) => i < 10 ? v : 0.35), hourly_today: junk.slice(0, 24), hourly_today_hour: 20 });
    I = await info(page);
    check('D4: brak <img> w tabeli', await page.evaluate(() => !window.__el.shadowRoot.getElementById('hourlyFcTable').querySelector('img')));
    check('D4: wartości nieliczbowe → „–”/„·”', I.rowsTxt[0][26] === '–' && I.rowsTxt[0][27] === '–' && I.rowsTxt[0][28] === '–', I.rowsTxt[0].slice(25, 30));
    check('D4: brak NaN/undefined w nagłówku i tabeli', !/NaN|undefined|Infinity/.test(I.sub + I.rowsTxt[0].join(' ')), I.sub);
    // D5: puste jutro → komunikat, wykres i tabela ukryte
    await setFc(page, { hourly_forecast_today: null, hourly_forecast: null, profiles_days: 1 });
    I = await info(page); const IT = await info(page, 'tomorrow');
    check('D5: brak prognozy → komunikat, canvas i tabela ukryte (dziś)', I.emptyMsg && I.canvasDisplay === 'none' && I.tblDisplay === 'none', [I.emptyMsg, I.canvasDisplay, I.tblDisplay]);
    check('D5: to samo na wykresie jutra', IT.emptyMsg && IT.canvasDisplay === 'none' && IT.tblDisplay === 'none', [IT.emptyMsg, IT.canvasDisplay, IT.tblDisplay]);
    await setFc(page, { hourly_forecast_today: F, hourly_forecast: G, hourly_today: pad24(A15), hourly_today_hour: 15 });
    I = await info(page);
    check('D5: po powrocie danych wykres wraca, komunikat znika', !I.emptyMsg && I.canvasDisplay === 'block' && I.tblDisplay === '', [I.emptyMsg, I.canvasDisplay, I.tblDisplay]);
    // D6: same zera jutro
    await setFc(page, { hourly_forecast_today: Array(24).fill(0), hourly_forecast: Array(24).fill(0) });
    I = await info(page);
    check('D6: same zera → traktowane jak brak danych', I.emptyMsg, I);
    // D7: atrybut hourly_today_hour spoza zakresu / nie liczba → bez podświetlenia, bez wyjątku
    await setFc(page, { hourly_forecast_today: F, hourly_forecast: G, hourly_today: pad24(A15), hourly_today_hour: 99 });
    I = await info(page);
    check('D7: hourly_today_hour=99 → nagłówek na podstawie ostatniej godziny z pomiarem', /Dziś do 15:00: 5\.1 kWh/.test(I.sub), I.sub);
    // D8: cache: ten sam stan → brak ponownego rysowania; zmiana „dziś” → rysowanie; zmiana szerokości → rysowanie
    await setFc(page, { hourly_forecast_today: F, hourly_forecast: G, hourly_today: pad24(A15), hourly_today_hour: 15 });
    const d = await page.evaluate(async () => {
      const el = window.__el; const out = {}; window.__draws = 0;
      el._renderHourlyForecastChart(); out.same = window.__draws;
      const st = window.__hass.states['sensor.bms_load_forecast'];
      st.attributes = Object.assign({}, st.attributes, { hourly_today: st.attributes.hourly_today.map((v, i) => (i === 15 ? 0.33 : v)), hourly_today_hour: 16 });
      el._renderHourlyForecastChart(); out.changed = window.__draws;
      document.getElementById('host').style.width = '700px'; await new Promise(r => setTimeout(r, 80));
      el._renderHourlyForecastChart(); out.resized = window.__draws;
      window.__draws = 0; el._lastHourlyFcKey = null; el._renderHourlyForecastChart(); out.reset = window.__draws;
      return out; });
    check('D8: ten sam stan → 0 rysowań', d.same === 0, d);
    check('D8: nowa godzina → tylko wykres „dziś” (1 rysowanie)', d.changed === 1, d);
    check('D8: zmiana szerokości → oba wykresy (razem 3)', d.resized === 3, d);
    check('D8: reset pamięci podręcznej (motyw / zakładka) → oba wykresy', d.reset === 2, d);
    // D9: _niceStep
    const ns = await page.evaluate(() => { const e = window.__el; return [0.1617, 0.0013, 0.4, 0.99, 1.2, 3.1, 7.9, 0, -1, NaN].map(v => e._niceStep(v)); });
    check('D9: _niceStep daje 1/2/5 × 10^k i bezpieczne wartości', JSON.stringify(ns) === JSON.stringify([0.2, 0.002, 0.5, 1, 2, 5, 10, 0.1, 0.1, 0.1]), ns);
    check('D: bez błędów JS', errs.length === 0, errs);
    await page.context().close(); }

  // ===== E. pośrednia szerokość (tablet 600 px) — 2 bloki, bez ucinania =====
  { const { page, errs } = await open(browser, 600);
    await setFc(page, { hourly_forecast_today: F, hourly_forecast: G, hourly_today: pad24(A15), hourly_today_hour: 15 });
    const I = await info(page);
    check('E: 600 px → 2 bloki po 12', I.blocks === 2 && /repeat\(12/.test(I.cols[0]), I.cols);
    check('E: komórki nie są ucinane', await page.evaluate(() => [...window.__el.shadowRoot.querySelectorAll('.hfc-tbl > div:not(.l)')].every(d => d.scrollWidth <= d.clientWidth + 1)));
    check('E: bez błędów JS', errs.length === 0, errs);
    await page.context().close(); }
  { const { page, errs } = await open(browser, 760);
    await setFc(page, { hourly_forecast_today: F, hourly_forecast: G, hourly_today: pad24(A15), hourly_today_hour: 15 });
    const I = await info(page);
    check('E2: 760 px (24 kolumn by się ucinało) → 2 bloki, nic nie jest ucinane', I.blocks === 2 && await page.evaluate(() => [...window.__el.shadowRoot.querySelectorAll('.hfc-tbl > div:not(.l)')].every(d => d.scrollWidth <= d.clientWidth + 1)), I.blocks);
    check('E2: bez błędów JS', errs.length === 0, errs);
    await page.context().close(); }

  await browser.close();
  console.log(`HOURLY-CHART PASS=${PASS} FAIL=${FAILS}`);
  console.log(FAILS ? 'FAILS' : 'ALL OK');
})();
