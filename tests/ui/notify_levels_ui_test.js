// Powiadomienia: (1) konfigurator — poziom „na telefon” (wszystkie / ważne / krytyczne), autoodczyt, etykiety ważności przy rodzajach;
// (2) dzwonek — informacje czytają się po zamknięciu okienka, okienko wyskakuje samo tylko przy ostrzeżeniu/błędzie, znacznik „odczytane automatycznie”.
const { openCard, chromium } = require('./ui_env');
const { seed, curve, REPORT, HEALTH, openSec } = require('./extras_helpers');
const fs = require('fs');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const BASE = JSON.parse(fs.readFileSync('notify_payload.json', 'utf8'));
const PRIO = { low_soc: 1, alarm: 1, summary_daily: 2, rce_negative: 2, battery_full: 3, rce_high: 3 };
const withPrio = (pay, lvl, ar) => { const p = JSON.parse(JSON.stringify(pay)); p.catalog.forEach(c => { c.prio = PRIO[c.key] || 2; }); p.settings.phone_level = lvl; p.settings.auto_read = ar; return p; };

(async () => {
  const b = await chromium.launch();
  // ------------------------------------------------------------ 1) konfigurator
  let e = await openCard(b, { admin: true });
  await seed(e, { curve: curve(), report: REPORT(), health: HEALTH });
  await e.q((pay) => { window.__svc = window.__svc || {}; window.__ntSet = [];
    window.__svc['bms_komp_dec.notify_settings_get'] = () => ({ response: JSON.parse(JSON.stringify(pay)) });
    window.__svc['bms_komp_dec.notify_settings_set'] = (m) => { const st = (m.service_data || m).settings; window.__ntSet.push(st); return { response: { settings: st } }; }; }, withPrio(BASE, 'important', true));
  await openSec(e, 'notify'); await sleep(700);
  const cfg = () => e.q(() => { const R = __el.shadowRoot, sel = R.getElementById('dgNtPhoneLevel'), ar = R.getElementById('dgNtAutoRead'), row = (k) => R.querySelector(`#dgNt [data-nt-row="${k}"]`);
    const tag = (k) => { const r = row(k); return r ? { p: (r.querySelector('[data-prio]') || {}).dataset ? r.querySelector('[data-prio]').dataset.prio : null, only: !!r.querySelector('[data-dzwonek]') } : null; };
    return { has: !!R.getElementById('dgNtLevel'), lvl: sel && sel.value, auto: ar && ar.checked, low: tag('low_soc'), sum: tag('summary_daily'), cyc: tag('rce_high'), hint: tag('battery_full'),
      onlyN: R.querySelectorAll('#dgNt [data-dzwonek]').length, save: !R.querySelector('#dgNt [data-act="nt-save"]').disabled, txt: (R.getElementById('dgNtLevel') || {}).textContent || '' }; });
  let c = await cfg();
  ok(c.has && c.lvl === 'important' && c.auto === true, 'karta „Co ma Ci przerywać dzień”: poziom „ważne”, autoodczyt włączony');
  ok(/dzwonek w panelu dostaje zawsze wszystko/i.test(c.txt) && /Błędy i nieodhaczone ostrzeżenia zostają nieprzeczytane/.test(c.txt), 'opis: dzwonek dostaje wszystko, błędy zostają nieprzeczytane');
  ok(c.low && c.low.p === '1' && c.sum && c.sum.p === '2' && c.cyc && c.cyc.p === '3', 'etykiety ważności przy rodzajach (krytyczne / ważne / info)');
  ok(c.low.only === false && c.sum.only === false && c.cyc.only === true && c.hint.only === true, 'poziom „ważne”: tylko info ma dopisek „tylko dzwonek”');
  ok(!c.save, 'bez zmian zapis nieaktywny');
  const setSel = (v) => e.q((v) => { const s = __el.shadowRoot.getElementById('dgNtPhoneLevel'); s.value = v; s.dispatchEvent(new Event('change', { bubbles: true })); }, v);
  await setSel('critical'); await sleep(200); c = await cfg();
  ok(c.lvl === 'critical' && c.sum.only === true && c.cyc.only === true && c.low.only === false, 'poziom „krytyczne”: ważne też tylko w dzwonku, krytyczne nadal na telefon');
  ok(c.save, 'zmiana poziomu aktywuje zapis');
  await setSel('all'); await sleep(200); c = await cfg();
  ok(c.lvl === 'all' && c.onlyN === 0, 'poziom „wszystkie”: żadnego dopisku „tylko dzwonek”');
  await e.q(() => { const a = __el.shadowRoot.getElementById('dgNtAutoRead'); a.checked = false; a.dispatchEvent(new Event('change', { bubbles: true })); }); await sleep(200);
  ok((await cfg()).auto === false, 'przełącznik autoodczytu można wyłączyć');
  await e.q(() => __el.shadowRoot.querySelector('#dgNt [data-act="nt-save"]').click()); await sleep(400);
  const sent = await e.q(() => window.__ntSet[0]);
  ok(sent && sent.phone_level === 'all' && sent.auto_read === false && sent.kinds && sent.sched, 'zapis wysyła phone_level i auto_read razem z resztą ustawień');
  await e.q(() => { window.confirm = () => true; __el.shadowRoot.querySelector('#dgNt [data-act="nt-defaults"]').click(); }); await sleep(300); c = await cfg();
  ok(c.lvl === 'important' && c.auto === true && c.save, '„Domyślne”: poziom „ważne”, autoodczyt włączony, do zapisania');
  ok(e.errs.length === 0, 'konfigurator: brak błędów JS ' + JSON.stringify(e.errs));
  await e.page.context().close();

  // starsza integracja (bez phone_level, auto_read i prio) → panel nie wywala się, pokazuje domyślne
  e = await openCard(b, { admin: true });
  await seed(e, { curve: curve(), report: REPORT(), health: HEALTH });
  await e.q((pay) => { window.__svc = window.__svc || {}; window.__svc['bms_komp_dec.notify_settings_get'] = () => ({ response: JSON.parse(JSON.stringify(pay)) }); }, BASE);
  await openSec(e, 'notify'); await sleep(700); c = await cfg();
  ok(c.has && c.lvl === 'important' && c.auto === true && c.low && c.low.p === '2', 'starsza integracja: domyślnie „ważne” + autoodczyt, brak ważności = „ważne”');
  ok(e.errs.length === 0, 'starsza integracja: brak błędów JS ' + JSON.stringify(e.errs));
  await e.page.context().close();

  // ------------------------------------------------------------ 2) dzwonek
  const now = () => Math.round(Date.now() / 1000);
  const note = (id, level, extra) => Object.assign({ id, ts: now() - 60, kind: 'k' + id, group: 'Inne', title: `Tytuł ${id}`, message: `Treść ${id}`, level, read: false }, extra || {});
  async function bellEnv(autoRead, width) {
    const x = await openCard(b, { mobile: !!width });
    if (width) { await x.page.setViewportSize({ width, height: 800 }); await x.q((w) => { document.getElementById('h').style.width = w + 'px'; }, width); }
    await seed(x, { curve: curve(), proposals: {} });      // bez propozycji planu: licznik dzwonka = same powiadomienia
    await x.q(() => { window.__calls.length = 0; });
    return x;
  }
  const setNotes = (x, notes, autoRead, init) => x.q(([notes, ar, init]) => {
    if (init) { __el._inbInit = false; __el._inbOpen = false; try { localStorage.removeItem('bms_inb_seen'); } catch (e) { /* */ } }   // jak świeżo załadowana karta: istniejące powiadomienia uznaje za „widziane”
    const st = __states['sensor.bms_monitor_status'] || (__states['sensor.bms_monitor_status'] = { entity_id: 'sensor.bms_monitor_status', state: 'ok', attributes: {} });
    st.attributes.inbox = notes; st.attributes.inbox_rejected = {}; st.attributes.auto_skip = {}; if (ar === undefined) delete st.attributes.inbox_auto_read; else st.attributes.inbox_auto_read = ar;
    __el.hass = __mk(); __el._inbSig = null; __el._renderInbox();
  }, [notes, autoRead, !!init]);
  const bell = (x) => x.q(() => { const R = __el.shadowRoot, ov = R.getElementById('inbOv'); const read = [...R.querySelectorAll('#inbOv .inb-card.n-info, #inbOv .inb-card.n-ok, #inbOv .inb-card.n-warn, #inbOv .inb-card.n-error')];
    return { open: !!ov && !ov.hidden, badge: (R.getElementById('bellN') || {}).textContent, badgeHidden: !!(R.getElementById('bellN') || {}).hidden,
      calls: window.__calls.filter(c => c[1] === 'inbox_action').map(c => c[2].action), unread: read.filter(c => c.classList.contains('unread')).length, tags: [...R.querySelectorAll('#inbOv .inb-autotag')].map(t => t.textContent.trim()) }; });

  let x = await bellEnv();
  await setNotes(x, [note(4, 'error'), note(3, 'warn'), note(2, 'ok'), note(1, 'info')], true, true);   // pierwszy odczyt: zapamiętuje „widziane”, okienko się nie otwiera
  let r = await bell(x);
  ok(!r.open && r.badge === '4', `autoodczyt: stare nieprzeczytane (4) nie otwierają okienka, licznik 4 (${r.badge})`);
  await setNotes(x, [note(5, 'info'), note(4, 'error'), note(3, 'warn'), note(2, 'ok'), note(1, 'info')], true);
  r = await bell(x);
  ok(!r.open, 'autoodczyt: nowa INFORMACJA nie wyskakuje sama (czeka pod dzwonkiem)');
  await setNotes(x, [note(6, 'warn'), note(5, 'info'), note(4, 'error'), note(3, 'warn'), note(2, 'ok'), note(1, 'info')], true);
  r = await bell(x);
  ok(r.open, 'autoodczyt: nowe OSTRZEŻENIE wyskakuje samo');
  ok(r.badge === '6' && r.unread === 6, `przed zamknięciem: 6 nieprzeczytanych (${r.badge})`);
  await x.q(() => __el.shadowRoot.querySelector('#inbOv [data-inb="close"]').click()); await sleep(200);
  r = await bell(x);
  ok(r.calls.length === 1 && r.calls[0] === 'read_seen', 'zamknięcie okienka (✕) → usługa inbox_action: read_seen: ' + JSON.stringify(r.calls));
  ok(r.badge === '1', `po zamknięciu licznik = tylko tylko błąd (1), jest ${r.badge}`);
  await x.q(() => __el._el('bell').click()); await sleep(150);
  r = await bell(x);
  ok(r.open && r.unread === 1, `po ponownym otwarciu nieprzeczytane zostały tylko: błąd (${r.unread})`);
  await x.page.context().close();

  // zamknięcie dzwonkiem (przełącznik) i kliknięciem w tło
  x = await bellEnv();
  await setNotes(x, [note(2, 'warn'), note(1, 'info')], true, true);
  await setNotes(x, [note(3, 'info'), note(2, 'warn'), note(1, 'info')], true);
  await x.q(() => __el._el('bell').click()); await sleep(150);
  ok((await bell(x)).open, 'dzwonek otwiera okienko');
  await x.q(() => __el._el('bell').click()); await sleep(200);
  r = await bell(x);
  ok(!r.open && r.calls.includes('read_seen') && r.badge === '1', `zamknięcie dzwonkiem też „ogląda” informacje (licznik ${r.badge})`);
  await x.q(() => window.__calls.length = 0);
  await x.q(() => __el._el('bell').click()); await sleep(150);
  await x.q(() => { const ov = __el.shadowRoot.getElementById('inbOv'); ov.dispatchEvent(new MouseEvent('click', { bubbles: true })); }); await sleep(150);
  r = await bell(x);
  ok(!r.open && r.calls.length === 0, 'zamknięcie tłem, gdy nie ma nieprzeczytanych informacji: bez zbędnego wywołania usługi');
  await x.page.context().close();

  // autoodczyt wyłączony albo starsza integracja: zachowanie jak dotąd
  for (const ar of [false, undefined]) {
    x = await bellEnv();
    await setNotes(x, [note(1, 'info')], ar, true);
    await setNotes(x, [note(2, 'info'), note(1, 'info')], ar);
    r = await bell(x);
    ok(r.open, `autoodczyt ${ar === false ? 'wyłączony' : 'nieznany (starsza integracja)'}: nowa informacja wyskakuje jak dotąd`);
    await x.q(() => __el.shadowRoot.querySelector('#inbOv [data-inb="close"]').click()); await sleep(200);
    r = await bell(x);
    ok(r.calls.length === 0 && r.badge === '2', 'zamknięcie nic nie czyta (licznik 2, bez wywołania usługi)');
    await x.page.context().close();
  }

  // znacznik „odczytane automatycznie” (escapowany), mieści się na telefonie
  x = await bellEnv(null, 360);
  await setNotes(x, [note(3, 'warn', { read: true, auto: 'sytuacja minęła' }), note(2, 'info', { read: true, auto: '<img src=x onerror=window.__pwn=1>' }), note(1, 'info', { read: true })], true);
  await x.q(() => __el._el('bell').click()); await sleep(200);
  r = await bell(x);
  ok(r.tags.length === 2 && /odczytane automatycznie: sytuacja minęła/.test(r.tags[0]), 'przeczytane automatycznie: widać powód: ' + JSON.stringify(r.tags));
  const fit = await x.q(() => { const o = __el.shadowRoot.getElementById('inbOv'), card = o.querySelector('.inb-card').getBoundingClientRect(); return { inside: [...o.querySelectorAll('.inb-autotag')].every(t => { const q = t.getBoundingClientRect(); return q.right <= card.right + 1 && q.left >= card.left - 1; }), imgs: o.querySelectorAll('img').length, pwn: window.__pwn === 1, doc: document.documentElement.scrollWidth }; });
  ok(fit.inside && fit.imgs === 0 && !fit.pwn && fit.doc <= 360, `znacznik mieści się w karcie (360 px), jest escapowany: ${JSON.stringify(fit)}`);
  ok(x.errs.length === 0, 'dzwonek: brak błędów JS ' + JSON.stringify(x.errs));
  await x.page.context().close();
  console.log(fails ? `FAILS ${fails}` : 'OK');
  await b.close();
  process.exit(fails ? 1 : 0);
})();
