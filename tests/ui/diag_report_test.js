// Ustawienia → Autotest → „📨 Raport do zgłoszenia”: jeden klik zbiera raport z integracji (usługa diagnostic_report) i go kopiuje;
// gdy przeglądarka blokuje kopiowanie, zostaje przycisk „Kopiuj” i pole do ręcznego zaznaczenia; jest też pobieranie .txt.
const { openCard, chromium } = require('./ui_env');
const { seed, curve, REPORT, HEALTH, openSec } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const ST = { version: '0.9.5', time: '2026-11-18T16:30:00+01:00', summary: { errors: 0, warnings: 0, ok: 1 }, commands: [],
  groups: [{ name: 'Falownik i połączenie', checks: [{ id: 'live_soc', title: 'SOC baterii', status: 'ok', detail: '80 %', fix: '' }] }] };
const REP = { text: 'EMS komp-dec 0.9.5.5 — raport diagnostyczny 2026-11-18T17:00:00+01:00\nFalownik: deye\n\n== Auto-stosowanie\n"why": "przesunięcie o 6.0 h <img src=x onerror=window.__pwn=1>"\nbrama x.x.x.x',
  filename: 'ems-raport-20261118-1700.txt', summary: { errors: 0, warnings: 0, log_lines: 12 } };

async function setup(b, opts) {
  const e = await openCard(b, Object.assign({ admin: true }, opts || {}));
  await seed(e, { curve: curve(), report: REPORT(), health: HEALTH });
  await e.q(([st, rep]) => { window.__svc = window.__svc || {}; window.__repN = 0;
    window.__svc['bms_komp_dec.self_test'] = () => ({ response: JSON.parse(JSON.stringify(st)) });
    window.__svc['bms_komp_dec.diagnostic_report'] = () => { window.__repN++; return { response: JSON.parse(JSON.stringify(rep)) }; }; }, [ST, REP]);
  await openSec(e, 'selftest'); await sleep(700);
  return e;
}
const clipOk = (e) => e.q(() => { window.__clip = null; Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true }); Object.defineProperty(navigator, 'clipboard', { value: { writeText: async (x) => { window.__clip = x; } }, configurable: true }); });
const clipBad = (e) => e.q(() => { window.__clip = null; Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true }); Object.defineProperty(navigator, 'clipboard', { value: { writeText: async () => { throw new Error('NotAllowedError'); } }, configurable: true }); document.execCommand = () => false; });
const ui = (e) => e.q(() => { const sh = __el.shadowRoot, ta = sh.getElementById('dgRepTxt');
  return { btn: !!sh.querySelector('[data-act="st-report"]'), btnTxt: (sh.querySelector('[data-act="st-report"]') || {}).textContent, copy: !!sh.querySelector('[data-act="st-report-copy"]'), dl: !!sh.querySelector('[data-act="st-report-dl"]'),
    msg: ((sh.getElementById('dgRepMsg') || {}).textContent || '').trim(), taShown: !!ta && getComputedStyle(ta).display !== 'none', taVal: ta ? ta.value : '', imgs: sh.querySelectorAll('#dgSt img').length,
    pwn: window.__pwn === 1, calls: window.__repN, doc: document.documentElement.scrollWidth }; });

(async () => {
  const b = await chromium.launch();
  // 1) kopiowanie działa → jeden klik wystarcza
  let e = await setup(b);
  let r = await ui(e);
  ok(r.btn && /Raport do zgłoszenia/.test(r.btnTxt) && !r.copy && !r.dl, 'jest przycisk „Raport do zgłoszenia”, na początku bez „Kopiuj” i „Pobierz”');
  ok(/zamazane/.test(await e.q(() => __el.shadowRoot.getElementById('dgSt').textContent)) && /hasła nie trafiają do raportu/.test(await e.q(() => __el.shadowRoot.getElementById('dgSt').textContent)), 'opis mówi, że dane są zamazane, a hasła nie trafiają do raportu');
  await clipOk(e);
  await e.q(() => __el.shadowRoot.querySelector('[data-act="st-report"]').click()); await sleep(600);
  r = await ui(e);
  ok(r.calls === 1, 'jedno kliknięcie = jedno wywołanie usługi diagnostic_report');
  ok((await e.q(() => window.__clip)) === REP.text, 'raport skopiowany do schowka w całości');
  ok(/Raport skopiowany/.test(r.msg) && !r.taShown, 'komunikat „skopiowany”, pole tekstowe ukryte');
  ok(r.copy && r.dl, 'po zebraniu pojawiają się „Kopiuj” i „Pobierz .txt”');
  ok(r.taVal === REP.text && r.imgs === 0 && !r.pwn, 'treść w polu jest escapowana (bez wstrzykiwania HTML), tekst identyczny z raportem');

  // 2) pobieranie .txt
  await e.q(() => { window.__dl = null; window.__blob = null; URL.createObjectURL = (bl) => { window.__blob = bl; return 'blob:test'; }; URL.revokeObjectURL = () => {};
    HTMLAnchorElement.prototype.click = function () { window.__dl = { name: this.download, href: this.href }; }; });
  await e.q(() => __el.shadowRoot.querySelector('[data-act="st-report-dl"]').click()); await sleep(200);
  const dl = await e.q(async () => ({ dl: window.__dl, txt: window.__blob ? await window.__blob.text() : null, type: window.__blob ? window.__blob.type : '' }));
  ok(dl.dl && dl.dl.name === 'ems-raport-20261118-1700.txt' && /blob:/.test(dl.dl.href), 'pobieranie: plik o nazwie z integracji (ems-raport-RRRRMMDD-GGMM.txt)');
  ok(dl.txt === REP.text && /text\/plain/.test(dl.type), 'pobieranie: zawartość pliku = raport, typ text/plain');
  await e.page.context().close();

  // 3) przeglądarka blokuje schowek → pole do ręcznego skopiowania + przycisk „Kopiuj”
  e = await setup(b);
  await clipBad(e);
  await e.q(() => __el.shadowRoot.querySelector('[data-act="st-report"]').click()); await sleep(600);
  r = await ui(e);
  ok(r.taShown && r.taVal === REP.text && /Raport gotowy/.test(r.msg) && r.copy, 'blokada schowka: pole z raportem widoczne, komunikat i przycisk „Kopiuj”');
  await clipOk(e);
  await e.q(() => __el.shadowRoot.querySelector('[data-act="st-report-copy"]').click()); await sleep(300);
  r = await ui(e);
  ok((await e.q(() => window.__clip)) === REP.text && !r.taShown && /Skopiowano raport/.test(r.msg), 'ponowna próba z przycisku „Kopiuj” działa, pole znika');
  ok(r.calls === 1, '„Kopiuj” nie woła usługi drugi raz');
  await e.page.context().close();

  // 4) błąd usługi (np. brak uprawnień) → czytelny komunikat, bez przycisków kopiowania
  e = await setup(b);
  await e.q(() => { window.__svc['bms_komp_dec.diagnostic_report'] = () => { throw new Error('Unauthorized'); }; });
  await e.q(() => __el.shadowRoot.querySelector('[data-act="st-report"]').click()); await sleep(500);
  r = await ui(e);
  ok(/Nie udało się zebrać raportu: .*Unauthorized/.test(r.msg) && !r.copy && !r.dl && r.btn, 'błąd usługi: komunikat z powodem, przycisk dostępny do ponowienia');
  await e.page.context().close();

  // 5) autotest padł, a raport nadal można pobrać (to właśnie wtedy jest potrzebny)
  e = await openCard(b, { admin: true });
  await seed(e, { curve: curve(), report: REPORT(), health: HEALTH });
  await e.q((rep) => { window.__svc = window.__svc || {}; window.__svc['bms_komp_dec.self_test'] = () => { throw new Error('Nie działa'); };
    window.__svc['bms_komp_dec.diagnostic_report'] = () => ({ response: JSON.parse(JSON.stringify(rep)) }); }, REP);
  await openSec(e, 'selftest'); await sleep(700);
  r = await ui(e);
  ok(r.btn && (await e.q(() => !!__el.shadowRoot.querySelector('#dgSt .dg-bad'))), 'autotest z błędem: przycisk raportu nadal dostępny');
  await clipOk(e); await e.q(() => __el.shadowRoot.querySelector('[data-act="st-report"]').click()); await sleep(500);
  ok((await e.q(() => window.__clip)) === REP.text, 'autotest z błędem: raport i tak się kopiuje');
  await e.page.context().close();

  // 7) HA otwarte przez http://adres-IP (brak bezpiecznego kontekstu → brak navigator.clipboard): kopiowanie przez zaznaczenie pola
  e = await setup(b);
  await e.q(() => { window.__sel = null; Object.defineProperty(window, 'isSecureContext', { value: false, configurable: true });
    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true });
    document.execCommand = (c) => { const ta = __el.shadowRoot.getElementById('dgRepTxt'); window.__sel = { c, val: ta ? ta.value : null, shown: ta ? getComputedStyle(ta).display : null }; return true; }; });
  await e.q(() => __el.shadowRoot.querySelector('[data-act="st-report"]').click()); await sleep(600);
  r = await ui(e); const sel = await e.q(() => window.__sel);
  ok(sel && sel.c === 'copy' && sel.val === REP.text && sel.shown !== 'none', 'http bez schowka: raport kopiowany przez zaznaczenie pola (execCommand copy)');
  ok(/Raport skopiowany/.test(r.msg) && !r.taShown, 'http bez schowka: komunikat „skopiowany”, pole chowa się po udanym kopiowaniu');
  await e.page.context().close();

  // 6) telefon 360 px: przyciski mieszczą się w karcie
  e = await setup(b, { mobile: true });
  await e.page.setViewportSize({ width: 360, height: 800 });
  await e.q(() => { document.getElementById('h').style.width = '360px'; });
  await clipOk(e); await e.q(() => __el.shadowRoot.querySelector('[data-act="st-report"]').click()); await sleep(500);
  const lay = await e.q(() => { const sh = __el.shadowRoot, card = sh.querySelector('#dgSt .dg-card').getBoundingClientRect();
    return { inside: [...sh.querySelectorAll('#dgSt [data-act^="st-report"], #dgRepMsg')].every(x => { const q = x.getBoundingClientRect(); return q.left >= card.left - 1 && q.right <= card.right + 1; }), doc: document.documentElement.scrollWidth }; });
  ok(lay.inside && lay.doc <= 360, `360 px: przyciski i komunikat mieszczą się w karcie, bez przewijania w bok (doc ${lay.doc})`);
  ok(e.errs.length === 0, 'brak błędów JS ' + JSON.stringify(e.errs));
  await e.page.context().close();
  console.log(fails ? `FAILS ${fails}` : 'OK');
  await b.close();
  process.exit(fails ? 1 : 0);
})();
