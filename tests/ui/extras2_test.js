const { openCard, chromium, readFile } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const T = require('./extras_helpers');
const { seed, curve, REPORT, HEALTH, tab, sr, openModes, openSec } = T;

(async () => {
  const b = await chromium.launch();

  // ===== 1. raport + zdrowie baterii (zakładka Zysk i log)
  let e = await openCard(b, {});
  await seed(e, { curve: curve(), report: REPORT(), health: HEALTH });
  await tab(e, 'log');
  await e.page.waitForFunction(() => { const x = __el.shadowRoot.querySelector('#exReportBox'); return x && /Bilans z siecią/.test(x.textContent); }, null, { timeout: 8000 });
  const rt = await sr(e, '#exReportBox');
  ok(/Listopad 2026/.test(rt) && /dane z 3 z 30 dni/.test(rt) && /bieżący/.test(rt), 'raport: tytuł i zakres danych');
  ok(/\+4,30 zł/.test(rt) && /12,50 zł/.test(rt) && /8,20 zł/.test(rt), 'raport: bilans, sprzedaż i zakup');
  ok(/18,4 kWh · śr\. 0,68 zł\/kWh/.test(rt) && /14,1 kWh · śr\. 0,58/.test(rt), 'raport: energia i średnie ceny');
  ok(/autokonsumpcja 65%/.test(rt) && /samowystarczalność 77%/.test(rt), 'raport: autokonsumpcja i samowystarczalność');
  ok(/24 \/ 21 kWh/.test(rt) && /sprawność 89%|sprawność 88%/.test(rt), 'raport: bateria i sprawność cyklu');
  ok(/Oszczędność \(szacunek\)/i.test(rt) && /orientacyjnie/.test(rt) && /35,70 zł/.test(rt), 'raport: oszczędność oznaczona jako szacunek');
  ok(/Najlepszy dzień: 2026-11-02/.test(rt) && /Najsłabszy dzień: 2026-11-01/.test(rt) && /ujemnej cenie RCE: 0,6 kWh/.test(rt), 'raport: najlepszy/najsłabszy dzień, ujemne ceny');
  ok(await e.q(() => __el.shadowRoot.querySelector('#exReportBox [data-ex="rep-next"]').disabled), 'raport: „następny” wyłączony dla bieżącego miesiąca');
  const ht = await sr(e, '#exHealthBox');
  ok(/89,2%/.test(ht) && /88,1%/.test(ht) && /87,0%/.test(ht) && /z 6 dób/.test(ht), 'zdrowie: sprawność 7/30/90 dni z liczbą dób');
  ok(/\+1,1 pp/.test(ht) && /9,6 kWh/.test(ht) && /ustawiona 10,0 kWh · 11 pomiarów/.test(ht) && /96%/.test(ht) && /nie jest pomiarem SOH/.test(ht), 'zdrowie: trend, pojemność, stosunek do ustawionej');
  ok(!/odbiega od ustawionej/.test(ht), 'zdrowie: brak ostrzeżenia przy 96%');

  // poprzedni miesiąc → usługa monthly_report
  await e.q((r) => { window.__svc = window.__svc || {}; window.__svc['bms_komp_dec.monthly_report'] = (m) => { window.__repCalls = (window.__repCalls || []).concat([m.service_data]); if (m.service_data.month === 9) throw new Error('baza niedostępna'); return { response: Object.assign({}, r, { month: m.service_data.month, year: m.service_data.year, title: 'Miesiąc ' + m.service_data.month, net: -1.5, days_with_data: m.service_data.month === 8 ? 0 : 20, complete: true, days_in_month: 31 }) }; }; }, REPORT());
  await e.q(() => __el.shadowRoot.querySelector('#exReportBox [data-ex="rep-prev"]').click());
  await sleep(500);
  const r2 = await sr(e, '#exReportBox');
  ok(await e.q(() => window.__repCalls[0].year === 2026 && window.__repCalls[0].month === 10), 'raport: poprzedni miesiąc → usługa (2026, 10)');
  ok(/Miesiąc 10/.test(r2) && /pełny miesiąc/.test(r2) && /−1,50 zł/.test(r2) && !/bieżący/.test(r2), 'raport: dane z poprzedniego miesiąca wyświetlone');
  ok(await e.q(() => !__el.shadowRoot.querySelector('#exReportBox [data-ex="rep-next"]').disabled), 'raport: „następny” aktywny dla starszego miesiąca');
  await e.q(() => __el.shadowRoot.querySelector('#exReportBox [data-ex="rep-prev"]').click()); await sleep(500);
  ok(/Błąd: baza niedostępna/.test(await sr(e, '#exReportBox')), 'raport: błąd usługi pokazany użytkownikowi');
  await e.q(() => __el.shadowRoot.querySelector('#exReportBox [data-ex="rep-prev"]').click()); await sleep(500);
  ok(await e.q(() => window.__repCalls[window.__repCalls.length - 1].month === 8) && /Brak danych za ten miesiąc/.test(await sr(e, '#exReportBox')), 'raport: miesiąc bez danych → komunikat');
  // wróć do bieżącego przez „następny” x3
  for (let i = 0; i < 3; i++) { await e.q(() => { const n = __el.shadowRoot.querySelector('#exReportBox [data-ex="rep-next"]'); if (n && !n.disabled) n.click(); }); await sleep(450); }
  ok(/Listopad 2026/.test(await sr(e, '#exReportBox')) && /bieżący/.test(await sr(e, '#exReportBox')), 'raport: powrót do bieżącego miesiąca (z sensora)');
  // odświeżenie sensora nie niszczy nawigacji
  ok(e.errs.length === 0, '1: brak błędów JS ' + JSON.stringify(e.errs));
  await e.ctx.close();

  // puste dane i skrajne wartości
  e = await openCard(b, {});
  await seed(e, { curve: curve(), report: REPORT({ days_with_data: 0, days: [], best_day: null, worst_day: null }), health: { eff_7d: null, days_7d: 0, eff_30d: null, days_30d: 0, eff_90d: null, days_90d: 0, eff_trend_pp: null, capacity_est_kwh: null, capacity_samples: 2, capacity_configured_kwh: 10, soh_est_pct: null } });
  await tab(e, 'log');
  await e.page.waitForFunction(() => { const x = __el.shadowRoot.querySelector('#exReportBox'); return x && !/Ładowanie…/.test(x.textContent); }, null, { timeout: 8000 });
  ok(/Brak danych za ten miesiąc/.test(await sr(e, '#exReportBox')), 'raport: brak danych w miesiącu');
  const h2 = await sr(e, '#exHealthBox');
  ok((h2.match(/za mało pełnych dób/g) || []).length === 3 && /potrzeba ≥ 15 dób/.test(h2) && /za mało pełnych cykli \(2\/3\)/.test(h2), 'zdrowie: brak danych → czytelne komunikaty (bez NaN)');
  ok(!/NaN|undefined|null/.test(h2 + await sr(e, '#exReportBox')), 'zdrowie/raport: brak NaN/undefined');
  await e.q(() => { window.__states['sensor.bms_battery_health'].attributes = { eff_30d: 80, days_30d: 10, capacity_est_kwh: 7.0, capacity_samples: 8, capacity_configured_kwh: 10, soh_est_pct: 70 }; window.__states['sensor.bms_battery_health'].last_updated = new Date().toISOString(); __el.hass = __mk(); __el._lastLogKey = null; __el._renderLogTab(); });
  await sleep(300);
  ok(/odbiega od ustawionej pojemności/.test(await sr(e, '#exHealthBox')), 'zdrowie: ostrzeżenie przy szacunku 70% ustawionej pojemności');
  ok(e.errs.length === 0, '1b: brak błędów JS ' + JSON.stringify(e.errs));
  await e.ctx.close();

  // ===== 2. kreator instalacji
  const HC = { version: '0.6.0', checks: [
    { id: 'ctl_work_mode', title: 'Tryb pracy falownika', status: 'ok', detail: 'select.deye_work_mode', fix: '' },
    { id: 'ctl_tou', title: 'Harmonogram TOU', status: 'error', detail: 'Nie znaleziono encji select.deye_time_of_use <i>x</i>.', fix: 'Wskaż encję w konfiguracji.' },
    { id: 'notify', title: 'Powiadomienia na telefon', status: 'warn', detail: 'Nie ustawiono usługi.', fix: 'Wpisz usługę.' }],
    commands: [{ key: 'sprzedaz_6000w', label: 'Sprzedaż 6000 W', ok: true, error: null, steps: [{ domain: 'select', entity_id: 'select.deye_work_mode', value: 'Selling First', exists: true }, { domain: 'number', entity_id: 'number.deye_export_surplus_power', value: 6000, exists: true }] },
      { key: 'przywroc_ladowanie', label: 'Przywróć ładowanie', ok: false, error: 'brak encji: number.deye_x', steps: [{ domain: 'number', entity_id: 'number.deye_x', value: 170, exists: false }] }],
    summary: { errors: 1, warnings: 1, ok: 1, commands_failing: 1, ready: false } };
  e = await openCard(b, {});
  await seed(e, { curve: curve(), report: REPORT(), health: HEALTH });
  await tab(e, 'diag'); await sleep(400);
  ok(await e.q(() => !__el.shadowRoot.querySelector('#exWizBox') && !!__el.shadowRoot.getElementById('dgPw')), 'kreator niewidoczny przed podaniem hasła');
  await openSec(e, 'wizard');
  ok(await e.q(() => { const ems = __el.shadowRoot.querySelector('[data-tab-content="ems"]'); const dg = __el.shadowRoot.querySelector('[data-tab-content="diag"]'); return !ems.querySelector('#exWizBox') && !!dg.querySelector('#exWizBox'); }), 'kreator w Diagnostyce po odblokowaniu (sekcja „Kreator instalacji”), nie w EMS');
  await e.page.waitForFunction(() => { const x = __el.shadowRoot.querySelector('#exWizBox'); return x && /Sprawdź konfigurację/.test(x.textContent); }, null, { timeout: 8000 });
  ok(/Niczego nie wysyła do falownika/.test(await sr(e, '#exWizBox')), 'kreator: informacja, że nic nie jest zapisywane');
  await e.q((hc) => { window.__svc = window.__svc || {}; window.__svc['bms_komp_dec.health_check'] = (m) => { window.__hcCalls = (window.__hcCalls || 0) + 1; window.__hcData = window.__hcData || hc; if (window.__hcFail) throw new Error('Unauthorized'); return { response: window.__hcData }; }; window.__copied = null; Object.defineProperty(navigator, 'clipboard', { value: { writeText: async (t) => { window.__copied = t; } }, configurable: true }); }, HC);
  const callsBefore = await e.q(() => window.__calls.length);
  await e.q(() => __el.shadowRoot.querySelector('#exWizBox [data-ex="wiz-run"]').click());
  await e.page.waitForFunction(() => /do poprawy/.test(__el.shadowRoot.querySelector('#exWizBox').textContent), null, { timeout: 5000 });
  const wt = await sr(e, '#exWizBox');
  ok(/❌ do poprawy: 1 błędów, 1 komend nie zadziała/.test(wt) && /⚠ 1 uwag/.test(wt) && /wersja 0\.6\.0/.test(wt), 'kreator: podsumowanie');
  ok(await e.q(() => __el.shadowRoot.querySelector('#exWizBox .ex-chk b').textContent === 'Harmonogram TOU'), 'kreator: błędy na górze listy');
  ok(await e.q(() => !__el.shadowRoot.querySelector('#exWizBox .ex-chk i')), 'kreator: HTML z odpowiedzi zescape-owany');
  ok(/Nie znaleziono encji select\.deye_time_of_use/.test(wt) && /→ Wskaż encję w konfiguracji\./.test(wt), 'kreator: opis i wskazówka naprawy');
  ok(/Sprzedaż 6000 W/.test(wt) && /select\.set/.test(wt) && /= Selling First/.test(wt) && /= 6000/.test(wt), 'kreator: podgląd komend');
  ok(await e.q(() => { const d = __el.shadowRoot.querySelectorAll('#exWizBox details.ex-cmd'); return d.length === 2 && !d[0].open && d[1].open; }), 'kreator: niedziałająca komenda rozwinięta, działająca zwinięta');
  ok(await e.q((n) => window.__calls.length === n, callsBefore), 'kreator: żadna usługa sterująca nie została wywołana (tylko odczyt)');
  await e.q(() => __el.shadowRoot.querySelector('#exWizBox [data-ex="wiz-copy"]').click()); await sleep(200);
  const cp = await e.q(() => window.__copied);
  ok(cp && /\[ERROR\] Harmonogram TOU/.test(cp) && /\[BŁĄD\] Przywróć ładowanie — brak encji: number\.deye_x/.test(cp) && /number\.deye_x = 170 \(brak encji\)/.test(cp), 'kreator: raport tekstowy skopiowany');
  // gotowe
  await e.q((hc) => { window.__hcData = Object.assign({}, hc, { checks: hc.checks.slice(0, 1), commands: [hc.commands[0]], summary: { errors: 0, warnings: 0, ok: 1, commands_failing: 0, ready: true } }); }, HC);
  await e.q(() => __el.shadowRoot.querySelector('#exWizBox [data-ex="wiz-run"]').click()); await sleep(400);
  ok(/✅ gotowe do pracy/.test(await sr(e, '#exWizBox')), 'kreator: stan „gotowe do pracy”');
  // błąd usługi (np. brak uprawnień)
  await e.q(() => { window.__hcFail = true; });
  await e.q(() => __el.shadowRoot.querySelector('#exWizBox [data-ex="wiz-run"]').click()); await sleep(400);
  ok(/Nie udało się wykonać sprawdzenia: Unauthorized/.test(await sr(e, '#exWizBox')) && /wymaga konta administratora/.test(await sr(e, '#exWizBox')), 'kreator: błąd usługi pokazany z przyczyną');
  await e.q(() => { window.__hcFail = false; });
  await e.q(() => __el.shadowRoot.querySelector('#exWizBox [data-ex="wiz-run"]').click()); await sleep(400);
  ok(/gotowe do pracy/.test(await sr(e, '#exWizBox')), 'kreator: po naprawie działa ponownie');
  ok(e.errs.length === 0, '2: brak błędów JS ' + JSON.stringify(e.errs));
  await e.ctx.close();

  // ===== 3. baner statusu i tryby (rdzeń; nie wymaga modułu dodatków)
  e = await openCard(b, {});
  await seed(e, { curve: curve() });
  await sleep(400);
  ok(await e.q(() => __el.shadowRoot.querySelector('#statusBanner').style.display === 'none'), 'baner: ukryty, gdy wszystko w porządku');
  const nowS = Math.floor(Date.now() / 1000);
  await seed(e, { curve: curve(), monitor: { fault_note: 'Opis kodu dotyczy hybryd niskonapięciowych Deye (SG01LP1). W innych modelach znaczenie bywa inne.', alarms: [{ entity_id: 'sensor.deye_alert', state: 'F35 <img src=x onerror=window.__xss=1>', text: 'Brak sieci AC' }], low_soc_active: false,
    watches: [{ id: 'w1', status: 'drift', label: 'Zero export', entity_id: 'number.x', expected: 20, t0: nowS - 600, checks: [{ value: 65516, note: 'przepełnienie U16', ok: false }] }, { id: 'w2', status: 'drift', label: 'Stary', expected: 1, t0: nowS - 9 * 3600, checks: [{ value: 5 }] }, { id: 'w3', status: 'pending', label: 'Czeka', expected: 3, t0: nowS, checks: [] }],
    storm_until: nowS + 7200 }, storm_mode: 'on', vacation_mode: 'on' });
  await sleep(300);
  const bn = await sr(e, '#statusBanner');
  ok(/Alarm falownika: sensor\.deye_alert = F35/.test(bn) && /Brak sieci AC/.test(bn), 'baner: alarm falownika z opisem kodu');
  ok(/Zero export: ustawiono 20, a falownik raportuje 65516 \(przepełnienie U16\)/.test(bn), 'baner: dryf parametru po zapisie');
  ok(!/Stary|Czeka/.test(bn), 'baner: stary dryf (>6 h) i oczekująca kontrola nie są pokazywane');
  ok(/Tryb burzowy do/.test(bn) && /rezerwa 100%/.test(bn) && /Tryb urlopowy/.test(bn) && /250 W/.test(bn), 'baner: tryb burzowy (do kiedy) i urlopowy (zużycie)');
  ok(await e.q(() => window.__xss === undefined && !__el.shadowRoot.querySelector('#statusBanner img')), 'baner: znaczniki HTML w stanie alarmu nie są wykonywane');
  ok(await e.q(() => __el.shadowRoot.querySelectorAll('#statusBanner .sb-item.bad').length === 2 && __el.shadowRoot.querySelectorAll('#statusBanner .sb-item.warn').length === 1), 'baner: kolory — 2 czerwone, 1 pomarańczowy');
  ok(await e.q(() => /⚠/.test(__el.shadowRoot.getElementById('tabDiag').textContent)), 'zakładka Diagnostyka: ⚠ od alarmu z integracji');
  ok(/ⓘ/.test(bn) && await e.q(() => /niskonapięciowych/.test(__el.shadowRoot.querySelector('#statusBanner .sb-item span[title]').title)), 'baner: zastrzeżenie o modelu falownika w podpowiedzi ⓘ');
  // tryby — przeniesione do Diagnostyki (zakładka „🛡️ Tryby”)
  await tab(e, 'ems');
  ok(await e.q(() => !__el.shadowRoot.querySelector('#modesBox') && !/Tryby i powiadomienia/.test(__el.shadowRoot.querySelector('[data-tab-content="ems"]').textContent)), 'tryby: sekcji nie ma już w zakładce EMS');
  await tab(e, 'main');
  ok(await e.q(() => !__el.shadowRoot.querySelector('[data-mode-sw]') && !/Tryby i powiadomienia/.test(__el.shadowRoot.querySelector('[data-tab-content="main"]').textContent)), 'tryby: sekcji nie ma na stronie głównej');
  await openModes(e);
  const dgq = (f, ...a) => e.q(f, ...a);
  ok(await dgq(() => !/Ładowanie modułu/.test(__el.shadowRoot.getElementById('diagRoot').textContent) && __el.shadowRoot.getElementById('diagRoot').querySelectorAll('.chart-empty').length === 0), 'Diagnostyka: po załadowaniu modułu nie zostaje napis „Ładowanie modułu…”');
  ok(await dgq(() => __el.shadowRoot.querySelectorAll('#dgBody [data-act="mode-sw"]').length === 7 && __el.shadowRoot.querySelectorAll('#dgBody input[data-mode-num]').length === 2), 'tryby (Diagnostyka): 5 przełączników i 2 pola liczbowe');
  ok(/Tryb burzowy/.test(await sr(e, '#dgBody')) && /Tryb urlopowy/.test(await sr(e, '#dgBody')) && /Powiadomienia/.test(await sr(e, '#dgBody')) && /Auto-stosowanie: tylko podgląd/.test(await sr(e, '#dgBody')), 'tryby (Diagnostyka): nazwy i opisy');
  ok(await dgq(() => __el.shadowRoot.querySelector('[data-act="mode-sw"][data-k="storm_mode"]').classList.contains('green') && !__el.shadowRoot.querySelector('[data-act="mode-sw"][data-k="auto_apply_dry_run"]').classList.contains('green')), 'tryby (Diagnostyka): stan przycisków zgodny ze stanem encji');
  await e.q(() => { window.__calls.length = 0; __el.shadowRoot.querySelector('[data-act="mode-sw"][data-k="auto_apply_dry_run"]').click(); }); await sleep(100);
  ok(await dgq(() => JSON.stringify(window.__calls[0]) === JSON.stringify(['switch', 'turn_on', { entity_id: 'switch.bms_auto_apply_dry_run' }])), 'tryby (Diagnostyka): kliknięcie → switch.turn_on dla właściwej encji');
  await e.q(() => { window.__calls.length = 0; __el.shadowRoot.querySelector('[data-act="mode-sw"][data-k="storm_mode"]').click(); }); await sleep(100);
  ok(await dgq(() => window.__calls[0][1] === 'turn_off' && window.__calls[0][2].entity_id === 'switch.bms_storm_mode'), 'tryby (Diagnostyka): włączony tryb burzowy → turn_off');
  ok(await dgq(() => !window.__calls.some((c) => c[0] === 'bms_komp_dec') && !window.__ws.some((t) => /watch/.test(t))), 'tryby (Diagnostyka): zapis nie zgłasza się do kontroli odczytu falownika');
  await e.q(() => { window.__calls.length = 0; const i = __el.shadowRoot.querySelector('[data-mode-num="storm_mode_hours"]'); i.value = '48'; i.dispatchEvent(new Event('input', { bubbles: true })); }); await sleep(50);
  ok(await dgq(() => __el.shadowRoot.querySelector('[data-mode-num="storm_mode_hours"]').classList.contains('dirty') && window.__calls.length === 0), 'tryby (Diagnostyka): zmiana pola oznaczona, ale jeszcze niezapisana');
  await e.q(() => { __el.hass = __mk(); }); await sleep(1300);
  ok(await dgq(() => __el.shadowRoot.querySelector('[data-mode-num="storm_mode_hours"]').value === '48'), 'tryby (Diagnostyka): odświeżenie stanu nie kasuje wpisywanej wartości');
  await e.q(() => { __el.shadowRoot.querySelector('[data-act="mode-save"][data-k="storm_mode_hours"]').click(); }); await sleep(100);
  ok(await dgq(() => JSON.stringify(window.__calls[0]) === JSON.stringify(['number', 'set_value', { entity_id: 'number.bms_storm_mode_hours', value: 48 }])), 'tryby (Diagnostyka): „Zapisz” → number.set_value 48');
  await e.q(() => { window.__calls.length = 0; const i = __el.shadowRoot.querySelector('[data-mode-num="vacation_load_w"]'); i.value = '300'; i.focus(); i.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, composed: true })); }); await sleep(100);
  ok(await dgq(() => JSON.stringify(window.__calls[0]) === JSON.stringify(['number', 'set_value', { entity_id: 'number.bms_vacation_load_w', value: 300 }])), 'tryby (Diagnostyka): Enter w polu zapisuje wartość');
  await e.q(() => { window.__calls.length = 0; const i = __el.shadowRoot.querySelector('[data-mode-num="storm_mode_hours"]'); i.value = '500'; __el.shadowRoot.querySelector('[data-act="mode-save"][data-k="storm_mode_hours"]').click(); }); await sleep(100);
  ok(await dgq(() => window.__calls.length === 0) && /Największa dozwolona wartość: 96/.test(await sr(e, '#dgToast')), 'tryby (Diagnostyka): wartość powyżej zakresu encji jest odrzucona z komunikatem');
  await e.q(() => { window.__calls.length = 0; const i = __el.shadowRoot.querySelector('[data-mode-num="vacation_load_w"]'); i.value = 'abc'; __el.shadowRoot.querySelector('[data-act="mode-save"][data-k="vacation_load_w"]').click(); }); await sleep(100);
  ok(await dgq(() => window.__calls.length === 0), 'tryby (Diagnostyka): niepoprawna liczba nie wywołuje usługi');
  // brak encji (stara wersja integracji)
  await e.q(() => { delete window.__states['switch.bms_storm_mode']; delete window.__states['number.bms_vacation_load_w']; __el.hass = __mk(); }); await sleep(1400);
  ok(await dgq(() => __el.shadowRoot.querySelector('[data-act="mode-sw"][data-k="storm_mode"]').disabled && __el.shadowRoot.querySelector('[data-mode-num="vacation_load_w"]').disabled) && /niedostępne/.test(await sr(e, '#dgBody')), 'tryby (Diagnostyka): brak encji → wyłączone z komunikatem');
  ok(await dgq(() => !window.__xss), 'tryby (Diagnostyka): brak wykonania obcego HTML');
  ok(e.errs.length === 0, '3: brak błędów JS ' + JSON.stringify(e.errs));
  await e.ctx.close();

  // kafelek „Rezerwa SOC” w trybie burzowym
  e = await openCard(b, {});
  await seed(e, { curve: curve(), storm: true });
  await e.q(() => { window.__states['sensor.bms_reserve_soc'].state = '100'; window.__states['sensor.bms_reserve_soc'].attributes = { storm: true, enabled: true, need_kwh: 10, until_hour: null, capacity_kwh: 10, inverter_floor: 25 }; window.__states['sensor.bms_decision_log'] = { state: 'x', attributes: { entries: [] }, last_updated: new Date().toISOString() }; __el.hass = __mk(); });
  await tab(e, 'log'); await sleep(400);
  const tile = await sr(e, '#logTabBody');
  ok(/tryb burzowy — cała energia zostaje w baterii/.test(tile) && !/do \?:00|do null:00/.test(tile), 'Rezerwa SOC: tryb burzowy bez „do ?:00”');
  await e.ctx.close();

  console.log('FAILS', fails); await b.close(); process.exit(fails ? 1 : 0);
})();
