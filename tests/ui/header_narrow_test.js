// Nagłówek panelu (logo, data, przyciski 🎨 / 🔔 / motyw) mieści się w jednym wierszu i w oknie karty na wąskich telefonach
// (320, 360, 375, 390 px) we wszystkich sześciu stylach — wcześniej przyciski wystawały poza ekran (np. Komfort miał logo 44 px).
const { openCard, chromium } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const SK = ['classic', 'm3', 'glass', 'matrix', 'space', 'comfort'];
(async () => {
  const b = await chromium.launch();
  for (const sk of SK) for (const w of [320, 360, 375, 390]) {
    const e = await openCard(b, { admin: false, mobile: true });
    await e.page.setViewportSize({ width: w, height: 760 });
    await e.q(([w, sk]) => { document.getElementById('h').style.width = w + 'px'; __el._setSkin(sk); }, [w, sk]); await sleep(450);
    const r = await e.q(() => {
      const sh = __el.shadowRoot, app = sh.querySelector('.app').getBoundingClientRect(), L = sh.querySelector('.header > div').getBoundingClientRect(), R = sh.querySelector('.hdr-r').getBoundingClientRect();
      const btn = [...sh.querySelectorAll('.hdr-r button')].map(n => n.getBoundingClientRect()), last = btn[btn.length - 1];
      return { appR: app.right, right: R.right, rightBtn: last.right, leftEdge: R.left - L.right, oneRow: R.top < L.bottom - 2, doc: document.documentElement.scrollWidth, n: btn.length };
    });
    ok(r.n === 4 && r.right <= r.appR + 0.5 && r.rightBtn <= r.appR + 0.5 && r.doc <= w, `${sk} ${w}px: przyciski nagłówka mieszczą się w oknie karty (prawa krawędź ${Math.round(r.right)} ≤ ${Math.round(r.appR)})`);
    ok(r.leftEdge >= 0 && r.oneRow, `${sk} ${w}px: logo i przyciski w jednym wierszu, bez nakładania (odstęp ${Math.round(r.leftEdge)} px)`);
    await e.page.context().close();
  }
  console.log(fails ? `FAILS ${fails}` : 'OK');
  await b.close();
  process.exit(fails ? 1 : 0);
})();
