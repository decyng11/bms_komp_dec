// Profile pracy (zakładka EMS): lista, podgląd zmian, zastosowanie, powrót, profil zakończony, brak uprawnień, błędy usług, XSS.
const { openCard, chromium } = require('./ui_env');
const { seed, curve, REPORT, HEALTH, tab, sr } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

const PROFILES = () => [
  { id: 'winter', name: 'Zima', icon: '❄️', desc: 'Krótkie dni i mało słońca <img src=x onerror=window.__pwn=1>.', active: false, nothing_to_change: false,
    changes: [
      { key: 'reserve_floor_soc', label: 'Dynamiczna rezerwa — minimum', kind: 'number', available: true, now: 15, target: 30, now_text: '15 %', target_text: '30 %', differs: true },
      { key: 'dynamic_reserve', label: 'Dynamiczna rezerwa SOC', kind: 'switch', available: true, now: false, target: true, now_text: 'wyłączone', target_text: 'włączone', differs: true },
      { key: 'grid_charge_enabled', label: 'Ładuj baterię z sieci w tanich godzinach', kind: 'switch', available: true, now: true, target: true, now_text: 'włączone', target_text: 'włączone', differs: false },
      { key: 'dawn_margin_soc', label: 'Margines SOC ponad próg odcięcia', kind: 'number', available: false, now: null, target: 15, now_text: '—', target_text: '15 %', differs: false },
    ] },
  { id: 'summer', name: 'Lato', icon: '☀️', desc: 'Dużo słońca.', active: false, nothing_to_change: true,
    changes: [{ key: 'pv_plan_pessimism_pct', label: 'Ostrożność prognozy PV', kind: 'number', available: true, now: 0, target: 0, now_text: '0 %', target_text: '0 %', differs: false }] },
  { id: 'vacation', name: 'Urlop', icon: '🏖', desc: 'Nikogo nie ma.', active: false, nothing_to_change: false,
    changes: [{ key: 'vacation_mode', label: 'Tryb urlopowy', kind: 'switch', available: true, now: false, target: true, now_text: 'wyłączone', target_text: 'włączone', differs: true }] },
  { id: 'storm', name: 'Burza', icon: '⛈', desc: 'Ryzyko awarii sieci.', active: false, nothing_to_change: false,
    changes: [{ key: 'storm_mode', label: 'Tryb burzowy', kind: 'switch', available: true, now: false, target: true, now_text: 'wyłączone', target_text: 'włączone', differs: true }] },
];

async function mkServer(e, opts = {}) {
  await e.q(([PR, opts]) => {
    window.__pfCalls = [];
    window.__pf = { active: null };
    const view = () => {
      const ps = JSON.parse(JSON.stringify(PR));
      ps.forEach((p) => { p.active = !!(window.__pf.active && window.__pf.active.id === p.id && !window.__pf.active.ended); });
      return { profiles: ps, active: window.__pf.active ? JSON.parse(JSON.stringify(window.__pf.active)) : null };
    };
    window.__pfView = view;
    window.__svc = window.__svc || {};
    window.__svc['bms_komp_dec.profiles_get'] = () => { window.__pfCalls.push(['get']); if (opts.getFail) throw new Error('Unknown service'); return { response: view() }; };
    window.__svc['bms_komp_dec.profile_apply'] = (m) => {
      const id = (m.service_data || m).id; window.__pfCalls.push(['apply', id]);
      if (opts.applyFail) throw new Error('boom');
      const p = PR.find((x) => x.id === id);
      window.__pf.active = { id, name: p.name, since: '2026-11-20T10:00:00+01:00', ended: null, can_revert: true,
        restore: [{ key: 'reserve_floor_soc', label: 'Dynamiczna rezerwa — minimum', now_text: '30 %', prev_text: '15 %' }, { key: 'dynamic_reserve', label: 'Dynamiczna rezerwa SOC', now_text: 'włączone', prev_text: 'wyłączone' }] };
      return { response: Object.assign({ ok: true, id, changed: 2, skipped: ['Margines SOC'] }, view()) };
    };
    window.__svc['bms_komp_dec.profile_revert'] = () => { window.__pfCalls.push(['revert']); window.__pf.active = null; return { response: Object.assign({ ok: true, restored: 2, kept: ['Min SOC do sprzedaży 6000W'] }, view()) }; };
    window.__el.hass = window.__mk();
  }, [PROFILES(), opts]);
}

(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  await seed(e, { curve: curve(), report: REPORT(), health: HEALTH });
  await mkServer(e);
  await tab(e, 'ems'); await sleep(1400);

  let t = await sr(e, '#exProfBox');
  ok(t && /Zima/.test(t) && /Lato/.test(t) && /Urlop/.test(t) && /Burza/.test(t), 'lista: cztery profile');
  ok(await e.q(() => __el.shadowRoot.querySelectorAll('#exProfBox [data-pf="pick"]').length === 4), 'lista: cztery przyciski profili');
  ok(await e.q(() => !!__el.shadowRoot.querySelector('[data-tile="ems-profiles"]')), 'kafelek „Profile pracy” w układzie EMS');
  ok(!/Zastosowany profil/.test(t) && !/Wróć do ustawień/.test(t), 'bez aktywnego profilu: brak banera i przycisku powrotu');
  ok(await e.q(() => !__el.shadowRoot.querySelector('#exProfBox [data-role="profile-preview"]')), 'podgląd zamknięty, dopóki nic nie wybrano');

  // podgląd Zimy
  await e.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="pick"][data-id="winter"]').click()); await sleep(200);
  t = await sr(e, '#exProfBox [data-role="profile-preview"]');
  ok(t && /Dynamiczna rezerwa — minimum15 %30 %/.test(t) && /Dynamiczna rezerwa SOCwyłączonewłączone/.test(t), 'podgląd: teraz → po profilu');
  ok(/Ładuj baterię z sieci w tanich godzinachwłączonewłączone \(bez zmian\)/.test(t), 'podgląd: ustawienie już zgodne oznaczone „bez zmian”');
  ok(/Margines SOC ponad próg odcięciabrak encji — pominięte/.test(t), 'podgląd: brak encji → pominięte');
  ok(await e.q(() => __el.shadowRoot.querySelectorAll('#exProfBox [data-role="profile-preview"] tbody tr').length === 4), 'podgląd: cztery wiersze');
  ok(/Krótkie dni i mało słońca/.test(t) && await e.q(() => !__el.shadowRoot.querySelector('#exProfBox img') && !window.__pwn), 'opis profilu zescape-owany (XSS)');
  ok(await e.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="apply"]').disabled === false), 'przycisk „Zastosuj” aktywny dla admina');
  ok(await e.q(() => window.__pfCalls.every((c) => c[0] === 'get')), 'sam podgląd nie wywołuje zmian');

  // kliknięcie tego samego profilu zwija podgląd; Lato: nic do zmiany
  await e.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="pick"][data-id="winter"]').click()); await sleep(150);
  ok(await e.q(() => !__el.shadowRoot.querySelector('#exProfBox [data-role="profile-preview"]')), 'ponowne kliknięcie zwija podgląd');
  await e.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="pick"][data-id="summer"]').click()); await sleep(150);
  ok(/nic się nie zmieni/.test(await sr(e, '#exProfBox')), 'Lato: komunikat „nic się nie zmieni”');
  await e.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="cancel"]').click()); await sleep(150);
  ok(await e.q(() => !__el.shadowRoot.querySelector('#exProfBox [data-role="profile-preview"]')), 'Anuluj zamyka podgląd');

  // zastosowanie
  await e.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="pick"][data-id="winter"]').click()); await sleep(150);
  await e.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="apply"]').click()); await sleep(500);
  ok(await e.q(() => JSON.stringify(window.__pfCalls.filter((c) => c[0] === 'apply')) === JSON.stringify([['apply', 'winter']])), 'zastosowanie: usługa profile_apply z id=winter');
  t = await sr(e, '#exProfBox');
  ok(/Profil „Zima” włączony — zmieniono 2 ustawień, pominięto 1/.test(t), 'zastosowanie: komunikat o wyniku');
  ok(/Zastosowany profil: Zima/.test(t) && /Zima ✓/.test(t), 'zastosowanie: baner i znacznik ✓ przy profilu');
  ok(/Dynamiczna rezerwa — minimum: 30 % → 15 %/.test(t), 'zastosowanie: lista tego, co przywróci powrót');
  ok(await e.q(() => !__el.shadowRoot.querySelector('#exProfBox [data-role="profile-preview"]')), 'zastosowanie: podgląd zamknięty');

  // powrót
  await e.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="revert"]').click()); await sleep(500);
  t = await sr(e, '#exProfBox');
  ok(await e.q(() => window.__pfCalls.some((c) => c[0] === 'revert')), 'powrót: usługa profile_revert');
  ok(/Przywrócono 2 ustawień; 1 zostawiono, bo zmieniłeś je ręcznie/.test(t) && !/Zastosowany profil/.test(t), 'powrót: komunikat i brak banera');

  // profil zakończony
  await e.q(() => { window.__pf.active = { id: 'storm', name: 'Burza', since: '2026-11-20T10:00:00+01:00', ended: { at: '2026-11-21T09:00:00+01:00', keys: ['storm_mode'] }, can_revert: true, restore: [] }; window.__el.hass = window.__mk(); });
  await e.q(() => { const s = __el._exS().prof; s.at = 0; s.msg = ''; __el._exProf(); }); await sleep(600);
  t = await sr(e, '#exProfBox');
  ok(/Profil Burza/.test(t) && /przestał obowiązywać/.test(t) && /Wróć do ustawień sprzed profilu/.test(t), 'profil zakończony: informacja i możliwość powrotu');
  ok(!/Burza ✓/.test(t), 'profil zakończony nie ma znacznika ✓');
  ok(e.errs.length === 0, 'brak błędów JS ' + JSON.stringify(e.errs));

  // brak uprawnień
  const e2 = await openCard(b, {});
  await seed(e2, { curve: curve(), report: REPORT(), health: HEALTH });
  await mkServer(e2);
  await e2.q(() => { window.__admin = false; window.__el.hass = window.__mk(); });
  await tab(e2, 'ems'); await sleep(1400);
  await e2.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="pick"][data-id="winter"]').click()); await sleep(200);
  ok(await e2.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="apply"]').disabled === true), 'zwykły użytkownik: „Zastosuj” wyłączony');
  ok(/wymaga konta administratora/.test(await sr(e2, '#exProfBox')), 'zwykły użytkownik: informacja o uprawnieniach');
  ok(e2.errs.length === 0, 'brak błędów JS (bez uprawnień) ' + JSON.stringify(e2.errs));

  // błąd zapisu
  const e3 = await openCard(b, {});
  await seed(e3, { curve: curve(), report: REPORT(), health: HEALTH });
  await mkServer(e3, { applyFail: true });
  await tab(e3, 'ems'); await sleep(1400);
  await e3.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="pick"][data-id="storm"]').click()); await sleep(150);
  await e3.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="apply"]').click()); await sleep(500);
  ok(/Nie udało się: boom/.test(await sr(e3, '#exProfBox')) && !/Zastosowany profil/.test(await sr(e3, '#exProfBox')), 'błąd usługi: czytelny komunikat, brak fałszywego sukcesu');
  ok(await e3.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="apply"]') === null || __el.shadowRoot.querySelector('#exProfBox [data-pf="apply"]').disabled === false), 'błąd usługi: można spróbować ponownie');
  ok(e3.errs.length === 0, 'brak błędów JS (błąd zapisu) ' + JSON.stringify(e3.errs));

  // starsza integracja
  const e4 = await openCard(b, {});
  await seed(e4, { curve: curve(), report: REPORT(), health: HEALTH });
  await mkServer(e4, { getFail: true });
  await tab(e4, 'ems'); await sleep(1400);
  t = await sr(e4, '#exProfBox');
  ok(/Nie udało się wczytać profili: Unknown service/.test(t) && await e4.q(() => !!__el.shadowRoot.querySelector('#exProfBox [data-pf="reload"]')), 'starsza integracja: komunikat i „Spróbuj ponownie”');
  ok(e4.errs.length === 0, 'brak błędów JS (starsza integracja) ' + JSON.stringify(e4.errs));

  await b.close();
  console.log(fails ? 'FAILS ' + fails : 'ALL OK');
  process.exit(fails ? 1 : 0);
})();
