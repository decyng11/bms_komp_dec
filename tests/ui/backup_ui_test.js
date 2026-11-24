// Kopia ustawień (EMS): przyciski tylko dla administratora, podgląd zmian po wybraniu pliku, zatwierdzenie i anulowanie
const { openCard, chromium } = require('./ui_env');
const { seed, curve, tab, sr } = require('./extras_helpers');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('FAIL', m); } else console.log('ok  ', m); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const FILE = JSON.stringify({ format: 'bms_komp_dec_settings', schema: 1, values: { reserve_floor_soc: 40 } });
(async () => {
  const b = await chromium.launch();
  for (const admin of [true, false]) {
    const e = await openCard(b, {});
    await seed(e, { curve: curve() });
    await e.q((admin) => {
      window.__svc = window.__svc || {}; window.__calls3 = [];
      window.__svc['bms_komp_dec.settings_export'] = () => ({ response: { format: 'bms_komp_dec_settings', schema: 1, exported_at: '2026-11-24T10:00:00', values: { reserve_floor_soc: 25 } } });
      window.__svc['bms_komp_dec.settings_import'] = (d) => { const x = d.service_data || d; window.__calls3.push(x.apply ? 'apply' : 'preview');
        return { response: { changes: [{ key: 'reserve_floor_soc', label: 'Rezerwa <b>baterii</b>', now: '25%', to: '40%' }], skipped: ['xyz'], extras: [], applied: !!x.apply, failed: [] } }; };
      if (!admin) window.__admin = false;
      window.__el.hass = window.__mk();
    }, admin);
    await tab(e, 'ems'); await sleep(1000);
    const dis = await e.q(() => Array.from(__el.shadowRoot.querySelectorAll('#exBackupBox button[data-bk]')).map(x => x.disabled));
    ok(dis.length >= 2 && dis.every(d => d === !admin), `${admin ? 'admin' : 'zwykły'}: przyciski ${admin ? 'aktywne' : 'wyłączone'}`);
    if (admin) {
      await e.page.locator('#exBackupBox input[data-bk="file"]').setInputFiles({ name: 'u.json', mimeType: 'application/json', buffer: Buffer.from(FILE) });
      await e.page.waitForFunction(() => !!__el.shadowRoot.querySelector('#exBackupBox [data-role="bk-prev"]'), null, { timeout: 5000 });
      const t = await sr(e, '#exBackupBox');
      ok(/zmieni 1 ustawień/.test(t) && /25% → 40%/.test(t) && /xyz/.test(t), 'podgląd zmian po wybraniu pliku: ' + t.slice(0, 120));
      ok(await e.q(() => !__el.shadowRoot.querySelector('#exBackupBox [data-role="bk-prev"] b b')), 'etykiety zescape-owane (bez HTML)');
      ok(await e.q(() => JSON.stringify(window.__calls3) === '["preview"]'), 'podgląd nie zapisuje (apply=false)');
      await e.q(() => __el.shadowRoot.querySelector('#exBackupBox [data-bk="apply"]').click()); await sleep(500);
      ok(await e.q(() => JSON.stringify(window.__calls3) === '["preview","apply"]'), 'Wczytaj: usługa z apply=true');
      ok(/Wczytano ustawienia/.test(await sr(e, '#exBackupBox')) && await e.q(() => !__el.shadowRoot.querySelector('#exBackupBox [data-role="bk-prev"]')), 'komunikat sukcesu, podgląd zniknął');
    }
    await e.close && e.close();
  }
  await b.close();
  console.log(fails ? 'FAILED ' + fails : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
