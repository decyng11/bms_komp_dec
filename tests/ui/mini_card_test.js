// Mała karta „bms-mini-card” (do dashboardu HA) i opis „Co EMS planuje na najbliższe 24 h”
const { openCard, chromium } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, { mobile: true, admin: false });
  const q = (f, a) => e.q(f, a);
  // plan względem „teraz”: PV 0–2 h, bateria zasila dom 3–6, sieć 7–9, sprzedaż 12–14, reszta bez zmian
  await q(() => {
    const d0 = new Date(); d0.setMinutes(0, 0, 0);
    const dk = (d) => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
    const rows = []; let soc = 50;
    for (let i = 0; i < 30; i++) {
      const d = new Date(d0.getTime() + i * 3600e3), h = d.getHours();
      let action = 'idle', label = 'Bez zmian', ds = 0, imp = 0, exp = 0, cost = 0;
      if (i <= 2) { action = 'pv'; label = 'Ładuj z PV'; ds = 5; }
      else if (i <= 6) { action = 'home'; label = 'Bateria zasila dom'; ds = -3; }
      else if (i <= 9) { action = 'grid'; label = 'Ładuj z sieci'; ds = 6; imp = 3; cost = 2.1; }
      else if (i >= 12 && i <= 14) { action = 'sell'; label = 'Sprzedaj z baterii'; ds = -7; exp = 2; cost = -1.5; }
      soc = Math.max(20, Math.min(100, soc + ds));
      rows.push({ t: d.toISOString(), h, day: dk(d), action, label, peak: false, buy: 0.7, sell: 0.5, pv: 0, load: 0.5, soc, floor: 20, import_kwh: imp, export_kwh: exp, cost });
    }
    const t0 = new Date().toISOString();
    __states['sensor.bms_plan_view'] = { state: 'pv', attributes: { table: rows, generated_at: t0 }, last_updated: t0, last_changed: t0 };
    window.__rows = rows;
    __el.style.display = 'none';
    const m = document.createElement('bms-mini-card'); m.setConfig({ title: 'Mój dom <img src=x onerror="window.__xss=1">' }); document.getElementById('h').appendChild(m); m.hass = __mk(); window.__mini = m;
  });
  await sleep(500);
  const sh = (sel) => q((sel) => { const x = __mini.shadowRoot.querySelector(sel); return x ? x.textContent.replace(/\s+/g, ' ').trim() : null; }, sel);
  ok(await q(() => !!customElements.get('bms-mini-card') && window.customCards.some(c => c.type === 'bms-mini-card')), 'karta zarejestrowana w HA (customElements + customCards)');
  ok(/67/.test(await sh('.mini-ring')) && await q(() => __mini.shadowRoot.querySelectorAll('.mini-n').length === 4), 'pierścień baterii (67%) i cztery wartości mocy');
  ok(/3,2 kW/.test(await sh('.mini-nums')) && /1,1 kW/.test(await sh('.mini-nums')), 'moce PV i domu w kW');
  ok(await q(() => __mini.shadowRoot.querySelectorAll('.mini-strip i').length === 24), 'pasek planu: 24 godziny');
  ok(await q(() => __mini.shadowRoot.querySelector('.mini-strip i.now') === __mini.shadowRoot.querySelector('.mini-strip i')), 'pasek planu: pierwsza kolumna oznaczona jako „teraz”');
  // opis planu — godziny liczone tak samo jak w karcie, niezależnie od strefy czasowej
  const exp = await q(() => { const hh = (i) => String(new Date(__rows[i].t).getHours()).padStart(2, '0') + ':00'; const dk = (i) => __rows[i].day; const T = __el._todayKey(), M = __el._tomorrowKey();
    const pre = (i) => dk(i) === T ? '' : (dk(i) === M ? 'jutro ' : ''); return { pv: `teraz–${hh(3)} (3 h)`, grid: `${pre(7)}${hh(7)}–${hh(10)} (3 h)`, sell: `${pre(12)}${hh(12)}–${hh(15)} (3 h)` }; });
  const text = await sh('.ps');
  ok(text.includes('Co EMS planuje na najbliższe 24 h'), 'opis planu: nagłówek');
  ok(text.includes('Ładowanie z PV: ' + exp.pv), 'opis planu: ładowanie z PV — ' + exp.pv);
  ok(text.includes('Ładowanie z sieci: ' + exp.grid), 'opis planu: ładowanie z sieci — ' + exp.grid);
  ok(text.includes('Sprzedaż z baterii: ' + exp.sell), 'opis planu: sprzedaż z baterii — ' + exp.sell);
  ok(/Bateria: najniżej \d+% \(.*\), na koniec okresu \d+%/.test(text), 'opis planu: SOC najniżej i na koniec okresu');
  ok(/Szacunek: koszt 1,80 zł · pobór 9,0 kWh, oddanie 6,0 kWh/.test(text), 'opis planu: szacunek kosztu i energii: ' + (text.match(/Szacunek:[^T]*/) || [''])[0]);
  ok(/przelicza plan na bieżąco/.test(text), 'opis planu: zastrzeżenie, że to szacunek');
  // fragmenty planu: nic nie planuje → czytelny tekst; kilka okien → „i jeszcze”
  const edge = await q(() => {
    const t = (rows) => { const d = document.createElement('div'); d.innerHTML = __mini._planSummaryHtml(rows); return d.textContent.replace(/\s+/g, ' '); };
    const base = window.__rows.map(r => Object.assign({}, r, { action: 'home', label: 'x', cost: 0, import_kwh: 0, export_kwh: 0 }));
    const many = window.__rows.map((r, i) => Object.assign({}, r, { action: i % 2 ? 'home' : 'grid' }));
    const past = window.__rows.map(r => Object.assign({}, r, { t: new Date(Date.parse(r.t) - 72 * 3600e3).toISOString() }));
    return { none: t(base), many: t(many), empty: __mini._planSummaryHtml([]), junk: __mini._planSummaryHtml([null, {}, { t: 'x' }, { t: window.__rows[0].t, soc: 'abc', cost: null }]), past: __mini._planSummaryHtml(past) };
  });
  ok(/Ładowanie z sieci: nie planuje/.test(edge.none) && /Sprzedaż z baterii: nie planuje/.test(edge.none) && /bilans około 0 zł/.test(edge.none), 'brak ładowania i sprzedaży: „nie planuje”, bilans około 0 zł');
  ok(/i jeszcze \d+/.test(edge.many), 'wiele okien: pierwsze trzy i „i jeszcze N”');
  ok(edge.empty === '' && edge.past === '', 'pusty plan albo plan z przeszłości: brak opisu (bez błędu)');
  ok(typeof edge.junk === 'string' && !/NaN|undefined/.test(edge.junk), 'śmieci w danych planu: bez NaN / undefined');
  // bezpieczeństwo
  ok(await q(() => !window.__xss) && (await sh('.mini-t')).includes('<img'), 'tytuł z HTML jest wyświetlony jako tekst, nic się nie wykonuje');
  // motyw i styl z przeglądarki
  ok(await q(() => __mini.hasAttribute('data-theme')), 'karta ma motyw (jasny/ciemny)');
  await q(() => { __el._setSkin('glass', true); __mini.hass = __mk(); });
  ok(await q(() => __mini.getAttribute('data-skin') === 'glass'), 'karta stosuje wybrany styl panelu');
  // nawigacja
  await q(() => { window.__nav = []; window.addEventListener('location-changed', () => window.__nav.push(location.pathname)); __mini.setConfig({ title: 'Dom', navigation_path: '/lovelace/ems' }); });
  await q(() => __mini.shadowRoot.querySelector('.mini').click());
  ok(await q(() => window.__nav.length === 1 && window.__nav[0] === '/lovelace/ems'), 'navigation_path: klik otwiera wskazany widok');
  await q(() => __mini.setConfig({ title: 'Dom' }));
  await q(() => { window.__nav = []; __mini.shadowRoot.querySelector('.mini').click(); });
  ok(await q(() => window.__nav.length === 0 && !__mini.shadowRoot.querySelector('.mini').hasAttribute('data-nav')), 'bez navigation_path: karta nie jest klikalna');
  // opcje
  await q(() => __mini.setConfig({ show_summary: false, show_strip: false, show_flow: false }));
  ok(await q(() => !__mini.shadowRoot.querySelector('.ps') && !__mini.shadowRoot.querySelector('.mini-strip') && !__mini.shadowRoot.querySelector('.mini-nums') && !!__mini.shadowRoot.querySelector('.mini-ring')), 'show_summary / show_strip / show_flow: false chowają części, pierścień zostaje');
  // brak planu i brak danych EMS
  await q(() => { __mini.setConfig({}); delete __states['sensor.bms_plan_view']; __mini.hass = __mk(); });
  ok(/Plan jeszcze nie jest policzony/.test(await sh('.ps')), 'bez planu: komunikat zamiast pustego miejsca');
  await q(() => { for (const k of Object.keys(__states)) delete __states[k]; __mini.hass = __mk(); });
  ok(/Brak danych EMS/.test(await sh('.mini-empty')), 'bez danych EMS: czytelny komunikat');
  ok(e.errs.length === 0, 'brak błędów w konsoli: ' + JSON.stringify(e.errs));
  await b.close();
  console.log(fails ? `\n${fails} niepowodzeń` : '\nOK'); process.exit(fails ? 1 : 0);
})();
