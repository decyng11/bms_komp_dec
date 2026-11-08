const { openCard, chromium } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  const render = (sums) => e.q((sums) => {
    const eid = __el._eid('sensor', 'profit_today');
    window.__states[eid] = { state: '-1.23', attributes: sums ? { sums, friendly_name: 'EMS Bilans dziś' } : { friendly_name: 'EMS Bilans dziś' }, last_updated: new Date().toISOString(), last_changed: new Date().toISOString() };
    __el.hass = __mk(); __el._renderPlan();
    const t = __el.shadowRoot.querySelector('[data-role=money-table]');
    return t ? [...t.querySelectorAll('tr')].map(r => [...r.children].map(c => c.textContent.replace(/\s/g, ' ').trim()).join('|')).join('\n') : null;
  }, sums);
  const S = { day: { revenue: 1.15, cost: 2.38, export_kwh: 2.8, import_kwh: 3.5, net: -1.23 },
              month: { revenue: 142.6, cost: 96.2, export_kwh: 366, import_kwh: 135, net: 46.4 },
              total: { revenue: 1204.4, cost: 1011.1, export_kwh: 3100, import_kwh: 1400, net: 193.3 } };
  let t = await render(S);
  ok(t && /Sprzedałem\|1,15 zł\|142,60 zł\|1 204 zł/.test(t), 'sprzedałem: dziś, miesiąc, razem w zł');
  ok(/Kupiłem\|2,38 zł\|96,20 zł\|1 011 zł/.test(t), 'kupiłem: dziś, miesiąc, razem');
  ok(/Saldo\|−1,23 zł\|\+46,40 zł\|\+193,30 zł/.test(t), 'saldo ze znakiem (− dla straty, + dla zysku)');
  ok(/0,41 \/ 0,68/.test(t), 'średnie ceny sprzedaży / zakupu dziś (0,41 / 0,68)');
  const colors = await e.q(() => [...__el.shadowRoot.querySelectorAll('[data-role=money-table] tr')].map(r => [...r.querySelectorAll('td')].slice(1).map(c => c.style.color).join('|')));
  ok(/#34c759|rgb\(52, 199, 89\)/.test(colors[1]) && /#ff9f0a|rgb\(255, 159, 10\)/.test(colors[2]), 'kolory: sprzedaż zielona, zakup pomarańczowy');
  ok(/rgb\(255, 69, 58\)\|rgb\(52, 199, 89\)/.test(colors[3]), 'saldo: czerwone dla straty, zielone dla zysku');
  t = await render(null);
  ok(t === null, 'bez atrybutu „sums” (stara wersja integracji) tabelki nie ma — brak błędu');
  await b.close();
  console.log(fails ? `FAILS ${fails}` : 'FAILS 0'); process.exit(fails ? 1 : 0);
})();
