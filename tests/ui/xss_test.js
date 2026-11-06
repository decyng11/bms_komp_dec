// Test wstrzykiwania HTML: wszystkie dane „z zewnątrz” (nazwy encji, stany, atrybuty, odpowiedzi usług) zawierają payload.
// Oczekiwanie: nic się nie wykonuje (window.__xss === undefined), w shadow DOM nie ma <img src=x>, <script>, <svg onload>, atrybutów on*.
const { openCard, chromium } = require('./ui_env');
const T = require('./extras_helpers');
const { curve, REPORT, HEALTH } = T;
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const P = `<img src=x onerror="window.__xss=(window.__xss||0)+1"><svg onload="window.__xss=(window.__xss||0)+1"></svg>"'><script>window.__xss=(window.__xss||0)+1</script>`;

const scan = (e) => e.q(() => {
  const bad = [];
  const walk = (root, path) => {
    root.querySelectorAll('*').forEach((n) => {
      const tag = n.tagName.toLowerCase();
      if (tag === 'script') bad.push(path + ' <script>');
      if (tag === 'img' && /(^|\/)x$/.test(n.getAttribute('src') || '')) bad.push(path + ' <img src=x>');
      if (tag === 'svg' && n.hasAttribute('onload')) bad.push(path + ' <svg onload>');
      [...n.attributes].forEach((a) => { if (/^on/i.test(a.name)) bad.push(path + ' ' + tag + ' ' + a.name); });
      if (n.shadowRoot) walk(n.shadowRoot, path + '>' + tag);
    });
  };
  walk(__el.shadowRoot, 'card');
  return { bad, xss: window.__xss };
});

(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, { admin: true });
  // 1. trujemy WSZYSTKIE encje: friendly_name, stan tekstowy, opcje selectów, atrybuty
  await e.q((P) => {
    const st = window.__states;
    Object.keys(st).forEach((k) => {
      const s = st[k]; s.attributes.friendly_name = P + ' ' + k;
      if (!/^(number|sensor)\./.test(k) || /fault|alert/.test(k)) s.state = /^(select|switch|time|button)\./.test(k) ? s.state : P;
      if (s.attributes.options) s.attributes.options = s.attributes.options.concat([P]);
    });
    window.__el.hass = window.__mk();
  }, P);
  // 2. runtime’owe sensory BMS z payloadem w każdym polu tekstowym
  const c = curve();
  await T.seed(e, {
    curve: c, report: REPORT({ title: P, error: P, best_day: { date: P, net: 1 }, worst_day: { date: P, net: -1 }, days: [{ date: P, net: 1 }] }), health: HEALTH,
    planError: P, mode: P, planState: P,
    proposals: { start_grid_charge: { label: P, current: P, proposed: P, skip: false }, bateria_sprzedaz_start: { label: P, current: P, proposed: null, skip: true, reason: P } },
    monitor: { fault_note: P, alarms: [{ entity_id: 'sensor.inverter_alert', state: P, text: P }, { entity_id: P, state: P, text: P }], low_soc_active: true, watches: [{ id: P, entity_id: P, label: P, expected: P, state: P, message: P }] },
  });
  // plan z payloadem w tablicach tekstowych
  await e.q((P) => { const a = window.__states['sensor.bms_plan_curve'].attributes; a.curve.start = P; a.reason = P; a.notes = [P]; window.__el.hass = window.__mk(); }, P);
  // 3. odpowiedzi usług z payloadem
  await e.q((P) => {
    window.__svc = window.__svc || {};
    const deepP = (o) => JSON.parse(JSON.stringify(o, (k, v) => (typeof v === 'string' ? P : v)));
    window.__svc['bms_komp_dec.health_check'] = () => ({ response: { ok: false, level: P, checks: [{ name: P, ok: false, detail: P, fix: P }, { id: P, status: P, message: P, hint: P }], summary: P } });
    window.__svc['bms_komp_dec.watch_status'] = () => ({ response: { items: [{ id: P, entity_id: P, label: P, expected: P, state: P, status: P, message: P }] } });
    window.__svc['bms_komp_dec.diag_store_get_all'] = () => ({ response: { data: { log: [{ ts: Date.now(), name: P, from: P, to: P, eid: P, who: P }], auto: [{ name: P }], profiles: { [P]: { name: P, values: { [P]: P } } }, prefix: P, alarms: [{ ts: Date.now(), text: P, code: P }], backups: [{ ts: Date.now(), name: P, values: { [P]: P } }], watch: [{ eid: P, name: P }] } } });
    window.__svc['bms_komp_dec.monthly_report'] = () => ({ response: deepP({ year: 2026, month: 10, title: 'x', days: [], best_day: { date: 'a', net: 1 } }) });
    window.__svc['bms_komp_dec.get_plan'] = () => ({ response: { plan: { error: P } } });
    window.__svc['solarman.read_holding_registers'] = () => ({ response: { value: [P] } });
    window.__el.hass = window.__mk();
  }, P);

  // 4. przejście po wszystkich zakładkach i popupach
  for (const t of ['main', 'ems', 'charts', 'log']) { await T.tab(e, t); await sleep(400); const r = await scan(e); ok(r.bad.length === 0 && r.xss === undefined, `zakładka ${t}: brak wykonania HTML (${JSON.stringify(r.bad.slice(0, 3))} xss=${r.xss})`); }
  // klik w każdy element z data-* na głównej i EMS (popupy, kafelki)
  for (const t of ['main', 'ems', 'log']) {
    await T.tab(e, t);
    const n = await e.q(() => __el.shadowRoot.querySelectorAll('[data-pop],[data-act],[data-ex],[data-flow],[data-k]').length);
    for (let i = 0; i < Math.min(n, 60); i++) {
      await e.q((i) => { const x = __el.shadowRoot.querySelectorAll('[data-pop],[data-act],[data-ex],[data-flow],[data-k]')[i]; if (x && !x.disabled && !/reset|apply|undo|clear|delete|write/i.test(x.dataset.act || '')) x.click(); }, i).catch(() => {});
    }
    await sleep(600);
    const r = await scan(e); ok(r.bad.length === 0 && r.xss === undefined, `kliknięte elementy w ${t}: brak wykonania HTML (${JSON.stringify(r.bad.slice(0, 3))} xss=${r.xss})`);
  }
  // 5. Diagnostyka (po odblokowaniu hasłem)
  await T.tab(e, 'diag'); await sleep(1200);
  await e.q(() => { const s = __el.shadowRoot; if (s.getElementById('dgPw')) { s.getElementById('dgPw').value = 'slonce'; s.querySelector('[data-act=unlock]').click(); } });
  await sleep(1500);
  let r = await scan(e); ok(r.bad.length === 0 && r.xss === undefined, `Diagnostyka (odblokowana): brak wykonania HTML (${JSON.stringify(r.bad.slice(0, 3))} xss=${r.xss})`);
  const secs = await e.q(() => [...__el.shadowRoot.querySelectorAll('#diagRoot [data-sec], #diagRoot [data-scope], #diagRoot [data-dgtab], #diagRoot .dg-tab')].map((x) => x.dataset.sec || x.dataset.scope || x.dataset.dgtab || x.textContent.trim()));
  console.log('sekcje Diagnostyki:', JSON.stringify(secs));
  for (let i = 0; i < secs.length; i++) {
    await e.q((i) => { const x = [...__el.shadowRoot.querySelectorAll('#diagRoot [data-sec], #diagRoot [data-scope], #diagRoot [data-dgtab], #diagRoot .dg-tab')][i]; if (x) x.click(); }, i).catch(() => {});
    await sleep(500);
    r = await scan(e); ok(r.bad.length === 0 && r.xss === undefined, `Diagnostyka sekcja #${i} ${secs[i]}: brak wykonania HTML (${JSON.stringify(r.bad.slice(0, 3))} xss=${r.xss})`);
  }
  // wszystkie przyciski odczytu (nie zapisu) w Diagnostyce
  const nb = await e.q(() => __el.shadowRoot.querySelectorAll('#diagRoot [data-act]').length);
  for (let i = 0; i < nb; i++) {
    await e.q((i) => { const x = __el.shadowRoot.querySelectorAll('#diagRoot [data-act]')[i]; if (x && !x.disabled && /health|watch|refresh|alarm|log|backup|export|read|mb|show|load|check|list/i.test(x.dataset.act)) x.click(); }, i).catch(() => {});
    if (i % 10 === 0) await sleep(150);
  }
  await sleep(1200);
  r = await scan(e); ok(r.bad.length === 0 && r.xss === undefined, `Diagnostyka po kliknięciu przycisków odczytu: brak wykonania HTML (${JSON.stringify(r.bad.slice(0, 3))} xss=${r.xss})`);
  // kontrola pozytywna 1: skaner wykrywa prawdziwe wstrzyknięcie
  await e.q(() => { const d = document.createElement('div'); d.innerHTML = '<img src=x onerror="window.__ctl=1">'; __el.shadowRoot.appendChild(d); });
  r = await scan(e); ok(r.bad.length >= 1, 'kontrola: skaner wykrywa ręcznie wstrzyknięty <img src=x onerror> (' + r.bad.length + ')');
  await e.q(() => { const l = [...__el.shadowRoot.children].pop(); l.remove(); });
  // kontrola pozytywna 2: payload faktycznie dotarł do DOM jako zwykły tekst (czyli test nie jest pusty)
  const seen = {};
  for (const t of ['main', 'ems', 'log', 'diag']) {
    await T.tab(e, t); await sleep(500);
    seen[t] = await e.q(() => { const txt = (__el.shadowRoot.textContent || ''); return (txt.match(/<img src=x onerror/g) || []).length; });
  }
  console.log('wystąpienia payloadu jako tekstu:', JSON.stringify(seen));
  ok(Object.values(seen).reduce((a, v) => a + v, 0) >= 5, 'kontrola: payload widoczny jako tekst w DOM (test nie jest pusty)');
  ok(e.errs.filter((m) => !/Failed to load resource|favicon/.test(m)).length === 0, 'brak błędów JS przy złośliwych danych: ' + JSON.stringify(e.errs.slice(0, 3)));
  console.log(fails ? 'FAILS ' + fails : 'ALL OK');
  await b.close();
})().catch((x) => { console.log('ERR', x); process.exit(1); });
