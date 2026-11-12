/**
 * EMS Centrum Energii — moduł dodatków (plan 24 h, raport, zdrowie baterii, kreator)
 * Ładowany na żądanie przez bms-panel.js (kontrakt modułu: 1). Nie dodawaj tego pliku do zasobów dashboardu ręcznie.
 */
(function () {
  'use strict';
  const install = function (BmsPanel, shared) {
    const TC = shared.TC;
    const BMS_INFO = { card: shared.version || '', url: shared.urlVersion || '' };
    // =====================================================================
    //  DODATKI: wspólne narzędzia, style i rysowanie (plan 24 h, raport, zdrowie baterii, kreator instalacji)
    //  Dane liczy integracja (sensory plan_curve / monthly_report / battery_health, usługi health_check,
    //  monthly_report, get_plan) — ten moduł tylko je wyświetla, niczego nie zapisuje do falownika.
    // =====================================================================
    const exEsc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const exNum = (v) => (v === null || v === undefined || v === '' || isNaN(Number(v))) ? null : Number(v);
    const exFmt = (v, d, unit) => { const n = exNum(v); return n === null ? '—' : n.toFixed(d == null ? 1 : d).replace('.', ',') + (unit || ''); };
    const exMoney = (v) => { const n = exNum(v); return n === null ? '—' : (n >= 0 ? '+' : '−') + Math.abs(n).toFixed(2).replace('.', ',') + ' zł'; };
    const exErr = (e) => String((e && (e.message || e.code)) || e || 'błąd').slice(0, 200);
    const exCall = (card, service, data) => card._hass.callWS({ type: 'call_service', domain: 'bms_komp_dec', service, service_data: data || {}, return_response: true });
    const exResp = (res) => (res && res.response !== undefined ? res.response : res);
    const exHH = (n) => String(((n % 24) + 24) % 24).padStart(2, '0');

    const EX_CSS = `
      .ex-sum { display:flex; flex-wrap:wrap; gap:8px; margin:0 0 10px; }
      .ex-chip { padding:4px 10px; border-radius:999px; font-size:11px; background:var(--surface); color:var(--text2); }
      .ex-chip.warn { background:rgba(255,159,10,.16); color:var(--orange); }
      .ex-chip.bad { background:rgba(255,69,58,.16); color:var(--red); }
      .ex-chip.ok { background:rgba(48,209,88,.16); color:var(--green); }
      .ex-plan { position:relative; }
      .ex-plan canvas { width:100%; height:250px; display:block; touch-action:pan-y; }
      .ex-tip { position:absolute; z-index:3; pointer-events:none; background:var(--card); color:var(--text); border:1px solid var(--line); border-radius:10px; padding:8px 10px; font-size:11px; line-height:1.5; box-shadow:0 6px 18px rgba(0,0,0,.35); white-space:nowrap; }
      .ex-leg { display:flex; flex-wrap:wrap; gap:6px 14px; font-size:11px; color:var(--muted); margin-top:8px; }
      .ex-leg i { display:inline-block; width:12px; height:8px; border-radius:2px; margin-right:5px; vertical-align:middle; }
      .ex-leg i.line { height:2px; border-radius:0; }
      .ex-leg i.dash { height:0; border-top:2px dashed var(--red); background:none; }
      .ex-lines { margin-top:10px; font-size:12px; color:var(--text2); line-height:1.6; }
      .ex-lines div { padding:2px 0; }
      .ex-prop { display:flex; justify-content:space-between; gap:10px; padding:5px 0; border-bottom:1px solid var(--line); font-size:12px; }
      .ex-prop:last-child { border-bottom:none; }
      .ex-prop .skip { color:var(--muted); }
      .ex-tiles { display:flex; gap:10px; flex-wrap:wrap; }
      .ex-tile { flex:1 1 130px; min-width:120px; background:var(--surface); border-radius:14px; padding:12px 14px; }
      .ex-tile .l { font-size:11px; color:var(--muted); text-transform:uppercase; letter-spacing:.5px; }
      .ex-tile .v { font-size:20px; font-weight:700; margin-top:4px; }
      .ex-tile .s { font-size:11px; color:var(--muted); margin-top:2px; }
      .ex-nav { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:12px; }
      .ex-nav b { font-size:15px; }
      .ex-bars { display:flex; align-items:center; gap:2px; height:80px; margin-top:12px; }
      .ex-note { font-size:11px; color:var(--muted); margin-top:10px; line-height:1.5; }
      .ex-chk { display:flex; gap:10px; padding:8px 0; border-bottom:1px solid var(--line); font-size:12px; line-height:1.45; }
      .ex-chk:last-child { border-bottom:none; }
      .ex-chk .ic { flex:none; width:18px; text-align:center; }
      .ex-chk .fix { color:var(--muted); margin-top:2px; }
      .ex-cmd { background:var(--surface); border-radius:12px; padding:8px 12px; margin-top:8px; font-size:12px; }
      .ex-cmd summary { cursor:pointer; list-style:none; display:flex; gap:8px; align-items:center; }
      .ex-cmd summary::-webkit-details-marker { display:none; }
      .ex-cmd code { font-size:11px; color:var(--muted); word-break:break-all; }
      .ex-cmd .st { padding:3px 0 3px 26px; }
    `;

    Object.assign(BmsPanel.prototype, {
      _exS() {
        if (!this._ex) this._ex = { ins: { data: null, at: 0, loading: false, err: '', period: 'last30' }, planOverride: null, rep: { year: null, month: null, data: null, loading: false, err: '' }, wiz: { state: 'idle', data: null, err: '' }, keys: {} };
        return this._ex;
      },
      _exCss() {
        const root = this.shadowRoot;
        if (!root || root.getElementById('exStyle')) return;
        const st = document.createElement('style'); st.id = 'exStyle'; st.textContent = EX_CSS; root.appendChild(st);
      },
      // wywoływane co ~10 s oraz po zmianie zakładki: każdy fragment sam pilnuje, czy jest widoczny i czy dane się zmieniły
      _exRender() {
        if (!this._hass) return;
        this._exCss();
        this._safe(() => this._exPlan());
        this._safe(() => this._exLog());
        this._safe(() => this._exWiz());
      },
      _exLog() {
        if (this._activeTab !== 'log') return;
        this._exInsights();
        this._exReport();
        this._exHealth();
      },
    });

    // =====================================================================
    //  PLAN 24 h — przewidywana krzywa SOC z zaplanowanym ładowaniem z sieci i sprzedażą (liczy integracja)
    // =====================================================================
    const exRanges = (flags) => {
      const out = []; let st = -1;
      for (let i = 0; i <= flags.length; i++) {
        const on = i < flags.length && !!flags[i];
        if (on && st < 0) st = i;
        if (!on && st >= 0) { out.push([st, i]); st = -1; }
      }
      return out;
    };
    const exStartHour = (c) => {
      const m = /T(\d\d):/.exec(String(c.start || ''));
      if (m) return parseInt(m[1], 10);
      const d = new Date(c.start); return isNaN(d) ? 0 : d.getHours();
    };

    Object.assign(BmsPanel.prototype, {
      _exPlanData() {
        const s = this._exS();
        const st = this._hass.states[this._eid('sensor', 'plan_curve')];
        if (!st) return { missing: true };
        const a = st.attributes || {};
        let plan = { mode: a.mode, generated_at: a.generated_at, error: a.error, curve: a.curve, proposals: a.proposals, assumptions: a.assumptions, state: st.state };
        const ov = s.planOverride;
        if (ov && ov.generated_at && (!plan.generated_at || String(ov.generated_at) > String(plan.generated_at))) plan = Object.assign({ state: '' }, ov);
        return { plan };
      },

      _exPlan() {
        const box = this._el('exPlanBox');
        if (!box || this._activeTab !== 'ems') return;
        const s = this._exS();
        if (!box.dataset.exBound) {
          box.dataset.exBound = '1';
          box.addEventListener('click', (ev) => {
            const b = ev.target && ev.target.closest ? ev.target.closest('[data-ex="plan-refresh"]') : null;
            if (b) this._exPlanRefresh();
          });
        }
        const d = this._exPlanData();
        const msg = (t, bad) => {
          const k = 'msg:' + t; if (s.keys.plan === k) return; s.keys.plan = k;
          box.innerHTML = `<div class="chart-empty"${bad ? ' style="color:var(--red);"' : ''}>${t}</div>`;
        };
        if (d.missing) { msg('Brak sensora planu — zaktualizuj integrację do wersji z planem 24 h i zrestartuj Home Assistant.', true); return; }
        const p = d.plan, c = p.curve;
        if (p.error) { msg('Plan niedostępny: ' + exEsc(p.error), true); return; }
        if (p.state === 'brak' && !c) { msg('Plan jeszcze nie został policzony — pojawi się w ciągu kilku minut po starcie integracji.'); return; }
        if (!c || !Array.isArray(c.soc) || !c.soc.length) { msg('Plan niedostępny — brak danych (SOC, prognoz PV lub zużycia).', true); return; }

        const key = JSON.stringify([p.generated_at, p.mode, Math.round(box.clientWidth), TC('text'), c.soc.length, c.start]);
        const cv0 = box.querySelector('canvas');
        if (s.keys.plan === key && cv0) { if (s.hover == null) return; }
        else {
          s.keys.plan = key; s.hover = null;
          box.innerHTML = this._exPlanHtml(p, c);
          const cv = box.querySelector('canvas');
          const move = (ev) => {
            const r = cv.getBoundingClientRect(); const n = c.soc.length;
            const padL = this._exPlanPad().l, padR = this._exPlanPad().r;
            const x = ev.clientX - r.left;
            const i = Math.floor((x - padL) / Math.max(1, (r.width - padL - padR) / n));
            s.hover = (i >= 0 && i < n) ? i : null;
            this._exPlanPaint(box, c);
          };
          cv.addEventListener('pointermove', move);
          cv.addEventListener('pointerdown', move);
          cv.addEventListener('pointerleave', () => { s.hover = null; this._exPlanPaint(box, c); });
        }
        this._exPlanPaint(box, c);
      },

      _exPlanPad() { return { l: 34, r: 8, t: 10 }; },

      _exPlanHtml(p, c) {
        const n = c.soc.length, h0 = exStartHour(c);
        const hm = (i) => exHH(h0 + i) + ':00';
        const gen = p.generated_at ? new Date(p.generated_at) : null;
        const genTxt = gen && !isNaN(gen) ? gen.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' }) : '—';
        const chips = [`<span class="ex-chip">Policzono ${exEsc(genTxt)}</span>`, `<span class="ex-chip">SOC teraz ${exFmt(c.soc_now, 0, '%')}</span>`];
        if (p.mode === 'storm') chips.push('<span class="ex-chip warn">⛈ tryb burzowy — cel 100%, bez sprzedaży</span>');
        else if (p.mode === 'vacation') chips.push('<span class="ex-chip">🏖 tryb urlopowy</span>');

        const soc = c.soc.map(Number), fl = (c.floor || []).map(Number);
        let mi = 0; soc.forEach((v, i) => { if (v < soc[mi]) mi = i; });
        const lines = [];
        const as = p.assumptions;
        if (as && typeof as === 'object') {
          const kwh = (v) => (exNum(v) === null ? '?' : exFmt(v, 1)) + ' kWh';
          const pvSrc = as.pv_source ? ` (${exEsc(as.pv_source)})` : '';
          const parts = [`zużycie do północy ~<b>${kwh(as.load_rest_today_kwh)}</b> (${/^tempo dnia/.test(String(as.load_today_source || '')) ? 'z dzisiejszego zużycia' : 'z profilu'})`];
          if (as.load_live && exNum(as.load_live.live_kw) !== null) parts.push(`teraz dom bierze <b>${exFmt(as.load_live.live_kw, 1)} kW</b> (oczekiwano ${exFmt(as.load_live.expected_kw, 1)}) — najbliższe godziny skorygowane`);
          if (exNum(as.load_tomorrow_kwh) !== null) parts.push(`jutro <b>${kwh(as.load_tomorrow_kwh)}</b>`);
          if (exNum(as.pv_tomorrow_kwh) !== null) parts.push(`PV jutro <b>${kwh(as.pv_tomorrow_kwh)}</b>${pvSrc}`);
          const pf = exNum(as.pv_factor);
          if (pf !== null && Math.abs(pf - 1) > 0.004) parts.push(`prognoza PV × <b>${exFmt(pf, 2)}</b> (korekta z historii)`);
          if (exNum(as.wear_cost) > 0) parts.push(`zużycie baterii <b>${exFmt(as.wear_cost, 2)} zł/kWh</b>`);
          lines.push(`<div>📋 Plan zakłada: ${parts.join(' · ')}.</div>`);
          const acc = (this._hass.states[this._eid('sensor', 'monitor_status')] || {}).attributes;
          const ac = acc && acc.accuracy;
          const accTxt = (st, what) => {
            if (!st || exNum(st.mae_pct) === null) return null;
            const b = exNum(st.bias_pct);
            return `${what} ±<b>${exFmt(st.mae_pct, 0)}%</b>${b !== null && Math.abs(b) >= 3 ? ` (zwykle ${b > 0 ? 'zawyżona' : 'zaniżona'} o ${exFmt(Math.abs(b), 0)}%)` : ''}`;
          };
          const accParts = ac ? [accTxt(ac.load, 'zużycie'), accTxt(ac.pv, 'PV')].filter(Boolean) : [];
          if (accParts.length) lines.push(`<div>🎯 Trafność prognoz (ostatnie dni: ${exFmt(Math.max((ac.load || {}).n || 0, (ac.pv || {}).n || 0), 0)}): ${accParts.join(' · ')}.</div>`);
          if (!as.pv_hourly_tomorrow) lines.push(`<div style="color:var(--red);">⚠ Brak godzinowej prognozy PV na jutro — plan liczy tak, jakby jutro nie było słońca. Wskaż encję prognozy Solcast albo Forecast.Solar w konfiguracji.</div>`);
        }
        const lowTxt = `Najniższy SOC w planie: <b>${exFmt(soc[mi], 0, '%')}</b> o ${hm(mi + 1)}`;
        const nearFloor = fl[mi] > 0 && soc[mi] <= fl[mi] + 2;
        lines.push(`<div>${nearFloor ? '⚠ ' : ''}${lowTxt}${nearFloor ? ` — blisko progu odcięcia falownika (${exFmt(fl[mi], 0, '%')}): bateria przestaje zasilać dom, falownik pobiera prąd z sieci.` : ` (próg falownika ${exFmt(fl[mi], 0, '%')}).`}</div>`);
        const gr = exRanges(c.grid || []);
        if (gr.length) {
          lines.push('<div>🔌 Ładowanie z sieci: ' + gr.map((r) => {
            const tg = (c.target || []).slice(r[0], r[1]).map(Number).filter((x) => isFinite(x) && x > 0);
            return `<b>${hm(r[0])}–${hm(r[1])}</b>${tg.length ? ` (do ${Math.round(Math.max(...tg))}%)` : ''}`;
          }).join(', ') + '</div>');
        } else lines.push('<div>🔌 Ładowanie z sieci: <b>nie jest potrzebne</b> w tym horyzoncie.</div>');
        const sr = exRanges(c.sale || []);
        if (p.mode === 'storm') lines.push('<div>💰 Sprzedaż z baterii: <b>wyłączona</b> (tryb burzowy).</div>');
        else if (sr.length) lines.push('<div>💰 Sprzedaż z baterii: ' + sr.map((r) => {
          const w = ((as && as.sale_windows) || []).find((x) => `${String(x.start).padStart(2, '0')}:00` === hm(r[0]) && exNum(x.power_w) > 0);
          return `<b>${hm(r[0])}–${hm(r[1])}</b>${w ? ` (moc obniżona do ${exFmt(exNum(w.power_w) / 1000, 1)} kW — sprzedaję tylko zapas energii)` : ''}`;
        }).join(', ') + '</div>');
        else {
          // przyczyna z planera (zestaw 1 i 2 mogą mieć różne); bez niej — stary, ogólny opis
          const why = ['bateria_sprzedaz_start', 'bateria_sprzedaz_start_2'].map((k) => (p.proposals || {})[k])
            .filter((x) => x && x.skip && x.reason).map((x) => String(x.reason).replace(/^Pomiń\s*[—-]\s*/, '').trim());
          const uniq = why.filter((x, i) => why.indexOf(x) === i);
          lines.push(uniq.length
            ? `<div>💰 Sprzedaż z baterii: <b>nie planuję</b> — ${uniq.map((x) => exEsc(x.charAt(0).toLowerCase() + x.slice(1))).join('<br>oraz ')}</div>`
            : '<div>💰 Sprzedaż z baterii: <b>brak opłacalnych godzin</b> (lub brak pełnych cen RCE).</div>');
        }
        const sell = (c.sell || []).map(exNum);
        const buy = (c.buy || []).map(exNum);
        if (sell.some((v) => v !== null)) {
          let bi = -1; sell.forEach((v, i) => { if (v !== null && (bi < 0 || v > sell[bi])) bi = i; });
          lines.push(`<div>📈 Najwyższa cena sprzedaży: <b>${exFmt(sell[bi], 2)} zł/kWh</b> o ${hm(bi)}.</div>`);
        } else lines.push('<div>📈 Brak cen RCE w horyzoncie planu — sprzedaż nie jest planowana.</div>');
        if (buy.some((v) => v !== null)) {
          let ci = -1; buy.forEach((v, i) => { if (v !== null && (ci < 0 || v < buy[ci])) ci = i; });
          lines.push(`<div>🛒 Najtańszy zakup: <b>${exFmt(buy[ci], 2)} zł/kWh</b> o ${hm(ci)}.</div>`);
        }

        const props = Object.keys(p.proposals || {}).map((k) => p.proposals[k]).filter((x) => x && !x.skip && x.proposed != null && String(x.proposed) !== String(x.current));
        const propHtml = props.length
          ? `<div class="ex-note" style="margin-top:12px;">Zmiany w harmonogramie, które plan zakłada:</div>` + props.map((x) => `<div class="ex-prop"><span>${exEsc(x.label || '')}</span><span>${exEsc(x.current || '—')} → <b>${exEsc(x.proposed)}</b></span></div>`).join('')
          : '<div class="ex-note" style="margin-top:12px;">Obecny harmonogram jest zgodny z planem — nie trzeba niczego zmieniać.</div>';
        return `
          <div class="ex-sum">${chips.join('')}</div>
          <div class="ex-plan"><canvas id="exPlanCv" role="img" aria-label="Wykres planu SOC na najbliższe ${n} godzin"></canvas><div class="ex-tip" id="exPlanTip" hidden></div></div>
          <div class="ex-leg">
            <span><i class="line" style="background:#0a84ff;"></i>SOC (plan)</span>
            <span><i class="dash"></i>próg odcięcia falownika</span>
            <span><i style="background:rgba(10,132,255,.35);"></i>ładowanie z sieci</span>
            <span><i style="background:rgba(48,209,88,.4);"></i>sprzedaż z baterii</span>
            <span><i style="background:rgba(255,159,10,.28);"></i>szczyt taryfy</span>
          </div>
          <div class="ex-lines">${lines.join('')}</div>
          ${propHtml}
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:12px;">
            <button type="button" class="btn" data-ex="plan-refresh" style="padding:8px 14px;flex-direction:row;gap:8px;"><span>🔄</span><span class="label">Przelicz teraz</span></button>
            <span id="exPlanMsg" style="font-size:11px;color:var(--muted);"></span>
          </div>
          <div class="ex-note">To prognoza, nie gwarancja: opiera się na prognozie PV, historii zużycia, cenach RCE i taryfie. Pasek pod wykresem pokazuje ceny kupna (górny) i sprzedaży (dolny) dla każdej godziny; dotknij wykresu, aby zobaczyć szczegóły.</div>`;
      },

      async _exPlanRefresh() {
        const msg = this._el('exPlanMsg'); const s = this._exS();
        if (s.planBusy) return;
        s.planBusy = true;
        if (msg) msg.textContent = 'Liczę…';
        try {
          const res = exResp(await exCall(this, 'get_plan', { force: true }));
          const plan = res && res.plan;
          if (plan && (plan.curve || plan.error)) { s.planOverride = plan; s.keys.plan = null; this._exPlan(); const m2 = this._el('exPlanMsg'); if (m2) m2.textContent = 'Plan przeliczony.'; }
          else if (msg) msg.textContent = 'Nie udało się przeliczyć planu (brak danych).';
        } catch (e) { if (msg) msg.textContent = 'Błąd: ' + exErr(e); }
        finally { s.planBusy = false; }
      },

      _exPlanPaint(box, c) {
        const cv = box.querySelector('#exPlanCv'); if (!cv) return;
        const s = this._exS();
        const dpr = window.devicePixelRatio || 1;
        const w = cv.clientWidth || 360, h = cv.clientHeight || 250;
        if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
        const ctx = cv.getContext('2d');
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, w, h);
        const n = c.soc.length, h0 = exStartHour(c);
        const pad = this._exPlanPad();
        const stripH = 11, labH = 16, gap = 5;
        const plotL = pad.l, plotR = w - pad.r, plotT = pad.t;
        const plotB = h - labH - 2 * stripH - gap - 8;
        const plotW = plotR - plotL, plotH = plotB - plotT;
        const cw = plotW / n;
        const xAt = (i) => plotL + i * cw;
        const yAt = (v) => plotT + (1 - Math.max(0, Math.min(100, v)) / 100) * plotH;
        const FONT = '-apple-system, "Segoe UI", sans-serif';

        // tło kolumn: szczyt taryfy, ładowanie z sieci, sprzedaż
        for (let i = 0; i < n; i++) {
          if (c.peak && c.peak[i]) { ctx.fillStyle = 'rgba(255,159,10,0.10)'; ctx.fillRect(xAt(i), plotT, cw, plotH); }
          if (c.grid && c.grid[i]) { ctx.fillStyle = 'rgba(10,132,255,0.22)'; ctx.fillRect(xAt(i), plotT, cw, plotH); }
          if (c.sale && c.sale[i]) { ctx.fillStyle = 'rgba(48,209,88,0.26)'; ctx.fillRect(xAt(i), plotT, cw, plotH); }
        }
        // siatka i oś SOC
        ctx.lineWidth = 1; ctx.font = '10px ' + FONT; ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
        for (let g = 0; g <= 4; g++) {
          const v = g * 25, y = yAt(v);
          ctx.strokeStyle = TC('grid'); ctx.beginPath(); ctx.moveTo(plotL, y); ctx.lineTo(plotR, y); ctx.stroke();
          ctx.fillStyle = TC('muted'); ctx.fillText(v + '%', plotL - 5, y);
        }
        // granica doby
        for (let i = 0; i < n; i++) {
          if ((h0 + i) % 24 === 0 && i > 0) {
            ctx.strokeStyle = TC('line'); ctx.setLineDash([3, 3]); ctx.beginPath(); ctx.moveTo(xAt(i), plotT); ctx.lineTo(xAt(i), plotB + labH - 4); ctx.stroke(); ctx.setLineDash([]);
            ctx.fillStyle = TC('muted'); ctx.textAlign = 'left'; ctx.textBaseline = 'top'; ctx.fillText('jutro', xAt(i) + 3, plotT + 2);
          }
        }
        // próg odcięcia falownika (schodkowo)
        const fl = (c.floor || []).map(Number);
        if (fl.length) {
          ctx.strokeStyle = '#ff453a'; ctx.lineWidth = 1.5; ctx.setLineDash([5, 4]); ctx.beginPath();
          for (let i = 0; i < n; i++) { const y = yAt(isFinite(fl[i]) ? fl[i] : 0); if (i === 0) ctx.moveTo(xAt(i), y); else ctx.lineTo(xAt(i), y); ctx.lineTo(xAt(i + 1), y); }
          ctx.stroke(); ctx.setLineDash([]);
        }
        // krzywa SOC: punkt 0 = teraz (początek pierwszej godziny planu), potem SOC na koniec każdej godziny
        const pts = [[xAt(0), yAt(Number(c.soc_now))]];
        for (let i = 0; i < n; i++) pts.push([xAt(i + 1), yAt(Number(c.soc[i]))]);
        const grad = ctx.createLinearGradient(0, plotT, 0, plotB);
        grad.addColorStop(0, 'rgba(10,132,255,0.30)'); grad.addColorStop(1, 'rgba(10,132,255,0.02)');
        ctx.beginPath(); ctx.moveTo(pts[0][0], plotB); pts.forEach((q) => ctx.lineTo(q[0], q[1])); ctx.lineTo(pts[pts.length - 1][0], plotB); ctx.closePath(); ctx.fillStyle = grad; ctx.fill();
        ctx.beginPath(); pts.forEach((q, i) => { if (i === 0) ctx.moveTo(q[0], q[1]); else ctx.lineTo(q[0], q[1]); });
        ctx.strokeStyle = '#0a84ff'; ctx.lineWidth = 2.5; ctx.lineJoin = 'round'; ctx.stroke();
        // najniższy punkt
        let mi = 0; for (let i = 1; i < n; i++) if (Number(c.soc[i]) < Number(c.soc[mi])) mi = i;
        const mp = pts[mi + 1];
        ctx.fillStyle = '#0a84ff'; ctx.beginPath(); ctx.arc(mp[0], mp[1], 3.5, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = TC('text2'); ctx.font = 'bold 10px ' + FONT; ctx.textAlign = mp[0] > plotR - 30 ? 'right' : 'center'; ctx.textBaseline = 'top';
        ctx.fillText(Math.round(Number(c.soc[mi])) + '%', mp[0], Math.min(plotB - 11, mp[1] + 5));

        // etykiety godzin
        const step = cw >= 24 ? 1 : (cw >= 12 ? 2 : 3);
        ctx.fillStyle = TC('muted'); ctx.font = '10px ' + FONT; ctx.textAlign = 'center'; ctx.textBaseline = 'top';
        for (let i = 0; i < n; i += step) ctx.fillText(exHH(h0 + i), xAt(i) + cw / 2, plotB + 4);

        // paski cen: kupno (górny), sprzedaż (dolny)
        const buy = (c.buy || []).map(exNum), sell = (c.sell || []).map(exNum);
        const maxBuy = Math.max(0.01, ...buy.filter((v) => v !== null)), maxSell = Math.max(0.01, ...sell.filter((v) => v !== null && v > 0));
        const y1 = plotB + labH, y2 = y1 + stripH + 2;
        ctx.font = '9px ' + FONT; ctx.textAlign = 'right'; ctx.textBaseline = 'middle'; ctx.fillStyle = TC('muted');
        ctx.fillText('kup.', plotL - 5, y1 + stripH / 2); ctx.fillText('sprz.', plotL - 5, y2 + stripH / 2);
        for (let i = 0; i < n; i++) {
          const b = buy[i], sv = sell[i];
          ctx.fillStyle = b === null ? 'rgba(128,128,128,0.15)' : `rgba(255,159,10,${(0.18 + 0.72 * Math.min(1, b / maxBuy)).toFixed(2)})`;
          ctx.fillRect(xAt(i) + 0.5, y1, Math.max(1, cw - 1), stripH);
          ctx.fillStyle = sv === null ? 'rgba(128,128,128,0.15)' : (sv < 0 ? 'rgba(255,69,58,0.85)' : `rgba(48,209,88,${(0.18 + 0.72 * Math.min(1, sv / maxSell)).toFixed(2)})`);
          ctx.fillRect(xAt(i) + 0.5, y2, Math.max(1, cw - 1), stripH);
        }

        // podświetlenie i podpowiedź
        const tip = box.querySelector('#exPlanTip');
        const hv = s.hover;
        if (hv != null && hv >= 0 && hv < n) {
          ctx.strokeStyle = TC('text2'); ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(xAt(hv) + cw / 2, plotT); ctx.lineTo(xAt(hv) + cw / 2, y2 + stripH); ctx.stroke();
          const q = pts[hv + 1]; ctx.fillStyle = '#fff'; ctx.strokeStyle = '#0a84ff'; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(q[0], q[1], 4, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
          if (tip) {
            const flags = [];
            if (c.grid && c.grid[hv]) { const t = exNum((c.target || [])[hv]); flags.push('🔌 ładowanie z sieci' + (t ? ` do ${Math.round(t)}%` : '')); }
            if (c.sale && c.sale[hv]) flags.push('💰 sprzedaż z baterii');
            if (c.peak && c.peak[hv]) flags.push('szczyt taryfy');
            tip.innerHTML = `<b>${exHH(h0 + hv)}:00–${exHH(h0 + hv + 1)}:00</b><br>SOC na koniec: <b>${exFmt(c.soc[hv], 0, '%')}</b> (próg ${exFmt(fl[hv], 0, '%')})<br>PV ${exFmt((c.pv || [])[hv], 1)} kWh · dom ${exFmt((c.load || [])[hv], 1)} kWh<br>kupno ${exFmt(buy[hv], 2)} · sprzedaż ${exFmt(sell[hv], 2)} zł/kWh${flags.length ? '<br>' + flags.join(' · ') : ''}`;
            tip.hidden = false;
            const tw = tip.offsetWidth || 160;
            let left = xAt(hv) + cw / 2 + 10; if (left + tw > w - 2) left = xAt(hv) + cw / 2 - tw - 10; if (left < 2) left = 2;
            tip.style.left = left + 'px'; tip.style.top = (plotT + 4) + 'px';
          }
        } else if (tip) tip.hidden = true;
      },
    });

    // =====================================================================
    //  RAPORT MIESIĘCZNY i ZDROWIE BATERII (zakładka „Zysk i log”)
    // =====================================================================
    const exPct = (v, d) => { const n = exNum(v); return n === null ? '—' : n.toFixed(d == null ? 0 : d).replace('.', ',') + '%'; };
    const exTile = (l, v, s) => `<div class="ex-tile"><div class="l">${l}</div><div class="v">${v}</div>${s ? `<div class="s">${s}</div>` : ''}</div>`;
    const EX_MONTHS = ['styczeń', 'luty', 'marzec', 'kwiecień', 'maj', 'czerwiec', 'lipiec', 'sierpień', 'wrzesień', 'październik', 'listopad', 'grudzień'];
    const exMonthTitle = (y, m) => { const n = EX_MONTHS[m - 1] || ''; return n ? n.charAt(0).toUpperCase() + n.slice(1) + ' ' + y : '…'; };
    const exMonthShift = (year, month, delta) => { const t = year * 12 + (month - 1) + delta; return [Math.floor(t / 12), (t % 12) + 1]; };

    Object.assign(BmsPanel.prototype, {
      _exReport() {
        const box = this._el('exReportBox'); if (!box) return;
        const s = this._exS(), r = s.rep;
        if (!box.dataset.exBound) {
          box.dataset.exBound = '1';
          box.addEventListener('click', (ev) => {
            const b = ev.target && ev.target.closest ? ev.target.closest('[data-ex]') : null;
            if (!b) return;
            const a = b.dataset.ex;
            if (a === 'rep-prev' || a === 'rep-next' || a === 'rep-now') this._exRepGo(a);
          });
        }
        const st = this._hass.states[this._eid('sensor', 'monthly_report')];
        const cur = st && st.attributes && st.attributes.year ? st.attributes : null;
        const rep = r.year == null ? cur : r.data;
        const key = JSON.stringify([r.year, r.month, r.loading, r.err, rep ? [rep.year, rep.month, rep.net, rep.days_with_data, rep.export_kwh, rep.import_kwh, rep.pv_kwh, rep.saving_estimate] : null, TC('text')]);
        if (box.dataset.exKey === key) return;
        box.dataset.exKey = key;
        if (!rep && !r.loading && !r.err) {
          box.innerHTML = st ? '<div class="chart-empty">Raport jeszcze się nie policzył — pojawi się po kilku minutach pracy integracji.</div>'
            : '<div class="chart-empty" style="color:var(--red);">Brak sensora raportu — zaktualizuj integrację i zrestartuj Home Assistant.</div>';
          return;
        }
        const isCur = r.year == null;
        const title = rep ? rep.title : (r.year != null ? exMonthTitle(r.year, r.month) : '…');
        const nav = `<div class="ex-nav">
          <button type="button" class="btn" data-ex="rep-prev" style="padding:6px 12px;" ${r.loading ? 'disabled' : ''} aria-label="Poprzedni miesiąc">◀</button>
          <div style="text-align:center;"><b>${exEsc(title)}</b>${rep ? `<div class="ex-note" style="margin:2px 0 0;">${rep.complete ? 'pełny miesiąc' : `dane z ${rep.days_with_data} z ${rep.days_in_month} dni`}${isCur ? ' · bieżący' : ''}</div>` : ''}</div>
          <button type="button" class="btn" data-ex="rep-next" style="padding:6px 12px;" ${r.loading || isCur ? 'disabled' : ''} aria-label="Następny miesiąc">▶</button></div>`;
        if (r.loading || !rep) { box.innerHTML = nav + `<div class="chart-empty">${r.err ? 'Błąd: ' + exEsc(r.err) : 'Ładowanie raportu…'}</div>`; return; }
        if (r.err) { box.innerHTML = nav + `<div class="chart-empty" style="color:var(--red);">Błąd: ${exEsc(r.err)}</div>`; return; }
        if (!rep.days_with_data) { box.innerHTML = nav + '<div class="chart-empty">Brak danych za ten miesiąc — bilans liczy się od chwili uruchomienia integracji.</div>'; return; }
        const col = (v) => (exNum(v) === null ? 'inherit' : (Number(v) >= 0 ? 'var(--green)' : 'var(--red)'));
        const tiles = [
          exTile('Bilans z siecią', `<span style="color:${col(rep.net)}">${exMoney(rep.net)}</span>`, `sprzedaż − zakup`),
          exTile('Sprzedaż do sieci', exMoney(rep.revenue).replace(/^\+/, ''), `${exFmt(rep.export_kwh, 1)} kWh · śr. ${exFmt(rep.avg_sell_price, 2)} zł/kWh`),
          exTile('Zakup z sieci', exMoney(rep.cost).replace(/^\+/, ''), `${exFmt(rep.import_kwh, 1)} kWh · śr. ${exFmt(rep.avg_buy_price, 2)} zł/kWh`),
        ];
        if (rep.pv_kwh != null) tiles.push(exTile('Produkcja PV', exFmt(rep.pv_kwh, 0, ' kWh'), rep.self_consumption_pct != null ? `autokonsumpcja ${exPct(rep.self_consumption_pct)}` : ''));
        if (rep.load_kwh != null) tiles.push(exTile('Zużycie domu', exFmt(rep.load_kwh, 0, ' kWh'), rep.self_sufficiency_pct != null ? `samowystarczalność ${exPct(rep.self_sufficiency_pct)}` : ''));
        if (rep.battery_charge_kwh != null) tiles.push(exTile('Bateria', `${exFmt(rep.battery_charge_kwh, 0)} / ${exFmt(rep.battery_discharge_kwh, 0)} kWh`, `ładowanie / rozładowanie${rep.cycle_efficiency_pct != null ? ` · sprawność ${exPct(rep.cycle_efficiency_pct, 0)}` : ''}`));
        if (rep.saving_estimate != null) tiles.push(exTile('Oszczędność (szacunek)', `<span style="color:${col(rep.saving_estimate)}">${exMoney(rep.saving_estimate).replace(/^\+/, '')}</span>`, 'orientacyjnie, względem braku PV i baterii'));
        const days = Array.isArray(rep.days) ? rep.days : [];
        const bars = days.length > 1 ? (typeof this._balanceSvg === 'function' ? this._balanceSvg(days, '') : '') : '';
        const best = rep.best_day ? `<div>🏆 Najlepszy dzień: <b>${exEsc(rep.best_day.date)}</b> (${exEsc(exMoney(rep.best_day.net))})</div>` : '';
        const worst = rep.worst_day && rep.days_with_data > 1 ? `<div>📉 Najsłabszy dzień: <b>${exEsc(rep.worst_day.date)}</b> (${exEsc(exMoney(rep.worst_day.net))})</div>` : '';
        const neg = Number(rep.neg_export_kwh) > 0.05 ? `<div>⚠ Energia oddana przy ujemnej cenie RCE: <b>${exFmt(rep.neg_export_kwh, 1)} kWh</b></div>` : '';
        box.innerHTML = nav + `<div class="ex-tiles">${tiles.join('')}</div>${bars}
          <div class="ex-lines">${best}${worst}${neg}</div>
          <div class="ex-note">Bilans liczony jest z mocy sieci i cen chwilowych (jak „Bilans w PLN” wyżej), więc może się różnić od rachunku. „Oszczędność” to szacunek: koszt zużytej energii po średniej cenie zakupu z tego miesiąca minus faktyczny bilans — bez opłat stałych.</div>`;
      },

      async _exRepGo(action) {
        const s = this._exS(), r = s.rep;
        if (r.loading) return;
        const st = this._hass.states[this._eid('sensor', 'monthly_report')];
        const cur = st && st.attributes && st.attributes.year ? st.attributes : null;
        const y0 = r.year != null ? r.year : ((cur && cur.year) || new Date().getFullYear());
        const m0 = r.year != null ? r.month : ((cur && cur.month) || (new Date().getMonth() + 1));
        if (action === 'rep-now') { r.year = null; r.month = null; r.data = null; r.err = ''; this._exLog(); return; }
        const [y, m] = exMonthShift(y0, m0, action === 'rep-prev' ? -1 : 1);
        const today = new Date();
        if (y > today.getFullYear() || (y === today.getFullYear() && m >= today.getMonth() + 1)) { r.year = null; r.month = null; r.data = null; r.err = ''; this._exLog(); return; }
        if (y < today.getFullYear() - 3) return;
        r.loading = true; r.err = ''; r.year = y; r.month = m; r.data = null; this._exLog();
        try {
          const res = exResp(await exCall(this, 'monthly_report', { year: y, month: m }));
          if (r.year === y && r.month === m) r.data = res && res.year ? res : null;
          if (r.year === y && r.month === m && !r.data) r.err = 'nieprawidłowa odpowiedź integracji';
        } catch (e) { r.err = exErr(e); }
        finally { r.loading = false; }
        this._exLog();
      },

      _exHealth() {
        const box = this._el('exHealthBox'); if (!box) return;
        const st = this._hass.states[this._eid('sensor', 'battery_health')];
        if (!st) { box.innerHTML = '<div class="chart-empty" style="color:var(--red);">Brak sensora zdrowia baterii — zaktualizuj integrację i zrestartuj Home Assistant.</div>'; return; }
        const a = st.attributes || {};
        const key = JSON.stringify([a.eff_7d, a.eff_30d, a.eff_90d, a.days_7d, a.days_30d, a.days_90d, a.eff_trend_pp, a.capacity_est_kwh, a.capacity_samples, a.capacity_configured_kwh, a.soh_est_pct, TC('text')]);
        if (box.dataset.exKey === key) return;
        box.dataset.exKey = key;
        const effTile = (l, e, n) => exTile(l, exPct(e, 1), e == null ? 'za mało pełnych dób' : `z ${n} ${n === 1 ? 'doby' : 'dób'}`);
        const tr = exNum(a.eff_trend_pp);
        const trend = tr === null ? exTile('Trend sprawności', '—', 'potrzeba ≥ 15 dób w 90 dniach')
          : exTile('Trend sprawności', `<span style="color:${tr >= -0.5 ? 'var(--green)' : (tr >= -2 ? 'var(--orange)' : 'var(--red)')}">${tr >= 0 ? '+' : '−'}${Math.abs(tr).toFixed(1).replace('.', ',')} pp</span>`, 'ostatnie 30 dni względem 90');
        const est = exNum(a.capacity_est_kwh), conf = exNum(a.capacity_configured_kwh), soh = exNum(a.soh_est_pct);
        const capTile = est === null
          ? exTile('Pojemność (szacunek)', '—', a.capacity_samples ? `za mało pełnych cykli (${a.capacity_samples}/3)` : 'czeka na długie ładowanie (≥ 15 pkt SOC)')
          : exTile('Pojemność (szacunek)', exFmt(est, 1, ' kWh'), `ustawiona ${exFmt(conf, 1)} kWh · ${a.capacity_samples} pomiarów`);
        const sohTile = soh === null ? '' : exTile('Stosunek do ustawionej', `${soh.toFixed(0)}%`, 'orientacyjnie, nie jest pomiarem SOH');
        let hint = '';
        if (soh !== null && (soh < 80 || soh > 115)) hint = `<div class="ex-chip warn" style="display:inline-block;margin-top:10px;">Szacunek znacznie odbiega od ustawionej pojemności (${exFmt(conf, 1)} kWh) — sprawdź, czy pojemność w konfiguracji integracji jest prawidłowa.</div>`;
        box.innerHTML = `<div class="ex-tiles">${effTile('Sprawność cyklu 7 dni', a.eff_7d, a.days_7d)}${effTile('30 dni', a.eff_30d, a.days_30d)}${effTile('90 dni', a.eff_90d, a.days_90d)}${trend}${capTile}${sohTile}</div>${hint}
          <div class="ex-note">Sprawność cyklu = energia oddana (z poprawką na zmianę SOC) ÷ energia pobrana, liczona dla dób z wyraźnym ładowaniem (≥ 2 kWh) i pełnymi danymi. Pojemność jest szacowana z odcinków ładowania (mediana ostatnich pomiarów); SOC falownika jest zaokrąglany, więc to wskazówka, a nie pomiar zdrowia baterii.</div>`;
      },
    });

    // =====================================================================
    //  OSZCZĘDNOŚCI (3 warianty) i TRAFNOŚĆ PROGNOZ — dane z usługi insights_get (co 5 min)
    // =====================================================================
    const EX_PERIODS = [['today', 'dziś'], ['last30', '30 dni'], ['month', 'ten miesiąc'], ['year', 'ten rok'], ['total', 'od początku']];
    const exDay = (iso) => { const m = /^(\d{4})-(\d\d)-(\d\d)/.exec(String(iso || '')); return m ? `${m[3]}.${m[2]}` : String(iso || ''); };
    const exPairBars = (rows, fk, ak, unit, colAct) => {
      const vals = []; rows.forEach((r) => { [r[fk], r[ak]].forEach((v) => { if (exNum(v) !== null) vals.push(Number(v)); }); });
      if (!vals.length) return '<div class="chart-empty">Brak danych.</div>';
      const mx = Math.max(...vals, 0.01);
      const cols = rows.map((r) => {
        const f = exNum(r[fk]), a = exNum(r[ak]);
        const h = (v) => (v === null ? 0 : Math.max(1, Math.round(v / mx * 100)));
        const tip = `${exDay(r.date)}: prognoza ${exFmt(f, 1)} ${unit}, wykonanie ${exFmt(a, 1)} ${unit}`;
        return `<div title="${exEsc(tip)}" style="flex:1;display:flex;align-items:flex-end;gap:1px;height:100%;min-width:0;">
          <div style="flex:1;height:${h(f)}%;background:var(--muted);opacity:.45;border-radius:2px 2px 0 0;"></div>
          <div style="flex:1;height:${h(a)}%;background:${a === null ? 'transparent' : colAct};border-radius:2px 2px 0 0;"></div></div>`;
      }).join('');
      return `<div style="display:flex;align-items:flex-end;gap:2px;height:90px;">${cols}</div>
        <div style="display:flex;justify-content:space-between;font-size:10px;color:var(--muted);margin-top:3px;"><span>${exEsc(exDay(rows[0].date))}</span><span>${exEsc(exDay(rows[rows.length - 1].date))}</span></div>`;
    };

    Object.assign(BmsPanel.prototype, {
      async _exInsLoad() {
        const s = this._exS().ins;
        if (s.loading) return;
        s.loading = true;
        try { s.data = exResp(await exCall(this, 'insights_get', {})) || {}; s.err = ''; s.at = Date.now(); }
        catch (e) { s.err = exErr(e); s.at = Date.now(); }
        finally { s.loading = false; }
        this._exInsights();
      },
      _exInsights() {
        const sb = this._el('exSavBox'), ab = this._el('exAccBox');
        if (!sb && !ab) return;
        const s = this._exS().ins;
        if (!s.loading && Date.now() - s.at > 300000) this._exInsLoad();
        [sb, ab].forEach((box) => {
          if (!box || box.dataset.exBound) return;
          box.dataset.exBound = '1';
          box.addEventListener('click', (ev) => {
            const b = ev.target && ev.target.closest ? ev.target.closest('[data-exi]') : null;
            if (!b) return;
            if (b.dataset.exi === 'period') { s.period = b.dataset.p; this._exInsights(); }
            else if (b.dataset.exi === 'reload') { s.at = 0; this._exInsights(); }
          });
        });
        const key = JSON.stringify([s.at, s.err, s.period, !!s.data, TC('text')]);
        if (sb && sb.dataset.exKey !== key) { sb.dataset.exKey = key; sb.innerHTML = this._exSavHtml(); }
        if (ab && ab.dataset.exKey !== key) { ab.dataset.exKey = key; ab.innerHTML = this._exAccHtml(); }
      },
      _exSavHtml() {
        const s = this._exS().ins;
        if (!s.data) {
          if (s.err) return `<div class="chart-empty" style="color:var(--red);">Nie udało się wczytać: ${exEsc(s.err)}</div><div class="ex-note">Wymaga integracji 0.8.5 lub nowszej.</div><button class="btn" data-exi="reload" style="margin-top:8px;">Spróbuj ponownie</button>`;
          return '<div class="chart-empty">Ładowanie…</div>';
        }
        const sv = s.data.savings || {};
        const p = sv[s.period] || {};
        const pills = EX_PERIODS.map(([k, l]) => `<button class="btn" data-exi="period" data-p="${k}" style="padding:5px 12px;font-size:12px;${s.period === k ? 'background:var(--accent,#0a84ff);color:#fff;' : ''}">${l}</button>`).join('');
        const col = (v) => (exNum(v) === null ? 'inherit' : (Number(v) >= 0 ? 'var(--green)' : 'var(--red)'));
        const cost = (v) => { const n = exNum(v); return n === null ? '—' : (n < 0 ? '−' : '') + Math.abs(n).toFixed(2).replace('.', ',') + ' zł'; };
        if (!p.days) {
          return `<div class="ex-nav" style="justify-content:flex-start;flex-wrap:wrap;gap:6px;">${pills}</div>
            <div class="chart-empty">Brak danych za ten okres. Oszczędności liczą się od dnia instalacji wersji 0.8.5 — pierwszy pełny dzień pojawi się jutro.</div>`;
        }
        const tiles = [
          exTile('Zapłaciłeś', cost(p.actual), 'zakup z sieci minus to, co sprzedałeś'),
          exTile('Bez baterii zapłaciłbyś', cost(p.nobat), 'ten sam dom i PV, ale bez magazynu'),
          exTile('Z samą baterią (bez EMS)', cost(p.simple), 'bateria ładuje się tylko z nadwyżki PV'),
          exTile('Oszczędność', `<span style="color:${col(p.vs_nobat)}">${exMoney(p.vs_nobat)}</span>`, 'dzięki baterii i EMS, wobec domu bez baterii'),
          exTile('Z tego zasługa EMS', `<span style="color:${col(p.vs_simple)}">${exMoney(p.vs_simple)}</span>`, 'różnica wobec baterii działającej „samej” (minus = EMS wypadł gorzej)'),
        ];
        const daily = (sv.daily || []).filter((d) => d.complete || d.partial).slice(-30);
        let bars = '';
        if (daily.length > 1) {
          const vals = daily.map((d) => Number(d.nobat) - Number(d.actual));
          const mx = Math.max(...vals.map((v) => Math.abs(v)), 0.01);
          bars = `<div style="font-size:11px;color:var(--muted);margin-top:12px;">Oszczędność dzień po dniu (względem braku baterii)</div>
            <div style="display:flex;align-items:center;gap:2px;height:80px;margin-top:4px;">${daily.map((d, i) => {
              const v = vals[i]; const h = Math.max(2, Math.round(Math.abs(v) / mx * 48));
              const tip = `${exDay(d.date)}${d.partial ? ' (dziś, do teraz)' : ''}: ${exMoney(v)} · koszt ${cost(d.actual)}, bez baterii ${cost(d.nobat)}, bateria bez planera ${cost(d.simple)}`;
              return `<div title="${exEsc(tip)}" style="flex:1;min-width:0;height:100%;display:flex;flex-direction:column;justify-content:center;">
                <div style="height:${v >= 0 ? h : 0}px;background:var(--green);opacity:${d.partial ? 0.5 : 1};border-radius:2px 2px 0 0;align-self:stretch;margin-top:auto;"></div>
                <div style="height:${v < 0 ? h : 0}px;background:var(--red);opacity:${d.partial ? 0.5 : 1};border-radius:0 0 2px 2px;margin-bottom:auto;"></div></div>`;
            }).join('')}</div>`;
        }
        const pr = sv.params || {};
        return `<div class="ex-nav" style="justify-content:flex-start;flex-wrap:wrap;gap:6px;">${pills}</div>
          <div class="ex-tiles">${tiles.join('')}</div>${bars}
          <div class="ex-note">Z ${p.days} ${p.days === 1 ? 'dnia' : 'dni'}${sv.since ? `, dane od ${exEsc(exDay(sv.since))}` : ''}. Dzisiejszy dzień liczony do bieżącej godziny. Ceny godzinowe, bez opłat stałych.
            Porównuję 3 sytuacje: dom bez baterii · bateria bez sterowania · bateria z EMS (Twoja).
            Bateria ${exFmt(pr.cap, 1)} kWh, sprawność ${exPct((exNum(pr.eff) || 0) * 100)}, próg ${exPct(pr.floor)}.</div>`;
      },
      _exAccHtml() {
        const s = this._exS().ins;
        if (!s.data) return s.err ? `<div class="chart-empty" style="color:var(--red);">Nie udało się wczytać: ${exEsc(s.err)}</div>` : '<div class="chart-empty">Ładowanie…</div>';
        const ac = s.data.accuracy || {};
        const pv = ac.pv || {}, ld = ac.load || {}, so = ac.soc || {}, pc = ac.pv_correction || {};
        const bias = (b) => { const n = exNum(b); return n === null ? '' : (n > 0 ? `prognoza zawyżona o ${exPct(n)}` : (n < 0 ? `prognoza zaniżona o ${exPct(-n)}` : 'bez stałego odchylenia')); };
        const errCol = (m) => { const n = exNum(m); return n === null ? 'inherit' : (n <= 15 ? 'var(--green)' : (n <= 30 ? 'var(--orange)' : 'var(--red)')); };
        const fac = exNum(pc.factor);
        const corrTxt = !s.data.pv_correction_on ? 'wyłączona przełącznikiem' : (pc.days >= 5 ? `z ${pc.days} dni${exNum(pc.ratio) !== null ? `, wykonanie / prognoza ${exFmt(pc.ratio, 2)}` : ''}` : `czeka na ≥ 5 dni z prognozą ≥ 1 kWh (jest ${pc.days || 0})`);
        const tiles = [
          exTile('Prognoza PV — błąd', `<span style="color:${errCol(pv.mape)}">${exPct(pv.mape, 1)}</span>`, pv.n ? `${bias(pv.bias)} · ${pv.n} dni` : 'zbiera dane (prognoza z rana vs wykonanie)'),
          exTile('Prognoza zużycia — błąd', `<span style="color:${errCol(ld.mape)}">${exPct(ld.mape, 1)}</span>`, ld.n ? `${bias(ld.bias)} · ${ld.n} dni` : 'brak historii'),
          exTile('Plan SOC — błąd', exNum(so.mae) === null ? '—' : exFmt(so.mae, 1, ' pp'), so.n ? `średnio na godzinę · ${so.n} dni` : 'zbiera dane (plan z rana vs SOC)'),
          exTile('Korekta PV dziś', s.data.pv_correction_on && fac !== null ? '× ' + exFmt(fac, 2) : '—', corrTxt),
        ];
        const rows = (ac.days || []).slice(-30);
        const pvRows = rows.filter((r) => r.pv_fc !== null || r.pv_act !== null);
        const ldRows = rows.filter((r) => r.load_fc !== null || r.load_act !== null);
        const charts = (pvRows.length > 1 ? `<div style="font-size:11px;color:var(--muted);margin-top:12px;">Produkcja PV: prognoza (szary) i wykonanie, kWh/dzień</div>${exPairBars(pvRows, 'pv_fc', 'pv_act', 'kWh', 'var(--orange,#ff9f0a)')}` : '')
          + (ldRows.length > 1 ? `<div style="font-size:11px;color:var(--muted);margin-top:12px;">Zużycie domu: prognoza (szary) i wykonanie, kWh/dzień</div>${exPairBars(ldRows, 'load_fc', 'load_act', 'kWh', 'var(--accent,#0a84ff)')}` : '');
        const hz = Array.isArray(ac.pv_by_horizon) ? ac.pv_by_horizon : [];
        const hzName = (h) => h === 0 ? 'dziś' : h === 1 ? 'jutro' : `za ${h} dni`;
        const hzRows = hz.map((r) => `<tr><td>${hzName(r.h)}</td><td style="text-align:right;">${r.n || 0}</td>
            <td style="text-align:right;color:${errCol(r.mape)}">${exPct(r.mape, 1)}</td>
            <td style="text-align:right;color:${errCol(r.mape_adj)}">${r.n_adj >= 3 ? exPct(r.mape_adj, 1) : '—'}</td>
            <td style="text-align:right;">${s.data.pv_correction_on ? '× ' + exFmt(r.factor, 2) : '—'}</td>
            <td style="text-align:right;">± ${exPct((exNum(r.spread) || 0) * 100)}</td></tr>`).join('');
        const hzTable = hz.length ? `<div style="font-size:11px;color:var(--muted);margin-top:12px;">Prognoza PV: błąd osobno dla każdego dnia do przodu</div>
          <div style="overflow-x:auto;"><table data-role="pv-horizon" style="width:100%;border-collapse:collapse;font-size:12px;margin-top:4px;">
            <thead><tr style="color:var(--muted);text-align:right;"><th style="text-align:left;font-weight:600;">Dzień</th><th style="font-weight:600;">Dni danych</th><th style="font-weight:600;">Błąd surowej</th><th style="font-weight:600;">Błąd po korekcie</th><th style="font-weight:600;">Korekta</th><th style="font-weight:600;">Zakres</th></tr></thead>
            <tbody>${hzRows}</tbody></table></div>` : '';
        const hzTune = (() => {
          const tn = hz.filter((r) => r.tune && r.tune.mae != null);
          if (!tn.length) return '';
          const ch = tn.filter((r) => r.tune.window !== 30 || r.tune.mode !== 'median');
          const nm = (t) => `${t.window} dni${t.mode === 'ewma' ? ', świeższe dni ważniejsze' : ''}`;
          return `<div class="ex-note" data-role="pv-tune">🎯 Samostrojenie PV: EMS co dobę sprawdza okno uczenia (7, 14 albo 30 dni) na Twojej historii. ${ch.length
            ? ch.map((r) => `${hzName(r.h)}: ${nm(r.tune)} (błąd ${exFmt(r.tune.mae, 2)} kWh zamiast ${exFmt(r.tune.mae_default, 2)} kWh)`).join('; ') + '.'
            : 'Na razie standardowe 30 dni jest najlepsze albo żaden wariant nie był wyraźnie lepszy.'}</div>`;
        })();
        return `<div class="ex-tiles">${tiles.join('')}</div>${hzTable}${hzTune}${charts}
          <div class="ex-note">Błąd to średnia różnica prognozy i wykonania w procentach (dni z co najmniej 0,5 kWh), z ostatnich 30 dni. Prognoza PV jest zapisywana rano (od 6:00) dla każdego z 7 dni do przodu, prognoza zużycia — dzień wcześniej.
            Korekta PV jest liczona osobno dla każdego dnia do przodu (mediana wykonania do prognozy z 30 dni, w granicach 0,5–1,4), uwzględnia stały wzorzec godzinowy i poprawia dzisiejszy dzień na podstawie godzin, które już minęły.
            Dni, w których bateria była pełna i falownik ucinał produkcję, nie uczą modelu. „Błąd po korekcie” liczony jest z prognoz faktycznie wydanych po korekcie, więc pokazuje, czy korekta pomaga. Zakres to typowy błąd tego dnia.</div>`;
      },
    });

    // =====================================================================
    //  KREATOR INSTALACJI: sprawdzenie konfiguracji i podgląd komend BEZ wysyłania czegokolwiek do falownika
    // =====================================================================
    const EX_ST_ICON = { ok: '✅', warn: '⚠️', error: '❌' };

    Object.assign(BmsPanel.prototype, {
      _exWiz() {
        const box = this._el('exWizBox');
        if (!box || this._activeTab !== 'diag') return;
        const s = this._exS(), w = s.wiz;
        if (!box.dataset.exBound) {
          box.dataset.exBound = '1';
          box.addEventListener('click', (ev) => {
            const b = ev.target && ev.target.closest ? ev.target.closest('[data-ex]') : null;
            if (!b) return;
            if (b.dataset.ex === 'wiz-run') this._exWizRun();
            else if (b.dataset.ex === 'wiz-copy') this._exWizCopy();
          });
        }
        const key = JSON.stringify([w.state, w.err, w.data ? [w.data.summary, w.data.version, (w.data.checks || []).length] : null, TC('text')]);
        if (box.dataset.exKey === key) return;
        box.dataset.exKey = key;
        const intro = 'Kreator sprawdza, czy integracja widzi encje falownika (tryb pracy, prąd ładowania, moc eksportu, TOU), czy działają ceny RCE i prognoza PV oraz co wykonałby każdy przycisk. <b>Niczego nie wysyła do falownika</b> — to tylko odczyt i podgląd.';
        const runBtn = (label) => `<button type="button" class="btn" data-ex="wiz-run" style="padding:10px 16px;flex-direction:row;gap:8px;" ${w.state === 'loading' ? 'disabled' : ''}><span>🧭</span><span class="label">${label}</span></button>`;
        if (w.state === 'idle') { box.innerHTML = `<div class="ex-note" style="margin:0 0 12px;font-size:12px;">${intro}</div>${runBtn('Sprawdź konfigurację')}`; return; }
        if (w.state === 'loading') { box.innerHTML = `<div class="chart-empty">Sprawdzam konfigurację…</div>`; return; }
        if (w.state === 'error') {
          box.innerHTML = `<div class="ex-chip bad" style="display:block;border-radius:12px;padding:10px 12px;margin-bottom:10px;">Nie udało się wykonać sprawdzenia: ${exEsc(w.err)}</div><div class="ex-note" style="margin:0 0 12px;">Kreator wymaga konta administratora Home Assistant i integracji w wersji z usługą <code>health_check</code>.</div>${runBtn('Spróbuj ponownie')}`;
          return;
        }
        const d = w.data || {}, sm = d.summary || {};
        const head = sm.ready
          ? `<span class="ex-chip ok">✅ gotowe do pracy</span>`
          : `<span class="ex-chip bad">❌ do poprawy: ${exEsc(sm.errors || 0)} błędów${sm.commands_failing ? `, ${exEsc(sm.commands_failing)} komend nie zadziała` : ''}</span>`;
        const chips = `<div class="ex-sum">${head}${sm.warnings ? `<span class="ex-chip warn">⚠ ${exEsc(sm.warnings)} uwag</span>` : ''}<span class="ex-chip">${exEsc(sm.ok || 0)} poprawnych</span>${d.version ? `<span class="ex-chip">wersja ${exEsc(d.version)}</span>` : ''}</div>`;
        const order = { error: 0, warn: 1, ok: 2 };
        const checks = (d.checks || []).slice().sort((a, b) => (order[a.status] ?? 3) - (order[b.status] ?? 3)).map((c) => `
          <div class="ex-chk"><span class="ic">${EX_ST_ICON[c.status] || '•'}</span><div><b>${exEsc(c.title)}</b><div>${exEsc(c.detail)}</div>${c.fix ? `<div class="fix">→ ${exEsc(c.fix)}</div>` : ''}</div></div>`).join('');
        const cmds = (d.commands || []).map((c) => `
          <details class="ex-cmd"${c.ok ? '' : ' open'}><summary><span>${c.ok ? '✅' : '❌'}</span><span>${exEsc(c.label)}</span></summary>
            ${c.error ? `<div class="st" style="color:var(--red);">${exEsc(c.error)}</div>` : ''}
            ${(c.steps || []).map((x) => `<div class="st">${x.exists ? '' : '⚠ '}<code>${exEsc(x.domain)}.${exEsc(x.domain === 'button' ? 'press' : 'set')}</code> → <code>${exEsc(x.entity_id)}</code>${x.value !== undefined && x.value !== null && x.value !== '' ? ` = <b>${exEsc(x.value)}</b>` : ''}</div>`).join('')}
          </details>`).join('');
        box.innerHTML = `${chips}${checks || '<div class="chart-empty">Brak wyników.</div>'}
          <div class="section-title" style="margin:16px 0 4px;padding-left:0;">Co zrobią przyciski (podgląd)</div>${cmds || '<div class="ex-note">Brak komend do wyświetlenia.</div>'}
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:14px;">${runBtn('Sprawdź ponownie')}
            <button type="button" class="btn" data-ex="wiz-copy" style="padding:10px 16px;flex-direction:row;gap:8px;"><span>📋</span><span class="label">Kopiuj raport</span></button></div>
          <div class="ex-note">Raport można wkleić znajomemu lub przy zgłaszaniu problemu — zawiera nazwy encji i wyniki testów, bez haseł i adresów.</div>`;
      },

      async _exWizRun() {
        const s = this._exS(), w = s.wiz;
        if (w.state === 'loading') return;
        w.state = 'loading'; w.err = ''; this._exWiz();
        try {
          const res = exResp(await exCall(this, 'health_check', {}));
          if (!res || !Array.isArray(res.checks)) throw new Error('nieprawidłowa odpowiedź integracji');
          w.data = res; w.state = 'done';
        } catch (e) { w.state = 'error'; w.err = exErr(e); }
        this._exWiz();
      },

      _exWizText() {
        const d = this._exS().wiz.data; if (!d) return '';
        const out = [`EMS komp-dec ${d.version || ''} — raport konfiguracji`, ''];
        (d.checks || []).forEach((c) => out.push(`[${String(c.status).toUpperCase()}] ${c.title}: ${c.detail}${c.fix ? ' → ' + c.fix : ''}`));
        out.push('', 'Komendy:');
        (d.commands || []).forEach((c) => {
          out.push(`${c.ok ? '[OK]' : '[BŁĄD]'} ${c.label}${c.error ? ' — ' + c.error : ''}`);
          (c.steps || []).forEach((x) => out.push(`    ${x.entity_id}${x.value !== undefined && x.value !== null && x.value !== '' ? ' = ' + x.value : ''}${x.exists ? '' : ' (brak encji)'}`));
        });
        return out.join('\n');
      },

      async _exWizCopy() {
        const txt = this._exWizText(); if (!txt) return;
        try {
          if (!navigator.clipboard || !navigator.clipboard.writeText) throw new Error('schowek niedostępny');
          await navigator.clipboard.writeText(txt);
          this._showToast('✅ Skopiowano raport');
        } catch (e) {
          this._showToast('❌ Nie udało się skopiować — ' + exErr(e), true);
        }
      },
    });

  };
  install.contract = 1;
  install.version = '0.9.4';
  window.__bmsExtrasInstall = install;
})();
