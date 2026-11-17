// Losowy test układu panelu: seria przypadkowych przeniesień, przesunięć, ukryć, zmian kolejności i przywróceń (te same ziarna
// dają te same ciągi operacji). Po każdej operacji sprawdza niezmienniki: każdy kafelek jest dokładnie raz, DOM zgadza się
// z zapisaną kolejnością, ukryte mają data-tile-off, ponowne zastosowanie układu nic nie zmienia, a układ domyślny nie zostawia zapisu.
const { openCard, chromium } = require('./ui_env');
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
(async () => {
  const b = await chromium.launch();
  const seeds = [1, 2, 3], N = 110;
  let bad = 0;
  for (const seed of seeds) {
    const e = await openCard(b, { admin: false });
    await e.q(() => { try { ['bms_panel_layout', 'bms_panel_prefs_meta'].forEach(k => localStorage.removeItem(k)); } catch (x) {} });
    // wejście na wszystkie zakładki, żeby kafelki Zysku i logu powstały
    for (const t of ['charts', 'ems', 'log', 'main']) { await e.q((t) => __el.shadowRoot.querySelector(`.tab[data-tab="${t}"]`).click(), t); await sleep(500); }
    const res = await e.q(async ([seed, N]) => {
      let a = seed >>> 0; const rnd = () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
      const pick = (arr) => arr[Math.floor(rnd() * arr.length)];
      const G = __el._layoutGroups(), movable = G.filter(g => !g.fixed), tiles = [].concat(...G.map(g => g.tiles.map(t => t[0])));
      const sh = __el.shadowRoot, errs = [];
      const check = (op) => {
        const L = __el._layoutState(), hid = L.hidden;
        for (const g of movable) {
          const cont = g.tab === 'log' ? sh.querySelector(`[data-tab-content="log"] #logTabBody`) : sh.querySelector(`[data-tab-content="${g.tab}"]`);
          const dom = [...cont.children].filter(n => n.dataset && n.dataset.tile).map(n => n.dataset.tile);
          const want = L.orders[g.tab].filter(id => sh.querySelector(`[data-tile="${id}"]`));
          if (dom.join() !== want.join()) errs.push(`${op}: kolejność DOM ${g.tab}: [${dom}] ≠ [${want}]`);
        }
        for (const id of tiles) {
          const n = sh.querySelectorAll(`[data-tile="${id}"]`).length;
          if (n > 1) errs.push(`${op}: ${id} występuje ${n}×`);
          const el = sh.querySelector(`[data-tile="${id}"]`);
          if (el && el.hasAttribute('data-tile-off') !== hid.has(id)) errs.push(`${op}: ${id} data-tile-off=${el.hasAttribute('data-tile-off')} a ukryty=${hid.has(id)}`);
        }
        // każdy kafelek (poza pogodą) jest dokładnie na jednej liście
        const all = [].concat(...movable.map(g => L.orders[g.tab])), uniq = new Set(all);
        if (all.length !== uniq.size) errs.push(`${op}: duplikat na listach: ${all.filter((x, i) => all.indexOf(x) !== i)}`);
        const exp = movable.reduce((s, g) => s + g.tiles.length, 0);
        if (uniq.size !== exp) errs.push(`${op}: liczba kafelków ${uniq.size} ≠ ${exp}`);
        // zapis → ponowne wczytanie daje to samo
        const before = JSON.stringify(L.orders), hb = JSON.stringify([...hid].sort());
        __el._applyLayout();
        const L2 = __el._layoutState();
        if (JSON.stringify(L2.orders) !== before || JSON.stringify([...L2.hidden].sort()) !== hb) errs.push(`${op}: stan po ponownym zastosowaniu się zmienił`);
        // lista zapisana ≠ domyślna, gdy niczego nie zmieniono
        const raw = localStorage.getItem('bms_panel_layout');
        const isDef = movable.every(g => L.orders[g.tab].join() === g.tiles.map(t => t[0]).join()) && !hid.size;
        if (isDef && raw && raw !== 'null') { try { const o = JSON.parse(raw); if (Object.keys(o.order || {}).length || (o.hidden || []).length) errs.push(`${op}: układ domyślny, a zapis niepusty: ${raw.slice(0, 80)}`); } catch (x) {} }
      };
      for (let i = 0; i < N; i++) {
        const r = rnd(), id = pick(tiles), g = pick(movable);
        let op;
        if (r < 0.40) { op = `moveTo(${id}→${g.tab})`; __el._layoutMoveTo(id, g.tab); }
        else if (r < 0.55) { const cur = __el._layoutState().orders[g.tab]; if (cur.length) { const x = pick(cur), d = rnd() < .5 ? -1 : 1; op = `move(${g.tab},${x},${d})`; __el._layoutMove(g.tab, x, d); } else op = 'noop'; }
        else if (r < 0.72) { op = `toggle(${id})`; __el._layoutToggle(id); }
        else if (r < 0.82) { const cur = __el._layoutState().orders[g.tab].slice().sort(() => rnd() - .5); op = `setOrder(${g.tab},${cur})`; __el._layoutSetOrder(g.tab, cur); }
        else if (r < 0.92) { op = `reset(${g.tab})`; __el._layoutReset(g.tab); }
        else if (r < 0.94) { op = 'resetAll'; __el._layoutReset(); }
        else { const t = pick(['main', 'charts', 'ems', 'log']); op = `tab(${t})`; sh.querySelector(`.tab[data-tab="${t}"]`).click(); await new Promise(r => setTimeout(r, 120)); }
        check(`#${i} ${op}`);
        if (errs.length > 3) break;
      }
      return errs.slice(0, 6);
    }, [seed, N]);
    console.log(res.length || e.errs.length ? 'FAIL' : 'ok  ', `ziarno ${seed}: ${N} losowych operacji na układzie` + (res.length ? ' · ' + res.join(' | ') : '') + (e.errs.length ? ' · błędy konsoli: ' + e.errs.slice(0, 2).join(' | ') : ''));
    if (res.length || e.errs.length) bad++;
    await e.page.context().close();
  }
  console.log(bad ? `FAILS ${bad}` : 'OK');
  await b.close();
  process.exit(bad ? 1 : 0);
})();
