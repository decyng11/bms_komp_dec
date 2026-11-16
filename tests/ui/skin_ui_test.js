// Style wyglądu: Klasyczny (domyślny) / Material 3 / Szkło / Matryca / Przestrzeń / Komfort — wybór w Diagnostyce → Wygląd, zapamiętany, działa z jasnym i ciemnym motywem
const { openCard, chromium } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  await e.q(() => __el._setTheme('dark'));
  await e.q(() => { __el.shadowRoot.querySelector('[data-tab="diag"]').click(); });
  await e.page.waitForFunction(() => typeof __el._dgSec_look === 'function', null, { timeout: 8000 });
  await e.q(() => __el.shadowRoot.querySelector('[data-tab="main"]').click());
  const cs = (v) => e.q((v) => getComputedStyle(__el).getPropertyValue(v).trim(), v);
  ok(await e.q(() => !__el.hasAttribute('data-skin')), 'domyślnie styl klasyczny (brak atrybutu)');
  const bgClassic = await cs('--card');
  const sec = await e.q(() => { __el._dgState && 0; return __el._dgSec_look ? __el._dgSec_look() : ''; });
  ok(['classic', 'm3', 'glass', 'matrix', 'space', 'comfort'].every(k => new RegExp('data-skin="' + k + '"').test(sec)), 'Ustawienia → Wygląd: sześć stylów do wyboru');
  ok(/Szkło/.test(sec) && /Matryca/.test(sec) && /Przestrzeń/.test(sec) && /Komfort/.test(sec), 'Ustawienia → Wygląd: własne nazwy nowych stylów');
  ok(/class="dg-skin on" data-act="skin" data-skin="classic"/.test(sec), 'aktywny styl oznaczony');
  await e.q(() => __el._setSkin('m3'));
  ok(await e.q(() => __el.getAttribute('data-skin') === 'm3'), 'wybór Material 3 ustawia atrybut');
  ok(await e.q(() => localStorage.getItem('bms_panel_skin') === 'm3'), 'wybór zapamiętany w przeglądarce');
  const bgM3 = await cs('--card');
  ok(bgM3 && bgM3 !== bgClassic, 'zmienne kolorów się zmieniły: ' + bgClassic + ' → ' + bgM3);
  // jasny i ciemny motyw mają różne palety M3
  await e.q(() => __el._setTheme('light'));
  const light = await cs('--bg');
  await e.q(() => __el._setTheme('dark'));
  const dark = await cs('--bg');
  ok(light === '#f4fbf8' && dark === '#0f1513', 'M3: jasny ' + light + ', ciemny ' + dark);
  // aktywna zakładka ma wskaźnik-pigułkę, nie pełne tło
  await e.page.waitForTimeout(400);
  const nav = await e.q(() => { const t = __el.shadowRoot.querySelector('.tabs.bottom .tab.active'); const i = t.querySelector('.ti'); return { tab: getComputedStyle(t).backgroundColor, ti: getComputedStyle(i).backgroundColor }; });
  ok(/rgba\(0, 0, 0, 0\)|transparent/.test(nav.tab) && !/rgba\(0, 0, 0, 0\)/.test(nav.ti), 'M3: pigułka za ikoną aktywnej zakładki: ' + JSON.stringify(nav));
  // przeładowanie: styl wraca ze storage
  const e2 = await openCard(b, {});
  await e2.q(() => { localStorage.setItem('bms_panel_skin', 'm3'); __el._applySkin(); });
  ok(await e2.q(() => __el.getAttribute('data-skin') === 'm3'), 'odczyt zapisanego stylu');
  // wybór nieznanej wartości jest ignorowany; powrót do klasycznego
  await e.q(() => __el._setSkin('nieznany'));
  ok(await e.q(() => __el.getAttribute('data-skin') === 'm3'), 'nieznany styl ignorowany');
  await e.q(() => __el._setSkin('classic'));
  ok(await e.q(() => !__el.hasAttribute('data-skin')), 'powrót do klasycznego usuwa atrybut');
  ok((await cs('--card')) === bgClassic, 'kolory klasyczne przywrócone');
  // układ Material 3 na ekranie głównym: karta baterii, pigułki przepływu, kafelki, pasek planu 24 h
  await e.q(() => {
    const rows = []; const d = new Date(); const day = (o) => { const z = new Date(d.getTime() + o * 864e5); return z.getFullYear() + '-' + String(z.getMonth() + 1).padStart(2, '0') + '-' + String(z.getDate()).padStart(2, '0'); };   // data lokalna
    const pat = ['idle','idle','idle','idle','idle','idle','home','home','pv','pv','pv','pv','pv','pv','grid','home','home','home','sell','sell','home','home','grid','grid'];
    for (let o = 0; o < 3; o++) for (let h = 0; h < 24; h++) rows.push({ day: day(o), h, action: pat[h], label: pat[h], soc: 50 });
    const t0 = new Date().toISOString(); __states['sensor.bms_plan_view'] = { state: 'pv', attributes: { table: rows }, last_updated: t0, last_changed: t0 };
    __el._setSkin('m3'); __el.hass = __mk();
  });
  await e.page.waitForTimeout(700);
  const m3 = await e.q(() => { const r = __el.shadowRoot; const q = (s) => r.querySelector(s);
    return { hero: !!q('.m3-hero'), soc: (q('.m3-big') || {}).textContent, marks: r.querySelectorAll('.m3-lp .m').length, pills: r.querySelectorAll('.m3-flow svg rect').length,
      kpis: r.querySelectorAll('.m3-kpi').length, strip: r.querySelectorAll('.m3-strip i').length, oldSvg: !!q('#nodesBox .nf-svg') }; });
  ok(m3.hero && /^\d+%$/.test(m3.soc || '') , 'M3: karta baterii z SOC: ' + m3.soc);
  ok(m3.marks >= 1, 'M3: znaczniki rezerwy / celu na pasku baterii: ' + m3.marks);
  ok(m3.pills === 4 && m3.kpis === 3, 'M3: cztery pigułki przepływu i trzy kafelki');
  ok(m3.strip === 24, 'M3: pasek planu ma 24 godziny: ' + m3.strip);
  ok(!m3.oldSvg, 'M3: stary schemat kółek ukryty');
  await e.q(() => __el._setSkin('classic'));
  await e.page.waitForTimeout(500);
  const cl = await e.q(() => ({ old: !!__el.shadowRoot.querySelector('#nodesBox .nf-svg'), m3: !!__el.shadowRoot.querySelector('.m3-hero') }));
  ok(cl.old && !cl.m3, 'powrót do klasycznego przywraca schemat kółek');

  // nowe style z własnym ekranem głównym: Szkło / Matryca / Przestrzeń / Komfort
  const palettes = {};
  for (const sk of ['glass', 'matrix', 'space', 'comfort']) {
    await e.q((sk) => { __el._setTheme('dark', true); __el._setSkin(sk); __el.hass = __mk(); }, sk);
    await e.page.waitForTimeout(700);
    ok(await e.q((sk) => __el.getAttribute('data-skin') === sk && localStorage.getItem('bms_panel_skin') === sk, sk), sk + ': atrybut i zapis w przeglądarce');
    const dk = await cs('--bg'), card = await cs('--card');
    await e.q(() => __el._setTheme('light', true));
    const lt = await cs('--bg');
    await e.q(() => __el._setTheme('dark', true));
    ok(dk && lt && dk !== lt, sk + ': inne tło w jasnym (' + lt + ') i ciemnym (' + dk + ') motywie');
    ok(card && card !== bgClassic && card !== bgM3, sk + ': własna paleta kart: ' + card);
    palettes[sk] = card + '|' + dk;
    const h = await e.q(() => { const r = __el.shadowRoot; const q = (s) => r.querySelector(s);
      return { hero: !!q('.sk-hero svg.sk-ring'), flow: !!q('.sk-flow svg'), flowTxt: (q('.sk-flow svg') || { textContent: '' }).textContent,
        kpis: r.querySelectorAll('.sk-kpi').length, bars: r.querySelectorAll('.sk-strip i').length, dotsStrip: !!q('.sk-strip-card svg.sk-dots'),
        kpiDots: r.querySelectorAll('.sk-kpi .v svg.sk-dots').length, bigDots: !!q('.sk-ring rect') , oldSvg: !!q('#nodesBox .nf-svg'), m3: !!q('.m3-hero'),
        nodesBg: getComputedStyle(q('.chart-card.nodes-card')).backgroundColor }; });
    ok(h.hero && h.flow && h.kpis === 3, sk + ': karta baterii z pierścieniem, schemat przepływu i trzy kafelki');
    ok(/3,20 kW/.test(h.flowTxt) && /1,10 kW/.test(h.flowTxt) && /800 W/.test(h.flowTxt), sk + ': schemat pokazuje moce PV / dom / sieć: ' + h.flowTxt.replace(/\s+/g, ' ').slice(0, 80));
    if (sk === 'matrix') ok(h.dotsStrip && h.kpiDots === 3 && h.bigDots, 'matrix: pasek planu, wartości kafelków i pierścień z kwadratowych pikseli');
    else ok(h.bars === 24, sk + ': pasek planu ma 24 godziny: ' + h.bars);
    ok(!h.oldSvg && !h.m3, sk + ': stary schemat kółek i układ Material 3 ukryte');
    ok(/rgba\(0, 0, 0, 0\)|transparent/.test(h.nodesBg), sk + ': zewnętrzna karta schematu przezroczysta (bez podwójnej ramki): ' + h.nodesBg);
  }
  ok(new Set(Object.values(palettes)).size === 4, 'cztery nowe style mają różne palety');
  // Przestrzeń: na szerokim ekranie pionowy pasek zakładek, na wąskim zwykły dolny
  await e.q(() => __el._setSkin('space'));
  await e.page.waitForTimeout(300);
  const wide = await e.q(() => getComputedStyle(__el.shadowRoot.querySelector('.tabs.bottom')).flexDirection);
  await e.page.setViewportSize({ width: 390, height: 844 }); await e.page.waitForTimeout(300);
  const narrow = await e.q(() => getComputedStyle(__el.shadowRoot.querySelector('.tabs.bottom')).flexDirection);
  await e.page.setViewportSize({ width: 1100, height: 900 });
  ok(wide === 'column' && narrow === 'row', 'Przestrzeń: pasek zakładek pionowy na szerokim (' + wide + ') i poziomy na wąskim (' + narrow + ') ekranie');
  // klik zakładek działa we wszystkich stylach (bez błędów w konsoli)
  for (const sk of ['glass', 'matrix', 'space', 'comfort']) {
    await e.q((sk) => { __el._setSkin(sk); ['charts', 'ems', 'main'].forEach(t => __el.shadowRoot.querySelector('[data-tab="' + t + '"]').click()); }, sk);
    await e.page.waitForTimeout(250);
  }
  ok(e.errs.length === 0, 'brak błędów w konsoli: ' + e.errs.slice(0, 3).join(' | '));
  await e.q(() => __el._setSkin('classic'));
  await e.page.waitForTimeout(500);
  const back = await e.q(() => ({ old: !!__el.shadowRoot.querySelector('#nodesBox .nf-svg'), sk: !!__el.shadowRoot.querySelector('.sk-home') }));
  ok(back.old && !back.sk, 'powrót do klasycznego przywraca schemat kółek po nowych stylach');
  // kliknięcie w karcie w Diagnostyce przełącza styl
  await b.close();
  console.log(fails ? `FAILS ${fails}` : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
