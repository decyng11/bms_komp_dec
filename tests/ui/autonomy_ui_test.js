// „Na ile godzin starczy baterii” na ekranie głównym
const { openCard, chromium } = require('./ui_env');
const { seed, curve, sr } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
(async () => {
  const b = await chromium.launch();
  const e = await openCard(b, {});
  await seed(e, { curve: curve() });
  const set = (au) => e.q((au) => { const st = __states['sensor.bms_reserve_soc']; if (au === null) delete st.attributes.autonomy; else st.attributes.autonomy = au; __el.hass = __mk(); }, au);
  ok(await e.q(() => !!__el.shadowRoot.querySelector('[data-tile="main-active"] #autonomyBox')), 'pole jest w kafelku „Aktywne funkcje” (bez nowego kafelka)');
  await set(null); await sleep(200);
  ok(await e.q(() => __el.shadowRoot.getElementById('autonomyBox').style.display === 'none'), 'brak danych → pole ukryte');
  await set({ hours: 14.2, text: '14 h', capped: false, usable_kwh: 6.8, load_w: 480, floor: 20, soc: 80 }); await sleep(200);
  let t = await sr(e, '#autonomyBox');
  ok(/Bateria starczy na ok\. 14 h/.test(t) && /dom bierze 480 W/.test(t) && /do progu 20%/.test(t) && /bez PV i sieci/.test(t), 'tekst: czas, pobór, próg: ' + t);
  ok(await e.q(() => __el.shadowRoot.querySelector('#autonomyBox b').style.color) === 'var(--green)', 'dużo czasu → zielony');
  ok(/6,8 kWh/.test(await e.q(() => __el.shadowRoot.getElementById('autonomyBox').title)), 'podpowiedź z użyteczną energią');
  await set({ hours: 4.0, text: '4 h', usable_kwh: 2, load_w: 480, floor: 20 }); await sleep(150);
  ok(await e.q(() => __el.shadowRoot.querySelector('#autonomyBox b').style.color) === 'var(--orange)', '4 h → pomarańczowy');
  await set({ hours: 1.0, text: '1 h', usable_kwh: 1, load_w: 1000, floor: 20 }); await sleep(150);
  ok(await e.q(() => __el.shadowRoot.querySelector('#autonomyBox b').style.color) === 'var(--red)', '1 h → czerwony');
  await set({ hours: 72, text: 'ponad 3 doby', capped: true, usable_kwh: 9, load_w: 50, floor: 10 }); await sleep(150);
  ok(/ponad 3 doby/.test(await sr(e, '#autonomyBox')), 'ponad 3 doby');
  // odporność na śmieci
  await set({ hours: 'x', text: '<img src=x onerror=window.__pwn4=1>' }); await sleep(150);
  ok(await e.q(() => __el.shadowRoot.getElementById('autonomyBox').style.display === 'none'), 'zła liczba godzin → pole ukryte');
  await set({ hours: 5, text: '<img src=x onerror=window.__pwn4=1>', load_w: 'abc', floor: null, usable_kwh: null }); await sleep(150);
  ok(await e.q(() => !window.__pwn4 && !__el.shadowRoot.querySelector('#autonomyBox img')), 'treść nie jest interpretowana jako HTML');
  ok(/dom bierze \? W/.test(await sr(e, '#autonomyBox')), 'zła liczba mocy → „?” zamiast NaN');
  await set('śmieć'); await sleep(150);
  ok(await e.q(() => __el.shadowRoot.getElementById('autonomyBox').style.display === 'none'), 'atrybut nie-obiekt → ukryte');
  ok(e.errs.length === 0, 'brak błędów JS ' + JSON.stringify(e.errs));
  await b.close();
  console.log(fails ? 'FAILS ' + fails : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
