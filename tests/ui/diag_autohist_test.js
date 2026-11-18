// Ustawienia → Autotest: grupa „Auto-stosowanie” oraz historia ostatnich prób (kiedy, skąd, co zastosowano / dlaczego nie).
const { openCard, chromium } = require('./ui_env');
const { seed, curve, REPORT, HEALTH, openSec } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const ST = {
  version: '0.9.5', time: '2026-11-18T16:30:00+01:00', summary: { errors: 0, warnings: 1, ok: 3 }, commands: [],
  groups: [{ name: 'Auto-stosowanie', checks: [
    { id: 'auto_on', title: 'Automatyczne stosowanie propozycji', status: 'ok', detail: 'włączone', fix: '' },
    { id: 'auto_pending', title: 'Propozycje czekające na zastosowanie', status: 'warn', detail: 'start_grid_charge 01:00→19:00 (przesunięcie za duże)', fix: 'Powód jest też widoczny w karcie propozycji.' }] }],
};
const HIST = [
  { at: '2026-11-18T16:30:10', src: 'live', why: { start_grid_charge: 'przesunięcie o 6.0 h przekracza limit 4 h <img src=x onerror=window.__pwn=1>' } },
  { at: '2026-11-18T16:00:02', src: 'daily', busy: ['trwa sprzedaż'] },
  { at: '2026-11-17T16:00:03', src: 'daily', applied: { start_grid_charge: '23:00', stop_grid_charge: '05:00' } },
  { at: '2026-11-16T09:12:00', src: 'manual', would: { start_grid_charge: '22:00' } },
];
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, { admin: true });
  await seed(e, { curve: curve(), report: REPORT(), health: HEALTH });
  await e.q(([st, hist]) => {
    window.__svc = window.__svc || {}; window.__svc['bms_komp_dec.self_test'] = () => ({ response: JSON.parse(JSON.stringify(st)) });
    const ms = window.__states['sensor.bms_monitor_status'] || (window.__states['sensor.bms_monitor_status'] = { entity_id: 'sensor.bms_monitor_status', state: 'ok', attributes: {} });
    ms.attributes.auto_hist = hist; window.__el.hass = window.__mk();
  }, [ST, HIST]);
  await openSec(e, 'selftest'); await sleep(900);
  const r = await e.q(() => { const sh = __el.shadowRoot, box = sh.getElementById('dgAutoHist');
    return { has: !!box, txt: box ? box.innerText.replace(/\s+/g, ' ') : '', rows: box ? box.querySelectorAll('div[style*="border-bottom"]').length : 0, open: box ? box.open : false,
      groups: [...sh.querySelectorAll('#dgSt summary')].map(s => s.textContent.replace(/\s+/g, ' ').trim()), pwn: window.__pwn === 1, imgs: box ? box.querySelectorAll('img').length : -1 }; });
  ok(r.groups.some(g => /Auto-stosowanie/.test(g)), 'autotest: grupa „Auto-stosowanie” widoczna: ' + r.groups.join(' | '));
  ok(r.has && r.open && r.rows === 4, `historia: karta otwarta, 4 wiersze (${r.rows})`);
  ok(/na żywo/.test(r.txt) && /codzienna propozycja/.test(r.txt) && /ręcznie/.test(r.txt), 'historia: źródła prób po polsku');
  ok(/zastosowano: start_grid_charge → 23:00, stop_grid_charge → 05:00/.test(r.txt), 'historia: zastosowane godziny');
  ok(/wstrzymane: trwa sprzedaż/.test(r.txt), 'historia: wstrzymanie z powodem');
  ok(/podgląd \(bez zapisu\): start_grid_charge → 22:00/.test(r.txt), 'historia: tryb podglądu');
  ok(/start_grid_charge: przesunięcie o 6\.0 h przekracza limit 4 h/.test(r.txt), 'historia: powód odmowy');
  ok(!r.pwn && r.imgs === 0, 'historia: powód jest escapowany (bez wstrzykiwania HTML)');
  ok(/11-18 16:30/.test(r.txt) && /11-16 09:12/.test(r.txt), 'historia: czasy w formacie MM-DD GG:MM');
  // raport do skopiowania zawiera historię
  const txt = await e.q(() => __el._dgStText());
  ok(/== Historia auto-stosowania/.test(txt) && /przesunięcie o 6\.0 h/.test(txt) && /zastosowano: start_grid_charge → 23:00/.test(txt), 'raport do skopiowania zawiera historię auto-stosowania');
  // pusta historia
  await e.q(() => { window.__states['sensor.bms_monitor_status'].attributes.auto_hist = []; window.__el.hass = window.__mk(); __el._dgStPaint(); }); await sleep(200);
  ok(/Jeszcze nie było prób/.test(await e.q(() => __el.shadowRoot.getElementById('dgAutoHist').textContent)), 'pusta historia: podpowiedź zamiast pustej karty');
  await b.close();
  console.log(fails ? `FAILS ${fails}` : 'OK');
  process.exit(fails ? 1 : 0);
})();
