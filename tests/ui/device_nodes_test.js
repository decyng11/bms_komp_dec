// Urządzenia na ekranie głównym (wariant „satelity przy węźle dom”): ikony pokazują WYŁĄCZNIE urządzenia już dodane w zakładce
// „Urządzenia” (sensor.bms_devices), te same dane we wszystkich sześciu stylach, pełne dane w okienku po dotknięciu.
const { openCard, chromium } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const SK = ['classic', 'm3', 'glass', 'matrix', 'space', 'comfort'];
const D = (id, name, icon, p, kwh, cost, run, room) => ({ id, name, icon, category: 'x', room: room || '', power: p, today_kwh: kwh, today_cost: cost, running: run });
const D3 = [D('hp', 'Pompa ciepła', '🔥', 412, 3.84, 3.1, true, 'Kotłownia'), D('ac', 'Klimatyzacja', '❄️', 255, 0.92, 0.74, true, 'Salon'), D('bo', 'Bojler CWU', '🚿', 0, 1.2, 0.96, false)];
const D6 = D3.concat([D('ev', 'Ładowarka EV', '🚗', 0, 0, 0, false, 'Garaż'), D('pr', 'Pralka', '🧺', 0, 0.45, 0.36, false, 'Łazienka'), D('zm', 'Zmywarka', '🍽️', 1800, 0.3, 0.2, true, 'Kuchnia')]);

// ustawia stan domu i listę urządzeń (devs === undefined → brak czujnika bms_devices) oraz styl
const setup = (e, sk, devs) => e.q(([sk, devs]) => {
  const S = (v, a) => ({ state: String(v), attributes: a || {}, last_updated: new Date().toISOString(), last_changed: new Date().toISOString() });
  const st = window.__states;
  st['sensor.bms_soc'] = S(58); st['sensor.bms_pv_power'] = S(900); st['sensor.bms_load_power'] = S(747); st['sensor.bms_grid_power'] = S(11); st['sensor.bms_battery_power'] = S(-200);
  st['sensor.bms_energy_pv_today'] = S(2.4); st['sensor.bms_energy_load_today'] = S(5.2); st['sensor.bms_energy_grid_import_today'] = S(1.9); st['sensor.bms_energy_grid_export_today'] = S(0);
  st['sensor.bms_energy_battery_charge_today'] = S(2.8); st['sensor.bms_energy_battery_discharge_today'] = S(4.5);
  st['sensor.bms_reserve_soc'] = S(20, { price_buy: 1.29, price_sell: 0.305, capacity_kwh: 12.6, inverter_floor: 20 });
  if (devs === undefined || devs === null) delete st['sensor.bms_devices']; else st['sensor.bms_devices'] = S(devs.length, { devices: devs, power_total: 0 });
  __el.hass = __mk(); __el._setTheme('dark'); __el._setSkin(sk);
}, [sk, devs]);
const setDevs = (e, devs) => e.q((devs) => { const st = window.__states; st['sensor.bms_devices'] = { state: String(devs.length), attributes: { devices: devs }, last_updated: new Date().toISOString(), last_changed: new Date().toISOString() }; __el.hass = __mk(); }, devs);
// opis satelitów widoczny na schemacie: aria-label każdego węzła (nazwa: moc[, pracuje]) i klucze obszarów dotyku
const view = (e) => e.q(() => { const box = __el.shadowRoot.getElementById('nodesBox');
  return { labels: [...box.querySelectorAll('.nf-dv')].map(g => g.getAttribute('aria-label')), on: box.querySelectorAll('.nf-dv.on').length,
    hits: [...box.querySelectorAll('.nf-hit')].map(h => h.dataset.k).filter(k => k.startsWith('dev:')), txt: box.innerText }; });
const tap = (e, key) => e.q(async (key) => { const h = [...__el.shadowRoot.querySelectorAll('#nodesBox .nf-hit')].find(x => x.dataset.k === key); if (!h) return false; const r = h.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; }, key)
  .then(async (p) => { if (!p) return false; await e.page.mouse.click(p.x, p.y); await sleep(350); return true; });
const pop = (e) => e.q(() => { const p = __el.shadowRoot.getElementById('nodePop'); return { hidden: p.hidden, text: p.innerText, pin: p.classList.contains('pin'), go: !!p.querySelector('.np-go'), goShown: !!p.querySelector('.np-go') && getComputedStyle(p.querySelector('.np-go')).display !== 'none' }; });

(async () => {
  const b = await chromium.launch();

  // ---- nic nie dodano → nic na schemacie (brak czujnika i pusta lista), schemat klasyczny ma dotychczasową wysokość
  for (const [what, devs] of [['brak czujnika bms_devices', undefined], ['pusta lista urządzeń', []]]) for (const sk of SK) {
    const e = await openCard(b, { admin: false });
    await setup(e, sk, devs); await sleep(500);
    const v = await view(e);
    ok(v.labels.length === 0 && v.hits.length === 0, `${sk}, ${what}: brak satelitów i obszarów dotyku`);
    if (sk === 'classic') ok(await e.q(() => / 380$/.test(__el.shadowRoot.querySelector('#nodesBox svg').getAttribute('viewBox'))), `classic, ${what}: schemat bez zmian (wysokość 380)`);
    await e.page.context().close();
  }

  // ---- trzy urządzenia: te same dane we wszystkich stylach
  const ref = {};
  for (const sk of SK) {
    const e = await openCard(b, { admin: false });
    await setup(e, sk, D3); await sleep(600);
    const v = await view(e); ref[sk] = v;
    ok(v.labels.length === 3 && v.on === 2 && v.hits.join() === 'dev:hp,dev:ac,dev:bo', `${sk}: 3 satelity (2 pracują), obszary dotyku dla każdego: ${v.hits}`);
    ok(/Pompa ciepła: 412 W, pracuje/.test(v.labels[0]) && /Klimatyzacja: 255 W, pracuje/.test(v.labels[1]) && /Bojler CWU: 0 W$/.test(v.labels[2]), `${sk}: nazwa i moc w opisie (${v.labels.join(' | ')})`);
    ok(/🔥/.test(v.txt) && /❄/.test(v.txt) && /🚿/.test(v.txt), `${sk}: ikony urządzeń widoczne na schemacie`);
    ok(await e.q(() => ['pv', 'home', 'grid', 'batt'].every(k => __el.shadowRoot.querySelectorAll(`#nodesBox .nf-hit[data-k="${k}"]`).length === 1)), `${sk}: cztery główne węzły nadal klikalne`);
    await e.page.context().close();
  }
  ok(SK.every(sk => JSON.stringify(ref[sk].labels) === JSON.stringify(ref.classic.labels)), 'wszystkie style: identyczne opisy satelitów (nazwa, moc, stan)');

  // ---- okienko po dotknięciu: te same dane co kafelek w zakładce Urządzenia
  for (const sk of SK) {
    const e = await openCard(b, { admin: false, mobile: true });
    await setup(e, sk, D3); await sleep(600);
    ok(await tap(e, 'dev:hp'), `${sk}: dotknięcie ikony „Pompa ciepła”`);
    const p = await pop(e);
    ok(!p.hidden && p.pin && /Pompa ciepła/.test(p.text) && /pracuje/.test(p.text) && /412 W/.test(p.text) && /3,84 kWh/.test(p.text) && /3,10 zł/.test(p.text) && /Kotłownia/.test(p.text), `${sk}: okienko — nazwa, „pracuje”, 412 W, 3,84 kWh, 3,10 zł, pokój`);
    ok(p.go && p.goShown, `${sk}: przycisk „Wszystkie urządzenia” widoczny po przypięciu okienka`);
    await tap(e, 'dev:bo');
    const p2 = await pop(e);
    ok(/Bojler CWU/.test(p2.text) && /nie pracuje/.test(p2.text) && /1,20 kWh/.test(p2.text) && /0,96 zł/.test(p2.text) && !/Pokój/.test(p2.text), `${sk}: urządzenie bez pokoju i w spoczynku: „nie pracuje”, 1,20 kWh, 0,96 zł, bez wiersza Pokój`);
    await e.page.context().close();
  }

  // ---- „Wszystkie urządzenia →” przechodzi do zakładki Urządzenia; w trybie prostym przycisku nie ma
  {
    const e = await openCard(b, { admin: false, mobile: true });
    await setup(e, 'classic', D3); await sleep(500);
    await tap(e, 'dev:ac');
    await e.q(() => __el.shadowRoot.querySelector('#nodePop .np-go').click()); await sleep(600);
    ok(await e.q(() => __el.shadowRoot.querySelector('.tab[data-tab="dev"]').classList.contains('active')), 'przycisk „Wszystkie urządzenia” otwiera zakładkę Urządzenia');
    ok(await e.q(() => __el.shadowRoot.getElementById('nodePop').hidden), 'po przejściu okienko się zamyka');
    await e.q(() => { __el._laySimple = () => true; __el._hidePop(); });
    await e.q(() => __el.shadowRoot.querySelector('.tab[data-tab="main"]').click()); await sleep(400);
    await tap(e, 'dev:ac');
    ok(!(await pop(e)).go, 'tryb prosty (zakładka Urządzenia ukryta): okienko bez przycisku przejścia');
    await e.page.context().close();
  }

  // ---- więcej niż 4: trzy urządzenia + „+N”; pracujące mają pierwszeństwo, reszta w okienku
  for (const sk of SK) {
    const e = await openCard(b, { admin: false, mobile: true });
    await setup(e, sk, D6); await sleep(600);
    const v = await view(e);
    ok(v.hits.length === 4 && v.hits[3] === 'dev:+', `${sk}: 6 urządzeń → 3 węzły + „+3” (${v.hits})`);
    ok(v.hits.includes('dev:zm') && v.hits.includes('dev:hp') && v.hits.includes('dev:ac'), `${sk}: pracujące urządzenia (w tym ostatnie z listy) są na schemacie, nie w „+3”`);
    await tap(e, 'dev:+');
    const p = await pop(e);
    ok(/Pozostałe urządzenia \(3\)/.test(p.text) && /Bojler CWU/.test(p.text) && /Ładowarka EV/.test(p.text) && /Pralka/.test(p.text) && /0,45 kWh/.test(p.text) && /0,36 zł/.test(p.text) && !/Pompa ciepła/.test(p.text), `${sk}: okienko „+3” wylicza pozostałe z kWh i zł`);
    await e.page.context().close();
  }
  {
    const e = await openCard(b, { admin: false });
    await setup(e, 'classic', D6.slice(0, 4)); await sleep(500);
    ok((await view(e)).hits.join() === 'dev:hp,dev:ac,dev:bo,dev:ev', 'dokładnie 4 urządzenia: wszystkie na schemacie, bez „+N”');
    await e.page.context().close();
  }

  // ---- zmiana na żywo: moc, stan, usunięcie urządzenia (okienko się odświeża / zamyka)
  for (const sk of ['classic', 'm3', 'glass']) {
    const e = await openCard(b, { admin: false, mobile: true });
    await setup(e, sk, D3); await sleep(500);
    await tap(e, 'dev:hp'); await e.page.mouse.move(2, 2);          // kursor poza schematem (po zmianie układu pod kursorem pojawiłby się inny węzeł)
    await setDevs(e, [D('hp', 'Pompa ciepła', '🔥', 1230, 4.1, 3.3, true, 'Kotłownia'), D3[1], D3[2]]); await sleep(700);
    ok((await view(e)).labels[0].includes('1,23 kW'), `${sk}: zmiana mocy na żywo (1,23 kW)`);
    const p = await pop(e);
    ok(!p.hidden && /1,23 kW/.test(p.text) && /4,10 kWh/.test(p.text) && /3,30 zł/.test(p.text), `${sk}: otwarte okienko odświeża się razem ze schematem`);
    await setDevs(e, [D('hp', 'Pompa ciepła', '🔥', 0, 4.1, 3.3, false, 'Kotłownia'), D3[1], D3[2]]); await sleep(700);
    ok((await view(e)).on === 1 && /nie pracuje/.test((await pop(e)).text), `${sk}: pompa przestaje pracować → 1 pracujący węzeł, okienko: „nie pracuje”`);
    await setDevs(e, [D3[1], D3[2]]); await sleep(700);
    ok((await view(e)).hits.join() === 'dev:ac,dev:bo' && (await pop(e)).hidden, `${sk}: urządzenie usunięte → znika ze schematu, okienko się zamyka`);
    await setDevs(e, []); await sleep(600);
    ok((await view(e)).hits.length === 0, `${sk}: usunięto wszystkie urządzenia → schemat bez satelitów`);
    ok(e.errs.length === 0, `${sk}: bez błędów w konsoli` + (e.errs.length ? ' · ' + e.errs.slice(0, 2).join(' | ') : ''));
    await e.page.context().close();
  }

  // ---- brak mocy (czujnik niedostępny) → „—”; dziwny identyfikator i nazwa z HTML nie psują schematu
  {
    const e = await openCard(b, { admin: false, mobile: true });
    await setup(e, 'classic', [D('a"b\'c <d>', '<b>Grzejnik</b> & "Co"', '🔌', null, null, null, false), D('x', 'Drugie', '💡', 12, 0.1, 0.08, false)]); await sleep(600);
    const v = await view(e);
    ok(v.hits.length === 2 && /—/.test(v.labels[0]) && /<b>Grzejnik<\/b>/.test(v.labels[0]), 'brak mocy: „—”, nazwa z HTML nie jest interpretowana: ' + v.labels[0]);
    ok(await tap(e, 'dev:a"b\'c <d>'), 'identyfikator ze znakami specjalnymi: dotknięcie działa');
    const p = await pop(e);
    ok(!p.hidden && /<b>Grzejnik<\/b> & "Co"/.test(p.text) && /—/.test(p.text), 'okienko pokazuje nazwę dosłownie, a brakujące dane jako „—”: ' + p.text.replace(/\n/g, ' ').slice(0, 120));
    ok(e.errs.length === 0, 'bez błędów w konsoli');
    await e.page.context().close();
  }

  // ---- geometria: teksty nie nakładają się, satelity mieszczą się w ramce schematu i nie wchodzą w pierścień baterii (telefon i szeroki ekran)
  for (const mobile of [true, false]) for (const sk of SK) for (const n of [4, 2]) {
    const e = await openCard(b, { admin: false, mobile });
    await setup(e, sk, D6.slice(0, n)); await sleep(700);
    const g = await e.q(() => {
      const box = __el.shadowRoot.getElementById('nodesBox'), svg = box.querySelector('svg'), sr = svg.getBoundingClientRect();
      const ts = [...svg.querySelectorAll('text')].map(t => ({ r: t.getBoundingClientRect(), s: t.textContent })).filter(x => x.r.width > 0);
      const bad = []; for (let i = 0; i < ts.length; i++) for (let j = i + 1; j < ts.length; j++) { const a = ts[i].r, c = ts[j].r;
        const w = Math.min(a.right, c.right) - Math.max(a.left, c.left), h = Math.min(a.bottom, c.bottom) - Math.max(a.top, c.top); if (w > 1 && h > 1.5) bad.push(ts[i].s + ' × ' + ts[j].s); }
      const out = [...svg.querySelectorAll('.nf-dv')].filter(g => { const r = g.getBoundingClientRect(); return r.left < sr.left - 1 || r.right > sr.right + 1 || r.bottom > sr.bottom + 1 || r.top < sr.top - 1; }).length;
      const bg = svg.querySelector('.nf-bg'); let ring = 0;
      if (bg) { const rr = bg.getBoundingClientRect(); const cx = rr.x + rr.width / 2, cy = rr.y + rr.height / 2, R = rr.width / 2;
        ring = [...svg.querySelectorAll('.nf-dv circle')].filter(c => { const r = c.getBoundingClientRect(); const dx = r.x + r.width / 2 - cx, dy = r.y + r.height / 2 - cy; return Math.hypot(dx, dy) < R + r.width / 2; }).length; }
      return { n: ts.length, bad, out, ring };
    });
    ok(!g.bad.length && !g.out && !g.ring, `${sk} (${mobile ? 'telefon' : 'szeroki'}, ${n} urz.): bez nakładania tekstów (${g.n}), w ramce schematu, poza pierścieniem baterii` + (g.bad.length ? ' · ' + g.bad.join('; ') : '') + (g.out ? ' · poza ramką: ' + g.out : '') + (g.ring ? ' · w pierścieniu: ' + g.ring : ''));
    await e.page.context().close();
  }

  console.log(fails ? `FAILS ${fails}` : 'OK');
  await b.close();
  process.exit(fails ? 1 : 0);
})();
