/**
 * BMS Centrum Energii — moduł „Urządzenia” (dodatkowe odbiorniki z pomiarem W / kWh)
 * Ładowany na żądanie przez bms-panel.js (kontrakt modułu: 1). Nie dodawaj tego pliku do zasobów dashboardu ręcznie.
 * Dane liczy integracja (usługi devices_get / devices_set, sensor bms_devices); historia sprzed dodania urządzenia
 * jest uzupełniana ze statystyk długoterminowych Home Assistanta (dla encji z state_class).
 */
(function () {
  'use strict';
  const install = function (BmsPanel, shared) {
    const dvEsc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const dvNum = (v) => (v === null || v === undefined || v === '' || isNaN(Number(v))) ? null : Number(v);
    const dvFmt = (v, d, unit) => { const n = dvNum(v); return n === null ? '—' : n.toFixed(d == null ? 1 : d).replace('.', ',') + (unit || ''); };
    const dvZl = (v) => { const n = dvNum(v); return n === null ? '—' : n.toFixed(2).replace('.', ',') + ' zł'; };
    const dvErr = (e) => String((e && (e.message || e.code)) || e || 'błąd').slice(0, 200);
    const dvCall = (card, service, data) => card._hass.callWS({ type: 'call_service', domain: 'bms_komp_dec', service, service_data: data || {}, return_response: true });
    const dvResp = (r) => (r && r.response !== undefined ? r.response : r);
    const dk = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    const COLORS = ['#0a84ff', '#ff9f0a', '#30d158', '#bf5af2', '#ff375f', '#64d2ff', '#ffd60a', '#ac8e68', '#5e5ce6', '#ff6961', '#66d4cf', '#e5a00d'];
    const REST = '#8e8e93';
    const RANGES = [['1d', '1 dzień'], ['7d', '7 dni'], ['30d', '30 dni'], ['3m', '3 mies.'], ['6m', '6 mies.'], ['12m', '12 mies.']];
    const SRC_NAMES = ['PV', 'bateria', 'sieć'];
    const MONTHS = ['sty', 'lut', 'mar', 'kwi', 'maj', 'cze', 'lip', 'sie', 'wrz', 'paź', 'lis', 'gru'];

    const DV_CSS = `
      .dv-bar { display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-bottom:10px; }
      .dv-pill { border:none; background:var(--surface); color:var(--text2); border-radius:999px; padding:6px 12px; font-size:12px; cursor:pointer; font-family:inherit; }
      .dv-pill.on { background:var(--accent, #0a84ff); color:#fff; }
      .dv-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(170px, 1fr)); gap:10px; }
      .dv-tile { background:var(--surface); border-radius:14px; padding:10px 12px; cursor:pointer; border:2px solid transparent; }
      .dv-tile.sel { border-color:var(--accent, #0a84ff); }
      .dv-tile .n { font-size:13px; font-weight:600; display:flex; gap:6px; align-items:center; }
      .dv-tile .p { font-size:20px; font-weight:700; margin-top:4px; }
      .dv-tile .s { font-size:11px; color:var(--muted); margin-top:2px; }
      .dv-run { font-size:10px; padding:1px 6px; border-radius:999px; background:rgba(48,209,88,.18); color:var(--green); }
      .dv-tbl { width:100%; border-collapse:collapse; font-size:12px; }
      .dv-tbl th { text-align:left; color:var(--muted); font-weight:500; padding:6px 6px; border-bottom:1px solid var(--line); white-space:nowrap; }
      .dv-tbl td { padding:6px; border-bottom:1px solid var(--line); vertical-align:top; }
      .dv-tbl td.r, .dv-tbl th.r { text-align:right; white-space:nowrap; }
      .dv-scroll { overflow-x:auto; }
      .dv-leg { display:flex; flex-wrap:wrap; gap:6px 14px; font-size:11px; color:var(--muted); margin:8px 0 4px; }
      .dv-leg i { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:4px; vertical-align:-1px; }
      .dv-note { font-size:11px; color:var(--muted); margin-top:8px; line-height:1.5; }
      .dv-form { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:10px 14px; }
      .dv-form label { font-size:12px; color:var(--muted); display:flex; flex-direction:column; gap:4px; }
      .dv-form input[type=text], .dv-form input[type=number], .dv-form select { background:var(--surface); color:var(--text); border:1px solid var(--line); border-radius:10px; padding:8px 10px; font-size:13px; font-family:inherit; }
      .dv-form .chk { flex-direction:row; align-items:center; gap:8px; color:var(--text2); }
      .dv-form .full { grid-column:1 / -1; }
      .dv-btn { border:none; border-radius:10px; padding:8px 14px; font-size:13px; font-weight:600; cursor:pointer; font-family:inherit; background:var(--accent, #0a84ff); color:#fff; }
      .dv-btn.sec { background:var(--surface); color:var(--text); }
      .dv-btn.bad { background:rgba(255,69,58,.18); color:var(--red); }
      .dv-heat { display:grid; gap:2px; font-size:10px; color:var(--muted); }
      .dv-heat div.c { height:16px; border-radius:3px; }
      @media (max-width:600px) { .dv-form { grid-template-columns:1fr; } }
    `;

    Object.assign(BmsPanel.prototype, {
      _dvS() {
        if (!this._dv) this._dv = { data: null, loading: false, err: '', range: '7d', sel: 'all', edit: null, msg: '', stats: {}, statsKey: '', fetchedAt: 0 };
        return this._dv;
      },
      _dvAdmin() { const u = this._hass && this._hass.user; return !!(u && u.is_admin); },
      _dvCss() {
        const root = this.shadowRoot; if (!root || root.getElementById('dvStyle')) return;
        const st = document.createElement('style'); st.id = 'dvStyle'; st.textContent = DV_CSS; root.appendChild(st);
      },
      _devOpen() {
        this._dvCss();
        const s = this._dvS();
        const root = this._el('devRoot'); if (!root) return;
        if (!root.dataset.dvBound) {
          root.dataset.dvBound = '1';
          root.addEventListener('click', (e) => this._dvClick(e));
          root.addEventListener('change', (e) => this._dvChange(e));
        }
        if (!s.data || Date.now() - s.fetchedAt > 300000) this._dvLoad();
        else this._dvRender();
      },
      _devTick() {
        if (this._activeTab !== 'dev') return;
        const s = this._dvS();
        if (s.edit || s.disc) return;                             // nie przerysowujemy formularza w trakcie edycji / wyszukiwania
        if (Date.now() - s.fetchedAt > 300000 && !s.loading) { this._dvLoad(); return; }
        this._dvLive();
      },
      async _dvLoad() {
        const s = this._dvS();
        s.loading = true; s.err = ''; this._dvRender();
        try {
          s.data = dvResp(await dvCall(this, 'devices_get', { history: true })) || {};
          s.fetchedAt = Date.now();
          await this._dvLoadStats();
        } catch (e) { s.err = dvErr(e); }
        s.loading = false; this._dvRender();
      },
      // Statystyki długoterminowe HA (dziennie, do 13 miesięcy) — uzupełniają dni sprzed dodania urządzenia.
      async _dvLoadStats() {
        const s = this._dvS(); const devs = (s.data && s.data.devices) || [];
        const ids = []; devs.forEach((d) => { if (d.energy_eid) ids.push(d.energy_eid); else if (d.power_eid) ids.push(d.power_eid); });
        const key = ids.join('|');
        if (!ids.length || s.statsKey === key) return;
        try {
          const end = new Date(); const start = new Date(end.getTime() - 400 * 86400000);
          const res = await this._hass.callWS({ type: 'recorder/statistics_during_period', start_time: start.toISOString(), end_time: end.toISOString(), statistic_ids: ids, period: 'day', types: ['change', 'mean'] });
          const out = {};
          devs.forEach((d) => {
            const eid = d.energy_eid || d.power_eid; const rows = (res && res[eid]) || []; const m = {};
            rows.forEach((r) => {
              const t = new Date(typeof r.start === 'number' ? r.start : String(r.start));
              if (isNaN(t.getTime())) return;
              let v = null;
              if (d.energy_eid && dvNum(r.change) !== null) v = Math.max(0, Number(r.change));
              else if (!d.energy_eid && dvNum(r.mean) !== null) v = Math.max(0, Number(r.mean)) * 24 / 1000;
              if (v !== null && v < 500) m[dk(t)] = v;
            });
            out[d.id] = m;
          });
          s.stats = out; s.statsKey = key;
        } catch (e) { s.stats = {}; s.statsKey = key; }
      },
      _dvDevs() { const s = this._dvS(); return (s.data && s.data.devices) || []; },
      _dvCat(key) { const s = this._dvS(); return ((s.data && s.data.categories) || []).find((c) => c.key === key); },
      // dzienne kWh urządzenia: dane integracji, a dni bez nich — ze statystyk HA
      _dvDaily(id) {
        const s = this._dvS(); const h = ((s.data && s.data.history) || {})[id] || {};
        return Object.assign({}, (s.stats && s.stats[id]) || {}, h.daily || {});
      },
      _dvSelected() {
        const s = this._dvS(); const devs = this._dvDevs();
        if (s.sel === 'all') return devs;
        if (s.sel.startsWith('room:')) return devs.filter((d) => (d.room || '') === s.sel.slice(5));
        if (s.sel.startsWith('grp:')) return devs.filter((d) => { const c = this._dvCat(d.category); return c && c.group === s.sel.slice(4); });
        return devs.filter((d) => d.id === s.sel);
      },
      // Szereg do wykresu: etykiety i wartości (kWh) per urządzenie + „reszta domu” (gdy pokazujemy wszystkie)
      _dvSeries() {
        const s = this._dvS(); const sel = this._dvSelected(); const today = new Date();
        const hist = (s.data && s.data.history) || {};
        const house = (s.data && s.data.house_daily) || {};
        let labels = [], buckets = [];
        if (s.range === '1d') {
          labels = Array.from({ length: 24 }, (_, h) => String(h).padStart(2, '0'));
          const k = dk(today);
          const series = sel.map((d) => ({ d, vals: (((hist[d.id] || {}).hourly || {})[k] || new Array(24).fill(0)).map(Number) }));
          let rest = null;
          if (s.sel === 'all') {
            const lf = this._hass.states[this._eid('sensor', 'load_forecast')];
            const ht = lf && lf.attributes && Array.isArray(lf.attributes.hourly_today) ? lf.attributes.hourly_today : null;
            if (ht) rest = ht.map((v, h) => (dvNum(v) === null ? 0 : Math.max(0, Number(v) - series.reduce((a, x) => a + (x.vals[h] || 0), 0))));
          }
          return { labels, series, rest, unit: 'kWh/h' };
        }
        const days = { '7d': 7, '30d': 30, '3m': 91, '6m': 182, '12m': 365 }[s.range] || 7;
        const keys = Array.from({ length: days }, (_, i) => { const d = new Date(today); d.setDate(d.getDate() - (days - 1 - i)); return dk(d); });
        const group = s.range === '12m' ? 'month' : (s.range === '3m' || s.range === '6m') ? 'week' : 'day';
        const bkey = (k) => {
          if (group === 'day') return k;
          if (group === 'month') return k.slice(0, 7);
          const d = new Date(k + 'T12:00:00'); const wd = (d.getDay() + 6) % 7; d.setDate(d.getDate() - wd); return dk(d);
        };
        keys.forEach((k) => { const b = bkey(k); if (!buckets.length || buckets[buckets.length - 1] !== b) buckets.push(b); });
        labels = buckets.map((b) => group === 'month' ? `${MONTHS[Number(b.slice(5, 7)) - 1]} ${b.slice(2, 4)}` : `${b.slice(8, 10)}.${b.slice(5, 7)}`);
        const sum = (map) => buckets.map((b) => keys.filter((k) => bkey(k) === b).reduce((a, k) => a + (Number(map[k]) || 0), 0));
        const series = sel.map((d) => ({ d, vals: sum(this._dvDaily(d.id)) }));
        let rest = null;
        if (s.sel === 'all') {
          const hv = sum(house);
          rest = hv.map((v, i) => Math.max(0, v - series.reduce((a, x) => a + x.vals[i], 0)));
          if (!rest.some((v) => v > 0)) rest = null;
        }
        return { labels, series, rest, unit: group === 'day' ? 'kWh/dzień' : group === 'week' ? 'kWh/tydzień' : 'kWh/miesiąc', keys, bkey };
      },
      _dvChart() {
        const { labels, series, rest, unit } = this._dvSeries();
        const all = series.map((x, i) => ({ name: `${x.d.icon || ''} ${x.d.name}`, color: COLORS[this._dvDevs().indexOf(x.d) % COLORS.length], vals: x.vals }))
          .concat(rest ? [{ name: 'reszta domu', color: REST, vals: rest }] : []);
        const n = labels.length;
        if (!n || !all.length) return '<div class="chart-empty">Brak danych w tym zakresie.</div>';
        const totals = labels.map((_, i) => all.reduce((a, s) => a + (s.vals[i] || 0), 0));
        const max = Math.max(0.01, ...totals);
        const every = Math.max(1, Math.ceil(n / 12));
        const bw = Math.min(70, 100 / n * 0.7);
        const cols = labels.map((lab, i) => {
          let segs = ''; let acc = 0;
          all.forEach((s) => {
            const v = s.vals[i] || 0; if (v <= 0) return;
            const h = v / max * 100;
            segs += `<div title="${dvEsc(s.name)}: ${dvFmt(v, 2, ' kWh')}" style="position:absolute;left:0;right:0;bottom:${acc}%;height:${h}%;background:${s.color};"></div>`;
            acc += h;
          });
          const x = (i + 0.5) / n * 100;
          return `<div title="${dvEsc(lab)}: ${dvFmt(totals[i], 2, ' kWh')}" style="position:absolute;left:${x}%;bottom:0;top:0;width:min(${bw}%, 26px);transform:translateX(-50%);">${segs}</div>`
            + ((i % every === 0 || i === n - 1) ? `<div style="position:absolute;left:${x}%;top:100%;transform:translateX(-50%);margin-top:4px;font-size:11px;color:var(--muted);white-space:nowrap;">${dvEsc(lab)}</div>` : '');
        }).join('');
        const leg = all.map((s) => `<span><i style="background:${s.color};"></i>${dvEsc(s.name)} <b>${dvFmt(s.vals.reduce((a, v) => a + v, 0), 1, ' kWh')}</b></span>`).join('');
        return `<div class="dv-leg">${leg}</div>
          <div style="display:flex;margin-top:6px;">
            <div style="width:46px;flex:none;position:relative;height:170px;font-size:11px;color:var(--muted);">
              <div style="position:absolute;right:6px;top:0;transform:translateY(-50%);">${dvFmt(max, 1)}</div>
              <div style="position:absolute;right:6px;top:50%;transform:translateY(-50%);">${dvFmt(max / 2, 1)}</div>
              <div style="position:absolute;right:6px;bottom:0;transform:translateY(50%);">0</div></div>
            <div style="flex:1;min-width:0;position:relative;height:170px;border-bottom:1px solid var(--line);margin-bottom:22px;">
              <div style="position:absolute;left:0;right:0;top:50%;border-top:1px dashed var(--line);"></div>${cols}</div></div>
          <div class="dv-note">Jednostka: ${dvEsc(unit)}. Najedź na słupek, aby zobaczyć wartości.${rest ? ' „Reszta domu” = zużycie domu minus dodane urządzenia.' : ''}</div>`;
      },
      _dvRangeTotals(d) {
        const s = this._dvS(); const { series, keys } = this._dvSeries();
        const x = series.find((q) => q.d.id === d.id); const kwh = x ? x.vals.reduce((a, v) => a + v, 0) : 0;
        let cost = null;
        if (s.range === '1d') cost = dvNum(((s.data.summary || []).find((q) => q.id === d.id) || {}).today_cost);
        else if (keys) { const c = (((s.data.history || {})[d.id] || {}).cost) || {}; const v = keys.reduce((a, k) => a + (Number(c[k]) || 0), 0); cost = v > 0 ? v : null; }
        return { kwh, cost };
      },
      _dvTable() {
        const s = this._dvS(); const sum = (s.data && s.data.summary) || []; const devs = this._dvSelected();
        if (!devs.length) return '';
        const rows = devs.map((d) => {
          const q = sum.find((x) => x.id === d.id) || {}; const t = this._dvRangeTotals(d);
          const src = Array.isArray(q.src_pct) ? q.src_pct.map((v, i) => `${SRC_NAMES[i]} ${v}%`).join(' · ') : '—';
          const cyc = q.cycles_30d ? `${q.cycles_30d} × śr. ${dvFmt(q.cycle_avg_kwh, 2, ' kWh')}${q.cycle_avg_cost != null ? ', ' + dvZl(q.cycle_avg_cost) : ''}${q.cycle_avg_min != null ? ', ' + dvFmt(q.cycle_avg_min, 0, ' min') : ''}` : '—';
          const stb = q.standby_w != null ? `${dvFmt(q.standby_w, 1, ' W')}${q.standby_cost_year != null ? ` (~${dvFmt(q.standby_cost_year, 0, ' zł/rok')})` : ''}` : '—';
          return `<tr><td>${dvEsc(d.icon)} ${dvEsc(d.name)}${d.room ? `<div class="dv-note" style="margin:0;">${dvEsc(d.room)}</div>` : ''}</td>
            <td class="r">${dvFmt(t.kwh, 2)}</td><td class="r">${t.cost != null ? dvZl(t.cost) : '—'}</td>
            <td class="r">${q.share_house_30d != null ? dvFmt(q.share_house_30d, 0, '%') : '—'}</td><td class="r">${q.avg_price != null ? dvFmt(q.avg_price, 2) : '—'}</td>
            <td>${stb}</td><td>${cyc}</td><td>${src}</td><td class="r">${q.saving_30d != null ? dvZl(q.saving_30d) : '—'}</td></tr>`;
        }).join('');
        return `<div class="dv-scroll"><table class="dv-tbl"><thead><tr><th>Urządzenie</th><th class="r">kWh (zakres)</th><th class="r">Koszt (zakres)</th><th class="r">% domu (30 d)</th><th class="r">Śr. cena zł/kWh</th><th>Czuwanie</th><th>Cykle (30 d)</th><th>Źródło energii (30 d)</th><th class="r">Do zaoszczędzenia (30 d)</th></tr></thead><tbody>${rows}</tbody></table></div>
          <div class="dv-note">„Do zaoszczędzenia” — dla urządzeń elastycznych: o ile taniej byłoby, gdyby całe zużycie dnia przypadło na jego najtańszą godzinę (górna granica). Źródło energii to szacunek z bilansu domu w chwili pracy urządzenia. Koszt liczony jest po cenie zakupu z sieci (tak, jakby całość pochodziła z sieci) — część z PV i baterii kosztuje w praktyce mniej, patrz „Źródło energii”. Koszt jest znany od dnia dodania urządzenia (wcześniejsze dni ze statystyk HA mają tylko kWh).</div>`;
      },
      _dvCompare() {
        const devs = this._dvSelected(); if (!devs.length) return '';
        const now = new Date();
        const ym = (y, m) => `${y}-${String(m + 1).padStart(2, '0')}`;
        const cur = ym(now.getFullYear(), now.getMonth());
        const pm = new Date(now.getFullYear(), now.getMonth() - 1, 1); const prev = ym(pm.getFullYear(), pm.getMonth());
        const ly = ym(now.getFullYear() - 1, now.getMonth());
        const day = now.getDate();
        const tot = (prefix, uptoDay) => devs.reduce((a, d) => a + Object.entries(this._dvDaily(d.id)).filter(([k]) => k.startsWith(prefix) && (!uptoDay || Number(k.slice(8, 10)) <= uptoDay)).reduce((x, [, v]) => x + Number(v || 0), 0), 0);
        const c = tot(cur), p = tot(prev, day), l = tot(ly, day);
        const pct = (a, b) => (b > 0.05 ? `${a >= b ? '+' : '−'}${Math.abs((a / b - 1) * 100).toFixed(0)}%` : '—');
        return `<div class="dv-scroll"><table class="dv-tbl"><thead><tr><th>Okres (do ${day}. dnia)</th><th class="r">kWh</th><th class="r">Zmiana</th></tr></thead><tbody>
          <tr><td>Ten miesiąc</td><td class="r">${dvFmt(c, 1)}</td><td></td></tr>
          <tr><td>Poprzedni miesiąc</td><td class="r">${p > 0 ? dvFmt(p, 1) : '—'}</td><td class="r">${pct(c, p)}</td></tr>
          <tr><td>Ten sam miesiąc rok temu</td><td class="r">${l > 0 ? dvFmt(l, 1) : '—'}</td><td class="r">${pct(c, l)}</td></tr></tbody></table></div>
          <div class="dv-note">Porównanie tych samych dni miesiąca. Dane sprzed dodania urządzenia pochodzą ze statystyk Home Assistanta (jeśli encja je zapisywała).</div>`;
      },
      _dvRooms() {
        const devs = this._dvDevs(); const rooms = {};
        devs.forEach((d) => { const r = d.room || ''; if (!r) return; const t = this._dvRangeTotals(d); rooms[r] = (rooms[r] || 0) + t.kwh; });
        const ks = Object.keys(rooms); if (!ks.length) return '';
        const max = Math.max(0.01, ...Object.values(rooms));
        return ks.sort((a, b) => rooms[b] - rooms[a]).map((r) => `<div style="display:flex;align-items:center;gap:8px;margin:4px 0;font-size:12px;">
          <div style="width:120px;flex:none;">${dvEsc(r)}</div><div style="flex:1;background:var(--surface);border-radius:6px;height:12px;"><div style="width:${rooms[r] / max * 100}%;height:100%;background:#0a84ff;border-radius:6px;"></div></div>
          <div style="width:80px;text-align:right;">${dvFmt(rooms[r], 1, ' kWh')}</div></div>`).join('');
      },
      _dvHeat() {
        const s = this._dvS(); const devs = this._dvSelected();
        if (devs.length !== 1) return '<div class="dv-note">Wybierz jedno urządzenie, aby zobaczyć mapę godzin.</div>';
        const h = (((s.data.history || {})[devs[0].id] || {}).hourly) || {};
        const today = new Date();
        const days = Array.from({ length: 14 }, (_, i) => { const d = new Date(today); d.setDate(d.getDate() - (13 - i)); return dk(d); });
        const max = Math.max(0.001, ...days.flatMap((k) => (h[k] || []).map(Number)));
        const head = `<div></div>${Array.from({ length: 24 }, (_, i) => `<div style="text-align:center;">${i % 3 === 0 ? i : ''}</div>`).join('')}`;
        const rows = days.map((k) => `<div style="white-space:nowrap;">${k.slice(8, 10)}.${k.slice(5, 7)}</div>` + Array.from({ length: 24 }, (_, i) => {
          const v = Number((h[k] || [])[i] || 0);
          return `<div class="c" title="${k} ${String(i).padStart(2, '0')}:00 — ${dvFmt(v, 3, ' kWh')}" style="background:rgba(10,132,255,${v > 0 ? Math.max(0.08, v / max).toFixed(2) : 0.04});"></div>`;
        }).join('')).join('');
        return `<div class="dv-scroll"><div class="dv-heat" style="grid-template-columns:44px repeat(24, minmax(10px, 1fr));min-width:420px;">${head}${rows}</div></div>
          <div class="dv-note">Ostatnie 14 dni: im ciemniej, tym więcej kWh w danej godzinie.</div>`;
      },
      _dvInfo() {
        const s = this._dvS(); const d = s.data || {}; const out = [];
        (d.flex_plan || []).forEach((p) => out.push(`<div>🗓 ${dvEsc(p.icon)} <b>${dvEsc(p.name)}</b>: najlepiej ${dvEsc(String(p.start).slice(11, 16))}–${dvEsc(String(p.end).slice(11, 16))} (~${dvFmt(p.kwh, 1, ' kWh')}, ${dvEsc(p.why)}, ok. ${dvZl(p.cost)})</div>`));
        if (d.unknown) out.push(`<div>🔎 Nierozpoznany odbiornik: ok. ${String(d.unknown.hour).padStart(2, '0')}:00 dom pobiera ok. ${dvFmt(d.unknown.kwh, 1, ' kWh')} więcej (${d.unknown.days} z ${d.unknown.of} dni). Jeśli wiesz, co to jest — dodaj je.</div>`);
        const fs = d.forecast_split;
        if (fs) out.push(`<div>📈 Prognoza zużycia z podziałem na urządzenia: ${fs.use ? `<b>używana</b> (${dvFmt(fs.total, 1, ' kWh')} jutro; reszta domu ${dvFmt(fs.residual, 1)} + ${(fs.parts || []).map((p) => `${dvEsc(p.name)} ${dvFmt(p.kwh, 1)}`).join(' + ')})` : 'nie używana'} — ${dvEsc(fs.reason || '')}${fs.mae_split != null ? ` (błąd z podziałem ${dvFmt(fs.mae_split, 2)} kWh, bez ${dvFmt(fs.mae_total, 2)} kWh)` : ''}.</div>`);
        return out.length ? `<div style="font-size:12px;line-height:1.7;">${out.join('')}</div>` : '<div class="dv-note">Plan dla urządzeń elastycznych pojawi się po kilku dniach danych (typowe zużycie i moc).</div>';
      },
      _dvLiveTiles() {
        const s = this._dvS(); const st = this._hass.states[this._eid('sensor', 'devices')];
        const live = (st && st.attributes && Array.isArray(st.attributes.devices)) ? st.attributes.devices : ((s.data && s.data.live) || []);
        const devs = this._dvDevs();
        return devs.map((d, i) => {
          const l = live.find((x) => x.id === d.id) || {};
          return `<div class="dv-tile ${s.sel === d.id ? 'sel' : ''}" data-dv="sel" data-id="${dvEsc(d.id)}" style="border-left:4px solid ${COLORS[i % COLORS.length]};">
            <div class="n">${dvEsc(d.icon)} ${dvEsc(d.name)} ${l.running ? '<span class="dv-run">pracuje</span>' : ''}</div>
            <div class="p">${l.power != null ? dvFmt(l.power, 0, ' W') : '—'}</div>
            <div class="s">dziś ${dvFmt(l.today_kwh, 2, ' kWh')} · ${dvZl(l.today_cost)}${d.room ? ' · ' + dvEsc(d.room) : ''}</div>
            ${this._dvAdmin() ? `<div style="margin-top:6px;"><button class="dv-pill" data-dv="edit" data-id="${dvEsc(d.id)}">✏️ Edytuj</button></div>` : ''}</div>`;
        }).join('');
      },
      _dvLive() { const g = this._el('dvLive'); if (g) g.innerHTML = this._dvLiveTiles(); },
      _dvRender() {
        const root = this._el('devRoot'); if (!root) return;
        const s = this._dvS();
        if (s.edit) { root.innerHTML = this._dvEditor(); return; }
        if (s.disc) { root.innerHTML = this._dvDiscView(); return; }
        if (s.loading && !s.data) { root.innerHTML = '<div class="chart-empty">Wczytuję urządzenia…</div>'; return; }
        if (s.err && !s.data) { root.innerHTML = `<div class="chart-empty" style="color:var(--red);">Nie udało się wczytać urządzeń: ${dvEsc(s.err)}<br><button class="dv-btn sec" data-dv="reload" style="margin-top:10px;">Spróbuj ponownie</button><div class="dv-note">Wymaga integracji 0.8.1 lub nowszej.</div></div>`; return; }
        const devs = this._dvDevs(); const admin = this._dvAdmin();
        const head = `<div class="dv-bar">${admin ? `<button class="dv-btn" data-dv="add" ${devs.length >= ((s.data && s.data.max_devices) || 40) ? 'disabled' : ''}>➕ Dodaj urządzenie</button><button class="dv-btn sec" data-dv="disc" ${devs.length >= ((s.data && s.data.max_devices) || 40) ? 'disabled' : ''}>🔍 Wyszukaj urządzenia</button>` : ''}
          <button class="dv-btn sec" data-dv="csv" ${devs.length ? '' : 'disabled'}>⬇ CSV</button><button class="dv-btn sec" data-dv="reload">⟳ Odśwież</button>
          <span class="dv-note" style="margin:0;">${dvEsc(s.msg || '')}</span></div>`;
        if (!devs.length) {
          root.innerHTML = `<div class="section"><div class="section-title">🔌 Urządzenia</div><div class="chart-card full" style="padding:14px 16px;">${head}
            <div class="chart-empty">Nie dodano jeszcze żadnego urządzenia.${admin ? ' Kliknij „Wyszukaj urządzenia”, żeby znaleźć liczniki kWh w Home Assistant, albo „Dodaj urządzenie” i wskaż encję ręcznie.' : ' Urządzenia może dodać administrator.'}</div></div></div>`;
          return;
        }
        const rooms = Array.from(new Set(devs.map((d) => d.room).filter(Boolean)));
        const groups = Array.from(new Set(devs.map((d) => (this._dvCat(d.category) || {}).group).filter(Boolean)));
        const opt = (v, l) => `<option value="${dvEsc(v)}" ${s.sel === v ? 'selected' : ''}>${dvEsc(l)}</option>`;
        const filter = `<select data-dv="filter" style="background:var(--surface);color:var(--text);border:1px solid var(--line);border-radius:10px;padding:6px 10px;">
          ${opt('all', 'Wszystkie urządzenia + reszta domu')}${groups.length ? `<optgroup label="Kategorie">${groups.map((g) => opt('grp:' + g, g)).join('')}</optgroup>` : ''}
          ${rooms.length ? `<optgroup label="Pomieszczenia">${rooms.map((r) => opt('room:' + r, r)).join('')}</optgroup>` : ''}
          <optgroup label="Urządzenie">${devs.map((d) => opt(d.id, `${d.icon} ${d.name}`)).join('')}</optgroup></select>`;
        const ranges = RANGES.map(([k, l]) => `<button class="dv-pill ${s.range === k ? 'on' : ''}" data-dv="range" data-r="${k}">${l}</button>`).join('');
        root.innerHTML = `
          <div class="section"><div class="section-title">🔌 Urządzenia — teraz</div><div class="chart-card full" style="padding:14px 16px;">${head}<div class="dv-grid" id="dvLive">${this._dvLiveTiles()}</div></div></div>
          <div class="section"><div class="section-title">📊 Zużycie</div><div class="chart-card full" style="padding:14px 16px;">
            <div class="dv-bar">${ranges}<span style="flex:1;"></span>${filter}</div>${this._dvChart()}</div></div>
          <div class="section"><div class="section-title">💰 Ranking i koszty</div><div class="chart-card full" style="padding:14px 16px;">${this._dvTable()}</div></div>
          <div class="section"><div class="section-title">📅 Porównanie miesięcy</div><div class="chart-card full" style="padding:14px 16px;">${this._dvCompare()}</div></div>
          ${rooms.length ? `<div class="section"><div class="section-title">🏠 Pomieszczenia (zakres)</div><div class="chart-card full" style="padding:14px 16px;">${this._dvRooms()}</div></div>` : ''}
          <div class="section"><div class="section-title">🕒 Kiedy pracuje</div><div class="chart-card full" style="padding:14px 16px;">${this._dvHeat()}</div></div>
          <div class="section"><div class="section-title">💡 Plan i podpowiedzi</div><div class="chart-card full" style="padding:14px 16px;">${this._dvInfo()}</div></div>`;
      },
      // ------------------------------------------------------------ edytor
      _dvEditor() {
        const s = this._dvS(); const e = s.edit; const cats = (s.data && s.data.categories) || []; const groups = (s.data && s.data.groups) || [];
        const ents = Object.keys(this._hass.states).filter((x) => x.startsWith('sensor.'));
        const unitOf = (x) => String(((this._hass.states[x] || {}).attributes || {}).unit_of_measurement || '').toLowerCase();
        const pw = ents.filter((x) => ['w', 'kw'].includes(unitOf(x))).sort();
        const en = ents.filter((x) => ['wh', 'kwh', 'mwh'].includes(unitOf(x))).sort();
        const rooms = Array.from(new Set(this._dvDevs().map((d) => d.room).filter(Boolean)));
        const catSel = `<select data-dvf="category">${groups.map((g) => `<optgroup label="${dvEsc(g)}">${cats.filter((c) => c.group === g).map((c) => `<option value="${dvEsc(c.key)}" ${e.category === c.key ? 'selected' : ''}>${dvEsc(c.icon)} ${dvEsc(c.name)}</option>`).join('')}</optgroup>`).join('')}</select>`;
        const chk = (k, l) => `<label class="chk"><input type="checkbox" data-dvf="${k}" ${e[k] ? 'checked' : ''}/> ${l}</label>`;
        const num = (k, l, step) => `<label>${l}<input type="number" step="${step}" data-dvf="${k}" value="${dvEsc(e[k])}"/></label>`;
        return `<div class="section"><div class="section-title">${e._new ? '➕ Nowe urządzenie' : '✏️ Edycja urządzenia'}</div><div class="chart-card full" style="padding:14px 16px;">
          <div class="dv-form">
            <label>Nazwa<input type="text" maxlength="40" data-dvf="name" value="${dvEsc(e.name)}"/></label>
            <label>Kategoria${catSel}</label>
            <label>Ikona (emoji)<input type="text" maxlength="4" data-dvf="icon" value="${dvEsc(e.icon)}"/></label>
            <label>Pomieszczenie (opcjonalnie)<input type="text" maxlength="30" list="dvRooms" data-dvf="room" value="${dvEsc(e.room)}"/><datalist id="dvRooms">${rooms.map((r) => `<option value="${dvEsc(r)}">`).join('')}</datalist></label>
            <label>Encja mocy (W)<input type="text" list="dvPw" data-dvf="power_eid" placeholder="sensor.pralka_moc" value="${dvEsc(e.power_eid)}"/><datalist id="dvPw">${pw.map((x) => `<option value="${dvEsc(x)}">`).join('')}</datalist></label>
            <label>Encja energii (kWh)<input type="text" list="dvEn" data-dvf="energy_eid" placeholder="sensor.pralka_energia" value="${dvEsc(e.energy_eid)}"/><datalist id="dvEn">${en.map((x) => `<option value="${dvEsc(x)}">`).join('')}</datalist></label>
            <div class="dv-note full" style="margin:0;">Wystarczy jedna encja. Sama moc → integracja policzy kWh; sam licznik kWh → moc szacowana z przyrostów. Najlepiej obie.</div>
            <label>Od czego zależy zużycie (prognoza)<select data-dvf="driver">
              <option value="temp" ${e.driver === 'temp' ? 'selected' : ''}>temperatura (ogrzewanie, klimatyzacja)</option>
              <option value="weekday" ${e.driver === 'weekday' ? 'selected' : ''}>dzień tygodnia (pranie, auto)</option>
              <option value="flat" ${e.driver === 'flat' ? 'selected' : ''}>stałe (lodówka, serwer)</option></select></label>
            <div></div>
            ${chk('flexible', 'Elastyczne — może poczekać na tanią godzinę lub nadwyżkę PV')}
            ${chk('cycles', 'Pracuje cyklami (pralka, zmywarka…)')}
            ${chk('standby', 'Licz pobór w czuwaniu (noc 1:00–5:00)')}
            <div></div>
            ${num('cycle_w', 'Próg pracy (W)', 1)}${num('cycle_end_min', 'Koniec cyklu po (min poniżej progu)', 1)}
            ${num('max_run_h', 'Ostrzeż po ciągłej pracy (h, 0 = nie)', 0.5)}<div></div>
            ${chk('notify_cycle', 'Powiadom o końcu cyklu')}${chk('notify_anomaly', 'Powiadom o nietypowej pracy')}${chk('notify_hint', 'Podpowiadaj „uruchom teraz”')}
          </div>
          <div class="dv-note">Powiadomienia działają, gdy dany rodzaj jest włączony też w Diagnostyce → Powiadomienia (grupa „Urządzenia”).</div>
          <div class="dv-bar" style="margin-top:12px;"><button class="dv-btn" data-dv="save">💾 Zapisz</button><button class="dv-btn sec" data-dv="cancel">Anuluj</button>
            ${e._new ? '' : '<span style="flex:1;"></span><button class="dv-btn bad" data-dv="del">🗑 Usuń</button>'}<span class="dv-note" id="dvMsg" style="margin:0;color:var(--red);"></span></div></div></div>`;
      },
      _dvDefaultsFor(cat, base) {
        const c = this._dvCat(cat) || this._dvCat('other') || { name: 'Urządzenie', icon: '🔌', default: {} };
        return Object.assign({}, base || {}, { category: cat, icon: c.icon, name: (base && base.name && !base._autoName) ? base.name : c.name, _autoName: !(base && base.name && !base._autoName) }, c.default || {},
          { notify_cycle: !!(c.default || {}).cycles, notify_anomaly: true, notify_hint: !!(c.default || {}).flexible });
      },
      _dvClick(ev) {
        const t = ev.target && ev.target.closest ? ev.target.closest('[data-dv]') : null; if (!t) return;
        const s = this._dvS(); const a = t.dataset.dv;
        if (a === 'range') { s.range = t.dataset.r; this._dvRender(); }
        else if (a === 'sel') { if (ev.target.closest('[data-dv="edit"]')) return; s.sel = s.sel === t.dataset.id ? 'all' : t.dataset.id; this._dvRender(); }
        else if (a === 'reload') { s.fetchedAt = 0; s.statsKey = ''; this._dvLoad(); }
        else if (a === 'add') { s.edit = Object.assign(this._dvDefaultsFor('other', {}), { _new: true, room: '', power_eid: '', energy_eid: '' }); this._dvRender(); }
        else if (a === 'edit') { const d = this._dvDevs().find((x) => x.id === t.dataset.id); if (d) { s.edit = Object.assign({}, d); this._dvRender(); } }
        else if (a === 'cancel') { s.edit = null; this._dvRender(); }
        else if (a === 'save') this._dvSave();
        else if (a === 'del') this._dvDelete();
        else if (a === 'csv') this._dvCsv();
        else if (a === 'disc') this._dvDiscover();
        else if (a === 'disc-cancel') { s.disc = null; this._dvRender(); }
        else if (a === 'disc-add') this._dvDiscAdd();
        else if (a === 'disc-all' || a === 'disc-none') { this._dvDiscCollect(); const on = a === 'disc-all'; Object.values((s.disc && s.disc.picks) || {}).forEach((p) => { p.on = on; }); this._dvRender(); }
      },
      _dvChange(ev) {
        const t = ev.target; const s = this._dvS();
        if (t.dataset && t.dataset.dv === 'filter') { s.sel = t.value; this._dvRender(); return; }
        if (t.dataset && t.dataset.dvd && s.disc) {
          const p = (s.disc.picks || {})[t.dataset.k]; if (!p) return;
          if (t.type === 'checkbox') p.on = !!t.checked; else p[t.dataset.dvd] = String(t.value).trim();
          if (t.dataset.dvd === 'category' || t.type === 'checkbox') { this._dvDiscCollect(); this._dvRender(); }
          return;
        }
        if (!s.edit || !t.dataset || !t.dataset.dvf) return;
        const f = t.dataset.dvf;
        if (f === 'category') { s.edit = Object.assign(this._dvDefaultsFor(t.value, s.edit), { id: s.edit.id, _new: s.edit._new, room: s.edit.room, power_eid: s.edit.power_eid, energy_eid: s.edit.energy_eid }); this._dvRender(); return; }
        if (t.type === 'checkbox') s.edit[f] = !!t.checked;
        else if (t.type === 'number') { const v = parseFloat(String(t.value).replace(',', '.')); if (isFinite(v)) s.edit[f] = v; }
        else { s.edit[f] = String(t.value).trim(); if (f === 'name') s.edit._autoName = false; }
      },
      _dvCollect() {
        // pola tekstowe mogą nie wywołać „change” przed kliknięciem Zapisz — czytamy je z formularza
        const s = this._dvS(); const root = this._el('devRoot'); if (!root || !s.edit) return;
        root.querySelectorAll('[data-dvf]').forEach((el) => {
          const f = el.dataset.dvf; if (f === 'category') return;
          if (el.type === 'checkbox') s.edit[f] = !!el.checked;
          else if (el.type === 'number') { const v = parseFloat(String(el.value).replace(',', '.')); if (isFinite(v)) s.edit[f] = v; }
          else s.edit[f] = String(el.value).trim();
        });
      },
      async _dvPersist(list, okMsg) {
        const s = this._dvS();
        const clean = list.map((d) => { const o = Object.assign({}, d); delete o._new; delete o._autoName; return o; });
        const r = dvResp(await dvCall(this, 'devices_set', { devices: clean })) || {};
        s.edit = null; s.msg = okMsg + (r.dropped ? ` (pominięto ${r.dropped} bez encji)` : '');
        s.fetchedAt = 0; s.statsKey = ''; await this._dvLoad();
      },
      async _dvSave() {
        const s = this._dvS(); this._dvCollect(); const e = s.edit; const msg = this._el('dvMsg');
        const bad = (x) => x && !/^sensor\.[a-z0-9_]+$/.test(x);
        if (!e.power_eid && !e.energy_eid) { if (msg) msg.textContent = 'Wskaż encję mocy (W) albo energii (kWh).'; return; }
        if (bad(e.power_eid) || bad(e.energy_eid)) { if (msg) msg.textContent = 'Encja musi mieć postać sensor.nazwa_encji.'; return; }
        if (!String(e.name || '').trim()) { if (msg) msg.textContent = 'Podaj nazwę.'; return; }
        const list = this._dvDevs().filter((d) => d.id !== e.id);
        if (e._new) list.push(e); else { const i = this._dvDevs().findIndex((d) => d.id === e.id); list.splice(i < 0 ? list.length : i, 0, e); }
        try { await this._dvPersist(list, '✅ Zapisano'); } catch (err) { if (msg) msg.textContent = '❌ ' + dvErr(err); }
      },
      async _dvDelete() {
        const s = this._dvS(); const e = s.edit; if (!e || e._new) return;
        if (!confirm(`Usunąć „${e.name}”? Zebrane dane tego urządzenia zostaną skasowane.`)) return;
        try { await this._dvPersist(this._dvDevs().filter((d) => d.id !== e.id), '🗑 Usunięto'); } catch (err) { const m = this._el('dvMsg'); if (m) m.textContent = '❌ ' + dvErr(err); }
      },
      // ------------------------------------------------------------ wyszukiwanie urządzeń (liczniki kWh w HA)
      async _dvDiscover() {
        const s = this._dvS();
        s.disc = { loading: true, err: '', data: null, picks: {}, msg: '' }; this._dvRender();
        try {
          const d = dvResp(await dvCall(this, 'devices_discover', {})) || {};
          const picks = {};
          (d.candidates || []).forEach((c) => {
            picks[c.key] = { on: !!c.energy_dashboard && !c.unavailable, name: c.name, category: c.category || 'other', room: c.room || '', energy_eid: c.energy_eid || '', power_eid: c.power_eid || '' };
          });
          if (s.disc) { s.disc.data = d; s.disc.picks = picks; }
        } catch (e) { if (s.disc) s.disc.err = dvErr(e); }
        if (s.disc) s.disc.loading = false;
        this._dvRender();
      },
      _dvDiscCollect() {
        const s = this._dvS(); const root = this._el('devRoot'); if (!root || !s.disc) return;
        root.querySelectorAll('[data-dvd]').forEach((el) => {
          const p = (s.disc.picks || {})[el.dataset.k]; if (!p) return;
          if (el.type === 'checkbox') p.on = !!el.checked; else p[el.dataset.dvd] = String(el.value).trim();
        });
      },
      _dvDiscView() {
        const s = this._dvS(); const ds = s.disc;
        const wrap = (body) => `<div class="section"><div class="section-title">🔍 Wyszukane urządzenia z licznikiem kWh</div><div class="chart-card full" style="padding:14px 16px;">${body}</div></div>`;
        if (ds.loading) return wrap('<div class="chart-empty">Szukam liczników energii w Home Assistant…</div>');
        if (ds.err) return wrap(`<div class="chart-empty" style="color:var(--red);">Nie udało się wyszukać: ${dvEsc(ds.err)}</div><div class="dv-note">Wymaga integracji 0.8.4 lub nowszej i konta administratora.</div><div class="dv-bar" style="margin-top:10px;"><button class="dv-btn sec" data-dv="disc">Spróbuj ponownie</button><button class="dv-btn sec" data-dv="disc-cancel">Wróć</button></div>`);
        const d = ds.data || {}; const list = d.candidates || []; const sk = d.skipped || {};
        const cats = (s.data && s.data.categories) || []; const groups = (s.data && s.data.groups) || [];
        const free = d.free_slots == null ? 40 : d.free_slots;
        const picked = list.filter((c) => (ds.picks[c.key] || {}).on).length;
        const skipNote = [sk.home ? `${sk.home} liczników domu (sieć, PV, bateria, encje z konfiguracji BMS)` : '', sk.bms ? `${sk.bms} encji BMS / falownika` : '',
          sk.helper ? `${sk.helper} pomocniczych (Utility Meter, prognozy, inne falowniki)` : '', sk.added ? `${sk.added} już dodanych` : ''].filter(Boolean).join(', ');
        if (!list.length) {
          return wrap(`<div class="chart-empty">Nie znalazłem nowych urządzeń z licznikiem kWh.</div>${skipNote ? `<div class="dv-note">Pominięto: ${dvEsc(skipNote)}.</div>` : ''}
            <div class="dv-note">Urządzenie bez licznika kWh (tylko moc w W) dodasz przyciskiem „Dodaj urządzenie”.</div>
            <div class="dv-bar" style="margin-top:10px;"><button class="dv-btn sec" data-dv="disc-cancel">Wróć</button></div>`);
        }
        const catSel = (k, val) => `<select data-dvd="category" data-k="${dvEsc(k)}">${groups.map((g) => `<optgroup label="${dvEsc(g)}">${cats.filter((c) => c.group === g).map((c) => `<option value="${dvEsc(c.key)}" ${val === c.key ? 'selected' : ''}>${dvEsc(c.icon)} ${dvEsc(c.name)}</option>`).join('')}</optgroup>`).join('')}</select>`;
        const optVal = (o) => { const v = dvNum(o.value); return v === null ? '' : ` — ${dvFmt(v, (o.unit === 'wh' || o.unit === 'w') ? 0 : 1, ' ' + (o.unit === 'kw' ? 'kW' : o.unit === 'w' ? 'W' : o.unit === 'wh' ? 'Wh' : o.unit === 'mwh' ? 'MWh' : 'kWh'))}`; };
        const rows = list.map((c) => {
          const p = ds.picks[c.key] || {}; const k = dvEsc(c.key);
          const en = (c.energy_options || []).length > 1
            ? `<select data-dvd="energy_eid" data-k="${k}">${c.energy_options.map((o) => `<option value="${dvEsc(o.eid)}" ${p.energy_eid === o.eid ? 'selected' : ''}>${dvEsc(o.eid)}${dvEsc(optVal(o))}${o.stats ? '' : ' (bez statystyk)'}</option>`).join('')}</select>`
            : `<div style="font-size:12px;color:var(--text2);word-break:break-all;">${dvEsc(c.energy_eid)}${dvEsc(optVal((c.energy_options || [])[0] || {}))}</div>`;
          const pw = `<select data-dvd="power_eid" data-k="${k}"><option value="" ${p.power_eid ? '' : 'selected'}>— bez encji mocy (moc z przyrostów kWh) —</option>${(c.power_options || []).map((o) => `<option value="${dvEsc(o.eid)}" ${p.power_eid === o.eid ? 'selected' : ''}>${dvEsc(o.eid)}${dvEsc(optVal(o))}</option>`).join('')}</select>`;
          const badges = [c.energy_dashboard ? '<span class="dv-run" style="background:rgba(10,132,255,.18);color:var(--accent,#0a84ff);">panel Energia</span>' : '',
            c.unavailable ? '<span class="dv-run" style="background:rgba(255,69,58,.18);color:var(--red);">niedostępne</span>' : '',
            c.stats ? '' : '<span class="dv-run" style="background:rgba(255,159,10,.18);color:var(--orange,#ff9f0a);" title="Encja bez state_class — historia sprzed dodania nie zostanie uzupełniona">bez historii</span>',
            c.integration ? `<span class="dv-note" style="margin:0;">${dvEsc(c.integration)}</span>` : ''].filter(Boolean).join(' ');
          return `<div style="border-bottom:1px solid var(--line);padding:10px 0;${p.on ? '' : 'opacity:.75;'}">
            <label class="chk" style="display:flex;gap:8px;align-items:center;font-size:13px;font-weight:600;color:var(--text);"><input type="checkbox" data-dvd="on" data-k="${k}" ${p.on ? 'checked' : ''}/> ${dvEsc(c.name)}
              <span style="font-weight:400;color:var(--muted);font-size:12px;">${c.power_w == null ? '' : '· teraz ' + dvFmt(c.power_w, 0, ' W')}</span></label>
            <div style="margin:4px 0 0 26px;display:flex;gap:6px;flex-wrap:wrap;align-items:center;">${badges}</div>
            ${p.on ? `<div class="dv-form" style="margin:8px 0 0 26px;">
              <label>Nazwa<input type="text" maxlength="40" data-dvd="name" data-k="${k}" value="${dvEsc(p.name)}"/></label>
              <label>Kategoria${catSel(c.key, p.category)}</label>
              <label>Pomieszczenie<input type="text" maxlength="30" data-dvd="room" data-k="${k}" value="${dvEsc(p.room)}"/></label>
              <label>Encja mocy (W)${pw}</label>
              <label class="full">Licznik energii (kWh)${en}</label></div>` : ''}</div>`;
        }).join('');
        const over = picked > free;
        return wrap(`<div class="dv-note" style="margin:0 0 6px;">Znaleziono ${list.length}${d.total > list.length ? ` (pokazuję ${list.length} z ${d.total})` : ''}. Zaznacz urządzenia, sprawdź kategorię i kliknij „Dodaj zaznaczone”. Ustawienia (próg pracy, cykle, powiadomienia) przyjmą domyślne dla kategorii — zmienisz je później w „Edytuj”.</div>
          <div class="dv-bar"><button class="dv-pill" data-dv="disc-all">zaznacz wszystkie</button><button class="dv-pill" data-dv="disc-none">odznacz wszystkie</button></div>
          ${rows}
          ${skipNote ? `<div class="dv-note">Pominięto: ${dvEsc(skipNote)}.</div>` : ''}
          <div class="dv-bar" style="margin-top:12px;"><button class="dv-btn" data-dv="disc-add" ${picked && !over ? '' : 'disabled'}>➕ Dodaj zaznaczone (${picked})</button><button class="dv-btn sec" data-dv="disc-cancel">Anuluj</button>
            <span class="dv-note" id="dvMsg" style="margin:0;color:${over ? 'var(--red)' : 'var(--muted)'};">${over ? `Za dużo — wolnych miejsc: ${free}.` : `Wolnych miejsc: ${free}.`}</span></div>`);
      },
      async _dvDiscAdd() {
        const s = this._dvS(); if (!s.disc) return; this._dvDiscCollect();
        const msg = this._el('dvMsg'); const list = (s.disc.data && s.disc.data.candidates) || [];
        const add = [];
        for (const c of list) {
          const p = s.disc.picks[c.key]; if (!p || !p.on) continue;
          if (!String(p.name || '').trim()) { if (msg) msg.textContent = 'Każde zaznaczone urządzenie musi mieć nazwę.'; return; }
          const dev = this._dvDefaultsFor(p.category || 'other', { name: p.name, _autoName: false });
          add.push(Object.assign(dev, { name: String(p.name).trim().slice(0, 40), room: String(p.room || '').trim().slice(0, 30), energy_eid: p.energy_eid || c.energy_eid, power_eid: p.power_eid || '' }));
        }
        if (!add.length) return;
        const free = (s.disc.data && s.disc.data.free_slots != null) ? s.disc.data.free_slots : 40;
        if (add.length > free) { if (msg) msg.textContent = `Za dużo — wolnych miejsc: ${free}.`; return; }
        try { s.disc = null; await this._dvPersist(this._dvDevs().concat(add), `✅ Dodano ${add.length} ${add.length === 1 ? 'urządzenie' : (add.length < 5 ? 'urządzenia' : 'urządzeń')}`); }
        catch (err) { s.msg = '❌ ' + dvErr(err); this._dvRender(); }
      },
      _dvCsv() {
        const s = this._dvS(); const devs = this._dvSelected();
        const days = { '1d': 1, '7d': 7, '30d': 30, '3m': 91, '6m': 182, '12m': 365 }[s.range] || 30;
        const today = new Date();
        const keys = Array.from({ length: days }, (_, i) => { const d = new Date(today); d.setDate(d.getDate() - (days - 1 - i)); return dk(d); });
        const q = (v) => `"${String(v).replace(/"/g, '""')}"`;
        const lines = [['data', ...devs.map((d) => q(d.name + ' kWh')), ...devs.map((d) => q(d.name + ' zł'))].join(';')];
        keys.forEach((k) => {
          lines.push([k, ...devs.map((d) => String(Number(this._dvDaily(d.id)[k] || 0).toFixed(3)).replace('.', ',')),
            ...devs.map((d) => String(Number(((((s.data.history || {})[d.id] || {}).cost) || {})[k] || 0).toFixed(2)).replace('.', ','))].join(';'));
        });
        try {
          const blob = new Blob(['﻿' + lines.join('\n')], { type: 'text/csv;charset=utf-8' });
          const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `bms-urzadzenia-${s.range}-${dk(today)}.csv`;
          document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
          s.msg = `⬇ Pobrano CSV (${keys.length} dni)`; const m = this.shadowRoot && this.shadowRoot.querySelector('#devRoot .dv-bar .dv-note'); if (m) m.textContent = s.msg;
        } catch (e) { s.msg = '❌ ' + dvErr(e); }
      },
    });
  };
  install.contract = 1;
  install.version = '0.8.4';
  window.__bmsDevicesInstall = install;
})();
