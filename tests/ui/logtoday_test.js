// „Co EMS zrobił dziś”: tylko dzisiejsze ważne zdarzenia, liczniki, limit wierszy
const { openCard, chromium } = require('./ui_env');
const { seed, curve, tab } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  await seed(e, { curve: curve() });
  await e.q(() => {
    const now = new Date(), yest = new Date(now.getTime() - 26 * 3600 * 1000);
    const E = (d, kind, level, msg) => ({ ts: d.toISOString(), kind, level, msg });
    const ents = [E(yest, 'command', 'ok', 'WCZORAJSZA komenda'), E(now, 'plan', 'info', 'Plan: zwykły wpis informacyjny'),
      E(now, 'command', 'ok', 'Sprzedaż 6000W (harmonogram)'), E(now, 'guard', 'warn', 'Sprzedaż ZABLOKOWANA: import z sieci'),
      E(now, 'auto', 'ok', 'Wyłączono Sprzedaż (2)')];
    for (let i = 0; i < 12; i++) ents.push(E(now, 'command', 'ok', 'komenda ' + i));
    __states['sensor.bms_decision_log'] = { state: 'x', attributes: { entries: ents }, last_updated: new Date().toISOString(), last_changed: new Date().toISOString() };
    __el.hass = __mk();
  });
  await tab(e, 'log'); await sleep(500);
  const r = await e.q(() => { const s = __el.shadowRoot.getElementById('logToday'); return s ? { t: s.textContent, rows: s.querySelectorAll('div[style*="border-bottom"]').length } : null; });
  ok(r && /Co EMS zrobił dziś/.test(r.t), 'sekcja „Co EMS zrobił dziś” jest');
  ok(r && !/WCZORAJSZA/.test(r.t), 'wczorajsze zdarzenia pominięte');
  ok(r && !/zwykły wpis informacyjny/.test(r.t), 'zwykły wpis informacyjny (plan) pominięty');
  ok(r && /blokad/.test(r.t) && /komend/.test(r.t) && /zmian automatu/.test(r.t), 'liczniki komend / blokad / zmian automatu: ' + (r && r.t.slice(0, 160)));
  ok(r && r.rows === 12 && /więcej/.test(r.t), 'limit 12 wierszy + „…i N więcej”: ' + (r && r.rows));
  await b.close();
  console.log(fails ? `FAILS ${fails}` : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
