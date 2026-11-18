// „Do decyzji”: gdy auto-stosowanie jest włączone, a propozycja i tak wisi, karta pokazuje KONKRETNY powód
// (limit przesunięcia, trwająca sprzedaż, czekanie na stabilność…) — wcześniej było to tylko w dzienniku i w powiadomieniu.
const { openCard, chromium } = require('./ui_env');
const { seed, curve } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, { mobile: true });
  await e.page.setViewportSize({ width: 360, height: 800 });
  await e.q(() => { document.getElementById('h').style.width = '360px'; });
  await seed(e, { curve: curve(), proposals: {
    start_grid_charge: { label: 'Start ładowania z sieci 1', current: '01:00', proposed: '19:00', skip: false, reason: 'trzeba doładować do rana', confidence: 'high', required: true },
    stop_grid_charge: { label: 'Stop ładowania z sieci 1', current: '03:00', proposed: '03:00', skip: false, reason: 'x', confidence: 'high', required: true } } });
  const set = (auto, skip) => e.q(([auto, skip]) => {
    __states['switch.bms_auto_apply'] = { entity_id: 'switch.bms_auto_apply', state: auto ? 'on' : 'off', attributes: {}, last_updated: new Date().toISOString(), last_changed: new Date().toISOString() };
    const st = __states['sensor.bms_monitor_status'] || (__states['sensor.bms_monitor_status'] = { entity_id: 'sensor.bms_monitor_status', state: 'ok', attributes: {} });
    st.attributes.inbox = []; st.attributes.inbox_rejected = {}; st.attributes.auto_skip = skip; __el.hass = __mk();
    __el._inbSig = null; __el._renderInbox();
  }, [auto, skip]);
  const card = () => e.q(() => { const o = __el.shadowRoot.getElementById('inbOv'); const n = o.querySelector('.inb-auto'), c = o.querySelector('.inb-card'); const cr = c && c.getBoundingClientRect(), nr = n && n.getBoundingClientRect();
    return { note: n ? n.textContent.replace(/\s+/g, ' ').trim() : null, cls: n ? n.className : '', inside: !!(n && cr && nr.left >= cr.left - 1 && nr.right <= cr.right + 1), html: n ? n.innerHTML : '' }; });
  const SK = { start_grid_charge: { kind: 'skip', why: 'przesunięcie o 6.0 h przekracza limit 4 h — potwierdź ręcznie albo zwiększ „Auto-stosowanie — maks. przesunięcie godzin” w Ustawieniach', prop: '19:00', at: '2026-11-18T16:00:00+01:00' } };

  await set(true, SK);
  await e.q(() => __el._el('bell').click()); await sleep(300);
  let r = await card();
  ok(r.note && /Auto-stosowanie: przesunięcie o 6\.0 h przekracza limit 4 h/.test(r.note), 'auto włączone + odmowa: karta pokazuje powód: ' + (r.note || '').slice(0, 90));
  ok(/warn/.test(r.cls) && r.inside, 'powód w żółtej plakietce, mieści się w karcie na telefonie (360 px)');

  await set(false, SK);
  r = await card();
  ok(r.note === null, 'auto-stosowanie wyłączone: bez komunikatu o powodzie (nie ma czego tłumaczyć)');

  await set(true, { start_grid_charge: Object.assign({}, SK.start_grid_charge, { prop: '18:00' }) });
  r = await card();
  ok(r.note === null, 'powód dotyczy innej godziny niż proponowana teraz: nie pokazujemy cudzego komunikatu');

  await set(true, { start_grid_charge: { kind: 'wait', why: 'czekam, aż propozycja utrzyma się 30 min bez zmian — wtedy zastosuję ją sama', prop: '19:00' } });
  r = await card();
  ok(r.note && /czekam/.test(r.note) && /wait/.test(r.cls), 'oczekiwanie na stabilność: szara plakietka „czekam…”');

  await set(true, { start_grid_charge: { kind: 'skip', why: '<img src=x onerror=window.__xss=1> <b>pogrubione</b>', prop: '19:00' } });
  r = await card(); await sleep(100);
  ok(r.note && !/<b>/.test(r.html) && /&lt;img/.test(r.html) && !(await e.q(() => window.__xss)), 'powód jest escapowany (bez wstrzykiwania HTML)');

  await set(true, {});
  r = await card();
  ok(r.note === null, 'brak zapisanego powodu: karta bez dodatkowej plakietki');

  await b.close();
  console.log(fails ? `FAILS ${fails}` : 'OK');
  process.exit(fails ? 1 : 0);
})();
