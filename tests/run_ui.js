// Testy karty w przeglądarce (Playwright, Chromium): node tests/run_ui.js
// Wymaga pakietu playwright i przeglądarki: npm install playwright && npx playwright install --with-deps chromium
const { spawnSync } = require('child_process');
const fs = require('fs'); const path = require('path');
const DIR = path.join(__dirname, 'ui');
fs.mkdirSync(path.join(DIR, 'shots'), { recursive: true });
const tests = fs.readdirSync(DIR).filter((f) => /_test\.js$/.test(f)).sort();
const failed = [];
for (const t of tests) {
  const t0 = Date.now();
  const r = spawnSync(process.execPath, [t], { cwd: DIR, encoding: 'utf8', timeout: 400000, env: process.env });
  const out = (r.stdout || '') + (r.stderr || '');
  const bad = r.status !== 0 || /^FAIL\b/m.test(r.stdout || '') || /FAILS [1-9]/.test(out);
  const last = (r.stdout || '').trim().split('\n').slice(-1)[0] || '';
  console.log(`${bad ? 'BŁĄD' : 'OK  '} ${t.padEnd(26)} ${((Date.now() - t0) / 1000).toFixed(1).padStart(5)} s  ${last.slice(0, 100)}`);
  if (bad) { failed.push(t); console.log(out.trim().split('\n').slice(-25).join('\n')); }
}
console.log(`\n${tests.length - failed.length}/${tests.length} plików testów bez błędów`);
process.exit(failed.length ? 1 : 0);
