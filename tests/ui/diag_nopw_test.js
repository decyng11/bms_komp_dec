// Ustawienia (Diagnostyka): bez hasła (wyłączone na prośbę właściciela) i z widocznymi wszystkimi sekcjami.
// - administrator wchodzi od razu, bez bramki hasła i bez paska „tryb instalatora”; nie-administrator nadal jest odsyłany;
// - na komputerze wszystkie 13 sekcji jest widocznych (pasek się zawija, wcześniej 5 ostatnich było poza widokiem bez paska przewijania);
// - na telefonie pasek przewija się palcem, ma zanik jako podpowiedź, a wybrana sekcja z końca listy nie znika po przerysowaniu;
// - bramka z hasłem nadal działa po włączeniu (window.__BMS_DG_PW), na wypadek powrotu do hasła.
const { openCard, chromium } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const openDiag = async (e) => {
  await e.q(() => __el.shadowRoot.querySelector('[data-tab="diag"]').click());
  await e.page.waitForFunction(() => !!__el.shadowRoot.getElementById('dgBody') || !!__el.shadowRoot.getElementById('dgPw') || /administrator/i.test(__el.shadowRoot.getElementById('dgHost') ? __el.shadowRoot.getElementById('dgHost').textContent : ''), null, { timeout: 8000 });
  await sleep(300);
};
const nav = (e) => e.q(() => {
  const n = __el.shadowRoot.querySelector('.dg-nav'), nr = n.getBoundingClientRect();
  const pills = [...n.querySelectorAll('.dg-pill')].map(p => { const r = p.getBoundingClientRect(); return { t: p.textContent.trim(), sec: p.dataset.sec, on: p.classList.contains('on'), vis: r.width > 0 && r.left >= nr.left - 1 && r.right <= nr.right + 1 }; });
  return { n: pills.length, hidden: pills.filter(p => !p.vis).map(p => p.t), cw: n.clientWidth, sw: n.scrollWidth, sl: n.scrollLeft, more: n.classList.contains('more-r'), on: pills.find(p => p.on), onVis: (pills.find(p => p.on) || {}).vis };
});
(async () => {
  const b = await chromium.launch();

  // ---- komputer, bez hasła
  for (const [w, sk] of [[1060, 'classic'], [900, 'm3'], [720, 'comfort']]) {
    const e = await openCard(b, { admin: true, mobile: false });
    await e.page.setViewportSize({ width: w, height: 900 });
    await e.q(([w, sk]) => { document.getElementById('h').style.width = w + 'px'; __el._setSkin(sk); }, [w, sk]);
    await openDiag(e);
    const g = await e.q(() => { const s = __el.shadowRoot; return { pw: !!s.getElementById('dgPw'), body: !!s.getElementById('dgBody'), bar: !!s.querySelector('.dg-bar') && /instalatora aktywny/.test(s.querySelector('.dg-bar').textContent), unlockBtn: !!s.querySelector('[data-act=unlock]') }; });
    ok(!g.pw && !g.unlockBtn && g.body, `${sk} ${w}px: administrator wchodzi do Ustawień bez hasła`);
    ok(!g.bar, `${sk} ${w}px: brak paska „tryb instalatora aktywny / wygasa za”`);
    const n = await nav(e);
    ok(n.n === 13 && n.hidden.length === 0 && n.sw <= n.cw + 1, `${sk} ${w}px: wszystkie ${n.n} sekcje widoczne bez przewijania (ukryte: ${n.hidden.join(', ') || 'brak'})`);
    // ostatnia sekcja jest klikalna myszą i otwiera się
    await e.q(() => __el.shadowRoot.querySelector('[data-act="sec"][data-sec="adv"]').click()); await sleep(400);
    ok(await e.q(() => !!__el.shadowRoot.querySelector('[data-act=clear-load-hist]') || /Zaawansowane/i.test(__el.shadowRoot.querySelector('.dg-pill.on').textContent)), `${sk} ${w}px: ostatnia sekcja „Zaawansowane” otwiera się z paska`);
    await e.page.context().close();
  }

  // ---- nie-administrator: nadal odesłany
  {
    const e = await openCard(b, { admin: false, mobile: false });
    await e.q(() => { __el.shadowRoot.getElementById('tabDiag').style.display = ''; __el.shadowRoot.querySelector('[data-tab="diag"]').click(); }); await sleep(500);
    ok(await e.q(() => { const s = __el.shadowRoot; return !s.getElementById('dgBody') && !s.getElementById('dgPw') && /administrator/i.test(s.getElementById('dgHost') ? s.getElementById('dgHost').textContent : ''); }), 'nie-administrator: bez dostępu do Ustawień (komunikat o administratorach)');
    await e.page.context().close();
  }

  // ---- telefon: przewijany rząd z zanikiem, wybrana sekcja zostaje w widoku
  {
    const e = await openCard(b, { admin: true, mobile: true });
    await e.page.setViewportSize({ width: 390, height: 800 });
    await e.q(() => { document.getElementById('h').style.width = '390px'; });
    await openDiag(e);
    let n = await nav(e);
    ok(n.sw > n.cw + 1 && n.more, `telefon: pasek sekcji przewijany (${n.sw} > ${n.cw}), zanik przy prawej krawędzi jako podpowiedź`);
    await e.q(() => { const n = __el.shadowRoot.querySelector('.dg-nav'); n.scrollLeft = n.scrollWidth; n.dispatchEvent(new Event('scroll')); }); await sleep(150);
    n = await nav(e);
    ok(!n.more, 'telefon: po przewinięciu do końca zanik znika');
    await e.q(() => __el.shadowRoot.querySelector('[data-act="sec"][data-sec="adv"]').click()); await sleep(450);
    n = await nav(e);
    ok(n.on && n.on.sec === 'adv' && n.onVis, `telefon: po wyborze ostatniej sekcji pasek jest przewinięty tak, że ją widać (scrollLeft ${Math.round(n.sl)})`);
    await e.page.context().close();
  }

  // ---- bramka z hasłem po włączeniu (powrót do hasła)
  {
    const e = await openCard(b, { admin: true, mobile: false });
    await e.q(() => { window.__BMS_DG_PW = true; });
    await openDiag(e);
    ok(await e.q(() => !!__el.shadowRoot.getElementById('dgPw') && !__el.shadowRoot.getElementById('dgBody')), 'po włączeniu bramki: pole hasła, bez treści Ustawień');
    await e.q(() => { const s = __el.shadowRoot; s.getElementById('dgPw').value = 'zle'; s.querySelector('[data-act=unlock]').click(); }); await sleep(200);
    ok(await e.q(() => !!__el.shadowRoot.getElementById('dgPw') && /Nieprawidłowe/.test(__el.shadowRoot.getElementById('dgGateMsg').textContent)), 'po włączeniu bramki: złe hasło odrzucone');
    await e.page.context().close();
  }

  console.log(fails ? `FAILS ${fails}` : 'OK');
  await b.close();
  process.exit(fails ? 1 : 0);
})();
