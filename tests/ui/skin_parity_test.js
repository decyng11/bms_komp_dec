// Zgodność danych między stylami: klasyczny, Material 3, Szkło, Matryca, Przestrzeń i Komfort pokazują na ekranie głównym
// TEN SAM zestaw informacji (liczby i etykiety) — różni się tylko sposób rysowania. Test pilnuje, żeby nowy styl lub zmiana
// w jednym stylu nie zgubiła np. strat falownika, „Do rezerwy”, zysku dziś, dziennych kWh przy węzłach czy pola pojemności baterii.
const { openCard, chromium } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const SK = ['classic', 'm3', 'glass', 'matrix', 'space', 'comfort', 'hero'];
const SC = {
  'ładowanie z PV i sprzedaż': { soc: 48, pv: 2100, load: 1240, grid: -800, batt: -403 },
  'import, bateria w spoczynku': { soc: 71, pv: 0, load: 1240, grid: 1240, batt: 0 },
  'moc sieci poniżej 20 W': { soc: 48, pv: 39, load: 486, grid: 10, batt: -403 },
  'wartości graniczne 1 kW': { soc: 99.6, pv: 999, load: 1000, grid: 1001, batt: -1000 },
};
// liczby (bez jednostek: Matryca rysuje jednostkę osobno) z tekstu widocznego, wartości aria-label i paska cen
const TOK = () => {
  const s = __el.shadowRoot, tc = s.querySelector('[data-tab-content="main"]');
  const pb = s.getElementById('priceBar');
  const txt = [(tc.innerText || ''), pb ? pb.innerText : '', ...[...tc.querySelectorAll('svg[aria-label]')].map(n => n.getAttribute('aria-label'))].join('\n').toLowerCase();
  const nums = new Set((txt.match(/\d+(?:[.,]\d+)?/g) || []).map(x => x.replace(',', '.')).map(x => String(+x)));
  const flow = s.querySelector('[data-tile="main-flow"]');
  const labels = (flow.innerText + '\n' + [...flow.querySelectorAll('svg[aria-label]')].map(n => n.getAttribute('aria-label')).join('\n')).toLowerCase();
  const dots = /\d\.\d+\s?(kwh|kw|zł)/.test(txt);
  return { nums: [...nums], labels, dots, txt };
};
(async () => {
  const b = await chromium.launch();
  for (const [sn, sc] of Object.entries(SC)) {
    const e = await openCard(b, { admin: false });
    await e.q((sc) => {
      const S = (v, a) => ({ state: String(v), attributes: a || {}, last_updated: new Date().toISOString(), last_changed: new Date().toISOString() });
      const st = window.__states;
      st['sensor.bms_soc'] = S(sc.soc); st['sensor.bms_pv_power'] = S(sc.pv); st['sensor.bms_load_power'] = S(sc.load); st['sensor.bms_grid_power'] = S(sc.grid); st['sensor.bms_battery_power'] = S(sc.batt);
      st['sensor.bms_energy_pv_today'] = S(12.4); st['sensor.bms_energy_load_today'] = S(9.8); st['sensor.bms_energy_grid_import_today'] = S(3.1); st['sensor.bms_energy_grid_export_today'] = S(5.2);
      st['sensor.bms_energy_battery_charge_today'] = S(4.1); st['sensor.bms_energy_battery_discharge_today'] = S(3.6); st['sensor.bms_profit_today'] = S(4.22);
      st['sensor.bms_reserve_soc'] = S(30, { price_buy: 1.29, price_sell: 0.305, capacity_kwh: 10, inverter_floor: 25 });
      __el.hass = __mk(); __el._setTheme('dark');
    }, sc);
    const R = {};
    for (const sk of SK) { await e.q((sk) => __el._setSkin(sk), sk); await sleep(500); R[sk] = await e.q(TOK); }
    const base = new Set(R.classic.nums);
    for (const sk of SK.slice(1)) {
      const have = new Set(R[sk].nums);
      const miss = [...base].filter(x => !have.has(x)), extra = [...have].filter(x => !base.has(x));
      ok(!miss.length && !extra.length, `[${sn}] ${sk}: te same liczby co w klasycznym` + (miss.length ? ' · brakuje: ' + miss.join(',') : '') + (extra.length ? ' · nadmiarowe: ' + extra.join(',') : ''));
    }
    for (const sk of SK) {
      const L = R[sk].labels;
      const need = ['do rezerwy 25%', 'przy tym tempie', 'straty falownika', 'zysk dziś', 'dziś 12,4 kwh', 'dziś 9,8 kwh', '↓3,1', '↑5,2', '↓4,1', '↑3,6'];
      const miss = need.filter(x => !L.includes(x));
      ok(!miss.length, `[${sn}] ${sk}: komplet etykiet i dziennych kWh` + (miss.length ? ' · brakuje: ' + miss.join(' | ') : ''));
      ok(!R[sk].dots, `[${sn}] ${sk}: liczby z przecinkiem (bez „12.4 kWh”)`);
    }
  }

  // urządzenia dodane w zakładce „Urządzenia”: te same liczby, ikony i nazwy w opisie węzłów we wszystkich stylach
  {
    const e = await openCard(b, { admin: false });
    await e.q(() => {
      const S = (v, a) => ({ state: String(v), attributes: a || {}, last_updated: new Date().toISOString(), last_changed: new Date().toISOString() });
      const st = window.__states;
      st['sensor.bms_soc'] = S(48); st['sensor.bms_pv_power'] = S(2100); st['sensor.bms_load_power'] = S(1240); st['sensor.bms_grid_power'] = S(-800); st['sensor.bms_battery_power'] = S(-403);
      st['sensor.bms_reserve_soc'] = S(30, { price_buy: 1.29, price_sell: 0.305, capacity_kwh: 10, inverter_floor: 25 });
      st['sensor.bms_devices'] = S(3, { devices: [
        { id: 'hp', name: 'Pompa ciepła', icon: '🔥', category: 'x', room: 'Kotłownia', power: 412, today_kwh: 3.84, today_cost: 3.1, running: true },
        { id: 'ac', name: 'Klimatyzacja', icon: '❄️', category: 'x', room: '', power: 255, today_kwh: 0.92, today_cost: 0.74, running: true },
        { id: 'bo', name: 'Bojler CWU', icon: '🚿', category: 'x', room: '', power: 0, today_kwh: 1.2, today_cost: 0.96, running: false }] });
      __el.hass = __mk(); __el._setTheme('dark');
    });
    const R = {};
    for (const sk of SK) { await e.q((sk) => __el._setSkin(sk), sk); await sleep(500); R[sk] = await e.q(TOK); R[sk].dv = await e.q(() => [...__el.shadowRoot.querySelectorAll('#nodesBox .nf-dv')].map(g => g.getAttribute('aria-label')).join(' | ')); }
    const base = new Set(R.classic.nums);
    for (const sk of SK.slice(1)) {
      const have = new Set(R[sk].nums), miss = [...base].filter(x => !have.has(x)), extra = [...have].filter(x => !base.has(x));
      ok(!miss.length && !extra.length, `urządzenia: ${sk} ma te same liczby co klasyczny` + (miss.length ? ' · brakuje: ' + miss.join(',') : '') + (extra.length ? ' · nadmiarowe: ' + extra.join(',') : ''));
    }
    ok(['412', '255'].every(x => base.has(x)), 'urządzenia: moce 412 W i 255 W są na schemacie');
    ok(SK.every(sk => R[sk].dv === R.classic.dv && R.classic.dv.split(' | ').length === 3), 'urządzenia: identyczny opis trzech satelitów we wszystkich stylach');
    await e.page.context().close();
  }

  // moc sieci 10 W: M3 pokazuje rzeczywistą wartość, a nie „0 W”
  {
    const e = await openCard(b, { admin: false });
    await e.q(() => { const S = (v, a) => ({ state: String(v), attributes: a || {}, last_updated: new Date().toISOString(), last_changed: new Date().toISOString() }); const st = window.__states;
      st['sensor.bms_soc'] = S(50); st['sensor.bms_pv_power'] = S(39); st['sensor.bms_load_power'] = S(486); st['sensor.bms_grid_power'] = S(10); st['sensor.bms_battery_power'] = S(-403); __el.hass = __mk(); __el._setSkin('m3'); });
    await sleep(600);
    ok(await e.q(() => /sieć 10 W/.test(__el.shadowRoot.querySelector('.m3-flow').innerText)), 'M3: sieć 10 W pokazana jako 10 W (nie „0 W”)');
    await e.page.context().close();
  }

  // brak czujnika zysku: „—” zamiast „+0,00 zł”; zysk ujemny z minusem
  {
    const e = await openCard(b, { admin: false });
    await e.q(() => { delete window.__states['sensor.bms_profit_today']; __el.hass = __mk(); __el._setSkin('glass'); });
    await sleep(600);
    ok(await e.q(() => { const k = [...__el.shadowRoot.querySelectorAll('.sk-kpi')].find(n => /zysk/i.test(n.textContent)); return !!k && /—/.test(k.querySelector('.v').textContent) && !/0,00/.test(k.textContent); }), 'brak czujnika zysku: kafelek pokazuje „—”, nie „+0,00 zł”');
    await e.q(() => { window.__states['sensor.bms_profit_today'] = { state: '-1.5', attributes: {}, last_updated: new Date().toISOString(), last_changed: new Date().toISOString() }; __el.hass = __mk(); });
    await sleep(600);
    ok(await e.q(() => /−1,50 zł/.test([...__el.shadowRoot.querySelectorAll('.sk-kpi')].find(n => /zysk/i.test(n.textContent)).textContent)), 'zysk ujemny: „−1,50 zł”');
    await e.page.context().close();
  }

  // pole pojemności baterii: jest w każdym stylu, wpisanie wartości dokłada „Do rezerwy” i zapisuje pojemność
  for (const sk of SK) {
    const e = await openCard(b, { admin: false });
    await e.q((sk) => { try { localStorage.removeItem('bms_panel_capacity'); } catch (x) {}
      const S = (v, a) => ({ state: String(v), attributes: a || {}, last_updated: new Date().toISOString(), last_changed: new Date().toISOString() }); const st = window.__states;
      st['sensor.bms_soc'] = S(60); st['sensor.bms_pv_power'] = S(800); st['sensor.bms_load_power'] = S(500); st['sensor.bms_grid_power'] = S(0); st['sensor.bms_battery_power'] = S(0);
      st['sensor.bms_reserve_soc'] = S(30, { price_buy: 1, price_sell: 0.3, inverter_floor: 20 }); __el.hass = __mk(); __el._setSkin(sk); }, sk);
    await sleep(700);
    ok(await e.q(() => !!__el.shadowRoot.getElementById('capInput')), `${sk}: pole pojemności baterii jest, gdy integracja jej nie podała`);
    await e.q(() => { const i = __el.shadowRoot.getElementById('capInput'); i.value = '12'; i.dispatchEvent(new Event('change', { bubbles: true })); });
    await sleep(700);
    ok(await e.q(() => localStorage.getItem('bms_panel_capacity') === '12' && !__el.shadowRoot.getElementById('capInput') && /do rezerwy 20%/i.test(__el.shadowRoot.querySelector('[data-tile="main-flow"]').innerText)), `${sk}: po wpisaniu 12 kWh pojawia się „Do rezerwy” i pole znika`);
    await e.page.context().close();
  }

  // węzły są klikalne we wszystkich stylach (mini wykres 24 h jak w klasycznym)
  for (const sk of SK) {
    const e = await openCard(b, { admin: false });
    await e.q((sk) => __el._setSkin(sk), sk); await sleep(600);
    ok(await e.q(() => ['pv', 'home', 'grid', 'batt'].every(k => __el.shadowRoot.querySelectorAll(`#nodesBox .nf-hit[data-k="${k}"]`).length === 1)), `${sk}: cztery klikalne węzły (PV, dom, sieć, bateria)`);
    await e.page.context().close();
  }

  // teksty na schemacie nie nachodzą na siebie (telefon i szeroki ekran)
  for (const mobile of [true, false]) for (const sk of ['glass', 'matrix', 'space', 'comfort', 'hero']) {
    const e = await openCard(b, { admin: false, mobile });
    await e.q((sk) => { const S = (v, a) => ({ state: String(v), attributes: a || {}, last_updated: new Date().toISOString(), last_changed: new Date().toISOString() }); const st = window.__states;
      st['sensor.bms_soc'] = S(48); st['sensor.bms_pv_power'] = S(2100); st['sensor.bms_load_power'] = S(1240); st['sensor.bms_grid_power'] = S(-800); st['sensor.bms_battery_power'] = S(-403);
      st['sensor.bms_energy_pv_today'] = S(12.4); st['sensor.bms_energy_load_today'] = S(9.8); st['sensor.bms_energy_grid_import_today'] = S(13.1); st['sensor.bms_energy_grid_export_today'] = S(15.2);
      st['sensor.bms_energy_battery_charge_today'] = S(14.1); st['sensor.bms_energy_battery_discharge_today'] = S(13.6); __el.hass = __mk(); __el._setSkin(sk); }, sk);
    await sleep(700);
    const ov = await e.q(() => { const ts = [...__el.shadowRoot.querySelectorAll('.sk-flow svg text')].map(t => ({ r: t.getBoundingClientRect(), s: t.textContent })).filter(x => x.r.width > 0);
      const bad = []; for (let i = 0; i < ts.length; i++) for (let j = i + 1; j < ts.length; j++) { const a = ts[i].r, c = ts[j].r;
        const w = Math.min(a.right, c.right) - Math.max(a.left, c.left), h = Math.min(a.bottom, c.bottom) - Math.max(a.top, c.top); if (w > 1 && h > 1.5) bad.push(ts[i].s + ' × ' + ts[j].s); }
      return { n: ts.length, bad }; });
    ok(ov.n >= 8 && !ov.bad.length, `${sk} (${mobile ? 'telefon' : 'szeroki'}): teksty na schemacie się nie nakładają (${ov.n})` + (ov.bad.length ? ' · ' + ov.bad.join('; ') : ''));
    await e.page.context().close();
  }

  console.log(fails ? `FAILS ${fails}` : 'OK');
  await b.close();
  process.exit(fails ? 1 : 0);
})();
