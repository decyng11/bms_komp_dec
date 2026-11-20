// Własne profile i profil z datami (zakładka EMS → Profile pracy): zapis, lista, usuwanie, planowanie, baner planu, uprawnienia, błędy, XSS
const { openCard, chromium } = require('./ui_env');
const { seed, curve, REPORT, HEALTH, tab, sr } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

const BUILTIN = () => [
  { id: 'winter', name: 'Zima', icon: '❄️', desc: 'Zima.', custom: false, active: false, nothing_to_change: false,
    changes: [{ key: 'reserve_floor_soc', label: 'Dynamiczna rezerwa — minimum', kind: 'number', available: true, now: 15, target: 30, now_text: '15 %', target_text: '30 %', differs: true }] },
  { id: 'vacation', name: 'Urlop', icon: '🏖', desc: 'Nikogo nie ma.', custom: false, active: false, nothing_to_change: false,
    changes: [{ key: 'vacation_mode', label: 'Tryb urlopowy', kind: 'switch', available: true, now: false, target: true, now_text: 'wyłączone', target_text: 'włączone', differs: true }] },
];
const iso = (off) => { const d = new Date(); d.setDate(d.getDate() + off); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };

async function mk(b, opts = {}) {
  const e = await openCard(b, {});
  await seed(e, { curve: curve(), report: REPORT(), health: HEALTH });
  await e.q(([B, opts]) => {
    window.__calls = [];
    window.__st = { custom: opts.custom ? JSON.parse(JSON.stringify(opts.custom)) : [], plan: opts.plan || null };
    const view = () => ({ profiles: JSON.parse(JSON.stringify(B)).concat(JSON.parse(JSON.stringify(window.__st.custom))), active: null,
      plan: window.__st.plan ? JSON.parse(JSON.stringify(window.__st.plan)) : null, custom_limit: 8, icons: ['⭐', '🏠', '🌙'], custom_keys: [] });
    window.__svc = window.__svc || {};
    window.__svc['bms_komp_dec.profiles_get'] = () => { window.__calls.push(['get']); if (opts.old) return { response: { profiles: JSON.parse(JSON.stringify(B)), active: null } }; return { response: view() }; };
    window.__svc['bms_komp_dec.profile_save'] = (m) => {
      const d = m.service_data || m; window.__calls.push(['save', d.name, d.icon]);
      if (opts.saveFail) throw new Error('Podaj nazwę profilu <b>x</b>');
      const ex = window.__st.custom.find((c) => c.name.toLowerCase() === String(d.name).toLowerCase());
      if (ex) ex.icon = d.icon || ex.icon;
      else window.__st.custom.push({ id: 'u_' + (window.__st.custom.length + 1), name: d.name, icon: d.icon || '⭐', desc: 'Własny zestaw ustawień: 3 ustawienia.', custom: true, active: false, nothing_to_change: true,
        changes: [{ key: 'reserve_floor_soc', label: 'Dynamiczna rezerwa — minimum', kind: 'number', available: true, now: 15, target: 15, now_text: '15 %', target_text: '15 %', differs: false }] });
      return { response: Object.assign({ ok: true, replaced: !!ex }, view()) };
    };
    window.__svc['bms_komp_dec/profile_delete'.replace('/', '.')] = (m) => {
      const id = (m.service_data || m).id; window.__calls.push(['delete', id]);
      window.__st.custom = window.__st.custom.filter((c) => c.id !== id);
      return { response: Object.assign({ ok: true, dropped_plan: false }, view()) };
    };
    window.__svc['bms_komp_dec.profile_schedule'] = (m) => {
      const d = m.service_data || m; window.__calls.push(['schedule', d.id, d.from, d.to]);
      if (opts.schedFail) throw new Error('Data „od” nie może być z przeszłości');
      const p = B.concat(window.__st.custom).find((x) => x.id === d.id);
      window.__st.plan = { id: d.id, name: p.name, from: d.from, to: d.to, status: 'waiting', phase: 'before', resume: null };
      return { response: Object.assign({ ok: true }, view()) };
    };
    window.__svc['bms_komp_dec.profile_schedule_clear'] = () => { window.__calls.push(['clear']); window.__st.plan = null; return { response: Object.assign({ ok: true }, view()) }; };
    window.__el.hass = window.__mk();
  }, [BUILTIN(), opts]);
  if (opts.user) await e.q(() => { window.__admin = false; window.__el.hass = window.__mk(); });
  await tab(e, 'ems'); await sleep(1400);
  return e;
}
const box = (e) => sr(e, '#exProfBox');
const q = (e, sel) => e.q((sel) => !!__el.shadowRoot.querySelector(sel), sel);
const setVal = (e, sel, v, ev) => e.q(([sel, v, ev]) => { const el = __el.shadowRoot.querySelector(sel); el.value = v; el.dispatchEvent(new Event(ev, { bubbles: true })); }, [sel, v, ev]);

(async () => {
  const b = await chromium.launch();

  // ---------- zapis własnego profilu
  let e = await mk(b);
  ok(await q(e, '#exProfBox [data-role="profile-save"]') && /Zapisz bieżące ustawienia jako własny profil/.test(await box(e)), 'formularz zapisu widoczny dla admina');
  ok(/Własnych profili: 0 z 8/.test(await box(e)) && /bez godzin, prądów, mocy i zabezpieczeń/.test(await box(e)), 'informacja o limicie i o tym, czego profil nie rusza');
  await setVal(e, '#exProfBox [data-pf-in="name"]', 'Weekend <img src=x onerror=window.__pwn8=1>', 'input'); await sleep(100);
  ok(await q(e, '#exProfBox [data-pf-in="name"]'), 'wpisanie nazwy nie przerysowuje formularza (fokus zostaje)');
  await setVal(e, '#exProfBox [data-pf-in="icon"]', '🏠', 'change'); await sleep(200);
  ok(await e.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf-in="name"]').value.startsWith('Weekend')), 'po zmianie ikony nazwa zostaje w polu');
  await e.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="save"]').click()); await sleep(500);
  ok(await e.q(() => window.__calls.some((c) => c[0] === 'save' && c[1].startsWith('Weekend') && c[2] === '🏠')), 'usługa profile_save z nazwą i ikoną');
  let t = await box(e);
  ok(/Zapisano własny profil z bieżących ustawień/.test(t) && /Własnych profili: 1 z 8/.test(t), 'komunikat i licznik po zapisie');
  ok(await e.q(() => __el.shadowRoot.querySelectorAll('#exProfBox [data-pf="pick"]').length === 3), 'własny profil na liście obok gotowych');
  ok(await e.q(() => !__el.shadowRoot.querySelector('#exProfBox img') && !window.__pwn8), 'nazwa profilu zescape-owana (XSS)');
  ok(await e.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf-in="name"]').value === ''), 'pole nazwy wyczyszczone po zapisie');

  // ---------- podgląd własnego profilu: usuwanie
  await e.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="pick"][data-id="u_1"]').click()); await sleep(200);
  ok(await q(e, '#exProfBox [data-pf="delete"][data-id="u_1"]') && /Usuń ten profil/.test(await box(e)), 'własny profil ma przycisk Usuń');
  await e.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="pick"][data-id="winter"]').click()); await sleep(200);
  ok(await e.q(() => !__el.shadowRoot.querySelector('#exProfBox [data-pf="delete"]')), 'gotowy profil nie ma przycisku Usuń');
  await e.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="pick"][data-id="u_1"]').click()); await sleep(200);
  await e.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="delete"]').click()); await sleep(500);
  ok(await e.q(() => window.__calls.some((c) => c[0] === 'delete' && c[1] === 'u_1')) && /Własny profil usunięty/.test(await box(e)) && await e.q(() => __el.shadowRoot.querySelectorAll('#exProfBox [data-pf="pick"]').length === 2), 'usunięcie: usługa, komunikat, lista bez profilu');
  ok(e.errs.length === 0, 'brak błędów JS ' + JSON.stringify(e.errs));

  // ---------- planowanie na daty
  e = await mk(b);
  await e.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="pick"][data-id="vacation"]').click()); await sleep(200);
  ok(await q(e, '#exProfBox [data-role="profile-schedule"]') && /Albo zaplanuj na daty/.test(await box(e)), 'podgląd: sekcja planowania na daty');
  ok(await e.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="schedule"]').disabled === true), 'bez dat przycisk Zaplanuj wyłączony');
  await setVal(e, '#exProfBox [data-pf-in="from"]', iso(3), 'change'); await sleep(150);
  ok(await e.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="schedule"]').disabled === true), 'tylko data „od”: przycisk nadal wyłączony');
  await setVal(e, '#exProfBox [data-pf-in="to"]', iso(1), 'change'); await sleep(150);
  ok(await e.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="schedule"]').disabled === true), '„do” przed „od”: przycisk wyłączony');
  await setVal(e, '#exProfBox [data-pf-in="to"]', iso(10), 'change'); await sleep(150);
  ok(await e.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="schedule"]').disabled === false), 'poprawne daty: przycisk aktywny');
  ok(await e.q((m) => __el.shadowRoot.querySelector('#exProfBox [data-pf-in="from"]').min === m, iso(0)), 'data „od” nie wcześniej niż dziś (min)');
  await e.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="schedule"]').click()); await sleep(500);
  ok(await e.q(([a, b_]) => JSON.stringify(window.__calls.filter((c) => c[0] === 'schedule')) === JSON.stringify([['schedule', 'vacation', a, b_]]), [iso(3), iso(10)]), 'usługa profile_schedule z id i datami');
  t = await box(e);
  ok(/Zaplanowano profil „Urlop” od/.test(t) && await q(e, '#exProfBox [data-role="profile-plan"]'), 'komunikat i baner planu');
  const dd = (o) => iso(o).slice(8) + '.' + iso(o).slice(5, 7);
  ok(new RegExp(`Zaplanowany profil: Urlop od ${dd(3)} do ${dd(10)} \\(włącznie\\) — włączy się sam pierwszego dnia`).test(t.replace(/\s+/g, ' ')), 'baner: nazwa, daty i informacja o starcie: ' + t.replace(/\s+/g, ' ').slice(0, 260));
  await e.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="plan-clear"]').click()); await sleep(500);
  ok(await e.q(() => window.__calls.some((c) => c[0] === 'clear')) && /Plan profilu anulowany/.test(await box(e)) && !(await q(e, '#exProfBox [data-role="profile-plan"]')), 'anulowanie planu: usługa, komunikat, baner znika');

  // plan trwający
  e = await mk(b, { plan: { id: 'vacation', name: 'Urlop', from: iso(-1), to: iso(4), status: 'active', phase: 'during', resume: null } });
  t = (await box(e)).replace(/\s+/g, ' ');
  ok(/Trwa zaplanowany profil: Urlop od/.test(t) && !/włączy się sam pierwszego dnia/.test(t) && /Zakończ teraz/.test(t), 'plan trwający: „Trwa…” i przycisk „Zakończ teraz”');

  // ---------- błędy usług
  e = await mk(b, { saveFail: true });
  await setVal(e, '#exProfBox [data-pf-in="name"]', 'X', 'input');
  await e.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="save"]').click()); await sleep(500);
  ok(/Nie udało się: Podaj nazwę profilu/.test(await box(e)) && await e.q(() => !__el.shadowRoot.querySelector('#exProfBox b')), 'błąd zapisu: komunikat bez interpretacji HTML');
  e = await mk(b, { schedFail: true });
  await e.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="pick"][data-id="vacation"]').click()); await sleep(150);
  await setVal(e, '#exProfBox [data-pf-in="from"]', iso(1), 'change'); await sleep(100); await setVal(e, '#exProfBox [data-pf-in="to"]', iso(2), 'change'); await sleep(100);
  await e.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="schedule"]').click()); await sleep(500);
  ok(/Nie udało się: Data „od” nie może być z przeszłości/.test(await box(e)) && !(await q(e, '#exProfBox [data-role="profile-plan"]')), 'błąd planowania: czytelny komunikat, brak fałszywego planu');

  // ---------- zwykły użytkownik
  e = await mk(b, { user: true, custom: [{ id: 'u_1', name: 'Mój', icon: '⭐', desc: 'x', custom: true, active: false, nothing_to_change: true, changes: [] }],
                    plan: { id: 'vacation', name: 'Urlop', from: iso(2), to: iso(5), status: 'waiting', phase: 'before', resume: null } });
  t = await box(e);
  ok(!(await q(e, '#exProfBox [data-role="profile-save"]')) && !(await q(e, '#exProfBox [data-pf="plan-clear"]')), 'zwykły użytkownik: bez formularza zapisu i bez Anuluj plan');
  ok(/Zaplanowany profil: Urlop/.test(t.replace(/\s+/g, ' ')), 'zwykły użytkownik widzi plan');
  await e.q(() => __el.shadowRoot.querySelector('#exProfBox [data-pf="pick"][data-id="u_1"]').click()); await sleep(200);
  ok(!(await q(e, '#exProfBox [data-pf="delete"]')) && !(await q(e, '#exProfBox [data-role="profile-schedule"]')), 'zwykły użytkownik: bez Usuń i bez planowania');

  // ---------- stary backend (bez własnych profili i planu) i śmieci
  e = await mk(b, { old: true });
  t = await box(e);
  ok(/Zima/.test(t) && !(await q(e, '#exProfBox [data-role="profile-plan"]')) && e.errs.length === 0 && /Własnych profili: 0 z 8/.test(t), 'stary backend: lista działa, domyślny limit 8, bez błędów JS ' + JSON.stringify(e.errs));
  for (const [name, plan] of [['plan = napis', 'x'], ['plan bez dat', { id: 'a', name: 'A', status: 'waiting' }], ['plan ze złymi datami', { id: 'a', name: 'A', from: '<b>', to: 5, status: 'waiting' }], ['plan = liczba', 5]]) {
    e = await mk(b, { plan });
    ok(!(await q(e, '#exProfBox [data-role="profile-plan"]')) && /Zima/.test(await box(e)) && e.errs.length === 0, `śmieci (${name}): baner pominięty, lista działa, bez błędów JS`);
  }
  await b.close();
  console.log(fails ? 'FAILS ' + fails : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
