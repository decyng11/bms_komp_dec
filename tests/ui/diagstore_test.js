const { openCard, chromium } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const SHUT = 'number.inverter_battery_shutdown_soc';

async function setup(b, { seedLocal, haData, failGet, failSet, failWatch, mobile } = {}) {
  const e = await openCard(b, { mobile, preload: [] });
  const { page: p, q } = e;
  await q(({ seedLocal, haData, failGet, failSet, failWatch }) => {
    window.__haData = haData || {}; window.__cfg = { failGet, failSet, failWatch }; window.__store = {}; window.__sets = []; window.__watchW = [];
    for (const [k, v] of Object.entries(seedLocal || {})) localStorage.setItem(k, JSON.stringify(v));
    window.__svc = {
      'bms_komp_dec.diag_store_get_all': () => { if (window.__cfg.failGet) throw new Error('Unauthorized'); return { response: { data: window.__haData } }; },
      'bms_komp_dec.diag_store_set': (m) => { if (window.__cfg.failSet) throw new Error('Unauthorized'); window.__sets.push(m.service_data); window.__store[m.service_data.key] = m.service_data.value; return { response: { key: m.service_data.key, bytes: 10 } }; },
      'bms_komp_dec.watch_write': (m) => { if (window.__cfg.failWatch) throw new Error('usługa niedostępna'); window.__watchW.push(m.service_data); return { response: { item: { id: 'w' + window.__watchW.length, status: 'pending' } } }; },
    };
  }, { seedLocal, haData, failGet, failSet, failWatch });
  return e;
}
const unlock = async (e) => {
  await e.q(() => __el.shadowRoot.querySelector('[data-tab="diag"]').click());
  await e.page.waitForFunction(() => !!__el.shadowRoot.getElementById('dgPw'), null, { timeout: 8000 });
  await e.q(() => { const s = __el.shadowRoot; s.getElementById('dgPw').value = 'slonce'; s.querySelector('[data-act=unlock]').click(); });
  await e.page.waitForFunction(() => !!__el.shadowRoot.getElementById('dgBody'), null, { timeout: 5000 });
};
const writeShutdown = async (e, val) => {
  await e.q(() => __el.shadowRoot.querySelector('[data-sec=config]').click());
  await e.q(([eid, v]) => { const i = __el.shadowRoot.querySelector(`[data-eid="${eid}"]`); i.value = v; i.dispatchEvent(new Event('input', { bubbles: true })); }, [SHUT, String(val)]);
  await e.q((eid) => __el.shadowRoot.querySelector(`[data-eid="${eid}"]`).closest('[data-scope=row]').querySelector('[data-act=save-row]').click(), SHUT);
  await sleep(150);
  await e.q(() => { const m = __el.shadowRoot.querySelector('.dg-modal'); const n = m.querySelector('#dgNeed'); if (n) n.click(); m.querySelector('[data-id=ok]').click(); });
  await sleep(1800);
};

(async () => {
  const b = await chromium.launch();

  // A. migracja z localStorage do HA (HA puste)
  let e = await setup(b, { seedLocal: { bms_diag_log: [{ ts: 1, eid: 'number.x', name: 'X', from: '1', to: '2', ok: true }], bms_diag_profiles: { 'Zima': { ts: 2, values: { 'number.x': '5' } } } } });
  await unlock(e); await sleep(1500);
  ok((await e.q(() => Object.keys(window.__store).sort())).join() === 'log,profiles', 'migracja: do HA trafiły log i profiles: ' + JSON.stringify(await e.q(() => Object.keys(window.__store))));
  ok(await e.q(() => window.__store.log[0].eid === 'number.x' && window.__store.profiles['Zima'].ts === 2), 'migracja: wartości identyczne jak w przeglądarce');
  ok(/przeniesiono 2/.test(await e.q(() => __el.shadowRoot.getElementById('dgStoreNote').textContent)), 'migracja: informacja o przeniesieniu: ' + await e.q(() => __el.shadowRoot.getElementById('dgStoreNote').textContent));
  ok(e.errs.length === 0, 'A: brak błędów JS ' + JSON.stringify(e.errs));
  await e.ctx.close();

  // B. HA ma dane — wygrywa nad przeglądarką; nic nie jest nadpisywane
  e = await setup(b, { seedLocal: { bms_diag_log: [{ ts: 1, eid: 'number.lokalny' }] }, haData: { log: { value: [{ ts: 9, eid: 'number.z_ha', name: 'HA', ok: true }], updated: 'x' }, profiles: { value: { P1: { ts: 3, values: {} } }, updated: 'x' } } });
  await unlock(e); await sleep(1200);
  ok(await e.q(() => __el._dgLS().get('bms_diag_log')[0].eid === 'number.z_ha'), 'HA wygrywa: dziennik z HA');
  ok(await e.q(() => !!__el._dgLS().get('bms_diag_profiles').P1), 'HA wygrywa: profile z HA');
  ok(await e.q(() => !window.__sets.some(s => s.key === 'log')), 'HA wygrywa: lokalny dziennik nie nadpisał HA');
  await e.q(() => __el.shadowRoot.querySelector('[data-sec=log]').click());
  ok(await e.q(() => /number\.z_ha|HA/.test(__el.shadowRoot.getElementById('dgBody').textContent)), 'sekcja Dziennik pokazuje wpis z HA');
  await e.ctx.close();

  // C. zapis parametru: dziennik + kopia do HA, kontrola po zapisie zarejestrowana w integracji
  e = await setup(b, { haData: {} });
  await unlock(e); await sleep(800);
  await writeShutdown(e, 25);
  await sleep(1200);
  const sets = await e.q(() => window.__sets.map(s => s.key));
  ok(sets.includes('log') && sets.includes('auto'), 'zapis: dziennik i kopia automatyczna zapisane w HA: ' + sets.join());
  const lastLog = await e.q(() => window.__store.log[0]);
  ok(lastLog && lastLog.eid === SHUT && String(lastLog.to) === '25' && lastLog.ok === true, 'zapis: wpis dziennika w HA: ' + JSON.stringify(lastLog));
  const ww = await e.q(() => window.__watchW);
  ok(ww.length === 1 && ww[0].entity_id === SHUT && ww[0].expected === 25 && ww[0].tolerance === 0.01 && ww[0].source === 'Diagnostyka' && typeof ww[0].label === 'string', 'zapis: watch_write z oczekiwaną wartością: ' + JSON.stringify(ww));
  ok(await e.q(() => __el._dgLS().get('bms_diag_watch').some(w => w.eid === 'number.inverter_battery_shutdown_soc' && w.srv === 'w1')), 'zapis: lokalny wpis kontroli powiązany z kontrolą w integracji (srv=w1)');
  ok((await e.q(() => window.__calls.filter(c => c[0] === 'number').length)) === 1, 'zapis: dokładnie jedno wywołanie number.set_value');

  // D. wynik kontroli z integracji → alarm w karcie (dryf) i zamknięcie (ok)
  await e.q(() => { window.__states['sensor.bms_monitor_status'] = { state: '0', attributes: { watches: [{ id: 'w1', status: 'drift', entity_id: 'number.inverter_battery_shutdown_soc', expected: 25, checks: [{ value: 65516, ok: false, note: 'U16' }] }] }, last_updated: new Date().toISOString() }; __el.hass = __mk(); });
  await e.q(() => { __el._dgS()._wcAt = 0; __el._dgSyncTab(); });
  const al = await e.q(() => __el._dgLS().get('bms_diag_alarms'));
  ok(al.length === 1 && al[0].eid === SHUT && al[0].read === 65516 && String(al[0].wrote) === '25', 'dryf z integracji → alarm w karcie: ' + JSON.stringify(al));
  ok(await e.q(() => /rozbieżność/.test(__el.shadowRoot.getElementById('dgAlarmBox').textContent)), 'dryf: alarm widoczny w Diagnostyce');
  ok(await e.q(() => !__el._dgLS().get('bms_diag_watch').some(w => w.srv === 'w1')), 'dryf: kontrola usunięta z listy oczekujących');
  ok(await e.q(() => /⚠/.test(__el.shadowRoot.getElementById('tabDiag').textContent)), 'dryf: znacznik ⚠ na zakładce');
  await e.ctx.close();

  // D2. kontrola zakończona sukcesem → wpis oznaczony „ok”
  e = await setup(b, { haData: {} });
  await unlock(e); await sleep(800); await writeShutdown(e, 26); await sleep(800);
  await e.q(() => { window.__states['sensor.bms_monitor_status'] = { state: '0', attributes: { watches: [{ id: 'w1', status: 'ok', checks: [{ ok: true }, { ok: true }, { ok: true }] }] }, last_updated: new Date().toISOString() }; __el.hass = __mk(); });
  await e.q(() => { __el._dgS()._wcAt = 0; __el._dgSyncTab(); });
  ok(await e.q(() => __el._dgLS().get('bms_diag_log')[0].ver === 'ok' && (__el._dgLS().get('bms_diag_alarms') || []).length === 0), 'sukces z integracji → wpis dziennika ver=ok, brak alarmu');
  await e.ctx.close();

  // E. zapis do HA nie działa (np. brak uprawnień) → ostrzeżenie + dane zostają lokalnie; po naprawie dosyłane
  e = await setup(b, { haData: {}, failSet: true });
  await unlock(e); await sleep(800);
  await e.q(() => __el._dgLogAdd({ eid: 'number.x', name: 'X', from: '1', to: '2', ok: true, label: 't' }));
  await sleep(1500);
  const note = await e.q(() => __el.shadowRoot.getElementById('dgStoreNote').textContent);
  ok(/tylko w tej przeglądarce/.test(note) && /Unauthorized/.test(note), 'błąd zapisu: ostrzeżenie z przyczyną: ' + note);
  ok(await e.q(() => __el._dgLS().get('bms_diag_log').length === 1), 'błąd zapisu: dziennik nadal dostępny lokalnie');
  await e.q(() => { window.__cfg.failSet = false; });
  await sleep(16500);
  ok(await e.q(() => window.__store.log && window.__store.log.length === 1), 'po naprawie: zaległy dziennik dosłany do HA automatycznie');
  ok(/zapisywane w Home Assistant/.test(await e.q(() => __el.shadowRoot.getElementById('dgStoreNote').textContent)), 'po naprawie: ostrzeżenie znika');
  await e.ctx.close();

  // F. odczyt z HA nie działa przy otwarciu → ostrzeżenie; ponowna próba przy ponownym otwarciu zakładki
  e = await setup(b, { haData: { log: { value: [{ ts: 5, eid: 'number.z_ha' }] } }, failGet: true, seedLocal: { bms_diag_log: [{ ts: 1, eid: 'number.lokalny' }] } });
  await unlock(e); await sleep(600);
  ok(/tylko w tej przeglądarce/.test(await e.q(() => __el.shadowRoot.getElementById('dgStoreNote').textContent)), 'brak odczytu z HA: ostrzeżenie');
  ok(await e.q(() => __el._dgLS().get('bms_diag_log')[0].eid === 'number.lokalny'), 'brak odczytu z HA: działa na danych lokalnych');
  ok(await e.q(() => Object.keys(window.__sets).length === 0), 'brak odczytu z HA: nic nie jest wysyłane (nie nadpiszemy danych w HA lokalnymi)');
  await e.q(() => { window.__cfg.failGet = false; __el.shadowRoot.querySelector('[data-tab="main"]').click(); __el.shadowRoot.querySelector('[data-tab="diag"]').click(); });
  await sleep(1200);
  ok(await e.q(() => __el._dgLS().get('bms_diag_log')[0].eid === 'number.z_ha'), 'po ponownym otwarciu: dane z HA wczytane');
  await e.ctx.close();

  // G. watch_write niedostępny → kontrola lokalna i komunikat
  e = await setup(b, { haData: {}, failWatch: true });
  await unlock(e); await sleep(800); await writeShutdown(e, 27); await sleep(500);
  ok(await e.q(() => __el._dgLS().get('bms_diag_watch').some(w => w.eid === 'number.inverter_battery_shutdown_soc' && !w.srv)), 'brak usługi kontroli: kontrola lokalna pozostaje');
  ok(await e.q(() => /działa tylko przy otwartej karcie/.test(__el.shadowRoot.getElementById('dgToast').textContent)), 'brak usługi kontroli: czytelny komunikat');
  await e.ctx.close();

  await b.close();
  console.log('FAILS', fails); process.exit(fails ? 1 : 0);
})();
