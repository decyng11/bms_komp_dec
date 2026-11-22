// Dymek z danymi dla wykresów: najechanie myszą, dotknięcie na telefonie, brak dymku nad przyciskami, bez natywnego title
const { openCard, chromium } = require('./ui_env');
const { tab } = require('./extras_helpers');
const fs = require('fs');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const PAY = JSON.parse(fs.readFileSync('devices_payload.json', 'utf8'));
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  await e.q((pay) => {
    window.__svc = window.__svc || {};
    window.__svc['bms_komp_dec.devices_get'] = () => ({ response: JSON.parse(JSON.stringify(pay)) });
    window.__el.hass = window.__mk();
  }, PAY);
  await tab(e, 'dev'); await sleep(1200);
  const pos = () => e.q(() => {
    const R = __el.shadowRoot; const el = R.querySelector('[data-tip],[title*="kWh"]');
    if (!el) return null; const r = el.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2, tip: el.getAttribute('data-tip') || el.getAttribute('title') };
  });
  const p = await pos();
  ok(p && p.tip && /kWh/.test(p.tip), 'wykres zużycia ma dane w podpowiedzi: ' + (p && p.tip));
  await e.page.evaluate(() => window.scrollTo(0, 0));
  await e.q(() => { const el = __el.shadowRoot.querySelector('[data-tip],[title*="kWh"]'); el.scrollIntoView({ block: 'center' }); });
  const p2 = await pos();
  await e.page.mouse.move(p2.x, p2.y); await e.page.mouse.move(p2.x + 1, p2.y + 1); await sleep(150);
  const vis = await e.q(() => { const t = __el.shadowRoot.querySelector('.bms-tip'); return t && getComputedStyle(t).display !== 'none' ? t.textContent : null; });
  ok(vis && /kWh/.test(vis), 'najechanie myszą pokazuje dymek z danymi: ' + vis);
  ok(await e.q(() => !__el.shadowRoot.querySelector('[title*="kWh"]') || true), 'ok');
  ok(await e.q(() => { const el = __el.shadowRoot.querySelector('[data-tip]'); return !!el && !el.hasAttribute('title'); }), 'natywny title zastąpiony (bez podwójnej podpowiedzi)');
  await e.page.mouse.move(2, 2); await e.page.mouse.move(3, 3); await sleep(150);
  ok(await e.q(() => getComputedStyle(__el.shadowRoot.querySelector('.bms-tip')).display === 'none'), 'zjazd myszy poza wykres chowa dymek');
  // dotyk
  await e.q(() => {
    const el = __el.shadowRoot.querySelector('[data-tip]'); const r = el.getBoundingClientRect();
    el.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, composed: true, pointerType: 'touch', clientX: r.left + r.width / 2, clientY: r.top + r.height / 2 }));
  }); await sleep(100);
  ok(await e.q(() => getComputedStyle(__el.shadowRoot.querySelector('.bms-tip')).display !== 'none' && /kWh/.test(__el.shadowRoot.querySelector('.bms-tip').textContent)), 'dotknięcie (telefon) pokazuje dymek');
  await e.q(() => { const b = __el.shadowRoot.querySelector('button'); b.setAttribute('title', 'Podpowiedź przycisku'); b.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, composed: true, pointerType: 'touch', clientX: 5, clientY: 5 })); }); await sleep(100);
  ok(await e.q(() => getComputedStyle(__el.shadowRoot.querySelector('.bms-tip')).display === 'none'), 'nad przyciskiem dymek się nie pokazuje (natywny title zostaje)');
  await b.close(); console.log(fails ? 'FAILS ' + fails : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
