// Dzwonek: licznik, arkusz „Do decyzji”, Potwierdź / Odrzuć per propozycja (bez przycisków zbiorczych), skrzynka powiadomień
const { openCard, chromium } = require('./ui_env');
const { seed, curve } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const now = () => Math.round(Date.now() / 1000);
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  await seed(e, { curve: curve(), proposals: {
    start_grid_charge: { label: 'Start ładowania z sieci 1', current: '22:00', proposed: '23:00', skip: false, reason: 'tańsze godziny po 23', confidence: 'high' },
    stop_grid_charge: { label: 'Stop ładowania z sieci 1', current: '06:00', proposed: '05:00', skip: false, reason: 'bateria wystarczy', confidence: 'high' },
    bateria_sprzedaz_start: { label: 'Start sprzedaży 1', current: '18:00', proposed: null, skip: true, reason: 'Pomiń — za niska cena' },
    pv_export_start: { label: 'PV start', current: '10:00', proposed: '10:00', skip: false } } });
  const setNotes = (notes, rej) => e.q((a) => {
    const st = __states['sensor.bms_monitor_status'] || (__states['sensor.bms_monitor_status'] = { entity_id: 'sensor.bms_monitor_status', state: 'ok', attributes: {} });
    st.attributes.inbox = a[0]; st.attributes.inbox_rejected = a[1]; __el.hass = __mk();
  }, [notes, rej || {}]);
  await setNotes([
    { id: 3, ts: now() - 120, kind: 'alarm', group: 'Falownik', title: '🚨 Alarm falownika', message: 'F23 — upływ prądu', level: 'error', read: false },
    { id: 2, ts: now() - 7200, kind: 'summary_daily', group: 'Podsumowania', title: 'Podsumowanie dnia', message: 'Zysk 3,10 zł', level: 'info', read: true }]);
  await sleep(200);
  const badge = await e.q(() => { const n = __el._el('bellN'); return [n.hidden, n.textContent]; });
  ok(badge[0] === false && badge[1] === '2', 'dzwonek: 1 propozycja do decyzji + 1 nieprzeczytane = 2: ' + badge);
  ok(await e.q(() => __el.shadowRoot.getElementById('inbOv').hidden), 'arkusz domyślnie zamknięty');
  await e.q(() => __el._el('bell').click()); await sleep(200);
  const txt = await e.q(() => __el.shadowRoot.getElementById('inbOv').innerText.replace(/\s+/g, ' '));
  ok(/Do decyzji \(1\)/.test(txt), 'tytuł „Do decyzji (1)”: ' + txt.slice(0, 80));
  ok(/ZMIENIAM/.test(txt) && /22:00 → 23:00/.test(txt) && /06:00 → 05:00/.test(txt), 'para START/STOP: zmiany stare → nowe');
  ok(/POMIJAM/.test(txt), 'pomijana propozycja oznaczona POMIJAM');
  ok(!/PV start/.test(txt) && !/10:00/.test(txt), 'bez zmian (proponowane = bieżące) nie pokazujemy');
  ok(!/Potwierdź wszystkie|Odrzuć wszystkie/i.test(txt), 'brak przycisków zbiorczych');
  ok(await e.q(() => __el.shadowRoot.querySelectorAll('#inbOv [data-inb="apply"]').length) === 1, 'jeden przycisk Potwierdź (na propozycję)');
  ok(/Alarm falownika/.test(txt) && /Podsumowanie dnia/.test(txt) && /2 min temu/.test(txt), 'skrzynka: alarm i podsumowanie z czasem');
  ok(/auto-stosowanie wył\./.test(txt), 'pigułka, gdy auto-stosowanie wyłączone');
  ok(/tańsze godziny po 23/i.test(await e.q(() => __el.shadowRoot.getElementById('inbOv').textContent)), 'uzasadnienie w rozwijanym „Dlaczego”');
  // Potwierdź
  await e.q(() => { window.__calls.length = 0; __el.shadowRoot.querySelector('#inbOv [data-inb="apply"]').click(); }); await sleep(300);
  const c1 = await e.q(() => window.__calls.filter(c => c[1] === 'apply_schedule_times'));
  ok(c1.length === 1 && c1[0][2].times.start_grid_charge === '23:00' && c1[0][2].times.stop_grid_charge === '05:00', 'Potwierdź → apply_schedule_times z obiema godzinami: ' + JSON.stringify(c1));
  // Odrzuć
  await e.q(() => { window.__calls.length = 0; __el.shadowRoot.querySelector('#inbOv [data-inb="reject"]').click(); }); await sleep(300);
  const c2 = await e.q(() => window.__calls.filter(c => c[1] === 'inbox_action').map(c => c[2]));
  ok(c2.length === 2 && c2.every(x => x.action === 'reject') && c2.some(x => x.key === 'start_grid_charge' && x.proposed === '23:00'), 'Odrzuć → inbox_action reject dla każdego klucza: ' + JSON.stringify(c2));
  const txt2 = await e.q(() => __el.shadowRoot.getElementById('inbOv').innerText.replace(/\s+/g, ' '));
  ok(!/ZMIENIAM/.test(txt2) && /Powiadomienia/.test(txt2), 'po odrzuceniu propozycja znika od razu (tytuł: Powiadomienia)');
  ok(await e.q(() => __el._el('bellN').textContent) === '1', 'licznik spada do 1 (tylko nieprzeczytane)');
  // odrzucona zapamiętana po stronie serwera + nowa propozycja wraca
  await setNotes([], { start_grid_charge: '23:00', stop_grid_charge: '05:00' });
  await e.q(() => { __el._inbRej = {}; __el._inbSig = null; __el._renderInbox(); });
  ok(!/ZMIENIAM/.test(await e.q(() => __el.shadowRoot.getElementById('inbOv').innerText)), 'odrzucenie z serwera ukrywa propozycję po odświeżeniu');
  await setNotes([], { start_grid_charge: '22:30' });
  await e.q(() => { __el._inbRej = {}; __el._inbSig = null; __el._renderInbox(); });
  ok(/ZMIENIAM/.test(await e.q(() => __el.shadowRoot.getElementById('inbOv').innerText)), 'inna propozycja tego samego klucza wraca');
  // powiadomienia: przeczytane / usuń / wyczyść
  await setNotes([{ id: 3, ts: now() - 60, kind: 'alarm', group: 'Falownik', title: 'A', message: 'm', level: 'error', read: false }]);
  await e.q(() => { __el._inbSig = null; __el._renderInbox(); window.__calls.length = 0; __el.shadowRoot.querySelector('#inbOv [data-inb="read"]').click(); }); await sleep(300);
  ok(await e.q(() => window.__calls.some(c => c[1] === 'inbox_action' && c[2].action === 'read' && c[2].id === 3)), 'Przeczytane → inbox_action read');
  await e.q(() => { window.__calls.length = 0; __el.shadowRoot.querySelector('#inbOv [data-inb="del"]').click(); }); await sleep(300);
  ok(await e.q(() => window.__calls.some(c => c[2].action === 'delete')) && /Brak powiadomień/.test(await e.q(() => __el.shadowRoot.getElementById('inbOv').innerText)), 'Usuń → delete i pusty stan');
  // zamykanie
  await e.q(() => __el.shadowRoot.querySelector('#inbOv [data-inb="close"]').click());
  ok(await e.q(() => __el.shadowRoot.getElementById('inbOv').hidden), 'X zamyka arkusz');
  // starsza integracja (bez inbox / proposals): bez błędu
  await e.q(() => { delete __states['sensor.bms_monitor_status'].attributes.inbox; __states['sensor.bms_plan_curve'].attributes.proposals = null; __el.hass = __mk(); });
  ok(await e.q(() => __el._el('bellN').hidden), 'bez danych: brak licznika, brak błędu');
  await b.close();
  console.log(fails ? `FAILS ${fails}` : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
