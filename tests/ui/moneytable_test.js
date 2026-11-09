const { openCard, chromium } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  const render = (sums, extras) => e.q(([sums, extras]) => {
    const eid = __el._eid('sensor', 'profit_today');
    window.__states[eid] = { state: '-1.23', attributes: sums ? { sums, extras, friendly_name: 'EMS Bilans dziś' } : { friendly_name: 'EMS Bilans dziś' }, last_updated: new Date().toISOString(), last_changed: new Date().toISOString() };
    __el.hass = __mk(); __el._renderPlan();
    const t = __el.shadowRoot.querySelector('[data-role=money-table]');
    return t ? [...t.querySelectorAll('tr')].map(r => [...r.children].map(c => c.textContent.replace(/\s/g, ' ').trim()).join('|')).join('\n') : null;
  }, [sums, extras]);
  const S = { day: { revenue: 1.15, cost: 2.38, export_kwh: 2.8, import_kwh: 3.5, net: -1.23 },
              month: { revenue: 142.6, cost: 96.2, export_kwh: 366, import_kwh: 135, net: 46.4 },
              week: { revenue: 8.5, cost: 6.2, export_kwh: 20, import_kwh: 9, net: 2.3 },
              prev_month: { revenue: 150.2, cost: 160.7, export_kwh: 400, import_kwh: 200, net: -10.5 },
              year: { revenue: 1204.4, cost: 1011.1, export_kwh: 3100, import_kwh: 1400, net: 193.3 } };
  let t = await render(S);
  ok(t && /Sprzedałem\|1,15\|8,50\|142,60\|150,20\|1 204$/m.test(t), 'sprzedałem: dziś, tydzień, miesiąc, poprzedni miesiąc, rok');
  ok(/Kupiłem\|2,38\|6,20\|96,20\|160,70\|1 011$/m.test(t), 'kupiłem: wszystkie okresy');
  ok(/Saldo\|−1,23\|\+2,30\|\+46,40\|−10,50\|\+193,30$/m.test(t), 'saldo ze znakiem (− dla straty, + dla zysku)');
  ok(!/Śr\. cena/.test(t) && /Dziś\|Tydz\.\|Miesiąc\|Poprz\. m\.\|Rok/.test(t), 'bez wiersza średnich cen; kolumny: Dziś, Tydz., Miesiąc, Poprz. m., Rok');
  const colors = await e.q(() => [...__el.shadowRoot.querySelectorAll('[data-role=money-table] tr')].map(r => [...r.querySelectorAll('td')].slice(1).map(c => c.style.color).join('|')));
  ok(/#34c759|rgb\(52, 199, 89\)/.test(colors[1]) && /#ff9f0a|rgb\(255, 159, 10\)/.test(colors[2]), 'kolory: sprzedaż zielona, zakup pomarańczowy');
  ok(/rgb\(255, 69, 58\)\|rgb\(52, 199, 89\)\|rgb\(52, 199, 89\)\|rgb\(255, 69, 58\)\|rgb\(52, 199, 89\)/.test(colors[3]), 'saldo: czerwone dla straty, zielone dla zysku');
  const EX = { day: { savings: { without_cost: 11.15, actual_cost: 1.23, saving: 9.92 }, split: { load_kwh: 16.4, pv_pct: 9, battery_pct: 70, grid_pct: 21 }, tariff: { peak_kwh: 1, peak_pct: 29, offpeak_kwh: 2.5, offpeak_pct: 71 } },
    month: { savings: { without_cost: 80, actual_cost: -46.4, saving: 126.4 }, split: null, tariff: { peak_kwh: 4, peak_pct: 53, offpeak_kwh: 3.5, offpeak_pct: 47 } },
    week: { savings: { without_cost: 30, actual_cost: -2.3, saving: 32.3 }, split: null, tariff: null },
    prev_month: { savings: { without_cost: 70, actual_cost: 10.5, saving: 59.5 }, split: null, tariff: null },
    year: { savings: { without_cost: null, saving: null }, split: null, tariff: null } };
  t = await render(S, EX);
  ok(/Bez PV i baterii \(szac\.\)\|11,15\|30,00\|80,00\|70,00\|—$/m.test(t), 'koszt bez PV i baterii: okresy, myślnik dla roku bez danych');
  ok(/Oszczędzam \(szac\.\)\|\+9,92\|\+32,30\|\+126,40\|\+59,50\|—$/m.test(t), 'oszczędność z plusem, myślnik gdy brak danych');
  const sp = await e.q(() => { const x = __el.shadowRoot.querySelector('[data-role=split]'); return x ? [x.textContent.replace(/\s+/g, ' '), [...x.querySelectorAll('[title]')].map(d => d.style.width).join(',')] : null; });
  ok(sp && /PV 9%/.test(sp[0]) && /bateria 70%/.test(sp[0]) && /sieć 21%/.test(sp[0]) && sp[1] === '9%,70%,21%', 'pasek „skąd energia”: PV 9 / bateria 70 / sieć 21');
  const tf = await e.q(() => { const x = __el.shadowRoot.querySelector('[data-role=tariff]'); return x ? x.textContent : null; });
  ok(tf && /drogie godziny 4,0 kWh \(53%\)/.test(tf) && /tanie 3,5 kWh \(47%\)/.test(tf), 'taryfa: udział poboru w drogich godzinach (miesiąc)');
  t = await render(S, null);
  ok(t && !/Oszczędzam/.test(t) && !(await e.q(() => !!__el.shadowRoot.querySelector('[data-role=split]'))), 'bez atrybutu extras: tylko tabela podstawowa, bez błędu');
  t = await render(null);
  ok(t === null, 'bez atrybutu „sums” (stara wersja integracji) tabelki nie ma — brak błędu');
  await b.close();
  console.log(fails ? `FAILS ${fails}` : 'FAILS 0'); process.exit(fails ? 1 : 0);
})();
