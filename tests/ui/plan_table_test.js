// Tabela „Plan godzina po godzinie”: na telefonie wszystkie kolumny widoczne bez przewijania w bok (dwa wiersze na godzinę), na szerokim ekranie bez zmian; nad tabelą opis planu
const { openCard, chromium } = require('./ui_env');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const seed = () => {
  const d0 = new Date(); d0.setMinutes(0, 0, 0);
  const dk = (d) => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  const rows = []; let soc = 52;
  for (let i = 0; i < 30; i++) {
    const d = new Date(d0.getTime() + i * 3600e3), h = d.getHours();
    const act = i < 3 ? ['pv', 'Ładuj z PV'] : i < 8 ? ['home', 'Bateria zasila dom'] : i < 11 ? ['grid', 'Ładuj z sieci'] : i === 12 ? ['sell', 'Sprzedaj z baterii'] : ['idle', 'Bez zmian'];
    soc = Math.max(20, Math.min(100, soc + (act[0] === 'pv' ? 4 : act[0] === 'grid' ? 5 : act[0] === 'home' ? -2.5 : act[0] === 'sell' ? -6 : 0)));
    rows.push({ t: d.toISOString(), h, day: dk(d), action: act[0], label: act[1], peak: h >= 15 && h <= 21, buy: 1.29, sell: 0.96, pv: 2.6, load: 0.8, soc, floor: 20, import_kwh: act[0] === 'grid' ? 3 : 0, export_kwh: 0, cost: act[0] === 'grid' ? -1234.56 : 0 });
  }
  const t0 = new Date().toISOString();
  __states['sensor.bms_plan_view'] = { state: 'pv', attributes: { table: rows, table_totals: { import_kwh: 9, export_kwh: 0, cost: -0.4 }, generated_at: t0 }, last_updated: t0, last_changed: t0 };
  __el.hass = __mk(); __el.shadowRoot.querySelector('.tab[data-tab="charts"]').click();
};
(async () => {
  const b = await chromium.launch();
  // ---- telefon
  const m = await openCard(b, { mobile: true, admin: true });
  await m.q(seed); await sleep(1200);
  const g = await m.q(() => {
    const w = __el.shadowRoot.querySelector('.px-tbl-wrap.px-plan'), wr = w.getBoundingClientRect();
    const row = [...w.querySelectorAll('tbody tr')].find(r => !r.classList.contains('day') && !r.classList.contains('tot'));
    const cells = [...row.children].map(td => { const r = td.getBoundingClientRect(); return { l: td.dataset.l || '', t: td.textContent.trim(), in: r.width > 0 && r.left >= wr.left - 0.5 && r.right <= wr.right + 0.5, over: td.scrollWidth > td.clientWidth + 1 }; });
    return { sw: w.scrollWidth, cw: w.clientWidth, disp: getComputedStyle(row).display, head: getComputedStyle(w.querySelector('thead')).display, cells, rows: w.querySelectorAll('tbody tr').length };
  });
  ok(g.sw <= g.cw, `telefon: brak przewijania w bok (scrollWidth ${g.sw} ≤ ${g.cw})`);
  ok(g.cells.length === 8 && g.cells.every(c => c.in), 'telefon: wszystkie 8 komórek wiersza mieści się w tabeli: ' + JSON.stringify(g.cells.filter(c => !c.in)));
  ok(g.cells.every(c => !c.over), 'telefon: żadna wartość nie jest ucięta: ' + JSON.stringify(g.cells.filter(c => c.over)));
  ok(g.disp === 'grid' && g.head === 'none', 'telefon: układ dwuwierszowy, nagłówek zastąpiony etykietami w komórkach');
  ok(['Kup', 'Sprz', 'PV', 'Dom', 'SOC'].every(l => g.cells.some(c => c.l === l)) && /zł/.test(g.cells[7].t), 'telefon: etykiety Kup / Sprz / PV / Dom / SOC i koszt w zł');
  const big = await m.q(() => { const t = [...__el.shadowRoot.querySelectorAll('.px-plan td')].find(td => /1\s?234,56/.test(td.textContent)); if (!t) return null; return { over: t.scrollWidth > t.clientWidth + 1, in: t.getBoundingClientRect().right <= __el.shadowRoot.querySelector('.px-plan').getBoundingClientRect().right + 0.5 }; });
  ok(big && !big.over && big.in, 'telefon: duża kwota kosztu (−1 234,56 zł) mieści się: ' + JSON.stringify(big));
  ok(await m.q(() => { const t = __el.shadowRoot.querySelector('.px-plan tr.tot'); return !!t && getComputedStyle(t).display === 'flex' && /pobór/.test(t.textContent) && /Razem/.test(t.textContent); }), 'telefon: wiersz „Razem” z poborem i oddaniem widoczny');
  ok(await m.q(() => { const r = __el.shadowRoot.querySelector('.px-plan tr.peak td:first-child'); return !!r && /inset 3px/.test(getComputedStyle(r).boxShadow) || !!r && getComputedStyle(r).boxShadow !== 'none'; }), 'telefon: pomarańczowy znacznik godzin szczytu zachowany');
  const sum = await m.q(() => { const s = __el.shadowRoot.querySelector('#exTblBox .ps'); return s ? s.textContent.replace(/\s+/g, ' ') : ''; });
  ok(/Co EMS planuje na najbliższe 24 h/.test(sum) && /Ładowanie z PV: teraz–/.test(sum) && /Ładowanie z sieci:/.test(sum) && /Sprzedaż z baterii:/.test(sum), 'nad tabelą: opis „Co EMS planuje na najbliższe 24 h”');
  ok(m.errs.length === 0, 'telefon: brak błędów w konsoli: ' + JSON.stringify(m.errs));
  // ---- szeroki ekran: bez zmian
  const w = await openCard(b, { admin: true });
  await w.q(seed); await sleep(1200);
  const gw = await w.q(() => { const t = __el.shadowRoot.querySelector('.px-plan table'); const row = t.querySelector('tbody tr:not(.day):not(.tot)'); return { tbl: getComputedStyle(t).display, head: getComputedStyle(t.querySelector('thead')).display, row: getComputedStyle(row).display, cols: t.querySelectorAll('thead th').length, ths: [...t.querySelectorAll('thead th')].map(x => x.textContent) }; });
  ok(gw.tbl === 'table' && gw.head !== 'none' && gw.row === 'table-row' && gw.cols === 8, 'szeroki ekran: klasyczna tabela z nagłówkiem (8 kolumn): ' + JSON.stringify(gw));
  ok(w.errs.length === 0, 'szeroki ekran: brak błędów w konsoli');
  await b.close();
  console.log(fails ? `\n${fails} niepowodzeń` : '\nOK'); process.exit(fails ? 1 : 0);
})();
