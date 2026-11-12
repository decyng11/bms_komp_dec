// Godziny zestawu wyszarzone („nieaktywne”), gdy zestaw wyłączony albo okno puste (start = stop)
const { openCard, chromium } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  const idle = async (sw, t1, t2) => e.q(([sw, t1, t2]) => {
    const now = new Date().toISOString(), S = (s) => ({ state: s, attributes: {}, last_updated: now, last_changed: now });
    __states['switch.bms_bateria_sprzedaz_2'] = S(sw);
    __states['time.bms_bateria_sprzedaz_start_2'] = S(t1); __states['time.bms_bateria_sprzedaz_stop_2'] = S(t2);
    __el.hass = __mk();
    __el._updateBadge('switch', 'bateria_sprzedaz_2', 'badge-sprzedaz-2', ['bateria_sprzedaz_start_2', 'bateria_sprzedaz_stop_2']);
    const f = (k) => __el.shadowRoot.querySelector(`[data-time-key="${k}"]`).closest('.row').classList.contains('inactive-row');
    return [f('bateria_sprzedaz_start_2'), f('bateria_sprzedaz_stop_2')];
  }, [sw, t1, t2]);
  let r = await idle('on', '15:00:00', '16:00:00'); ok(!r[0] && !r[1], 'zestaw włączony, okno pełne: aktywne');
  r = await idle('off', '15:00:00', '16:00:00'); ok(r[0] && r[1], 'zestaw wyłączony: oba wiersze nieaktywne');
  r = await idle('on', '15:00:00', '15:00:00'); ok(r[0] && r[1], 'okno puste (start = stop): nieaktywne');
  r = await idle('on', '15:00:00', '17:00:00'); ok(!r[0] && !r[1], 'po włączeniu i nowym oknie wraca do aktywnych');
  await b.close();
  console.log(fails ? `FAILS ${fails}` : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
