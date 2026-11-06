const sleep = (ms) => new Promise(r => setTimeout(r, ms));
// ---- dane testowe: krzywa planu 24 h od 16:00 (wsz. tablice po 24 elementy)
function curve(opts = {}) {
  const n = 24, h0 = 16;
  const soc = [], floor = [], pv = [], load = [], buy = [], sell = [], peak = [], grid = [], sale = [], target = [];
  let s = 62;
  for (let i = 0; i < n; i++) {
    const h = (h0 + i) % 24;
    const isPeak = (h >= 6 && h < 13) || (h >= 15 && h < 22);
    const g = h >= 22 || h < 6;
    const sl = h === 18 || h === 19;
    if (sl) s -= 12; else if (g) s = Math.min(95, s + 18); else if (h >= 9 && h <= 15) s = Math.min(100, s + 9); else s -= 4;
    if (opts.low && i === 10) s = 26;
    s = Math.max(s, 5);
    soc.push(Math.round(s * 10) / 10); floor.push(25); pv.push(h >= 8 && h <= 16 ? 2.4 : 0); load.push(0.6 + (h === 19 ? 0.9 : 0));
    buy.push(isPeak ? 1.29 : 0.62); sell.push(opts.noSell ? null : (h === 19 ? 1.1 : (h === 13 ? -0.05 : 0.45)));
    peak.push(isPeak ? 1 : 0); grid.push(opts.noGrid ? 0 : (g ? 1 : 0)); sale.push(sl ? 1 : 0); target.push(g && !opts.noGrid ? 90 : null);
  }
  return { start: '2026-11-03T16:00:00+01:00', hours: n, soc_now: 62, soc, floor, pv, load, buy, sell, peak, grid, sale, target };
}
const REPORT = (o = {}) => Object.assign({
  year: 2026, month: 11, title: 'Listopad 2026', days_with_data: 3, days_in_month: 30, complete: false, revenue: 12.5, cost: 8.2, net: 4.3,
  export_kwh: 18.4, import_kwh: 14.1, neg_export_kwh: 0.6, avg_sell_price: 0.679, avg_buy_price: 0.58, pv_kwh: 52, load_kwh: 61,
  battery_charge_kwh: 24, battery_discharge_kwh: 21, self_consumption_pct: 65, self_sufficiency_pct: 77, saving_estimate: 35.7,
  best_day: { date: '2026-11-02', net: 2.4 }, worst_day: { date: '2026-11-01', net: -0.3 }, cycle_efficiency_pct: 88.5, cycle_efficiency_days: 2,
  days: [{ date: '2026-11-01', net: -0.3 }, { date: '2026-11-02', net: 2.4 }, { date: '2026-11-03', net: 2.2 }],
}, o);
const HEALTH = { eff_7d: 89.2, days_7d: 6, eff_30d: 88.1, days_30d: 20, eff_90d: 87.0, days_90d: 60, eff_trend_pp: 1.1, capacity_est_kwh: 9.6, capacity_samples: 11, capacity_configured_kwh: 10.0, soh_est_pct: 96 };

async function seed(e, o = {}) {
  await e.q((o) => {
    const S = (v, a) => ({ state: String(v), attributes: a || {}, last_updated: new Date().toISOString() });
    const st = window.__states;
    st['sensor.bms_reserve_soc'] = S(40, { inverter_floor: 25, capacity_kwh: 10, price_buy: 1.29, price_sell: 0.45, storm: !!o.storm });
    if (!o.noPlan) st['sensor.bms_plan_curve'] = S(o.planState || 'normal', { mode: o.mode || 'normal', generated_at: '2026-11-03T15:50:00+01:00', error: o.planError || null, curve: o.noCurve ? null : o.curve, proposals: o.proposals || { start_grid_charge: { label: 'Start ładowania z sieci 1', current: '22:00', proposed: '23:00', skip: false }, stop_grid_charge: { label: 'Stop ładowania z sieci 1', current: '06:00', proposed: '06:00', skip: false }, bateria_sprzedaz_start: { label: 'Start sprzedaży 1', current: '18:00', proposed: null, skip: true } } });
    if (!o.noReport) st['sensor.bms_monthly_report'] = S(4.3, o.report);
    st['sensor.bms_battery_health'] = S(88.1, o.health);
    st['sensor.bms_monitor_status'] = S(0, o.monitor || { alarms: [], low_soc_active: false, watches: [] });
    ['storm_mode', 'vacation_mode', 'notifications_enabled', 'auto_apply_dry_run'].forEach((k) => { st['switch.bms_' + k] = S(k === 'notifications_enabled' ? 'on' : (o[k] || 'off'), { friendly_name: k }); });
    st['number.bms_storm_mode_hours'] = S(24, { min: 1, max: 96, step: 1 });
    st['number.bms_vacation_load_w'] = S(250, { min: 0, max: 5000, step: 10 });
    window.__el.hass = window.__mk();
  }, o);
}
const tab = async (e, t) => { await e.q((t) => __el.shadowRoot.querySelector(`[data-tab="${t}"]`).click(), t); await sleep(300); };
const sr = (e, sel) => e.q((sel) => { const x = __el.shadowRoot.querySelector(sel); return x ? x.textContent.replace(/\s+/g, ' ').trim() : null; }, sel);
const blue = (e) => e.q(() => { const c = __el.shadowRoot.querySelector('#exPlanCv'); if (!c) return -1; const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let n = 0; for (let i = 0; i < d.length; i += 4) if (d[i + 3] > 200 && Math.abs(d[i] - 10) < 25 && Math.abs(d[i + 1] - 132) < 25 && d[i + 2] > 220) n++; return n; });


// Diagnostyka → odblokowanie hasłem → pill „Tryby”
const openModes = async (e) => {
  await tab(e, 'diag');
  await e.page.waitForFunction(() => !!__el.shadowRoot.getElementById('dgPw') || !!__el.shadowRoot.querySelector('[data-act="sec"]'), null, { timeout: 8000 });
  await e.q(() => { const s = __el.shadowRoot; if (s.getElementById('dgPw')) { s.getElementById('dgPw').value = 'slonce'; s.querySelector('[data-act=unlock]').click(); } });
  await sleep(500);
  await e.q(() => __el.shadowRoot.querySelector('[data-act="sec"][data-sec="modes"]').click());
  await sleep(400);
};

// Diagnostyka → odblokowanie hasłem → pill dowolnej sekcji
const openSec = async (e, sec) => {
  await tab(e, 'diag');
  await e.page.waitForFunction(() => !!__el.shadowRoot.getElementById('dgPw') || !!__el.shadowRoot.querySelector('[data-act="sec"]'), null, { timeout: 8000 });
  await e.q(() => { const s = __el.shadowRoot; if (s.getElementById('dgPw')) { s.getElementById('dgPw').value = 'slonce'; s.querySelector('[data-act=unlock]').click(); } });
  await sleep(500);
  await e.q((sec) => __el.shadowRoot.querySelector(`[data-act="sec"][data-sec="${sec}"]`).click(), sec);
  await sleep(500);
};

module.exports = { seed, curve, REPORT, HEALTH, tab, sr, blue, openModes, openSec };
